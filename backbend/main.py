"""
FastAPI 后端服务 - 新能源 Agent 知识助手 v2.0
提供 RESTful API + SSE 流式 + WebSocket + 静态文件托管
"""
import os
import sys
import json
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List, Any
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 下面再写 transformers / langchain 导入代码


# 将项目根目录加入路径（确保能导入 services）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.agent_graph_v2 import AgenticRAGAssistantV2
from services.checkpointer_factory import get_checkpointer, get_thread_config
from services.ingest_service import ingest_file, DATA_DIR

# ==================== 全局状态 ====================
assistants: dict[str, AgenticRAGAssistantV2] = {}
checkpointer = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载 checkpointer"""
    global checkpointer
    checkpointer = get_checkpointer()
    print(f"[Startup] Checkpointer loaded: {type(checkpointer).__name__}")
    yield
    print("[Shutdown] Cleaning up...")

app = FastAPI(
    title="新能源 Agent API",
    description="基于 LangGraph Agent 的 RAG 问答后端服务",
    version="2.0.0",
    lifespan=lifespan
)

# CORS：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Pydantic 模型 ====================
class ChatRequest(BaseModel):
    question: str = Field(..., description="用户问题")
    thread_id: Optional[str] = Field(None, description="会话ID，为空则创建新会话")
    provider: str = Field("deepseek", description="模型提供商")
    stream: bool = Field(False, description="是否流式输出")

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]
    thread_id: str
    reasoning: str
    chart_path: Optional[str] = None
    is_interrupted: bool = False
    interrupt_data: Optional[dict] = None

class ReviewRequest(BaseModel):
    thread_id: str
    action: str = Field(..., description="approve / retry / reject")

class UploadResponse(BaseModel):
    filename: str
    chunk_count: int
    page_count: int
    status: str


# ==================== 辅助函数 ====================
def get_or_create_assistant(thread_id: Optional[str], provider: str) -> AgenticRAGAssistantV2:
    """获取或创建 Assistant 实例"""
    key = f"{provider}:{thread_id or 'new'}"
    if key not in assistants:
        assistants[key] = AgenticRAGAssistantV2(
            provider=provider,
            checkpointer=checkpointer,
            thread_id=thread_id
        )
    return assistants[key]


# ==================== API 路由 ====================

@app.get("/")
async def root():
    return {"message": "新能源 Agent API v2.0", "status": "running", "docs": "/docs"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """普通问答接口（非流式）"""
    assistant = get_or_create_assistant(request.thread_id, request.provider)

    try:
        answer, sources, is_interrupted, extra = assistant.ask(request.question)

        return ChatResponse(
            answer=answer,
            sources=sources,
            thread_id=assistant.thread_id,
            reasoning=extra.get("reasoning", "") if isinstance(extra, dict) else "",
            chart_path=extra.get("chart_path") if isinstance(extra, dict) else None,
            is_interrupted=is_interrupted,
            interrupt_data=extra if is_interrupted else None
        )
    except Exception as e:
        import traceback
        print(f"[Error] /api/chat: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE 流式问答接口"""
    assistant = get_or_create_assistant(request.thread_id, request.provider)

    async def event_generator():
        try:
            # 发送开始标记
            yield f"data: {json.dumps({'type': 'start', 'thread_id': assistant.thread_id}, ensure_ascii=False)}\n\n"

            # 执行 Agent
            answer, sources, is_interrupted, extra = assistant.ask(request.question)

            # 分段输出回答（模拟打字机效果）
            chunk_size = 4
            for i in range(0, len(answer), chunk_size):
                chunk = answer[i:i+chunk_size]
                yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)

            # 发送结束标记
            end_data = {
                'type': 'end',
                'answer': answer,
                'sources': sources,
                'is_interrupted': is_interrupted,
                'chart_path': extra.get('chart_path') if isinstance(extra, dict) else None
            }
            yield f"data: {json.dumps(end_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/review", response_model=ChatResponse)
async def review(request: ReviewRequest):
    """HITL 人工审核接口"""
    # 查找匹配的 assistant（简化：遍历查找）
    assistant = None
    for key, inst in assistants.items():
        if inst.thread_id == request.thread_id:
            assistant = inst
            break

    if not assistant:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    try:
        answer, sources, is_interrupted, extra = assistant.resume({"action": request.action})

        return ChatResponse(
            answer=answer,
            sources=sources,
            thread_id=assistant.thread_id,
            reasoning="",
            chart_path=extra.get("chart_path") if isinstance(extra, dict) else None,
            is_interrupted=is_interrupted,
            interrupt_data=extra if is_interrupted else None
        )
    except Exception as e:
        import traceback
        print(f"[Error] /api/review: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """文档上传接口"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    allowed_ext = ('.pdf', '.doc', '.docx', '.txt')
    if not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(status_code=400, detail=f"仅支持 {allowed_ext} 格式")

    save_path = os.path.join(DATA_DIR, file.filename)

    try:
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)

        chunk_count, page_count = ingest_file(save_path)

        return UploadResponse(
            filename=file.filename,
            chunk_count=chunk_count,
            page_count=page_count,
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history/{thread_id}")
async def get_history(thread_id: str):
    """获取指定会话的历史检查点"""
    assistant = None
    for key, inst in assistants.items():
        if inst.thread_id == thread_id:
            assistant = inst
            break

    if not assistant:
        return {"history": [], "message": "会话不存在"}

    try:
        history = assistant.get_state_history()
        simplified = []
        for i, h in enumerate(history[:10]):
            simplified.append({
                "index": i,
                "question": h.values.get("question", "N/A")[:50] if hasattr(h, 'values') else "N/A",
                "node": h.next[0] if hasattr(h, 'next') and h.next else "END",
                "timestamp": str(h.created_at) if hasattr(h, 'created_at') else "N/A"
            })
        return {"history": simplified}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/history/{thread_id}")
async def clear_history(thread_id: str):
    """清空指定会话的历史"""
    keys_to_remove = []
    for key, inst in assistants.items():
        if inst.thread_id == thread_id:
            inst.clear_history()
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del assistants[key]

    return {"message": "历史已清空", "thread_id": thread_id}


# ==================== WebSocket 实时通信 ====================
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_message(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """WebSocket 实时聊天接口"""
    await manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            if msg_type == "chat":
                question = data.get("question", "")
                thread_id = data.get("thread_id")
                provider = data.get("provider", "deepseek")

                assistant = get_or_create_assistant(thread_id, provider)

                await websocket.send_json({
                    "type": "start",
                    "thread_id": assistant.thread_id
                })

                answer, sources, is_interrupted, extra = assistant.ask(question)

                if is_interrupted:
                    await websocket.send_json({
                        "type": "interrupt",
                        "data": extra,
                        "thread_id": assistant.thread_id
                    })
                else:
                    await websocket.send_json({
                        "type": "complete",
                        "answer": answer,
                        "sources": sources,
                        "thread_id": assistant.thread_id,
                        "chart_path": extra.get("chart_path") if isinstance(extra, dict) else None,
                        "reasoning": extra.get("reasoning", "") if isinstance(extra, dict) else ""
                    })

            elif msg_type == "review":
                thread_id = data.get("thread_id")
                action = data.get("action", "approve")

                assistant = None
                for key, inst in assistants.items():
                    if inst.thread_id == thread_id:
                        assistant = inst
                        break

                if assistant:
                    answer, sources, is_interrupted, extra = assistant.resume({"action": action})

                    if is_interrupted:
                        await websocket.send_json({
                            "type": "interrupt",
                            "data": extra,
                            "thread_id": thread_id
                        })
                    else:
                        await websocket.send_json({
                            "type": "complete",
                            "answer": answer,
                            "sources": sources,
                            "thread_id": thread_id,
                            "chart_path": extra.get("chart_path") if isinstance(extra, dict) else None
                        })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        manager.disconnect(client_id)


# ==================== 静态文件托管（生产环境）====================
# 检测 frontend/dist 是否存在，存在则托管
FRONTEND_DIST = os.path.join(PROJECT_ROOT, "..", "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    # 托管 assets 目录
    assets_path = os.path.join(FRONTEND_DIST, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    # 其他静态资源
    for subdir in ["images", "fonts", "img"]:
        sub_path = os.path.join(FRONTEND_DIST, subdir)
        if os.path.exists(sub_path):
            app.mount(f"/{subdir}", StaticFiles(directory=sub_path), name=subdir)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Vue SPA 路由：所有路径返回 index.html"""
        # API 路由优先，这里只处理非 API 路径
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            raise HTTPException(status_code=404, detail="Not Found")

        index_file = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"error": "Frontend not built. Run 'npm run build' in frontend/"}

    print(f"[Static] Frontend dist found at {FRONTEND_DIST}, serving static files")
else:
    print(f"[Static] Frontend dist not found at {FRONTEND_DIST}, API-only mode")


# ==================== 启动入口 ====================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )