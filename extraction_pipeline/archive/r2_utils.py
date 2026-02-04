"""
R2 Infrastructure - List and process ALL studies in R2 bucket.

This module properly handles:
1. Numeric study IDs (e.g., 121058356)
2. Named studies (e.g., BRAC_programs/Bandiera_(2017))
3. Document variants (appendices, translations, supplements)
4. Deduplication via content hash

Uses DocumentRegistry for proper document management.
"""
import os
from dotenv import load_dotenv
load_dotenv()

os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

import boto3
import re
import json
from typing import Optional, Dict, List, Tuple
from enum import Enum

# R2 Configuration
BUCKET_NAME = 'devchat-pdfs'
RAG_PREFIX = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/'
JSON_PREFIX = RAG_PREFIX + 'json/'
MD_PREFIX = RAG_PREFIX + 'md/'
PDF_PREFIX = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/input-pdfs/'


class DocumentVariantType(str, Enum):
    """Type of document variant."""
    MAIN = "main"
    APPENDIX = "appendix"
    TRANSLATION = "translation"
    UNKNOWN = "unknown"


# Patterns for extracting metadata from filenames
FILENAME_PATTERNS = {
    # Content hash prefix (12 hex chars)
    'content_hash': re.compile(r'^([a-f0-9]{12})_'),
    
    # Numeric study ID (9 digits)
    'numeric_id': re.compile(r'(\d{9})'),
    
    # Appendix indicators
    'appendix': re.compile(r'[_-]?(appendix|app|suppl|supplement|si|sm|supporting)[_.-]?', re.I),
    
    # Language indicators
    'spanish': re.compile(r'[_-]?(spanish|espanol|esp)[_.-]?', re.I),
    'english': re.compile(r'[_-]?(english|eng|translated)[_.-]?', re.I),
    
    # BRAC author pattern
    'brac_author': re.compile(r'BRAC_programs_\(40\)_([A-Za-z]+)_?\(?(\d{4})\)?'),
}


def get_r2_client():
    """Get R2 storage client."""
    return boto3.client(
        's3',
        endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
    )


def extract_document_metadata(filename: str) -> Dict:
    """
    Extract detailed metadata from filename.
    
    Returns dict with:
    - study_id: Canonical study identifier
    - doc_id: Unique document ID (includes hash for uniqueness)
    - variant_type: main, appendix, translation
    - language: en, es, etc.
    - content_hash: If present in filename
    """
    result = {
        'study_id': None,
        'doc_id': None,
        'variant_type': DocumentVariantType.MAIN,
        'language': 'en',
        'content_hash': None,
        'is_appendix': False,
        'is_translation': False,
    }
    
    # Extract content hash prefix if present
    hash_match = FILENAME_PATTERNS['content_hash'].match(filename)
    if hash_match:
        result['content_hash'] = hash_match.group(1)
        filename_clean = filename[len(hash_match.group(0)):]
    else:
        filename_clean = filename
    
    # Remove extension
    filename_clean = re.sub(r'\.(json|pdf|md)$', '', filename_clean, flags=re.I)
    
    # Check for appendix/supplement
    if FILENAME_PATTERNS['appendix'].search(filename_clean):
        result['variant_type'] = DocumentVariantType.APPENDIX
        result['is_appendix'] = True
    
    # Check for language/translation
    if FILENAME_PATTERNS['spanish'].search(filename_clean):
        result['language'] = 'es'
        if 'translated' in filename_clean.lower() or 'english' in filename_clean.lower():
            result['variant_type'] = DocumentVariantType.TRANSLATION
            result['is_translation'] = True
    elif FILENAME_PATTERNS['english'].search(filename_clean):
        result['language'] = 'en'
        if 'translated' in filename_clean.lower():
            result['variant_type'] = DocumentVariantType.TRANSLATION
            result['is_translation'] = True
    
    # Extract study ID
    numeric_match = FILENAME_PATTERNS['numeric_id'].search(filename_clean)
    if numeric_match:
        base_id = numeric_match.group(1)
        result['study_id'] = base_id
        
        # Create unique doc_id including variant info
        suffix = ""
        if result['is_appendix']:
            suffix += "_appendix"
        if result['language'] != 'en':
            suffix += f"_{result['language']}"
        
        result['doc_id'] = f"{base_id}{suffix}"
    
    elif 'BRAC' in filename_clean:
        brac_match = FILENAME_PATTERNS['brac_author'].search(filename_clean)
        if brac_match:
            author = brac_match.group(1)
            year = brac_match.group(2)
            base_id = f"BRAC_{author}_{year}"
        else:
            # Extract author-like pattern
            author_match = re.search(r'([A-Z][a-z]+)[\s_]*\(?\s*(\d{4})\)?', filename_clean)
            if author_match:
                base_id = f"BRAC_{author_match.group(1)}_{author_match.group(2)}"
            else:
                base_id = filename_clean
        
        result['study_id'] = base_id
        
        # For BRAC studies with same author/year but different papers,
        # use content hash to distinguish them
        if result['content_hash']:
            # Use first 4 chars of hash to distinguish same-author papers
            result['doc_id'] = f"{base_id}_{result['content_hash'][:4]}"
        else:
            result['doc_id'] = base_id
    
    else:
        # Fallback: clean up filename
        cleaned = re.sub(r'^PDFs_of_included_programs_', '', filename_clean)
        cleaned = re.sub(r'^Bangladesh_-_all_BRAC_programs_', '', cleaned)
        result['study_id'] = cleaned
        result['doc_id'] = cleaned
    
    return result


def list_all_json_files(include_variants: bool = True) -> List[Dict]:
    """
    List ALL JSON files in R2 bucket with proper metadata extraction.
    
    Args:
        include_variants: If True, include all variants (appendices, translations).
                         If False, return only main documents (deduplicated by study_id).
    
    Returns list of dicts with:
    - key: Full S3 key
    - filename: Just the filename
    - study_id: Canonical study identifier (same for main + appendix)
    - doc_id: Unique document identifier (distinguishes variants)
    - identifier: Alias for doc_id (backward compatibility)
    - variant_type: main, appendix, translation
    - language: en, es, etc.
    - content_hash: If present in filename
    - size: File size in bytes
    """
    client = get_r2_client()
    paginator = client.get_paginator('list_objects_v2')
    
    files = []
    seen_study_ids = set()  # For deduplication when include_variants=False
    
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=JSON_PREFIX):
        for obj in page.get('Contents', []):
            key = obj['Key']
            filename = key.split('/')[-1]
            
            # Extract detailed metadata
            meta = extract_document_metadata(filename)
            
            # Skip if we're deduplicating and already saw this study
            if not include_variants:
                if meta['study_id'] in seen_study_ids:
                    continue
                seen_study_ids.add(meta['study_id'])
            
            files.append({
                'key': key,
                'filename': filename,
                'study_id': meta['study_id'],
                'doc_id': meta['doc_id'],
                'identifier': meta['doc_id'],  # Backward compatibility
                'variant_type': meta['variant_type'].value,
                'language': meta['language'],
                'content_hash': meta['content_hash'],
                'is_appendix': meta['is_appendix'],
                'is_translation': meta['is_translation'],
                'size': obj.get('Size', 0),
                # Legacy fields for backward compatibility
                'study_name': meta['study_id'] if not meta['study_id'] or not meta['study_id'].isdigit() else None,
            })
    
    return files


def list_unique_studies() -> List[Dict]:
    """
    List unique studies (one entry per study, preferring main document).
    
    Returns list with one entry per canonical study_id.
    """
    all_files = list_all_json_files(include_variants=True)
    
    # Group by study_id
    studies = {}
    for f in all_files:
        study_id = f['study_id']
        if study_id not in studies:
            studies[study_id] = []
        studies[study_id].append(f)
    
    # Select best variant for each study (prefer main, then English)
    result = []
    for study_id, variants in studies.items():
        # Sort: main first, then by language (en preferred)
        def sort_key(v):
            type_order = 0 if v['variant_type'] == 'main' else 1
            lang_order = 0 if v['language'] == 'en' else 1
            return (type_order, lang_order)
        
        variants.sort(key=sort_key)
        best = variants[0]
        best['variant_count'] = len(variants)
        best['has_appendix'] = any(v['is_appendix'] for v in variants)
        best['has_translation'] = any(v['is_translation'] for v in variants)
        result.append(best)
    
    return result


def load_json_by_key(key: str) -> Optional[dict]:
    """Load JSON directly by S3 key."""
    try:
        client = get_r2_client()
        response = client.get_object(Bucket=BUCKET_NAME, Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        print(f"  [ERROR] Failed to load {key}: {e}")
        return None


def load_json_by_identifier(identifier: str, files: List[Dict] = None, 
                            prefer_main: bool = True) -> Optional[Tuple[dict, Dict]]:
    """
    Load JSON by identifier (doc_id, study_id, or legacy study_name).
    
    Args:
        identifier: Document ID, study ID, or legacy name
        files: Pre-fetched file list (optional)
        prefer_main: If True and identifier matches study_id with variants, 
                     return main document (not appendix)
    
    Returns tuple of (json_data, file_info) or (None, None) if not found.
    """
    if files is None:
        files = list_all_json_files()
    
    # Collect all matches
    matches = []
    for f in files:
        if (f['doc_id'] == identifier or 
            f['study_id'] == identifier or 
            f.get('study_name') == identifier or 
            f['identifier'] == identifier):
            matches.append(f)
    
    if not matches:
        print(f"  [ERROR] No file found for identifier: {identifier}")
        return None, None
    
    # If multiple matches and prefer_main, sort to get main document first
    if len(matches) > 1 and prefer_main:
        def sort_key(m):
            type_order = 0 if m['variant_type'] == 'main' else 1
            lang_order = 0 if m['language'] == 'en' else 1
            return (type_order, lang_order)
        matches.sort(key=sort_key)
    
    # Load the best match
    best = matches[0]
    doc = load_json_by_key(best['key'])
    return (doc, best) if doc else (None, None)


def load_all_variants(study_id: str, files: List[Dict] = None) -> List[Tuple[dict, Dict]]:
    """
    Load all document variants for a study (main, appendices, translations).
    
    Returns list of (json_data, file_info) tuples.
    """
    if files is None:
        files = list_all_json_files()
    
    results = []
    for f in files:
        if f['study_id'] == study_id:
            doc = load_json_by_key(f['key'])
            if doc:
                results.append((doc, f))
    
    return results


def get_study_summary() -> Dict:
    """Get summary of all studies in R2 with variant analysis."""
    files = list_all_json_files(include_variants=True)
    unique_studies = list_unique_studies()
    
    # Analyze variants
    with_appendix = sum(1 for s in unique_studies if s.get('has_appendix'))
    with_translation = sum(1 for s in unique_studies if s.get('has_translation'))
    
    return {
        'total_files': len(files),
        'unique_studies': len(unique_studies),
        'studies_with_appendix': with_appendix,
        'studies_with_translation': with_translation,
        'files': files,
        'studies': unique_studies
    }


if __name__ == '__main__':
    print("=" * 70)
    print("R2 DOCUMENT INVENTORY (Production)")
    print("=" * 70)
    
    summary = get_study_summary()
    files = summary['files']
    studies = summary['studies']
    
    print(f"\nTotal JSON files: {summary['total_files']}")
    print(f"Unique studies: {summary['unique_studies']}")
    print(f"Studies with appendices: {summary['studies_with_appendix']}")
    print(f"Studies with translations: {summary['studies_with_translation']}")
    
    # Group files by variant type
    by_type = {}
    for f in files:
        vtype = f['variant_type']
        if vtype not in by_type:
            by_type[vtype] = []
        by_type[vtype].append(f)
    
    print("\n" + "=" * 70)
    print("DOCUMENT BREAKDOWN BY TYPE")
    print("=" * 70)
    for vtype, vfiles in sorted(by_type.items()):
        print(f"\n{vtype.upper()} documents ({len(vfiles)}):")
        for f in sorted(vfiles, key=lambda x: x['doc_id']):
            extra = ""
            if f['language'] != 'en':
                extra = f" [{f['language']}]"
            print(f"  {f['doc_id']}{extra}")
    
    # Show studies with multiple variants
    multi_variant = [s for s in studies if s.get('variant_count', 1) > 1]
    if multi_variant:
        print("\n" + "=" * 70)
        print(f"STUDIES WITH MULTIPLE VARIANTS ({len(multi_variant)})")
        print("=" * 70)
        for s in sorted(multi_variant, key=lambda x: x['study_id']):
            flags = []
            if s.get('has_appendix'):
                flags.append('appendix')
            if s.get('has_translation'):
                flags.append('translation')
            print(f"  {s['study_id']}: {s['variant_count']} files ({', '.join(flags)})")
