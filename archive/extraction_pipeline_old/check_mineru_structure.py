"""Check MineRU table structure."""
import boto3, os, json
from dotenv import load_dotenv
load_dotenv()

client = boto3.client(
    's3',
    endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
)

r2_key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/8d23199222c8_PDFs_of_included_programs_121058356.json'
response = client.get_object(Bucket='devchat-pdfs', Key=r2_key)
data = json.loads(response['Body'].read().decode('utf-8'))

print('MineRU table structure:')
print('='*60)
for i, t in enumerate(data['tables'][:5]):
    print(f'Table {i}:')
    print(f'  type: {t.get("type")}')
    print(f'  keys: {list(t.keys())}')
    print(f'  caption: {str(t.get("table_caption", []))[:60]}')
    print()

print('All unique types:')
types = set(t.get('type') for t in data['tables'])
print(types)
