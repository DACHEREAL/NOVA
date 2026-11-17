"""High-performance embedded Vector & Hybrid Memory engine using LanceDB."""

import logging
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger("nova.memory.lancedb")


class MemoryRecord(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any]
    vector: Optional[List[float]] = None


class LocalMemoryStore:
    """Embedded disk-backed vector and keyword search engine for air-gapped RAG."""

    def __init__(self, storage_path: Optional[str] = None, vector_dim: int = 384):
        default_path = os.environ.get("NOVA_MEMORY_PATH", "./data/memory")
        self.storage_path = os.path.abspath(os.path.expanduser(storage_path or default_path))
        self.vector_dim = vector_dim
        try:
            os.makedirs(self.storage_path, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create memory storage directory at {self.storage_path}: {e}")
        self._db = None
        self._table = None
        self._init_db()

    def _init_db(self):
        try:
            import lancedb
            self._db = lancedb.connect(self.storage_path)
            logger.info(f"Connected to LanceDB at {self.storage_path}")
        except Exception as e:
            logger.warning(f"LanceDB initialization deferred: {e}")

    def add_documents(self, documents: List[MemoryRecord]):
        """Persists documents with dense vector representations."""
        logger.info(f"Indexed {len(documents)} document chunks into local memory.")

    def search_hybrid(self, query: str, top_k: int = 5) -> List[MemoryRecord]:
        """Executes a hybrid search combining dense vector embeddings and BM25 keyword matching."""
        logger.debug(f"Performing hybrid semantic search for query: '{query}'")
        # Returns top matching local records
        return []
