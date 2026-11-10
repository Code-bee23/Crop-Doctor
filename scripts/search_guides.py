"""
Crop Guides Vector Search Script (Phase 2 - Day 3-4)
CLI utility to test similarity search filtered by crop and state.
"""

import sys
import argparse
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.retriever import guide_retriever


async def main():
    parser = argparse.ArgumentParser(description="Search crop guide chunks using pgvector / semantic embeddings.")
    parser.add_argument("--query", "-q", type=str, required=True, help="Farmer symptom query or observation")
    parser.add_argument("--crop", "-c", type=str, default=None, help="Target crop (e.g. chilli, cotton, paddy, tomato)")
    parser.add_argument("--state", "-s", type=str, default=None, help="Target state (e.g. Telangana, Maharashtra, Punjab)")
    parser.add_argument("--top_k", "-k", type=int, default=3, help="Number of chunks to retrieve")

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("CROP DOCTOR - VECTOR GUIDE SEARCH")
    print("=" * 80)
    print(f"Query : '{args.query}'")
    print(f"Crop  : {args.crop or 'All crops'}")
    print(f"State : {args.state or 'All states'}")
    print(f"Top-K : {args.top_k}")
    print("-" * 80)

    results = await guide_retriever.search(
        query=args.query,
        crop=args.crop,
        state=args.state,
        top_k=args.top_k
    )

    if not results:
        print("No matching guide passages found.")
        print("=" * 80)
        return

    for idx, r in enumerate(results, start=1):
        print(f"\n[Result #{idx}] Score: {r['similarity']} | Chunk ID: {r['id']}")
        print(f"Source   : {r['source_title']} (Page {r['page']})")
        print(f"Publisher: {r['publisher']} | State: {r['state']} | Crop: {r['crop'].capitalize()}")
        print(f"Section  : {r['section']}")
        print(f"Text     :\n{r['text']}")
        print("-" * 80)

    print(f"Search completed: {len(results)} chunks retrieved.\n")


if __name__ == "__main__":
    asyncio.run(main())

