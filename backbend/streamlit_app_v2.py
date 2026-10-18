import streamlit as st
import os
from services.ingest_service import ingest_file, DATA_DIR
from services.agent_graph_v2 import AgenticRAGAssistantV2
from services.checkpointer_factory import get_checkpointer

st.set_page_config(
    page_title="新能源 Agent 知识助手 v2.0",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CSS 美化 ====================
st.markdown("""
<style>
.agent-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    margin-right: 6px;
}
.badge-calc { background: #e3f2fd; color: #1565c0; }
.badge-chart { background: #f3e5f5; color: #7b1fa2; }
.badge-hitl { background: #fff3e0; color: #e65100; }
.badge-ok { background: #e8f5e9; color: #2e7d32; }
.reasoning-box {
    background: #f8f9fa;
    border-left: 3px solid #1976d2;
    padding: 10px 14px;
    margin: 8px 0;
    border-radius: 0 8px 8px 0;
    font-family: monospace;
    font-size: 13px;
    color: #424242;
}
</style>
""", unsafe_allow_html=True)

# ==================== 侧边栏 ====================
with st.sidebar:
    st.header("⚙️ 系统配置")

    provider = st.selectbox("选择模型", ["deepseek", "本地模型（免费）"], index=0)

    # 持久化后端选择
    backend = st.selectbox(
        "持久化后端",
        ["memory", "sqlite", "postgres", "redis"],
        index=0,
        help="Memory=重启丢失, SQLite=本地文件, Postgres=生产推荐, Redis=分布式"
    )

    if st.button("🧹 清空对话"):
        st.session_state.messages = []
        st.session_state.interrupted = False
        st.session_state.interrupt_data = None
        if "assistant" in st.session_state:
            st.session_state.assistant.clear_history()
        st.rerun()

    # 时间穿越调试
    with st.expander("🕐 时间穿越（调试）"):
        if "assistant" in st.session_state:
            try:
                history = st.session_state.assistant.get_state_history()
                if history:
                    st.caption(f"当前会话共 {len(history)} 个检查点")
                    for i, h in enumerate(history[:5]):
                        st.text(f"#{i}: {h.values.get('question', 'N/A')[:30]}...")
                else:
                    st.caption("暂无检查点历史")
            except Exception as e:
                st.caption(f"获取历史失败: {e}")

    st.divider()
    st.header("📁 文档上传")
    uploaded = st.file_uploader("支持 PDF / Word / TXT", type=["pdf", "docx", "doc", "txt"])
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
    show_reasoning = st.toggle("🔍 显示 Agent 思考过程", value=False)
    st.caption("💡 Agent v2.0 特性：\n- 策略规划 + 多 Agent 协作\n- 自我纠错（查询重写）\n- 人工审核（HITL）\n- 状态持久化")

# ==================== 主界面 ====================
st.title("🤖 新能源 Agent 知识助手 v2.0")
st.caption("基于 LangGraph 的智能体 RAG | 支持计算 Agent、图表 Agent、人工审核与状态持久化")

# 初始化状态
if "messages" not in st.session_state:
    st.session_state.messages = []
if "interrupted" not in st.session_state:
    st.session_state.interrupted = False
if "interrupt_data" not in st.session_state:
    st.session_state.interrupt_data = None

# 初始化/切换 Agent
if "assistant" not in st.session_state or st.session_state.get("provider") != provider or st.session_state.get("backend") != backend:
    checkpointer = get_checkpointer(backend)
    st.session_state.assistant = AgenticRAGAssistantV2(
        provider=provider,
        checkpointer=checkpointer
    )
    st.session_state.provider = provider
    st.session_state.backend = backend
    st.session_state.messages = []  # 切换后端时重置（不同后端状态不互通）
    st.session_state.interrupted = False
    st.session_state.interrupt_data = None

assistant = st.session_state.assistant

# ==================== HITL 中断处理界面 ====================
if st.session_state.interrupted and st.session_state.interrupt_data:
    data = st.session_state.interrupt_data

    st.warning("🛑 Agent 执行已暂停，等待人工审核")

    with st.container(border=True):
        st.markdown("**审核内容**")
        st.markdown(f"问题：{data.get('question', 'N/A')}")
        st.markdown(f"生成回答：\n> {data.get('answer', 'N/A')[:300]}...")
        st.markdown(f"触发原因：{data.get('reasoning', 'N/A')}")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ 通过（信任回答）", type="primary", use_container_width=True):
                with st.spinner("恢复执行..."):
                    answer, sources, is_interrupted, extra = assistant.resume({"action": "approve"})
                    st.session_state.interrupted = is_interrupted
                    st.session_state.interrupt_data = extra if is_interrupted else None
                    if not is_interrupted:
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "sources": sources,
                            "reasoning": "[Human] 人工审核通过",
                            "badges": ["人工审核"]
                        })
                    st.rerun()

        with col2:
            if st.button("🔄 重试（重写查询）", use_container_width=True):
                with st.spinner("恢复执行..."):
                    answer, sources, is_interrupted, extra = assistant.resume({"action": "retry"})
                    st.session_state.interrupted = is_interrupted
                    st.session_state.interrupt_data = extra if is_interrupted else None
                    if not is_interrupted:
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "sources": sources,
                            "reasoning": "[Human] 要求重写查询后重试",
                            "badges": ["人工审核", "查询重写"]
                        })
                    st.rerun()

        with col3:
            if st.button("❌ 拒绝（退回）", use_container_width=True):
                with st.spinner("恢复执行..."):
                    answer, sources, is_interrupted, extra = assistant.resume({"action": "reject"})
                    st.session_state.interrupted = is_interrupted
                    st.session_state.interrupt_data = extra if is_interrupted else None
                    if not is_interrupted:
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "sources": sources,
                            "reasoning": "[Human] 人工拒绝",
                            "badges": ["人工审核"]
                        })
                    st.rerun()

    st.divider()

# ==================== 渲染历史消息 ====================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        # 显示徽章
        if msg.get("badges"):
            badges_html = " ".join([
                f'<span class="agent-badge badge-{b.lower().replace(" ", "-")}">{b}</span>'
                for b in msg["badges"]
            ])
            st.markdown(badges_html, unsafe_allow_html=True)

        st.markdown(msg["content"])

        # 图表展示
        if msg.get("chart_path") and os.path.exists(msg["chart_path"]):
            st.image(msg["chart_path"], caption="📊 Agent 生成的数据图表")

        # 引用来源
        if msg.get("sources"):
            with st.expander("📎 查看引用来源"):
                for s in msg["sources"]:
                    st.markdown(f"**{s['title']}**")
                    st.caption(f"> {s['snippet']}")

        # 思考过程
        if show_reasoning and msg.get("reasoning"):
            with st.expander("🧠 Agent 思考过程"):
                st.markdown(f'<div class="reasoning-box">{msg["reasoning"].replace(chr(10), "<br>")}</div>', 
                           unsafe_allow_html=True)

# ==================== 对话交互 ====================
if not st.session_state.interrupted:
    if question := st.chat_input("请输入您的问题..."):
        # 用户消息
        st.chat_message("user").markdown(question)
        st.session_state.messages.append({"role": "user", "content": question})

        # 助手回答
        with st.chat_message("assistant"):
            with st.spinner("Agent 正在思考、规划并检索资料..."):
                try:
                    answer, sources, is_interrupted, extra = assistant.ask(question)

                    if is_interrupted:
                        # HITL 中断：保存状态，展示审核界面
                        st.session_state.interrupted = True
                        st.session_state.interrupt_data = extra
                        st.warning("🛑 检测到潜在幻觉，Agent 已暂停等待人工审核")
                        st.rerun()
                    else:
                        # 正常完成
                        badges = []
                        if extra.get("chart_path"):
                            badges.append("图表Agent")

                        msg_data = {
                            "role": "assistant",
                            "content": answer,
                            "sources": sources,
                            "reasoning": "Agent 正常完成",
                            "badges": badges,
                        }

                        # 如果有图表，复制到可访问路径
                        if extra.get("chart_path") and os.path.exists(extra["chart_path"]):
                            import shutil
                            dest = f"/tmp/chart_display_{os.path.basename(extra['chart_path'])}"
                            shutil.copy(extra["chart_path"], dest)
                            msg_data["chart_path"] = dest
                            st.image(dest, caption="📊 Agent 生成的数据图表")

                        st.session_state.messages.append(msg_data)
                        st.markdown(answer)

                        if sources:
                            with st.expander("📎 查看引用来源"):
                                for s in sources:
                                    st.markdown(f"**{s['title']}**")
                                    st.caption(f"> {s['snippet']}")

                except Exception as e:
                    st.error(f"❌ 出错了: {e}")
                    import traceback
                    st.caption(f"```\n{traceback.format_exc()[:500]}\n```")