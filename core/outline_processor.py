"""大纲提炼 - LLM大脑"""
from typing import Optional
from .api_client import APIClient
from .rag_knowledge import RAGKnowledge


class OutlineProcessor:
    """大纲提炼 - LLM大脑"""

    def __init__(self, api_client: APIClient, rag_knowledge: Optional[RAGKnowledge] = None):
        """
        初始化大纲处理器

        Args:
            api_client: API客户端
            rag_knowledge: 可选的RAG知识库
        """
        self.api_client = api_client
        self.rag_knowledge = rag_knowledge

    def process(
        self,
        outline: str,
        model: str = "gpt-4o",
        page_limit: Optional[int] = None
    ) -> dict:
        """
        处理用户大纲

        流程：
        1. 结合RAG知识库（如果可用）
        2. 提炼内容结构
        3. 决定分页
        4. 设计排版
        5. 返回结构化大纲

        Args:
            outline: 用户输入的大纲
            model: 使用的模型
            page_limit: 最大页数限制

        Returns:
            结构化大纲：
            {
                "pages": [
                    {
                        "index": 1,
                        "title": "页面标题",
                        "content": "主要内容",
                        "layout": "左右分栏",
                        "style": "风格描述"
                    },
                    ...
                ],
                "design_notes": "整体风格说明"
            }
        """
        try:
            # 1. 获取RAG上下文
            rag_context = []
            if self.rag_knowledge:
                rag_results = self.rag_knowledge.query(outline, k=3)
                rag_context = [r["text"] for r in rag_results if r.get("text")]

            # 2. 构建提示词
            system_prompt = self._build_system_prompt(rag_context, page_limit)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": outline}
            ]

            # 3. 调用LLM
            response = self.api_client.chat(
                model=model,
                messages=messages,
                max_tokens=4000,
                temperature=0.7
            )

            # 4. 解析结果
            result = self._parse_llm_response(response["content"])
            return result

        except Exception as e:
            raise Exception(f"大纲处理失败: {str(e)}")

    def _build_system_prompt(self, rag_context: list[str], page_limit: Optional[int]) -> str:
        """
        构建系统提示词

        Args:
            rag_context: RAG检索到的上下文
            page_limit: 页数限制

        Returns:
            系统提示词
        """
        base_prompt = """你是一个专业的PPT设计助手。请根据用户的大纲，生成详细的PPT结构。

要求：
1. 将内容合理分配到不同页面（一般每页聚焦一个主题）
2. 为每页指定合适的布局（左右分栏、上下结构、卡片式、全图背景等）
3. 提供简洁的内容摘要
4. 指定整体风格方向

"""
        if rag_context:
            base_prompt += "\n参考知识库中的PPT设计模式：\n"
            for i, ctx in enumerate(rag_context[:2], 1):
                base_prompt += f"\n参考{i}：\n{ctx[:500]}\n"
            base_prompt += "\n请结合以上设计模式进行规划。\n"

        base_prompt += "\n请用JSON格式返回结果，格式如下：\n"
        base_prompt += """
{
    "pages": [
        {
            "index": 1,
            "title": "页面标题",
            "content": "主要内容摘要（50-100字）",
            "layout": "布局类型",
            "style": "风格描述"
        }
    ],
    "design_notes": "整体风格说明"
}
"""

        if page_limit:
            base_prompt += f"\n注意：页数不要超过{page_limit}页。"

        return base_prompt

    def _parse_llm_response(self, content: str) -> dict:
        """
        解析LLM响应

        Args:
            content: LLM返回的文本

        Returns:
            解析后的结构化数据
        """
        import json
        import re

        # 尝试提取JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                data = json.loads(json_match.group())
                # 验证格式
                if "pages" in data and isinstance(data["pages"], list):
                    return data
            except json.JSONDecodeError:
                pass

        # 如果解析失败，返回原始内容
        return {
            "pages": [],
            "design_notes": content,
            "raw_content": content
        }

    def refine_outline(
        self,
        current_outline: dict,
        user_feedback: str,
        model: str = "gpt-4o"
    ) -> dict:
        """
        根据用户反馈优化大纲

        Args:
            current_outline: 当前大纲
            user_feedback: 用户反馈
            model: 模型

        Returns:
            优化后的大纲
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": """你是一个PPT设计专家。用户会对当前的大纲提出修改意见，
请根据反馈调整大纲内容、布局或风格。返回调整后的完整大纲。"""
                },
                {
                    "role": "user",
                    "content": f"当前大纲：\n{current_outline}\n\n用户反馈：\n{user_feedback}"
                }
            ]

            response = self.api_client.chat(
                model=model,
                messages=messages,
                max_tokens=4000,
                temperature=0.7
            )

            result = self._parse_llm_response(response["content"])
            return result

        except Exception as e:
            raise Exception(f"大纲优化失败: {str(e)}")
