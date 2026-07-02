"""Tests for APM data isolation in system prompt.

Verifies that the system prompt correctly injects the authenticated APM_ID
into SQL scoping rules, ensuring each APM only sees their own data.

Requirements tested: 8.4, 8.6
"""

import pytest

from agentcore.prompts import build_system_prompt


# ---------------------------------------------------------------------------
# Test: APM_ID injection into system prompt
# ---------------------------------------------------------------------------

class TestApmDataIsolation:
    """Validate that build_system_prompt scopes all SQL queries by APM_ID."""

    def test_apm_id_injected_in_cartera_medica_filter(self):
        """Req 8.6: cartera_medica queries MUST filter by id_apm = authenticated APM."""
        prompt = build_system_prompt("APM_TEST_123", "CICLO_1")
        assert "cartera_medica.apm_id = 'APM_TEST_123'" in prompt

    def test_apm_id_injected_in_agenda_filter(self):
        """Req 8.4: agenda queries MUST filter by the authenticated APM."""
        prompt = build_system_prompt("APM_TEST_123", "CICLO_1")
        assert "agenda.apm_id = 'APM_TEST_123'" in prompt

    def test_apm_id_injected_in_linea_apm_filter(self):
        """Req 8.4: linea_apm queries MUST filter by the authenticated APM."""
        prompt = build_system_prompt("APM_TEST_123", "CICLO_1")
        assert "linea_apm.id_apm = 'APM_TEST_123'" in prompt

    def test_isolation_rule_text_present(self):
        """Req 8.4: The prompt MUST contain the explicit isolation rule."""
        prompt = build_system_prompt("APM_TEST_123", "CICLO_1")
        assert "SIEMPRE" in prompt
        assert "filtrar por el APM autenticado" in prompt

    def test_sql_examples_use_apm_id(self):
        """Req 8.4: All SQL examples in the prompt use the injected apm_id."""
        prompt = build_system_prompt("APM_DEMO_999", "CICLO_2")
        # Every SQL WHERE clause referencing apm_id should use the injected value
        assert "apm_id = 'APM_DEMO_999'" in prompt
        # Should NOT contain the raw placeholder
        assert "{apm_id}" not in prompt

    def test_ciclo_actual_injected(self):
        """Verify ciclo_actual is also injected (complementary to APM isolation)."""
        prompt = build_system_prompt("APM_TEST_123", "CICLO_2025_Q1")
        assert "CICLO_2025_Q1" in prompt
        assert "{ciclo_actual}" not in prompt

    def test_different_apm_ids_produce_different_prompts(self):
        """Req 8.6: Each APM gets a uniquely scoped prompt — no cross-APM leakage."""
        prompt_a = build_system_prompt("APM_ALFA", "CICLO_1")
        prompt_b = build_system_prompt("APM_BETA", "CICLO_1")

        assert "APM_ALFA" in prompt_a
        assert "APM_BETA" not in prompt_a
        assert "APM_BETA" in prompt_b
        assert "APM_ALFA" not in prompt_b

    def test_no_unresolved_placeholders(self):
        """Ensure no f-string placeholders remain after injection."""
        prompt = build_system_prompt("APM_X", "CICLO_Y")
        # Check that no curly-brace placeholders remain
        assert "{apm_id}" not in prompt
        assert "{ciclo_actual}" not in prompt
