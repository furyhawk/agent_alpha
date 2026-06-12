.PHONY: install run dev clean setup \
        frontend-install frontend-dev frontend-build \
        compose-up compose-down compose-build compose-logs compose-rebuild

# ── Container runtime detection (Docker / Podman) ─────────────────────────
# Uses Docker if available, otherwise falls back to Podman.
DOCKER := $(shell command -v docker 2>/dev/null || command -v podman 2>/dev/null)
DOCKER_COMPOSE := $(shell command -v docker-compose 2>/dev/null || (command -v docker 2>/dev/null && echo "docker compose") || (command -v podman 2>/dev/null && echo "podman compose"))

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

# ── Containers (Docker / Podman) ───────────────────────────────────────────

compose-up:                        ## Start all containers in detached mode
	$(DOCKER_COMPOSE) up -d

compose-down:                      ## Stop and remove containers
	$(DOCKER_COMPOSE) down

compose-build:                     ## Build (or rebuild) all container images
	$(DOCKER_COMPOSE) build

compose-rebuild:                   ## Rebuild images & restart containers
	$(DOCKER_COMPOSE) up -d --build

compose-logs:                      ## Follow container logs
	$(DOCKER_COMPOSE) logs -f

# ── Utilities ──────────────────────────────────────────────────────────────

clean:                             ## Remove caches and build artifacts
	rm -rf __pycache__ .venv build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
