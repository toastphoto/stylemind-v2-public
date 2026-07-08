#!/usr/bin/env python3
"""
按章节顺序生成 PPT 大纲
策略：逐章节生成，确保每个章节都完整覆盖
"""

import re
from typing import List, Dict, Any, Optional


def extract_brief_sections(text: str) -> List[Dict[str, str]]:
    """提取 brief 中的章节"""
    pat = re.compile(r'(?m)^\s*(\d{2})[｜|]\s*([^\n\r]+)\s*$')
    hits = list(pat.finditer(text or ""))
    if not hits:
        return []

    sections = []
    for idx, m in enumerate(hits):
        start = m.end()
        end = hits[idx + 1].start() if idx + 1 < len(hits) else len(text)
        sec_no = m.group(1)
        sec_title = m.group(2).strip()
        sec_body = (text[start:end] or "").strip()
        sections.append({"no": sec_no, "title": sec_title, "body": sec_body})
    return sections


def generate_outline_by_sections(api, config, brief_text: str, brand_name: str = "",
                                  brand_colors: str = "", style_description: str = "",
                                  progress_callback=None) -> Dict[str, Any]:
    """
    按章节顺序生成大纲

    Args:
        api: API 客户端
        config: 配置
        brief_text: 完整的 brief 文本
        brand_name: 品牌名称
        brand_colors: 品牌色系
        style_description: 风格描述
        progress_callback: 进度回调函数 (current, total, message)

    Returns:
        {"pages": [...], "total_pages": N}
    """
    from .prompt_v2 import SKELETON_PROMPT_V2

    # 1. 提取所有章节
    sections = extract_brief_sections(brief_text)
    if not sections:
        print("[WARN] 未能解析到章节，使用完整 brief 生成")
        return _generate_full(api, config, brief_text, brand_name, brand_colors, style_description)

    print(f"[INFO] 解析到 {len(sections)} 个章节")

    all_pages = []
    current_page_index = 1

    # 2. 逐章节生成
    for i, section in enumerate(sections):
        sec_no = section["no"]
        sec_title = section["title"]
        sec_body = section["body"]

        if progress_callback:
            progress_callback(i + 1, len(sections), f"正在生成第 {sec_no} 章: {sec_title}")

        print(f"[INFO] 生成章节 {sec_no}｜{sec_title}")

        # 构建单章节的提示词
        section_prompt = f"""你是一个专业的PPT大纲拆解专家。请将以下 brief 章节拆解成 PPT 页面。

【品牌信息】
品牌名称: {brand_name if brand_name else '未指定'}
品牌色系: {brand_colors if brand_colors else '根据内容自动识别'}
风格描述: {style_description if style_description else '专业、现代'}

【当前章节】
{sec_no}｜{sec_title}
{sec_body}

【排版类型说明】
1. 满版图片-全屏背景: 全屏背景图+白字叠加，适合封面、策略观点页
2. 满版图片-左图右文: 左侧摄影图+右侧白底文字区，适合内容对比页
3. 模块化-卡片: 多列卡片模块（AI自动判断列数），适合展示多个并列概念
4. 模块化-步骤流程: 纵向/横向步骤展示，适合流程说明
5. 模块化-时间轴: 横向时间轴，适合展示时间线
6. 模块化-表格: 表格形式，适合数据对比
7. 纯视觉页: 只有图片，无文字

【拆分规则】
1) 本章节的文字拆成 2~5 页展示（每页承载一个清晰子点/小段落）
2) content 必须来自原文（可以原句拆分/分段粘贴），不要创作新内容
3) 根据内容选择最合适的 layout 类型
4) 输出必须是严格 JSON 数组

【输出格式】
```json
[
  {{"index": 1, "title": "页面标题", "type": "content", "brief": "排版说明：...", "layout": "满版图片-全屏背景", "content": "来自 brief 的原文内容"}},
  ...
]
```

只输出 JSON 数组，不要任何解释文字。"""

        try:
            response = api.chat(
                model=config.get('chat_model', 'gpt-4o'),
                messages=[{'role': 'user', 'content': section_prompt}],
                max_tokens=8000,  # 单章节不需要太多 token
                timeout=120
            )

            content = response.get('content', '')
            pages = _extract_pages_from_response(content)

            if pages:
                # 更新页码索引
                for p in pages:
                    p['index'] = current_page_index
                    current_page_index += 1

                all_pages.extend(pages)
                print(f"[INFO] 章节 {sec_no} 生成 {len(pages)} 页")
            else:
                print(f"[WARN] 章节 {sec_no} 未能提取到页面")

        except Exception as e:
            print(f"[ERROR] 章节 {sec_no} 生成失败: {e}")
            continue

    # 3. 添加封面页
    if all_pages:
        cover_page = {
            "index": 1,
            "title": brand_name if brand_name else "封面",
            "type": "cover",
            "brief": "排版说明：大标题+副标题+全屏背景",
            "layout": "满版图片-全屏背景",
            "content": brief_text[:200] if len(brief_text) > 200 else brief_text
        }
        # 重新编号
        all_pages.insert(0, cover_page)
        for i, p in enumerate(all_pages, 1):
            p['index'] = i

    return {
        "pages": all_pages,
        "total_pages": len(all_pages)
    }


def _extract_pages_from_response(content: str) -> List[Dict]:
    """从 AI 响应中提取页面列表"""
    import json

    # 尝试提取 JSON
    try:
        # 查找 ```json ... ``` 代码块
        import re
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接找 JSON 数组
            json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', content)
            json_str = json_match.group(0) if json_match else content

        data = json.loads(json_str)

        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'pages' in data:
            return data['pages']
        else:
            return []
    except Exception as e:
        print(f"[ERROR] 解析 JSON 失败: {e}")
        return []


def _generate_full(api, config, brief_text, brand_name, brand_colors, style_description):
    """回退：使用完整 brief 生成（旧逻辑）"""
    from .prompt_v2 import SKELETON_PROMPT_V2

    prompt = SKELETON_PROMPT_V2.format(
        brand_name=brand_name,
        brand_colors=brand_colors,
        style_description=style_description,
        message=brief_text,
        knowledge_context=""
    )

    response = api.chat(
        model=config.get('chat_model', 'gpt-4o'),
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=16000,
        timeout=300
    )

    content = response.get('content', '')
    return _extract_pages_from_response(content)
