"""
Setup Langfuse for DevChat Evaluation

This script:
1. Creates a dataset with our test cases
2. Uploads system prompts for versioning
3. Sets up scoring configuration

Run with: python scripts/setup_langfuse.py
"""

import json
import os
from dotenv import load_dotenv

load_dotenv()

from langfuse import Langfuse

# Initialize Langfuse client
langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
)

# =============================================================================
# 1. Create Dataset with Test Cases
# =============================================================================

def create_test_dataset():
    """Create the DevChat test cases dataset."""
    
    # Load test cases from file
    with open("evaluation/test_cases.json", "r") as f:
        test_data = json.load(f)
    
    dataset_name = "devchat-graduation-tests"
    
    # Create or get existing dataset
    try:
        dataset = langfuse.create_dataset(
            name=dataset_name,
            description="Golden test cases for DevChat evaluation - Graduation Programs focus"
        )
        print(f"✅ Created dataset: {dataset_name}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"📌 Dataset already exists: {dataset_name}")
            dataset = langfuse.get_dataset(dataset_name)
        else:
            raise e
    
    # Add test cases as dataset items
    for tc in test_data.get("test_cases", []):
        try:
            langfuse.create_dataset_item(
                dataset_name=dataset_name,
                input={"query": tc.get("question", tc.get("query", ""))},
                expected_output={
                    "category": tc.get("category", "unknown"),
                    "expected_answer": tc.get("expected_answer"),
                    "expected_topics": tc.get("expected_topics", [])
                },
                metadata={
                    "id": tc.get("id"),
                    "category": tc.get("category")
                }
            )
            print(f"  ➕ Added: {tc.get('id')}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  📌 Already exists: {tc.get('id')}")
            else:
                print(f"  ❌ Error adding {tc.get('id')}: {e}")
    
    return dataset

# =============================================================================
# 2. Upload System Prompts
# =============================================================================

def upload_prompts():
    """Upload system prompts for versioning and A/B testing."""
    
    # Claim extraction prompt (Pass 1)
    claim_extraction_prompt = """You are analyzing academic research documents to extract factual claims.

For each source document provided, extract the key claims that can be used to answer the user's question.

For EACH claim you extract:
1. State the claim clearly and concisely
2. Provide the EXACT supporting quote from the source
3. Classify the claim type: finding, methodology, context, or limitation
4. Rate your confidence: high (exact quote), medium (paraphrased), low (inferred)

Focus on claims that are:
- Directly relevant to the user's question
- Verifiable from the source text
- Factual (not opinions unless attributed)

Output format:
```json
{
  "claims": [
    {
      "claim_id": "1a",
      "source_id": 1,
      "claim_text": "The graduation approach reduced poverty by 10%",
      "supporting_quote": "We find a 10 percentage point reduction in extreme poverty...",
      "claim_type": "finding",
      "confidence": "high"
    }
  ]
}
```"""

    # Answer synthesis prompt (Pass 2)
    synthesis_prompt = """You are a research assistant synthesizing evidence from academic studies.

You have been provided with a VERIFIED CLAIMS LEDGER containing claims extracted from source documents.
Each claim has been verified against the original text.

YOUR TASK:
Write a comprehensive answer to the user's question using ONLY the verified claims.

RULES:
1. ONLY use claims from the ledger - do not add information not in the ledger
2. Cite sources using [1], [2], etc. matching the source_id
3. Every factual statement MUST have a citation
4. Be comprehensive but concise
5. Organize by theme, not by source
6. If the ledger doesn't contain enough information to answer, say so

FORMAT:
- Use markdown formatting
- Start with a brief overview
- Use headers to organize themes
- End with synthesis/conclusions if appropriate"""

    prompts = [
        {
            "name": "claim-extraction-v1",
            "prompt": claim_extraction_prompt,
            "config": {
                "model": "gpt-4o",
                "temperature": 0.1,
                "max_tokens": 4000
            },
            "labels": ["extraction", "claim-ledger", "production"]
        },
        {
            "name": "synthesis-v1", 
            "prompt": synthesis_prompt,
            "config": {
                "model": "gpt-4o",
                "temperature": 0.3,
                "max_tokens": 4000
            },
            "labels": ["synthesis", "claim-ledger", "production"]
        }
    ]
    
    for p in prompts:
        try:
            langfuse.create_prompt(
                name=p["name"],
                prompt=p["prompt"],
                config=p["config"],
                labels=p["labels"]
            )
            print(f"✅ Created prompt: {p['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"📌 Prompt already exists: {p['name']}")
            else:
                print(f"❌ Error creating {p['name']}: {e}")

# =============================================================================
# 3. Create Score Configurations
# =============================================================================

def setup_scores():
    """Document the scoring configuration (scores are created per-trace)."""
    
    print("\n📊 Scoring Configuration:")
    print("  The following scores should be logged per trace:")
    print("  - faithfulness (0-1): Claims grounded in context")
    print("  - citation_recall (0-1): Sentences with valid citations")  
    print("  - citation_precision (0-1): Citations that support claims")
    print("  - latency_ms (numeric): Response time")
    print("\n  Scores are logged via: langfuse.score(trace_id, name, value)")

# =============================================================================
# Main
# =============================================================================

def main():
    print("🚀 Setting up Langfuse for DevChat Evaluation\n")
    
    print("=" * 50)
    print("1. Creating Test Dataset")
    print("=" * 50)
    create_test_dataset()
    
    print("\n" + "=" * 50)
    print("2. Uploading Prompts")
    print("=" * 50)
    upload_prompts()
    
    print("\n" + "=" * 50)
    print("3. Score Configuration")
    print("=" * 50)
    setup_scores()
    
    print("\n" + "=" * 50)
    print("✅ Setup Complete!")
    print("=" * 50)
    print(f"\nView in Langfuse: https://cloud.langfuse.com/project/cmjafx1vd00qkad06prpgl80o")
    print("  - Datasets: /datasets")
    print("  - Prompts: /prompts")
    print("  - Experiments: /experiments")
    
    # Flush to ensure all events are sent
    langfuse.flush()

if __name__ == "__main__":
    main()
