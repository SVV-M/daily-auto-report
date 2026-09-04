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
def search_with_deepseek_websearch(query, num_results=5):
    """使用DeepSeek Anthropic端点的联网搜索功能（优先方案）

    DeepSeek的Anthropic兼容端点支持 server_tool_use / web_search_tool_result，
    通过 tools=[{"type": "web_search"}] 让模型自动联网搜索并返回结构化结果。
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

        # 解析Anthropic Messages响应
        # 搜索结果在 content block 中，type="web_search_tool_result"
        content_blocks = data.get("content", [])
        search_result_text = ""
        assistant_text = ""

        for block in content_blocks:
            if block.get("type") == "text":
                assistant_text += block.get("text", "")
            # 跳过搜索请求block（server_tool_use）
            if block.get("type") == "server_tool_use":
                continue
            # web_search_tool_result 包含搜索引擎返回的原始结果
            if block.get("type") == "web_search_tool_result":
                search_content = block.get("content", {})
                # P0修复：处理content为字符串的情况（DeepSeek有时返回JSON字符串而非dict）
                if isinstance(search_content, str):
                    try:
                        search_content = json.loads(search_content)
                    except (json.JSONDecodeError, TypeError):
                        # JSON解析失败，将整段文本作为单条结果
                        results.append({
                            "title": "",
                            "url": "",
                            "snippet": search_content[:500],
                        })
                        search_content = {}

                if isinstance(search_content, dict):
                    # 提取搜索结果（标准路径：content.results数组）
                    for result_item in search_content.get("results", []):
                        results.append({
                            "title": result_item.get("title", ""),
                            "url": result_item.get("url", ""),
                            "snippet": result_item.get("snippet", ""),
                        })
                    # 兜底：DeepSeek有时把单条结果放在block顶层
                    if not results:
                        block_title = block.get("title", "")
                        block_url = block.get("url", "")
                        if block_title or block_url:
                            results.append({
                                "title": block_title,
                                "url": block_url,
                                "snippet": block.get("snippet", ""),
                            })

        # 如果没有从 web_search_tool_result 提取到结构化结果，
        # 尝试从助手文本回复中解析（模型通常会在文本中引用搜索结果）
        if not results and assistant_text:
            # 尝试从文本中提取URL和标题
            url_pattern = r'https?://[^\s<>"\')\]]+'
            urls = re.findall(url_pattern, assistant_text)
            # 按行分割，尝试提取标题
            lines = [l.strip() for l in assistant_text.split('\n') if l.strip()]
            for i, line in enumerate(lines[:num_results]):
                # 去除序号前缀
                clean_line = re.sub(r'^[\d]+[.、)\s]+', '', line)
                if clean_line and len(clean_line) > 5:
                    url = urls[i] if i < len(urls) else ""
                    results.append({
                        "title": clean_line[:100],
                        "url": url,
                        "snippet": "",
                    })

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
def generate_case_with_llm(dim_info, search_results):
    """使用LLM生成STAR/PDCA深度分析案例"""
    try:
        import requests
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        api_base = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        if not api_key:
            return None

        # 构建搜索结果摘要
        search_summary = "\n".join([
            f"- {r['title']}: {r['snippet']}" for r in search_results[:3]
        ])

        prompt = f"""你是一位汽车行业资深分析师，请基于以下搜索结果，为「{dim_info['icon']} {dim_info['name']}」维度生成一个标杆案例分析。

搜索结果：
{search_summary}

要求：
1. 选择搜索结果中最有代表性的一个案例深入分析
2. 使用STAR法则（情境-任务-行动-结果）或PDCA循环（计划-执行-检查-改进）组织内容
3. 每个环节内容要具体、有数据支撑，100-200字
4. 提取3-4个关键指标（metrics）
5. 补量可迁移点（其他品牌可复用的方法论）

请严格按以下JSON格式输出（不要输出其他内容）：
{{
  "title": "案例标题",
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

        resp = requests.post(f"{api_base}/chat/completions", headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 2000,
        }, timeout=60)

        content = resp.json()["choices"][0]["message"]["content"]
        # 提取JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            case_data = json.loads(json_match.group())
            return case_data
    except Exception as e:
        print(f"  ⚠️ LLM生成失败: {e}")
    return None


def _clean_llm_title(raw_title):
    """P1修复：清洗LLM搜索原文中的前缀和无关内容"""
    if not raw_title:
        return ""
    # 过滤LLM前缀模式
    llm_prefixes = [
        r'^我将为您搜索关于.*?[。.，,]\s*',
        r'^让我为您搜索.*?[。.，,]\s*',
        r'^以下是关于.*?[：:]\s*',
        r'^根据搜索结果[，,]\s*',
        r'^好的[，,]\s*',
        r'^关于.*?[，,]\s*',
    ]
    cleaned = raw_title
    for pattern in llm_prefixes:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    # 去除首尾空白和引号
    cleaned = cleaned.strip().strip('"\'""''')
    # 如果清洗后过短或仍含LLM痕迹，返回截断原文
    if len(cleaned) < 5 or cleaned.startswith('我将') or cleaned.startswith('让我'):
        # 取原文前30字作为兜底标题
        cleaned = raw_title[:30].rstrip() + ("..." if len(raw_title) > 30 else "")
    return cleaned


def _extract_brand_from_text(text, known_brands):
    """P1修复：从文本中提取品牌名"""
    for b in known_brands:
        if b in text:
            return b
    return ""


def _extract_brand_from_url(url):
    """P1修复：从URL中提取品牌线索"""
    brand_url_map = {
        "nio": "蔚来", "xpeng": "小鹏", "lixiang": "理想", "byd": "比亚迪",
        "zeekr": "极氪", "wenjie": "问界", "lynkco": "领克", "xiaomi": "小米",
        "tesla": "特斯拉", "volvo": "沃尔沃", "bmw": "宝马", "mercedes": "奔驰",
        "audi": "奥迪", "toyota": "丰田", "honda": "本田", "vw": "大众",
        "geely": "吉利", "chery": "奇瑞", "gwm": "长城", "saic": "上汽",
        "voyah": "岚图", "im": "智己", "avatr": "阿维塔", "jiyue": "极越",
    }
    url_lower = url.lower()
    for key, brand in brand_url_map.items():
        if key in url_lower:
            return brand
    return ""


def _extract_metrics_from_text(text):
    """P1修复：从文本中正则提取数值指标"""
    metrics = []
    # 匹配"提升X%"、"增长X%"、"降低X%"等模式
    pct_patterns = [
        (r'(?:提升|增长|增加|提高|上涨)[了]?(\d+(?:\.\d+)?)%', '增长率'),
        (r'(?:降低|下降|减少|缩减)[了]?(\d+(?:\.\d+)?)%', '降幅'),
        (r'(\d+(?:\.\d+)?)%\s*(?:↑|→|至)\s*(\d+(?:\.\d+)?)%', '变化幅度'),
    ]
    for pattern, label in pct_patterns:
        matches = re.findall(pattern, text)
        for m in matches[:2]:  # 每种模式最多取2个
            if isinstance(m, tuple):
                metrics.append({"label": label, "value": f"{m[0]}%→{m[1]}%"})
            else:
                metrics.append({"label": label, "value": f"+{m}%"})

    # 匹配具体数值："X万元"、"X亿"、"X万"
    amount_patterns = [
        (r'(\d+(?:\.\d+)?)\s*万[元人]', '规模'),
        (r'(\d+(?:\.\d+)?)\s*亿', '规模'),
    ]
    for pattern, label in amount_patterns:
        matches = re.findall(pattern, text)
        for m in matches[:2]:
            if len(metrics) < 4:  # metrics总数上限4
                metrics.append({"label": label, "value": m})

    return metrics[:4]  # 最多4个指标


# 维度→增长模式映射
CATEGORY_TYPE_MAP = {
    "brand-marketing":    "品牌事件驱动型传播",
    "user-growth":        "私域运营驱动型增长",
    "offline-experience": "场景体验驱动型转化",
    "digital-content":    "内容生态驱动型破圈",
    "crossover-eco":      "跨界联动驱动型裂变",
    "industry-trend":     "趋势洞察驱动型对标",
    "emotion-economy":    "情绪价值驱动型共鸣",
}


def _clean_summary_text(cases_data, max_chars=200):
    """P3修复：生成精炼摘要，格式：每维度一句"品牌+动作+关键数据"，总字数≤max_chars"""
    parts = []
    for case in cases_data:
        brand = case.get("brand", "")
        if brand in ("待补充", "（待确认）", ""):
            brand = ""
        title = _clean_llm_title(case.get("title", ""))
        # 从metrics中提取关键数据点
        metrics = case.get("metrics", [])
        metric_str = ""
        if metrics:
            metric_str = "，".join([f"{m['label']}{m['value']}" for m in metrics[:2]])

        # 组装：品牌+标题关键词+数据
        if brand:
            segment = brand + title[:20]
        else:
            segment = title[:25]
        if metric_str:
            segment += f"（{metric_str}）"
        parts.append(segment)

    summary = "今日精选7大维度案例：" + "、".join(parts[:7])
    # 截断至max_chars
    if len(summary) > max_chars:
        summary = summary[:max_chars - 3] + "..."
    return summary


def build_simple_case(dim_info, search_results, date_str):
    """无LLM时，基于搜索结果构建简要案例（P1增强版：title/brand/type/sections/metrics兜底）"""
    if not search_results:
        return None

    best = search_results[0]
    raw_title = best.get("title", "")
    snippet = best.get("snippet", "") or "暂无详细描述"
    url = best.get("url", "")

    # P1修复1：title清洗——过滤LLM前缀
    title = _clean_llm_title(raw_title)
    # 如果清洗后title为空或仍像LLM原文，用snippet前30字兜底
    if not title or len(title) < 5:
        title = snippet[:30].rstrip() + ("..." if len(snippet) > 30 else "")

    # P1修复2：brand提取——从title+snippet识别，再从URL提取
    known_brands = ["蔚来", "小鹏", "理想", "比亚迪", "极氪", "问界", "领克",
                    "小米", "上汽", "广汽", "吉利", "长城", "奇瑞", "宝马", "奔驰",
                    "大众", "丰田", "本田", "特斯拉", "极越", "岚图", "智己", "阿维塔",
                    "华为", "赛力斯", "极狐", "零跑", "合创", "飞凡", "smart"]
    brand = _extract_brand_from_text(title + snippet, known_brands)
    if not brand:
        brand = _extract_brand_from_url(url)
    if not brand:
        brand = "（待确认）"

    # P1修复3：type映射——从category映射到增长模式描述
    dim_id = dim_info.get("id", "")
    case_type = CATEGORY_TYPE_MAP.get(dim_id, f"{dim_info['name']}动态")

    # P1修复4：sections增强——至少2段有业务价值的内容
    sections = [
        {"label": "情境 (Situation)", "content": snippet},
    ]

    # 第二段：关键发现或行业背景
    if len(search_results) > 1:
        other_findings = []
        for r in search_results[1:4]:
            r_title = _clean_llm_title(r.get("title", ""))
            r_snippet = r.get("snippet", "")
            if r_snippet:
                other_findings.append(f"· {r_snippet[:80]}")
            elif r_title:
                other_findings.append(f"· {r_title}")
        if other_findings:
            sections.append({
                "label": "行动 (Action)",
                "content": "同维度相关动态：\n" + "\n".join(other_findings),
            })

    # 确保至少2段
    if len(sections) < 2:
        sections.append({
            "label": "信息来源",
            "content": f"原标题：{raw_title}。详细内容请访问原文链接。",
        })

    # P1修复5：metrics提取——从snippet中正则提取数值指标
    metrics = _extract_metrics_from_text(snippet)
    # 补充：从其他搜索结果的snippet中也提取
    for r in search_results[1:3]:
        extra_metrics = _extract_metrics_from_text(r.get("snippet", ""))
        for m in extra_metrics:
            if len(metrics) < 4 and m["label"] not in [existing["label"] for existing in metrics]:
                metrics.append(m)

    return {
        "title": title,
        "brand": brand,
        "type": case_type,
        "sections": sections,
        "metrics": metrics,
    }


# ============ HTML生成模块 ============
def generate_report_html(date_str, cases_data):
    """生成单日报告HTML文件，与现有模板风格一致"""

    # 构建案例JS数据
    cases_js = json.dumps(cases_data, ensure_ascii=False, indent=4)

    # P3修复：使用清洗后的精炼摘要
    summary_text = _clean_summary_text(cases_data)

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
    .bookmark-btn {{ font-size: 20px; padding: 4px 8px; border-radius: 8px; color: var(--c-accent); transition: all 0.2s ease; flex-shrink: 0; }}
    .bookmark-btn:hover {{ background: rgba(245,158,11,0.12); transform: scale(1.15); }}
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

    // P2修复：收藏功能（localStorage持久化）
    function getBookmarks() {{
      try {{ return JSON.parse(localStorage.getItem('case-bookmarks') || '[]'); }} catch {{ return []; }}
    }}
    function toggleBookmark(caseId) {{
      const bm = getBookmarks();
      const idx = bm.indexOf(caseId);
      if (idx === -1) {{ bm.push(caseId); showToast('⭐ 已收藏'); }}
      else {{ bm.splice(idx, 1); showToast('取消收藏'); }}
      localStorage.setItem('case-bookmarks', JSON.stringify(bm));
      renderCases();
    }}
    function showToast(msg) {{
      const t = $('#toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 1800);
    }}

    function renderCases() {{
      const container = $('#cases-container');
      let cases = CASES;
      if (state.activeDim !== '__all__') cases = cases.filter(c => c.category === state.activeDim);
      const empty = $('#empty-state');
      if (cases.length === 0) {{ container.innerHTML = ''; empty.style.display = 'block'; return; }}
      empty.style.display = 'none';
      const bookmarks = getBookmarks();
      container.innerHTML = cases.map((c, i) => {{
        const cat = CATEGORIES.find(ct => ct.id === c.category);
        if (!cat) return '';
        const isBm = bookmarks.includes(c.id);
        const sectionsHtml = (c.sections || []).map(s => `<div class="case-section"><h4>${{s.label}}</h4><p>${{s.content}}</p></div>`).join('');
        const metricsHtml = (c.metrics || []).map(m => `<span class="metric">${{m.label}} <strong>${{m.value}}</strong></span>`).join('');
        return `<div class="case" style="animation-delay:${{i * 60}}ms"><div class="case-header"><span class="case-cat" style="background:${{cat.color}}18;color:${{cat.color}}">${{cat.icon}} ${{cat.name}}</span><span class="case-title">${{c.title}}</span><button class="bookmark-btn" onclick="toggleBookmark('${{c.id}}')" title="${{isBm ? '取消收藏' : '收藏'}}">${{isBm ? '⭐' : '☆'}}</button></div><p class="case-brand">品牌：${{c.brand}} | 类型：${{c.type}}</p>${{sectionsHtml}}${{metricsHtml ? `<div class="case-metrics">${{metricsHtml}}</div>` : ''}}</div>`;
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
      // P2修复：暴露收藏/Toast到全局作用域（onclick内联调用需要）
      window.toggleBookmark = toggleBookmark;
      window.showToast = showToast;
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

    # P3修复：使用清洗后的精炼摘要
    summary = _clean_summary_text(new_cases)

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

    # 检查是否已有该日期的报告（默认覆盖，可通过环境变量控制）
    report_path = REPORTS_DIR / f"{today}.html"
    force_overwrite = os.environ.get("FORCE_OVERWRITE", "true").lower() in ("true", "1", "yes")
    if report_path.exists() and not force_overwrite:
        print(f"ℹ️ {today} 的报告已存在，跳过生成")
        print(f"  如需重新生成，请先删除 {report_path} 或设置 FORCE_OVERWRITE=true")
        return
    if report_path.exists():
        print(f"🔄 {today} 的报告已存在，将覆盖重新生成")
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
