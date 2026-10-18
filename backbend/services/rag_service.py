import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.vectorstore import get_vectorstore

load_dotenv()


class RAGAssistant:
    """RAG 问答助手：检索、多轮记忆、引用溯源、模型切换"""

    def __init__(self, provider: str = "deepseek"):
        self.provider = provider
        self.history = []  # 多轮对话历史（内存版，以后可接数据库）
        self.llm = self._get_llm(provider)
        self.retriever = get_vectorstore().as_retriever(search_kwargs={"k": 3})

    def _get_llm(self, provider: str):
        """LLM 工厂：DeepSeek / 本地 Ollama"""
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
            return ChatOpenAI(
                model="qwen2",
                openai_api_key="sk-no-key-required",
                openai_api_base="http://localhost:11434/v1",
                temperature=0.1,
            )
        else:
            raise ValueError(f"不支持的模型: {provider}")

    def _format_history(self, keep_rounds: int = 3):
        """格式化最近 N 轮历史"""
        if not self.history:
            return "无"
        lines = []
        for h in self.history[-keep_rounds:]:
            lines.append(f"用户：{h['question']}")
            lines.append(f"助手：{h['answer']}")
        return "\n".join(lines)

    def ask(self, question: str):
        """
        执行一次 RAG 问答
        返回: (answer: str, sources: list)
        """
        # 1. 语义检索
        docs = self.retriever.invoke(question)

        # 2. 构建带溯源的上下文
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

        # 3. 构建 Prompt（含多轮历史）
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
            history=self._format_history(),
        )

        # 4. 调用 LLM
        response = self.llm.invoke(messages)
        answer = response.content

        # 5. 保存历史
        self.history.append({"question": question, "answer": answer})

        return answer, sources_info

    def clear_history(self):
        """清空对话历史"""
        self.history = []