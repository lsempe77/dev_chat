"""
Extraction Pipeline Package
===========================

Production-ready extraction of treatment effects from impact evaluation papers.

Main entry points:
- `pipeline.py`: Monolithic pipeline (backward compatible)
- `cli_v2.py`: Modular CLI with comprehensive flags

Modules:
- `core/`: Infrastructure (errors, LLM client, storage, config)
- `adapters/`: Schema conversion (DataFrame ↔ Pydantic)
- `postprocessing/`: Effect size calculations
"""

__version__ = "2.1.0"
