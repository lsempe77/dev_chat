"""
Test script to verify which models work on OpenRouter.
Tests each model with a simple prompt.
"""

import os
import requests
from dotenv import load_dotenv
import time

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Models to test - January 2026 candidates
MODELS_TO_TEST = [
    # From user's list
    "qwen/qwen3-235b-a22b-2507",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-code-fast-1",
    "openai/gpt-oss-120b",
    "google/gemini-2.5-flash",
    "xiaomi/mimo-v2-flash:free",
    "mistralai/devstral-2512:free",
    "openai/gpt-5-mini",
    
    # Other potential models
    "openai/gpt-4o",
    "openai/gpt-4o-2024-11-20",
    "openai/gpt-4-turbo",
    "openai/o1-mini",
    "openai/o1-preview",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-opus",
    "google/gemini-2.0-flash",
    "google/gemini-2.0-flash-exp",
    "google/gemini-flash-1.5",
    "google/gemini-pro-1.5",
    "mistralai/mistral-large",
    "mistralai/mistral-large-2411",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-v3",
    "meta-llama/llama-3.3-70b-instruct",
]

def test_model(model: str) -> dict:
    """Test a single model with a simple prompt."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
        "max_tokens": 10,
        "temperature": 0,
    }
    
    try:
        start = time.time()
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        latency = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return {
                    "status": "✅ WORKS",
                    "latency": f"{latency:.1f}s",
                    "response": data["choices"][0]["message"]["content"][:50]
                }
            else:
                return {"status": "⚠️ NO CHOICES", "error": str(data)[:100]}
        else:
            error_msg = response.text[:100]
            if "not a valid model" in error_msg.lower() or "not found" in error_msg.lower():
                return {"status": "❌ NOT FOUND", "error": error_msg}
            elif "rate limit" in error_msg.lower():
                return {"status": "⏳ RATE LIMITED", "error": error_msg}
            else:
                return {"status": f"❌ ERROR {response.status_code}", "error": error_msg}
                
    except requests.exceptions.Timeout:
        return {"status": "⏱️ TIMEOUT", "error": "Request timed out"}
    except Exception as e:
        return {"status": "❌ EXCEPTION", "error": str(e)[:100]}


def main():
    print("=" * 70)
    print("OpenRouter Model Tester - January 2026")
    print("=" * 70)
    print()
    
    working = []
    failed = []
    
    for i, model in enumerate(MODELS_TO_TEST):
        print(f"[{i+1}/{len(MODELS_TO_TEST)}] Testing: {model}")
        result = test_model(model)
        
        if result["status"].startswith("✅"):
            print(f"    {result['status']} ({result['latency']})")
            working.append(model)
        else:
            print(f"    {result['status']}: {result.get('error', '')[:60]}")
            failed.append(model)
        
        # Small delay to avoid rate limiting
        time.sleep(0.5)
    
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print(f"✅ WORKING MODELS ({len(working)}):")
    for m in working:
        print(f"    - {m}")
    
    print()
    print(f"❌ FAILED MODELS ({len(failed)}):")
    for m in failed:
        print(f"    - {m}")
    
    # Output as Python list for easy copy-paste
    print()
    print("=" * 70)
    print("COPY-PASTE FOR V15:")
    print("=" * 70)
    print("models_to_test = [")
    for m in working:
        print(f'    "{m}",')
    print("]")


if __name__ == "__main__":
    main()
