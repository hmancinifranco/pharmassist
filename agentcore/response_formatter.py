"""ResponseFormatter — Post-processes agent text to extract structured metadata.

Scans the agent's raw text output for <!--STRUCTURED:...--> markers emitted by
query_db (via PharmaToolkit._format_result), extracts the JSON metadata, and
builds the structured response payload consumed by the frontend.

Requirements: 21.1, 21.2, 21.3, 21.4, 21.5
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Regex to match <!--STRUCTURED:{...}--> markers (greedy on JSON content)
_STRUCTURED_PATTERN = re.compile(
    r"<!--STRUCTURED:(.*?)-->",
    re.DOTALL,
)

# SQL code block pattern: ```sql ... ```
_SQL_CODE_BLOCK_PATTERN = re.compile(
    r"```sql\s*\n?(.*?)\n?\s*```",
    re.DOTALL | re.IGNORECASE,
)

# SQL inline patterns: "Query ejecutada:" or "SQL:" followed by content
_SQL_INLINE_PATTERN = re.compile(
    r"(?:Query ejecutada|SQL)\s*:\s*(.+?)(?:\n\n|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# Temporal column indicators (Spanish)
_TEMPORAL_INDICATORS = {
    "fecha", "mes", "año", "anio", "periodo",
    "trimestre", "inicio", "fin", "dia", "semana",
    "year", "month", "date", "quarter",
}

# Maximum rows for structured table
_MAX_TABLE_ROWS = 100


class ResponseFormatter:
    """Post-processes agent text to build frontend-ready structured payload."""

    @staticmethod
    def format_response(agent_text: str, prompt: str) -> dict:
        """Extract structured data from agent response and build frontend payload.

        Args:
            agent_text: Raw text output from the agent (may contain <!--STRUCTURED:...-->).
            prompt: Original user prompt (used for generating suggestions).

        Returns:
            {
                "result": str,        # Clean text (structured markers removed)
                "structured": {
                    "table": {...} | None,
                    "sql": str | None,
                    "chart": {...} | None,
                    "suggestions": [str, str, str]
                }
            }
        """
        # 1. Extract all structured markers
        structured_data = ResponseFormatter._extract_structured_markers(agent_text)

        # 2. Clean text (remove markers)
        clean_text = _STRUCTURED_PATTERN.sub("", agent_text).strip()

        # 3. Extract SQL — prefer the exact executed query captured in the
        #    STRUCTURED marker (reliable); fall back to regex-scanning the
        #    agent's prose only if the marker has no sql.
        sql = None
        if structured_data and structured_data.get("sql"):
            sql = structured_data["sql"]
        if not sql:
            sql = ResponseFormatter._extract_sql(agent_text)

        # 4. Build table (if rows > 2)
        table = ResponseFormatter._build_table(structured_data)

        # 5. Detect chart data
        chart = ResponseFormatter._detect_chart_data(structured_data)

        # 6. Generate suggestions
        suggestions = ResponseFormatter._generate_suggestions(prompt, structured_data, clean_text)

        return {
            "result": clean_text,
            "structured": {
                "table": table,
                "sql": sql,
                "chart": chart,
                "suggestions": suggestions,
            },
        }

    @staticmethod
    def _extract_structured_markers(text: str) -> Optional[dict]:
        """Extract JSON from <!--STRUCTURED:...--> markers. Uses the LAST match.

        Multiple markers can appear if the agent calls query_db multiple times.
        We use the last one as the most relevant result.

        Returns:
            Parsed JSON dict or None if no valid marker found.
        """
        matches = _STRUCTURED_PATTERN.findall(text)
        if not matches:
            return None

        # Use the last match (most relevant)
        raw_json = matches[-1].strip()
        try:
            data = json.loads(raw_json)
            return data
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Malformed STRUCTURED JSON: %s", str(e)[:200])
            return None

    @staticmethod
    def _extract_sql(text: str) -> Optional[str]:
        """Extract SQL query from agent text.

        Looks for SQL in:
        1. Code blocks (```sql ... ```)
        2. Inline patterns ("Query ejecutada:" / "SQL:")

        Returns the LAST SQL found (most relevant), or None.
        """
        # Try code blocks first
        code_blocks = _SQL_CODE_BLOCK_PATTERN.findall(text)
        if code_blocks:
            return code_blocks[-1].strip()

        # Try inline patterns
        inline_matches = _SQL_INLINE_PATTERN.findall(text)
        if inline_matches:
            return inline_matches[-1].strip()

        return None

    @staticmethod
    def _build_table(structured_data: Optional[dict]) -> Optional[dict]:
        """Build table payload if rows > 2.

        Requirements: 21.1 (table when rows > 2), 21.5 (max 100 rows)
        """
        if not structured_data:
            return None

        rows = structured_data.get("rows", [])
        columns = structured_data.get("columns", [])

        if not rows or len(rows) <= 2:
            return None

        # Cap at 100 rows
        capped_rows = rows[:_MAX_TABLE_ROWS]

        return {
            "columns": columns,
            "rows": capped_rows,
        }

    @staticmethod
    def _detect_chart_data(structured_data: Optional[dict]) -> Optional[dict]:
        """Detect if data is suitable for charting.

        Logic:
        - Check column names for temporal indicators
        - If temporal column found AND there are numeric columns → suggest chart
        - type: "line" for time series, "bar" for categorical groupings

        Requirements: 21.2
        """
        if not structured_data:
            return None

        columns = structured_data.get("columns", [])
        rows = structured_data.get("rows", [])

        if not columns or not rows or len(rows) <= 2:
            return None

        # Find temporal column
        temporal_col = None
        for col in columns:
            col_lower = col.lower().strip()
            for indicator in _TEMPORAL_INDICATORS:
                if indicator in col_lower:
                    temporal_col = col
                    break
            if temporal_col:
                break

        if not temporal_col:
            return None

        # Find numeric columns (check first few rows to determine type)
        numeric_cols = []
        for col in columns:
            if col == temporal_col:
                continue
            # Sample first rows to determine if column is numeric
            is_numeric = False
            for row in rows[:5]:
                val = row.get(col)
                if val is not None and isinstance(val, (int, float)):
                    is_numeric = True
                    break
            if is_numeric:
                numeric_cols.append(col)

        if not numeric_cols:
            return None

        # Determine chart type
        # "line" for date-based time series, "bar" for categorical periods
        chart_type = "line"
        temporal_lower = temporal_col.lower()
        if any(ind in temporal_lower for ind in ("mes", "trimestre", "quarter", "month")):
            chart_type = "bar"

        # Build series
        series = [
            {"dataKey": col, "label": col}
            for col in numeric_cols
        ]

        return {
            "type": chart_type,
            "xAxis": temporal_col,
            "series": series,
        }

    @staticmethod
    def _generate_suggestions(
        prompt: str,
        structured_data: Optional[dict],
        clean_text: str,
    ) -> list:
        """Generate 2-3 contextual follow-up suggestions in Spanish (Argentina).

        Strategy:
        - Based on the original prompt topic
        - Based on the data returned (drill-down patterns)
        - Common follow-up patterns (más detalle, otro período, otra zona)

        Requirements: 21.4
        """
        suggestions = []
        prompt_lower = prompt.lower()

        # Detect topic from prompt
        has_ventas = any(w in prompt_lower for w in ("venta", "ventas", "factur", "unidades"))
        has_medicos = any(w in prompt_lower for w in ("médico", "medico", "doctor", "dr."))
        has_visitas = any(w in prompt_lower for w in ("visita", "visitado", "agenda"))
        has_top = any(w in prompt_lower for w in ("top", "ranking", "mayor", "principal"))
        has_zona = any(w in prompt_lower for w in ("zona", "barrio", "localidad"))
        has_producto = any(w in prompt_lower for w in ("producto", "medicamento", "marca"))
        has_temporal = any(w in prompt_lower for w in ("mes", "año", "trimestre", "evolución", "tendencia"))

        # Generate contextual suggestions
        if has_ventas:
            if has_top:
                suggestions.append("¿Y los productos con menor venta?")
            if has_zona:
                suggestions.append("¿Cómo fue la evolución mes a mes?")
            else:
                suggestions.append("¿Cómo se distribuyen por zona?")
            if not has_temporal:
                suggestions.append("¿Cuál es la tendencia vs el año anterior?")
            if has_producto:
                suggestions.append("¿Qué farmacias concentran más venta de ese producto?")

        elif has_visitas:
            suggestions.append("¿Qué médicos tengo pendientes de visitar?")
            suggestions.append("¿Cuál es mi frecuencia de visita promedio?")
            if has_medicos:
                suggestions.append("¿Qué productos le presenté en las últimas visitas?")

        elif has_medicos:
            suggestions.append("¿Cuál es su historial de visitas?")
            suggestions.append("¿Qué productos debería presentarle?")
            if not has_zona:
                suggestions.append("¿Qué otros médicos tengo en esa zona?")

        else:
            # Generic fallback suggestions
            suggestions.append("¿Podés mostrarme más detalle?")
            suggestions.append("¿Cómo se compara con el período anterior?")
            suggestions.append("¿Qué médicos están involucrados?")

        # Ensure 2-3 suggestions
        if len(suggestions) < 2:
            suggestions.append("¿Podés darme más detalle?")
        if len(suggestions) < 2:
            suggestions.append("¿Hay algún patrón relevante?")

        return suggestions[:3]
