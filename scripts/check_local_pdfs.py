import os
import hashlib
from pathlib import Path

def compute_file_hash(filepath):
    """Compute MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        # Read in chunks to handle large files
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def check_unique_pdfs(directory):
    """Check for unique PDFs in the given directory."""
    dir_path = Path(directory)
    
    if not dir_path.exists():
        print(f"Error: Directory not found: {directory}")
        return

    print(f"Scanning directory: {directory}")
    
    pdf_files = list(dir_path.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files.")

    hashes = {}
    duplicates = []

    print("Computing hashes...")
    for pdf_path in pdf_files:
        try:
            file_hash = compute_file_hash(pdf_path)
            if file_hash in hashes:
                duplicates.append((pdf_path.name, hashes[file_hash]))
            else:
                hashes[file_hash] = pdf_path.name
        except Exception as e:
            print(f"Error processing {pdf_path.name}: {e}")

    unique_count = len(hashes)
    print(f"\nUnique PDFs by content: {unique_count}")
    
    if duplicates:
        print(f"\nFound {len(duplicates)} duplicates:")
        for dup_name, original_name in duplicates:
            print(f"  - {dup_name} is a duplicate of {original_name}")
    else:
        print("\nNo duplicates found.")

    if unique_count == 94:
        print("\n✅ CONFIRMED: There are exactly 94 unique PDFs.")
    else:
        print(f"\n❌ MISMATCH: Expected 94 unique PDFs, found {unique_count}.")

if __name__ == "__main__":
    target_dir = r"C:\Users\LucasSempe\Downloads\OneDrive_2025-12-19\PDFs of included programs"
    check_unique_pdfs(target_dir)
