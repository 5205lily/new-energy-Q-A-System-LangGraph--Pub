"""
LangGraph Agent 核心定义（DeepSeek 兼容版）
修复：移除 with_structured_output，改用 Prompt 强制 JSON + 正则解析
"""
from typing import TypedDict, Annotated, List
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
import os
import json
import re

from core.vectorstore import get_vectorstore
from services.rag_service import RAGAssistant

# ==================== 状态定义 ====================
class AgentState(TypedDict):
    """Agent 共享状态——所有节点读写同一个状态对象"""
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


# ==================== JSON 解析工具 ====================
def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON 块并解析"""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{.*?\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从模型输出中提取 JSON: {text[:200]}")


# ==================== 节点实现 ====================
class AgentNodes:
    MAX_REWRITE = 2

    def __init__(self, provider: str = "deepseek"):
        self.assistant = RAGAssistant(provider=provider)
        self.llm = self.assistant.llm
        self.retriever = get_vectorstore().as_retriever(search_kwargs={"k": 5})

    def guardrail_node(self, state: AgentState) -> dict:
        guardrail_prompt = """你是新能源运维系统的安全守卫。
判断以下问题是否属于新能源运维领域（风电、光伏、储能、变电站运维等），且无不安全内容。

问题：{question}

请严格按以下 JSON 格式输出，不要添加任何其他文字：
{{"is_safe": true, "reason": "理由"}}"""

        response = self.llm.invoke(guardrail_prompt.format(question=state["question"]))
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

    def planner_node(self, state: AgentState) -> dict:
        if not state["guardrail_passed"]:
            return {"needs_retrieval": False}

        planner_prompt = """你是新能源运维专家。判断回答以下问题是否需要查阅文档资料。

历史对话：
{history}

当前问题：{question}

如果问题是闲聊、打招呼、或仅凭常识就能回答，则不需要检索。
如果问题涉及具体设备参数、运维规程、故障处理等，需要检索。

请严格按以下 JSON 格式输出，不要添加任何其他文字：
{{"needs_retrieval": true, "reasoning": "理由"}}"""

        history = state.get("messages", [])
        history_text = "\n".join([f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {m.content}" 
                                    for m in history[-4:]])

        response = self.llm.invoke(planner_prompt.format(
            question=state["question"], 
            history=history_text or "无"
        ))

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

    def retrieve_node(self, state: AgentState) -> dict:
        question = state["question"]
        docs = self.retriever.invoke(question)
        return {
            "documents": docs,
            "reasoning": state.get("reasoning", "") + f"\n[Retrieve] 召回 {len(docs)} 篇文档"
        }

    def grade_node(self, state: AgentState) -> dict:
        question = state["question"]
        docs = state["documents"]

        grade_prompt = """评估以下文档是否与问题相关。

问题：{question}

文档片段：
{document}

文档是否包含回答问题所需的信息？只回答 yes 或 no。
请严格按以下 JSON 格式输出：
{{"score": "yes"}}"""

        filtered = []
        for doc in docs:
            response = self.llm.invoke(
                grade_prompt.format(question=question, document=doc.page_content[:800])
            )
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
            "reasoning": state.get("reasoning", "") + 
                        f"\n[Grade] {len(docs)} 篇 → 保留 {len(filtered)} 篇"
        }

    def rewrite_node(self, state: AgentState) -> dict:
        rewrite_prompt = """原始查询没有检索到足够的相关资料。请重写查询，使其更具体、包含更多专业关键词，以提高检索效果。

原始查询：{question}

请只输出重写后的查询，不要解释。"""

        response = self.llm.invoke(rewrite_prompt.format(question=state["question"]))
        # 修复：正确替换双引号，使用单引号括起替换目标
        rewritten = response.content.strip().replace('"', '').replace("'", "")
        count = state.get("query_rewrite_count", 0)

        return {
            "question": rewritten,
            "query_rewrite_count": count + 1,
            "reasoning": state.get("reasoning", "") + 
                        f"\n[Rewrite] '{state['question']}' → '{rewritten}'"
        }

    def generate_node(self, state: AgentState) -> dict:
        docs = state["filtered_docs"]
        question = state["question"]

        context_parts = []
        for i, doc in enumerate(docs, 1):
            context_parts.append(f"【来源{i}】\n{doc.page_content}")
        context = "\n\n".join(context_parts)

        history_msgs = state.get("messages", [])
        history_text = "\n".join([f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {m.content}" 
                                    for m in history_msgs[-3:]])

        generate_prompt = """你是新能源运维专家。根据【参考资料】回答【问题】。
如果资料不足以回答，请明确说明"根据现有资料无法回答"。

【历史对话】
{history}

【参考资料】
{context}

【问题】
{question}

要求：
1. 引用标注使用 [来源1]、[来源2] 等格式
2. 回答简洁专业
3. 不编造资料中未提及的信息"""

        response = self.llm.invoke(generate_prompt.format(
            context=context,
            question=question,
            history=history_text or "无"
        ))

        return {
            "generation": response.content,
            "reasoning": state.get("reasoning", "") + "\n[Generate] 已生成回答"
        }

    def hallucination_node(self, state: AgentState) -> dict:
        docs = state["filtered_docs"]
        generation = state["generation"]

        hallucination_prompt = """评估以下回答是否完全基于提供的资料，没有编造信息。

资料内容：
{documents}

生成的回答：
{generation}

回答是否完全基于资料？只回答 yes 或 no。
请严格按以下 JSON 格式输出：
{{"is_grounded": true}}"""

        docs_text = "\n".join([d.page_content[:500] for d in docs])
        response = self.llm.invoke(
            hallucination_prompt.format(documents=docs_text, generation=generation)
        )

        try:
            result = extract_json(response.content)
            is_grounded = result.get("is_grounded", True)
        except Exception:
            is_grounded = True

        return {
            "reasoning": state.get("reasoning", "") + 
                        f"\n[Hallucination] {'通过' if is_grounded else '检测到幻觉'}"
        }

    def direct_answer_node(self, state: AgentState) -> dict:
        history_msgs = state.get("messages", [])
        history_text = "\n".join([f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {m.content}" 
                                    for m in history_msgs[-3:]])

        prompt = """你是新能源运维专家。请直接回答用户问题（无需检索资料）。

【历史对话】
{history}

【问题】
{question}

请友好、专业地回答。"""

        response = self.llm.invoke(prompt.format(
            question=state["question"],
            history=history_text or "无"
        ))

        return {
            "generation": response.content,
            "sources_info": [],
            "reasoning": state.get("reasoning", "") + "\n[Direct] 直接回答（无需检索）"
        }

    def fallback_node(self, state: AgentState) -> dict:
        return {
            "generation": "根据现有资料无法回答您的问题。建议：\n1. 尝试用更具体的关键词描述问题\n2. 上传相关运维手册或技术文档\n3. 联系现场工程师获取支持",
            "sources_info": [],
            "reasoning": state.get("reasoning", "") + "\n[Fallback] 检索失败，优雅降级"
        }


# ==================== 条件边路由函数 ====================
def route_after_guardrail(state: AgentState) -> str:
    return "planner" if state["guardrail_passed"] else "fallback"

def route_after_planner(state: AgentState) -> str:
    return "retrieve" if state["needs_retrieval"] else "direct_answer"

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
    return END


# ==================== 构建图 ====================
def build_agent_graph(provider: str = "deepseek"):
    nodes = AgentNodes(provider)
    workflow = StateGraph(AgentState)

    workflow.add_node("guardrail", nodes.guardrail_node)
    workflow.add_node("planner", nodes.planner_node)
    workflow.add_node("retrieve", nodes.retrieve_node)
    workflow.add_node("grade", nodes.grade_node)
    workflow.add_node("rewrite", nodes.rewrite_node)
    workflow.add_node("generate", nodes.generate_node)
    workflow.add_node("hallucination", nodes.hallucination_node)
    workflow.add_node("direct_answer", nodes.direct_answer_node)
    workflow.add_node("fallback", nodes.fallback_node)

    workflow.add_edge(START, "guardrail")
    workflow.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {"planner": "planner", "fallback": "fallback"}
    )
    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {"retrieve": "retrieve", "direct_answer": "direct_answer"}
    )
    workflow.add_edge("retrieve", "grade")
    workflow.add_conditional_edges(
        "grade",
        route_after_grade,
        {"generate": "generate", "rewrite": "rewrite", "fallback": "fallback"}
    )
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("generate", "hallucination")
    workflow.add_conditional_edges(
        "hallucination",
        route_after_hallucination,
        {END: END, "rewrite": "rewrite"}   # 注意：这里 END 作为键和值都是合法的
    )
    workflow.add_edge("direct_answer", END)
    workflow.add_edge("fallback", END)

    return workflow.compile()


# ==================== 对外接口 ====================
class AgenticRAGAssistant:
    def __init__(self, provider: str = "deepseek"):
        self.provider = provider
        self.graph = build_agent_graph(provider)
        self.history = []

    def ask(self, question: str):
        messages = []
        for h in self.history[-3:]:
            messages.append(HumanMessage(content=h["question"]))
            messages.append(AIMessage(content=h["answer"]))

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
            "reasoning": ""
        }

        final_state = self.graph.invoke(initial_state)
        self.history.append({"question": question, "answer": final_state["generation"]})
        return final_state["generation"], final_state.get("sources_info", [])

    def clear_history(self):
        self.history = []