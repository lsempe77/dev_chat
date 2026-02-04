"""Find and optionally delete duplicate R2 entries."""
import pandas as pd
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

# Load data
summary = pd.read_csv('extraction_pipeline/outputs/batch_summary_20260201_163017.csv')
class_df = pd.read_csv('extraction_pipeline/outputs/batch_classification_20260201_163017.csv')

# Find duplicates
dupes = summary[summary.duplicated(subset=['study_id'], keep=False)].sort_values(['study_id', 'total_tables'])

print("=" * 80)
print("DUPLICATE STUDY ENTRIES")
print("=" * 80)

# For each duplicate study, find the R2 keys and decide which to keep
keys_to_delete = []

for sid in dupes['study_id'].unique():
    sub = class_df[class_df['study_id'] == sid]
    keys = sub['r2_key'].unique()
    
    # Get table counts for each key
    key_counts = {}
    for k in keys:
        count = len(class_df[class_df['r2_key'] == k])
        key_counts[k] = count
    
    print(f"\nStudy: {sid}")
    for k, count in sorted(key_counts.items(), key=lambda x: -x[1]):
        print(f"  {count:3d} tables: {k}")
    
    # Keep the one with more tables, delete the rest
    sorted_keys = sorted(key_counts.items(), key=lambda x: -x[1])
    keep_key = sorted_keys[0][0]
    delete_keys = [k for k, _ in sorted_keys[1:]]
    
    print(f"  → KEEP: {keep_key}")
    for dk in delete_keys:
        print(f"  → DELETE: {dk}")
        keys_to_delete.append(dk)

print("\n" + "=" * 80)
print(f"KEYS TO DELETE: {len(keys_to_delete)}")
print("=" * 80)
for k in keys_to_delete:
    print(f"  {k}")

# Ask for confirmation
print("\n" + "=" * 80)
confirm = input("Delete these keys from R2? (yes/no): ")

if confirm.lower() == 'yes':
    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    r2 = boto3.client(
        's3',
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
    )
    
    for key in keys_to_delete:
        try:
            r2.delete_object(Bucket='devchat-pdfs', Key=key)
            print(f"  ✓ Deleted: {key}")
        except Exception as e:
            print(f"  ✗ Error deleting {key}: {e}")
    
    print("\nDone!")
else:
    print("Cancelled.")
