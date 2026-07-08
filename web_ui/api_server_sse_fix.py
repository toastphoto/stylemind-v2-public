#!/usr/bin/env python3
"""
SSE 流大纲生成修复 V3 - 长章节自动分批生成
"""

import re
import json


def generate_outline_stream_v3(api, config, message, data, knowledge_context, yield_sse):
    """逐章节生成大纲，长章节自动分批，带进度条"""

    # 提取章节
    pat = re.compile(r'(?m)^\s*(\d{2})[｜|]\s*([^\n\r]+)\s*$')
    hits = list(pat.finditer(message or ""))
    sections = []
    for idx, m in enumerate(hits):
        start = m.end()
        end = hits[idx + 1].start() if idx + 1 < len(hits) else len(message)
        sections.append({
            "no": m.group(1),
            "title": m.group(2).strip(),
            "body": (message[start:end] or "").strip()
        })

    total_sections = len(sections)

    if total_sections == 0:
        yield_sse({"status": "progress", "percent": 20, "message": "未检测到章节格式，使用 AI 直接生成大纲..."})
        return _generate_outline_by_ai(api, config, message, data, knowledge_context, yield_sse)

    yield_sse({"status": "progress", "percent": 20, "message": f"共 {total_sections} 个章节，开始逐章生成..."})

    brand_name = data.get('brand_name', '')
    all_pages = []
    current_index = 1

    # 计算总任务数（长章节可能需要分批）
    BATCH_SIZE = 1500  # 每批最多1500字，确保 AI 能完全覆盖
    total_tasks = 0
    section_tasks = []  # [(section_idx, batch_idx, start, end), ...]
    for i, section in enumerate(sections):
        body = section["body"]
        if len(body) <= BATCH_SIZE:
            section_tasks.append((i, 0, 0, len(body)))
            total_tasks += 1
        else:
            # 按段落分批
            paragraphs = re.split(r'\n\n+', body)
            batch_start = 0
            batch_idx = 0
            current_batch = ""
            for para in paragraphs:
                if len(current_batch) + len(para) > BATCH_SIZE and current_batch:
                    section_tasks.append((i, batch_idx, batch_start, batch_start + len(current_batch)))
                    total_tasks += 1
                    batch_start += len(current_batch)
                    batch_idx += 1
                    current_batch = para + "\n\n"
                else:
                    current_batch += para + "\n\n"
            if current_batch.strip():
                section_tasks.append((i, batch_idx, batch_start, batch_start + len(current_batch)))
                total_tasks += 1

    yield_sse({"status": "progress", "percent": 22, "message": f"共 {total_tasks} 个生成任务（长章节自动分批）"})

    task_done = 0
    last_section_no = None

    for section_idx, batch_idx, start, end in section_tasks:
        section = sections[section_idx]
        sec_no = section["no"]
        sec_title = section["title"]
        sec_body = section["body"][start:end]

        # 显示进度
        if sec_no != last_section_no:
            task_done_label = f"章节 {sec_no}｜{sec_title}"
            last_section_no = sec_no
        else:
            task_done_label = f"章节 {sec_no}｜{sec_title}（续）"

        task_done += 1
        pct = 22 + int((task_done / total_tasks) * 63)
        yield_sse({"status": "progress", "percent": pct, "message": f"生成 {task_done_label} ({task_done}/{total_tasks})..."})

        # 判断是否是分批中的后续批次
        is_continuation = batch_idx > 0

        section_prompt = f"""你是一个专业的PPT大纲拆解专家。请将以下 brief 片段拆解成 2-5 页 PPT。

【品牌信息】
品牌名称: {brand_name if brand_name else '未指定'}

【当前章节】
章节编号: {sec_no}
章节标题: {sec_title}

【当前片段内容（{"第"+str(batch_idx+1)+"批/共多批" if is_continuation else "完整内容"}）】
{sec_body}

{"【注意】这是该章节的第"+str(batch_idx+1)+"批内容，请为这一批内容生成独立的页面。不要重复前面已生成的内容。" if is_continuation else ""}

【严格规则】
1) 将上方【当前片段内容】中的**每一个独立话题/事件/动作**都拆成独立页面，确保零遗漏
2) 如果内容包含多个事件（如事件1、事件2、动作1、动作2），每个事件/动作至少1页
3) content 必须来自上方【当前片段内容】的原文，可以原句粘贴
4) 绝对禁止生成"续""补充"等额外页面
5) 每页 title 应该反映这一页的具体子内容，不要都写章节标题
6) 输出必须是严格 JSON 数组
7) 【最重要】检查你的输出是否覆盖了上方内容的所有部分，如果有遗漏就是错误的

【输出格式】
```json
[
  {{"index": 1, "title": "具体子标题", "type": "content", "brief": "排版说明", "layout": "满版图片-全屏背景", "content": "来自上方原文的内容"}}
]
```"""

        try:
            response = api.chat(
                model=config.get('chat_model', 'gpt-4o'),
                messages=[{'role': 'user', 'content': section_prompt}],
                max_tokens=6000,
                timeout=120
            )

            content = response.get('content', '')
            try:
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', content)
                    json_str = json_match.group(0) if json_match else content

                pages = json.loads(json_str)
                if isinstance(pages, list):
                    for p in pages:
                        p['index'] = current_index
                        current_index += 1
                    all_pages.extend(pages)
                    print(f"[INFO] {task_done_label}: 生成 {len(pages)} 页")
            except Exception as e:
                print(f"[ERROR] 解析 {task_done_label} 失败: {e}")
        except Exception as e:
            print(f"[ERROR] 生成 {task_done_label} 失败: {e}")

    # 添加封面
    if all_pages:
        cover_page = {
            "index": 1,
            "title": brand_name if brand_name else "封面",
            "type": "cover",
            "brief": "排版说明：大标题+副标题+全屏背景",
            "layout": "满版图片-全屏背景",
            "content": message[:200] if len(message) > 200 else message
        }
        all_pages.insert(0, cover_page)
        for i, p in enumerate(all_pages, 1):
            p['index'] = i

    skeleton = {"pages": all_pages, "total_pages": len(all_pages)}
    yield_sse({"status": "progress", "percent": 88, "message": f"大纲生成完成，共 {len(all_pages)} 页"})

    return skeleton


def _generate_outline_by_ai(api, config, message, data, knowledge_context, yield_sse):
    """当用户输入是自然语言（无 Sxx｜章节格式）时，直接调用 AI 生成完整大纲"""

    brand_name = data.get('brand_name', '')

    # 处理超长文本：30MB文档不可能一次性塞进模型上下文
    MAX_INPUT_CHARS = 80000
    _original_len = len(message)
    if len(message) > MAX_INPUT_CHARS:
        print(f"[WARN] 用户输入过长 ({len(message)} 字符)，截断到 {MAX_INPUT_CHARS} 字符")
        message = message[:MAX_INPUT_CHARS] + "\n\n[注意：原文档较长，以上为前半部分内容。请基于已有内容尽可能详细拆分。]"

    has_section_markers = bool(re.search(r'[●◆■▪️]\s*[一二三四五六七八九十]|【.*?页】|step\s*\d|步骤\d|类型[一二三四]', message))
    has_sub_items = message.count('●') + message.count('step') + message.count('类型') + message.count('创意')

    if _original_len > 15000 or has_sub_items > 15:
        page_hint = '至少 40-60 页'
        split_instruction = """
【关键 — 细粒度拆分规则】
这份文档非常详细，你必须把每个独立话题都拆成单独页面：
- 每个 ● 子项 → 独立一页
- 每个 step1/step2/step3 → 各自独立一页
- 每个类型一/类型二/类型三 → 各自独立一页
- 每个竞品案例（小米/华为/海尔）→ 各自至少 2-3 页
- 每个传播阶段（起势期/爆发期/收尾期）下的每个动作 → 独立一页
- 【X页】标记的章节必须拆成 X 个或更多页面

绝对不要合并多个子项到同一页！宁可多拆也不要少拆。
"""
    elif _original_len > 8000 or has_sub_items > 8:
        page_hint = '至少 25-40 页'
        split_instruction = """
【关键 — 细粒度拆分规则】
文档内容较多，请详细拆分：
- 每个 ● 子项或编号子项 → 尽量独立成页
- step1/step2/step3、类型一/类型二 → 各自独立一页
- 每个竞品案例 → 至少 2 页
- 每个传播动作 → 独立一页
"""
    elif '10页' in message or '十页' in message:
        page_hint = '约 8-12 页'
        split_instruction = ''
    elif '5页' in message or '五页' in message:
        page_hint = '约 4-6 页'
        split_instruction = ''
    elif '20页' in message:
        page_hint = '约 18-25 页'
        split_instruction = ''
    else:
        page_hint = '至少 15-25 页'
        split_instruction = '''
【关键 — 细粒度拆分规则】
默认需要较详细的拆分：
- 每个主要话题点都应有独立页面
- 不要过度合并内容到同一页
'''

    yield_sse({"status": "progress", "percent": 30, "message": f"AI 分析需求中（目标{page_hint}）..."})

    outline_prompt = f"""你是一个专业的 PPT 大纲规划专家。请根据用户需求生成一份完整的 PPT 大纲。

【用户需求】
{message}

{f'【品牌名称】{brand_name}' if brand_name else ''}

{knowledge_context[:2000] if knowledge_context else ''}

【核心要求】
1. 生成 {page_hint} 的 PPT 大纲（这是最低要求，内容多的可以更多）
2. 必须包含：封面页 + 详细内容页 + 总结页
3. 每页需要有明确的 title（具体子标题，不要重复泛化）和 content（该页的详细内容）
4. type 取值：cover / content / visual / chart / summary / timeline
5. layout 取值：满版图片-全屏背景 / 满版图片-左图右文 / 模块化-卡片 / 模块化-步骤流程 / 模块化-时间轴 / 模块化-表格 / 纯视觉页
6. brief 字段简要说明这页的排版方向（一句话）
7. content 字段要写足够的内容（3-5句话），不能太简略

【⚠️ 内容边界 — 绝对禁止违反】
- content 字段的所有文字**必须来自用户提供的【用户需求】原文**
- 可以对原文进行**拆分、重组、分段粘贴**，但**绝对禁止自行创作、改写、扩写或添加原文没有的信息**
- 禁止添加"例如"、"比如"后接自己编造的例子
- 禁止添加数据、数字、百分比等原文中没有的信息
- 如果原文某部分信息不足，可以留空或写"待补充"，但不要编造
- 每页的 content 应该是原文的**摘录/拼接**，而不是 AI 的**创作/总结**

{split_instruction}

【输出格式 — 严格 JSON，只输出 JSON 不要其他文字】
```json
{{
  "title": "PPT标题",
  "pages": [
    {{"index": 1, "title": "封面", "type": "cover", "layout": "满版图片-全屏背景", "brief": "全屏背景+大标题", "content": "副标题文字"}},
    {{"index": 2, "title": "具体页面标题（具体子话题）", "type": "content", "layout": "满版图片-左图右文", "brief": "排版说明", "content": "该页详细内容..."}}
  ]
}}
```"""

    try:
        yield_sse({"status": "progress", "percent": 50, "message": "AI 正在生成大纲结构..."})

        response = api.chat(
            model=config.get('chat_model', 'gpt-4o'),
            messages=[{'role': 'user', 'content': outline_prompt}],
            max_tokens=16000,
            timeout=300
        )

        content = response.get('content', '')

        yield_sse({"status": "progress", "percent": 75, "message": "解析大纲结果..."})

        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{[\s\S]*"pages"[\s\S]*\}', content)
            json_str = json_match.group(0) if json_match else content

        data_resp = json.loads(json_str)
        pages = data_resp.get('pages', [])

        if isinstance(pages, list) and len(pages) > 0:
            cleaned = []
            for i, p in enumerate(pages):
                cleaned.append({
                    'index': i + 1,
                    'title': p.get('title', f'第{i+1}页'),
                    'type': p.get('type', 'content'),
                    'layout': p.get('layout', '满版图片-全屏背景'),
                    'brief': p.get('brief', ''),
                    'content': p.get('content', ''),
                })

            print(f"[INFO] AI 直接生成大纲: {len(cleaned)} 页")
            yield_sse({"status": "progress", "percent": 88, "message": f"大纲生成完成，共 {len(cleaned)} 页"})
            return {"pages": cleaned, "total_pages": len(cleaned), "title": data_resp.get('title', 'PPT大纲')}
        else:
            print(f"[WARN] AI 返回的大纲没有有效 pages: {content[:200]}")
            return {"pages": [], "total_pages": 0}

    except Exception as e:
        print(f"[ERROR] AI 大纲生成失败: {e}")
        return {"pages": [], "total_pages": 0}
