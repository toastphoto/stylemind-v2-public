"""Gradio对话UI"""
import os
import uuid
import gradio as gr
from pathlib import Path

from config import Config
from core.api_client import APIClient
from core.rag_knowledge import RAGKnowledge
from core.outline_processor import OutlineProcessor
from core.layout_planner import LayoutPlanner
from core.image_generator import ImageGenerator
from core.png_to_ppt import PNGToPPT
from storage.database import Database
from storage.vector_store import VectorStore
from storage.conversation_store import ConversationStore


class StyleMindApp:
    """StyleMind应用主类"""

    def __init__(self):
        """初始化应用"""
        # 加载配置
        self.config = Config()

        # 初始化存储
        self.db = Database()
        self.vector_store = VectorStore()
        self.conversation_store = ConversationStore()

        # 初始化API客户端
        self.api_client = None
        self._init_api_client()

        # 初始化核心组件
        self.rag_knowledge = None
        self.outline_processor = None
        self.layout_planner = LayoutPlanner()
        self.image_generator = None
        self.png_to_ppt = None

        if self.api_client:
            self._init_components()

        # 会话管理
        self.current_session_id = str(uuid.uuid4())
        self.current_outline = None
        self.generated_images = []

    def _init_api_client(self):
        """初始化API客户端"""
        api_base_url = self.config.get_api_base_url()
        api_key = self.config.get_api_key()

        if api_base_url and api_key:
            try:
                self.api_client = APIClient(api_base_url, api_key)
            except Exception as e:
                print(f"初始化API客户端失败: {e}")

    def _init_components(self):
        """初始化核心组件"""
        self.rag_knowledge = RAGKnowledge(
            self.vector_store,
            self.db,
            self.api_client
        )
        self.outline_processor = OutlineProcessor(
            self.api_client,
            self.rag_knowledge
        )
        self.image_generator = ImageGenerator(self.api_client)
        self.png_to_ppt = PNGToPPT(self.api_client)

    def get_available_models(self) -> list[str]:
        """获取可用模型列表"""
        if not self.api_client:
            return []
        return self.api_client.list_models()

    def chat_with_ai(self, message: str, history: list) -> tuple:
        """
        与AI对话

        Args:
            message: 用户消息
            history: 对话历史

        Returns:
            (响应文本, 更新后的历史)
        """
        if not self.api_client:
            return "请先在设置中配置API", history

        try:
            # 从配置获取模型
            model = self.config.get("chat_model", "chatgpt-4o-latest")

            # 保存用户消息
            self.conversation_store.save_conversation(
                self.current_session_id,
                history + [[message, None]]
            )

            # 检查是否是PPT生成请求
            if any(keyword in message.lower() for keyword in ["生成ppt", "生成ppt", "做ppt", "创建ppt"]):
                return self._process_ppt_request(message, history)

            # 普通对话
            messages = [
                {"role": "user", "content": message}
            ]

            response = self.api_client.chat(model=model, messages=messages)

            return response["content"], history + [[message, response["content"]]]

        except Exception as e:
            return f"错误: {str(e)}", history

    def _process_ppt_request(self, message: str, history: list) -> tuple:
        """
        处理PPT生成请求

        Args:
            message: 用户请求
            history: 对话历史

        Returns:
            (响应文本, 更新后的历史)
        """
        try:
            # 获取模型
            models = self.get_available_models()
            model = models[0] if models else "gpt-4o"

            # 处理大纲
            result = self.outline_processor.process(message, model=model)

            if "raw_content" in result:
                # LLM返回的不是JSON格式，显示原始内容
                return f"大纲已生成：\n\n{result.get('raw_content', '处理中...')}", history + [[message, result.get('raw_content', '')]]

            self.current_outline = result

            # 显示生成的页面结构
            pages_info = []
            for page in result.get("pages", []):
                pages_info.append(f"第{page['index']}页: {page['title']} ({page.get('layout', '左右分栏')})")

            pages_text = "\n".join(pages_info)

            return f"大纲已生成！\n\n{result.get('design_notes', '')}\n\n页面结构：\n{pages_text}", history + [[message, f"已生成大纲，包含{len(result.get('pages', []))}页"]]

        except Exception as e:
            return f"生成大纲失败: {str(e)}", history

    def generate_images(self, outline: dict = None) -> list[str]:
        """
        根据大纲生成图片

        Args:
            outline: 大纲字典

        Returns:
            生成的图片路径列表
        """
        if not outline:
            outline = self.current_outline

        if not outline:
            raise Exception("没有可用的大纲")

        if not self.image_generator:
            raise Exception("图片生成器未初始化")

        try:
            # 从配置获取图片生成模型
            image_model = self.config.get("image_model", "gpt-image-1")

            if not image_model:
                # 使用默认模型
                image_model = "gpt-image-1" if "gpt-image-1" in models else "dall-e-3"

            # 规划排版
            pages = outline.get("pages", [])
            planned_pages = self.layout_planner.plan(pages)

            # 生成图片
            prompts = [page["image_prompt"] for page in planned_pages]
            images = self.image_generator.generate_batch(
                prompts=prompts,
                model=image_model
            )

            self.generated_images = [img for img in images if img]

            return self.generated_images

        except Exception as e:
            raise Exception(f"生成图片失败: {str(e)}")

    def convert_to_ppt(self, image_paths: list[str]) -> str:
        """
        转换图片为PPT

        Args:
            image_paths: 图片路径列表

        Returns:
            PPT文件路径
        """
        if not image_paths:
            raise Exception("没有图片可以转换")

        if not self.png_to_ppt:
            raise Exception("PPT转换器未初始化")

        try:
            # 生成输出路径
            output_dir = os.path.dirname(image_paths[0]) if image_paths else "outputs"
            os.makedirs(output_dir, exist_ok=True)

            output_pptx = os.path.join(output_dir, f"presentation_{self.current_session_id[:8]}.pptx")

            # 批量转换
            self.png_to_ppt.convert_batch(
                png_paths=image_paths,
                output_pptx=output_pptx
            )

            return output_pptx

        except Exception as e:
            raise Exception(f"转换PPT失败: {str(e)}")

    def ingest_ppt_to_knowledge(self, ppt_path: str) -> dict:
        """
        导入PPT到知识库

        Args:
            ppt_path: PPT文件路径

        Returns:
            导入结果
        """
        if not self.rag_knowledge:
            return {"status": "error", "message": "知识库未初始化"}

        try:
            model = self.config.get("chat_model", "chatgpt-4o-latest")
            result = self.rag_knowledge.ingest_ppt(ppt_path, model=model)
            return result

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def ingest_file_to_knowledge(self, file_path: str, progress_callback=None) -> dict:
        """
        导入文件到知识库（自动识别 PPT 或 PDF）

        Args:
            file_path: 文件路径
            progress_callback: 进度回调函数

        Returns:
            导入结果
        """
        if not self.rag_knowledge:
            return {"status": "error", "message": "知识库未初始化"}

        try:
            model = self.config.get("chat_model", "chatgpt-4o-latest")
            print(f"[DEBUG] 开始导入文件: {file_path}")
            print(f"[DEBUG] 使用模型: {model}")
            print(f"[DEBUG] api_client: {self.api_client}")
            print(f"[DEBUG] rag_knowledge.api_client: {self.rag_knowledge.api_client}")

            result = self.rag_knowledge.ingest_file(file_path, model=model, progress_callback=progress_callback)

            print(f"[DEBUG] 导入完成: {result.get('status')}")
            return result

        except Exception as e:
            print(f"[ERROR] 导入失败: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def save_settings(self, api_base_url: str, api_key: str):
        """
        保存设置

        Args:
            api_base_url: API基础URL
            api_key: API密钥
        """
        self.config.set_api(api_base_url, api_key)

        # 重新初始化API客户端
        self._init_api_client()
        if self.api_client:
            self._init_components()

    def clear_conversation(self):
        """清空对话"""
        self.current_session_id = str(uuid.uuid4())
        self.current_outline = None
        self.generated_images = []
        return [], None

    def get_knowledge_status(self) -> str:
        """
        获取知识库状态

        Returns:
            状态信息
        """
        if not self.rag_knowledge:
            return "知识库未初始化"

        knowledge = self.rag_knowledge.get_all_knowledge()
        return f"知识库包含 {len(knowledge)} 条记录"


def create_app() -> gr.Blocks:
    """
    创建Gradio应用

    Returns:
        Gradio应用
    """
    app_instance = StyleMindApp()

    with gr.Blocks(title="StyleMind v2 - AI PPT生成") as app:
        gr.Markdown("""
        # StyleMind v2 - AI对话式PPT生成

        一个智能的AI对话式PPT生成工具，支持：
        - 对话式交互生成PPT
        - 上传PPT到知识库学习风格
        - 自动排版规划
        - 图片生成和PPT转换
        """)

        with gr.Tab("主界面"):
            with gr.Row():
                # 左侧：对话区域
                with gr.Column(scale=2):
                    chatbot = gr.Chatbot(
                        label="对话历史",
                        height=500
                    )

                    msg = gr.Textbox(
                        label="输入",
                        placeholder="输入大纲或对话...（例如：帮我创建一个关于AI技术发展的PPT）",
                        lines=3
                    )

                    with gr.Row():
                        submit_btn = gr.Button("发送", variant="primary")
                        clear_btn = gr.Button("清空对话")

                # 右侧：预览和操作区域
                with gr.Column(scale=1):
                    gr.Markdown("### 预览区域")

                    with gr.Tab("PNG预览"):
                        preview = gr.Image(
                            label="生成的图片预览",
                            height=300
                        )

                    with gr.Tab("所有图片"):
                        gallery = gr.Gallery(
                            label="生成的图片",
                            columns=3,
                            height=400
                        )

                    generate_ppt_btn = gr.Button(
                        "根据大纲生成图片",
                        variant="primary",
                        size="large"
                    )

                    convert_ppt_btn = gr.Button(
                        "转换为PPT",
                        variant="secondary",
                        size="large"
                    )

                    download_file = gr.File(
                        label="下载PPT"
                    )

                    status_text = gr.Textbox(
                        label="状态",
                        interactive=False
                    )

        with gr.Tab("知识库管理"):
            gr.Markdown("""
            ### 知识库管理

            上传 PPT 或 PDF 文件，AI会自动分析并学习其中的设计模式、排版逻辑和风格特征。
            """)

            with gr.Row():
                file_upload = gr.File(
                    label="上传文件（支持 .pptx 和 .pdf）",
                    file_types=[".pptx", ".pdf"],
                    height=100
                )
                ingest_btn = gr.Button("导入知识库", variant="primary")

            kb_status = gr.Textbox(
                label="知识库状态",
                interactive=False
            )

            with gr.Row():
                show_kb_btn = gr.Button("查看知识库")
                clear_kb_btn = gr.Button("清空知识库")

            kb_display = gr.JSON(
                label="知识库内容",
                height=300
            )

        with gr.Tab("设置"):
            gr.Markdown("""
            ### API设置

            配置您的OpenAI兼容API。
            """)

            with gr.Row():
                api_url = gr.Textbox(
                    label="API Base URL",
                    placeholder="https://api.openai.com/v1",
                    value=app_instance.config.get_api_base_url(),
                    scale=2
                )
                api_key = gr.Textbox(
                    label="API Key",
                    type="password",
                    placeholder="sk-...",
                    value=app_instance.config.get_api_key(),
                    scale=2
                )

            with gr.Row():
                save_settings_btn = gr.Button("保存设置", variant="primary")
                test_connection_btn = gr.Button("测试连接")

            test_result = gr.Textbox(
                label="连接测试结果",
                interactive=False
            )

            available_models = gr.Dropdown(
                label="可用模型",
                choices=app_instance.get_available_models(),
                interactive=False
            )

            refresh_models_btn = gr.Button("刷新模型列表")

            # 模型分类展示
            with gr.Accordion("推荐模型配置", open=True):
                gr.Markdown("**💬 对话模型（大纲提炼、RAG检索）**")
                chat_model_select = gr.Dropdown(
                    label="对话模型",
                    choices=[
                        "chatgpt-4o-latest（推荐）",
                        "gpt-4.5-preview（最强推理）",
                        "o3（深度思考）",
                        "o4-mini（快速思考）",
                        "claude-sonnet-4-20250514",
                        "gemini-2.5-pro",
                        "deepseek-chat",
                    ],
                    value="chatgpt-4o-latest（推荐）",
                    allow_custom_value=True,
                )

                gr.Markdown("**🎨 图片生成模型（生成PPT页面）**")
                image_model_select = gr.Dropdown(
                    label="图片生成模型",
                    choices=[
                        "gpt-image-2（最新·推荐）",
                        "gpt-image-2-preview（预览版）",
                        "gpt-image-1（主力）",
                        "gpt-4o-image（图生图）",
                        "gpt-4o-image-vip（高质量）",
                        "dall-e-3",
                        "nano-banana（Gemini优化版）",
                        "recraftv3（矢量风格）",
                        "flux-kontext-max（Flux）",
                    ],
                    value="gpt-image-2（最新·推荐）",
                    allow_custom_value=True,
                )

                gr.Markdown("**🔢 嵌入模型（RAG知识库向量化）**")
                embed_model_select = gr.Dropdown(
                    label="嵌入模型",
                    choices=[
                        "text-embedding-3-small（推荐·性价比高）",
                        "text-embedding-3-large（高精度）",
                        "text-embedding-ada-002",
                    ],
                    value="text-embedding-3-small（推荐·性价比高）",
                    allow_custom_value=True,
                )

        # ==================== 事件绑定 ====================

        def submit_message(message, history):
            """提交消息"""
            if not message.strip():
                return "", history

            response, new_history = app_instance.chat_with_ai(message, history)
            return "", new_history

        # 发送按钮
        submit_btn.click(
            fn=submit_message,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot]
        )

        # 回车提交
        msg.submit(
            fn=submit_message,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot]
        )

        # 清空对话
        def clear_conversation():
            return [], None, ""

        clear_btn.click(
            fn=clear_conversation,
            outputs=[chatbot, preview, status_text]
        )

        # 生成图片
        def handle_generate_images():
            try:
                images = app_instance.generate_images()
                return images, f"成功生成 {len(images)} 张图片"
            except Exception as e:
                return [], str(e)

        generate_ppt_btn.click(
            fn=handle_generate_images,
            outputs=[gallery, status_text]
        )

        # 转换为PPT
        def handle_convert_ppt():
            try:
                if not app_instance.generated_images:
                    return None, "没有可转换的图片"

                pptx_path = app_instance.convert_to_ppt(app_instance.generated_images)
                return pptx_path, f"PPT已生成: {pptx_path}"
            except Exception as e:
                return None, str(e)

        convert_ppt_btn.click(
            fn=handle_convert_ppt,
            outputs=[download_file, status_text]
        )

        # 导入文件到知识库
        def handle_ingest_file(file):
            if not file:
                return "请先上传文件"

            try:
                result = app_instance.ingest_file_to_knowledge(file)

                if result.get("status") == "success":
                    file_type = result.get("metadata", {}).get("parser", "PPT")
                    total_pages = result.get("total_pages", result.get("pages", 0))
                    analyzed_pages = result.get("pages", 0)
                    elapsed = result.get("elapsed_seconds", 0)

                    # 显示进度信息
                    progress = result.get("progress", {})

                    msg = f"✅ 导入成功！\n"
                    msg += f"📄 文件类型: {file_type}\n"

                    # 显示拆分信息
                    split_info = result.get("split_info", {})
                    if split_info.get("split_count", 1) > 1:
                        msg += f"📦 自动拆分: {split_info['original_file']} ({split_info['original_size_mb']}MB) → {split_info['split_count']} 个文件\n"

                    msg += f"📊 总页数: {total_pages}\n"
                    msg += f"📝 已导入: {analyzed_pages} 页\n"
                    msg += f"⏱️ 耗时: {elapsed} 秒"

                    return msg
                else:
                    error_msg = result.get('message', '未知错误')
                    # 检查是否是API错误
                    if 'API' in error_msg or '连续失败' in error_msg:
                        return f"❌ API 错误，导入已停止！\n\n{error_msg}\n\n请检查：\n1. API Key 是否正确\n2. API 服务是否正常\n3. 网络是否通畅\n\n修复后重新上传即可。"
                    return f"❌ 导入失败: {error_msg}"
            except Exception as e:
                error_str = str(e)
                if 'API' in error_str or '连续失败' in error_str:
                    return f"❌ API 错误，导入已停止！\n\n{error_str}\n\n请检查 API 配置后重试。"
                import traceback
                return f"❌ 导入失败: {error_str}\n{traceback.format_exc()}"

        ingest_btn.click(
            fn=handle_ingest_file,
            inputs=[file_upload],
            outputs=[kb_status]
        )

        # 查看知识库
        def show_knowledge():
            if not app_instance.rag_knowledge:
                return "知识库未初始化"

            try:
                # 从向量数据库获取带排版信息的数据
                knowledge = app_instance.rag_knowledge.vector_store.get_all()
                if not knowledge:
                    return "知识库为空"

                # 统计信息
                total = len(knowledge)
                files = set()
                layout_stats = {"cover": 0, "toc": 0, "content": 0, "split": 0, "data": 0, "summary": 0}

                for item in knowledge:
                    metadata = item.get('metadata', {})
                    files.add(metadata.get('source', '未知'))
                    lt = metadata.get('layout_type', 'content')
                    if lt in layout_stats:
                        layout_stats[lt] += 1

                # 构建显示文本
                result = f"📚 知识库深度统计\n"
                result += f"━━━━━━━━━━━━━━━━\n"
                result += f"📊 总记录数: {total} 条\n"
                result += f"📁 来源文件: {len(files)} 个\n\n"

                # 排版类型分布
                result += f"📐 排版类型分布:\n"
                for lt, count in layout_stats.items():
                    if count > 0:
                        result += f"  • {lt}: {count} 页\n"

                # 显示来源文件
                result += f"\n📂 来源文件:\n"
                for f in files:
                    result += f"  • {f}\n"

                # 显示前5条的详细排版信息
                result += f"\n📝 最近导入的内容（前5条带排版信息）:\n"
                result += f"━━━━━━━━━━━━━━━━\n"
                for i, item in enumerate(knowledge[:5], 1):
                    metadata = item.get('metadata', {})
                    source = metadata.get('source', '未知')
                    page = metadata.get('page_index', 0) + 1
                    layout_type = metadata.get('layout_type', '未记录')
                    columns = metadata.get('layout_columns', '未记录')
                    alignment = metadata.get('layout_alignment', '未记录')
                    density = metadata.get('layout_density', '未记录')
                    has_images = '✅' if metadata.get('has_images') else '❌'
                    has_tables = '✅' if metadata.get('has_tables') else '❌'
                    title_h = metadata.get('title_hierarchy', [])

                    result += f"\n{i}. {source} [第{page}页]\n"
                    result += f"   📐 布局: {layout_type} | {columns}栏 | {alignment}对齐 | {density}\n"
                    result += f"   🖼️ 图片: {has_images} | 📊 表格: {has_tables}\n"
                    if title_h and len(title_h) > 0:
                        result += f"   📑 标题层级: {len(title_h)}级\n"
                        for h in title_h[:2]:
                            result += f"      - {h.get('type')}: {h.get('text', '')[:30]}\n"

                if total > 5:
                    result += f"\n... 还有 {total - 5} 条记录 ..."

                return result
            except Exception as e:
                import traceback
                return f"查看失败: {str(e)}\n{traceback.format_exc()}"

        show_kb_btn.click(
            fn=show_knowledge,
            outputs=[kb_status]
        )

        # 清空知识库
        def clear_knowledge():
            if app_instance.rag_knowledge:
                result = app_instance.rag_knowledge.clear()
                return result.get("message", "已清空")
            return "知识库未初始化"

        clear_kb_btn.click(
            fn=clear_knowledge,
            outputs=[kb_status]
        )

        # 保存设置
        def save_settings(url, key, chat_model, image_model, embed_model):
            # 解析模型名（去掉括号里的中文说明）
            def parse_model(raw):
                if not raw:
                    return ""
                return raw.split("（")[0].split("(")[0].strip()

            app_instance.save_settings(url, key)
            app_instance.config.set("chat_model", parse_model(chat_model))
            app_instance.config.set("image_model", parse_model(image_model))
            app_instance.config.set("embed_model", parse_model(embed_model))
            return f"✅ 设置已保存！\n对话模型: {parse_model(chat_model)}\n图片模型: {parse_model(image_model)}\n嵌入模型: {parse_model(embed_model)}"

        save_settings_btn.click(
            fn=save_settings,
            inputs=[api_url, api_key, chat_model_select, image_model_select, embed_model_select],
            outputs=[test_result]
        )

        # 测试连接
        def test_api_connection():
            if not app_instance.api_client:
                return "API未配置，请先保存设置"

            try:
                models = app_instance.api_client.list_models()
                if models:
                    # 过滤掉embedding模型，只保留对话和图片模型
                    chat_models = [m for m in models if any(x in m.lower() for x in ['gpt', 'claude', 'chat', 'text', 'vision', 'image', 'o1', 'o3', 'o4'])]
                    display_models = chat_models[:10] if chat_models else models[:10]
                    return f"✅ 连接成功！\n可用模型: {', '.join(display_models)}"
                else:
                    return "⚠️ 连接成功，但无法获取模型列表。\n可能原因：API不支持/models端点\n建议：请手动输入模型名称"
            except Exception as e:
                return f"❌ 连接失败: {str(e)}"

        test_connection_btn.click(
            fn=test_api_connection,
            outputs=[test_result]
        )

        # 刷新模型列表
        def refresh_models():
            models = app_instance.get_available_models()
            if models:
                return gr.Dropdown.update(choices=models, value=models[0] if models else None)
            else:
                return gr.Dropdown.update(
                    choices=["gpt-4o", "gpt-4o-mini", "gpt-image-1", "dall-e-3"],
                    value="gpt-4o"
                )

        refresh_models_btn.click(
            fn=refresh_models,
            outputs=[available_models]
        )

    return app


def main():
    """主函数"""
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False
    )


if __name__ == "__main__":
    main()
