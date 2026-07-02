"""
Voice mode response filter for BidiAgent compatibility.

Strips structured metadata and non-speakable content from agent responses
so that Nova Sonic text-to-speech can deliver clean, conversational output.

The BidiAgent sends `mode: "voice"` when invoking the Unified Agent. In this mode:
- <!--STRUCTURED:...--> markers are removed (JSON metadata for frontend)
- SQL code blocks (```sql...```) are removed (not useful for voice)
- Markdown table syntax (|...|) is removed (not speakable)
- Natural language explanations are preserved for text-to-speech

Requirements: 19.3, 19.4
"""

import re


def strip_for_voice(text: str) -> str:
    """Strip non-speakable content from agent response for voice mode.

    Removes structured metadata markers, SQL code blocks, and markdown tables
    while preserving conversational natural language text for text-to-speech.

    Args:
        text: Raw response text from the agent (may contain markdown, SQL, metadata).

    Returns:
        Clean text suitable for text-to-speech via Nova Sonic.

    Examples:
        >>> strip_for_voice("Tenés 42 médicos.\\n<!--STRUCTURED:{...}-->")
        'Tenés 42 médicos.'

        >>> strip_for_voice("Resultado:\\n```sql\\nSELECT * FROM x\\n```\\nListo.")
        'Resultado:\\nListo.'

        >>> strip_for_voice("| Col1 | Col2 |\\n|---|---|\\n| a | b |")
        ''
    """
    if not text:
        return ""

    result = text

    # 1. Remove <!--STRUCTURED:...--> markers (may span multiple lines)
    result = re.sub(r"<!--STRUCTURED:.*?-->", "", result, flags=re.DOTALL)

    # 2. Remove SQL code blocks (```sql ... ```)
    result = re.sub(r"```sql\b.*?```", "", result, flags=re.DOTALL | re.IGNORECASE)

    # 3. Remove generic code blocks that might contain SQL (```...```)
    # Only remove if the block looks like SQL (contains SELECT, FROM, etc.)
    def _remove_sql_codeblocks(match: re.Match) -> str:
        content = match.group(0).upper()
        if "SELECT" in content or "FROM" in content or "WHERE" in content:
            return ""
        return match.group(0)

    result = re.sub(r"```.*?```", _remove_sql_codeblocks, result, flags=re.DOTALL)

    # 4. Remove markdown table lines (lines starting with |)
    lines = result.split("\n")
    filtered_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip table rows (|...|) and separator rows (|---|---|)
        if stripped.startswith("|") and stripped.endswith("|"):
            continue
        # Skip table separator lines (---|---|---)
        if re.match(r"^\|?[\s\-:|]+\|?$", stripped):
            continue
        filtered_lines.append(line)

    result = "\n".join(filtered_lines)

    # 5. Clean up excessive whitespace from removed content
    # Collapse 3+ consecutive newlines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)

    # Strip leading/trailing whitespace
    result = result.strip()

    return result
