import asyncio
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.requests import Request

logging.basicConfig(level=logging.INFO)

load_dotenv()

from inference.fim import FIMRequest, complete  # noqa: E402
from rag.chunker import chunk_text  # noqa: E402
from rag.store import ChunkStore  # noqa: E402

app = FastAPI(title="Dhi Server", version="0.1.0")
store = ChunkStore()

# Single-flight guard for Ollama. A plain bool is race-safe in asyncio
# (single-threaded event loop).
_ollama_busy = False


# ── Request / response models ──────────────────────────────────────────────────


class CompleteRequest(BaseModel):
    file_path: str
    prefix: str
    suffix: str
    language: str


class CompleteResponse(BaseModel):
    completion: str


class IndexRequest(BaseModel):
    file_path: str
    content: str
    language: str


class IndexResponse(BaseModel):
    indexed: int


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/complete", response_model=CompleteResponse)
async def complete_endpoint(req: CompleteRequest, request: Request) -> CompleteResponse:
    global _ollama_busy
    if _ollama_busy:
        logging.info("complete_endpoint: busy")
        raise HTTPException(status_code=503, detail="server busy")
    _ollama_busy = True
    try:
        fim_req = FIMRequest(
            file_path=req.file_path,
            prefix=req.prefix,
            suffix=req.suffix,
            language=req.language,
        )
        ollama_task = asyncio.create_task(complete(fim_req, store))

        # Poll for client disconnect while Ollama generates.
        # asyncio.sleep(0) yields so the task can run; 0.1 s limits how often
        # we call is_disconnected() (it does a socket peek each time).
        # When the VS Code extension aborts (user typed again), we detect it
        # here and cancel the Ollama task — closing the TCP connection to
        # Ollama, which cancels its Go request context mid-generation.
        while True:
            await asyncio.sleep(0)
            if ollama_task.done():
                break
            if await request.is_disconnected():
                ollama_task.cancel()
                try:
                    await ollama_task
                except asyncio.CancelledError:
                    pass
                logging.info("complete_endpoint: client disconnected — lock released")
                return CompleteResponse(completion="")
            await asyncio.sleep(0.1)

        completion = await ollama_task
        return CompleteResponse(completion=completion)
    except Exception as exc:
        logging.exception("complete_endpoint error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        _ollama_busy = False


@app.post("/index", response_model=IndexResponse)
def index_endpoint(req: IndexRequest) -> IndexResponse:
    try:
        chunks = chunk_text(req.content, req.language, file_path=req.file_path)
        store.upsert(chunks)
        return IndexResponse(indexed=len(chunks))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
