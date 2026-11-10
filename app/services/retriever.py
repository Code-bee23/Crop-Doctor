import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import get_settings
from app.database import db
from app.services.embedding import embedding_service
from guides.data import GUIDE_RECORDS

logger = logging.getLogger("crop_doctor.retriever")


class GuideRetriever:
    """
    RAG Retriever for University and ICAR Crop Guides.
    Queries Supabase pgvector RPC with fallback to local vectorized memory store.
    """
    def __init__(self):
        self.settings = get_settings()
        self.local_chunks: List[Dict[str, Any]] = []
        self._init_local_store()

    def _init_local_store(self):
        """Pre-index and embed crop guide records in memory."""
        vector_store_file = Path("guides/vector_store.json")
        if vector_store_file.exists():
            try:
                with open(vector_store_file, "r", encoding="utf-8") as f:
                    self.local_chunks = json.load(f)
                    logger.info(f"Loaded {len(self.local_chunks)} guide chunks from vector_store.json")
                    return
            except Exception as e:
                logger.warning(f"Could not load vector_store.json: {e}")

        # Build in-memory embeddings from GUIDE_RECORDS
        self.local_chunks = []
        for idx, item in enumerate(GUIDE_RECORDS, start=1):
            chunk_text = f"{item['crop']} {item['section']} {item['text']}"
            emb = embedding_service.get_embedding(chunk_text)
            self.local_chunks.append({
                "id": idx,
                "source_title": item["source_title"],
                "publisher": item["publisher"],
                "state": item["state"],
                "crop": item["crop"].lower(),
                "section": item["section"],
                "page": item["page"],
                "text": item["text"],
                "embedding": emb
            })
        logger.info(f"Initialized {len(self.local_chunks)} in-memory guide chunks.")

    async def search(
        self,
        query: str,
        crop: Optional[str] = None,
        state: Optional[str] = None,
        top_k: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Search crop guide passages with mandatory crop filter and optional state filter.
        
        :param query: Symptom description or farmer voice note transcript.
        :param crop: Crop name (e.g. 'chilli', 'cotton', 'paddy', 'tomato').
        :param state: State name (e.g. 'Telangana', 'Maharashtra', 'Punjab').
        :param top_k: Maximum number of chunks to return (default: 6).
        :return: List of top matching guide chunks with similarity scores.
        """
        query_embedding = embedding_service.get_embedding(query)
        crop_clean = crop.strip().lower() if crop else None
        state_clean = state.strip().lower() if state else None

        # 1. Attempt Supabase pgvector search if client is active
        if db.client:
            try:
                rpc_params = {
                    "query_embedding": query_embedding,
                    "filter_crop": crop_clean,
                    "filter_state": state_clean,
                    "match_count": top_k
                }
                res = db.client.rpc("match_guide_chunks", rpc_params).execute()
                if res.data and len(res.data) > 0:
                    logger.info(f"Supabase pgvector matched {len(res.data)} chunks.")
                    return res.data
            except Exception as e:
                logger.warning(f"Supabase RPC search failed: {e}. Falling back to local vector store.")

        # 2. Local vector search with strict crop and state filters
        candidates = []
        for chunk in self.local_chunks:
            # Crop filter
            if crop_clean and chunk["crop"] != crop_clean:
                continue

            # State filter
            if state_clean and chunk["state"].lower() != state_clean:
                # If state doesn't match, we keep chunk but apply a slight penalty if crop matches
                continue

            sim = embedding_service.cosine_similarity(query_embedding, chunk["embedding"])
            candidates.append({
                "id": chunk["id"],
                "source_title": chunk["source_title"],
                "publisher": chunk["publisher"],
                "state": chunk["state"],
                "crop": chunk["crop"],
                "section": chunk["section"],
                "page": chunk["page"],
                "text": chunk["text"],
                "similarity": round(sim, 4)
            })

        # If strict state filter returned 0 results, relax state filter to ensure crop coverage
        if not candidates and crop_clean:
            for chunk in self.local_chunks:
                if chunk["crop"] == crop_clean:
                    sim = embedding_service.cosine_similarity(query_embedding, chunk["embedding"])
                    candidates.append({
                        "id": chunk["id"],
                        "source_title": chunk["source_title"],
                        "publisher": chunk["publisher"],
                        "state": chunk["state"],
                        "crop": chunk["crop"],
                        "section": chunk["section"],
                        "page": chunk["page"],
                        "text": chunk["text"],
                        "similarity": round(sim, 4)
                    })

        # Rank by cosine similarity descending
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        results = candidates[:top_k]
        logger.info(f"Local vector search retrieved {len(results)} chunks for crop='{crop}', state='{state}'")
        return results


guide_retriever = GuideRetriever()

