"""Check raw HTML structure for Followup 2 rows."""

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

tables = data.get('tables', [])
for t in tables:
    if 'Table 1' in str(t.get('table_caption', [])):
        html = t.get('table_body', '')
        # Show the section around Followup 2
        lines = html.split('</tr>')
        print("Looking for Followup 2 and Capital rows:")
        print("=" * 70)
        for i, line in enumerate(lines[10:20]):  # Rows 10-20 likely contain Followup 2
            print(f"Row {i+10}: {line}")
            print()
        break
