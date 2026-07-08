"""排版规划器"""
from typing import Optional


class LayoutPlanner:
    """排版规划器 - 为每页设计详细排版"""

    LAYOUT_TEMPLATES = {
        "左右分栏": {
            "description": "左侧文字说明，右侧图片或图表",
            "structure": "vertical_line | [text_block(40%)] | [media_block(60%)]"
        },
        "上下结构": {
            "description": "上方标题+副标题，下方主要内容",
            "structure": "[title_bar] | [content_area]"
        },
        "卡片式": {
            "description": "多个卡片均匀分布，适合对比或列表",
            "structure": "[card] [card] [card] | [card] [card] [card]"
        },
        "全图背景": {
            "description": "整页图片作为背景，文字叠加在上面",
            "structure": "[background_image] + [overlay_text]"
        },
        "居中布局": {
            "description": "内容居中显示，适合标题页或引用",
            "structure": "[center_content]"
        },
        "三栏布局": {
            "description": "三个等宽栏位，适合多要点展示",
            "structure": "[col1(33%)] | [col2(33%)] | [col3(33%)]"
        },
        "左图右文": {
            "description": "左侧大图，右侧详细说明",
            "structure": "[image_block(50%)] | [text_block(50%)]"
        },
        "右图左文": {
            "description": "右侧大图，左侧详细说明",
            "structure": "[text_block(50%)] | [image_block(50%)]"
        },
    }

    def __init__(self):
        """初始化排版规划器"""
        self.default_layout = "左右分栏"

    def plan(self, pages: list[dict], style_guide: Optional[dict] = None) -> list[dict]:
        """
        为每页规划详细排版

        Args:
            pages: 页面列表
            style_guide: 风格指南

        Returns:
            带详细排版信息的页面列表
        """
        planned_pages = []

        for page in pages:
            layout = page.get("layout", self.default_layout)

            # 获取布局模板信息
            layout_info = self.LAYOUT_TEMPLATES.get(
                layout,
                self.LAYOUT_TEMPLATES[self.default_layout]
            )

            # 生成Image API提示词
            image_prompt = self.generate_image_prompt(page, style_guide)

            planned_page = {
                **page,
                "layout_info": layout_info,
                "image_prompt": image_prompt,
                "specifications": self._generate_specifications(page, layout_info),
            }

            planned_pages.append(planned_page)

        return planned_pages

    def generate_image_prompt(
        self,
        page: dict,
        style_guide: Optional[dict] = None,
        reference_image: Optional[str] = None
    ) -> str:
        """
        生成Image API提示词

        Args:
            page: 页面信息
            style_guide: 风格指南
            reference_image: 参考图片路径

        Returns:
            图像生成提示词
        """
        layout = page.get("layout", self.default_layout)
        title = page.get("title", "")
        content = page.get("content", "")
        style = page.get("style", "")

        # 构建提示词
        prompt_parts = []

        # 布局描述
        layout_descriptions = {
            "左右分栏": "Two-column layout: left side has text content, right side has visual elements. Clean, modern design.",
            "上下结构": "Top-bottom layout: header area with title, main content area below. Professional presentation style.",
            "卡片式": "Card-based layout: multiple cards arranged in grid. Each card with rounded corners, subtle shadows.",
            "全图背景": "Full-bleed background image with text overlay. Transparent text boxes over the image.",
            "居中布局": "Centered layout: content perfectly centered on slide. Minimalist, elegant design.",
            "三栏布局": "Three-column layout: equal width columns. Balanced, organized presentation.",
            "左图右文": "Left-right split: large image on left, text content on right. Visual storytelling.",
            "右图左文": "Left-right split: text content on left, large image on right. Clean composition.",
        }

        prompt_parts.append(layout_descriptions.get(layout, layout_descriptions["左右分栏"]))

        # 标题
        if title:
            prompt_parts.append(f"Title: {title}")

        # 内容要点
        if content:
            # 限制内容长度
            content_summary = content[:300] + "..." if len(content) > 300 else content
            prompt_parts.append(f"Content: {content_summary}")

        # 风格
        if style:
            prompt_parts.append(f"Style: {style}")

        # 添加技术规范
        prompt_parts.append("PPT slide dimensions: 16:9 aspect ratio. High quality, professional design. White or light background.")

        # 如果有参考图片
        if reference_image:
            prompt_parts.append("Style reference: follow the design aesthetic of the reference image.")

        # 如果有风格指南
        if style_guide:
            if style_guide.get("color_scheme"):
                prompt_parts.append(f"Color scheme: {style_guide['color_scheme']}")
            if style_guide.get("font_style"):
                prompt_parts.append(f"Typography: {style_guide['font_style']}")

        return " | ".join(prompt_parts)

    def _generate_specifications(self, page: dict, layout_info: dict) -> dict:
        """
        生成详细规格说明

        Args:
            page: 页面信息
            layout_info: 布局信息

        Returns:
            详细规格
        """
        return {
            "layout_type": page.get("layout", self.default_layout),
            "structure": layout_info.get("structure", ""),
            "recommended_font_sizes": {
                "title": "36-48pt",
                "subtitle": "24-32pt",
                "body": "18-24pt",
                "caption": "12-16pt"
            },
            "color_recommendations": [
                "Primary: #2563EB (Blue)",
                "Secondary: #64748B (Slate)",
                "Accent: #10B981 (Emerald)",
                "Background: #FFFFFF or #F8FAFC"
            ]
        }

    def suggest_layout(self, page_type: str) -> str:
        """
        根据页面类型建议布局

        Args:
            page_type: 页面类型（title, content, summary, toc等）

        Returns:
            建议的布局类型
        """
        suggestions = {
            "title": "全图背景",
            "toc": "卡片式",
            "content": "左右分栏",
            "summary": "居中布局",
            "section": "上下结构",
        }

        return suggestions.get(page_type, self.default_layout)

    def get_available_layouts(self) -> list[dict]:
        """
        获取所有可用的布局

        Returns:
            布局列表
        """
        return [
            {
                "name": name,
                "description": info["description"],
                "structure": info["structure"]
            }
            for name, info in self.LAYOUT_TEMPLATES.items()
        ]
