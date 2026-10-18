import os
import sys
from services.ingest_service import ingest_file, DATA_DIR


def ingest_folder(folder_path: str = DATA_DIR):
    """批量入库整个文件夹"""
    files = [f for f in os.listdir(folder_path)
             if f.endswith(('.txt', '.pdf', '.doc', '.docx'))]
    if not files:
        print("⚠️ 未找到可处理的文档")
        return

    total = 0
    for f in files:
        chunk_count, doc_count = ingest_file(os.path.join(folder_path, f))
        total += chunk_count
        print(f"✅ {f}: {doc_count} 页/段 → {chunk_count} 块")

    print(f"\n🎉 全部完成！共入库 {total} 个文本块")


if __name__ == "__main__":
    # 用法1: python ingest.py → 批量处理 data/ 文件夹
    # 用法2: python ingest.py ./data/某文件.pdf → 单文件
    if len(sys.argv) > 1:
        chunk_count, doc_count = ingest_file(sys.argv[1])
        print(f"✅ 已处理 {doc_count} 页/段，切分 {chunk_count} 块入库")
    else:
        ingest_folder()