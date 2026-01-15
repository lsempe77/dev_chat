"""Quick test of V4's LLM call with fixed model"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"

print(f"Testing model: {MODEL}")
print(f"API key present: {bool(OPENROUTER_API_KEY)}")

# Simple test prompt
test_prompt = """Extract outcomes from this text:

"The treatment increased income by $100 (SE=10) for the treatment group (N=500) compared to control (N=500)."

Return JSON: {"outcomes": [{"outcome_name": "Income", "coefficient": 100, "standard_error": 10, "n_treatment": 500, "n_control": 500}]}
"""

try:
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": test_prompt}],
            "max_tokens": 500,
            "temperature": 0
        },
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        timeout=30
    )
    
    print(f"\nStatus code: {response.status_code}")
    
    if response.status_code == 200:
        content = response.json()["choices"][0]["message"]["content"]
        print(f"✅ SUCCESS! Model returned: {content[:200]}")
    else:
        print(f"❌ FAILED: {response.text[:200]}")
        
except Exception as e:
    print(f"❌ ERROR: {e}")
