#!/usr/bin/env python3
"""
按章节顺序生成 PPT 大纲 - V2
策略：逐章节生成，每个章节独立调用 AI，不续生成
"""

import re
import json
from typing import List, Dict, Any


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


def generate_outline_by_sections_v2(api, config, brief_text: str,
                                     brand_name: str = "", brand_colors: str = "",
                                     style_description: str = "") -> Dict[str, Any]:
    """
    按章节顺序生成大纲 - V2 版本
    每个章节独立调用 AI，生成 2-5 页，不续生成
    """

    # 1. 提取所有章节
    sections = extract_brief_sections(brief_text)
    if not sections:
        print("[WARN] 未能解析到章节")
        return {"pages": [], "total_pages": 0}

    print(f"[INFO] 解析到 {len(sections)} 个章节: {[s['no']+'｜'+s['title'] for s in sections]}")

    all_pages = []
    current_index = 1

    # 2. 逐章节生成
    for i, section in enumerate(sections):
        sec_no = section["no"]
        sec_title = section["title"]
        sec_body = section["body"]

        print(f"[INFO] [{i+1}/{len(sections)}] 生成章节 {sec_no}｜{sec_title}")

        # 构建严格的单章节提示词
        section_prompt = f"""你是一个专业的PPT大纲拆解专家。请将以下 brief 章节拆解成 2-5 页 PPT。

【品牌信息】
品牌名称: {brand_name if brand_name else '未指定'}
品牌色系: {brand_colors if brand_colors else '根据内容自动识别'}
风格描述: {style_description if style_description else '专业、现代'}

【当前章节 - 必须严格按此生成】
章节编号: {sec_no}
章节标题: {sec_title}
章节内容:
{sec_body}

【排版类型选择】
- 满版图片-全屏背景: 适合封面、策略观点页
- 满版图片-左图右文: 适合内容对比页
- 模块化-卡片: 适合展示多个并列概念（AI自动判断2-5列）
- 模块化-步骤流程: 适合流程说明
- 模块化-时间轴: 适合展示时间线

【严格规则 - 违反会导致错误】
1) 将上方【当前章节】中的**每一个独立话题/事件/动作**都拆成独立页面，确保零遗漏
2) 如果内容包含多个事件（如事件1、事件2、动作1、动作2），每个事件/动作至少1页
3) content 必须来自上方【当前章节】的原文，可以原句拆分/分段粘贴
4) 绝对禁止生成"续""补充""详细"等额外页面
4) 绝对禁止把本章内容写成其他章节的"续"
5) 输出必须是严格 JSON 数组

【输出格式】
```json
[
  {{"index": 1, "title": "页面标题（来自章节内容）", "type": "content", "brief": "排版说明", "layout": "满版图片-全屏背景", "content": "来自章节原文的内容"}},
  {{"index": 2, "title": "页面标题", "type": "content", "brief": "排版说明", "layout": "满版图片-全屏背景", "content": "来自章节原文的内容"}}
]
```

只输出 JSON 数组，不要任何解释文字。"""

        try:
            response = api.chat(
                model=config.get('chat_model', 'gpt-4o'),
                messages=[{'role': 'user', 'content': section_prompt}],
                max_tokens=6000,
                timeout=120
            )

            content = response.get('content', '')
            pages = _extract_pages_from_response(content)

            if pages:
                # 更新页码
                for p in pages:
                    p['index'] = current_index
                    current_index += 1

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
        all_pages.insert(0, cover_page)
        # 重新编号
        for i, p in enumerate(all_pages, 1):
            p['index'] = i

    print(f"[INFO] 总共生成 {len(all_pages)} 页")
    return {
        "pages": all_pages,
        "total_pages": len(all_pages)
    }


def _extract_pages_from_response(content: str) -> List[Dict]:
    """从 AI 响应中提取页面列表"""
    try:
        # 查找 ```json ... ``` 代码块
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
