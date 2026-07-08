"""PDF 拆分模块 - 自动拆分大文件"""
import os
import tempfile
from typing import List, Tuple
from pathlib import Path

# 强制设置临时目录到 /run
os.environ['TMPDIR'] = '/run'
os.environ['TEMP'] = '/run'
os.environ['TMP'] = '/run'
tempfile.tempdir = '/run'


class PDFSplitter:
    """PDF 拆分器"""

    def __init__(self, max_size_mb: int = 40, max_pages: int = 50):
        """
        初始化拆分器

        Args:
            max_size_mb: 单个文件最大大小（MB）
            max_pages: 单个文件最大页数
        """
        self.max_size = max_size_mb * 1024 * 1024
        self.max_pages = max_pages

    def split_if_needed(self, file_path: str) -> List[str]:
        """
        如果需要则拆分 PDF

        Args:
            file_path: 原始 PDF 路径

        Returns:
            拆分后的文件路径列表（如果不需要拆分则返回原文件）
        """
        file_size = os.path.getsize(file_path)

        # 获取页数
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            total_pages = len(reader.pages)
        except Exception:
            # 如果无法读取，假设需要拆分
            total_pages = 999

        # 检查是否需要拆分
        need_split = False
        reason = []

        if file_size > self.max_size:
            need_split = True
            reason.append(f"文件大小 {file_size/1024/1024:.1f}MB 超过限制 {self.max_size/1024/1024:.0f}MB")

        if total_pages > self.max_pages:
            need_split = True
            reason.append(f"页数 {total_pages} 超过限制 {self.max_pages}")

        if not need_split:
            return [file_path]

        # 执行拆分
        return self._split_pdf(file_path, total_pages)

    def _split_pdf(self, file_path: str, total_pages: int) -> List[str]:
        """
        拆分 PDF 文件

        Args:
            file_path: 原始 PDF 路径
            total_pages: 总页数

        Returns:
            拆分后的文件路径列表
        """
        from PyPDF2 import PdfReader, PdfWriter

        reader = PdfReader(file_path)
        output_files = []

        # 计算需要分成几份
        num_parts = max(
            (total_pages + self.max_pages - 1) // self.max_pages,  # 按页数计算
            2  # 至少分成2份
        )

        pages_per_part = (total_pages + num_parts - 1) // num_parts

        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="pdf_split_")
        base_name = Path(file_path).stem

        for part_idx in range(num_parts):
            writer = PdfWriter()

            start_page = part_idx * pages_per_part
            end_page = min((part_idx + 1) * pages_per_part, total_pages)

            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])

            # 保存拆分后的文件
            output_path = os.path.join(temp_dir, f"{base_name}_part{part_idx+1}.pdf")
            with open(output_path, "wb") as output_file:
                writer.write(output_file)

            output_files.append(output_path)

        return output_files

    def get_split_info(self, original_path: str, split_files: List[str]) -> dict:
        """
        获取拆分信息

        Args:
            original_path: 原始文件路径
            split_files: 拆分后的文件路径列表

        Returns:
            拆分信息字典
        """
        original_size = os.path.getsize(original_path)
        split_sizes = [os.path.getsize(f) for f in split_files]

        return {
            "original_file": os.path.basename(original_path),
            "original_size_mb": round(original_size / 1024 / 1024, 2),
            "split_count": len(split_files),
            "split_files": [os.path.basename(f) for f in split_files],
            "split_sizes_mb": [round(s / 1024 / 1024, 2) for s in split_sizes],
            "temp_dir": os.path.dirname(split_files[0]) if split_files else None,
        }


# 便捷函数
def split_large_pdf(file_path: str, max_size_mb: int = 40, max_pages: int = 50) -> Tuple[List[str], dict]:
    """
    拆分大 PDF 文件

    Args:
        file_path: PDF 文件路径
        max_size_mb: 单个文件最大大小（MB）
        max_pages: 单个文件最大页数

    Returns:
        (拆分后的文件路径列表, 拆分信息)
    """
    splitter = PDFSplitter(max_size_mb=max_size_mb, max_pages=max_pages)
    split_files = splitter.split_if_needed(file_path)

    if len(split_files) > 1:
        info = splitter.get_split_info(file_path, split_files)
    else:
        info = {
            "original_file": os.path.basename(file_path),
            "original_size_mb": round(os.path.getsize(file_path) / 1024 / 1024, 2),
            "split_count": 1,
            "message": "文件大小符合要求，无需拆分",
        }

    return split_files, info
