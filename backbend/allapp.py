import streamlit as st
import os
from dotenv import load_dotenv

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()

CHROMA_DIR = "./chroma_db"
DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)


@st.cache_resource
def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


@st.cache_resource
def get_vectorstore():
    return Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=get_embeddings(),
    )


def get_llm(provider: str):
    """只保留 DeepSeek（付费）和本地模型（免费）"""
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("请在 .env 中设置 DEEPSEEK_API_KEY")
        return ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=api_key,
            openai_api_base="https://api.deepseek.com/v1",
            temperature=0.1,
        )
    elif provider == "本地模型（免费）":
        # 需要本地安装 Ollama 并运行: ollama run qwen2
        return ChatOpenAI(
            model="qwen2",
            openai_api_key="sk-no-key-required",
            openai_api_base="http://localhost:11434/v1",
            temperature=0.1,
        )
    else:
        raise ValueError(f"不支持的模型: {provider}")


def load_document(file_path: str):
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
    documents = load_document(file_path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=30,
        length_function=len,
    )
    chunks = splitter.split_documents(documents)
    get_vectorstore().add_documents(chunks)
    return len(chunks), len(documents)


def format_history(history: list):
    if not history:
        return "无"
    lines = []
    for h in history[-3:]:
        lines.append(f"用户：{h['question']}")
        lines.append(f"助手：{h['answer']}")
    return "\n".join(lines)


# ==================== Streamlit 界面 ====================

st.set_page_config(page_title="新能源知识助手", page_icon="🤖", layout="wide")

with st.sidebar:
    st.header("⚙️ 系统配置")

    # 只保留 DeepSeek 和本地模型
    provider = st.selectbox(
        "选择模型",
        ["deepseek", "本地模型（免费）"],
        index=0,
        help="DeepSeek 按 token 计费 | 本地模型需安装 Ollama，完全免费",
    )

    if st.button("🧹 清空对话"):
        st.session_state.messages = []
        st.session_state.history = []
        st.rerun()

    st.divider()
    st.header("📁 文档上传")

    uploaded = st.file_uploader(
        "支持 PDF / Word / TXT",
        type=["pdf", "docx", "doc", "txt"],
    )

    if uploaded:
        save_path = os.path.join(DATA_DIR, uploaded.name)
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())

        if st.button("🚀 开始入库"):
            with st.spinner("正在解析并入库..."):
                try:
                    chunk_count, page_count = ingest_file(save_path)
                    st.success(f"✅ 已处理 {page_count} 页/段，切分 {chunk_count} 块入库")
                except Exception as e:
                    st.error(f"❌ 入库失败: {e}")

    # 省钱提示
    st.divider()
    st.caption("💡 省钱技巧：检索 k=3，只传最相关的 3 段给 LLM")

st.title("🤖 新能源知识助手")
st.caption("基于私有文档的 RAG 问答系统 | 支持多轮对话与引用溯源")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    st.session_state.history = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander("📎 查看引用来源"):
                for s in msg["sources"]:
                    st.markdown(f"**{s['title']}**")
                    st.caption(f"> {s['snippet']}")

# ==================== 对话主逻辑（已优化省 token） ====================

if question := st.chat_input("请输入您的问题..."):
    st.chat_message("user").markdown(question)
    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("assistant"):
        with st.spinner("检索资料并生成中..."):
            try:
                # 语义检索：只取最相关的 3 块（省 token）
                retriever = get_vectorstore().as_retriever(search_kwargs={"k": 3})
                docs = retriever.invoke(question)

                context_parts = []
                sources_info = []

                for i, doc in enumerate(docs, 1):
                    source_path = doc.metadata.get("source", "未知")
                    page = doc.metadata.get("page")
                    page_str = f" (第{page + 1}页)" if page is not None else ""
                    file_name = os.path.basename(source_path)

                    context_parts.append(
                        f"【来源{i}】{file_name}{page_str}\n{doc.page_content}"
                    )
                    sources_info.append({
                        "title": f"【来源{i}】{file_name}{page_str}",
                        "snippet": doc.page_content[:150] + "...",
                    })

                context = "\n\n".join(context_parts)

                # 精简 Prompt，减少系统 token 消耗
                template = """你是新能源运维专家。根据【参考资料】回答【问题】，无资料则答"根据现有资料无法回答"。

【历史】
{history}

【资料】
{context}

【问题】
{question}

要求：引用标注[来源1]等，简洁回答。"""

                prompt = ChatPromptTemplate.from_template(template)
                messages = prompt.format_messages(
                    context=context,
                    question=question,
                    history=format_history(st.session_state.history),
                )

                llm = get_llm(provider)
                response = llm.invoke(messages)
                answer = response.content

                st.markdown(answer)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources_info,
                })
                st.session_state.history.append({
                    "question": question,
                    "answer": answer,
                })

            except Exception as e:
                st.error(f"❌ 出错了: {e}")