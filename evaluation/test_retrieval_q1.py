"""Debug Query 1 retrieval failure."""
import asyncio
from src.retrieval.hybrid_retriever import HybridRetriever

async def test():
    retriever = HybridRetriever(collection_name="devchat_v2_contextual")
    query = "What is the graduation approach to poverty reduction?"
    results = await retriever.retrieve(query, top_k=5)
    print(f"Query: {query}")
    print(f"Retrieved {len(results)} documents")
    for i, doc in enumerate(results):
        title = doc.metadata.get("title", "Unknown")
        score = doc.metadata.get("score", "N/A")
        print(f"\n{i+1}. {title}")
        print(f"   Score: {score}")
        print(f"   Text: {doc.page_content[:200]}...")

if __name__ == "__main__":
    asyncio.run(test())
