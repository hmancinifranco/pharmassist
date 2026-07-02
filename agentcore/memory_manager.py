"""
MemoryManager — AgentCore Memory integration for STM and Semantic Memory.

Provides:
- Short-term memory (STM): store conversation events within a session
- Semantic search: cross-session retrieval of relevant past interactions
- Session history: get events from current session

All methods implement graceful degradation: catch exceptions, return empty/False,
and NEVER fail the agent request due to memory issues.
"""

import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)


class MemoryManager:
    """Gestiona STM y Semantic Memory via AgentCore Memory API."""

    def __init__(self, memory_id: str | None = None):
        self.memory_id = memory_id or os.environ.get("AGENTCORE_MEMORY_ID", "")
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-initialize the AgentCore client."""
        if self._client is None:
            region = os.environ.get("AWS_REGION", "us-east-1")
            self._client = boto3.client("bedrock-agentcore", region_name=region)
        return self._client

    @staticmethod
    def build_actor_id(apm_id: str) -> str:
        """Build consistent actor_id: 'apm-{apm_id}'."""
        return f"apm-{apm_id}"

    def store_event(
        self, actor_id: str, session_id: str, messages: list[dict]
    ) -> bool:
        """Store conversation messages as a memory event (STM).

        Args:
            actor_id: Actor identifier, format 'apm-{apm_id}'.
            session_id: Session identifier for grouping events.
            messages: List of dicts with 'role' and 'content' keys.

        Returns:
            True if the event was stored successfully, False otherwise.
        """
        try:
            if not self.memory_id:
                logger.warning("AGENTCORE_MEMORY_ID not configured, skipping store_event")
                return False

            if not messages:
                return False

            payload = [
                {
                    "conversationMessage": {
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                    }
                }
                for msg in messages
                if msg.get("content")
            ]

            if not payload:
                return False

            self.client.create_memory_event(
                memoryId=self.memory_id,
                actorId=actor_id,
                sessionId=session_id,
                payload=payload,
            )

            logger.info(
                "Memory event stored: actor=%s, session=%s, messages=%d",
                actor_id,
                session_id,
                len(payload),
            )
            return True

        except Exception as e:
            logger.error("Failed to store memory event: %s", str(e))
            return False

    def retrieve_context(
        self, actor_id: str, query: str, top_k: int = 3
    ) -> str:
        """Semantic search for relevant memories across sessions.

        Args:
            actor_id: Actor identifier used as namespace, format 'apm-{apm_id}'.
            query: Search query for semantic retrieval.
            top_k: Maximum number of records to retrieve.

        Returns:
            Concatenated text of relevant memory records, or empty string on failure.
        """
        try:
            if not self.memory_id:
                logger.warning("AGENTCORE_MEMORY_ID not configured, skipping retrieve_context")
                return ""

            if not query.strip():
                return ""

            response = self.client.retrieve_memory_records(
                memoryId=self.memory_id,
                namespace=actor_id,
                searchQuery=query,
                topK=top_k,
            )

            records = response.get("memoryRecords", [])
            if not records:
                return ""

            # Extract text content from memory records
            texts = []
            for record in records:
                content = record.get("content", {})
                text = content.get("text", "") if isinstance(content, dict) else ""
                if text:
                    texts.append(text)

            if not texts:
                return ""

            context = "\n---\n".join(texts)
            logger.info(
                "Retrieved %d memory records for actor=%s", len(texts), actor_id
            )
            return context

        except Exception as e:
            logger.error("Failed to retrieve memory context: %s", str(e))
            return ""

    def get_session_history(
        self, actor_id: str, session_id: str, max_events: int = 10
    ) -> list[dict]:
        """Get events from the current session (STM).

        Args:
            actor_id: Actor identifier, format 'apm-{apm_id}'.
            session_id: Session identifier to retrieve events for.
            max_events: Maximum number of events to retrieve.

        Returns:
            List of event dicts with payload, or empty list on failure.
        """
        try:
            if not self.memory_id:
                logger.warning("AGENTCORE_MEMORY_ID not configured, skipping get_session_history")
                return []

            response = self.client.list_memory_events(
                memoryId=self.memory_id,
                actorId=actor_id,
                sessionId=session_id,
                maxResults=min(max_events, 100),
            )

            events = response.get("events", [])
            logger.info(
                "Retrieved %d session events: actor=%s, session=%s",
                len(events),
                actor_id,
                session_id,
            )
            return events

        except Exception as e:
            logger.error("Failed to get session history: %s", str(e))
            return []
