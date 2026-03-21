"""
NEXUS SDLC - RAG Service
ChromaDB + sentence-transformers for semantic search with optional BM25 hybrid ranking.
"""

import asyncio
import logging
import math
import re
import uuid

from app.core.config import settings

logger = logging.getLogger("nexus.rag")

_chroma_client = None
_collection = None
_embedding_fn = None


def _get_chroma():
    global _chroma_client, _collection, _embedding_fn
    if _chroma_client is None:
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            _chroma_client = chromadb.PersistentClient(path=settings.CHROMADB_PATH)
            _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=settings.EMBEDDING_MODEL
            )
            _collection = _chroma_client.get_or_create_collection(
                name=settings.CHROMADB_COLLECTION,
                embedding_function=_embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB ready: collection=%s", settings.CHROMADB_COLLECTION)
        except ImportError:
            logger.warning("chromadb or sentence-transformers not installed; RAG disabled.")
    return _collection


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_@.-]+", (text or "").lower())


def _normalize_scores(raw_scores: dict[str, float]) -> dict[str, float]:
    if not raw_scores:
        return {}
    values = list(raw_scores.values())
    max_score = max(values)
    min_score = min(values)
    if math.isclose(max_score, min_score):
        return {key: 1.0 if max_score > 0 else 0.0 for key in raw_scores}
    return {key: (value - min_score) / (max_score - min_score) for key, value in raw_scores.items()}


def _bm25_scores(query: str, documents: dict[str, str]) -> dict[str, float]:
    tokenized_docs = {doc_id: _tokenize(text) for doc_id, text in documents.items()}
    query_terms = _tokenize(query)
    if not tokenized_docs or not query_terms:
        return {}

    doc_count = len(tokenized_docs)
    avg_doc_len = sum(len(tokens) for tokens in tokenized_docs.values()) / max(doc_count, 1)
    if avg_doc_len <= 0:
        return {}

    doc_freq: dict[str, int] = {}
    for tokens in tokenized_docs.values():
        for term in set(tokens):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    k1 = 1.5
    b = 0.75
    scores: dict[str, float] = {}

    for doc_id, tokens in tokenized_docs.items():
        if not tokens:
            continue
        term_counts: dict[str, int] = {}
        for token in tokens:
            term_counts[token] = term_counts.get(token, 0) + 1

        doc_len = len(tokens)
        score = 0.0
        for term in query_terms:
            term_frequency = term_counts.get(term, 0)
            if term_frequency == 0:
                continue
            frequency = doc_freq.get(term, 0)
            idf = math.log(1 + ((doc_count - frequency + 0.5) / (frequency + 0.5)))
            numerator = term_frequency * (k1 + 1)
            denominator = term_frequency + k1 * (1 - b + b * (doc_len / avg_doc_len))
            score += idf * (numerator / denominator)
        if score > 0:
            scores[doc_id] = score
    return scores


def _compose_result(doc_id: str, document: str, metadata: dict, semantic_score: float, bm25_score: float, hybrid_score: float) -> dict:
    return {
        "chunk_id": doc_id,
        "excerpt": (document or "")[:300],
        "score": round(hybrid_score, 4),
        "semantic_score": round(semantic_score, 4),
        "bm25_score": round(bm25_score, 4),
        "metadata": metadata or {},
        "request_id": (metadata or {}).get("request_id", ""),
    }


async def index_request(request_id: str, text: str, metadata: dict, weight: float = 1.0):
    """Embed and upsert a request into the knowledge base."""
    collection = _get_chroma()
    if not collection:
        return

    loop = asyncio.get_event_loop()
    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, request_id))
    meta = {**metadata, "weight": weight, "request_id": request_id}

    def _upsert():
        collection.upsert(
            ids=[chunk_id],
            documents=[text],
            metadatas=[meta],
        )

    await loop.run_in_executor(None, _upsert)
    logger.info("RAG indexed: %s weight=%s", request_id, weight)


async def retrieve_similar(query: str, top_k: int = 3, filter_meta: dict = None) -> list:
    """
    Hybrid similarity search.
    Returns list of {request_id, excerpt, score, semantic_score, bm25_score, metadata}.
    """
    collection = _get_chroma()
    if not collection:
        return []

    loop = asyncio.get_event_loop()
    search_mode = (settings.RAG_SEARCH_MODE or "semantic").lower()
    candidate_pool = max(top_k, settings.RAG_CANDIDATE_POOL)

    def _semantic_query():
        kwargs = {
            "query_texts": [query],
            "n_results": candidate_pool,
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_meta:
            kwargs["where"] = filter_meta
        return collection.query(**kwargs)

    semantic_results = await loop.run_in_executor(None, _semantic_query)

    doc_map: dict[str, dict] = {}
    semantic_scores: dict[str, float] = {}

    if semantic_results and semantic_results.get("ids") and semantic_results["ids"][0]:
        for i, doc_id in enumerate(semantic_results["ids"][0]):
            distance = semantic_results["distances"][0][i]
            similarity = max(0.0, 1.0 - distance)
            metadata = semantic_results["metadatas"][0][i] or {}
            document = semantic_results["documents"][0][i] or ""
            doc_map[doc_id] = {"document": document, "metadata": metadata}
            semantic_scores[doc_id] = similarity

    if search_mode == "semantic":
        output = []
        for doc_id, semantic_score in sorted(semantic_scores.items(), key=lambda item: item[1], reverse=True):
            if semantic_score < settings.RAG_RELEVANCE_THRESHOLD:
                continue
            item = doc_map[doc_id]
            output.append(_compose_result(doc_id, item["document"], item["metadata"], semantic_score, 0.0, semantic_score))
            if len(output) >= top_k:
                break
        return output

    def _fetch_all_candidates():
        kwargs = {"include": ["documents", "metadatas"]}
        if filter_meta:
            kwargs["where"] = filter_meta
        return collection.get(**kwargs)

    all_candidates = await loop.run_in_executor(None, _fetch_all_candidates)
    all_docs: dict[str, str] = {}
    all_meta: dict[str, dict] = {}

    if all_candidates and all_candidates.get("ids"):
        for i, doc_id in enumerate(all_candidates["ids"]):
            all_docs[doc_id] = (all_candidates.get("documents") or [""])[i] or ""
            all_meta[doc_id] = (all_candidates.get("metadatas") or [{}])[i] or {}
            if doc_id not in doc_map:
                doc_map[doc_id] = {"document": all_docs[doc_id], "metadata": all_meta[doc_id]}

    bm25_raw = _bm25_scores(query, all_docs)
    bm25_scores = _normalize_scores(bm25_raw)

    semantic_norm = _normalize_scores(semantic_scores)
    semantic_weight = max(0.0, settings.RAG_SEMANTIC_WEIGHT)
    bm25_weight = max(0.0, settings.RAG_BM25_WEIGHT)
    total_weight = semantic_weight + bm25_weight or 1.0
    semantic_weight /= total_weight
    bm25_weight /= total_weight

    combined: list[dict] = []
    candidate_ids = set(semantic_norm) | set(bm25_scores)
    for doc_id in candidate_ids:
        semantic_score = semantic_norm.get(doc_id, 0.0)
        bm25_score = bm25_scores.get(doc_id, 0.0)
        hybrid_score = (semantic_score * semantic_weight) + (bm25_score * bm25_weight)
        if hybrid_score < settings.RAG_RELEVANCE_THRESHOLD:
            continue
        item = doc_map.get(doc_id, {"document": "", "metadata": {}})
        combined.append(_compose_result(doc_id, item["document"], item["metadata"], semantic_score, bm25_score, hybrid_score))

    combined.sort(key=lambda item: item["score"], reverse=True)
    return combined[:top_k]


async def purge_collection():
    """Delete all documents from collection."""
    collection = _get_chroma()
    if collection:
        global _chroma_client
        _chroma_client.delete_collection(settings.CHROMADB_COLLECTION)
        logger.warning("RAG collection purged!")


async def get_stats() -> dict:
    collection = _get_chroma()
    if not collection:
        return {"available": False}
    count = collection.count()
    return {
        "available": True,
        "doc_count": count,
        "collection_name": settings.CHROMADB_COLLECTION,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dim": 384,
        "search_mode": settings.RAG_SEARCH_MODE,
        "semantic_weight": settings.RAG_SEMANTIC_WEIGHT,
        "bm25_weight": settings.RAG_BM25_WEIGHT,
    }
