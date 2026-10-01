"""Print the OpenAPI schema, used by the frontend to generate its API types:

uv run python -m app.export_openapi > ../frontend/openapi/openapi.json
"""

import json
import sys

from app.main import app

if __name__ == "__main__":
    json.dump(app.openapi(), sys.stdout, indent=1)
