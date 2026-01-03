"""Check if chat_history table exists."""
from dotenv import load_dotenv
load_dotenv()
import os
from supabase import create_client

supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

# Check if table exists
try:
    result = supabase.table('chat_history').select('id').limit(1).execute()
    print('✅ chat_history table already exists!')
    print(f'   Found {len(result.data)} rows')
except Exception as e:
    print(f'❌ Table does not exist yet')
    print(f'   Error: {e}')
    print('')
    print('Please run this SQL in Supabase Dashboard > SQL Editor:')
    print('=' * 60)
    with open('supabase/migrations/20260103_chat_history.sql', 'r') as f:
        print(f.read())
