#!/usr/bin/env python3
"""
StyleMind 知识库管理 - Streamlit 独立界面
"""
import streamlit as st
import os
import json
import glob
import time

st.set_page_config(page_title="StyleMind 知识库", page_icon="📚")

# 初始化组件
@st.cache_resource
def init_components():
    from core.api_client import APIClient
    from core.pdf_parser import PDFParser
    from core.rag_knowledge import RAGKnowledge
    from storage.vector_store import VectorStore
    from storage.database import Database

    # 加载配置
    with open('config.json', 'r') as f:
        config = json.load(f)

    api = APIClient(config['api_base_url'], config['api_key'])
    vs = VectorStore()
    db = Database()
    rag = RAGKnowledge(vs, db, api)

    return api, rag, config

api, rag, config = init_components()

st.title("📚 StyleMind 知识库管理")

# 侧边栏 - 配置
st.sidebar.header("⚙️ 配置")
st.sidebar.write(f"**API**: {config['api_base_url']}")
st.sidebar.write(f"**模型**: {config.get('chat_model', 'gpt-4o')}")

# 主界面
tab1, tab2, tab3 = st.tabs(["📤 导入", "📊 知识库", "🔍 测试"])

with tab1:
    st.header("导入文件到知识库")

    uploaded_file = st.file_uploader("选择 PDF 文件", type=['pdf'])

    if uploaded_file:
        st.info(f"已选择: {uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.2f} MB)")

        if st.button("🚀 开始导入", type="primary"):
            with st.spinner("正在导入..."):
                # 保存文件
                save_path = f"/tmp/upload_{uploaded_file.name}"
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # 进度显示
                progress_bar = st.progress(0)
                status_text = st.empty()

                def progress_callback(current, total, message):
                    progress = int(current / total * 100) if total > 0 else 0
                    progress_bar.progress(progress)
                    status_text.text(message)

                # 导入
                try:
                    result = rag.ingest_file(save_path, model=config.get('chat_model', 'gpt-4o'), progress_callback=progress_callback)

                    progress_bar.progress(100)
                    status_text.text("完成!")

                    if result.get('status') == 'success':
                        st.success(f"✅ 导入成功! 共 {result.get('pages', result.get('total_pages', 0))} 页")
                    else:
                        st.error(f"❌ 导入失败: {result.get('message', '未知错误')}")

                except Exception as e:
                    st.error(f"❌ 导入出错: {str(e)}")

with tab2:
    st.header("📊 知识库统计")

    # 获取知识库数据
    all_data = rag.vector_store.get_all()

    if all_data:
        # 统计
        total = len(all_data)
        has_insights = sum(1 for item in all_data if item.get('metadata', {}).get('insights') and len(item['metadata']['insights']) > 10)

        col1, col2, col3 = st.columns(3)
        col1.metric("总记录", total)
        col2.metric("有LLM分析", has_insights)
        col3.metric("无LLM分析", total - has_insights)

        # 按文件统计
        st.subheader("📁 按文件统计")
        files = {}
        for item in all_data:
            m = item.get('metadata', {})
            src = m.get('source', '未知')
            if src not in files:
                files[src] = {'total': 0, 'has_insights': 0, 'layouts': {}}
            files[src]['total'] += 1
            if m.get('insights') and len(m['insights']) > 10:
                files[src]['has_insights'] += 1

        for fname, stats in files.items():
            with st.expander(f"📄 {fname}"):
                st.write(f"总页数: {stats['total']}")
                st.write(f"有LLM分析: {stats['has_insights']} ({stats['has_insights']/stats['total']*100:.1f}%)")

        # 显示示例
        st.subheader("📝 Insights 示例")
        examples = [item for item in all_data if item.get('metadata', {}).get('insights') and len(item['metadata']['insights']) > 10]

        if examples:
            for i, item in enumerate(examples[:5]):
                m = item['metadata']
                with st.expander(f"第{m.get('page_index', 0)+1}页 - {m.get('source', '')}"):
                    st.json(json.loads(m['insights'].replace('```json', '').replace('```', '')))
        else:
            st.info("暂无 LLM 分析结果，请先导入文件")
    else:
        st.info("知识库为空，请先导入文件")

with tab3:
    st.header("🔍 API 测试")

    if st.button("测试 API 连接"):
        with st.spinner("测试中..."):
            try:
                resp = api.chat(model='gpt-4o', messages=[{'role': 'user', 'content': '说 hello'}], max_tokens=50, timeout=20)
                st.success(f"✅ API 正常: {resp['content']}")
            except Exception as e:
                st.error(f"❌ API 失败: {str(e)}")

    st.subheader("LLM 深度分析测试")

    # 找 PDF
    pdfs = glob.glob('/tmp/pdf_split_*/*.pdf', recursive=True) or glob.glob('/tmp/**/*.pdf', recursive=True)

    if pdfs and st.button("测试 LLM 分析"):
        from core.pdf_parser import PDFParser
        parser = PDFParser()

        with st.spinner("解析 PDF..."):
            pages, _ = parser.parse(pdfs[0])

        if pages:
            st.info(f"解析到 {len(pages)} 页")

            with st.spinner("LLM 分析中..."):
                insights = rag._analyze_pdf_with_llm(pages[:2], 'gpt-4o')

            for i, ins in enumerate(insights):
                st.success(f"第 {i+1} 页分析成功:")
                if ins:
                    try:
                        st.json(json.loads(ins.replace('```json', '').replace('```', '')))
                    except:
                        st.text(ins[:500])
                else:
                    st.warning(f"第 {i+1} 页分析失败")

if __name__ == "__main__":
    st.sidebar.markdown("---")
    st.sidebar.markdown("Made with ❤️ by StyleMind")
