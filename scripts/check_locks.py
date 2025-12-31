import boto3
import os
from dotenv import load_dotenv

load_dotenv()

def check_locks():
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")

    print("Checking for locks in R2...")
    
    locks = []
    continuation_token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "locks/"}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = s3.list_objects_v2(**kwargs)
        if "Contents" in resp:
            locks.extend([o["Key"] for o in resp["Contents"]])
        if resp.get("IsTruncated"):
            continuation_token = resp["NextContinuationToken"]
        else:
            break
            
    print(f"Found {len(locks)} locks.")
    for lock in locks:
        print(f"  - {lock}")

if __name__ == "__main__":
    check_locks()
