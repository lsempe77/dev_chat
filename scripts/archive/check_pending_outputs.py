import boto3
import os
from dotenv import load_dotenv

load_dotenv()

def check_outputs():
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")

    # All 11 missing PDFs
    missing_files = [
        "11aa6d14_121294813",
        "18c72c7b_121058368",
        "2facbce1_121498842_Spanish",
        "55046f5e_121058373_app",
        "6768afa9_Misha_(2019)",
        "9caf18f1_121378379",
        "a27f8abb_Montoya_(2023)",
        "ae3690b4_121499003",
        "b589c87c_122182713",
        "bf649dd7_121378216",
        "c180f7f8_121328483_Banerjee_(2022)",
    ]

    print(f"Checking R2 outputs for {len(missing_files)} missing files...")
    
    has_output = []
    no_output = []
    
    for doc_id in missing_files:
        key = f"outputs/json/{doc_id}.json"
        try:
            s3.head_object(Bucket=bucket, Key=key)
            print(f"  ✅ {doc_id}: JSON exists (needs re-indexing only)")
            has_output.append(doc_id)
        except Exception:
            print(f"  ❌ {doc_id}: No JSON (needs full processing)")
            no_output.append(doc_id)
    
    print(f"\nSummary:")
    print(f"  - Has output, needs re-indexing: {len(has_output)}")
    print(f"  - No output, needs full processing: {len(no_output)}")

if __name__ == "__main__":
    check_outputs()
