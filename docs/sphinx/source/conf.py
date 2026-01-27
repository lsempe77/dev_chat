# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Add project root to path for autodoc
sys.path.insert(0, os.path.abspath('../../..'))

# -- Project information -----------------------------------------------------
project = 'DevChat'
copyright = '2026, 3ie'
author = '3ie'
release = '2.0'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',  # Google/NumPy docstring support
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
    'sphinx_autodoc_typehints',
    'myst_parser',  # Markdown support
]

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__',
    'show-inheritance': True,
}

# Generate autosummary pages
autosummary_generate = True

# Napoleon settings (Google-style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = None

# Type hints settings
typehints_defaults = 'comma'
always_document_param_types = True

# MyST (Markdown) settings
myst_enable_extensions = [
    'colon_fence',
    'deflist',
]
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'fastapi': ('https://fastapi.tiangolo.com/', None),
}

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_title = 'DevChat Documentation'

html_theme_options = {
    'navigation_depth': 4,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'includehidden': True,
    'titles_only': False,
}

# -- Mock imports for autodoc ------------------------------------------------
# Mock heavy dependencies that aren't needed for docs
autodoc_mock_imports = [
    'modal',
    'qdrant_client',
    'cohere',
    'langfuse',
    'supabase',
    'neo4j',
    'magic_pdf',
    'torch',
    'transformers',
    'boto3',
    'botocore',
    'fuzzywuzzy',
    'anthropic',
    'openai',
    'tiktoken',
    'sentence_transformers',
    'ragas',
    'datasets',
    'pandas',
    'numpy',
    'openpyxl',
    'pyzotero',
    'httpx',
    'bs4',
    'lxml',
    'pymupdf',
    'fitz',
    'modal_lib',
]

# Suppress specific warnings
suppress_warnings = ['autodoc.import_failure']
