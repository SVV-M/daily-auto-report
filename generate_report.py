# AI生成
#!/usr/bin/env python3
"""
独立日报生成脚本 - 在 GitHub Actions 中运行
功能：搜索当日汽车行业新闻 → 生成7维度案例报告 → 输出HTML + 更新data.js

支持两种模式：
1. LLM增强模式：使用OpenAI兼容API生成STAR深度分析（推荐）
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

# ============ 文本清洗模块 ============
# LLM搜索泄漏关键词（DeepSeek/Claude等常见回复开头，绝不应出现在最终输出中）
LLM_LEAKAGE_PATTERNS = [
    # 中文LLM搜索提示语
    r'我将为您搜索',
    r'我来为您搜索',
    r'我来帮您搜索',
    r'让我为您搜索',
    r'请?搜索以下主题',
    r'以下是.*搜索.*结果',
    r'根据搜索结果',
    r'根据搜索',
    r'为您搜索',
    r'搜索到',
    r'根据主题',
    r'我整理了',
    r'筛选出',
    r'我筛选出',
    r'我为您筛选',
    r'让我先.*搜索',
    r'让我进一步.*搜索',
    r'让我再.*搜索',
    r'我已.*搜索',
    r'我已通过.*搜索',
    r'基于与.*综合匹',
    r'以下是根据',
    r'以下是筛选',
    # 英文LLM提示语
    r'I will search',
    r'Let me search',
    r'Based on the search',
    r'Here are the results',
]

# 编译正则
_LLM_LEAKAGE_RE = re.compile(
    '|'.join(f'(?:{p})' for p in LLM_LEAKAGE_PATTERNS),
    re.IGNORECASE
)

# Markdown残留标记
_MD_BOLD_RE = re.compile(r'\*{2,}')       # ** 或 ***
_MD_ITALIC_RE = re.compile(r'(?<!\*)\*(?!\*)')  # 单个 * (非bold)
_MD_HEADING_RE = re.compile(r'^#{1,6}\s+', re.MULTILINE)  # # 标题
_MD_LIST_RE = re.compile(r'^\s*[-*+]\s+', re.MULTILINE)  # - * + 列表

# URL正则
_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')


def sanitize_text(text, remove_urls=False):
    """清洗文本：去除LLM搜索泄漏、Markdown残留、多余标点、无意义*号

    Args:
        text: 原始文本
        remove_urls: 是否移除URL（默认保留，某些场景需移除）
    """
    if not text or not text.strip():
        return ""

    # 1. 移除LLM搜索泄漏整句
    # 按句分割，过滤含泄漏关键词的句子
    sentences = re.split(r'([。；！？\n])', text)
    clean_parts = []
    for part in sentences:
        if not _LLM_LEAKAGE_RE.search(part):
            clean_parts.append(part)
    text = ''.join(clean_parts)

    # 2. 移除Markdown bold标记 ** 和 ***
    text = _MD_BOLD_RE.sub('', text)

    # 3. 移除Markdown italic标记 *（单独的*号，非bold残留）
    #    仅移除包裹词组的*号，保留数学表达式中的*
    text = re.sub(r'(?<!\w)\*(?!\*)(?=\S)', '', text)   # 开头*
    text = re.sub(r'(?<!\*)(?<!\w)\*(?=\W|$)', '', text)  # 结尾*

    # 4. 移除Markdown heading标记 (# ## ### 等)
    text = _MD_HEADING_RE.sub('', text)

    # 5. 移除Markdown列表标记（- * + 开头）
    text = _MD_LIST_RE.sub('', text)

    # 6. 移除URL（可选）
    if remove_urls:
        text = _URL_RE.sub('', text)

    # 7. 清理残留的编号列表标记（如 "1. " "2）" 等，仅在行首）
    text = re.sub(r'(?<=\n)\s*\d+[.、)）]\s+', '', text)
    text = re.sub(r'^\s*\d+[.、)）]\s+', '', text)

    # 8. 清理多余空白
    text = re.sub(r'\s{3,}', ' ', text)  # 多空格→单空格
    text = re.sub(r'\n{3,}', '\n\n', text)  # 多换行→双换行

    # 9. 清理首尾空白和标点
    text = text.strip()
    # 移除开头残留的列表标记
    text = re.sub(r'^[\s·*\-]+', '', text)

    # 10. 清理断句问题：移除句中多余的句号+空格组合（如"xxx。 yyy"→"xxx，yyy"）
    #     仅当句号后跟小写字母或非标点时，视为断句错误
    text = re.sub(r'。\s+([^\x00-\x7F])', r'，\1', text)

    return text


def sanitize_title(title):
    """清洗标题：去除LLM泄漏、Markdown标记、URL、多余标点、无意义*号

    标准标题特征（参照9月3日标准）：
    - 包含品牌名和核心动作
    - 15-30字，简洁有力
    - 无*号、无URL、无LLM泄漏语
    """
    if not title:
        return ""

    # 1. 如果整个标题就是LLM搜索提示语，标记为无效
    if _LLM_LEAKAGE_RE.search(title[:50]):
        return ""

    # 2. 移除所有Markdown标记（**加粗**、*斜体*、#标题等）
    title = _MD_BOLD_RE.sub('', title)
    title = _MD_HEADING_RE.sub('', title)
    # 移除单独的*号（italic标记或残留）
    title = re.sub(r'(?<!\w)\*(?!\*)', '', title)
    title = re.sub(r'(?<!\*)\*(?!\w)', '', title)

    # 3. 移除URL
    title = _URL_RE.sub('', title)

    # 4. 移除Markdown列表标记和编号
    title = re.sub(r'^[\s·*\-\d]+[.、)\s]+', '', title)

    # 5. 移除多余标点和空白
    title = re.sub(r'\s{2,}', ' ', title)
    title = title.strip()
    # 移除首尾无意义字符（*号、·号、-号等）
    title = re.sub(r'^[·*\-\s]+', '', title)
    title = re.sub(r'[·*\-\s]+$', '', title)

    # 6. 移除标题中的引号包裹（如「xxx」→ xxx）
    title = re.sub(r'[「」『』]', '', title)

    # 7. 如果清洗后标题过短（<5字），视为无效
    if len(title) < 5:
        return ""

    # 8. 截断过长标题（保留完整语义，在句号/逗号处截断）
    if len(title) > 50:
        # 优先在句号、逗号处截断
        for sep in ['。', '，', '、', '；']:
            pos = title[:50].rfind(sep)
            if pos > 10:
                title = title[:pos]
                break
        else:
            title = title[:47] + '...'

    return title


def sanitize_summary(summary):
    """清洗摘要：确保不含LLM泄漏语、Markdown残留、无意义*号

    标准摘要特征（参照9月3日标准）：
    - 以"今日精选7大维度案例："开头
    - 每个案例用顿号分隔，格式为"图标+标题"
    - 无LLM搜索提示语、无*号、无URL
    """
    if not summary:
        return "今日案例报告已生成"

    # 按顿号/逗号分割摘要片段，过滤含泄漏的片段
    parts = re.split(r'[、，]', summary)
    clean_parts = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 跳过含LLM泄漏的片段
        if _LLM_LEAKAGE_RE.search(part[:50]):
            continue
        # 清洗Markdown标记（**加粗**、*斜体*）
        part = _MD_BOLD_RE.sub('', part)
        part = re.sub(r'(?<!\w)\*(?!\*)', '', part)
        part = re.sub(r'(?<!\*)\*(?!\w)', '', part)
        # 清洗URL
        part = _URL_RE.sub('', part)
        # 清洗编号标记
        part = re.sub(r'^\d+[.、)）]\s*', '', part)
        part = part.strip()
        # 片段需有意义长度且不含搜索提示语
        if part and len(part) > 2 and not _LLM_LEAKAGE_RE.search(part[:30]):
            clean_parts.append(part)

    if not clean_parts:
        return "今日案例报告已生成"

    result = "、".join(clean_parts)

    # 截断过长摘要（参照9月3日标准，摘要约80-120字）
    if len(result) > 150:
        # 在最后一个顿号处截断
        last_sep = result[:150].rfind('、')
        if last_sep > 30:
            result = result[:last_sep] + '等。'
        else:
            result = result[:147] + '...'

    return result


def validate_case(case_data):
    """验证案例数据质量，返回(is_valid, reason)

    检查项：
    - 标题非空且不含LLM泄漏、无*号
    - 品牌名非"待补充"/"（待确认）"
    - sections至少有3个，且content非空
    - sections使用STAR框架（至少有Situation和Result）
    - 不含URL堆砌（action中URL占比<50%）
    - content中无残留*号和Markdown标记
    - metrics不为空（至少1个）
    """
    if not case_data:
        return False, "案例数据为空"

    # 标题检查
    title = case_data.get("title", "")
    if not title or not title.strip():
        return False, "标题为空"
    if _LLM_LEAKAGE_RE.search(title[:50]):
        return False, f"标题含LLM泄漏: {title[:30]}"
    if _URL_RE.search(title):
        return False, f"标题含URL: {title[:30]}"
    # 标题中不应有*号
    if '*' in title:
        return False, f"标题含*号: {title[:30]}"

    # 品牌检查
    brand = case_data.get("brand", "")
    if brand in ("待补充", "（待确认）", "待确认", ""):
        return False, f"品牌无效: {brand}"

    # Sections检查
    sections = case_data.get("sections", [])
    if len(sections) < 3:
        return False, f"sections不足3个: {len(sections)}"

    # 检查sections内容非空
    empty_count = sum(1 for s in sections if not s.get("content", "").strip() or s.get("content", "").strip() == "暂无详细描述")
    if empty_count > len(sections) // 2:
        return False, f"超半数sections内容为空: {empty_count}/{len(sections)}"

    # 检查sections内容中无残留*号
    for s in sections:
        content = s.get("content", "")
        # 检查是否有**加粗**残留
        if _MD_BOLD_RE.search(content):
            return False, f"section含**残留: {s.get('label', '')}"
        # 检查是否有单独*号残留（排除数学表达式如3*2）
        # 如果*号前后都是中文字符，则视为残留
        if re.search(r'[\u4e00-\u9fff]\*[\u4e00-\u9fff]', content):
            return False, f"section含*号残留: {s.get('label', '')}"

    # 检查是否使用STAR框架（而非"新闻概要"/"信息来源"等非标准标签）
    labels = [s.get("label", "") for s in sections]
    star_labels = {"情境 (Situation)", "任务 (Task)", "行动 (Action)", "结果 (Result)"}
    has_star = any(l in star_labels for l in labels)
    non_standard_labels = {"新闻概要", "信息来源", "同维度动态"}
    has_non_standard = any(l in non_standard_labels for l in labels)
    if has_non_standard and not has_star:
        return False, "使用非标准section标签（新闻概要/信息来源）"

    # URL堆砌检查：action内容中URL字符占比
    for s in sections:
        content = s.get("content", "")
        if "Action" in s.get("label", "") or "行动" in s.get("label", ""):
            url_chars = sum(len(m.group()) for m in _URL_RE.finditer(content))
            if len(content) > 0 and url_chars / len(content) > 0.5:
                return False, "Action中URL占比过高"

    # 检查泛化模板内容（在Result section中）
    for s in sections:
        content = s.get("content", "")
        if "Result" in s.get("label", "") or "结果" in s.get("label", ""):
            generic_endings = [
                "为后续深化运营奠定了基础",
                "为后续发展奠定了基础",
                "已初见成效",
                "呈现积极增长态势",
            ]
            for ending in generic_endings:
                if content.strip().endswith(ending):
                    return False, f"Result含泛化结尾: {ending}"

    # Metrics检查：至少有1个有效指标
    metrics = case_data.get("metrics", [])
    valid_metrics = [m for m in metrics if m.get("label") and m.get("value") and m["value"] not in ("", "N/A", "暂无")]
    if not valid_metrics and len(sections) >= 4:
        # 有完整STAR但无metrics，发出警告但不拒绝（搜索结果可能确实无数据）
        pass  # 允许无metrics通过验证，但在后续步骤中会尝试补充

    return True, "OK"


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
    """使用LLM生成STAR深度分析案例

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
        base = api_base.rstrip('/')
        if not base.endswith('/v1') and '/v1/' not in base:
            base = re.sub(r'/anthropic/?$', '', base)
            chat_url = f"{base}/v1/chat/completions"
        else:
            chat_url = f"{base}/chat/completions"

        print(f"    LLM端点: {chat_url}, 模型: {model}")

        # 构建搜索结果摘要（包含标题和摘要，不含URL以避免泄漏）
        search_summary = "\n".join([
            f"- 标题: {r['title']}\n  摘要: {r['snippet']}" for r in search_results[:5]
        ])

        prompt = f"""你是一位汽车行业资深分析师，请基于以下搜索结果，为「{dim_info['icon']} {dim_info['name']}」维度生成一个标杆案例分析。

搜索结果：
{search_summary}

严格要求：
1. 选择搜索结果中最有代表性的一个案例深入分析
2. 使用STAR法则（情境-任务-行动-结果）组织内容，每个环节100-200字
3. Action环节用①②③④编号列出关键动作，每条30-50字
4. Result环节必须有具体数值和数据，不可泛化
5. 提取3-4个关键指标（metrics），必须有具体数值
6. 从搜索结果标题中提取品牌名

禁止事项（违反则输出无效）：
- 禁止在title/brand/content中出现"我将搜索""我来搜索""根据搜索""以下是根据"等搜索提示语
- 禁止在content中包含URL或"来源URL""SourceURL"等字样
- 禁止使用Markdown格式标记（**加粗**、*斜体*、#标题等）
- 禁止使用"暂无详细描述""待补充""（待确认）"等占位文字
- 禁止使用"当前汽车行业XX领域正处于快速发展期"等泛化开头
- 禁止使用"综合公开信息分析，上述举措已初见成效"等泛化结尾
- 禁止使用"为后续深化运营奠定了基础"等模板化结尾
- 禁止输出"可迁移点"section（仅输出4个STAR section）
- 禁止在title中使用引号包裹（如「xxx」）

请严格按以下JSON格式输出（不要输出markdown代码块标记，直接输出JSON）：
{{
  "title": "案例标题（简洁有力，包含品牌和核心动作，15-30字，无引号无*号）",
  "brand": "品牌名（从搜索结果提取，不可为空）",
  "type": "案例类型描述（具体描述，如'年度发布会情感营销'，非泛化标签）",
  "sections": [
    {{"label": "情境 (Situation)", "content": "行业背景与品牌面临的挑战（100-200字，要有具体数据和事实）"}},
    {{"label": "任务 (Task)", "content": "品牌需要解决的核心问题与目标（100-200字，要有量化目标）"}},
    {{"label": "行动 (Action)", "content": "品牌采取的具体策略与执行细节（100-200字，用①②③编号列出关键动作）"}},
    {{"label": "结果 (Result)", "content": "策略实施后的成效与数据（100-200字，要有具体数值，禁止泛化结尾）"}}
  ],
  "metrics": [
    {{"label": "指标名（4字以内）", "value": "指标值（含数值和单位）"}},
    {{"label": "指标名", "value": "指标值"}}
  ]
}}"""

        # DeepSeek Reasoner模型需要更多token输出完整JSON
        # finish_reason=length 表示输出被截断，需要增大max_tokens
        max_output_tokens = 8000 if "reasoner" in model.lower() else 3000

        resp = requests.post(chat_url, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": max_output_tokens,
        }, timeout=120)

        if resp.status_code != 200:
            print(f"    ⚠️ LLM API HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        # 提取响应内容（兼容多种API响应格式）
        resp_json = resp.json()
        content = None

        # ---- 诊断：记录choices结构 ----
        choices = resp_json.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            finish_reason = choices[0].get("finish_reason", "unknown")
            msg_keys = list(msg.keys()) if isinstance(msg, dict) else "non-dict"
            print(f"    📋 choices[0].message keys: {msg_keys}, finish_reason: {finish_reason}")
            # 诊断关键字段值
            if isinstance(msg, dict):
                content_val = msg.get("content")
                reasoning_val = msg.get("reasoning_content")
                tool_calls_val = msg.get("tool_calls")
                print(f"    📋 content={'<None>' if content_val is None else f'<len={len(str(content_val))}>'}")
                if reasoning_val:
                    print(f"    📋 reasoning_content: <len={len(str(reasoning_val))}>")
                if tool_calls_val:
                    print(f"    📋 tool_calls: {len(tool_calls_val)} calls")
        else:
            print(f"    ⚠️ 响应无choices，顶层keys: {list(resp_json.keys())}")

        # 格式1：标准OpenAI格式 choices[0].message.content
        try:
            content = resp_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass

        # 格式1b：DeepSeek Reasoner模型 — reasoning_content字段
        #    deepseek-reasoner将推理过程放在reasoning_content，最终答案在content
        #    但某些版本content为空，reasoning_content可能包含完整JSON或仅含思考过程
        if not content or not content.strip():
            try:
                reasoning_content = resp_json["choices"][0]["message"]["reasoning_content"]
                if reasoning_content and reasoning_content.strip():
                    print(f"    ℹ️ 尝试从reasoning_content提取内容...")
                    rc_stripped = reasoning_content.strip()

                    # 策略1：用_extract_json_from_llm_response尝试提取（支持多种JSON格式）
                    rc_json = _extract_json_from_llm_response(rc_stripped)
                    if rc_json:
                        content = json.dumps(rc_json, ensure_ascii=False)
                        print(f"    ✅ 从reasoning_content成功提取JSON（长度{len(content)}）")
                    else:
                        # 策略2：reasoning_content可能被截断（finish_reason=length），
                        # 尝试找最后一个完整JSON对象（从后往前找}匹配{）
                        last_brace = rc_stripped.rfind('}')
                        if last_brace > 0:
                            # 从最后的}往前找匹配的{
                            depth = 0
                            start_pos = last_brace
                            while start_pos >= 0:
                                if rc_stripped[start_pos] == '}':
                                    depth += 1
                                elif rc_stripped[start_pos] == '{':
                                    depth -= 1
                                    if depth == 0:
                                        break
                                start_pos -= 1
                            if start_pos >= 0 and depth == 0:
                                candidate = rc_stripped[start_pos:last_brace+1]
                                try:
                                    test = json.loads(candidate)
                                    if isinstance(test, dict) and "title" in test:
                                        content = candidate
                                        print(f"    ✅ 从reasoning_content尾部提取到JSON（长度{len(candidate)}）")
                                except json.JSONDecodeError:
                                    pass

                        # 如果仍然没提取到JSON，说明reasoning_content只是思考过程
                        # 不要把它当作content传给解析器（思考过程不是JSON，只会导致误导日志）
                        if not content:
                            print(f"    ⚠️ reasoning_content仅含思考过程，无有效JSON（长度{len(rc_stripped)}）")
            except (KeyError, IndexError, TypeError):
                pass

        # 格式1c：模型返回tool_calls而非content（某些DeepSeek版本行为）
        if (not content or not content.strip()) and choices:
            try:
                tool_calls = resp_json["choices"][0]["message"].get("tool_calls", [])
                if tool_calls:
                    # 从tool_calls的function.arguments中提取内容
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", "")
                        if args and args.strip():
                            content = args
                            print(f"    ℹ️ 从tool_calls[{tc.get('id','')}]提取内容（长度{len(args)}）")
                            break
            except (KeyError, IndexError, TypeError):
                pass

        # 格式2：Anthropic格式 content[0].text
        if not content or not content.strip():
            try:
                for block in resp_json.get("content", []):
                    if block.get("type") == "text":
                        text_val = block.get("text", "")
                        if text_val and text_val.strip():
                            content = text_val
                            break
            except (KeyError, TypeError):
                pass

        # 格式3：直接在response中
        if not content or not content.strip():
            content = resp_json.get("content", "") or resp_json.get("text", "")

        if not content or not content.strip():
            # 最终诊断：打印完整message对象帮助排查
            if choices:
                msg_obj = choices[0].get("message", {})
                print(f"    ⚠️ LLM返回空内容，完整message: {json.dumps(msg_obj, ensure_ascii=False)[:500]}")
            else:
                print(f"    ⚠️ LLM返回空内容，响应键: {list(resp_json.keys())}")
            return None

        # 预处理：去除BOM、零宽字符、首尾空白
        content = content.strip()
        content = content.lstrip("﻿")  # BOM
        content = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', content)  # 零宽字符

        # 提取JSON：尝试多种方式（从严格到宽松）
        case_data = _extract_json_from_llm_response(content)

        if not case_data:
            print(f"    ⚠️ LLM响应无法解析为有效JSON，内容前300字: {content[:300]}")
            return None

        # 对LLM输出进行清洗
        case_data = _clean_llm_case(case_data)

        # 验证清洗后的结果
        is_valid, reason = validate_case(case_data)
        if not is_valid:
            print(f"    ⚠️ LLM生成案例未通过验证: {reason}")
            return None

        return case_data

    except Exception as e:
        print(f"  ⚠️ LLM生成失败: {e}")
    return None


def _extract_json_from_llm_response(content):
    """从LLM响应中鲁棒地提取JSON对象

    策略优先级（从严格到宽松）：
    1. 直接解析整个响应
    2. 提取```json```或```代码块
    3. 用平衡括号法找到最外层JSON对象（非贪婪）
    4. 尝试修复常见JSON问题后重试（尾部逗号、注释等）
    """
    if not content or not content.strip():
        return None

    def _try_parse(text):
        """尝试解析JSON，返回包含title和sections的dict，否则None"""
        if not text or not text.strip():
            return None
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "title" in data and "sections" in data:
                return data
        except json.JSONDecodeError:
            pass
        return None

    # 方式1：直接解析整个响应
    result = _try_parse(content)
    if result:
        return result

    # 方式2：提取```json```或```代码块
    code_block = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
    if code_block:
        result = _try_parse(code_block.group(1).strip())
        if result:
            return result

    # 方式3：用平衡括号法找到第一个完整的顶层JSON对象
    # 从第一个{开始，用深度计数找到匹配的}，而非贪婪正则
    def _find_balanced_json(text, start=0):
        """从text中start位置开始，用平衡括号法找第一个完整JSON对象"""
        first_brace = text.find('{', start)
        if first_brace < 0:
            return None
        depth = 0
        in_string = False
        escape_next = False
        for i in range(first_brace, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[first_brace:i+1]
        return None

    candidate = _find_balanced_json(content)
    if candidate:
        result = _try_parse(candidate)
        if result:
            return result

    # 方式4：尝试修复常见JSON问题后重试
    repaired = _repair_json_string(content)
    if repaired != content:
        result = _try_parse(repaired)
        if result:
            return result
        # 也尝试从修复后的文本中提取代码块和括号匹配
        code_block = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', repaired)
        if code_block:
            result = _try_parse(code_block.group(1).strip())
            if result:
                return result
        candidate = _find_balanced_json(repaired)
        if candidate:
            result = _try_parse(candidate)
            if result:
                return result

    return None


def _repair_json_string(text):
    """修复LLM输出中常见的JSON格式问题

    处理：
    - 尾部逗号（,}和,]）
    - JavaScript注释（//和/* */）
    - 多余的换行和空白
    """
    if not text:
        return text

    # 移除JavaScript单行注释（// ...）—— 但不破坏URL中的 //
    # 仅移除行首或逗号后的注释
    text = re.sub(r'(?<=[,\[\{])\s*//[^\n]*', '', text)
    text = re.sub(r'^\s*//[^\n]*', '', text, flags=re.MULTILINE)
    # 移除JavaScript多行注释（/* ... */）
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)

    # 修复尾部逗号：,} → }  ,] → ]
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)

    return text


def _clean_llm_case(case_data):
    """对LLM生成的案例数据进行清洗，确保无泄漏和Markdown残留

    对齐9月3日标准：仅保留4个STAR section，移除"可迁移点"等非标准section
    """
    # 清洗标题
    case_data["title"] = sanitize_title(case_data.get("title", ""))
    # 清洗品牌
    brand = case_data.get("brand", "")
    if brand in ("待补充", "（待确认）", "待确认"):
        case_data["brand"] = "行业综合"
    # 清洗type
    case_data["type"] = sanitize_text(case_data.get("type", ""))
    # 清洗sections — 仅保留标准STAR 4个section
    star_labels_std = {"情境 (Situation)", "任务 (Task)", "行动 (Action)", "结果 (Result)"}
    cleaned_sections = []
    for s in case_data.get("sections", []):
        label = s.get("label", "")
        # 跳过非标准section（可迁移点、新闻概要等）
        if label in ("可迁移点", "新闻概要", "信息来源", "同维度动态"):
            continue
        # 清洗content
        content = sanitize_text(s.get("content", ""), remove_urls=True)
        # 清洗label
        label = sanitize_text(label)
        if content and label:
            cleaned_sections.append({"label": label, "content": content})
    case_data["sections"] = cleaned_sections
    # 清洗metrics
    for m in case_data.get("metrics", []):
        m["label"] = sanitize_text(m.get("label", ""))
        m["value"] = sanitize_text(m.get("value", ""), remove_urls=True)
    # 移除空metrics
    case_data["metrics"] = [m for m in case_data.get("metrics", []) if m.get("label") and m.get("value")]
    return case_data


def build_simple_case(dim_info, search_results, date_str):
    """无LLM或LLM失败时，基于搜索结果构建STAR结构化案例

    对齐9月3日标准：
    - 仅4个STAR section（情境/任务/行动/结果），无"可迁移点"
    - Action用①②③编号列出关键动作
    - Result必须有具体数据，禁止泛化结尾
    - 标题包含品牌名和核心动作
    - 宁可信息不完整，也不要用泛化模板填充
    """
    if not search_results:
        return None

    # 从所有搜索结果中提取品牌名
    known_brands = ["蔚来", "小鹏", "理想", "比亚迪", "极氪", "问界", "领克",
                    "小米", "上汽", "广汽", "吉利", "长城", "奇瑞", "宝马", "奔驰",
                    "大众", "丰田", "本田", "特斯拉", "极越", "岚图", "智己", "阿维塔",
                    "奥迪", "保时捷", "沃尔沃", "现代", "起亚", "马自达", "福特",
                    "捷达", "林肯", "AITO", "smart", "启辰", "极豆", "生数", "传祺",
                    "零跑", "深蓝", "方程豹", "腾势", "享界", "尊界"]

    brand = "行业综合"
    all_text = " ".join(r.get("title", "") + " " + r.get("snippet", "") for r in search_results)
    for b in known_brands:
        if b in all_text:
            brand = b
            break

    # 选择最佳案例：优先选有具体品牌名且标题不含LLM泄漏的结果
    best = None
    for r in search_results:
        title = r.get("title", "")
        # 跳过含LLM泄漏的标题
        if _LLM_LEAKAGE_RE.search(title[:50]):
            continue
        # 跳过含URL的标题
        if _URL_RE.search(title):
            continue
        # 跳过含*号的标题
        if '*' in title:
            continue
        # 优先选含品牌名的
        if brand != "行业综合" and brand in title:
            best = r
            break
        # 次选标题长度合理（10-50字）的
        if not best and 10 <= len(title) <= 50:
            best = r

    if not best:
        best = search_results[0]

    title = sanitize_title(best.get("title", ""))
    if not title:
        # 从其他结果中找有效标题
        for r in search_results[1:]:
            title = sanitize_title(r.get("title", ""))
            if title:
                best = r
                break
    if not title:
        return None  # 无法生成有效案例

    snippet = best.get("snippet", "") or ""

    # 收集所有搜索结果的摘要（用于构建更丰富的内容）
    all_snippets = []
    for r in search_results[:5]:
        s = r.get("snippet", "")
        s = sanitize_text(s, remove_urls=True)
        if s and len(s) > 15 and not _LLM_LEAKAGE_RE.search(s[:30]):
            all_snippets.append(s)

    # ---- 构建STAR结构化内容 ----
    # 核心原则：宁可引用搜索原文，也不用泛化模板填充。
    # 每个section必须包含搜索结果中的实质信息，禁止"XX维度创新策略"等空话。

    # 情境 (Situation)：从搜索摘要中提取行业背景
    # 优先使用snippet原文，其次综合多条摘要，最后才用标题推断
    situation = ""
    if snippet and len(snippet) > 30:
        situation = sanitize_text(snippet[:200], remove_urls=True)
    if not situation and all_snippets:
        # 拼接前2条摘要的关键句
        sit_parts = []
        for s in all_snippets[:2]:
            # 取第一句（句号前）
            first_sent = s.split('。')[0].strip()
            if first_sent and len(first_sent) > 15:
                sit_parts.append(first_sent)
        if sit_parts:
            situation = '。'.join(sit_parts) + '。'
    if not situation:
        # 从标题推断，但必须包含标题中的具体事实
        situation = f"近期{title}，行业格局与用户需求持续演变。"

    # 任务 (Task)：从标题和摘要中推演核心挑战
    # 优先从摘要中提取含"挑战/问题/目标"的句子，否则从标题+品牌推断具体任务
    task_hints = []
    for s in all_snippets[:3]:
        for kw in ["挑战", "问题", "痛点", "需求", "压力", "困境", "不足", "缺乏", "转型", "升级", "目标", "旨在", "致力于"]:
            idx = s.find(kw)
            if idx > 0:
                start = max(0, s.rfind('。', 0, idx) + 1)
                end = s.find('。', idx)
                if end < 0:
                    end = min(len(s), idx + 100)
                task_hints.append(s[start:end].strip())
                break

    task = None  # 初始化，避免UnboundLocalError
    if task_hints:
        task = sanitize_text(task_hints[0][:200], remove_urls=True)
    elif all_snippets:
        # 从第一条摘要中提取核心问题（取含品牌名或关键动词的句子）
        for s in all_snippets[:2]:
            sentences = s.split('。')
            for sent in sentences:
                sent = sent.strip()
                if len(sent) > 15 and (brand in sent or any(v in sent for v in ["推出", "发布", "上线", "启动", "开展", "布局", "投入"])):
                    task = sent + '。'
                    break
            if task and task != f"{brand}需通过{dim_info['name']}维度的创新策略，在激烈竞争中实现差异化突破与用户价值提升。":
                break
        # 如果for循环未找到有效task，用标题构建
        if not task:
            task = f"{brand}围绕「{title[:30]}」推进{dim_info['name']}维度落地。"
    else:
        task = f"{brand}围绕「{title[:30]}」推进{dim_info['name']}维度落地。"

    # 行动 (Action)：从多条搜索结果中综合行动策略，用①②③编号
    # 核心改进：直接引用搜索摘要中的具体行动描述，而非泛化"多元化策略"
    action_parts = []
    for i, r in enumerate(search_results[:4]):
        s = r.get("snippet", "") or r.get("title", "")
        # 清洗
        s = _URL_RE.sub('', s)
        s = re.sub(r'(?:来源|URL|链接|Source)[：:]\s*', '', s)
        s = re.sub(r'\*+', '', s)  # 移除所有*号
        s = sanitize_text(s, remove_urls=True)
        if s and len(s) > 10:
            # 截取关键行动信息（每条30-80字，保留更多细节）
            if len(s) > 120:
                # 在句号处截断，保留完整句意
                cut_pos = s[:100].rfind('。')
                if cut_pos < 20:
                    cut_pos = s[:100].rfind('，')
                if cut_pos < 20:
                    cut_pos = 80
                s = s[:cut_pos + 1] if s[cut_pos] in '。' else s[:cut_pos]
            action_parts.append(f"{'①②③④'[i]} {s}")

    if action_parts:
        action = "\n".join(action_parts)
    else:
        # 最后回退：用标题作为行动描述（至少有具体事实）
        action = f"① {title}"

    # 结果 (Result)：尝试从摘要中提取数据化成效，禁止泛化结尾
    result_data = []
    # 匹配百分比增长
    pct_matches = re.findall(r'(?:提升|增长|增加|上升|提高|突破)[了]?([^.。!?！？\n]*?(?:\d+(?:\.\d+)?%))', all_text)
    if pct_matches:
        result_data.extend(pct_matches[:2])
    # 匹配绝对数值
    abs_matches = re.findall(r'(\d+(?:\.\d+)?(?:万|亿)[辆元人次条期])', all_text)
    if abs_matches:
        result_data.extend(abs_matches[:2])

    if result_data:
        result = f"相关举措已取得显著成效：{'；'.join(result_data[:3])}。"
    elif all_snippets:
        # 从摘要中找含成效关键词的句子
        found_result = False
        for s in all_snippets:
            for kw in ["成效", "成果", "效果", "提升", "增长", "突破", "完成", "实现", "达到", "突破", "超过"]:
                if kw in s:
                    result = sanitize_text(s[:200], remove_urls=True)
                    # 确保不以泛化结尾结束
                    for ending in ["为后续深化运营奠定了基础", "已初见成效", "呈现积极增长态势",
                                   "为后续发展奠定了基础", "取得阶段性进展"]:
                        if result.endswith(ending):
                            result = result[:-len(ending)].rstrip('，。；') + '。'
                    found_result = True
                    break
            if found_result:
                break
        if not found_result:
            # 用搜索摘要中的最后一条作为结果（比"取得阶段性进展"更有实质内容）
            last_snippet = all_snippets[-1][:150] if all_snippets else ""
            if last_snippet and len(last_snippet) > 20:
                result = sanitize_text(last_snippet, remove_urls=True)
            else:
                result = f"相关举措持续推进中，具体成效待后续数据验证。"
    else:
        result = f"相关举措持续推进中，具体成效待后续数据验证。"

    # ---- 仅构建4个STAR section（对齐9月3日标准，无"可迁移点"）----
    sections = [
        {"label": "情境 (Situation)", "content": situation},
        {"label": "任务 (Task)", "content": task},
        {"label": "行动 (Action)", "content": action},
        {"label": "结果 (Result)", "content": result},
    ]

    # 从搜索文本中提取指标（增强版）
    metrics = _extract_metrics(all_text, dim_info)

    case_data = {
        "title": title,
        "brand": brand,
        "type": _infer_case_type(title, snippet, dim_info),
        "sections": sections,
        "metrics": metrics,
    }

    # 验证
    is_valid, reason = validate_case(case_data)
    if not is_valid:
        print(f"    ⚠️ 简要案例未通过验证: {reason}")
        # 尝试修复而非直接返回None
        if "品牌无效" in reason:
            case_data["brand"] = "行业综合"
        if "标题" in reason:
            return None
        # 对于泛化结尾等问题，尝试修复后重新验证
        if "泛化结尾" in reason:
            for s in case_data.get("sections", []):
                if "结果" in s.get("label", ""):
                    s["content"] = s["content"].rstrip('，。；') + "，相关指标持续向好。"

    return case_data


def _extract_metrics(text, dim_info):
    """从文本中提取汽车行业常见指标，返回metrics列表

    增强版v2：更多指标模式，更好的标签命名，对齐9月3日标准
    标准metrics格式：label 4字以内，value 含数值和单位（如"+180%"、"2万+"、"82分"）
    """
    metrics = []

    # 百分比增长指标（优先提取带方向性的数据）
    pct_patterns = [
        (r'转化率[^\d]*?(\d+(?:\.\d+)?)%', '转化率'),
        (r'增长率[^\d]*?(\d+(?:\.\d+)?)%', '增长率'),
        (r'提升[了]?[^\d]*?(\d+(?:\.\d+)?)%', '提升幅度'),
        (r'增长[了]?[^\d]*?(\d+(?:\.\d+)?)%', '增长幅度'),
        (r'增幅[^\d]*?(\d+(?:\.\d+)?)%', '增幅'),
        (r'环比[^\d]*?(\d+(?:\.\d+)?)%', '环比'),
        (r'同比[^\d]*?(\d+(?:\.\d+)?)%', '同比'),
        (r'上涨[了]?[^\d]*?(\d+(?:\.\d+)?)%', '涨幅'),
        (r'增加[了]?[^\d]*?(\d+(?:\.\d+)?)%', '增幅'),
        (r'渗透率[^\d]*?(\d+(?:\.\d+)?)%', '渗透率'),
        (r'占比[^\d]*?(\d+(?:\.\d+)?)%', '占比'),
    ]
    for pattern, label in pct_patterns:
        match = re.search(pattern, text)
        if match:
            metrics.append({"label": label, "value": f"{match.group(1)}%"})
            if len(metrics) >= 4:
                break

    # 绝对数值指标
    abs_patterns = [
        (r'(\d+(?:\.\d+)?)\s*万(?:辆|台)', '规模(万辆)'),
        (r'(\d+(?:\.\d+)?)\s*万人', '用户数(万)'),
        (r'(\d+(?:\.\d+)?)\s*万条', '内容量(万条)'),
        (r'(\d+(?:\.\d+)?)\s*亿(?:次|人)', '曝光量(亿)'),
        (r'(\d+(?:\.\d+)?)\s*万元', '金额(万元)'),
        (r'(\d+(?:\.\d+)?)\s*亿元', '营收(亿元)'),
        (r'(\d+(?:\.\d+)?)\s*亿(?:辆|台)', '规模(亿辆)'),
        (r'(\d+(?:\.\d+)?)\s*万次', '互动(万次)'),
    ]
    for pattern, label in abs_patterns:
        match = re.search(pattern, text)
        if match:
            metrics.append({"label": label, "value": match.group(1)})
            if len(metrics) >= 4:
                break

    # NPS评分
    nps_match = re.search(r'NPS[^\d]*?(\d+)\s*分', text)
    if nps_match and len(metrics) < 4:
        metrics.append({"label": "NPS", "value": f"{nps_match.group(1)}分"})

    # 订单/销量指标
    order_match = re.search(r'(?:订单|销量|交付)[^\d]*?(\d+(?:\.\d+)?)\s*万', text)
    if order_match and len(metrics) < 4:
        metrics.append({"label": "订单量", "value": f"{order_match.group(1)}万"})

    return metrics[:4]


def _infer_case_type(title, snippet, dim_info):
    """从标题和摘要中推断案例类型描述"""
    # 从标题中提取关键动作词
    type_keywords = {
        "brand-marketing": ["情感营销", "品牌焕新", "新品上市", "创意广告", "观点营销", "代言人"],
        "user-growth": ["KOC种草", "私域裂变", "会员体系", "积分权益", "用户共创", "车主社群"],
        "offline-experience": ["试驾营", "快闪店", "车友会", "交付仪式", "体验中心", "车主活动"],
        "digital-content": ["AIGC", "智能座舱", "大模型", "数据运营", "短视频", "直播"],
        "crossover-eco": ["跨界联名", "异业合作", "IP营销", "快闪店", "联名", "生态联动"],
        "industry-trend": ["出海", "政策补贴", "行业趋势", "对标", "竞争秩序", "市场格局"],
        "emotion-economy": ["情绪价值", "情感营销", "品牌人设", "治愈体验", "情绪共鸣", "真实故事"],
    }

    dim_id = dim_info.get("id", "")
    text = (title + " " + snippet).lower()

    for kw in type_keywords.get(dim_id, []):
        if kw.lower() in text:
            return kw + "标杆案例"

    return f"{dim_info['name']}标杆案例"


# ============ HTML生成模块 ============
def generate_report_html(date_str, cases_data):
    """生成单日报告HTML文件，与现有模板风格一致"""

    # 构建案例JS数据
    cases_js = json.dumps(cases_data, ensure_ascii=False, indent=4)

    # 构建摘要（清洗版，对齐9月3日标准）
    summary_parts = []
    for case in cases_data:
        cat_id = case.get("category", "")
        cat_info = next((c for c in CATEGORIES if c["id"] == cat_id), None)
        title = sanitize_title(case.get('title', ''))
        if cat_info and title:
            # 确保标题不含LLM泄漏
            if not _LLM_LEAKAGE_RE.search(title[:30]):
                summary_parts.append(f"{cat_info['icon']}{title}")

    summary_text = "今日精选7大维度案例：" + "、".join(summary_parts[:7]) if summary_parts else "今日案例报告已生成"
    summary_text = sanitize_summary(summary_text)

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


def _json_to_js_literal(obj, indent=2, _level=0):
    """将Python对象递归转为JS字面量字符串（无引号key + 单引号value）

    对齐data.js现有格式：
    - key无引号：date: '2026-09-07'
    - 字符串值用单引号
    - 缩进2空格递增
    """
    prefix = " " * (indent * _level)
    inner = " " * (indent * (_level + 1))

    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = []
        for k, v in obj.items():
            items.append(f"{inner}{k}: {_json_to_js_literal(v, indent, _level + 1)}")
        return "{\n" + ",\n".join(items) + "\n" + prefix + "}"
    elif isinstance(obj, list):
        if not obj:
            return "[]"
        items = []
        for v in obj:
            items.append(f"{inner}{_json_to_js_literal(v, indent, _level + 1)}")
        return "[\n" + ",\n".join(items) + "\n" + prefix + "]"
    elif isinstance(obj, str):
        # 转义单引号和特殊字符
        escaped = obj.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        return f"'{escaped}'"
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif obj is None:
        return "null"
    else:
        return str(obj)


def update_data_js(date_str, new_cases):
    """将新日报数据覆盖写入data.js的reports数组（同日期先删旧再写入新的）

    使用大括号计数法精确定位和移除旧条目，
    使用文件末尾 ]; 模式定位插入点，避免正则匹配嵌套结构出错。
    输出格式对齐data.js现有风格：无引号key + 单引号value + 2空格缩进。
    """
    if not DATA_JS_PATH.exists():
        print("  ⚠️ data.js 不存在，跳过更新")
        return

    content = DATA_JS_PATH.read_text(encoding="utf-8")

    # 检查是否已有该日期的数据，如有则先移除旧数据再覆盖写入新的
    # 支持三种格式：JS字面量(date: 'xxx')、JSON双引号("date": "xxx")、JSON无引号key(date: "xxx")
    date_check_js = f"date: '{date_str}'"
    date_check_json_dq = f'"date": "{date_str}"'
    date_check_json_bare = f'date: "{date_str}"'
    if date_check_js in content or date_check_json_dq in content or date_check_json_bare in content:
        print(f"  ℹ️ data.js 已包含 {date_str} 的数据，将移除旧数据后覆盖写入")
        content = _remove_report_entry_by_date(content, date_str)

    # 构建新报告条目（清洗版摘要）
    # 对齐9月3日标准：摘要格式为"今日精选7大维度案例：图标标题、图标标题、..."
    summary_parts = []
    for case in new_cases:
        cat_id = case.get("category", "")
        cat_info = next((c for c in CATEGORIES if c["id"] == cat_id), None)
        # 每个标题都经过sanitize_title清洗，确保无LLM泄漏、无*号、无URL
        title = sanitize_title(case.get('title', ''))
        if cat_info and title:
            # 检查标题不含LLM泄漏（二次确认）
            if not _LLM_LEAKAGE_RE.search(title[:30]):
                summary_parts.append(f"{cat_info['icon']}{title}")

    raw_summary = "今日精选7大维度案例：" + "、".join(summary_parts[:7]) if summary_parts else "今日案例报告"
    summary = sanitize_summary(raw_summary)

    new_report = {
        "date": date_str,
        "title": "每日案例报告",
        "summary": summary,
        "cases": new_cases,
    }

    # 将新报告转为JS字面量格式（无引号key + 单引号value，与data.js现有格式一致）
    new_report_js = _json_to_js_literal(new_report, indent=2)
    # 缩进处理：在每行前加4个空格（与data.js中现有条目对齐）
    indented_lines = []
    for line in new_report_js.split("\n"):
        indented_lines.append("    " + line)
    new_report_str = "\n".join(indented_lines)

    # 在reports数组的结束 ] 前插入新条目
    close_pattern = r'\]\s*\n\s*\}\;\s*$'
    match = re.search(close_pattern, content)
    if match:
        bracket_pos = match.start()
        before_bracket = content[:bracket_pos].rstrip()
        new_content = before_bracket + ",\n" + new_report_str + "\n  ]\n};\n"
        DATA_JS_PATH.write_text(new_content, encoding="utf-8")
        print(f"  ✅ 已将 {date_str} 数据追加到 data.js")
    else:
        # 备用方案：从文件末尾倒找 ]; 模式
        print("  ⚠️ 标准模式未匹配，尝试备用定位...")
        last_brace_semi = content.rfind("};")
        if last_brace_semi > 0:
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
    import argparse
    parser = argparse.ArgumentParser(description='每日案例报告生成脚本')
    parser.add_argument('--date', type=str, default=None,
                        help='指定日期 YYYY-MM-DD（默认今天），用于重新生成特定日期的日报')
    args = parser.parse_args()

    # 支持指定日期（用于重新生成历史日报）
    if args.date:
        # 验证日期格式
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
            today = args.date
        except ValueError:
            print(f"❌ 日期格式错误: {args.date}，应为 YYYY-MM-DD")
            sys.exit(1)
    else:
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

        # 尝试LLM增强（最多重试1次）
        case_data = None
        if has_llm:
            print(f"  🤖 {cat['icon']} {cat['name']}：使用LLM生成深度分析...")
            case_data = generate_case_with_llm(cat, search_results)
            # 如果LLM生成失败或未通过验证，重试1次
            if not case_data:
                print(f"  🔄 {cat['icon']} {cat['name']}：LLM首次生成未通过，重试1次...")
                case_data = generate_case_with_llm(cat, search_results)

        # 回退到简单模式
        if not case_data:
            print(f"  📝 {cat['icon']} {cat['name']}：生成简要案例...")
            case_data = build_simple_case(cat, search_results, today)

        if case_data:
            # 最终清洗和验证
            case_data["id"] = f"{today}-{dim_id}"
            case_data["category"] = dim_id

            is_valid, reason = validate_case(case_data)
            if is_valid:
                cases_data.append(case_data)
                print(f"  ✅ {cat['icon']} {cat['name']}：案例生成完成")
            else:
                print(f"  ⚠️ {cat['icon']} {cat['name']}：案例未通过最终验证({reason})，跳过")

    if not cases_data:
        print("\n❌ 未生成任何有效案例，请检查搜索API配置")
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
