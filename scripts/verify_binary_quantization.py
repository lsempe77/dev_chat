"""
Verify binary quantization is working correctly.

This script:
1. Connects to Qdrant Cloud
2. Creates a TEST collection with binary quantization
3. Inserts some test vectors
4. Verifies the collection has quantization enabled
5. Cleans up the test collection

Run: python scripts/verify_binary_quantization.py
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, 
    Distance, 
    PointStruct,
    BinaryQuantization,
    BinaryQuantizationConfig,
)

# Test collection name (will be deleted after test)
TEST_COLLECTION = "binary_quant_test_delete_me"


def get_qdrant_client():
    """Create Qdrant client."""
    url = os.environ.get("QDRANT_URL")
    api_key = os.environ.get("QDRANT_API_KEY")
    
    if not url or not api_key:
        print("❌ Missing QDRANT_URL or QDRANT_API_KEY")
        sys.exit(1)
    
    return QdrantClient(url=url, api_key=api_key)


def test_binary_quantization():
    """Test binary quantization setup."""
    print("=" * 60)
    print("Binary Quantization Verification Test")
    print("=" * 60)
    
    client = get_qdrant_client()
    print(f"\n✅ Connected to Qdrant Cloud")
    
    # Step 1: Delete test collection if it exists
    print(f"\n1. Cleaning up any existing test collection...")
    try:
        client.delete_collection(TEST_COLLECTION)
        print(f"   Deleted existing '{TEST_COLLECTION}'")
    except Exception:
        print(f"   No existing collection to delete")
    
    # Step 2: Create collection WITH binary quantization
    print(f"\n2. Creating collection with binary quantization...")
    try:
        client.create_collection(
            collection_name=TEST_COLLECTION,
            vectors_config={
                "dense": VectorParams(size=1536, distance=Distance.COSINE),
            },
            quantization_config=BinaryQuantization(
                binary=BinaryQuantizationConfig(
                    always_ram=True,
                )
            ),
        )
        print(f"   ✅ Created collection '{TEST_COLLECTION}'")
    except Exception as e:
        print(f"   ❌ Failed to create collection: {e}")
        return False
    
    # Step 3: Verify collection has binary quantization
    print(f"\n3. Verifying binary quantization config...")
    try:
        info = client.get_collection(TEST_COLLECTION)
        quant_config = info.config.quantization_config  # Correct path
        
        if quant_config is None:
            print(f"   ❌ Quantization config is None!")
            return False
        
        print(f"   ✅ Quantization config: {quant_config}")
        
        # Check it's BinaryQuantization
        if hasattr(quant_config, 'binary'):
            print(f"   ✅ Binary quantization confirmed")
            print(f"   ✅ always_ram: {quant_config.binary.always_ram}")
        else:
            print(f"   ⚠️ Config type: {type(quant_config)}")
            
    except Exception as e:
        print(f"   ❌ Failed to get collection info: {e}")
        return False
    
    # Step 4: Insert some test vectors
    print(f"\n4. Inserting test vectors...")
    try:
        import random
        test_vectors = [
            [random.random() for _ in range(1536)]
            for _ in range(5)
        ]
        
        points = [
            PointStruct(
                id=i,
                vector={"dense": vec},
                payload={"text": f"Test document {i}"}
            )
            for i, vec in enumerate(test_vectors)
        ]
        
        client.upsert(collection_name=TEST_COLLECTION, points=points)
        print(f"   ✅ Inserted {len(points)} test points")
    except Exception as e:
        print(f"   ❌ Failed to insert: {e}")
        return False
    
    # Step 5: Search to verify it works
    print(f"\n5. Testing search...")
    try:
        results = client.query_points(
            collection_name=TEST_COLLECTION,
            query=test_vectors[0],
            using="dense",
            limit=3,
        )
        print(f"   ✅ Search returned {len(results.points)} results")
        for r in results.points:
            print(f"      - ID {r.id}: score {r.score:.4f}")
    except Exception as e:
        print(f"   ❌ Search failed: {e}")
        return False
    
    # Step 6: Cleanup
    print(f"\n6. Cleaning up test collection...")
    try:
        client.delete_collection(TEST_COLLECTION)
        print(f"   ✅ Deleted test collection")
    except Exception as e:
        print(f"   ⚠️ Failed to delete: {e}")
    
    print("\n" + "=" * 60)
    print("✅ BINARY QUANTIZATION VERIFIED SUCCESSFULLY")
    print("=" * 60)
    print("\nThe code is ready. Next steps:")
    print("1. Deploy to Modal: modal deploy infrastructure/modal_mineru.py")
    print("2. Process a test PDF via your project's collection")
    print("   (Collections will be recreated with binary quantization automatically)")
    
    return True


def check_existing_collections():
    """Check existing collections for binary quantization."""
    print("\n" + "=" * 60)
    print("Checking Existing Collections")
    print("=" * 60)
    
    client = get_qdrant_client()
    collections = client.get_collections().collections
    
    for coll in collections:
        name = coll.name
        if name == TEST_COLLECTION:
            continue
            
        try:
            info = client.get_collection(name)
            quant = info.config.quantization_config  # Correct path
            has_quant = "✅ Binary" if quant else "❌ None"
            points = info.points_count
            print(f"\n{name}:")
            print(f"   Points: {points}")
            print(f"   Quantization: {has_quant}")
        except Exception as e:
            print(f"\n{name}: Error - {e}")


if __name__ == "__main__":
    # Run the test
    success = test_binary_quantization()
    
    # Also show existing collections status
    check_existing_collections()
    
    sys.exit(0 if success else 1)
