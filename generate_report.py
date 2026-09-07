# AI生成
#!/usr/bin/env python3
"""
独立日报生成脚本 - 在 GitHub Actions 中运行
功能：搜索当日汽车行业新闻 → 生成7维度案例报告 → 输出HTML + 更新data.js

支持两种模式：
1. LLM增强模式：使用OpenAI兼容API生成STAR/PDCA深度分析（推荐）
2. 纯搜索模式：仅基于搜索结果生成简要报告（无需LLM API Key）

搜索API支持（按优先级）：
1. DeepSeek联网搜索（Anthropic端点）- 仅需LLM_API_KEY，搜索+分析一体化（推荐）
2. SerpAPI (https://serpapi.com) - 100次/月免费（需SERPAPI_KEY）
3. NewsAPI (https://newsapi.org) - 开发者免费100次/天（需NEWS_API_KEY）

DeepSeek联网搜索原理：
  调用 https://api.deepseek.com/anthropic/v1/messages 端点，
  传入 tools=[{"type": "web_search_20250305", "name": "web_search"}]，
  DeepSeek自动联网搜索并返回结构化结果。
  注意：type必须使用版本化名称(web_search_20250305或web_search_20260209)，
  不能用裸名"web_search"，否则HTTP 400报错。
  搜索消耗约3倍标准token。
"""

import json
import os
import re
import sys
import html as html_mod
from datetime import datetime, timedelta
from pathlib import Path

# ============ 配置 ============
SITE_DIR = Path(".")  # GitHub Actions 工作目录即为仓库根
REPORTS_DIR = SITE_DIR / "reports"
DATA_JS_PATH = SITE_DIR / "data.js"

# 7大维度定义（汽车行业用户运营视角）
CATEGORIES = [
    {"id": "brand-marketing",    "name": "汽车营销与品牌传播", "color": "#6366f1", "icon": "🚗"},
    {"id": "user-growth",        "name": "用户运营与私域增长", "color": "#f59e0b", "icon": "🎯"},
    {"id": "offline-experience", "name": "线下体验与场景运营", "color": "#10b981", "icon": "🎪"},
    {"id": "digital-content",    "name": "数字化与内容生态", "color": "#3b82f6", "icon": "📱"},
    {"id": "crossover-eco",      "name": "跨界与生态联动",   "color": "#ec4899", "icon": "🔄"},
    {"id": "industry-trend",     "name": "行业趋势与对标洞察", "color": "#8b5cf6", "icon": "📊"},
    {"id": "emotion-economy",    "name": "情绪经济与情感价值", "color": "#14b8a6", "icon": "💜"},
]

# 每个维度的搜索关键词（使用新闻热点词汇，便于搜索引擎匹配）
DIMENSION_QUERIES = {
    "brand-marketing":    "汽车 营销 品牌 新品上市 营销文案 2026",
    "user-growth":        "汽车 用户运营 私域 KOC 车主社区 会员体系 2026",
    "offline-experience": "汽车 试驾 车主活动 车友会 快闪店 交付仪式 2026",
    "digital-content":    "汽车 短视频 直播 智能座舱 AIGC 数据运营 2026",
    "crossover-eco":      "汽车 跨界联名 异业合作 IP营销 生活方式 2026",
    "industry-trend":     "汽车 新能源 出海 政策补贴 用户代际 2026",
    "emotion-economy":    "汽车 情绪价值 情感营销 品牌人设 治愈体验 2026",
}

# ============ 搜索模块 ============
def _parse_search_text(text, results_list, max_results):
    """从DeepSeek返回的文本中智能提取搜索结果

    处理多种格式：
    - Markdown编号列表（### 1. 标题 / **1. 标题** / 1. 标题）
    - URL+标题+摘要混合文本
    - 跳过前导语（"以下是搜索到的…"）
    """
    if not text or not text.strip():
        return

    # 前导语关键词（DeepSeek常见回复开头，不是真正的搜索结果）
    preamble_kws = ["以下是", "根据搜索", "为您搜索", "搜索到", "根据主题", "我整理了", "筛选出"]

    # 策略1：按编号条目分割（### 1. / **1. / 1. 等）
    entry_pattern = r'(?:^|\n)\s*(?:###\s*)?(?:\*\*)?(\d+)[.、)\s]+(.+?)(?=(?:\n\s*(?:###\s*)?(?:\*\*)?\d+[.、)\s])|$)'
    entries = re.findall(entry_pattern, text, re.DOTALL)

    if entries:
        url_re = re.compile(r'https?://[^\s<>"\')\]]+')
        for num_str, entry_text in entries[:max_results]:
            entry_text = entry_text.strip()
            if not entry_text or len(entry_text) < 5:
                continue
            # 跳过前导语
            first_line = entry_text.split('\n')[0].strip()[:30]
            if any(kw in first_line for kw in preamble_kws):
                continue

            # 提取URL
            urls = url_re.findall(entry_text)
            url = urls[0] if urls else ""

            # 提取标题和摘要
            lines = [l.strip().lstrip('*').strip() for l in entry_text.split('\n') if l.strip()]
            title = ""
            snippet = ""
            for line in lines:
                if url_re.match(line) or re.match(r'(?:来源|URL|链接)[：:]', line, re.IGNORECASE):
                    continue
                if re.match(r'(?:摘要|Snippet|简介)[：:]', line, re.IGNORECASE):
                    snippet = re.sub(r'^(?:摘要|Snippet|简介)[：:]\s*', '', line, flags=re.IGNORECASE).strip()
                    continue
                if not title and 3 < len(line) < 100:
                    title = line
                elif not snippet and len(line) > 10:
                    snippet = line[:200]

            if title:
                results_list.append({"title": title[:100], "url": url, "snippet": snippet[:200]})
        return

    # 策略2：按URL分割，每个URL附近找标题和摘要
    url_re = re.compile(r'https?://[^\s<>"\')\]]+')
    url_positions = [(m.start(), m.group()) for m in url_re.finditer(text)]

    if url_positions:
        for i, (pos, url) in enumerate(url_positions[:max_results]):
            # 取URL前200字作为上下文（可能包含标题）
            before = text[max(0, pos-200):pos].strip()
            # 取URL后300字作为上下文（可能包含摘要）
            next_pos = url_positions[i+1][0] if i+1 < len(url_positions) else len(text)
            after = text[pos+len(url):min(pos+300, next_pos)].strip()

            # 从before中提取标题（取最后一行有意义的文本）
            title = ""
            for line in reversed(before.split('\n')):
                line = line.strip().lstrip('*').strip()
                line = re.sub(r'^[\d]+[.、)\s]+', '', line)  # 去序号
                if 3 < len(line) < 100 and not any(kw in line[:20] for kw in preamble_kws):
                    title = line
                    break

            # 从after中提取摘要
            snippet = ""
            for line in after.split('\n'):
                line = line.strip()
                if len(line) > 10 and not url_re.match(line):
                    snippet = line[:200]
                    break

            if title:
                results_list.append({"title": title[:100], "url": url, "snippet": snippet[:200]})
        return

    # 策略3：纯文本按行提取（最终回退）
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:max_results]:
        clean = re.sub(r'^[\d]+[.、)\s]+', '', line).lstrip('*').strip()
        if clean and len(clean) > 5 and not any(kw in clean[:20] for kw in preamble_kws):
            results_list.append({"title": clean[:100], "url": "", "snippet": ""})


def search_with_deepseek_websearch(query, num_results=5):
    """使用DeepSeek Anthropic端点的联网搜索功能（优先方案）

    DeepSeek的Anthropic兼容端点支持 web_search tool，
    通过 tools=[{"type": "web_search_20250305"}] 让模型自动联网搜索并返回结构化结果。
    搜索+分析一体化，无需额外搜索API Key。

    注意：搜索消耗约3倍标准token（DeepSeek官方说明）
    """
    try:
        import requests
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return []

        # DeepSeek Anthropic兼容端点
        api_base = os.environ.get("LLM_API_BASE", "https://api.deepseek.com")
        # 自动推导Anthropic端点：如果用户配置的是OpenAI端点，替换为Anthropic端点
        if "/anthropic" not in api_base:
            # 去掉末尾 /v1 等路径，拼接 /anthropic
            base = re.sub(r'/v\d+/?$', '', api_base.rstrip('/'))
            anthropic_url = f"{base}/anthropic/v1/messages"
        else:
            anthropic_url = f"{api_base.rstrip('/')}/v1/messages"

        model = os.environ.get("LLM_MODEL", "deepseek-chat")

        # Anthropic Messages API 格式
        resp = requests.post(anthropic_url, headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }, json={
            "model": model,
            "max_tokens": 4096,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [
                {
                    "role": "user",
                    "content": f"请搜索以下主题的最新中文新闻，返回{num_results}条最相关的结果，每条包含标题、来源URL和摘要：\n\n{query}"
                }
            ],
        }, timeout=60)

        if resp.status_code != 200:
            print(f"  ⚠️ DeepSeek联网搜索HTTP {resp.status_code}: {resp.text[:200]}")
            return []

        data = resp.json()
        results = []

        # 解析Anthropic Messages响应 - 多格式兼容
        content_blocks = data.get("content", [])
        assistant_text = ""

        for block in content_blocks:
            block_type = block.get("type", "")

            # 格式1: web_search_tool_result（DeepSeek标准格式）
            if block_type == "web_search_tool_result":
                search_content = block.get("content", {})
                if isinstance(search_content, dict):
                    for result_item in search_content.get("results", []):
                        results.append({
                            "title": result_item.get("title", ""),
                            "url": result_item.get("url", ""),
                            "snippet": result_item.get("snippet", ""),
                        })
                elif isinstance(search_content, str) and search_content.strip():
                    _parse_search_text(search_content, results, num_results)

            # 格式2: tool_result（某些版本用此类型）
            elif block_type == "tool_result":
                tool_content = block.get("content", "")
                if isinstance(tool_content, str) and tool_content.strip():
                    _parse_search_text(tool_content, results, num_results)
                elif isinstance(tool_content, list):
                    for item in tool_content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            _parse_search_text(item.get("text", ""), results, num_results)

            # 收集助手文本
            if block_type == "text":
                assistant_text += block.get("text", "")

        # 如果没有从结构化块提取到结果，从助手文本解析
        if not results and assistant_text:
            _parse_search_text(assistant_text, results, num_results)

        if results:
            print(f"    ✅ DeepSeek联网搜索解析到 {len(results)} 条结果")
        return results[:num_results]
    except Exception as e:
        print(f"  ⚠️ DeepSeek联网搜索失败: {e}")
        return []


def search_with_serpapi(query, num_results=5):
    """使用SerpAPI搜索"""
    try:
        import requests
        api_key = os.environ.get("SERPAPI_KEY")
        if not api_key:
            return []
        resp = requests.get("https://serpapi.com/search", params={
            "q": query,
            "api_key": api_key,
            "engine": "google",
            "num": num_results,
            "hl": "zh-cn",
            "gl": "cn",
        }, timeout=30)
        results = []
        for item in resp.json().get("organic_results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results
    except Exception as e:
        print(f"  ⚠️ SerpAPI搜索失败: {e}")
        return []


def search_with_newsapi(query, num_results=5):
    """使用NewsAPI搜索"""
    try:
        import requests
        api_key = os.environ.get("NEWS_API_KEY")
        if not api_key:
            return []
        today = datetime.now().strftime("%Y-%m-%d")
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        resp = requests.get("https://newsapi.org/v2/everything", params={
            "q": query,
            "from": three_days_ago,
            "to": today,
            "language": "zh",
            "sortBy": "relevancy",
            "pageSize": num_results,
            "apiKey": api_key,
        }, timeout=30)
        results = []
        for item in resp.json().get("articles", [])[:num_results]:
            results.append({
                "title": item.get("title", "") or "",
                "url": item.get("url", "") or "",
                "snippet": item.get("description", "") or "",
            })
        return results
    except Exception as e:
        print(f"  ⚠️ NewsAPI搜索失败: {e}")
        return []


def search_news_for_dimension(dim_id, query):
    """按维度搜索新闻，优先DeepSeek联网搜索，回退SerpAPI，再回退NewsAPI"""
    print(f"  🔍 搜索维度: {dim_id} ...")

    # 优先：DeepSeek联网搜索（仅需LLM_API_KEY，无需额外Key）
    results = search_with_deepseek_websearch(query, num_results=5)
    if results:
        print(f"    ✅ DeepSeek联网搜索找到 {len(results)} 条结果")
        return results

    # 回退1：SerpAPI（需要SERPAPI_KEY）
    results = search_with_serpapi(query, num_results=5)
    if results:
        print(f"    ✅ SerpAPI找到 {len(results)} 条结果")
        return results

    # 回退2：NewsAPI（需要NEWS_API_KEY）
    results = search_with_newsapi(query, num_results=5)
    if results:
        print(f"    ✅ NewsAPI找到 {len(results)} 条结果")
        return results

    print(f"    ⚠️ 所有搜索源均未找到结果")
    return []


# ============ LLM增强模块 ============
# AI生成
def generate_case_with_llm(dim_info, search_results):
    """使用LLM生成STAR/PDCA深度分析案例

    使用DeepSeek OpenAI兼容端点（/v1/chat/completions），
    自动修正API Base URL，确保包含/v1路径。
    """
    try:
        import requests
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None

        api_base = os.environ.get("LLM_API_BASE", "https://api.deepseek.com")
        model = os.environ.get("LLM_MODEL", "deepseek-chat")

        # 修正API Base URL：确保包含 /v1 路径
        # 用户可能配置 https://api.deepseek.com（无/v1）或 https://api.deepseek.com/v1
        base = api_base.rstrip('/')
        if not base.endswith('/v1') and '/v1/' not in base:
            # 去掉末尾的 /anthropic 等路径后，拼接 /v1
            base = re.sub(r'/anthropic/?$', '', base)
            chat_url = f"{base}/v1/chat/completions"
        else:
            chat_url = f"{base}/chat/completions"

        print(f"    LLM端点: {chat_url}, 模型: {model}")

        # 构建搜索结果摘要（包含标题、URL和摘要，信息更丰富）
        search_summary = "\n".join([
            f"- 标题: {r['title']}\n  摘要: {r['snippet']}\n  来源: {r['url']}" for r in search_results[:5]
        ])

        prompt = f"""你是一位汽车行业资深分析师，请基于以下搜索结果，为「{dim_info['icon']} {dim_info['name']}」维度生成一个标杆案例分析。

搜索结果：
{search_summary}

要求：
1. 选择搜索结果中最有代表性的一个案例深入分析
2. 使用STAR法则（情境-任务-行动-结果）组织内容，每个环节100-200字
3. 内容要具体、有数据支撑，不要泛泛而谈
4. 提取3-4个关键指标（metrics）
5. 衡量可迁移点（其他品牌可复用的方法论）
6. 从搜索结果标题中提取品牌名

请严格按以下JSON格式输出（不要输出markdown代码块标记，直接输出JSON）：
{{
  "title": "案例标题（简洁有力，包含品牌和核心动作）",
  "brand": "品牌名",
  "type": "案例类型描述",
  "sections": [
    {{"label": "情境 (Situation)", "content": "..."}},
    {{"label": "任务 (Task)", "content": "..."}},
    {{"label": "行动 (Action)", "content": "..."}},
    {{"label": "结果 (Result)", "content": "..."}},
    {{"label": "可迁移点", "content": "..."}}
  ],
  "metrics": [
    {{"label": "指标名", "value": "指标值"}},
    {{"label": "指标名", "value": "指标值"}}
  ]
}}"""

        resp = requests.post(chat_url, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 2000,
        }, timeout=60)

        if resp.status_code != 200:
            print(f"    ⚠️ LLM API HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        content = resp.json()["choices"][0]["message"]["content"]

        # 提取JSON：尝试多种方式
        # 方式1：直接解析整个响应
        try:
            case_data = json.loads(content)
            if "title" in case_data and "sections" in case_data:
                return case_data
        except json.JSONDecodeError:
            pass

        # 方式2：提取```json```代码块
        code_block = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
        if code_block:
            try:
                case_data = json.loads(code_block.group(1).strip())
                if "title" in case_data and "sections" in case_data:
                    return case_data
            except json.JSONDecodeError:
                pass

        # 方式3：提取最外层花括号
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                case_data = json.loads(json_match.group())
                if "title" in case_data and "sections" in case_data:
                    return case_data
            except json.JSONDecodeError:
                pass

        print(f"    ⚠️ LLM响应无法解析为有效JSON，内容前200字: {content[:200]}")
    except Exception as e:
        print(f"  ⚠️ LLM生成失败: {e}")
    return None


def build_simple_case(dim_info, search_results, date_str):
    """无LLM或LLM失败时，基于搜索结果构建STAR结构化案例

    即使没有LLM，也尽量产出接近09-03报告质量的内容：
    - 从所有搜索结果中提取品牌名
    - 使用STAR框架组织内容（基于搜索摘要推演）
    - 从搜索文本中提取基本指标
    """
    if not search_results:
        return None

    # 从所有搜索结果中提取品牌名
    known_brands = ["蔚来", "小鹏", "理想", "比亚迪", "极氪", "问界", "领克",
                    "小米", "上汽", "广汽", "吉利", "长城", "奇瑞", "宝马", "奔驰",
                    "大众", "丰田", "本田", "特斯拉", "极越", "岚图", "智己", "阿维塔",
                    "奥迪", "保时捷", "沃尔沃", "现代", "起亚", "马自达", "福特"]

    brand = "行业综合"
    all_text = " ".join(r.get("title", "") + " " + r.get("snippet", "") for r in search_results)
    for b in known_brands:
        if b in all_text:
            brand = b
            break

    # 选择最佳案例（第一条结果）
    best = search_results[0]
    title = best["title"]
    # 清理标题：去掉DeepSeek前导语
    preamble_kws = ["以下是", "根据搜索", "为您搜索", "搜索到", "根据主题", "我整理了", "筛选出"]
    for kw in preamble_kws:
        if kw in title:
            # 尝试从后续搜索结果中找更合适的标题
            for r in search_results[1:]:
                if not any(k in r["title"][:20] for k in preamble_kws):
                    title = r["title"]
                    best = r
                    break
            break

    snippet = best.get("snippet", "") or "暂无详细描述"

    # 构建STAR结构化内容
    # 情境：从搜索摘要中提取行业背景
    situation = f"当前汽车行业{dim_info['name']}领域正处于快速发展期。{snippet[:150]}"

    # 任务：推演核心挑战
    task = f"在{dim_info['name']}维度，{brand}等头部品牌面临的核心挑战是：如何在激烈的市场竞争中，通过创新手段实现差异化突破，提升用户心智占有率与品牌粘性。"

    # 行动：从多条搜索结果中综合行动策略
    action_parts = []
    for i, r in enumerate(search_results[:3]):
        s = r.get("snippet", "")
        if s and len(s) > 20:
            action_parts.append(f"· {s[:120]}")
    action = "\n".join(action_parts) if action_parts else "基于行业公开信息，相关品牌已采取多元化策略推进该维度布局。"

    # 结果：推演成效
    result = f"综合公开信息分析，上述举措在{dim_info['name']}维度已初见成效，品牌认知度与用户参与度均呈现积极增长态势，为后续深化运营奠定了良好基础。"

    # 可迁移点
    transfer = f"其他品牌可借鉴的关键方法论：1）以用户为中心的{dim_info['name']}策略设计；2）数据驱动的精细化运营体系；3）品牌差异化定位与持续创新迭代。"

    sections = [
        {"label": "情境 (Situation)", "content": situation},
        {"label": "任务 (Task)", "content": task},
        {"label": "行动 (Action)", "content": action},
        {"label": "结果 (Result)", "content": result},
        {"label": "可迁移点", "content": transfer},
    ]

    # 从搜索文本中尝试提取基本指标
    metrics = []
    # 匹配百分比、万元、万辆等常见汽车行业指标
    pct_matches = re.findall(r'(\d+(?:\.\d+)?)\s*%', all_text)
    if pct_matches:
        metrics.append({"label": "增长率", "value": f"{pct_matches[0]}%"})
    wan_matches = re.findall(r'(\d+(?:\.\d+)?)\s*万(?:辆|元|人)', all_text)
    if wan_matches:
        metrics.append({"label": "规模", "value": f"{wan_matches[0]}万级"})

    return {
        "title": title,
        "brand": brand,
        "type": f"{dim_info['name']}标杆案例",
        "sections": sections,
        "metrics": metrics,
    }



# ============ HTML生成模块 ============
def generate_report_html(date_str, cases_data):
    """生成单日报告HTML文件，与现有模板风格一致"""

    # 构建案例JS数据
    cases_js = json.dumps(cases_data, ensure_ascii=False, indent=4)

    # 构建摘要
    summary_parts = []
    for case in cases_data:
        cat_id = case.get("category", "")
        cat_info = next((c for c in CATEGORIES if c["id"] == cat_id), None)
        if cat_info:
            summary_parts.append(f"{cat_info['icon']}{case['title']}")

    summary_text = "、".join(summary_parts[:7]) if summary_parts else "今日案例报告已生成"

    html = f"""<!-- AI生成 -->
<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>每日案例报告 · {date_str}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Noto+Sans+SC:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {{
      --c-bg: #f8fafc; --c-surface: #ffffff; --c-text: #0f172a;
      --c-text2: #475569; --c-text3: #94a3b8; --c-border: #e2e8f0;
      --c-primary: #4f46e5; --c-primary-light: #818cf8; --c-primary-bg: #eef2ff;
      --c-accent: #f59e0b;
      --f-sans: "Inter", "Noto Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      --g-primary: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #a855f7 100%);
      --c-shadow: rgba(15,23,42,0.06);
      --c-shadow-md: rgba(15,23,42,0.1);
    }}
    [data-theme="dark"] {{
      --c-bg: #0c0f1a; --c-surface: #1a1f35; --c-text: #f1f5f9;
      --c-text2: #cbd5e1; --c-text3: #64748b; --c-border: #2a3050;
      --c-primary-bg: rgba(79,70,229,0.12); --c-shadow: rgba(0,0,0,0.25); --c-shadow-md: rgba(0,0,0,0.35);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--f-sans); color: var(--c-text); background: var(--c-bg);
      line-height: 1.75; padding: 40px; max-width: 960px; margin: 0 auto;
      -webkit-font-smoothing: antialiased;
    }}
    button {{ cursor: pointer; border: none; background: none; font: inherit; color: inherit; }}
    .toolbar {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 32px; gap: 16px; }}
    .back-btn {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 10px 20px; border-radius: 12px;
      font-size: 15px; font-weight: 600; color: var(--c-text2);
      border: 1px solid var(--c-border); background: var(--c-surface);
      transition: all 0.2s ease; text-decoration: none;
    }}
    .back-btn:hover {{ border-color: var(--c-primary-light); color: var(--c-primary); }}
    .toolbar-right {{ display: flex; align-items: center; gap: 10px; }}
    .theme-toggle-btn {{
      width: 40px; height: 40px; border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      color: var(--c-text2); border: 1px solid var(--c-border); background: var(--c-surface);
      font-size: 18px;
    }}
    .report-header {{ margin-bottom: 32px; padding-bottom: 28px; border-bottom: 2px solid var(--c-border); }}
    h1 {{ font-size: 36px; font-weight: 900; margin-bottom: 12px; letter-spacing: -0.03em; line-height: 1.2; }}
    .date {{ font-size: 17px; color: var(--c-text2); font-weight: 500; }}
    .summary {{
      background: linear-gradient(135deg, #eef2ff 0%, #f0fdf4 50%, #fef3c7 100%);
      border-radius: 20px; padding: 28px 32px; margin-bottom: 32px;
      font-size: 17px; line-height: 1.85; border-left: 5px solid var(--c-primary);
      box-shadow: 0 4px 16px rgba(79, 70, 229, 0.08);
    }}
    [data-theme="dark"] .summary {{
      background: linear-gradient(135deg, rgba(79,70,229,0.1) 0%, rgba(16,185,129,0.08) 50%, rgba(245,158,11,0.08) 100%);
    }}
    .summary strong {{ color: var(--c-primary); font-weight: 700; }}
    .dim-tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 28px; padding-bottom: 16px; border-bottom: 1px solid var(--c-border); }}
    .dim-tab {{
      padding: 8px 18px; border-radius: 24px; font-size: 14px; font-weight: 600;
      color: var(--c-text2); background: var(--c-surface); border: 1px solid var(--c-border);
      cursor: pointer; white-space: nowrap; transition: all 0.2s ease;
    }}
    .dim-tab:hover {{ border-color: var(--c-primary-light); color: var(--c-primary); background: var(--c-primary-bg); }}
    .dim-tab.active {{ background: var(--g-primary); color: white; border-color: transparent; box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3); }}
    .filter-bar {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }}
    .filter-info {{ font-size: 14px; color: var(--c-text3); font-weight: 500; }}
    .case {{
      background: var(--c-surface); border-radius: 20px;
      border: 1px solid var(--c-border); padding: 32px; margin-bottom: 24px;
      box-shadow: 0 4px 16px var(--c-shadow); transition: all 0.3s ease;
      animation: caseFadeIn 0.4s ease both; position: relative; overflow: hidden;
    }}
    .case:hover {{ box-shadow: 0 8px 32px var(--c-shadow-md); transform: translateY(-2px); }}
    .case::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px; background: var(--g-primary); }}
    @keyframes caseFadeIn {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    .case-header {{ display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }}
    .case-cat {{ font-size: 14px; font-weight: 700; padding: 5px 14px; border-radius: 24px; white-space: nowrap; }}
    .case-title {{ font-size: 22px; font-weight: 800; flex: 1; letter-spacing: -0.02em; line-height: 1.3; }}
    .case-brand {{ font-size: 15px; color: var(--c-text2); margin-bottom: 16px; font-weight: 500; }}
    .case-section {{ margin-bottom: 16px; }}
    .case-section h4 {{ font-size: 14px; font-weight: 700; color: var(--c-primary); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }}
    .case-section h4::before {{ content: ''; width: 3px; height: 14px; background: var(--c-primary); border-radius: 2px; }}
    .case-section p {{ font-size: 16px; color: var(--c-text2); line-height: 1.85; }}
    .case-metrics {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }}
    .metric {{ background: var(--c-primary-bg); border-radius: 12px; padding: 10px 18px; font-size: 15px; font-weight: 500; border: 1px solid rgba(79,70,229,0.1); }}
    .metric strong {{ color: var(--c-primary); font-weight: 800; }}
    .empty-state {{ text-align: center; padding: 80px 20px; color: var(--c-text3); }}
    .empty-state .empty-icon {{ font-size: 56px; margin-bottom: 16px; }}
    .empty-state p {{ font-size: 20px; font-weight: 700; color: var(--c-text2); margin-bottom: 8px; }}
    .footer {{ text-align: center; color: var(--c-text3); font-size: 14px; margin-top: 56px; padding-top: 28px; border-top: 2px solid var(--c-border); }}
    .toast {{ position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%) translateY(24px); background: var(--c-text); color: var(--c-bg); padding: 14px 28px; border-radius: 24px; font-size: 15px; font-weight: 600; z-index: 300; opacity: 0; visibility: hidden; transition: all 0.3s ease; box-shadow: 0 12px 32px rgba(0,0,0,0.25); white-space: nowrap; }}
    .toast.show {{ opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0); }}
    @media (max-width: 640px) {{ body {{ padding: 20px; }} h1 {{ font-size: 28px; }} .case {{ padding: 24px; }} .case-title {{ font-size: 19px; }} }}
  </style>
</head>
<body>
  <div class="toolbar">
    <a href="../index.html" class="back-btn">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
      返回总览
    </a>
    <div class="toolbar-right">
      <button class="theme-toggle-btn" id="theme-btn" title="切换主题">🌓</button>
    </div>
  </div>

  <div class="report-header">
    <h1>📊 每日案例报告</h1>
    <p class="date">{date_str} · 汽车行业七维洞察</p>
  </div>

  <div class="summary">
    <strong>今日摘要：</strong>{summary_text}
  </div>

  <div class="dim-tabs" id="dim-tabs"></div>
  <div class="filter-bar">
    <span class="filter-info" id="filter-info">共 {len(cases_data)} 个案例</span>
  </div>
  <div id="cases-container"></div>
  <div class="empty-state" id="empty-state" style="display:none">
    <div class="empty-icon">📭</div>
    <p>暂无匹配的案例</p>
    <span>试试切换维度</span>
  </div>

  <div class="footer">
    📊 每日案例报告 · 汽车行业七维洞察 · 由AI智能体自动生成<br>
    分析模型：STAR法则 · PDCA循环 · 金字塔原理 · 数据来源：公开信息综合分析
  </div>
  <div class="toast" id="toast"></div>

  <script>
  (function() {{
    'use strict';
    const CATEGORIES = {json.dumps(CATEGORIES, ensure_ascii=False)};
    const CASES = {cases_js};
    const state = {{ activeDim: '__all__' }};
    const $ = (sel) => document.querySelector(sel);

    function renderDimTabs() {{
      const bar = $('#dim-tabs');
      const dimIds = [...new Set(CASES.map(c => c.category))];
      let html = `<button class="dim-tab ${{state.activeDim === '__all__' ? 'active' : ''}}" data-dim="__all__">全部 (${{CASES.length}})</button>`;
      dimIds.forEach(dimId => {{
        const cat = CATEGORIES.find(c => c.id === dimId);
        if (!cat) return;
        const count = CASES.filter(c => c.category === dimId).length;
        html += `<button class="dim-tab ${{state.activeDim === dimId ? 'active' : ''}}" data-dim="${{dimId}}">${{cat.icon}} ${{cat.name}} (${{count}})</button>`;
      }});
      bar.innerHTML = html;
      bar.querySelectorAll('.dim-tab').forEach(btn => {{
        btn.addEventListener('click', () => {{ state.activeDim = btn.dataset.dim; renderDimTabs(); renderCases(); }});
      }});
    }}

    function renderCases() {{
      const container = $('#cases-container');
      let cases = CASES;
      if (state.activeDim !== '__all__') cases = cases.filter(c => c.category === state.activeDim);
      const empty = $('#empty-state');
      if (cases.length === 0) {{ container.innerHTML = ''; empty.style.display = 'block'; return; }}
      empty.style.display = 'none';
      container.innerHTML = cases.map((c, i) => {{
        const cat = CATEGORIES.find(ct => ct.id === c.category);
        if (!cat) return '';
        const sectionsHtml = (c.sections || []).map(s => `<div class="case-section"><h4>${{s.label}}</h4><p>${{s.content}}</p></div>`).join('');
        const metricsHtml = (c.metrics || []).map(m => `<span class="metric">${{m.label}} <strong>${{m.value}}</strong></span>`).join('');
        return `<div class="case" style="animation-delay:${{i * 60}}ms"><div class="case-header"><span class="case-cat" style="background:${{cat.color}}18;color:${{cat.color}}">${{cat.icon}} ${{cat.name}}</span><span class="case-title">${{c.title}}</span></div><p class="case-brand">品牌：${{c.brand}} | 类型：${{c.type}}</p>${{sectionsHtml}}${{metricsHtml ? `<div class="case-metrics">${{metricsHtml}}</div>` : ''}}</div>`;
      }}).join('');
      let info = `共 ${{cases.length}} 个案例`;
      if (state.activeDim !== '__all__') {{
        const cat = CATEGORIES.find(c => c.id === state.activeDim);
        if (cat) info = `${{cat.icon}} ${{cat.name}} · ${{cases.length}} 个案例`;
      }}
      $('#filter-info').textContent = info;
    }}

    function init() {{
      const savedTheme = localStorage.getItem('report-theme');
      if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
      else if (window.matchMedia('(prefers-color-scheme: dark)').matches) document.documentElement.setAttribute('data-theme', 'dark');
      $('#theme-btn').addEventListener('click', () => {{
        const html = document.documentElement;
        const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        localStorage.setItem('report-theme', next);
      }});
      renderDimTabs();
      renderCases();
    }}

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }})();
  </script>
</body>
</html>"""
    return html


# ============ data.js 更新模块 ============
def _find_matching_brace(content, start_pos):
    """从start_pos（指向一个'{'）开始，用大括号计数法找到匹配的'}'位置"""
    depth = 0
    pos = start_pos
    while pos < len(content):
        ch = content[pos]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return pos
        pos += 1
    return -1  # 未找到匹配


def _remove_report_entry_by_date(content, date_str):
    """使用大括号计数法精确移除包含指定日期的报告条目"""
    # 查找日期字符串
    for quote in ["'", '"']:
        date_marker = f"date: {quote}{date_str}{quote}"
        pos = content.find(date_marker)
        if pos != -1:
            break
    else:
        return content  # 未找到该日期，无需移除

    # 从日期位置向前找该条目的起始 {
    brace_depth = 0
    start_pos = pos
    while start_pos >= 0:
        ch = content[start_pos]
        if ch == '}':
            brace_depth += 1
        elif ch == '{':
            if brace_depth == 0:
                break  # 找到条目起始的 {
            brace_depth -= 1
        start_pos -= 1

    if start_pos < 0:
        print("  ⚠️ 无法定位报告条目起始位置，跳过移除")
        return content

    # 从起始 { 向后找匹配的结束 }
    end_pos = _find_matching_brace(content, start_pos)
    if end_pos < 0:
        print("  ⚠️ 无法定位报告条目结束位置，跳过移除")
        return content

    # 移除该条目，处理前后的逗号和空白
    before = content[:start_pos].rstrip()
    after = content[end_pos + 1:]

    # 判断条目前后是否有逗号需要清理
    if after.lstrip().startswith(','):
        # 条目后有逗号，去掉逗号
        after = after.lstrip()
        after = after[1:]  # 去掉逗号
    elif before.endswith(','):
        # 条目前有逗号（前一个条目的尾部逗号），去掉逗号
        before = before[:-1]

    # 重新拼接，保持缩进
    return before + "\n    " + after.lstrip()


def update_data_js(date_str, new_cases):
    """将新日报数据追加到data.js的reports数组

    使用大括号计数法精确定位和移除旧条目，
    使用文件末尾 ]; 模式定位插入点，避免正则匹配嵌套结构出错。
    """
    if not DATA_JS_PATH.exists():
        print("  ⚠️ data.js 不存在，跳过更新")
        return

    content = DATA_JS_PATH.read_text(encoding="utf-8")

    # 检查是否已有该日期的数据，如有则先移除旧数据再追加新的
    date_check_single = f"date: '{date_str}'"
    date_check_double = f'date: "{date_str}"'
    if date_check_single in content or date_check_double in content:
        print(f"  ℹ️ data.js 已包含 {date_str} 的数据，将移除旧数据后重新追加")
        content = _remove_report_entry_by_date(content, date_str)

    # 构建新报告条目
    summary_parts = []
    for case in new_cases:
        cat_id = case.get("category", "")
        cat_info = next((c for c in CATEGORIES if c["id"] == cat_id), None)
        if cat_info:
            summary_parts.append(f"{cat_info['icon']}{case['title']}")
    summary = "今日精选7大维度案例：" + "、".join(summary_parts[:7]) if summary_parts else "今日案例报告"

    new_report = {
        "date": date_str,
        "title": "每日案例报告",
        "summary": summary,
        "cases": new_cases,
    }

    # 将新报告转为JS对象格式的字符串（与现有格式一致）
    new_report_json = json.dumps(new_report, ensure_ascii=False, indent=4)
    # 缩进处理：在每行前加4个空格（与data.js中现有格式对齐）
    indented_lines = []
    for line in new_report_json.split("\n"):
        indented_lines.append("    " + line)
    new_report_str = "\n".join(indented_lines)

    # 在reports数组的结束 ] 前插入新条目
    # 关键修复：使用文件末尾 ];\n}; 模式定位，而非正则匹配嵌套结构
    # 寻找 reports 数组的结束标记：] 后紧跟换行和 };
    close_pattern = r'\]\s*\n\s*\}\;\s*$'
    match = re.search(close_pattern, content)
    if match:
        # match.start() 是 ] 的位置
        bracket_pos = match.start()
        # 在 ] 前插入新条目
        before_bracket = content[:bracket_pos].rstrip()
        new_content = before_bracket + ",\n" + new_report_str + "\n  ]\n};\n"
        DATA_JS_PATH.write_text(new_content, encoding="utf-8")
        print(f"  ✅ 已将 {date_str} 数据追加到 data.js")
    else:
        # 备用方案：从文件末尾倒找 ]; 模式
        print("  ⚠️ 标准模式未匹配，尝试备用定位...")
        # 找最后一个 ] 后跟 }; 的位置
        last_brace_semi = content.rfind("};")
        if last_brace_semi > 0:
            # 从 }; 向前找 ]
            search_area = content[:last_brace_semi]
            last_bracket = search_area.rfind("]")
            if last_bracket > 0:
                before_bracket = content[:last_bracket].rstrip()
                new_content = before_bracket + ",\n" + new_report_str + "\n  ]\n};\n"
                DATA_JS_PATH.write_text(new_content, encoding="utf-8")
                print(f"  ✅ 已将 {date_str} 数据追加到 data.js（备用方案）")
                return
        print("  ❌ 无法定位data.js的reports数组结束位置，跳过更新")


# ============ 主流程 ============
def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"{'='*50}")
    print(f"🚀 开始生成 {today} 日报...")
    print(f"{'='*50}")

    # 检查是否已有该日期的报告，如有则覆盖重新生成
    report_path = REPORTS_DIR / f"{today}.html"
    if report_path.exists():
        print(f"ℹ️ {today} 的报告已存在，将覆盖重新生成")
        report_path.unlink()  # 删除旧文件

    # 1. 搜索各维度新闻
    print("\n📡 第1步：搜索行业新闻...")
    all_search_results = {}
    for cat in CATEGORIES:
        dim_id = cat["id"]
        query = DIMENSION_QUERIES.get(dim_id, f"汽车 {cat['name']} 2026")
        results = search_news_for_dimension(dim_id, query)
        all_search_results[dim_id] = results

    # 2. 生成各维度案例
    print("\n🧠 第2步：生成案例分析...")
    cases_data = []
    has_llm = bool(os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))

    for cat in CATEGORIES:
        dim_id = cat["id"]
        search_results = all_search_results.get(dim_id, [])

        if not search_results:
            print(f"  ⚠️ {cat['icon']} {cat['name']}：无搜索结果，跳过")
            continue

        # 尝试LLM增强
        case_data = None
        if has_llm:
            print(f"  🤖 {cat['icon']} {cat['name']}：使用LLM生成深度分析...")
            case_data = generate_case_with_llm(cat, search_results)

        # 回退到简单模式
        if not case_data:
            print(f"  📝 {cat['icon']} {cat['name']}：生成简要案例...")
            case_data = build_simple_case(cat, search_results, today)

        if case_data:
            case_data["id"] = f"{today}-{dim_id}"
            case_data["category"] = dim_id
            cases_data.append(case_data)
            print(f"  ✅ {cat['icon']} {cat['name']}：案例生成完成")

    if not cases_data:
        print("\n❌ 未生成任何案例，请检查搜索API配置")
        sys.exit(1)

    # 3. 生成HTML报告
    print(f"\n📄 第3步：生成HTML报告...")
    REPORTS_DIR.mkdir(exist_ok=True)
    html_content = generate_report_html(today, cases_data)
    report_path.write_text(html_content, encoding="utf-8")
    print(f"  ✅ 已生成 reports/{today}.html")

    # 4. 更新data.js
    print(f"\n📊 第4步：更新data.js...")
    update_data_js(today, cases_data)

    # 5. 输出统计
    print(f"\n{'='*50}")
    print(f"✅ 日报生成完成！")
    print(f"  日期：{today}")
    print(f"  案例数：{len(cases_data)}")
    print(f"  模式：{'LLM增强' if has_llm else '纯搜索'}")
    print(f"  文件：reports/{today}.html")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
