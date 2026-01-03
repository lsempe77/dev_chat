"""Debug why specific PDFs aren't being processed."""
import boto3
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def check_pdf_status():
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")

    # Missing PDFs from check_r2_pdfs
    missing_doc_ids = [
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

    # Get all PDFs and their base names
    print("Scanning all PDFs in R2...")
    all_pdfs = []
    continuation_token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "input-pdfs/"}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = s3.list_objects_v2(**kwargs)
        if "Contents" in resp:
            all_pdfs.extend([o["Key"] for o in resp["Contents"] if o["Key"].endswith(".pdf")])
        if resp.get("IsTruncated"):
            continuation_token = resp["NextContinuationToken"]
        else:
            break
    
    print(f"Found {len(all_pdfs)} total PDFs")
    
    # Get existing JSON outputs
    existing_outputs = set()
    continuation_token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "outputs/json/"}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = s3.list_objects_v2(**kwargs)
        if "Contents" in resp:
            existing_outputs.update([Path(o["Key"]).stem for o in resp["Contents"]])
        if resp.get("IsTruncated"):
            continuation_token = resp["NextContinuationToken"]
        else:
            break
    
    print(f"Found {len(existing_outputs)} JSON outputs")
    
    # Check each missing PDF
    print("\n--- Missing PDF Status ---")
    for doc_id in missing_doc_ids:
        pdf_key = f"input-pdfs/{doc_id}.pdf"
        
        # Check if PDF exists
        try:
            s3.head_object(Bucket=bucket, Key=pdf_key)
            pdf_exists = True
            pdf_info = s3.head_object(Bucket=bucket, Key=pdf_key)
            pdf_size = pdf_info.get("ContentLength", 0) / (1024 * 1024)  # MB
        except:
            pdf_exists = False
            pdf_size = 0
        
        # Check if JSON output exists
        has_json = doc_id in existing_outputs
        
        # Extract base name
        stem = doc_id
        if "_" in stem and len(stem.split("_")[0]) == 8:
            base_name = "_".join(stem.split("_")[1:])
        else:
            base_name = stem
        
        # Check for duplicates with same base name
        duplicates = []
        for pdf in all_pdfs:
            other_stem = Path(pdf).stem
            if "_" in other_stem and len(other_stem.split("_")[0]) == 8:
                other_base = "_".join(other_stem.split("_")[1:])
            else:
                other_base = other_stem
            
            if other_base == base_name and other_stem != doc_id:
                # Check if this duplicate is indexed
                dup_has_json = other_stem in existing_outputs
                duplicates.append((other_stem, dup_has_json))
        
        # Print status
        status = []
        if pdf_exists:
            status.append(f"PDF exists ({pdf_size:.1f}MB)")
        else:
            status.append("PDF MISSING!")
        
        if has_json:
            status.append("JSON exists")
        else:
            status.append("NO JSON")
        
        if duplicates:
            dup_info = ", ".join([f"{d[0]} ({'indexed' if d[1] else 'not indexed'})" for d in duplicates])
            status.append(f"DUPLICATES: {dup_info}")
        
        print(f"  {doc_id}: {' | '.join(status)}")


if __name__ == "__main__":
    check_pdf_status()
