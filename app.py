"""StyleMind v2 - AI对话式PPT生成

主入口文件
"""
from ui.gradio_app import main as create_app


def main():
    """主函数"""
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True,
        show_error=True
    )


if __name__ == "__main__":
    main()
