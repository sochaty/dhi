import asyncio
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.requests import Request

logging.basicConfig(level=logging.INFO)

load_dotenv()

from inference.fim import FIMRequest, complete  # noqa: E402
from rag.chunker import chunk_file, chunk_text  # noqa: E402
from rag.indexer import iter_source_files  # noqa: E402
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


class IndexDirRequest(BaseModel):
    dir_path: str
    respect_gitignore: bool = True


class IndexDirResponse(BaseModel):
    indexed_files: int
    indexed_chunks: int


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    mode: str = "hybrid"  # "hybrid" | "vector" | "bm25"


class SearchResponse(BaseModel):
    results: list[str]


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
    """Index a single file's content sent by the extension."""
    try:
        chunks = chunk_text(req.content, req.language, file_path=req.file_path)
        store.upsert(chunks)
        return IndexResponse(indexed=len(chunks))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/index-dir", response_model=IndexDirResponse)
def index_dir_endpoint(req: IndexDirRequest) -> IndexDirResponse:
    """Index all source files under a directory (local/volume-mount mode).

    Discovers files via rag.indexer, reads each from disk, chunks with
    Tree-sitter, and upserts into the store.  Files that cannot be read are
    skipped silently so a single bad file doesn't abort the whole workspace.
    """
    try:
        total_files = 0
        total_chunks = 0
        for file_path in iter_source_files(req.dir_path, respect_gitignore=req.respect_gitignore):
            try:
                chunks = list(chunk_file(file_path))
                if chunks:
                    store.upsert(chunks)
                    total_chunks += len(chunks)
                total_files += 1
            except Exception:
                logging.exception("index_dir_endpoint: skipping %s", file_path)
        return IndexDirResponse(indexed_files=total_files, indexed_chunks=total_chunks)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/search", response_model=SearchResponse)
def search_endpoint(req: SearchRequest) -> SearchResponse:
    """Explicit similarity search — used by the chat panel and agent context assembly."""
    try:
        n = max(1, min(req.n_results, 20))
        if req.mode == "bm25":
            results = store.bm25_query(req.query, n)
        elif req.mode == "vector":
            results = store.query(req.query, n)
        else:
            results = store.hybrid_query(req.query, n)
        return SearchResponse(results=results)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
