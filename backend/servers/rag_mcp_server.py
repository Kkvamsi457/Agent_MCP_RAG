import json
from typing import Optional

from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from mcp.server.fastmcp import FastMCP

from app.config import EMBEDDING_MODEL, TOP_K
from app.ingestion import get_collection

mcp = FastMCP("Technical-Docs-RAG")


class DocumentChunk(BaseModel):
    text: str
    source_doc: str
    page_number: int
    section_heading: Optional[str] = None
    distance: float


class SearchResponse(BaseModel):
    results: list[DocumentChunk] = Field(default_factory=list)
    message: Optional[str] = None


_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


@mcp.tool()
def search_documentation(query: str, top_k: int = TOP_K) -> SearchResponse:
    """Search indexed technical documentation and return cited document chunks."""
    top_k = max(1, min(int(top_k), 20))
    collection = get_collection()

    if collection.count() == 0:
        return SearchResponse(
            results=[],
            message="Vector index is empty. Run ingestion first.",
        )

    vector = _get_embedder().encode(
        [query],
        normalize_embeddings=True,
    ).tolist()[0]

    result = collection.query(
        query_embeddings=[vector],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    rows = []
    for doc, meta, dist in zip(
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
    ):
        rows.append(
            DocumentChunk(
                text=doc,
                source_doc=meta.get("source_doc", ""),
                page_number=int(meta.get("page_number", 0)),
                section_heading=meta.get("section_heading") or None,
                distance=float(dist),
            )
        )

    return SearchResponse(results=rows)


if __name__ == "__main__":
    mcp.run(transport="stdio")
