#!/usr/bin/env python
"""Test the full agent retrieval after deduplication."""

import asyncio
from src.agents.devchat_agent import DevChatAgent, SearchSettings

async def test():
    agent = DevChatAgent()
    settings = SearchSettings(max_studies=5, use_claim_ledger=True)
    resp = await agent.chat('What is the graduation approach to poverty reduction?', search_settings=settings)
    
    print(f'Answer length: {len(resp.answer)} chars')
    print(f'Sources: {resp.num_sources}')
    print()
    for i, cite in enumerate(resp.citations, 1):
        title = cite.get('title', 'Unknown')[:50]
        authors = cite.get('authors', [])
        print(f'[{i}] {title}...')
        print(f'    Authors: {authors}')
    
    print('\n' + '='*60)
    print('ANSWER PREVIEW:')
    print('='*60)
    print(resp.answer[:500] + '...')

asyncio.run(test())
