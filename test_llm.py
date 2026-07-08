#!/usr/bin/env python3
"""
独立测试脚本 - 测试 LLM 深度分析是否正常工作
"""
import json
import glob

# 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

print(f"API: {config['api_base_url']}")

# 测试 1: API 连接
print("\n=== 测试 1: API 连接 ===")
from core.api_client import APIClient
api = APIClient(config['api_base_url'], config['api_key'])

try:
    resp = api.chat(model='gpt-4o', messages=[{'role': 'user', 'content': '说 hello'}], max_tokens=20, timeout=15)
    print(f"✅ API 正常: {resp['content']}")
except Exception as e:
    print(f"❌ API 失败: {e}")
    exit(1)

# 测试 2: PDF 解析
print("\n=== 测试 2: PDF 解析 ===")
from core.pdf_parser import PDFParser
parser = PDFParser()

# 找最新的 PDF
pdfs = glob.glob('/tmp/pdf_split_*/*.pdf', recursive=True) or glob.glob('/tmp/**/*.pdf', recursive=True)
if pdfs:
    pdf_path = pdfs[0]
    print(f"使用 PDF: {pdf_path}")
    pages, meta = parser.parse(pdf_path)
    print(f"✅ 解析成功: {len(pages)} 页")
else:
    print("❌ 没有找到 PDF")
    exit(1)

# 测试 3: LLM 分析
print("\n=== 测试 3: LLM 深度分析 ===")
from core.rag_knowledge import RAGKnowledge
from storage.vector_store import VectorStore
from storage.database import Database

vs = VectorStore()
db = Database()
rag = RAGKnowledge(vs, db, api)

# 只分析前3页
test_pages = pages[:3]
print(f"分析 {len(test_pages)} 页...")

try:
    insights = rag._analyze_pdf_with_llm(test_pages, 'gpt-4o')
    print(f"✅ LLM 分析成功!")
    print(f"   返回 {len(insights)} 条 insights")
    for i, ins in enumerate(insights):
        print(f"\n   第{i+1}页 insights:")
        print(f"   {ins[:300]}...")
except Exception as e:
    print(f"❌ LLM 分析失败: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# 测试 4: 存储到向量数据库
print("\n=== 测试 4: 存储到向量数据库 ===")
try:
    for i, page in enumerate(test_pages):
        content = f"{page.title}\n{page.content}"
        layout_data = page.layout.to_dict() if page.layout else {}

        vs.add(
            text=content,
            metadata={
                "source": f"测试_{i+1}.pdf",
                "page_index": i,
                "layout_type": layout_data.get("layout_type", "content"),
                "file_type": "pdf",
                "insights": insights[i] if i < len(insights) else "",
            }
        )
    print("✅ 存储成功!")

    # 验证存储
    results = vs.get_all()
    has_insights = sum(1 for r in results if r.get('metadata', {}).get('insights'))
    print(f"✅ 验证: {has_insights}/{len(results)} 条记录有 insights")

except Exception as e:
    print(f"❌ 存储失败: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "="*50)
print("✅ 所有测试通过!")
print("="*50)
