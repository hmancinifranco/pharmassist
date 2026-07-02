"""Tests for MemoryManager — AgentCore Memory integration."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestMemoryManagerBuildActorId:
    """Tests for the static build_actor_id method."""

    def test_build_actor_id_basic(self):
        from memory_manager import MemoryManager

        assert MemoryManager.build_actor_id("Demo APM") == "apm-Demo APM"

    def test_build_actor_id_numeric(self):
        from memory_manager import MemoryManager

        assert MemoryManager.build_actor_id("12345") == "apm-12345"

    def test_build_actor_id_empty(self):
        from memory_manager import MemoryManager

        assert MemoryManager.build_actor_id("") == "apm-"


class TestMemoryManagerInit:
    """Tests for MemoryManager initialization."""

    def test_init_with_explicit_memory_id(self):
        from memory_manager import MemoryManager

        mm = MemoryManager(memory_id="test-memory-123")
        assert mm.memory_id == "test-memory-123"

    def test_init_from_env_var(self):
        from memory_manager import MemoryManager

        with patch.dict(os.environ, {"AGENTCORE_MEMORY_ID": "env-memory-456"}):
            mm = MemoryManager()
            assert mm.memory_id == "env-memory-456"

    def test_init_no_memory_id(self):
        from memory_manager import MemoryManager

        with patch.dict(os.environ, {}, clear=True):
            # Remove AGENTCORE_MEMORY_ID if present
            env_copy = os.environ.copy()
            env_copy.pop("AGENTCORE_MEMORY_ID", None)
            with patch.dict(os.environ, env_copy, clear=True):
                mm = MemoryManager(memory_id=None)
                assert mm.memory_id == ""


class TestMemoryManagerStoreEvent:
    """Tests for store_event method — graceful degradation."""

    def _make_manager(self):
        from memory_manager import MemoryManager

        mm = MemoryManager(memory_id="test-memory-id")
        mm._client = MagicMock()
        return mm

    def test_store_event_success(self):
        mm = self._make_manager()
        mm._client.create_memory_event.return_value = {}

        result = mm.store_event(
            actor_id="apm-test",
            session_id="sess-001",
            messages=[
                {"role": "user", "content": "Hola"},
                {"role": "assistant", "content": "¡Hola! ¿En qué puedo ayudarte?"},
            ],
        )

        assert result is True
        mm._client.create_memory_event.assert_called_once_with(
            memoryId="test-memory-id",
            actorId="apm-test",
            sessionId="sess-001",
            payload=[
                {"conversationMessage": {"role": "user", "content": "Hola"}},
                {
                    "conversationMessage": {
                        "role": "assistant",
                        "content": "¡Hola! ¿En qué puedo ayudarte?",
                    }
                },
            ],
        )

    def test_store_event_empty_messages(self):
        mm = self._make_manager()

        result = mm.store_event("apm-test", "sess-001", [])
        assert result is False
        mm._client.create_memory_event.assert_not_called()

    def test_store_event_no_memory_id(self):
        from memory_manager import MemoryManager

        mm = MemoryManager(memory_id="")
        mm._client = MagicMock()

        result = mm.store_event(
            "apm-test", "sess-001", [{"role": "user", "content": "test"}]
        )
        assert result is False
        mm._client.create_memory_event.assert_not_called()

    def test_store_event_exception_returns_false(self):
        mm = self._make_manager()
        mm._client.create_memory_event.side_effect = Exception("Service unavailable")

        result = mm.store_event(
            "apm-test", "sess-001", [{"role": "user", "content": "test"}]
        )
        assert result is False

    def test_store_event_filters_empty_content(self):
        mm = self._make_manager()
        mm._client.create_memory_event.return_value = {}

        result = mm.store_event(
            actor_id="apm-test",
            session_id="sess-001",
            messages=[
                {"role": "user", "content": "Hola"},
                {"role": "assistant", "content": ""},
                {"role": "user", "content": "Segunda pregunta"},
            ],
        )

        assert result is True
        call_args = mm._client.create_memory_event.call_args
        payload = call_args.kwargs["payload"]
        assert len(payload) == 2  # Empty content message filtered out


class TestMemoryManagerRetrieveContext:
    """Tests for retrieve_context method — graceful degradation."""

    def _make_manager(self):
        from memory_manager import MemoryManager

        mm = MemoryManager(memory_id="test-memory-id")
        mm._client = MagicMock()
        return mm

    def test_retrieve_context_success(self):
        mm = self._make_manager()
        mm._client.retrieve_memory_records.return_value = {
            "memoryRecords": [
                {"content": {"text": "El Dr. Herrera prefiere visitas matutinas."}},
                {"content": {"text": "Último pedido de PAMOXET fue en marzo."}},
            ]
        }

        result = mm.retrieve_context("apm-test", "Dr. Herrera", top_k=3)

        assert "Dr. Herrera prefiere visitas matutinas" in result
        assert "PAMOXET" in result
        assert "---" in result  # separator between records
        mm._client.retrieve_memory_records.assert_called_once_with(
            memoryId="test-memory-id",
            namespace="apm-test",
            searchQuery="Dr. Herrera",
            topK=3,
        )

    def test_retrieve_context_empty_results(self):
        mm = self._make_manager()
        mm._client.retrieve_memory_records.return_value = {"memoryRecords": []}

        result = mm.retrieve_context("apm-test", "something")
        assert result == ""

    def test_retrieve_context_no_memory_id(self):
        from memory_manager import MemoryManager

        mm = MemoryManager(memory_id="")
        mm._client = MagicMock()

        result = mm.retrieve_context("apm-test", "query")
        assert result == ""
        mm._client.retrieve_memory_records.assert_not_called()

    def test_retrieve_context_empty_query(self):
        mm = self._make_manager()

        result = mm.retrieve_context("apm-test", "   ")
        assert result == ""
        mm._client.retrieve_memory_records.assert_not_called()

    def test_retrieve_context_exception_returns_empty(self):
        mm = self._make_manager()
        mm._client.retrieve_memory_records.side_effect = Exception("Timeout")

        result = mm.retrieve_context("apm-test", "query")
        assert result == ""

    def test_retrieve_context_records_without_text(self):
        mm = self._make_manager()
        mm._client.retrieve_memory_records.return_value = {
            "memoryRecords": [
                {"content": {"text": "Valid record"}},
                {"content": {}},  # No text
                {"content": {"text": ""}},  # Empty text
            ]
        }

        result = mm.retrieve_context("apm-test", "query")
        assert result == "Valid record"


class TestMemoryManagerGetSessionHistory:
    """Tests for get_session_history method — graceful degradation."""

    def _make_manager(self):
        from memory_manager import MemoryManager

        mm = MemoryManager(memory_id="test-memory-id")
        mm._client = MagicMock()
        return mm

    def test_get_session_history_success(self):
        mm = self._make_manager()
        fake_events = [
            {"eventId": "1", "payload": [{"conversationMessage": {"role": "user", "content": "Hola"}}]},
            {"eventId": "2", "payload": [{"conversationMessage": {"role": "assistant", "content": "¡Hola!"}}]},
        ]
        mm._client.list_memory_events.return_value = {"events": fake_events}

        result = mm.get_session_history("apm-test", "sess-001")

        assert len(result) == 2
        assert result[0]["eventId"] == "1"
        mm._client.list_memory_events.assert_called_once_with(
            memoryId="test-memory-id",
            actorId="apm-test",
            sessionId="sess-001",
            maxResults=10,
        )

    def test_get_session_history_no_memory_id(self):
        from memory_manager import MemoryManager

        mm = MemoryManager(memory_id="")
        mm._client = MagicMock()

        result = mm.get_session_history("apm-test", "sess-001")
        assert result == []
        mm._client.list_memory_events.assert_not_called()

    def test_get_session_history_exception_returns_empty(self):
        mm = self._make_manager()
        mm._client.list_memory_events.side_effect = Exception("Network error")

        result = mm.get_session_history("apm-test", "sess-001")
        assert result == []

    def test_get_session_history_respects_max_events(self):
        mm = self._make_manager()
        mm._client.list_memory_events.return_value = {"events": []}

        mm.get_session_history("apm-test", "sess-001", max_events=5)

        call_args = mm._client.list_memory_events.call_args
        assert call_args.kwargs["maxResults"] == 5

    def test_get_session_history_caps_max_at_100(self):
        mm = self._make_manager()
        mm._client.list_memory_events.return_value = {"events": []}

        mm.get_session_history("apm-test", "sess-001", max_events=200)

        call_args = mm._client.list_memory_events.call_args
        assert call_args.kwargs["maxResults"] == 100
