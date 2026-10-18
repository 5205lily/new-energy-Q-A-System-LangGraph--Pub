from functools import lru_cache
from langchain_chroma import Chroma
from core.embeddings import get_embeddings

CHROMA_DIR = "./chroma_db"


@lru_cache(maxsize=1)
def get_vectorstore():
    """加载持久化 Chroma 向量库（全局单例）"""
    return Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=get_embeddings(),
    )