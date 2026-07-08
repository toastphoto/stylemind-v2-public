"""OpenAI兼容API客户端"""
from typing import Optional, Any
import base64
import httpx
from openai import OpenAI


class APIClient:
    """OpenAI兼容API客户端 - 支持多模型"""

    def __init__(self, base_url: str, api_key: str):
        """
        初始化API客户端

        Args:
            base_url: API基础URL，例如 https://api.openai.com/v1
            api_key: API密钥
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=httpx.Client(timeout=600.0)
        )

    def list_models(self) -> list[str]:
        """
        获取可用模型列表

        Returns:
            模型ID列表
        """
        try:
            # 尝试标准 OpenAI 格式
            response = self.client.models.list()
            models = [model.id for model in response.data]
            return sorted(models)
        except Exception as e:
            print(f"标准模型列表获取失败: {e}")
            # 尝试直接请求 /models 端点
            try:
                import httpx
                response = httpx.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data:
                        models = [m.get("id", m.get("object", "")) for m in data["data"]]
                        return sorted([m for m in models if m])
                    elif "models" in data:
                        return sorted(list(data["models"].keys()))
                else:
                    print(f"模型列表请求失败: {response.status_code}")
            except Exception as e2:
                print(f"备用模型列表获取也失败: {e2}")
            return []

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> dict[str, Any]:
        """
        对话接口

        Args:
            model: 模型ID
            messages: 消息列表 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大token数
            timeout: 超时时间（秒）
            **kwargs: 其他参数

        Returns:
            API响应
        """
        try:
            params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens:
                params["max_tokens"] = max_tokens
            if timeout:
                params["timeout"] = timeout
            params.update(kwargs)

            response = self.client.chat.completions.create(**params)
            return {
                "content": response.choices[0].message.content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "model": response.model,
            }
        except Exception as e:
            print(f"对话请求失败: {e}")
            raise

    def image_generate(
        self,
        model: str,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
        reference_image: Optional[str] = None,
        **kwargs
    ) -> dict[str, Any]:
        """
        图片生成接口

        Args:
            model: 图像生成模型
            prompt: 提示词
            size: 图片尺寸
            quality: 图片质量
            n: 生成数量
            reference_image: 参考图片（base64 data URL 或 URL）
            **kwargs: 其他参数（如 messages 多模态输入）

        Returns:
            生成结果
        """
        try:
            response_format = "url"

            # 如果有参考图片或 messages 参数，使用原生HTTP请求（SDK的images.generate不支持这些参数）
            has_ref_img = reference_image and (reference_image.startswith('data:image') or reference_image.startswith('http'))
            has_messages = 'messages' in kwargs

            if has_ref_img or has_messages:
                return self._image_generate_with_reference(
                    model=model, prompt=prompt, size=size, quality=quality, n=n,
                    reference_image=reference_image, **kwargs
                )

            # 标准模式：无参考图片，使用SDK
            params = {
                "model": model,
                "prompt": prompt,
                "n": n,
                "quality": quality,
            }

            if model.startswith("dall-e"):
                params["size"] = size
                params["response_format"] = response_format
            elif model.startswith("gpt-image"):
                params["size"] = size
            else:
                params["size"] = size

            params.update(kwargs)

            response = self.client.images.generate(**params)

            return self._parse_images_response(response)

        except Exception as e:
            print(f"图片生成失败: {e}")
            raise

    def _image_generate_with_reference(
        self,
        model: str,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
        reference_image: Optional[str] = None,
        **kwargs
    ) -> dict[str, Any]:
        """带参考图片的图片生成 — 使用 /v1/images/edits (multipart/form-data)"""

        # 提取所有参考图 URL
        ref_urls = []
        if 'messages' in kwargs:
            ref_urls = self._extract_image_urls_from_messages(kwargs['messages'])
            del kwargs['messages']
        elif reference_image and (reference_image.startswith('data:image') or reference_image.startswith('http')):
            ref_urls = [reference_image]

        # 如果没有参考图，回退到标准生成
        if not ref_urls:
            params = {
                'model': model, 'prompt': prompt, 'n': n,
                'quality': quality, 'size': size, 'response_format': 'url'
            }
            params.update(kwargs)
            response = self.client.images.generate(**params)
            return self._parse_images_response(response)

        # 有参考图 → 使用 /v1/images/edits (multipart/form-data)
        edits_url = f"{self.base_url.rstrip('/')}/images/edits"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        # 准备 multipart form data
        files_list = []
        data = {
            'model': model,
            'prompt': prompt,
            'size': size,
            'quality': quality,
            'response_format': 'b64_json',
        }

        # 传入其他额外参数（如 n）
        for k, v in kwargs.items():
            if k not in ('messages', 'reference_image'):
                data[k] = v

        # 添加参考图（OpenAI-compatible providers may support multiple images）
        for i, ref_url in enumerate(ref_urls):
            if ref_url.startswith('data:image'):
                header, b64_data = ref_url.split(',', 1)
                raw_bytes = base64.b64decode(b64_data)

                # 压缩过大的图片
                if len(raw_bytes) > 512 * 1024:
                    compressed = self._compress_base64_image(ref_url)
                    if compressed:
                        _, comp_b64 = compressed.split(',', 1)
                        raw_bytes = base64.b64decode(comp_b64)

                files_list.append(('image', (f'product_{i}.png', raw_bytes, 'image/png')))
            elif ref_url.startswith('http'):
                data.setdefault('image_urls', []).append(ref_url)

        print(f"[INFO] 使用 /v1/images/edits 接口，附带 {len(files_list)} 张产品参考图，图片总大小约 {sum(f[1][1].__len__() if hasattr(f[1][1], '__len__') else 0 for f in files_list) / 1024:.0f}KB")

        import httpx as _httpx
        _timeout = _httpx.Timeout(connect=30.0, read=600.0, write=120.0, pool=60.0)

        try:
            resp = _httpx.post(edits_url, headers=headers, data=data, files=files_list if files_list else None, timeout=_timeout)
        except (_httpx.ReadTimeout, _httpx.WriteTimeout, _httpx.ConnectTimeout, _httpx.TimeoutException) as _te:
            print(f"[WARN] edits 接口超时 ({type(_te).__name__})，回退到无参考图模式...")
            return self._fallback_generate_no_ref(model, prompt, size, quality, n, kwargs)

        # 错误时回退到无参考图的普通生成
        if resp.status_code >= 400:
            print(f"[WARN] edits 接口返回 {resp.status_code}: {resp.text[:200]}，回退到无参考图模式...")
            return self._fallback_generate_no_ref(model, prompt, size, quality, n, kwargs)

        data_resp = resp.json()

        images = []
        for img in data_resp.get('data', []):
            images.append({
                "url": img.get('url'),
                "b64_json": img.get('b64_json'),
                "revised_prompt": img.get('revised_prompt'),
            })

        return {"images": images, "model": model}

    def _fallback_generate_no_ref(self, model, prompt, size, quality, n, kwargs):
        """回退到无参考图的标准生成模式"""
        print(f"[INFO] 回退: 使用标准 images.generate（无产品参考图）")
        try:
            params = {'model': model, 'prompt': prompt, 'n': n, 'quality': quality, 'size': size, 'response_format': 'url'}
            params.update(kwargs)
            response = self.client.images.generate(**params)
            return self._parse_images_response(response)
        except Exception as fallback_err:
            print(f"[ERROR] 回退生成也失败: {fallback_err}")
            raise

    def _extract_image_urls_from_messages(self, messages: list) -> list:
        """从 messages 多模态格式中提取图片 URL"""
        urls = []
        for msg in messages:
            content = msg.get('content', [])
            if isinstance(content, str):
                continue
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'image_url':
                        img_url = part.get('image_url')
                        if isinstance(img_url, dict):
                            urls.append(img_url.get('url', ''))
                        elif isinstance(img_url, str):
                            urls.append(img_url)
        return [u for u in urls if u]

    def _compress_base64_image(self, data_url: str, max_size_kb: int = 512) -> Optional[str]:
        """压缩 base64 图片：超过 max_size_kb 时缩小到 1024px"""
        try:
            import io
            from PIL import Image

            if not data_url.startswith('data:image'):
                return None

            header, b64_data = data_url.split(',', 1)
            raw = base64.b64decode(b64_data)
            size_kb = len(raw) / 1024

            if size_kb <= max_size_kb:
                return data_url

            img = Image.open(io.BytesIO(raw))

            w, h = img.size
            max_dim = 1024
            if w > max_dim or h > max_dim:
                ratio = min(max_dim / w, max_dim / h)
                new_w, new_h = int(w * ratio), int(h * ratio)
                img = img.resize((new_w, new_h), Image.LANCZOS)

            buf = io.BytesIO()
            fmt = 'JPEG' if img.mode in ('RGB', 'L') else 'PNG'
            img.save(buf, format=fmt, quality=85, optimize=True)
            compressed_b64 = base64.b64encode(buf.getvalue()).decode()
            mime = 'image/jpeg' if fmt == 'JPEG' else 'image/png'

            result = f"data:{mime};base64,{compressed_b64}"
            new_size = len(compressed_b64) / 1024
            print(f"[INFO] 产品图已压缩: {size_kb:.0f}KB → {new_size:.0f}KB ({w}x{h} → {img.size[0]}x{img.size[1]})")
            return result
        except Exception as e:
            print(f"[WARN] 图片压缩失败，使用原图: {e}")
            return None

    def _parse_images_response(self, response):
        """统一解析 images.generate 的响应"""
        images = []
        for img in response.data:
            images.append({
                "url": img.url if hasattr(img, 'url') and img.url else None,
                "b64_json": img.b64_json if hasattr(img, 'b64_json') and img.b64_json else None,
                "revised_prompt": img.revised_prompt if hasattr(img, 'revised_prompt') else None,
            })
        return {"images": images, "model": response.model}

    def image_edit(
        self,
        model: str,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        mask_bytes: Optional[bytes] = None,
        image_b64: Optional[str] = None,
        mask_b64: Optional[str] = None,
        size: str = "1024x1024",
        n: int = 1,
        timeout_s: int = 90,
        **kwargs,
    ) -> dict[str, Any]:
        """
        图片编辑/修复（inpaint）接口。

        说明：
        - 由于不同 OpenAI 兼容聚合平台对 /images/edits 的入参格式不一致，本方法做两种尝试：
          1) JSON（image/mask 为 base64 或 data URL）
          2) multipart/form-data（OpenAI 风格）
        - 若两种都失败，会抛出 RuntimeError，供上层做“背景重绘”回退。
        """
        import base64 as _b64
        import httpx

        # 统一将 data URL 转为纯 base64（如果需要）
        def _strip_data_url(b64_or_data_url: str) -> str:
            if b64_or_data_url.startswith("data:"):
                return b64_or_data_url.split(",", 1)[1]
            return b64_or_data_url

        if image_b64:
            image_b64 = _strip_data_url(image_b64)
        if mask_b64:
            mask_b64 = _strip_data_url(mask_b64)

        if image_bytes is None and image_b64:
            image_bytes = _b64.b64decode(image_b64)
        if mask_bytes is None and mask_b64:
            mask_bytes = _b64.b64decode(mask_b64)

        if not image_bytes or not mask_bytes:
            raise ValueError("image_edit requires image+mask (bytes or base64)")

        endpoint = f"{self.base_url}/images/edits"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        # 1) JSON 尝试（部分聚合平台支持）
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "n": n,
                "size": size,
                "image": _b64.b64encode(image_bytes).decode("utf-8"),
                "mask": _b64.b64encode(mask_bytes).decode("utf-8"),
            }
            payload.update(kwargs)
            r = httpx.post(endpoint, headers=headers, json=payload, timeout=timeout_s)
            if r.status_code == 200:
                data = r.json()
                # 兼容 {data:[{b64_json/url}]} 或 {images:[...]}
                raw_images = data.get("data") or data.get("images") or []
                images = []
                for img in raw_images:
                    images.append(
                        {
                            "url": img.get("url") if isinstance(img, dict) else None,
                            "b64_json": img.get("b64_json") if isinstance(img, dict) else None,
                            "revised_prompt": img.get("revised_prompt") if isinstance(img, dict) else None,
                        }
                    )
                return {"images": images, "model": data.get("model", model)}
        except Exception as e:
            # JSON 路线失败继续走 multipart
            print(f"[WARN] image_edit json attempt failed: {e}")

        # 2) multipart 尝试（更接近 OpenAI 官方）
        try:
            files = {
                "image": ("image.png", image_bytes, "image/png"),
                "mask": ("mask.png", mask_bytes, "image/png"),
            }
            form = {
                "model": model,
                "prompt": prompt,
                "n": str(n),
                "size": size,
            }
            for k, v in kwargs.items():
                form[k] = str(v)
            r = httpx.post(endpoint, headers=headers, data=form, files=files, timeout=timeout_s)
            if r.status_code != 200:
                raise RuntimeError(f"image_edit failed: {r.status_code} {r.text[:200]}")
            data = r.json()
            raw_images = data.get("data") or data.get("images") or []
            images = []
            for img in raw_images:
                images.append(
                    {
                        "url": img.get("url") if isinstance(img, dict) else None,
                        "b64_json": img.get("b64_json") if isinstance(img, dict) else None,
                        "revised_prompt": img.get("revised_prompt") if isinstance(img, dict) else None,
                    }
                )
            return {"images": images, "model": data.get("model", model)}
        except Exception as e:
            raise RuntimeError(f"image_edit failed: {e}") from e

    def close(self):
        """关闭客户端"""
        if hasattr(self.client, "close"):
            self.client.close()
