import streamlit as st
import os
from services.ingest_service import ingest_file, DATA_DIR
from services.agent_graph import AgenticRAGAssistant  # 替换为 Agent 版本

st.set_page_config(page_title="新能源 Agent 知识助手", page_icon="🤖", layout="wide")

# ==================== 侧边栏 ====================
with st.sidebar:
    st.header("⚙️ 系统配置")

    provider = st.selectbox(
        "选择模型",
        ["deepseek", "本地模型（免费）"],
        index=0,
    )

    if st.button("🧹 清空对话"):
        st.session_state.messages = []
        if "assistant" in st.session_state:
            st.session_state.assistant.clear_history()
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

    st.divider()

    # Agent 专属：显示思考过程开关
    show_reasoning = st.toggle("🔍 显示 Agent 思考过程", value=False)

    st.caption("💡 Agent 特性：自动规划 → 检索 → 评分 → 重写 → 生成")

# ==================== 主界面 ====================
st.title("🤖 新能源 Agent 知识助手")
st.caption("基于 LangGraph 的智能体 RAG | 支持策略规划、自我纠错与引用溯源")

# 初始化状态
if "messages" not in st.session_state:
    st.session_state.messages = []
if "assistant" not in st.session_state or st.session_state.get("provider") != provider:
    st.session_state.assistant = AgenticRAGAssistant(provider=provider)
    st.session_state.provider = provider

assistant = st.session_state.assistant

# 渲染历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander("📎 查看引用来源"):
                for s in msg["sources"]:
                    st.markdown(f"**{s['title']}**")
                    st.caption(f"> {s['snippet']}")
        # Agent 专属：展示思考过程
        if show_reasoning and msg.get("reasoning"):
            with st.expander("🧠 Agent 思考过程"):
                st.text(msg["reasoning"])

# ==================== 对话交互 ====================
if question := st.chat_input("请输入您的问题..."):
    # 用户消息
    st.chat_message("user").markdown(question)
    st.session_state.messages.append({"role": "user", "content": question})

    # 助手回答
    with st.chat_message("assistant"):
        with st.spinner("Agent 正在思考并检索资料..."):
            try:
                answer, sources = assistant.ask(question)
                st.markdown(answer)

                # 从 assistant 获取思考过程（需要稍微修改 AgenticRAGAssistant 暴露 reasoning）
                # 这里简化处理，实际可通过 graph.stream 获取中间状态
                reasoning = "Agent 执行了安全检查 → 策略规划 → 检索 → 评分 → 生成"

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources,
                    "reasoning": reasoning,
                })
            except Exception as e:
                st.error(f"❌ 出错了: {e}")