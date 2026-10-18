from services.rag_service import RAGAssistant


if __name__ == "__main__":
    print("🤖 新能源知识助手已启动 (输入 'exit' 退出)")
    assistant = RAGAssistant(provider="deepseek")

    while True:
        question = input("\n💬 请输入您的问题: ").strip()
        if question.lower() in ['exit', 'quit', 'q']:
            break
        if question == "clear":
            assistant.clear_history()
            print("🧹 历史已清空")
            continue

        try:
            answer, sources = assistant.ask(question)
            print(f"\n📝 回答: {answer}")
            if sources:
                print("\n📎 引用来源:")
                for s in sources:
                    print(f"   {s['title']}")
        except Exception as e:
            print(f"❌ 出错了: {e}")