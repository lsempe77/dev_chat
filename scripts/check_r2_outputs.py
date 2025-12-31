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

    missing_files = [
        "11aa6d14_121294813",
        "18c72c7b_121058368",
        "2facbce1_121498842_Spanish"
    ]

    print(f"Checking R2 outputs for {len(missing_files)} sample missing files...")
    
    for doc_id in missing_files:
        key = f"outputs/json/{doc_id}.json"
        try:
            s3.head_object(Bucket=bucket, Key=key)
            print(f"  ✅ Found output JSON: {key}")
        except Exception:
            print(f"  ❌ Missing output JSON: {key}")

if __name__ == "__main__":
    check_outputs()
