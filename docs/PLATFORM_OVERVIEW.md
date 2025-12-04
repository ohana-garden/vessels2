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
