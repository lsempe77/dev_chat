"""
R2 Storage Client
=================

Cloudflare R2 storage client for loading MineRU JSON documents.

Supports multi-tenant architecture:
- Each RAG project has its own R2 path: rags/{project_id}/outputs/json/
- Default project is the original graduation corpus
"""

import os
import json
from typing import Optional, List, Tuple

import boto3
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()


# Default project ID (graduation corpus)
DEFAULT_PROJECT_ID = "0816e8d3-ab23-417c-bf3f-e45531411c73"
DEFAULT_BUCKET = "devchat-pdfs"


def get_r2_client():
    """
    Get R2 storage client.
    
    Required environment variables:
    - CLOUDFLARE_ACCOUNT_ID
    - R2_ACCESS_KEY_ID
    - R2_SECRET_ACCESS_KEY
    """
    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    if not account_id:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID environment variable not set")
    
    return boto3.client(
        's3',
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
    )


def get_project_prefix(project_id: str = DEFAULT_PROJECT_ID) -> str:
    """Get R2 prefix for a project's JSON outputs."""
    return f"rags/{project_id}/outputs/json/"


def load_mineru_json(
    study_id: str,
    project_id: str = DEFAULT_PROJECT_ID,
    bucket: str = DEFAULT_BUCKET,
    prefix: Optional[str] = None,
) -> Optional[dict]:
    """
    Load MineRU JSON from R2 storage.
    
    Args:
        study_id: Study ID to load
        project_id: RAG project UUID (each project has its own document corpus)
        bucket: R2 bucket name
        prefix: Override path prefix (if None, uses project_id to build path)
        
    Returns:
        Parsed JSON document, or None if not found
    """
    # Build prefix from project_id if not explicitly provided
    if prefix is None:
        prefix = get_project_prefix(project_id)
    
    try:
        client = get_r2_client()
        
        # List objects to find the file matching this study_id
        response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=500)
        
        # Find matching file
        matching_key = None
        for obj in response.get('Contents', []):
            key = obj['Key']
            if study_id in key:
                matching_key = key
                break
        
        if not matching_key:
            logger.warning(f"No JSON found for study_id {study_id} in {prefix}")
            return None
        
        # Download and parse
        response = client.get_object(Bucket=bucket, Key=matching_key)
        content = response['Body'].read().decode('utf-8')
        doc = json.loads(content)
        
        # Store source key for reference
        doc['source_key'] = matching_key
        
        logger.info(f"Loaded MineRU JSON: {matching_key}")
        return doc
        
    except Exception as e:
        logger.error(f"Failed to load MineRU JSON for {study_id}: {e}")
        return None


def list_available_studies(
    project_id: str = DEFAULT_PROJECT_ID,
    bucket: str = DEFAULT_BUCKET,
    prefix: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """
    List all available documents in R2 storage for a project.
    
    Args:
        project_id: RAG project UUID
        bucket: R2 bucket name
        prefix: Override path prefix
        
    Returns:
        List of (study_id, filename) tuples found in storage
    """
    if prefix is None:
        prefix = get_project_prefix(project_id)
    
    try:
        client = get_r2_client()
        response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1000)
        
        studies = []
        for obj in response.get('Contents', []):
            key = obj['Key']
            filename = key.split('/')[-1]
            
            if not filename.endswith('.json'):
                continue
            
            # Extract study ID from filename
            # Handle formats: 121058356.json, BRAC_Ahmed_2009.json, hash_studyname.json
            base_name = filename.replace('.json', '')
            
            # Try to find numeric study ID
            parts = base_name.split('_')
            study_id = None
            
            # Check if it's a numeric ID
            for part in parts:
                if part.isdigit() and len(part) > 5:
                    study_id = part
                    break
            
            # If no numeric ID, use the whole base_name (e.g., BRAC studies)
            if study_id is None:
                # Remove hash prefix if present (8 char hex at start)
                if len(parts) > 1 and len(parts[0]) == 8 and all(c in '0123456789abcdef' for c in parts[0].lower()):
                    study_id = '_'.join(parts[1:])
                else:
                    study_id = base_name
            
            studies.append((study_id, filename))
        
        logger.info(f"Found {len(studies)} documents in {prefix}")
        return studies
        
    except Exception as e:
        logger.error(f"Failed to list studies for project {project_id}: {e}")
        return []


def list_projects(bucket: str = DEFAULT_BUCKET) -> List[dict]:
    """
    List all RAG projects that have documents in R2.
    
    Returns:
        List of dicts with project_id and document_count
    """
    try:
        client = get_r2_client()
        
        # List all prefixes under rags/
        response = client.list_objects_v2(
            Bucket=bucket, 
            Prefix="rags/",
            Delimiter="/",
        )
        
        projects = []
        for prefix_obj in response.get('CommonPrefixes', []):
            prefix = prefix_obj['Prefix']
            # Extract project_id from rags/{project_id}/
            parts = prefix.strip('/').split('/')
            if len(parts) >= 2:
                project_id = parts[1]
                
                # Count documents in this project
                json_prefix = f"rags/{project_id}/outputs/json/"
                docs_response = client.list_objects_v2(
                    Bucket=bucket,
                    Prefix=json_prefix,
                    MaxKeys=1000,
                )
                doc_count = len([
                    o for o in docs_response.get('Contents', [])
                    if o['Key'].endswith('.json')
                ])
                
                if doc_count > 0:
                    projects.append({
                        'project_id': project_id,
                        'document_count': doc_count,
                        'json_prefix': json_prefix,
                    })
        
        return projects
        
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        return []
