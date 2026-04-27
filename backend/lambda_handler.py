"""
AWS Lambda handler for the PharmAssist FastAPI application.

Uses Mangum to adapt the ASGI FastAPI app to the Lambda event/response format.
Supports dual-path imports so the handler works whether the code is packaged
from the project root (``from backend.main import app``) or from inside the
``backend/`` directory (``from main import app``).
"""

from mangum import Mangum

try:
    from backend.main import app
except ImportError:
    from main import app  # type: ignore[no-redef]

handler = Mangum(app, lifespan="off")
