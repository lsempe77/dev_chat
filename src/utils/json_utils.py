"""JSON utilities for handling LLM-generated JSON."""

import json
import re
from typing import Any


def safe_json_loads(text: str) -> Any:
    """
    Parse JSON with automatic fixing of common LLM errors.
    
    LLMs sometimes produce invalid escape sequences like \\e, \\a, \\s
    which are not valid JSON escapes. This function fixes them before parsing.
    
    Valid JSON escape sequences are: \\", \\\\, \\/, \\b, \\f, \\n, \\r, \\t, \\uXXXX
    """
    # Fix invalid escape sequences (e.g., \e, \a, \s) 
    # Only escape backslashes that aren't followed by valid JSON escape chars
    text = re.sub(r'\\([^"\\/bfnrtu])', r'\\\1', text)
    
    return json.loads(text)


def extract_json_from_llm_response(text: str) -> Any:
    """
    Extract and parse JSON from an LLM response.
    
    Handles:
    - Raw JSON
    - JSON wrapped in ```json ... ``` code blocks
    - JSON wrapped in ``` ... ``` code blocks
    - Invalid escape sequences
    """
    text = text.strip()
    
    # Extract from code blocks
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0]
    elif '```' in text:
        text = text.split('```')[1].split('```')[0]
    
    return safe_json_loads(text.strip())
