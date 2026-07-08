"""Image API生成PNG"""
import os
import base64
from typing import Optional
from pathlib import Path
from PIL import Image
import io
from .api_client import APIClient


class ImageGenerator:
    """Image API生成PNG"""

    def __init__(self, api_client: APIClient, output_dir: str = "outputs"):
        """
        初始化图片生成器

        Args:
            api_client: API客户端
            output_dir: 输出目录
        """
        self.api_client = api_client
        self.output_dir = output_dir
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

    def generate(
        self,
        prompt: str,
        model: str = "gpt-image-1",
        size: str = "1792x1024",
        quality: str = "standard",
        reference_image: Optional[str] = None
    ) -> str:
        """
        生成PPT图片

        Args:
            prompt: Image API提示词
            model: 图像生成模型
            size: 图片尺寸（默认16:9比例）
            quality: 图片质量
            reference_image: 可选的风格参考图路径

        Returns:
            生成的图片路径

        Raises:
            Exception: 生成失败时抛出异常
        """
        try:
            # 调用API生成图片
            response = self.api_client.image_generate(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
                reference_image=reference_image
            )

            if not response.get("images"):
                raise Exception("未收到图片数据")

            image_data = response["images"][0]

            # 生成文件名
            timestamp = self._generate_timestamp()
            filename = f"slide_{timestamp}.png"
            filepath = os.path.join(self.output_dir, filename)

            # 保存图片
            if image_data.get("b64_json"):
                # Base64格式
                image_bytes = base64.b64decode(image_data["b64_json"])
                self._save_image(image_bytes, filepath)
            elif image_data.get("url"):
                # URL格式，需要下载
                self._download_image(image_data["url"], filepath)
            else:
                raise Exception("图片数据格式不支持")

            return filepath

        except Exception as e:
            raise Exception(f"图片生成失败: {str(e)}")

    def generate_batch(
        self,
        prompts: list[str],
        model: str = "gpt-image-1",
        size: str = "1792x1024",
        quality: str = "standard",
        reference_image: Optional[str] = None
    ) -> list[str]:
        """
        批量生成图片

        Args:
            prompts: 提示词列表
            model: 图像生成模型
            size: 图片尺寸
            quality: 图片质量
            reference_image: 参考图片

        Returns:
            生成的图片路径列表
        """
        results = []

        for i, prompt in enumerate(prompts):
            try:
                # 为每个prompt添加页码
                enhanced_prompt = f"Slide {i+1}. {prompt}"

                filepath = self.generate(
                    prompt=enhanced_prompt,
                    model=model,
                    size=size,
                    quality=quality,
                    reference_image=reference_image
                )

                results.append(filepath)
                print(f"第{i+1}页生成完成: {filepath}")

            except Exception as e:
                print(f"第{i+1}页生成失败: {e}")
                results.append(None)

        return results

    def _save_image(self, image_bytes: bytes, filepath: str):
        """
        保存图片字节到文件

        Args:
            image_bytes: 图片字节数据
            filepath: 保存路径
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))

            # 转换为RGB（如果需要）
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")

            image.save(filepath, "PNG", quality=95)

        except Exception as e:
            raise Exception(f"保存图片失败: {str(e)}")

    def _download_image(self, url: str, filepath: str):
        """
        从URL下载图片

        Args:
            url: 图片URL
            filepath: 保存路径
        """
        try:
            import httpx

            with httpx.Client(timeout=60.0) as client:
                response = client.get(url)
                response.raise_for_status()

                self._save_image(response.content, filepath)

        except Exception as e:
            raise Exception(f"下载图片失败: {str(e)}")

    def _generate_timestamp(self) -> str:
        """
        生成时间戳

        Returns:
            时间戳字符串
        """
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    def validate_image(self, image_path: str) -> bool:
        """
        验证图片是否有效

        Args:
            image_path: 图片路径

        Returns:
            是否有效
        """
        try:
            if not os.path.exists(image_path):
                return False

            image = Image.open(image_path)
            image.verify()

            return True
        except:
            return False

    def resize_image(
        self,
        image_path: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        keep_aspect: bool = True
    ) -> str:
        """
        调整图片大小

        Args:
            image_path: 图片路径
            width: 目标宽度
            height: 目标高度
            keep_aspect: 是否保持宽高比

        Returns:
            调整后的图片路径
        """
        try:
            image = Image.open(image_path)

            if keep_aspect:
                image.thumbnail((width or image.width, height or image.height), Image.Resampling.LANCZOS)
            else:
                image = image.resize((width, height), Image.Resampling.LANCZOS)

            # 保存到新文件
            base, ext = os.path.splitext(image_path)
            new_path = f"{base}_resized.png"
            image.save(new_path, "PNG")

            return new_path

        except Exception as e:
            raise Exception(f"调整图片大小失败: {str(e)}")
