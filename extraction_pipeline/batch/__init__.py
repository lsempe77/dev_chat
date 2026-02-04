"""
Batch Processing Module
=======================

Batch classification and extraction across the corpus.
"""

from .classify import process_single_pdf, get_r2_client
from .extract import run_batch_extraction

__all__ = [
    'process_single_pdf',
    'get_r2_client',
    'run_batch_extraction',
]
