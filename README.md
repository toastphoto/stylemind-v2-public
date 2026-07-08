# StyleMind v2 - AI对话式PPT生成

一个智能的 AI 对话式 PPT 生成工具，支持：
- 上传大纲并生成 HTML 工作台预览
- 将大纲转成 renderer-neutral RenderPlan
- 导出原生可编辑 PPTX 文本框、形状和图片对象
- 将图片生成用于素材/背景层，而不是整页 PNG 交付

## Public Release Note

This public repository is a sanitized code release. Local API keys, generated files,
private reference decks, cleaned reference-template libraries, and third-party
experiment dumps are intentionally excluded.

Some verification scripts support private/local reference fixtures through
environment variables such as `STYLEMIND_REFERENCE_SOURCE`,
`STYLEMIND_DOCX_FIXTURE`, and `DASHIAI_PPT_SKILL_ROOT`. Without those assets, run
the app and the generic unit tests, but do not expect the private reference-template
visual QA pipeline to be fully reproducible.

## 快速开始

### 1. 环境要求

- Python 3.10+
- 支持 Windows / macOS / Linux

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行

```bash
cp config.example.json config.json

# Windows
start.bat

# macOS / Linux
./start.sh

# 上传/工作台 Web 服务
python web_ui/api_server.py
```

### 4. 访问

打开浏览器访问：

- 上传页：http://localhost:8091/upload
- Agent 工作台：http://localhost:8091/workbench
- 旧 Gradio 入口默认：http://localhost:7860

## 使用说明

### 第一步：配置API

1. 点击"设置"标签
2. 填入你的 OpenAI-compatible API Base URL（如：https://api.openai.com/v1）
3. 填入 API Key
4. 选择模型：
   - 对话模型：chatgpt-4o-latest（推荐）
   - 图片模型：gpt-image-2（推荐）
   - 嵌入模型：text-embedding-3-small
5. 点击"保存设置"

### 第二步：上传知识库

1. 点击"知识库管理"标签
2. 上传公司的 PPT 或 PDF 文件
3. AI 会自动分析并学习风格

### 第三步：生成PPT

1. 回到"主界面"标签
2. 输入大纲或需求
3. AI 会根据知识库风格生成 PPT

## 项目结构

```
stylemind_v2/
├── app.py                 # 旧 Gradio 入口
├── config.py              # 配置管理
├── config.example.json    # 本地配置模板
├── requirements.txt       # 依赖列表
├── start.bat             # Windows启动脚本
├── start.sh              # macOS/Linux启动脚本
├── README.md             # 本文件
├── core/                 # 核心模块
│   ├── api_client.py     # API客户端
│   ├── pdf_parser.py     # PDF解析
│   ├── rag_knowledge.py  # RAG知识库
│   └── layout_planner.py # 布局规划
├── web_ui/               # 上传页、工作台和 API 服务
│   ├── api_server.py
│   ├── upload.html
│   ├── workbench.html
│   └── services/         # RenderPlan 和 PPTX 渲染器
├── scripts/              # 验证和渲染探针
└── ui/                   # UI模块
    └── gradio_app.py     # Gradio界面
```

## 常见问题

### Q: 启动后无法访问？
A: 确保 7860 端口没有被占用，或修改 app.py 中的端口

### Q: PDF上传后一直在分析？
A: 大文件（>50页）会自动只分析前50页，超过92MB的PDF建议拆分

### Q: 如何更换端口？
A: 修改 app.py 中的 `server_port=7860` 为其他端口

## 技术栈

- Gradio - Web界面
- OpenAI API - AI对话和图片生成
- python-pptx - PPT处理
- pdfplumber - PDF解析
- ChromaDB - 向量存储
- SQLite - 数据存储

## License

MIT
