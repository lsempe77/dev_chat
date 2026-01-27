"""
Test binary quantization by uploading a test PDF to R2 and processing it.
"""
import os
import boto3
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# R2 client
r2 = boto3.client(
    's3',
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
)

BUCKET = os.environ.get('R2_BUCKET', 'devchat-pdfs')

def upload_test_pdf():
    """Upload a test PDF to R2."""
    test_pdf = Path("data/test_pdfs/alce_paper.pdf")
    if not test_pdf.exists():
        print(f"❌ Test PDF not found: {test_pdf}")
        return None
    
    key = f"input-pdfs/test_binary_quantization.pdf"
    
    print(f"📤 Uploading {test_pdf.name} to R2...")
    with open(test_pdf, 'rb') as f:
        r2.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=f.read(),
            ContentType='application/pdf'
        )
    
    print(f"✅ Uploaded to: {key}")
    return key

def list_input_pdfs():
    """List PDFs in input-pdfs folder."""
    print("\n📁 PDFs in input-pdfs/:")
    response = r2.list_objects_v2(Bucket=BUCKET, Prefix="input-pdfs/")
    for obj in response.get('Contents', []):
        print(f"   - {obj['Key']}")
    return response.get('Contents', [])

if __name__ == "__main__":
    # Upload test PDF
    key = upload_test_pdf()
    
    # List what's there
    list_input_pdfs()
    
    print(f"\n🚀 Now run:")
    print(f'   modal run infrastructure/modal_mineru.py --action single --pdf-key "{key}"')
