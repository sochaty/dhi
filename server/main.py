import logging
import threading

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)

load_dotenv()

from inference.fim import FIMRequest, complete  # noqa: E402
from rag.chunker import chunk_text  # noqa: E402
from rag.store import ChunkStore  # noqa: E402

app = FastAPI(title="Dhi Server", version="0.1.0")
store = ChunkStore()

# Only one Ollama generate call at a time — if busy, callers get empty immediately.
_ollama_lock = threading.Lock()


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
def complete_endpoint(req: CompleteRequest) -> CompleteResponse:
    if not _ollama_lock.acquire(blocking=False):
        logging.info("complete_endpoint: lock busy, returning empty")
        return CompleteResponse(completion="")
    try:
        fim_req = FIMRequest(
            file_path=req.file_path,
            prefix=req.prefix,
            suffix=req.suffix,
            language=req.language,
        )
        completion = complete(fim_req, store)
        return CompleteResponse(completion=completion)
    except Exception as exc:
        logging.exception("complete_endpoint error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        _ollama_lock.release()


@app.post("/index", response_model=IndexResponse)
def index_endpoint(req: IndexRequest) -> IndexResponse:
    try:
        chunks = chunk_text(req.content, req.language, file_path=req.file_path)
        store.upsert(chunks)
        return IndexResponse(indexed=len(chunks))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
