<div align="center">

# `Vessels`

### A Graph-Native Autonomous Agent Framework

*Built on Agent Zero, powered by FalkorDB + Graphiti*

</div>

## Overview

Vessels is an autonomous agent framework that extends [Agent Zero](https://github.com/agent0ai/agent-zero) with a unified graph-based storage layer using **FalkorDB** and **Graphiti**.

### Key Differentiators

- **Graph-Native Storage**: All data (memories, chats, knowledge, settings) stored in FalkorDB temporal knowledge graph
- **No Files, No FAISS**: Replaced file-based storage and FAISS vector DB with Graphiti's hybrid search
- **Temporal Knowledge**: Full temporal awareness with entity relationships and graph traversal
- **Unified Backend**: Single data store for all agent state and knowledge

## Documentation

[Installation](#installation) •
[Configuration](#configuration) •
[Architecture](#architecture) •
[Usage](./docs/usage.md) •
[Development](./docs/development.md)

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

## Installation

### Prerequisites

1. **Docker** for FalkorDB:
```bash
docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest
```

2. **Python 3.11+**

### Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/vessels.git
cd vessels

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run the agent
python run_ui.py
```

Visit `http://localhost:50001` to start.

## Configuration

### Environment Variables

```bash
# FalkorDB Connection
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_DATABASE=vessels

# Graphiti LLM (for knowledge graph construction)
GRAPHITI_LLM_PROVIDER=openai
GRAPHITI_LLM_MODEL=gpt-4o-mini
GRAPHITI_EMBEDDING_MODEL=text-embedding-3-small

# Agent LLM
OPENAI_API_KEY=your-key
# or
ANTHROPIC_API_KEY=your-key
```

## Features

### From Agent Zero

- **Multi-Agent Cooperation**: Hierarchical agent delegation (superior → subordinate)
- **LLM Agnostic**: 30+ providers via LiteLLM (Anthropic, OpenAI, Ollama, etc.)
- **Tool System**: Code execution, browser automation, search, and custom tools
- **Extension Points**: 24 hooks for customizing agent behavior
- **Web UI**: Real-time streaming Flask interface
- **MCP Support**: Model Context Protocol integration
- **Agent Profiles**: Specialized agents (Developer, Researcher, Hacker)

### Vessels Additions

- **Temporal Memory**: Memories with full temporal context and relationships
- **Hybrid Search**: Semantic + keyword + graph traversal search
- **Entity Extraction**: Automatic entity and relationship extraction
- **Knowledge Graph**: Connected knowledge with entity resolution
- **No File Storage**: All persistence through graph database

## Agent Profiles

| Profile | Description |
|---------|-------------|
| `vessels` | General-purpose assistant (default) |
| `developer` | Master Developer for software engineering |
| `researcher` | Deep Research for academic/corporate analysis |
| `hacker` | Security testing and penetration testing |

## Project Structure

```
vessels/
├── agent.py              # Core agent engine
├── models.py             # LLM integration
├── run_ui.py             # Web UI server
├── python/
│   ├── helpers/
│   │   ├── graph_store.py    # FalkorDB + Graphiti layer
│   │   ├── memory.py         # Graph-based memory
│   │   ├── vector_db.py      # Graph-based vector search
│   │   └── persist_chat.py   # Graph-based chat storage
│   ├── tools/            # Agent tools
│   └── extensions/       # Extension hooks
├── prompts/              # System prompts
├── agents/               # Agent profiles
│   ├── vessels/          # Default profile
│   ├── developer/        # Developer profile
│   ├── researcher/       # Researcher profile
│   └── hacker/           # Security profile
└── webui/                # Web interface
```

## Credits

Vessels is built on top of [Agent Zero](https://github.com/agent0ai/agent-zero) by [frdel](https://github.com/frdel).

Graph storage powered by:
- [FalkorDB](https://www.falkordb.com/) - High-performance graph database
- [Graphiti](https://github.com/getzep/graphiti) - Temporal knowledge graph library

## License

See [LICENSE](./LICENSE) for details.
