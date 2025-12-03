# Vessels: Executive Summary

## Overview

**Vessels** is an autonomous agent framework that extends Agent Zero with a unified graph-based storage layer powered by FalkorDB and Graphiti. It represents a paradigm shift in agent architecture, replacing traditional file-based and vector database systems with a **temporal knowledge graph** where all data—memories, chats, knowledge, and settings—are stored as interconnected graph entities.

---

## Core Value Proposition

| Traditional Agent Systems | Vessels Framework |
|--------------------------|-------------------|
| FAISS vector databases + files | FalkorDB temporal graph |
| JSON file chat storage | Graph episodes with relationships |
| File-based knowledge import | Graph-based entity extraction |
| Vector similarity search only | Hybrid search (semantic + keyword + graph traversal) |
| No temporal awareness | Full temporal tracking with time-based queries |
| Siloed data systems | Unified graph storage layer |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Vessels Agent                          │
├─────────────────────────────────────────────────────────────┤
│  Memories    │  Chats     │  Knowledge   │  Settings        │
│  (episodes)  │ (episodes) │  (episodes)  │  (episodes)      │
└──────────────┴────────────┴──────────────┴──────────────────┘
                             │
                   ┌─────────▼─────────┐
                   │     Graphiti      │
                   │  Hybrid Search    │
                   │  • Semantic       │
                   │  • Keyword (BM25) │
                   │  • Graph Traversal│
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │     FalkorDB      │
                   │  Graph Database   │
                   └───────────────────┘
```

### Technology Stack

- **FalkorDB**: High-performance graph database for persistent storage
- **Graphiti**: Temporal knowledge graph library for intelligent search and entity management
- **Agent Zero**: Base autonomous agent framework providing core agent capabilities
- **LiteLLM**: Support for 30+ LLM providers (OpenAI, Anthropic, Ollama, Google, etc.)
- **TigerBeetle**: Optional double-entry bookkeeping for financial operations

---

## Specialized Agent Profiles

Vessels provides four purpose-built agent profiles, each optimized for specific domains:

### 1. Vessels (Default)
- **Role**: General-purpose autonomous AI assistant
- **Capabilities**: Task orchestration, code execution, tool usage, subordinate delegation
- **Use Case**: Primary user-facing agent for broad task handling

### 2. Master Developer
- **Role**: Elite software architect and full-stack engineer
- **Capabilities**:
  - System design (microservices, monoliths, serverless)
  - Polyglot programming across paradigms
  - DevOps automation and CI/CD pipelines
  - Performance optimization and security implementation
- **Use Case**: Complex software engineering tasks

### 3. Deep Researcher
- **Role**: Autonomous research intelligence system
- **Capabilities**:
  - Literature synthesis and meta-analysis
  - Market analysis and competitive intelligence
  - Statistical analysis and predictive modeling
  - Cross-domain knowledge synthesis
- **Use Case**: Corporate, scientific, and academic research

### 4. Security Specialist
- **Role**: Penetration testing and security assessment
- **Capabilities**:
  - Red team and blue team operations
  - Vulnerability identification and testing
  - Security automation
- **Use Case**: Authorized security testing and assessments

---

## Core Components

### Graph Store (`python/helpers/graph_store.py`)

The unified storage layer providing:

| Domain | Functionality |
|--------|---------------|
| **Memories** | Semantic search with temporal tracking |
| **Chats** | Conversation persistence as graph episodes |
| **Knowledge** | Document ingestion with entity extraction |
| **Settings** | Configuration stored as graph properties |
| **Secrets** | Secure credential storage |
| **Content** | Prompts, docs, instruments as graph entities |

### Memory System (`python/helpers/memory.py`)

Graph-based memory with organized areas:

- **MAIN**: Primary storage for general information
- **FRAGMENTS**: Auto-generated conversation fragments
- **SOLUTIONS**: Successful solutions from past interactions
- **INSTRUMENTS**: Tool descriptions and capabilities

### Search Capabilities

Through Graphiti, Vessels provides three complementary search methods:

1. **Semantic Search**: Vector similarity based on embeddings
2. **Keyword Search**: BM25 full-text search
3. **Graph Traversal**: Relationship-based navigation through entity connections

### Guardian System (`python/helpers/guardians.py`)

Built-in security layer providing:
- Input sanitization and validation
- Prompt injection protection
- Security event logging
- External data flow guards

---

## Deployment Options

### Docker Compose (Development)
```bash
docker compose up -d
```
Launches FalkorDB and TigerBeetle containers.

### Standalone Container (Production)
```bash
docker build -f docker/standalone/Dockerfile -t vessels:latest .
docker run -d -p 8080:80 vessels:latest
```
All-in-one container with Vessels, FalkorDB, TigerBeetle, and Web UI.

### Local Python
```bash
pip install -r requirements.txt
python run_ui.py    # Web UI at http://localhost:50001
python run_cli.py   # CLI interface
```

### Service Ports

| Port | Service | Purpose |
|------|---------|---------|
| 8080/50001 | Web UI | Flask real-time streaming interface |
| 6379 | FalkorDB | Graph database |
| 3000 | TigerBeetle | Financial ledger |

---

## Configuration

### Environment Variables (`.env`)

```bash
# FalkorDB
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_DATABASE=vessels

# Graphiti (Knowledge Graph Construction)
GRAPHITI_LLM_PROVIDER=openai
GRAPHITI_LLM_MODEL=gpt-4o-mini
GRAPHITI_EMBEDDING_MODEL=text-embedding-3-small

# LLM API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=...

# TigerBeetle (Optional)
TIGERBEETLE_HOST=localhost
TIGERBEETLE_PORT=3000
```

---

## Key Differentiators

| Feature | Benefit |
|---------|---------|
| **Graph-Native Storage** | Unified data layer eliminates silos |
| **Temporal Awareness** | Track entity changes and relationships over time |
| **Entity Resolution** | Automatic extraction and normalization |
| **Hybrid Search** | Superior retrieval vs. vector-only approaches |
| **No File Dependencies** | Eliminates file system bottlenecks |
| **Knowledge Graphs** | Sophisticated relationship-based retrieval |
| **Specialized Agents** | Purpose-built profiles for common use cases |
| **Financial Integration** | Double-entry bookkeeping for transactions |
| **Security Guardians** | Built-in protection against attacks |

---

## Project Structure

```
vessels2/
├── agent.py                 # Core agent engine
├── models.py                # LLM provider integration
├── run_ui.py                # Web UI launcher
├── run_cli.py               # CLI launcher
│
├── python/
│   ├── helpers/
│   │   ├── graph_store.py   # Unified FalkorDB + Graphiti storage
│   │   ├── memory.py        # Graph-based memory system
│   │   ├── vector_db.py     # Graph-based vector search
│   │   ├── persist_chat.py  # Graph-based chat persistence
│   │   └── guardians.py     # Security & input validation
│   ├── api/                 # API endpoints
│   ├── tools/               # Tool implementations
│   └── extensions/          # Agent message loop extensions
│
├── agents/
│   ├── vessels/             # Default general-purpose agent
│   ├── developer/           # Master Developer profile
│   ├── researcher/          # Deep Researcher profile
│   └── hacker/              # Security specialist profile
│
├── prompts/                 # System prompts and behaviors
├── knowledge/               # Knowledge base documents
├── instruments/             # Custom tool scripts
├── docker/                  # Container configurations
└── docs/                    # Comprehensive documentation
```

---

## Migration Path

For existing Agent Zero deployments, Vessels provides migration utilities:

```python
from python.helpers.graph_store import MigrationHelper

# Migrate FAISS memories
await MigrationHelper.migrate_faiss_to_graph(faiss_dir, graph_store)

# Migrate JSON chats
await MigrationHelper.migrate_chats_to_graph(chats_dir, graph_store)

# Migrate markdown content
await MigrationHelper.migrate_md_files_to_graph(graph_store, base_dir)
```

The API maintains backward compatibility, allowing gradual migration.

---

## Summary

Vessels transforms autonomous agent architecture through:

1. **Unified Graph Storage**: All data in a single, queryable graph database
2. **Temporal Intelligence**: Time-aware entity and relationship tracking
3. **Hybrid Search**: Multiple search paradigms for optimal retrieval
4. **Specialized Profiles**: Purpose-built agents for development, research, and security
5. **Enterprise Security**: Built-in guardians and input sanitization
6. **Flexible Deployment**: Docker, standalone, or local Python execution

By replacing fragmented file-based systems with a coherent knowledge graph, Vessels enables more sophisticated reasoning, better context retention, and scalable agent deployments.

---

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/ohana-garden/vessels2.git
cd vessels2

# 2. Configure environment
cp .env.example .env
# Add your API keys to .env

# 3. Start services
docker compose up -d

# 4. Launch agent
python run_ui.py
# Open http://localhost:50001
```

---

*Document generated: 2025-12-03*
