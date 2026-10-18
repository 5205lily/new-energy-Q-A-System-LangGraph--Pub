import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from core.vectorstore import get_vectorstore

DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)


def load_document(file_path: str):
    """根据后缀自动选择加载器（PDF / Word / TXT）"""
    if file_path.endswith(".pdf"):
        return PyPDFLoader(file_path).load()
    elif file_path.endswith((".doc", ".docx")):
        try:
            from langchain_community.document_loaders import UnstructuredWordDocumentLoader
            return UnstructuredWordDocumentLoader(file_path).load()
        except ImportError:
            raise ImportError("请先安装: pip install python-docx unstructured")
    elif file_path.endswith(".txt"):
        return TextLoader(file_path, encoding="utf-8").load()
    else:
        raise ValueError("仅支持 PDF / Word / TXT 格式")


def ingest_file(file_path: str):
    """文档上传 → 分块 → 增量入库"""
    documents = load_document(file_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=30,
        length_function=len,
    )
    chunks = splitter.split_documents(documents)

    get_vectorstore().add_documents(chunks)  # 增量添加，不删旧数据

    return len(chunks), len(documents)