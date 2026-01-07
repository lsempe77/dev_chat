"""
Modal App Configuration

Defines the Modal app, images, secrets, volumes, and constants.
This module must be imported by all other modules that use @app.function decorators.
"""

import modal

# ============================================================================
# Modal App
# ============================================================================

app = modal.App("devchat-mineru")

# ============================================================================
# Constants
# ============================================================================

# Collection name for Qdrant - using enhanced collection with post-processing
QDRANT_COLLECTION_NAME = "devchat_v2_enhanced"

# ============================================================================
# Docker Image
# ============================================================================

# Base image with system dependencies
base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "libgl1-mesa-glx",
        "libglib2.0-0",
        "libsm6",
        "libxext6",
        "libxrender-dev",
    )
    .pip_install(
        "mineru[core]>=2.6.0",
        "boto3",
        "cohere>=5.0.0",
        "qdrant-client>=1.7.0",
        "httpx",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "supabase>=2.0.0",
    )
    .add_local_python_source("modal_lib")  # Include modal_lib package in container
)

# ============================================================================
# Volumes
# ============================================================================

# Volume for caching HuggingFace models (persists across runs)
model_cache = modal.Volume.from_name("mineru-model-cache", create_if_missing=True)

# ============================================================================
# Secrets
# ============================================================================

r2_secret = modal.Secret.from_name("r2-credentials")
qdrant_secret = modal.Secret.from_name("qdrant-credentials")
cohere_secret = modal.Secret.from_name("cohere-credentials")
openrouter_secret = modal.Secret.from_name("openrouter-credentials")
supabase_secret = modal.Secret.from_name("SUPABASE")
