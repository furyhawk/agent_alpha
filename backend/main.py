"""Entry point — run with `uv run python -m backend.main` or `uvicorn backend.app:create_app`."""

import uvicorn

from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("backend.app:create_app", host="0.0.0.0", port=8000, reload=True, factory=True)
