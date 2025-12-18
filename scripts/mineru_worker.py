"""
MinerU Celery Worker for Queue-Based PDF Processing

This worker:
1. Pulls PDF paths from Redis/SQS queue
2. Downloads PDF from S3
3. Processes with MinerU
4. Uploads results to S3
5. Triggers embedding pipeline

Usage:
    celery -A scripts.mineru_worker worker --loglevel=info --concurrency=1
    
Environment Variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379/0)
    AWS_S3_BUCKET: S3 bucket for PDFs
    MINERU_DEVICE: cuda or cpu (default: cuda if available)
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Optional
import logging

# Celery setup
from celery import Celery

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
S3_BUCKET = os.getenv("AWS_S3_BUCKET", "devchat-pdfs")

# Initialize Celery
app = Celery(
    "mineru_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Celery configuration
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 min max per PDF
    task_soft_time_limit=1500,  # Warn at 25 min
    worker_prefetch_multiplier=1,  # Process one at a time (GPU memory)
    task_acks_late=True,  # Requeue on failure
)

# Lazy-load processor to avoid loading models at import time
_processor = None

def get_processor():
    """Lazy-load MinerU processor (loads models only once)."""
    global _processor
    if _processor is None:
        logger.info("Loading MinerU processor (this may take 30-60 seconds)...")
        from pdf_processor import MinerUProcessor
        _processor = MinerUProcessor()
        logger.info("MinerU processor loaded successfully")
    return _processor


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_pdf_from_s3(
    self,
    s3_key: str,
    output_prefix: str = "parsed",
    metadata: Optional[dict] = None,
) -> dict:
    """
    Process a PDF from S3 and upload results.
    
    Args:
        s3_key: S3 key for the PDF (e.g., "pdfs/raw/paper123.pdf")
        output_prefix: S3 prefix for output (e.g., "pdfs/parsed")
        metadata: Optional metadata to include in results
        
    Returns:
        dict with processing results and S3 output locations
    """
    import boto3
    
    logger.info(f"Processing PDF: s3://{S3_BUCKET}/{s3_key}")
    
    try:
        s3 = boto3.client("s3")
        
        # Download PDF to temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            s3.download_file(S3_BUCKET, s3_key, tmp_pdf.name)
            pdf_path = Path(tmp_pdf.name)
        
        # Process with MinerU
        processor = get_processor()
        result = processor.process_pdf(pdf_path)
        
        if not result.success:
            raise Exception(f"MinerU processing failed: {result.error_message}")
        
        # Prepare output
        pdf_name = Path(s3_key).stem
        output_data = {
            "source_key": s3_key,
            "title": result.title or pdf_name,
            "authors": result.authors,
            "year": result.year,
            "abstract": result.abstract,
            "content": result.content,
            "tables": result.tables,
            "formulas": result.formulas,
            "page_count": result.page_count,
            "metadata": metadata or {},
        }
        
        # Upload markdown
        md_key = f"{output_prefix}/{pdf_name}.md"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=md_key,
            Body=result.content.encode("utf-8"),
            ContentType="text/markdown",
        )
        
        # Upload structured JSON
        json_key = f"{output_prefix}/{pdf_name}.json"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=json_key,
            Body=json.dumps(output_data, indent=2, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        
        # Clean up temp file
        pdf_path.unlink(missing_ok=True)
        
        logger.info(f"Successfully processed {s3_key} -> {json_key}")
        
        return {
            "success": True,
            "source_key": s3_key,
            "markdown_key": md_key,
            "json_key": json_key,
            "title": output_data["title"],
            "page_count": result.page_count,
            "table_count": len(result.tables),
            "formula_count": len(result.formulas),
        }
        
    except Exception as e:
        logger.error(f"Failed to process {s3_key}: {e}")
        
        # Retry with exponential backoff
        raise self.retry(exc=e)


@app.task(bind=True)
def process_pdf_local(self, pdf_path: str, output_dir: str = None) -> dict:
    """
    Process a local PDF file.
    
    Args:
        pdf_path: Local path to PDF file
        output_dir: Directory for output (default: same as PDF)
        
    Returns:
        dict with processing results
    """
    logger.info(f"Processing local PDF: {pdf_path}")
    
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    output_dir = Path(output_dir) if output_dir else pdf_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process with MinerU
    processor = get_processor()
    result = processor.process_pdf(pdf_path)
    
    if not result.success:
        return {
            "success": False,
            "error": result.error_message,
            "pdf_path": str(pdf_path),
        }
    
    # Save outputs
    pdf_name = pdf_path.stem
    
    # Save markdown
    md_path = output_dir / f"{pdf_name}.md"
    md_path.write_text(result.content, encoding="utf-8")
    
    # Save JSON
    json_path = output_dir / f"{pdf_name}.json"
    output_data = {
        "title": result.title,
        "authors": result.authors,
        "year": result.year,
        "abstract": result.abstract,
        "tables": result.tables,
        "formulas": result.formulas,
        "page_count": result.page_count,
    }
    json_path.write_text(
        json.dumps(output_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    logger.info(f"Saved: {md_path}, {json_path}")
    
    return {
        "success": True,
        "pdf_path": str(pdf_path),
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "title": result.title,
        "page_count": result.page_count,
        "table_count": len(result.tables),
        "formula_count": len(result.formulas),
    }


@app.task
def batch_process_folder(folder_path: str, output_dir: str = None) -> dict:
    """
    Queue all PDFs in a folder for processing.
    
    Args:
        folder_path: Path to folder containing PDFs
        output_dir: Output directory (default: {folder}/parsed)
        
    Returns:
        dict with queued task IDs
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")
    
    output_dir = output_dir or str(folder / "parsed")
    
    pdf_files = list(folder.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDFs in {folder}")
    
    # Queue each PDF
    task_ids = []
    for pdf_path in pdf_files:
        task = process_pdf_local.delay(str(pdf_path), output_dir)
        task_ids.append({
            "pdf": pdf_path.name,
            "task_id": task.id,
        })
    
    return {
        "queued": len(task_ids),
        "output_dir": output_dir,
        "tasks": task_ids,
    }


# Health check task
@app.task
def health_check() -> dict:
    """Check if worker is healthy and GPU is available."""
    import torch
    
    return {
        "status": "healthy",
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "processor_loaded": _processor is not None,
    }


if __name__ == "__main__":
    # For testing locally
    import sys
    
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        result = process_pdf_local(pdf_path)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python mineru_worker.py <pdf_path>")
        print("Or run as Celery worker:")
        print("  celery -A scripts.mineru_worker worker --loglevel=info")
