# Vessels: A Graph-Native Framework for Autonomous Agents

## Overview

Vessels is an autonomous agent framework built on [Agent Zero](https://github.com/agent0ai/agent-zero), extended with a unified graph-based storage layer using FalkorDB and Graphiti. The framework replaces traditional file-based storage and FAISS vector databases with a temporal knowledge graph that stores all agent state—memories, conversations, knowledge, and settings—in a single connected structure.

---

## The Core Experience: Self-Orchestrating Agents

When you interact with Vessels, you're not giving commands to a passive assistant. You're initiating a conversation with an agent that orchestrates its own work.

### The Monologue

Every agent runs a **monologue**—a continuous loop where the agent reasons about what to do next, takes action through tools, observes results, and decides whether to continue or respond. This loop continues until the agent determines it has completed the task or needs user input.

```
User message → Agent reasoning → Tool use → Observe results → Continue or respond
                    ↑                              ↓
                    └──────────────────────────────┘
```

The agent isn't following a script. It decides which tools to use, when to delegate to subordinate agents, and when the task is complete. This is what "self-orchestrating" means: the agent manages its own workflow.

### Agent Hierarchy

Agents can spawn subordinate agents to handle subtasks. Agent 0 (A0) is the primary agent that receives user messages. When A0 calls the `call_subordinate` tool, it creates A1 with a specific task. A1 can further spawn A2, and so on.

```
User ↔ A0 (primary agent)
         ↓ delegates
        A1 (subordinate)
         ↓ delegates
        A2 (subordinate)
```

Each subordinate runs its own monologue, completes its task, and returns results to its superior. The context remains unified—all agents share the same graph database.

### The A0 Framework

The A0 Framework (`python/helpers/a0_framework.py`) integrates all components into a unified system. It initializes in dependency order:

1. Ethics Engine (validates all actions)
2. Collective Memory (records all I/O)
3. Projects, Instruments, A2A, MCP, Prompts, Tools
4. Agent Factory (lifecycle management)

This singleton architecture ensures consistent state across all components.

---

## What Replaced What

Vessels made a specific architectural decision: **everything goes in the graph**.

| Traditional Approach | Vessels |
|---------------------|---------|
| FAISS vector database | Graphiti hybrid search (semantic + BM25 + graph traversal) |
| JSON files for chat history | Chat episodes in FalkorDB |
| Markdown files for memories | Memory nodes with entity relationships |
| File-based settings | Settings stored as graph properties |
| Scattered knowledge docs | Knowledge imported as connected graph nodes |

This isn't just storage consolidation—it enables queries that would be impossible otherwise. When you ask about something discussed weeks ago, the system can traverse relationships between the conversation, the entities mentioned, related memories, and connected knowledge.

---

## Available Tools

Agents work through tools. The core toolkit includes:

| Tool | What It Does |
|------|--------------|
| `code_execution_tool` | Run Python, Node.js, or shell commands |
| `call_subordinate` | Delegate a task to a new agent |
| `response_tool` | Send a response to the user and end the current task |
| `memory_tool` | Save, load, or forget information |
| `knowledge_tool` | Search imported documents and web |
| `behaviour_adjustment` | Modify the agent's behavioral rules |

Browser automation and MCP (Model Context Protocol) servers extend capabilities further.

---

## Code-in-Database

Vessels can store and execute code directly from FalkorDB (`python/helpers/code_loader.py`):

- **Code Loader**: Retrieves code from graph, compiles to Python modules, caches with hash validation
- **Code Store**: Semantic indexing of code snippets with execution history tracking

This enables agents to understand their own capabilities, write new tools at runtime, and maintain full audit trails of code evolution.

---

## Agent Profiles

Different profiles configure agents for different roles:

| Profile | Focus |
|---------|-------|
| `vessels` | General-purpose assistant (default) |
| `developer` | Software engineering and code |
| `researcher` | Analysis and synthesis |
| `hacker` | Security testing (authorized contexts) |

Profiles customize prompts and tool configurations. You can create your own.

---

## Memory Organization

Memory isn't a single bucket. It's organized into areas:

- **Main memory**: Long-term facts and knowledge
- **Fragments**: Short-term observations from recent conversations
- **Solutions**: Successful approaches from past tasks
- **Instruments**: Metadata about available tools

All areas are searchable through Graphiti's hybrid search, which combines semantic similarity with keyword matching and graph traversal.

---

## The Graph Store

FalkorDB with Graphiti provides:

- **Temporal awareness**: Every node tracks when it was created and accessed
- **Entity extraction**: Automatic identification of people, places, concepts
- **Relationship tracking**: How entities connect across contexts
- **Hybrid search**: Semantic + keyword + graph queries

This replaces the fragmented storage of typical agent frameworks with a single coherent data model.

---

## Ethics Framework

Vessels includes a Constitutional AI ethics engine (`python/helpers/ethics.py`) that validates agent actions against 18 principles organized into six categories:

- **Safety**: Harm prevention, human oversight, fail-safe
- **Transparency**: Honesty, explainability, auditability
- **Privacy**: Data minimization, consent respect, confidentiality
- **Fairness**: Non-discrimination, equal access, impartiality
- **Accountability**: Responsibility, traceability, corrective action
- **Autonomy**: Human agency, informed choice, reversibility

Validators check actions before execution. Violations are classified by severity (info → critical) and can trigger warnings, modifications, or blocks.

---

## Moral Geometry

The graph stores moral reasoning as points in a 15-dimensional ethical space. Each dimension represents a moral consideration (compassion, justice, truth, etc.).

- **Moral vectors**: Individual ethical positions
- **Moral trajectories**: How positions evolve across decisions
- **Spectral decomposition**: Eigenvalue analysis of moral patterns

This enables tracking how an agent's ethical reasoning develops over time.

---

## Entity Ontology

Vessels represents more than humans and agents. The entity ontology supports:

| Entity Type | Examples |
|-------------|----------|
| Human | Users, facilitators |
| Agent | AI assistants |
| Plant | Gardens, crops |
| Machine | Devices, infrastructure |
| System | Software, processes |
| Biome | Ecosystems |
| Community | Groups, organizations |

Each entity has a **voice source**: self (speaks directly), proxy (another entity speaks for it), sensor (data represents it), or collective (multiple entities represent it).

The **elicitation** process develops personas for entities that can't speak for themselves—discovering their boundaries, rhythms, and needs through facilitated sessions.

---

## Kala: Contribution Visibility

Kala tracks contributions that don't fit traditional economic categories. Events record:

- Participants and hours
- Roles and activities
- Community context

Two views exist:
- **Human View**: Your own contribution history
- **Agent View**: Aggregated patterns for coordination, including burnout detection and withdrawal signals

Integrates with TigerBeetle for formal accounting when needed.

---

## Hume.ai Integration

Voice interactions use Hume's Empathic Voice Interface for emotional intelligence:

- **Emotion detection**: Real-time inference from vocal characteristics
- **Voice profiles**: Persona voice settings stored in graph
- **Emotional trajectories**: Historical emotional state tracking
- **Vessel-level climate**: Aggregate emotional state across active sessions

---

## Extension Points

The agent message loop exposes 24 extension points where you can inject custom behavior:

- `agent_init` - When an agent is created
- `monologue_start` / `monologue_end` - Around the main loop
- `message_loop_start` / `message_loop_end` - Each iteration
- `system_prompt` - Modify what the agent sees
- `before_tool_execute` / `after_tool_execute` - Tool lifecycle
- And more...

Extensions are Python classes that receive control at these moments.

---

## Running Vessels

### Quick Start

```bash
# Start FalkorDB
docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest

# Install and run
pip install -r requirements.txt
cp .env.example .env  # Configure API keys
python run_ui.py
```

Visit `http://localhost:50001`.

### Configuration

Set your LLM credentials in `.env`:

```bash
OPENAI_API_KEY=your-key
# or
ANTHROPIC_API_KEY=your-key

# FalkorDB
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
```

Vessels supports 30+ model providers through LiteLLM.

---

## What Vessels Is For

Vessels works well for:

- **Software development**: The developer profile with code execution handles multi-step engineering tasks
- **Research**: Importing documents, synthesizing across sources, maintaining context over sessions
- **Automation**: Agents can run scheduled tasks and orchestrate multi-step workflows
- **Any task requiring memory**: The graph tracks context across interactions

It's not the right choice for simple Q&A where context doesn't matter. The graph architecture adds overhead that only pays off when relationships and temporal awareness are valuable.

---

## Credits

Built on [Agent Zero](https://github.com/agent0ai/agent-zero) by [frdel](https://github.com/frdel).

Graph storage: [FalkorDB](https://www.falkordb.com/) + [Graphiti](https://github.com/getzep/graphiti).
