# AI生成
#!/usr/bin/env python3
"""
generate_report.py 增强修复补丁 v2（模板化分析 + 标签 + Flash兼容）
======================================================================

相比 v1 补丁新增：
  - 4种分析模板：STAR / PDCA / SWOT / 5W1H，按维度自动匹配
  - 案例标签(tags)字段：LLM自动提取3-6个关键词标签
  - deepseek-v4-flash 兼容：max_tokens提升至4096，解决深度思考模型空content
  - HTML渲染增强：模板徽章 + 标签胶囊

Bug修复（继承v1）：
  - [FIX-A] isinstance(content, dict) → 兼容list/dict两种格式
  - [FIX-B] JSON未找到时打印错误日志（不再静默返回None）
  - [FIX-C] 处理深度思考模型返回空content（检查reasoning_content）

使用方法：
  1. 将 ANALYSIS_TEMPLATES / DIMENSION_TEMPLATE_MAP 两个常量添加到 generate_report.py 顶部（CATEGORIES之后）
  2. 将 search_with_deepseek_websearch 函数替换原函数
  3. 将 generate_case_with_llm 函数替换原函数
  4. 在 generate_report_html 的案例卡片渲染部分添加模板徽章和标签胶囊（见底部HTML补丁说明）
  5. 在 build_simple_case 返回值中添加 "template": "简报", "tags": [] 字段
"""
import json, os, re, requests


# ============ 分析模板定义 ============

ANALYSIS_TEMPLATES = {
    "STAR": {
        "name": "STAR法则",
        "description": "情境→任务→行动→结果，适用于标杆案例深度拆解",
        "sections": [
            {"label": "情境 (Situation)", "hint": "描述案例发生的背景和市场环境"},
            {"label": "任务 (Task)", "hint": "明确品牌/企业需要解决的核心问题"},
            {"label": "行动 (Action)", "hint": "详细描述采取的具体策略和执行步骤"},
            {"label": "结果 (Result)", "hint": "量化呈现取得的成效和关键数据"},
            {"label": "可迁移点", "hint": "其他品牌可复用的方法论和启示"},
        ],
    },
    "PDCA": {
        "name": "PDCA循环",
        "description": "计划→执行→检查→改进，适用于运营优化与迭代复盘",
        "sections": [
            {"label": "计划 (Plan)", "hint": "目标和策略规划"},
            {"label": "执行 (Do)", "hint": "具体实施步骤和资源投入"},
            {"label": "检查 (Check)", "hint": "效果评估和数据验证"},
            {"label": "改进 (Act)", "hint": "优化迭代和长期机制"},
            {"label": "可迁移点", "hint": "其他品牌可复用的方法论"},
        ],
    },
    "SWOT": {
        "name": "SWOT分析",
        "description": "优势-劣势-机会-威胁，适用于战略研判与竞争定位",
        "sections": [
            {"label": "优势 (Strengths)", "hint": "内部核心竞争力和差异化优势"},
            {"label": "劣势 (Weaknesses)", "hint": "内部短板和待改进领域"},
            {"label": "机会 (Opportunities)", "hint": "外部市场趋势和政策红利"},
            {"label": "威胁 (Threats)", "hint": "外部竞争压力和风险因素"},
            {"label": "战略建议", "hint": "基于SWOT的行动建议"},
        ],
    },
    "5W1H": {
        "name": "5W1H分析法",
        "description": "谁-什么-何时-何地-为何-如何，适用于事件解读与趋势速览",
        "sections": [
            {"label": "Who (主体)", "hint": "涉及的核心品牌/企业/人物"},
            {"label": "What (事件)", "hint": "发生了什么关键事件或动作"},
            {"label": "When (时间)", "hint": "时间节点和节奏安排"},
            {"label": "Where (场景)", "hint": "发生场景和渠道布局"},
            {"label": "Why (动因)", "hint": "背后的战略意图和市场逻辑"},
            {"label": "How (方法)", "hint": "具体执行方式和创新手法"},
        ],
    },
}

# 维度→模板自动映射（可根据需要调整或通过环境变量覆盖）
DIMENSION_TEMPLATE_MAP = {
    "brand-marketing":    "STAR",   # 营销案例 → STAR深度拆解
    "user-growth":        "PDCA",   # 用户运营 → PDCA迭代复盘
    "offline-experience": "STAR",   # 体验案例 → STAR拆解
    "digital-content":    "5W1H",   # 数字化事件 → 5W1H速览
    "crossover-eco":      "SWOT",   # 跨界联动 → SWOT战略研判
    "industry-trend":     "SWOT",   # 行业趋势 → SWOT宏观分析
    "emotion-economy":    "STAR",   # 情绪价值 → STAR案例拆解
}


# ============ 搜索模块（继承v1修复） ============

def search_with_deepseek_websearch(query, num_results=5):
    """修复后: 兼容 list/dict 两种 content 格式"""
    try:
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return []
        api_base = os.environ.get("LLM_API_BASE", "https://api.deepseek.com")
        if "/anthropic" not in api_base:
            base = re.sub(r'/v\d+/?$', '', api_base.rstrip('/'))
            anthropic_url = f"{base}/anthropic/v1/messages"
        else:
            anthropic_url = f"{api_base.rstrip('/')}/v1/messages"
        model = os.environ.get("LLM_MODEL", "deepseek-chat")
        resp = requests.post(anthropic_url, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json",
        }, json={
            "model": model, "max_tokens": 4096,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{"role": "user", "content": f"请搜索以下主题的最新中文新闻，返回{num_results}条最相关的结果，每条包含标题、来源URL和摘要：\n\n{query}"}],
        }, timeout=60)
        if resp.status_code != 200:
            print(f"    ⚠️ DeepSeek联网搜索HTTP {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
        results = []
        content_blocks = data.get("content", [])
        assistant_text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                assistant_text += block.get("text", "")
            if block.get("type") == "web_search_tool_result":
                search_content = block.get("content", {})
                # [FIX-A] 兼容 list（DeepSeek实际格式）和 dict（代码原假设格式）
                if isinstance(search_content, list):
                    for result_item in search_content:
                        if isinstance(result_item, dict) and result_item.get("type") == "web_search_result":
                            results.append({"title": result_item.get("title", ""), "url": result_item.get("url", ""), "snippet": result_item.get("snippet", "")})
                elif isinstance(search_content, dict):
                    for result_item in search_content.get("results", []):
                        results.append({"title": result_item.get("title", ""), "url": result_item.get("url", ""), "snippet": result_item.get("snippet", "")})
        # 调试日志
        block_types = [block.get("type") for block in content_blocks]
        has_structured = any(t == "web_search_tool_result" for t in block_types)
        if not has_structured:
            print(f"    ⚠️ 未找到web_search_tool_result（实际类型: {block_types}），使用fallback")
            print(f"    📝 助手回复前200字: {assistant_text[:200]}")
        elif not results:
            print(f"    ⚠️ web_search_tool_result存在但解析出0条结果，content格式可能变更")
            for block in content_blocks:
                if block.get("type") == "web_search_tool_result":
                    sc = block.get("content")
                    print(f"    📝 content type={type(sc).__name__}, 前200字={json.dumps(sc, ensure_ascii=False)[:200] if sc else 'None'}")
        # Fallback
        if not results and assistant_text:
            url_pattern = r'https?://[^\s<>"\')\]]+'
            urls = re.findall(url_pattern, assistant_text)
            lines = [l.strip() for l in assistant_text.split('\n') if l.strip()]
            intro_patterns = [r'^以下是为', r'^根据搜索', r'^围绕.*主题', r'^我[为给帮]您', r'^为您搜索', r'^以下是搜索', r'^根据您', r'^我整理了', r'^这些是', r'^搜索结果', r'^相关结果', r'^为您找到', r'^找到了?\s*\d', r'^共?\s*\d+\s*条', r'^关于.*搜索', r'^为您呈现', r'^以下是关于']
            for i, line in enumerate(lines[:num_results * 3]):
                clean_line = re.sub(r'^[\d]+[.、)\s]+', '', line)
                is_intro = any(re.match(p, clean_line) for p in intro_patterns)
                if clean_line and len(clean_line) > 5 and not is_intro:
                    url = urls[i] if i < len(urls) else ""
                    results.append({"title": clean_line[:100], "url": url, "snippet": ""})
                    if len(results) >= num_results: break
            if len(results) < num_results:
                print(f"    ⚠️ fallback过滤后仅{len(results)}条结果（目标{num_results}条）")
        return results[:num_results]
    except Exception as e:
        print(f"    ⚠️ DeepSeek联网搜索失败: {e}")
        return []


# ============ 案例生成模块（模板化增强） ============

def generate_case_with_llm(dim_info, search_results):
    """增强版: 支持STAR/PDCA/SWOT/5W1H模板 + 标签提取 + Flash兼容"""
    try:
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        api_base = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        if not api_key:
            return None
        base = api_base.rstrip('/')
        if not re.search(r'/v\d+$', base):
            base = base + '/v1'
        chat_url = f"{base}/chat/completions"

        # --- 模板选择 ---
        dim_id = dim_info.get("id", "")
        # 环境变量覆盖: ANALYSIS_TEMPLATE=PDCA 时强制所有维度使用PDCA
        env_template = os.environ.get("ANALYSIS_TEMPLATE", "").upper()
        if env_template in ANALYSIS_TEMPLATES:
            template_key = env_template
        else:
            template_key = DIMENSION_TEMPLATE_MAP.get(dim_id, "STAR")

        template = ANALYSIS_TEMPLATES[template_key]
        template_name = template["name"]
        template_desc = template["description"]

        # 构建sections的JSON模板和提示
        section_labels = [s["label"] for s in template["sections"]]
        section_hints = "\n".join([f"    - {s['label']}：{s['hint']}" for s in template["sections"]])
        sections_json = ", ".join([f'{{"label": "{s["label"]}", "content": "..."}}' for s in template["sections"]])

        search_summary = "\n".join([f"- {r['title']}: {r.get('snippet', '')}" for r in search_results[:3]])

        prompt = f"""你是一位汽车行业资深分析师，请基于以下搜索结果，为「{dim_info['icon']} {dim_info['name']}」维度生成一个标杆案例分析。

搜索结果：
{search_summary}

分析框架：{template_name}（{template_desc}）

要求：
1. 选择搜索结果中最有代表性的一个案例深入分析
2. 严格按{template_name}框架组织内容，每个环节100-200字
3. 提取3-4个关键指标（metrics），尽量有具体数值
4. 提取可迁移点（其他品牌可复用的方法论）
5. 生成3-6个标签关键词，用于案例分类和检索

各环节内容指引：
{section_hints}

请严格按以下JSON格式输出（不要输出其他内容）：
{{
  "title": "案例标题", "brand": "品牌名", "type": "案例类型描述",
  "template": "{template_key}",
  "tags": ["标签1", "标签2", "标签3"],
  "sections": [
    {sections_json}
  ],
  "metrics": [
    {{"label": "指标名", "value": "指标值"}}, {{"label": "指标名", "value": "指标值"}}
  ]
}}"""

        # [FIX-D] max_tokens提升至4096，兼容deepseek-v4-flash/pro深度思考模型
        # 深度思考模型的reasoning_content会消耗大量token，2000不够
        max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "4096"))

        resp = requests.post(chat_url, headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        }, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }, timeout=60)

        if resp.status_code != 200:
            print(f"    ⚠️ LLM API HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        resp_data = resp.json()
        if "choices" not in resp_data or not resp_data["choices"]:
            print(f"    ⚠️ LLM响应缺少choices，键: {list(resp_data.keys())}")
            return None

        msg = resp_data["choices"][0]["message"]
        content = msg.get("content", "")

        # [FIX-C] 处理深度思考模型返回空content（reasoning消耗了max_tokens）
        if not content:
            reasoning = msg.get("reasoning_content", "")
            print(f"    ⚠️ LLM返回空content（reasoning长度{len(reasoning)}），max_tokens={max_tokens}可能不足")
            print(f"    💡 建议：设置环境变量 LLM_MAX_TOKENS=8192 或更换非深度思考模型")
            return None

        # 提取JSON（支持markdown代码块包裹）
        code_block_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', content)
        if code_block_match:
            json_str = code_block_match.group(1)
        else:
            json_match = re.search(r'\{[\s\S]*\}', content)
            json_str = json_match.group() if json_match else None

        if json_str:
            try:
                case_data = json.loads(json_str)
                # 确保template和tags字段存在
                if "template" not in case_data:
                    case_data["template"] = template_key
                if "tags" not in case_data:
                    case_data["tags"] = []
                print(f"    📋 模板: {template_name} | 标签: {case_data.get('tags', [])}")
                return case_data
            except json.JSONDecodeError as e:
                print(f"    ⚠️ LLM生成失败: JSON解析错误: {e}")
                print(f"    📝 LLM返回前300字: {content[:300]}")
                # 尝试简单修复：去尾部逗号
                repaired = re.sub(r',\s*([}\]])', r'\1', json_str)
                if repaired != json_str:
                    try:
                        case_data = json.loads(repaired)
                        if "template" not in case_data:
                            case_data["template"] = template_key
                        if "tags" not in case_data:
                            case_data["tags"] = []
                        print(f"    ✅ JSON修复后解析成功")
                        return case_data
                    except json.JSONDecodeError:
                        pass
                return None
        else:
            # [FIX-B] 关键修复：打印错误日志而非静默返回None
            print(f"    ⚠️ LLM生成失败: 响应中未找到JSON结构")
            print(f"    📝 LLM返回前300字: {content[:300]}")
            return None
    except Exception as e:
        print(f"    ⚠️ LLM生成失败: {e}")
        return None


# ============ build_simple_case 增强 ============

def build_simple_case(dim_info, search_results, date_str):
    """增强版: 添加template和tags字段"""
    if not search_results:
        return None

    best = search_results[0]
    title = best["title"]
    brand = "待补充"
    snippet = best["snippet"] or "暂无详细描述"

    # 尝试从标题提取品牌名
    known_brands = ["蔚来", "小鹏", "理想", "比亚迪", "极氪", "问界", "领克",
                    "小米", "上汽", "广汽", "吉利", "长城", "奇瑞", "宝马", "奔驰",
                    "大众", "丰田", "本田", "特斯拉", "极越", "岚图", "智己", "阿维塔"]
    for b in known_brands:
        if b in title:
            brand = b
            break

    # 从标题提取简单标签
    tag_keywords = ["新能源", "电动", "智能", "出海", "营销", "私域", "社区",
                    "试驾", "直播", "短视频", "跨界", "联名", "情绪", "服务",
                    "OTA", "AIGC", "用户运营", "会员", "交付", "快闪"]
    tags = [kw for kw in tag_keywords if kw in title or kw in snippet][:4]
    if brand and brand not in tags:
        tags.insert(0, brand)

    sections = [
        {"label": "新闻概要", "content": snippet},
        {"label": "信息来源", "content": f"原标题：{title}。详细内容请访问原文链接。"},
    ]

    # 如果有多条搜索结果，合并为行业动态
    if len(search_results) > 1:
        other_titles = "\n".join([f"· {r['title']}" for r in search_results[1:4]])
        sections.append({"label": "同维度动态", "content": other_titles})

    return {
        "title": title,
        "brand": brand,
        "type": f"{dim_info['name']}行业动态",
        "template": "简报",
        "tags": tags,
        "sections": sections,
        "metrics": [],
    }


# ============ HTML渲染补丁说明 ============
"""
在 generate_report_html 函数中，案例卡片的渲染部分需要添加：

1. 模板徽章（在案例标题旁或卡片头部）：
   找到案例标题渲染位置，添加：
   <span class="template-badge">{case.get('template', 'STAR')}</span>

2. 标签胶囊（在metrics下方或卡片底部）：
   找到metrics渲染结束位置，添加：
   <div class="case-tags">
     {''.join([f'<span class="tag">{t}</span>' for t in case.get('tags', [])])}
   </div>

3. CSS样式（添加到<style>块中）：
   .template-badge {{
     display: inline-block; padding: 2px 10px; border-radius: 6px;
     font-size: 12px; font-weight: 600; margin-left: 8px;
     background: var(--c-primary-bg); color: var(--c-primary);
     border: 1px solid rgba(79,70,229,0.2);
   }}
   .template-badge.pdca {{ background: #fef3c7; color: #92400e; border-color: rgba(245,158,11,0.3); }}
   .template-badge.swot {{ background: #f0fdf4; color: #166534; border-color: rgba(16,185,129,0.3); }}
   .template-badge.5w1h {{ background: #fef2f2; color: #991b1b; border-color: rgba(239,68,68,0.3); }}
   .template-badge.简报 {{ background: #f1f5f9; color: #475569; border-color: rgba(148,163,184,0.3); }}
   .case-tags {{
     display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px;
   }}
   .case-tags .tag {{
     padding: 3px 10px; border-radius: 12px; font-size: 12px;
     background: var(--c-primary-bg); color: var(--c-primary);
     border: 1px solid rgba(79,70,229,0.15); font-weight: 500;
   }}

4. JavaScript中渲染案例时也需要处理template和tags字段。
   在renderCase函数中，标题后添加模板徽章，metrics后添加标签。
"""
