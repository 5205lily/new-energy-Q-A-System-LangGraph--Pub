"""
Checkpointer 持久化工厂（修复版）
解决 SqliteSaver.from_conn_string() 返回 _GeneratorContextManager 的问题
"""
import os
from typing import Optional


def get_checkpointer(backend: Optional[str] = None):
    """
    根据环境变量或参数创建 checkpointer
    返回 BaseCheckpointSaver 实例（不是上下文管理器）
    """
    backend = backend or os.getenv("CHECKPOINTER_BACKEND", "memory").lower()

    if backend == "memory":
        # LangGraph 新版使用 InMemorySaver
        try:
            from langgraph.checkpoint.memory import InMemorySaver
            print("[Checkpointer] 使用 InMemorySaver（内存，重启丢失）")
            return InMemorySaver()
        except ImportError:
            # 兼容旧版
            from langgraph.checkpoint.memory import MemorySaver
            print("[Checkpointer] 使用 MemorySaver（内存，重启丢失）")
            return MemorySaver()

    elif backend == "sqlite":
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver

        db_path = os.getenv("SQLITE_PATH", "./checkpoints.db")
        db_path = os.path.abspath(db_path)

        # 确保目录存在
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        # 直接创建 sqlite3 连接，避免 from_conn_string 返回上下文管理器
        conn = sqlite3.connect(db_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)

        print(f"[Checkpointer] 使用 SqliteSaver（文件: {db_path}）")
        return checkpointer

    elif backend == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver
        conn_string = os.getenv(
            "POSTGRES_URL",
            "postgresql://user:password@localhost:5432/agent_db"
        )
        print(f"[Checkpointer] 使用 PostgresSaver（生产推荐）")
        # PostgresSaver.from_conn_string 也可能返回上下文管理器，使用连接池方式
        import psycopg
        conn = psycopg.connect(conn_string)
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()
        return checkpointer

    elif backend == "redis":
        from langgraph.checkpoint.redis import RedisSaver
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        print(f"[Checkpointer] 使用 RedisSaver")
        # RedisSaver 通常直接实例化
        return RedisSaver.from_conn_string(redis_url)

    else:
        raise ValueError(f"不支持的 checkpointer 后端: {backend}")


def get_thread_config(thread_id: Optional[str] = None, user_id: Optional[str] = None):
    """生成 LangGraph 运行配置"""
    import uuid
    thread_id = thread_id or str(uuid.uuid4())

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    if user_id:
        config["configurable"]["user_id"] = user_id

    return config