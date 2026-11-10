"""
Crop Guides Ingestion Script (Phase 2 - Day 3-4)
Processes ICAR and State Agricultural University guides, generates embeddings,
and stores them in Supabase pgvector and local vector_store.json.
"""

import sys
import json
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import db
from app.services.embedding import embedding_service
from guides.data import GUIDE_RECORDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_guides")


def ingest():
    logger.info(f"Starting ingestion for {len(GUIDE_RECORDS)} crop guide sections...")

    vectorized_chunks = []
    supabase_records = []

    for idx, item in enumerate(GUIDE_RECORDS, start=1):
        full_text = f"{item['crop']} {item['section']} {item['text']}"
        embedding = embedding_service.get_embedding(full_text)

        chunk_data = {
            "id": idx,
            "source_title": item["source_title"],
            "publisher": item["publisher"],
            "state": item["state"],
            "crop": item["crop"].lower(),
            "section": item["section"],
            "page": item["page"],
            "text": item["text"],
            "embedding": embedding
        }
        vectorized_chunks.append(chunk_data)

        # Record for Supabase table insertion
        supabase_records.append({
            "source_title": item["source_title"],
            "publisher": item["publisher"],
            "state": item["state"],
            "crop": item["crop"].lower(),
            "section": item["section"],
            "page": item["page"],
            "text": item["text"],
            "embedding": embedding
        })

    # 1. Save local vectorized database to disk
    vector_store_path = Path("guides/vector_store.json")
    vector_store_path.parent.mkdir(parents=True, exist_ok=True)
    with open(vector_store_path, "w", encoding="utf-8") as f:
        json.dump(vectorized_chunks, f, indent=2, ensure_ascii=False)
    logger.info(f"Successfully saved {len(vectorized_chunks)} chunks to {vector_store_path}")

    # 2. Upload to Supabase if client is connected
    if db.client:
        try:
            logger.info("Syncing chunks to Supabase `guide_chunks` table...")
            # Upsert chunks
            for record in supabase_records:
                db.client.table("guide_chunks").insert(record).execute()
            logger.info("Supabase pgvector synchronization complete!")
        except Exception as e:
            logger.warning(f"Could not sync to Supabase: {e}. (Local vector store is active and ready).")

    # 3. Print verification table
    print("\n" + "=" * 80)
    print("INGESTED CROP GUIDES SUMMARY")
    print("=" * 80)
    print(f"{'Crop':<10} | {'State':<14} | {'Publisher':<20} | {'Page':<5} | {'Section'}")
    print("-" * 80)
    for c in vectorized_chunks:
        print(f"{c['crop'].capitalize():<10} | {c['state']:<14} | {c['publisher'][:20]:<20} | {c['page']:<5} | {c['section'][:25]}...")
    print("=" * 80)
    print(f"Total Chunks Ingested: {len(vectorized_chunks)}")
    print("Phase 2 Ingestion Complete!\n")


if __name__ == "__main__":
    ingest()

