from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import ChatRequest, ChatResponse, RouteRequest, RouteResponse
from .agent import answer, route, TOOL_LABELS, initialize_mcp, shutdown_mcp
from .ingestion import ingest
from .config import DATA_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_mcp()
    yield
    await shutdown_mcp()


app = FastAPI(
    title="Agentic RAG Multi-Tool Assistant",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/route", response_model=RouteResponse)
def route_query(req: RouteRequest):
    try:
        plan = route(req.message, req.history)
        return {
            "tool": plan["tool"],
            "tool_label": TOOL_LABELS[plan["tool"]],
            "reason": plan.get("reason", ""),
            "input": plan.get("input") or req.message,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest")
def run_ingest():
    try:
        count = ingest(force=True)
        return {"status": "ok", "chunks": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        return await answer(req.message, req.history, req.selected_tool)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents")
def documents():
    return {"documents": sorted(p.name for p in DATA_DIR.glob("*.pdf"))}
