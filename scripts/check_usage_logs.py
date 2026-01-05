"""Check usage_logs table."""
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
import os
import json

supabase = create_client(
    os.environ['SUPABASE_URL'], 
    os.environ['SUPABASE_SERVICE_ROLE_KEY']
)

# Check usage_logs
result = supabase.table('usage_logs').select('*').order('created_at', desc=True).limit(10).execute()
print(f"usage_logs records: {len(result.data)}")

if result.data:
    for row in result.data[:5]:
        print(f"\n  Model: {row.get('model')}")
        print(f"  Type: {row.get('event_type')}")
        print(f"  Tokens: in={row.get('input_tokens')}, out={row.get('output_tokens')}")
        print(f"  Cost: ${row.get('cost_usd')}")
        print(f"  Latency: {row.get('latency_ms')}ms")
        print(f"  Created: {row.get('created_at')}")
else:
    print("No usage_logs records found")

# Check chat_history
chat_result = supabase.table('chat_history').select('*').order('created_at', desc=True).limit(5).execute()
print(f"\nchat_history records: {len(chat_result.data)}")
if chat_result.data:
    print("Columns:", list(chat_result.data[0].keys()))
