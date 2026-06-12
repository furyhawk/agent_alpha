"""Entry point — run with ``uv run python -m backend.main``.

The FastAPI app is created lazily inside ``if __name__`` so importing
this module has no side effects.
"""

import uvicorn


def main() -> None:
    """Start the Uvicorn development server."""
    uvicorn.run(
        "backend.app:create_app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        factory=True,
    )


if __name__ == "__main__":
    main()
