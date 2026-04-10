# Aquila-Hammurabi

> **The Law, Decoded.** — AI-powered legal reasoning, document intelligence, and structured jurisprudence navigation.

---

## Overview

Aquila-Hammurabi is a vertically integrated legal AI system that ingests legal corpora (statutes, case law, contracts), stores them in a queryable knowledge graph and hybrid vector index, and exposes structured IRAC reasoning via a LangGraph agent and FastAPI REST interface.

```
┌──────────────────────────────────────────────────────────────────┐
│                        INTERFACE LAYER                           │
│   React/Vite UI (Pro + Student modes)  │  FastAPI REST  │  CLI   │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│                       REASONING LAYER                            │
│  LangGraph Agent  │  IRAC Chains  │  Drafting Chains  │  MCP     │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│                       KNOWLEDGE LAYER                            │
│   Neo4j (legal graph)  │  Qdrant (vectors)  │  PostgreSQL        │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│                       INGESTION LAYER                            │
│  PDF/DOCX  │  Structured Codes (XML/JSON)  │  Case Law  │  NER   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Milestones

| Milestone | Status | Deliverable |
|-----------|--------|-------------|
| M0 — Foundation | ✅ Done | Dev environment, CI, Docker stack, Neo4j legal constraints |
| M1 — Ingestion | ✅ Done | Ingest PDF contracts, statutory XML, case law; NER pipeline |
| M2 — Knowledge | ✅ Done | Legal graph (article + citation network) + hybrid semantic search |
| M3 — Reasoning | ⬜ Planned | IRAC agent, risk scoring, specialised legal chains |
| M4 — API + UI | ⬜ Planned | FastAPI backend + Pro mode UI + Student mode UI |
| M5 — Advanced | ⬜ Planned | Multi-jurisdiction, versioning, doctrine layer, benchmarking |

---

## Requirements

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker + Docker Compose (for Neo4j, Qdrant, PostgreSQL, MCP server)
- An OpenAI-compatible LLM and embeddings endpoint (default: local [Ollama](https://ollama.ai))

---

## Quick Start

### 1 — Install dependencies

```bash
uv sync --all-groups
```

### 2 — Start the dev stack

```bash
docker compose up -d
```

This starts four services:

| Service | Default host port | Purpose |
|---------|-------------------|---------|
| Neo4j Bolt | `7688` | Legal knowledge graph |
| Neo4j Browser | `7476` | Graph visualisation UI |
| Qdrant REST | `6335` | Vector + hybrid search |
| PostgreSQL | `5433` | Session & document persistence |
| MCP server | `8081` | Read-only Cypher tool for the agent |

> Ports are intentionally offset from defaults to avoid conflicts with local installations.

### 3 — Apply Neo4j constraints

Run the following file once against a fresh database (connect to `bolt://localhost:7688`):

```bash
# Using cypher-shell (if installed)
cypher-shell -a bolt://localhost:7688 -u neo4j -p password \
  --file scripts/neo4j_constraints.cypher

# Or paste the contents of scripts/neo4j_constraints.cypher
# into the Neo4j Browser at http://localhost:7475
```

### 4 — Configure environment (optional)

Copy `.env.example` to `.env` and override any defaults:

```bash
# LLM endpoint (default: local Ollama)
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.2

# Embeddings (default: nomic-embed-text via Ollama)
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768

# Neo4j
NEO4J_URI=bolt://localhost:7688
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6335

# Application
DEFAULT_JURISDICTION=FR
```

---

## Development Commands

All commands use `uv run` — no manual venv activation needed.

```bash
# Install all deps including dev group
uv sync --all-groups

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/knowledge/test_service.py

# Run a single test by name
uv run pytest -k "test_ingest_single_article_chunk"

# Lint (report only)
uv run ruff check .

# Format (auto-fix)
uv run ruff format .

# Format check only (CI mode — no writes)
uv run ruff format --check .

# Type-check
uv run mypy hammurabi/
```

---

## Package Layout

```
hammurabi/
  config.py          ← Pydantic Settings (single module-level `settings` instance)
  ingestion/         ← Phase 1: loaders, segmenter, NER, chunker
  knowledge/         ← Phase 2: Neo4j graph client, Qdrant vector store, service facade
  reasoning/         ← Phase 3: LangGraph agent, IRAC chains, risk scoring  (planned)
  api/               ← Phase 4: FastAPI routes, auth, streaming               (planned)

scripts/
  neo4j_constraints.cypher   ← Run once after stack start

tests/
  ingestion/         ← Phase 1 unit tests
  knowledge/         ← Phase 2 unit tests (mocked — no live services required)
```

---

### Vector collections

| Collection | Content |
|------------|---------|
| `hammurabi_statutes` | Statute article chunks |
| `hammurabi_cases` | Case law / judgment chunks |
| `hammurabi_documents` | User-uploaded contracts and regulations |

Each collection carries two named vector spaces:
- `dense` — cosine similarity (OpenAI-compatible embeddings endpoint)
- `sparse` — TF-based sparse vector (BM25-style, no external model required)

Hybrid search uses server-side `Prefetch(dense) + Prefetch(sparse)` → `FusionQuery(Fusion.RRF)`.

---

## Configuration Reference

| Env var | Default | Description |
|---------|---------|-------------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible LLM endpoint |
| `LLM_API_KEY` | `ollama` | LLM API key |
| `LLM_MODEL` | `llama3.2` | Model name |
| `EMBEDDING_BASE_URL` | `http://localhost:11434/v1` | Embeddings endpoint |
| `EMBEDDING_API_KEY` | `ollama` | Embeddings API key |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embeddings model name |
| `EMBEDDING_DIM` | `768` | Embedding vector dimension |
| `NEO4J_URI` | `bolt://localhost:7688` | Neo4j Bolt URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `password` | Neo4j password |
| `QDRANT_HOST` | `localhost` | Qdrant REST host |
| `QDRANT_PORT` | `6335` | Qdrant REST port |
| `QDRANT_API_KEY` | _(none)_ | Qdrant API key (unauthenticated local dev) |
| `POSTGRES_DSN` | `postgresql+psycopg://aquila:aquila@localhost:5433/aquila` | PostgreSQL DSN |
| `DEFAULT_JURISDICTION` | `FR` | ISO 3166-1 jurisdiction injected into retrieval |
| `API_KEY` | _(none)_ | X-API-Key header value; blank = open mode |
| `DEBUG` | `false` | Enable debug logging and reload |
| `LANGSMITH_API_KEY` | _(none)_ | Optional LangSmith tracing |
| `LANGSMITH_PROJECT` | `hammurabi` | LangSmith project name |

---

## CI

GitHub Actions runs on every push and pull request:

1. `uv run ruff check .` — lint
2. `uv run ruff format --check .` — format check
3. `uv run mypy hammurabi/` — strict type check
4. `uv run pytest` — full test suite

All checks must pass before merge.

---

## License

MIT
