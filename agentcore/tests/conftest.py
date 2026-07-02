"""
Conftest for agentcore tests — mocks external dependencies not available locally.

The agentcore module depends on bedrock_agentcore, strands, sqlalchemy, etc.
which may not be installed in the local dev environment. This conftest patches
those imports so tests can run without the full dependency stack.
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock external modules that aren't installed locally
# ---------------------------------------------------------------------------

# bedrock_agentcore
mock_bedrock_agentcore = MagicMock()
mock_bedrock_agentcore.BedrockAgentCoreApp = MagicMock


# strands
mock_strands = MagicMock()
mock_strands.Agent = MagicMock
mock_strands.tool = lambda f: f  # @tool decorator passthrough
mock_strands_models = MagicMock()
mock_strands_models.BedrockModel = MagicMock

# sqlalchemy
mock_sqlalchemy = MagicMock()
mock_sqlalchemy_pool = MagicMock()

# boto3
mock_boto3 = MagicMock()

# pandas
mock_pd = MagicMock()

# Register mocks in sys.modules (only if not already available)
_mocks = {
    "bedrock_agentcore": mock_bedrock_agentcore,
    "strands": mock_strands,
    "strands.models": mock_strands_models,
    "sqlalchemy": mock_sqlalchemy,
    "sqlalchemy.pool": mock_sqlalchemy_pool,
}

for mod_name, mock_mod in _mocks.items():
    if mod_name not in sys.modules:
        sys.modules[mod_name] = mock_mod
