"""
DevChat v2.0 SOTA - Conversation Memory

Manages conversation history for multi-turn interactions.
Stores chat sessions and messages in PostgreSQL for persistence.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import ChatSession, ChatMessage
from src.database.connection import async_session
from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ConversationMemory:
    """
    Manages conversation history for context-aware responses.
    
    Features:
    - Session-based message storage
    - Message retrieval with configurable window
    - Context injection for LLM prompts
    """
    
    def __init__(self, max_history_messages: int = 10):
        """
        Initialize conversation memory.
        
        Args:
            max_history_messages: Maximum messages to include in context
        """
        self.max_history_messages = max_history_messages
    
    async def create_session(
        self, 
        user_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """
        Create a new chat session.
        
        Args:
            user_id: Optional user identifier
            title: Optional session title
            
        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        
        if async_session is None:
            logger.warning("Database not initialized, returning in-memory session")
            return session_id
        
        try:
            async with async_session() as db:
                chat_session = ChatSession(
                    id=session_id,
                    user_id=user_id,
                    title=title or "New Conversation",
                )
                db.add(chat_session)
                await db.commit()
                
            logger.info(f"Created new chat session: {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return session_id  # Return ID anyway for in-memory fallback
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        query_type: Optional[str] = None,
        model_used: Optional[str] = None,
        num_sources: Optional[int] = None,
        citations: Optional[List[Dict]] = None,
        total_time_ms: Optional[float] = None,
    ) -> Optional[int]:
        """
        Add a message to a session.
        
        Args:
            session_id: Session to add message to
            role: 'user' or 'assistant'
            content: Message content
            query_type: Type of query (for assistant messages)
            model_used: LLM model used (for assistant messages)
            num_sources: Number of sources cited
            citations: Citation data
            total_time_ms: Response time
            
        Returns:
            Message ID if saved, None if in-memory mode
        """
        if async_session is None:
            logger.debug("Database not initialized, message not persisted")
            return None
        
        try:
            async with async_session() as db:
                # Check if session exists, create if not
                result = await db.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
                session = result.scalar_one_or_none()
                
                if not session:
                    # Auto-create session
                    session = ChatSession(id=session_id, title="Auto-created session")
                    db.add(session)
                    await db.flush()
                
                # Add message
                message = ChatMessage(
                    session_id=session_id,
                    role=role,
                    content=content,
                    query_type=query_type,
                    model_used=model_used,
                    num_sources=num_sources,
                    citations=citations,
                    total_time_ms=total_time_ms,
                )
                db.add(message)
                await db.commit()
                await db.refresh(message)
                
                # Update session title from first user message
                if role == "user" and session.title in [None, "New Conversation", "Auto-created session"]:
                    session.title = content[:100] + ("..." if len(content) > 100 else "")
                    await db.commit()
                
                return message.id
                
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            return None
    
    async def get_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a session.
        
        Args:
            session_id: Session to retrieve
            limit: Max messages (default: self.max_history_messages)
            
        Returns:
            List of message dictionaries
        """
        limit = limit or self.max_history_messages
        
        if async_session is None:
            return []
        
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(desc(ChatMessage.created_at))
                    .limit(limit)
                )
                messages = result.scalars().all()
                
                # Return in chronological order
                return [m.to_dict() for m in reversed(messages)]
                
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []
    
    async def get_context_for_prompt(
        self,
        session_id: str,
        max_tokens: int = 2000,
    ) -> str:
        """
        Get conversation history formatted for LLM context injection.
        
        Args:
            session_id: Session to retrieve
            max_tokens: Approximate max tokens (uses char estimate)
            
        Returns:
            Formatted conversation history string
        """
        # Rough estimate: 4 chars per token
        max_chars = max_tokens * 4
        
        history = await self.get_history(session_id)
        
        if not history:
            return ""
        
        # Build context string
        context_parts = ["Previous conversation:"]
        total_chars = len(context_parts[0])
        
        for msg in history:
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"]
            
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            
            line = f"{role}: {content}"
            
            if total_chars + len(line) > max_chars:
                break
                
            context_parts.append(line)
            total_chars += len(line)
        
        return "\n".join(context_parts)
    
    async def get_user_sessions(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get recent sessions for a user.
        
        Args:
            user_id: User identifier
            limit: Max sessions to return
            
        Returns:
            List of session dictionaries
        """
        if async_session is None:
            return []
        
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(ChatSession)
                    .where(ChatSession.user_id == user_id)
                    .order_by(desc(ChatSession.updated_at))
                    .limit(limit)
                )
                sessions = result.scalars().all()
                
                return [
                    {
                        "id": s.id,
                        "title": s.title,
                        "created_at": s.created_at.isoformat(),
                        "updated_at": s.updated_at.isoformat(),
                    }
                    for s in sessions
                ]
                
        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return []


# Global instance
_memory: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    """Get or create the global conversation memory instance."""
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory
