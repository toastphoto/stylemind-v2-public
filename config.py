"""配置管理"""
import json
import os
from pathlib import Path


# ============================================================
# 预定义模型列表（可按你的 OpenAI-compatible API provider 调整）
# ============================================================

# 对话/思考模型
CHAT_MODELS = [
    # GPT 系列
    "chatgpt-4o-latest",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.5-preview",
    "o3",
    "o3-mini",
    "o4-mini",
    # Claude 系列
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    # DeepSeek 系列
    "deepseek-chat",
    "deepseek-reasoner",
    # Gemini 系列
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    # Grok 系列
    "grok-3",
    "grok-3-mini",
    # Qwen 系列
    "qwen-max",
    "qwen-plus",
]

# 图片生成模型
IMAGE_MODELS = [
    # GPT Image 系列（核心）
    "gpt-image-1",           # GPT Image 1（主力）
    "gpt-image-2",           # GPT Image 2（最新）
    "gpt-image-2-preview",   # GPT Image 2 预览版
    "gpt-4o-image",          # GPT-4o 图生图
    "gpt-4o-image-vip",      # GPT-4o 图生图 VIP
    # Sora Image
    "sora_image",
    "sora_image-vip",
    # DALL-E
    "dall-e-3",
    "dall-e-2",
    # Flux 系列
    "flux-kontext-max",
    "flux-kontext-pro",
    "flux-kontext-dev",
    # 其他
    "recraftv3",
    "recraftv3-halloween",
    "qwen-image",
    "qwen-image-edit",
    "nano-banana",            # Gemini优化版
    "nano-banana-hd",         # 4K高清版
    "doubao-seedream-4-0-250828",  # 豆包即梦4
]

# 嵌入模型（用于 RAG）
EMBEDDING_MODELS = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
]


class Config:
    """配置管理类"""

    def __init__(self, config_file: str = "config.json"):
        """
        初始化配置

        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = {
            "api_base_url": "",
            "api_key": "",
            "theme": "default",
            "output_dir": "outputs",
            "db_path": "stylemind.db",
            "vector_store_path": "vector_store.json",
            "conversation_dir": "conversations",
        }
        self.load()

    def load(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
            except Exception as e:
                print(f"加载配置文件失败: {e}")

    def save(self):
        """保存配置"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置文件失败: {e}")

    def get(self, key: str, default: any = None) -> any:
        """
        获取配置

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        return self.config.get(key, default)

    def set(self, key: str, value: any):
        """
        设置配置

        Args:
            key: 配置键
            value: 配置值
        """
        self.config[key] = value
        self.save()

    def get_api_base_url(self) -> str:
        """
        获取API基础URL

        Returns:
            API基础URL
        """
        return self.config.get("api_base_url", "")

    def get_api_key(self) -> str:
        """
        获取API密钥

        Returns:
            API密钥
        """
        return self.config.get("api_key", "")

    def set_api(self, base_url: str, api_key: str):
        """
        设置API配置

        Args:
            base_url: API基础URL
            api_key: API密钥
        """
        self.config["api_base_url"] = base_url
        self.config["api_key"] = api_key
        self.save()

    def get_output_dir(self) -> str:
        """
        获取输出目录

        Returns:
            输出目录路径
        """
        return self.config.get("output_dir", "outputs")

    def get_db_path(self) -> str:
        """
        获取数据库路径

        Returns:
            数据库路径
        """
        return self.config.get("db_path", "stylemind.db")

    def get_vector_store_path(self) -> str:
        """
        获取向量存储路径

        Returns:
            向量存储路径
        """
        return self.config.get("vector_store_path", "vector_store.json")

    def get_conversation_dir(self) -> str:
        """
        获取对话存储目录

        Returns:
            对话存储目录
        """
        return self.config.get("conversation_dir", "conversations")

    def reset(self):
        """重置配置为默认值"""
        self.config = {
            "api_base_url": "",
            "api_key": "",
            "theme": "default",
            "output_dir": "outputs",
            "db_path": "stylemind.db",
            "vector_store_path": "vector_store.json",
            "conversation_dir": "conversations",
        }
        self.save()

    def all(self) -> dict:
        """
        获取所有配置

        Returns:
            所有配置
        """
        return self.config.copy()
