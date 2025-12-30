#!/usr/bin/env python
"""Debug: Compare EmbeddingGenerator with direct Cohere API."""

from src.ingestion.embeddings import EmbeddingGenerator
from src.config.settings import settings
import cohere
import os
from dotenv import load_dotenv
import numpy as np

load_dotenv()

eg = EmbeddingGenerator()
print(f'Provider: {eg.provider}')
print(f'Model: {eg.model}')
print(f'Settings model: {settings.embedding_model}')
print(f'Settings input_type: {settings.embedding_input_type}')

# Direct Cohere call
co = cohere.Client(api_key=os.environ['COHERE_API_KEY'])
text = 'graduation approach poverty'
query_resp = co.embed(texts=[text], model='embed-v4.0', input_type='search_query', embedding_types=['float'])
direct_vec = query_resp.embeddings.float_[0]

# Via EmbeddingGenerator
gen_vec = eg.embed_query(text)

sim = np.dot(direct_vec, gen_vec) / (np.linalg.norm(direct_vec) * np.linalg.norm(gen_vec))
print(f'\nDirect Cohere vec[:3]: {direct_vec[:3]}')
print(f'Generator vec[:3]: {gen_vec[:3]}')
print(f'Similarity between direct and generator: {sim:.6f}')
print(f'Dimensions: direct={len(direct_vec)}, generator={len(gen_vec)}')
