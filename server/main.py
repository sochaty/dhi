import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

from inference.fim import FIMRequest, complete  # noqa: E402
from rag.chunker import chunk_file  # noqa: E402
from rag.store import ChunkStore  # noqa: E402

app = FastAPI(title="Dhi Server", version="0.1.0")
store = ChunkStore()


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


class IndexResponse(BaseModel):
    indexed: int


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/complete", response_model=CompleteResponse)
def complete_endpoint(req: CompleteRequest) -> CompleteResponse:
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/index", response_model=IndexResponse)
def index_endpoint(req: IndexRequest) -> IndexResponse:
    try:
        chunks = list(chunk_file(req.file_path))
        store.upsert(chunks)
        return IndexResponse(indexed=len(chunks))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
