"""
API-based embedding (DashScope OpenAI-compatible).

Replaces the local MiA-EMB-8B model with an external embedding API so the
backend can run on machines without GPU or model weights.  Interface matches
``MiAEmbedding`` (``load`` / ``encode_queries`` / ``encode_documents`` /
``compute_similarity``), so callers in ``dual_channel`` / ``mia_rag`` /
``rag_manager`` are unaffected.

Embedding model: DashScope ``text-embedding-v3`` (1024 dims by default, or
set ``dimensions`` via config).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
import numpy as np

from .mia_config import MiAConfig

logger = logging.getLogger("mia_emb")

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "text-embedding-v3"
_DEFAULT_DIM = 1024


class ApiEmbedding:
    """Embedding via OpenAI-compatible API (DashScope text-embedding-v3)."""

    def __init__(
        self,
        config: MiAConfig,
        device: Optional[str] = None,  # kept for interface compatibility
    ):
        self.config = config
        self.device = device or "api"
        self._loaded = False
        self._load_mode = "api"
        self._base_url = getattr(config, "embedding_base_url", "") or _DEFAULT_BASE_URL
        self._api_key = getattr(config, "embedding_api_key", "") or ""
        self._model = getattr(config, "embedding_model", "") or _DEFAULT_MODEL
        self._dim = int(getattr(config, "embedding_dim", _DEFAULT_DIM) or _DEFAULT_DIM)

    # ── Lifecycle ─────────────────────────────────────────────────

    def load(self, model_path: Optional[str] = None, base_model_path: Optional[str] = None):
        """No-op for API mode: validates config instead of loading weights."""
        if not self._api_key:
            raise RuntimeError(
                "Embedding API key not configured. Set EMBEDDING_API_KEY "
                "environment variable or MiAConfig.embedding_api_key."
            )
        self._loaded = True
        logger.info(
            f"ApiEmbedding ready (model={self._model}, base_url={self._base_url})"
        )

    @property
    def loaded(self) -> bool:
        return self._loaded

    # ── Public encoding API ───────────────────────────────────────

    def encode_documents(self, documents: list[str], batch_size: int = 32) -> np.ndarray:
        """Embed document chunks, returning (n, dim) float32 array."""
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call .load() first.")
        if not documents:
            return np.array([])
        embeddings = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            embeddings.extend(self._call_api(batch))
        return np.asarray(embeddings, dtype=np.float32)

    def encode_queries(
        self,
        queries: list[str],
        mindscape: str = "",
        residual: bool = True,
        mode: str = "chunk",
    ) -> np.ndarray:
        """Embed queries. mindscape is ignored by the API model; residual is
        not applicable (no token-position extraction), so we return the plain
        query embedding -- shape (len(queries), dim)."""
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call .load() first.")
        if not queries:
            return np.array([])
        texts = [q for q in queries]
        embeddings = self._call_api(texts)
        return np.asarray(embeddings, dtype=np.float32)

    # ── Similarity ───────────────────────────────────────────────

    @staticmethod
    def compute_similarity(
        query_embedding: np.ndarray,
        doc_embeddings: np.ndarray,
        query_residual: Optional[np.ndarray] = None,
        delta: float = 0.5,
    ) -> np.ndarray:
        """Cosine similarity (residual fusion ignored for API embeddings)."""
        q = np.atleast_2d(query_embedding)
        d = np.atleast_2d(doc_embeddings)
        qn = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-8)
        dn = d / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-8)
        scores = qn @ dn.T
        return np.squeeze(scores, axis=0)

    # ── Internal ─────────────────────────────────────────────────

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """POST to the OpenAI-compatible /embeddings endpoint."""
        url = f"{self._base_url.rstrip('/')}/embeddings"
        payload: dict = {"model": self._model, "input": texts}
        # DashScope text-embedding-v3 supports a `dimensions` parameter.
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=60.0)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
            if not items:
                raise RuntimeError("Embedding API returned empty data")
            # Sort by index to preserve order
            items.sort(key=lambda x: x.get("index", 0))
            return [item["embedding"] for item in items]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Embedding API HTTP {e.response.status_code}: "
                f"{e.response.text[:300]}"
            )
            raise
        except Exception as e:
            logger.error(f"Embedding API request failed: {e}")
            raise
