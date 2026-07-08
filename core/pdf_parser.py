"""PDF 深度解析模块 - 提取文字、排版结构、图片位置、字体层级"""
import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    """文本块 - 带坐标和字体信息"""
    text: str
    x0: float = 0
    y0: float = 0
    x1: float = 0
    y1: float = 0
    font_size: float = 12
    font_name: str = ""
    is_bold: bool = False
    text_type: str = "body"  # title, subtitle, heading, body, caption, footnote

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "x0": round(self.x0, 1),
            "y0": round(self.y0, 1),
            "x1": round(self.x1, 1),
            "y1": round(self.y1, 1),
            "font_size": round(self.font_size, 1),
            "font_name": self.font_name,
            "is_bold": self.is_bold,
            "text_type": self.text_type,
        }


@dataclass
class ImageInfo:
    """图片信息"""
    x0: float = 0
    y0: float = 0
    width: float = 0
    height: float = 0
    position: str = ""  # top, bottom, left, right, center, background

    def to_dict(self) -> dict:
        return {
            "x0": round(self.x0, 1),
            "y0": round(self.y0, 1),
            "width": round(self.width, 1),
            "height": round(self.height, 1),
            "position": self.position,
        }


@dataclass
class LayoutInfo:
    """排版信息"""
    layout_type: str = "content"  # cover, toc, content, split, data, quote, summary
    columns: int = 1  # 分栏数
    has_header: bool = False  # 是否有页眉
    has_footer: bool = False  # 是否有页脚
    has_sidebar: bool = False  # 是否有侧边栏
    text_alignment: str = "left"  # left, center, right, justify
    reading_order: str = "top-bottom"  # top-bottom, left-right, z-pattern
    content_density: str = "normal"  # sparse, normal, dense
    title_hierarchy: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "layout_type": self.layout_type,
            "columns": self.columns,
            "has_header": self.has_header,
            "has_footer": self.has_footer,
            "has_sidebar": self.has_sidebar,
            "text_alignment": self.text_alignment,
            "reading_order": self.reading_order,
            "content_density": self.content_density,
            "title_hierarchy": self.title_hierarchy,
        }


@dataclass
class PDFPage:
    """PDF 页面深度内容"""
    page_index: int
    title: str = ""
    content: str = ""
    text_blocks: List[TextBlock] = field(default_factory=list)
    images: List[ImageInfo] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    layout: LayoutInfo = field(default_factory=LayoutInfo)
    page_width: float = 0
    page_height: float = 0

    def to_dict(self) -> dict:
        return {
            "page_index": self.page_index,
            "title": self.title,
            "content": self.content,
            "text_blocks": [b.to_dict() for b in self.text_blocks],
            "images": [i.to_dict() for i in self.images],
            "tables": self.tables,
            "layout": self.layout.to_dict(),
            "page_width": self.page_width,
            "page_height": self.page_height,
        }

    def get_layout_summary(self) -> str:
        """获取排版摘要（用于LLM分析）"""
        layout = self.layout
        summary = f"页面 {self.page_index + 1}:\n"
        summary += f"  标题: {self.title}\n"
        summary += f"  布局类型: {layout.layout_type}\n"
        summary += f"  分栏数: {layout.columns}\n"
        summary += f"  文本对齐: {layout.text_alignment}\n"
        summary += f"  内容密度: {layout.content_density}\n"
        summary += f"  图片数: {len(self.images)}\n"
        summary += f"  表格数: {len(self.tables)}\n"

        if layout.title_hierarchy:
            summary += "  标题层级:\n"
            for h in layout.title_hierarchy:
                summary += f"    - {h['type']}: {h['text'][:50]} (字号:{h['font_size']})\n"

        return summary


class PDFParser:
    """PDF 深度解析器"""

    def __init__(self):
        self.supported_extensions = [".pdf"]

    def parse(self, file_path: str) -> tuple[List[PDFPage], Dict[str, Any]]:
        """解析 PDF 文件（深度模式）"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 优先使用 pymupdf（深度解析）
        try:
            return self._parse_deep_with_pymupdf(file_path)
        except ImportError:
            pass

        # 备用：使用 pdfplumber
        try:
            return self._parse_deep_with_pdfplumber(file_path)
        except ImportError:
            pass

        # 最后：PyPDF2（基础模式）
        try:
            return self._parse_basic_with_pypdf2(file_path)
        except ImportError:
            raise ImportError("请安装 PDF 解析库: pip install pymupdf 或 pdfplumber")

    def _parse_deep_with_pymupdf(self, file_path: str) -> tuple[List[PDFPage], Dict[str, Any]]:
        """使用 pymupdf 深度解析"""
        import fitz

        doc = fitz.open(file_path)
        pages = []
        metadata = {
            "filename": os.path.basename(file_path),
            "page_count": len(doc),
            "parser": "pymupdf-deep",
            "mode": "deep",
        }

        for i, page in enumerate(doc):
            page_width = page.rect.width
            page_height = page.rect.height

            # 1. 提取文本块（带字体信息）
            text_blocks = []
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

            for block in blocks:
                if block["type"] != 0:  # 只处理文本块
                    continue

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue

                        block_info = TextBlock(
                            text=text,
                            x0=span["bbox"][0],
                            y0=span["bbox"][1],
                            x1=span["bbox"][2],
                            y1=span["bbox"][3],
                            font_size=span.get("size", 12),
                            font_name=span.get("font", ""),
                            is_bold="bold" in span.get("font", "").lower() or "black" in span.get("font", "").lower(),
                        )
                        text_blocks.append(block_info)

            # 2. 提取图片信息
            images = []
            img_list = page.get_images(full=True)
            for img_info in img_list:
                # 获取图片在页面上的位置
                for img_rect in page.get_image_rects(img_info[0]):
                    img = ImageInfo(
                        x0=img_rect.x0,
                        y0=img_rect.y0,
                        width=img_rect.width,
                        height=img_rect.height,
                    )
                    img.position = self._infer_image_position(img, page_width, page_height)
                    images.append(img)

            # 3. 提取表格
            tables = self._extract_tables_pymupdf(page)

            # 4. 分析排版结构
            layout = self._analyze_layout(text_blocks, images, tables, page_width, page_height)

            # 5. 提取标题和内容
            title = self._extract_title(text_blocks)
            content = self._extract_content(text_blocks)

            # 6. 识别标题层级
            layout.title_hierarchy = self._analyze_title_hierarchy(text_blocks)

            pdf_page = PDFPage(
                page_index=i,
                title=title,
                content=content,
                text_blocks=text_blocks,
                images=images,
                tables=tables,
                layout=layout,
                page_width=page_width,
                page_height=page_height,
            )
            pages.append(pdf_page)

        doc.close()
        return pages, metadata

    def _parse_deep_with_pdfplumber(self, file_path: str) -> tuple[List[PDFPage], Dict[str, Any]]:
        """使用 pdfplumber 深度解析"""
        import pdfplumber

        pages = []
        metadata = {
            "filename": os.path.basename(file_path),
            "page_count": 0,
            "parser": "pdfplumber-deep",
            "mode": "deep",
        }

        with pdfplumber.open(file_path) as pdf:
            metadata["page_count"] = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                page_width = page.width
                page_height = page.height

                # 提取文本块
                text_blocks = []
                chars = page.chars or []
                lines = self._group_chars_to_lines(chars)
                for line in lines:
                    block = TextBlock(
                        text=line["text"],
                        x0=line["x0"],
                        y0=line["y0"],
                        x1=line["x1"],
                        y1=line["y1"],
                        font_size=line.get("size", 12),
                        font_name=line.get("fontname", ""),
                        is_bold="bold" in line.get("fontname", "").lower(),
                    )
                    text_blocks.append(block)

                # 提取图片
                images = []
                for img in (page.images or [])[:10]:
                    img_info = ImageInfo(
                        x0=img.get("x0", 0),
                        y0=img.get("top", 0),
                        width=img.get("width", 0),
                        height=img.get("height", 0),
                    )
                    img_info.position = self._infer_image_position(img_info, page_width, page_height)
                    images.append(img_info)

                # 提取表格
                tables = []
                for table in (page.extract_tables() or []):
                    tables.append({
                        "rows": len(table),
                        "cols": len(table[0]) if table else 0,
                        "data": table[:3],
                    })

                # 分析排版
                layout = self._analyze_layout(text_blocks, images, tables, page_width, page_height)
                layout.title_hierarchy = self._analyze_title_hierarchy(text_blocks)

                title = self._extract_title(text_blocks)
                content = self._extract_content(text_blocks)

                pdf_page = PDFPage(
                    page_index=i,
                    title=title,
                    content=content,
                    text_blocks=text_blocks,
                    images=images,
                    tables=tables,
                    layout=layout,
                    page_width=page_width,
                    page_height=page_height,
                )
                pages.append(pdf_page)

        return pages, metadata

    def _parse_basic_with_pypdf2(self, file_path: str) -> tuple[List[PDFPage], Dict[str, Any]]:
        """使用 PyPDF2 基础解析（无排版信息）"""
        from PyPDF2 import PdfReader

        reader = PdfReader(file_path)
        pages = []
        metadata = {
            "filename": os.path.basename(file_path),
            "page_count": len(reader.pages),
            "parser": "PyPDF2-basic",
            "mode": "basic",
        }

        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            lines = text.split("\n")
            title = lines[0].strip() if lines else f"第{i+1}页"

            pdf_page = PDFPage(
                page_index=i,
                title=title[:100],
                content=text,
            )
            pages.append(pdf_page)

        return pages, metadata

    def _analyze_layout(
        self,
        text_blocks: List[TextBlock],
        images: List[ImageInfo],
        tables: List[Dict],
        page_width: float,
        page_height: float,
    ) -> LayoutInfo:
        """分析排版结构"""
        layout = LayoutInfo()

        if not text_blocks:
            return layout

        # 1. 判断布局类型
        layout.layout_type = self._infer_layout_type(text_blocks, images, tables)

        # 2. 判断分栏数
        layout.columns = self._detect_columns(text_blocks, page_width)

        # 3. 判断文本对齐
        layout.text_alignment = self._detect_alignment(text_blocks, page_width)

        # 4. 判断内容密度
        text_area = sum((b.y1 - b.y0) * (b.x1 - b.x0) for b in text_blocks)
        page_area = page_width * page_height
        density_ratio = text_area / page_area if page_area > 0 else 0

        if density_ratio < 0.2:
            layout.content_density = "sparse"
        elif density_ratio < 0.5:
            layout.content_density = "normal"
        else:
            layout.content_density = "dense"

        # 5. 判断页眉页脚
        layout.has_header = self._detect_header_footer(text_blocks, page_height, "header")
        layout.has_footer = self._detect_header_footer(text_blocks, page_height, "footer")

        # 6. 判断阅读顺序
        if layout.columns > 1:
            layout.reading_order = "left-right"
        elif layout.layout_type == "data":
            layout.reading_order = "z-pattern"
        else:
            layout.reading_order = "top-bottom"

        return layout

    def _infer_layout_type(
        self,
        text_blocks: List[TextBlock],
        images: List[ImageInfo],
        tables: List[Dict],
    ) -> str:
        """推断布局类型"""
        if not text_blocks and not images:
            return "cover"

        # 封面页：文字少、有大标题
        if len(text_blocks) <= 3 and any(b.font_size > 20 for b in text_blocks):
            return "cover"

        # 目录页
        content_text = " ".join(b.text for b in text_blocks).lower()
        if any(kw in content_text for kw in ["目录", "contents", "目 录", "table of contents"]):
            return "toc"

        # 数据页
        if tables:
            return "data"

        # 图文混排
        if images and text_blocks:
            return "split"

        # 总结页
        if any(kw in content_text for kw in ["总结", "summary", "谢谢", "thank", "感谢"]):
            return "summary"

        # 引用页
        if any(kw in content_text for kw in ["参考", "reference", "引用"]):
            return "quote"

        return "content"

    def _detect_columns(self, text_blocks: List[TextBlock], page_width: float) -> int:
        """检测分栏数"""
        if not text_blocks or page_width == 0:
            return 1

        # 找到所有文本块的X坐标中点
        midpoints = [(b.x0 + b.x1) / 2 for b in text_blocks if b.text.strip()]

        if len(midpoints) < 5:
            return 1

        # 用直方图检测分栏
        from collections import Counter
        bins = [int(m / (page_width / 4)) for m in midpoints]
        counter = Counter(bins)

        # 如果文本集中在2个以上不同区域，说明有分栏
        distinct_regions = sum(1 for count in counter.values() if count > len(midpoints) * 0.15)

        if distinct_regions >= 3:
            return 3
        elif distinct_regions >= 2:
            return 2

        return 1

    def _detect_alignment(self, text_blocks: List[TextBlock], page_width: float) -> str:
        """检测文本对齐方式"""
        if not text_blocks or page_width == 0:
            return "left"

        # 只分析正文（非标题）
        body_blocks = [b for b in text_blocks if b.text_type == "body" and len(b.text) > 10]
        if not body_blocks:
            body_blocks = text_blocks

        # 计算左边距的一致性
        left_margins = [b.x0 for b in body_blocks]
        avg_left = sum(left_margins) / len(left_margins)
        left_variance = sum((m - avg_left) ** 2 for m in left_margins) / len(left_margins)

        # 计算右边距的一致性
        right_margins = [page_width - b.x1 for b in body_blocks]
        avg_right = sum(right_margins) / len(right_margins)
        right_variance = sum((m - avg_right) ** 2 for m in right_margins) / len(right_margins)

        if left_variance < 100 and right_variance < 100:
            return "justify"
        elif right_variance < 100:
            return "right"
        elif left_variance < 100:
            return "left"
        else:
            # 检查是否居中
            centers = [(b.x0 + b.x1) / 2 for b in body_blocks]
            avg_center = sum(centers) / len(centers)
            if abs(avg_center - page_width / 2) < page_width * 0.1:
                return "center"

        return "left"

    def _detect_header_footer(self, text_blocks: List[TextBlock], page_height: float, position: str) -> bool:
        """检测页眉或页脚"""
        if not text_blocks:
            return False

        threshold = page_height * 0.05  # 顶部/底部5%区域

        if position == "header":
            header_blocks = [b for b in text_blocks if b.y0 < threshold]
        else:
            header_blocks = [b for b in text_blocks if b.y1 > page_height - threshold]

        return len(header_blocks) > 0

    def _infer_image_position(self, img: ImageInfo, page_width: float, page_height: float) -> str:
        """推断图片位置"""
        if page_width == 0 or page_height == 0:
            return "center"

        cx = img.x0 + img.width / 2
        cy = img.y0 + img.height / 2

        # 图片面积占比
        img_area = img.width * img.height
        page_area = page_width * page_height
        if img_area > page_area * 0.5:
            return "background"

        # 位置判断
        if cy < page_height * 0.3:
            return "top"
        elif cy > page_height * 0.7:
            return "bottom"
        elif cx < page_width * 0.3:
            return "left"
        elif cx > page_width * 0.7:
            return "right"
        else:
            return "center"

    def _extract_title(self, text_blocks: List[TextBlock]) -> str:
        """提取页面标题"""
        if not text_blocks:
            return "未命名页面"

        # 找字号最大的文本块
        max_block = max(text_blocks, key=lambda b: b.font_size)
        if max_block.font_size >= 14 and max_block.text.strip():
            return max_block.text.strip()[:100]

        # 取第一个非空文本
        for block in text_blocks:
            if block.text.strip() and len(block.text.strip()) > 2:
                return block.text.strip()[:100]

        return "未命名页面"

    def _extract_content(self, text_blocks: List[TextBlock]) -> str:
        """提取纯文本内容"""
        return "\n".join(b.text for b in text_blocks if b.text.strip())

    def _analyze_title_hierarchy(self, text_blocks: List[TextBlock]) -> List[Dict[str, Any]]:
        """分析标题层级"""
        if not text_blocks:
            return []

        # 统计字号分布
        font_sizes = [b.font_size for b in text_blocks if b.text.strip()]
        if not font_sizes:
            return []

        # 找到正文基准字号（出现最多的）
        from collections import Counter
        size_counter = Counter(round(s) for s in font_sizes)
        body_size = size_counter.most_common(1)[0][0] if size_counter else 12

        hierarchy = []
        seen_texts = set()

        for block in text_blocks:
            text = block.text.strip()
            if not text or text in seen_texts:
                continue
            if len(text) < 2:
                continue

            seen_texts.add(text)

            # 根据字号判断层级
            ratio = block.font_size / body_size if body_size > 0 else 1

            if ratio >= 2.0:
                text_type = "title"
            elif ratio >= 1.5:
                text_type = "subtitle"
            elif ratio >= 1.2:
                text_type = "heading"
            elif block.is_bold:
                text_type = "heading"
            else:
                text_type = "body"

            if text_type in ("title", "subtitle", "heading"):
                hierarchy.append({
                    "type": text_type,
                    "text": text[:80],
                    "font_size": block.font_size,
                    "is_bold": block.is_bold,
                })
                block.text_type = text_type
            else:
                block.text_type = "body"

        return hierarchy[:10]  # 最多返回10个标题

    def _extract_tables_pymupdf(self, page) -> List[Dict]:
        """使用 pymupdf 提取表格"""
        tables = []
        try:
            # pymupdf 没有内置表格提取，用简单方法检测
            # 检查是否有网格线
            drawings = page.get_drawings()
            if drawings:
                # 如果有很多水平线和垂直线，可能有表格
                h_lines = sum(1 for d in drawings if self._is_horizontal_line(d))
                v_lines = sum(1 for d in drawings if self._is_vertical_line(d))

                if h_lines > 2 and v_lines > 2:
                    tables.append({
                        "rows": "检测到表格结构",
                        "cols": f"水平线:{h_lines}, 垂直线:{v_lines}",
                        "data": [],
                    })
        except Exception:
            pass

        return tables

    def _is_horizontal_line(self, drawing: Dict) -> bool:
        """判断是否是水平线"""
        try:
            rect = drawing.get("rect", None)
            if rect:
                return rect.height < 2 and rect.width > 50
        except Exception:
            pass
        return False

    def _is_vertical_line(self, drawing: Dict) -> bool:
        """判断是否是垂直线"""
        try:
            rect = drawing.get("rect", None)
            if rect:
                return rect.width < 2 and rect.height > 50
        except Exception:
            pass
        return False

    def _group_chars_to_lines(self, chars: List[Dict]) -> List[Dict]:
        """将字符分组为行"""
        if not chars:
            return []

        lines = []
        current_line = {
            "text": "",
            "x0": float("inf"),
            "y0": float("inf"),
            "x1": 0,
            "y1": 0,
            "size": 12,
            "fontname": "",
        }

        prev_y = None
        tolerance = 3

        for char in chars:
            y = char.get("top", char.get("y0", 0))

            if prev_y is not None and abs(y - prev_y) > tolerance:
                if current_line["text"]:
                    lines.append(current_line)
                current_line = {
                    "text": char.get("text", ""),
                    "x0": char.get("x0", 0),
                    "y0": y,
                    "x1": char.get("x1", 0),
                    "y1": char.get("bottom", char.get("y1", y + 12)),
                    "size": char.get("size", 12),
                    "fontname": char.get("fontname", ""),
                }
            else:
                current_line["text"] += char.get("text", "")
                current_line["x0"] = min(current_line["x0"], char.get("x0", 0))
                current_line["y0"] = min(current_line["y0"], y)
                current_line["x1"] = max(current_line["x1"], char.get("x1", 0))
                current_line["y1"] = max(current_line["y1"], char.get("bottom", char.get("y1", y + 12)))
                current_line["size"] = char.get("size", 12)

            prev_y = y

        if current_line["text"]:
            lines.append(current_line)

        return lines


# 便捷函数
def parse_pdf(file_path: str) -> tuple[List[PDFPage], Dict[str, Any]]:
    """解析 PDF 文件"""
    parser = PDFParser()
    return parser.parse(file_path)
