from __future__ import annotations

import os
import time
import uuid
from typing import Optional


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_bytes(dir_path: str, data: bytes, ext: str, prefix: str = "asset") -> str:
    """保存 bytes 并返回文件名（不含目录）。"""
    ensure_dir(dir_path)
    fname = f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:10]}.{ext.lstrip('.')}"
    fpath = os.path.join(dir_path, fname)
    with open(fpath, "wb") as f:
        f.write(data)
    return fname


def url_for_generated(fname: str) -> str:
    return f"/api/generated/{fname}"
