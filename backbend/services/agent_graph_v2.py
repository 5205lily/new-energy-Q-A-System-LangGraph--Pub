"""
LangGraph Agent v2.0
扩展特性：
  1. LangSmith 自动追踪（零代码配置）
  2. Human-in-the-Loop：幻觉检测失败时中断等待人工审核
  3. 多 Agent 协作：计算 Agent + 图表 Agent
  4. Checkpointer 持久化：支持断点续跑、时间穿越
"""
from typing import TypedDict, Annotated, List, Optional
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
import os
import json
import re
import io
import sys
import uuid
from contextlib import redirect_stdout

from core.vectorstore import get_vectorstore
from services.rag_service import RAGAssistant
from services.checkpointer_factory import get_checkpointer, get_thread_config


# ==================== 状态定义（扩展版）====================
class AgentState(TypedDict):
    question: str
    original_question: str
    messages: Annotated[List[BaseMessage], add_messages]
    documents: List[Document]
    filtered_docs: List[Document]
    generation: str
    sources_info: List[dict]
    query_rewrite_count: int
    guardrail_passed: bool
    needs_retrieval: bool
    reasoning: str
    # v2.0 新增字段
    required_tools: List[str]          # orchestrator 决定调用的工具
    chart_path: Optional[str]          # 图表 Agent 生成的图片路径
    review_result: Optional[str]       # HITL 审核结果
    thread_id: str                     # 会话ID，用于持久化


# ==================== JSON 解析工具 ====================
def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r'(\{.*?\})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法提取 JSON: {text[:200]}")


# ==================== 节点实现 ====================
class AgentNodes:
    MAX_REWRITE = 2

    def __init__(self, provider: str = "deepseek"):
        self.assistant = RAGAssistant(provider=provider)
        self.llm = self.assistant.llm
        self.retriever = get_vectorstore().as_retriever(search_kwargs={"k": 5})

    def _format_history(self, messages: List[BaseMessage], rounds: int = 3) -> str:
        if not messages:
            return "无"
        lines = []
        for m in messages[-rounds * 2:]:
            role = "用户" if isinstance(m, HumanMessage) else "助手"
            lines.append(f"{role}：{m.content}")
        return "\n".join(lines)

    # ---------- 1. Guardrail ----------
    def guardrail_node(self, state: AgentState) -> dict:
        prompt = (
            "你是新能源运维系统的安全守卫。\n"
            "判断以下问题是否属于新能源运维领域（风电、光伏、储能、变电站运维等），"
            "且无不安全内容。\n\n"
            f"问题：{state['question']}\n\n"
            '请严格按以下 JSON 格式输出：\n'
            '{"is_safe": true, "reason": "理由"}'
        )
        response = self.llm.invoke(prompt)
        try:
            result = extract_json(response.content)
            is_safe = result.get("is_safe", False)
            reason = result.get("reason", "")
        except Exception:
            is_safe, reason = True, "解析失败，默认放行"

        return {
            "guardrail_passed": bool(is_safe),
            "reasoning": f"[Guardrail] {'通过' if is_safe else '拒绝'}: {reason}"
        }

    # ---------- 2. Planner ----------
    def planner_node(self, state: AgentState) -> dict:
        if not state["guardrail_passed"]:
            return {"needs_retrieval": False}

        history_text = self._format_history(state.get("messages", []))
        prompt = (
            "你是新能源运维专家。判断回答以下问题是否需要查阅文档资料。\n\n"
            f"历史对话：\n{history_text}\n\n"
            f"当前问题：{state['question']}\n\n"
            "如果问题是闲聊、打招呼、或仅凭常识就能回答，则不需要检索。\n"
            "如果问题涉及具体设备参数、运维规程、故障处理等，需要检索。\n\n"
            '请严格按以下 JSON 格式输出：\n'
            '{"needs_retrieval": true, "reasoning": "理由"}'
        )
        response = self.llm.invoke(prompt)
        try:
            result = extract_json(response.content)
            needs = result.get("needs_retrieval", True)
            reasoning = result.get("reasoning", "")
        except Exception:
            needs, reasoning = True, "解析失败，默认检索"

        return {
            "needs_retrieval": bool(needs),
            "reasoning": state.get("reasoning", "") + f"\n[Planner] {reasoning}"
        }

    # ---------- 3. Orchestrator：多 Agent 调度 ----------
    def orchestrator_node(self, state: AgentState) -> dict:
        """分析用户需求，决定调用哪些子 Agent/工具"""
        if not state["needs_retrieval"]:
            return {"required_tools": ["direct"]}

        prompt = (
            "分析以下新能源运维问题，判断需要调用哪些能力：\n"
            "- retrieve: 需要从文档库检索技术资料\n"
            "- calculate: 需要进行数值计算、公式推导、性能指标换算\n"  
            "- chart: 需要生成数据可视化图表（如功率曲线、效率对比图）\n"
            "- direct: 可以直接回答（无需任何工具）\n\n"
            f"问题：{state['question']}\n\n"
            "请严格按以下 JSON 格式输出（tools 是数组）：\n"
            '{"tools": ["retrieve"], "reasoning": "分析理由"}'
        )
        response = self.llm.invoke(prompt)
        try:
            result = extract_json(response.content)
            tools = result.get("tools", ["retrieve"])
            reasoning = result.get("reasoning", "")
        except Exception:
            tools, reasoning = ["retrieve"], "解析失败，默认检索"

        return {
            "required_tools": tools,
            "reasoning": state.get("reasoning", "") + f"\n[Orchestrator] 调度 {tools}: {reasoning}"
        }

    # ---------- 4. Retrieve ----------
    def retrieve_node(self, state: AgentState) -> dict:
        docs = self.retriever.invoke(state["question"])
        return {
            "documents": docs,
            "reasoning": state.get("reasoning", "") + f"\n[Retrieve] 召回 {len(docs)} 篇文档"
        }

    # ---------- 5. Calc Agent：计算 Agent ----------
    def calc_agent_node(self, state: AgentState) -> dict:
        """执行安全数值计算，结果作为文档注入"""
        question = state["question"]

        prompt = (
            "根据以下新能源运维问题，生成 Python 计算代码。\n"
            "只输出代码块（包含必要的 import），不要解释。\n"
            "代码最后必须将结果赋值给变量 `result`。\n\n"
            f"问题：{question}\n\n"
            "示例输出格式：\n"
            "```python\n"
            "# 计算风机年发电量\ncapacity = 2.5  # MW\n"
            "capacity_factor = 0.35\n"
            "hours_per_year = 8760\n"
            "result = capacity * capacity_factor * hours_per_year  # MWh\n"
            "```"
        )
        response = self.llm.invoke(prompt)
        code = response.content.strip()
        code = code.replace("```python", "").replace("```", "").strip()

        # 安全执行：限制 builtins
        safe_globals = {
            "__builtins__": {
                "abs": abs, "round": round, "max": max, "min": min,
                "sum": sum, "len": len, "range": range, "enumerate": enumerate,
                "zip": zip, "float": float, "int": int, "str": str,
                "print": lambda *args: None,  # 静默 print
            }
        }
        safe_locals = {}

        output_buffer = io.StringIO()
        try:
            with redirect_stdout(output_buffer):
                exec(code, safe_globals, safe_locals)
            calc_result = safe_locals.get("result", "计算完成但未定义 result")
            status = "成功"
        except Exception as e:
            calc_result = f"计算错误: {str(e)}"
            status = "失败"

        # 将计算结果封装为 Document 注入知识流
        calc_doc = Document(
            page_content=(
                f"【计算 Agent 结果 - {status}】\n"
                f"问题：{question}\n"
                f"计算结果：{calc_result}\n"
                f"计算代码：\n{code}"
            ),
            metadata={"source": "计算Agent", "type": "calculation", "status": status}
        )

        existing_docs = state.get("documents", [])
        return {
            "documents": existing_docs + [calc_doc],
            "reasoning": state.get("reasoning", "") + f"\n[CalcAgent] {status}: {calc_result}"
        }

    # ---------- 6. Chart Agent：图表 Agent ----------
    def chart_agent_node(self, state: AgentState) -> dict:
        """生成 matplotlib 图表，保存到本地"""
        question = state["question"]
        thread_id = state.get("thread_id", str(uuid.uuid4()))
        chart_path = f"/tmp/chart_{thread_id}.png"

        prompt = (
            "根据以下新能源运维问题，生成 matplotlib 图表代码。\n"
            f"图表必须保存到路径：{chart_path}\n"
            "代码必须包含 `plt.savefig()` 且使用中文友好设置。\n"
            "只输出代码块，不要解释。\n\n"
            f"问题：{question}\n\n"
            "注意：\n"
            "1. 使用 `plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']`\n"
            "2. 使用 `plt.rcParams['axes.unicode_minus'] = False`\n"
            "3. 最后必须执行 `plt.savefig('{chart_path}', dpi=150, bbox_inches='tight')`\n"
            "4. 然后 `plt.close()`"
        ).format(chart_path=chart_path)

        response = self.llm.invoke(prompt)
        code = response.content.strip()
        code = code.replace("```python", "").replace("```", "").strip()

        # 安全执行图表代码
        safe_globals = {
            "__builtins__": {
                "abs": abs, "round": round, "max": max, "min": min,
                "sum": sum, "len": len, "range": range, "enumerate": enumerate,
                "zip": zip, "float": float, "int": int, "str": str,
            },
            "__import__": __import__,
        }

        try:
            exec(code, safe_globals, {})
            status = "成功" if os.path.exists(chart_path) else "失败（文件未生成）"
        except Exception as e:
            status = f"失败: {str(e)}"
            chart_path = None

        return {
            "chart_path": chart_path,
            "reasoning": state.get("reasoning", "") + f"\n[ChartAgent] {status}"
        }

    # ---------- 7. Grade ----------
    def grade_node(self, state: AgentState) -> dict:
        question = state["question"]
        docs = state["documents"]
        filtered = []

        for doc in docs:
            prompt = (
                "评估以下文档是否与问题相关。\n\n"
                f"问题：{question}\n\n"
                f"文档片段：\n{doc.page_content[:800]}\n\n"
                "文档是否包含回答问题所需的信息？只回答 yes 或 no。\n"
                '请严格按以下 JSON 格式输出：\n'
                '{"score": "yes"}'
            )
            response = self.llm.invoke(prompt)
            try:
                result = extract_json(response.content)
                score = result.get("score", "no")
            except Exception:
                score = "no"

            if str(score).lower() == "yes":
                filtered.append(doc)

        sources_info = []
        for i, doc in enumerate(filtered, 1):
            source_path = doc.metadata.get("source", "未知")
            page = doc.metadata.get("page")
            page_str = f" (第{page + 1}页)" if page is not None else ""
            sources_info.append({
                "title": f"【来源{i}】{os.path.basename(source_path)}{page_str}",
                "snippet": doc.page_content[:150] + "...",
            })

        return {
            "filtered_docs": filtered,
            "sources_info": sources_info,
            "reasoning": state.get("reasoning", "") + f"\n[Grade] {len(docs)} 篇 → 保留 {len(filtered)} 篇"
        }

    # ---------- 8. Rewrite ----------
    def rewrite_node(self, state: AgentState) -> dict:
        prompt = (
            "原始查询没有检索到足够的相关资料。请重写查询，"
            "使其更具体、包含更多专业关键词，以提高检索效果。\n\n"
            f"原始查询：{state['question']}\n\n"
            "请只输出重写后的查询，不要解释。"
        )
        response = self.llm.invoke(prompt)
        rewritten = response.content.strip().replace('"', "").replace("'", "")
        count = state.get("query_rewrite_count", 0)

        return {
            "question": rewritten,
            "query_rewrite_count": count + 1,
            "reasoning": state.get("reasoning", "") + f"\n[Rewrite] '{state['question']}' → '{rewritten}'"
        }

    # ---------- 9. Generate ----------
    def generate_node(self, state: AgentState) -> dict:
        docs = state["filtered_docs"]
        question = state["question"]
        chart_path = state.get("chart_path")

        context_parts = []
        for i, doc in enumerate(docs, 1):
            context_parts.append(f"【来源{i}】\n{doc.page_content}")
        context = "\n\n".join(context_parts)

        history_text = self._format_history(state.get("messages", []))

        chart_hint = ""
        if chart_path and os.path.exists(chart_path):
            chart_hint = f"\n【系统提示】已生成数据图表，路径：{chart_path}，可在回答中提及。\n"

        prompt = (
            "你是新能源运维专家。根据【参考资料】回答【问题】。\n"
            '如果资料不足以回答，请明确说明"根据现有资料无法回答"。\n\n'
            f"【历史对话】\n{history_text}\n\n"
            f"【参考资料】\n{context}\n\n"
            f"【问题】\n{question}\n"
            f"{chart_hint}\n"
            "要求：\n"
            "1. 引用标注使用 [来源1]、[来源2] 等格式\n"
            "2. 回答简洁专业\n"
            "3. 不编造资料中未提及的信息\n"
            "4. 如有图表生成，告知用户图表已准备就绪"
        )
        response = self.llm.invoke(prompt)

        return {
            "generation": response.content,
            "reasoning": state.get("reasoning", "") + "\n[Generate] 已生成回答"
        }

    # ---------- 10. Hallucination + HITL ----------
    def hallucination_node(self, state: AgentState) -> dict:
        """幻觉检测 + Human-in-the-Loop 中断"""
        docs = state["filtered_docs"]
        generation = state["generation"]

        if not docs:
            # 无文档时跳过检测
            return {"review_result": "auto_pass"}

        docs_text = "\n".join([d.page_content[:500] for d in docs])
        prompt = (
            "评估以下回答是否完全基于提供的资料，没有编造信息。\n\n"
            f"资料内容：\n{docs_text}\n\n"
            f"生成的回答：\n{generation}\n\n"
            "回答是否完全基于资料？只回答 yes 或 no。\n"
            '请严格按以下 JSON 格式输出：\n'
            '{"is_grounded": true}'
        )
        response = self.llm.invoke(prompt)
        try:
            result = extract_json(response.content)
            is_grounded = result.get("is_grounded", True)
        except Exception:
            is_grounded = True

        if is_grounded:
            return {
                "review_result": "auto_pass",
                "reasoning": state.get("reasoning", "") + "\n[Hallucination] 自动通过"
            }

        # ===== Human-in-the-Loop 中断 =====
        # 暂停执行，等待人工审核（通过 Command(resume=...) 恢复）
        decision = interrupt({
            "type": "hallucination_review",
            "question": state["original_question"],
            "answer": generation,
            "sources": state.get("sources_info", []),
            "reasoning": "检测到回答可能包含资料中未提及的信息",
            "actions": [
                {"action": "approve", "label": "通过（信任回答）"},
                {"action": "retry", "label": "重试（重写查询再生成）"},
                {"action": "reject", "label": "拒绝（退回并提示用户）"}
            ]
        })

        # decision 是用户通过 Command(resume=decision) 传入的
        action = decision.get("action", "approve") if isinstance(decision, dict) else "approve"

        if action == "approve":
            return {
                "review_result": "human_approved",
                "reasoning": state.get("reasoning", "") + "\n[Human] 人工审核通过"
            }
        elif action == "retry":
            return {
                "review_result": "human_retry",
                "query_rewrite_count": state.get("query_rewrite_count", 0) + 1,
                "reasoning": state.get("reasoning", "") + "\n[Human] 要求重写查询重试"
            }
        else:  # reject
            return {
                "review_result": "human_rejected",
                "generation": (
                    "回答未通过人工审核，已撤回。\n"
                    "建议：\n"
                    "1. 尝试用更具体的关键词重新提问\n"
                    "2. 上传相关运维手册或技术文档补充知识库\n"
                    "3. 联系现场工程师获取支持"
                ),
                "sources_info": [],
                "reasoning": state.get("reasoning", "") + "\n[Human] 人工拒绝"
            }

    # ---------- 11. Direct Answer ----------
    def direct_answer_node(self, state: AgentState) -> dict:
        history_text = self._format_history(state.get("messages", []))
        prompt = (
            "你是新能源运维专家。请直接回答用户问题（无需检索资料）。\n\n"
            f"【历史对话】\n{history_text}\n\n"
            f"【问题】\n{state['question']}\n\n"
            "请友好、专业地回答。"
        )
        response = self.llm.invoke(prompt)

        return {
            "generation": response.content,
            "sources_info": [],
            "reasoning": state.get("reasoning", "") + "\n[Direct] 直接回答（无需检索）"
        }

    # ---------- 12. Fallback ----------
    def fallback_node(self, state: AgentState) -> dict:
        return {
            "generation": (
                "根据现有资料无法回答您的问题。建议：\n"
                "1. 尝试用更具体的关键词描述问题\n"
                "2. 上传相关运维手册或技术文档\n"
                "3. 联系现场工程师获取支持"
            ),
            "sources_info": [],
            "reasoning": state.get("reasoning", "") + "\n[Fallback] 检索失败，优雅降级"
        }


# ==================== 条件边路由 ====================
def route_after_guardrail(state: AgentState) -> str:
    return "planner" if state["guardrail_passed"] else "fallback"

def route_after_planner(state: AgentState) -> str:
    return "orchestrator" if state["needs_retrieval"] else "direct_answer"

def route_after_orchestrator(state: AgentState) -> str:
    """多 Agent 调度路由"""
    tools = state.get("required_tools", ["retrieve"])

    # 优先级：chart > calculate > retrieve > direct
    if "chart" in tools:
        return "chart_agent"
    elif "calculate" in tools:
        return "calc_agent"
    elif "retrieve" in tools:
        return "retrieve"
    return "direct_answer"

def route_after_grade(state: AgentState) -> str:
    filtered = state.get("filtered_docs", [])
    rewrite_count = state.get("query_rewrite_count", 0)

    if len(filtered) > 0:
        return "generate"
    elif rewrite_count < AgentNodes.MAX_REWRITE:
        return "rewrite"
    else:
        return "fallback"

def route_after_hallucination(state: AgentState) -> str:
    """HITL 后路由"""
    review = state.get("review_result", "auto_pass")

    if review == "human_retry":
        return "rewrite"
    elif review == "human_rejected":
        return "fallback"
    return END


# ==================== 构建图 ====================
def build_agent_graph(provider: str = "deepseek", checkpointer=None):
    """
    编译完整 Agent 状态图

    Args:
        provider: LLM 提供商
        checkpointer: 持久化后端（None 则使用内存）
    """
    nodes = AgentNodes(provider)

    workflow = StateGraph(AgentState)

    # 注册所有节点
    workflow.add_node("guardrail", nodes.guardrail_node)
    workflow.add_node("planner", nodes.planner_node)
    workflow.add_node("orchestrator", nodes.orchestrator_node)
    workflow.add_node("retrieve", nodes.retrieve_node)
    workflow.add_node("calc_agent", nodes.calc_agent_node)
    workflow.add_node("chart_agent", nodes.chart_agent_node)
    workflow.add_node("grade", nodes.grade_node)
    workflow.add_node("rewrite", nodes.rewrite_node)
    workflow.add_node("generate", nodes.generate_node)
    workflow.add_node("hallucination", nodes.hallucination_node)
    workflow.add_node("direct_answer", nodes.direct_answer_node)
    workflow.add_node("fallback", nodes.fallback_node)

    # 构建边
    workflow.add_edge(START, "guardrail")
    workflow.add_conditional_edges("guardrail", route_after_guardrail, {
        "planner": "planner",
        "fallback": "fallback"
    })
    workflow.add_conditional_edges("planner", route_after_planner, {
        "orchestrator": "orchestrator",
        "direct_answer": "direct_answer"
    })
    workflow.add_conditional_edges("orchestrator", route_after_orchestrator, {
        "retrieve": "retrieve",
        "calc_agent": "calc_agent",
        "chart_agent": "chart_agent",
        "direct_answer": "direct_answer"
    })
    # 计算/图表 Agent 完成后进入检索（补充资料）或直接生成
    workflow.add_edge("calc_agent", "retrieve")
    workflow.add_edge("chart_agent", "retrieve")
    workflow.add_edge("retrieve", "grade")
    workflow.add_conditional_edges("grade", route_after_grade, {
        "generate": "generate",
        "rewrite": "rewrite",
        "fallback": "fallback"
    })
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("generate", "hallucination")
    workflow.add_conditional_edges("hallucination", route_after_hallucination, {
        END: END,
        "rewrite": "rewrite",
        "fallback": "fallback"
    })
    workflow.add_edge("direct_answer", END)
    workflow.add_edge("fallback", END)

    # 编译：传入 checkpointer 启用持久化 + LangSmith 自动追踪
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)


# ==================== 对外接口 ====================
class AgenticRAGAssistantV2:
    """
    v2.0 Agent 包装器
    特性：持久化、HITL、多 Agent、LangSmith 追踪
    """

    def __init__(self, provider: str = "deepseek", checkpointer=None, thread_id: Optional[str] = None):
        self.provider = provider
        self.checkpointer = checkpointer or get_checkpointer()
        self.graph = build_agent_graph(provider, self.checkpointer)
        self.thread_id = thread_id or str(uuid.uuid4())
        self.history = []

    def ask(self, question: str, resume_command: Optional[Command] = None):
        """
        执行一次 Agent 问答

        Args:
            question: 用户问题（首次调用）
            resume_command: Command(resume={...}) 用于恢复 HITL 中断

        Returns:
            (answer, sources_info, is_interrupted, interrupt_data)
        """
        config = get_thread_config(self.thread_id)

        # 构建历史消息
        messages = []
        for h in self.history[-3:]:
            messages.append(HumanMessage(content=h["question"]))
            messages.append(AIMessage(content=h["answer"]))

        if resume_command:
            # 恢复 HITL 中断
            final_state = self.graph.invoke(resume_command, config=config)
        else:
            # 新提问
            initial_state = {
                "question": question,
                "original_question": question,
                "messages": messages,
                "documents": [],
                "filtered_docs": [],
                "generation": "",
                "sources_info": [],
                "query_rewrite_count": 0,
                "guardrail_passed": False,
                "needs_retrieval": True,
                "reasoning": "",
                "required_tools": ["retrieve"],
                "chart_path": None,
                "review_result": None,
                "thread_id": self.thread_id,
            }
            final_state = self.graph.invoke(initial_state, config=config)

        # 检测是否被中断（HITL）
        if "__interrupt__" in final_state:
            interrupt_data = final_state["__interrupt__"][0].value
            return "", [], True, interrupt_data

        # 正常完成
        answer = final_state.get("generation", "")
        sources = final_state.get("sources_info", [])
        chart_path = final_state.get("chart_path")

        self.history.append({"question": question, "answer": answer})

        return answer, sources, False, {"chart_path": chart_path}

    def resume(self, decision: dict):
        """恢复 HITL 中断（供前端调用）"""
        return self.ask("", resume_command=Command(resume=decision))

    def clear_history(self):
        self.history = []
        # 可选：同时清除持久化状态
        # self.checkpointer.delete_thread(self.thread_id)

    def get_state_history(self):
        """获取当前 thread 的执行历史（时间穿越）"""
        config = get_thread_config(self.thread_id)
        return list(self.graph.get_state_history(config))