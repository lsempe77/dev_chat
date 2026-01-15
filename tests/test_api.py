import requests
import os
from dotenv import load_dotenv
load_dotenv()

# Test with minimal content
response = requests.post(
    'https://openrouter.ai/api/v1/chat/completions',
    headers={
        'Authorization': f'Bearer {os.environ["OPENROUTER_API_KEY"]}',
        'Content-Type': 'application/json'
    },
    json={
        'model': 'anthropic/claude-sonnet-4-20250514',
        'messages': [{'role': 'user', 'content': 'Say hello'}],
        'max_tokens': 100
    }
)
print('Status:', response.status_code)
print('Response:', response.text[:500])
