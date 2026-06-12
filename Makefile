.PHONY: install run dev clean setup \
        frontend-install frontend-dev frontend-build

# ── Backend Setup ──────────────────────────────────────────────────────────

install:                           ## Install Python dependencies via uv
	uv sync

setup: .env                         ## Full first-time backend setup
	uv run python -m backend.main

.env: .env.example
	cp .env.example .env
	@echo "Created .env from .env.example — edit it with your real values."

# ── Backend Development ────────────────────────────────────────────────────

run:                               ## Start the backend (reload enabled)
	uv run python -m backend.main

dev:                               ## Alias for run
	uv run python -m backend.main

# ── Frontend ───────────────────────────────────────────────────────────────

frontend-install:                  ## Install frontend dependencies
	cd frontend && bun install

frontend-dev:                      ## Start the Vite dev server
	cd frontend && bun run dev

frontend-build:                    ## Build frontend for production
	cd frontend && bun run build

# ── Utilities ──────────────────────────────────────────────────────────────

clean:                             ## Remove caches and build artifacts
	rm -rf __pycache__ .venv build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
