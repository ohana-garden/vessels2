"""
Vessels Chat Persistence - Graph-based Implementation

This module provides chat persistence using FalkorDB + Graphiti
instead of file-based JSON storage.

The API remains compatible with the original persist_chat.py.
"""

from collections import OrderedDict
from datetime import datetime
from typing import Any, Optional
import uuid
import asyncio
import json

from agent import Agent, AgentConfig, AgentContext, AgentContextType
from python.helpers import history
from python.helpers.log import Log, LogItem
from python.helpers.graph_store import (
    GraphStore,
    ChatDocument,
    get_graph_store,
)
from python.helpers.print_style import PrintStyle
from initialize import initialize_agent


# Legacy constants for compatibility
CHATS_FOLDER = "tmp/chats"  # Not used in graph implementation
LOG_SIZE = 1000
CHAT_FILE_NAME = "chat.json"  # Not used in graph implementation

# Graph store instance
_graph_store: Optional[GraphStore] = None
_init_lock = asyncio.Lock()


async def _ensure_graph_store() -> GraphStore:
    """Ensure graph store is initialized."""
    global _graph_store
    async with _init_lock:
        if _graph_store is None:
            _graph_store = await get_graph_store()
        return _graph_store


def get_chat_folder_path(ctxid: str) -> str:
    """
    Get the folder path for a context (legacy compatibility).

    Note: In graph implementation, this is not used for storage
    but may be needed for file attachments.
    """
    from python.helpers import files
    return files.get_abs_path(CHATS_FOLDER, ctxid)


def get_chat_msg_files_folder(ctxid: str) -> str:
    """Get message files folder path (legacy compatibility)."""
    from python.helpers import files
    return files.get_abs_path(get_chat_folder_path(ctxid), "messages")


def save_tmp_chat(context: AgentContext) -> None:
    """
    Save context to the graph store.

    This is a sync wrapper for the async implementation.
    """
    if context.type == AgentContextType.BACKGROUND:
        return

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule for later execution if we're in an async context
            asyncio.create_task(_save_chat_async(context))
        else:
            loop.run_until_complete(_save_chat_async(context))
    except RuntimeError:
        # No event loop, create one
        asyncio.run(_save_chat_async(context))


async def _save_chat_async(context: AgentContext) -> None:
    """Save context to graph store asynchronously."""
    if context.type == AgentContextType.BACKGROUND:
        return

    graph_store = await _ensure_graph_store()
    data = _serialize_context(context)

    chat = ChatDocument(
        id=context.id,
        name=context.name or "",
        created_at=context.created_at or datetime.now(),
        last_message=context.last_message or datetime.now(),
        context_type=context.type.value,
        agents=data.get("agents", []),
        log=data.get("log", {}),
        data=data.get("data", {}),
        output_data=data.get("output_data", {}),
    )

    await graph_store.save_chat(chat)


def save_tmp_chats() -> None:
    """Save all contexts to the graph store."""
    for _, context in AgentContext._contexts.items():
        if context.type == AgentContextType.BACKGROUND:
            continue
        save_tmp_chat(context)


def load_tmp_chats() -> list[str]:
    """
    Load all contexts from the graph store.

    Returns:
        List of loaded context IDs
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't run sync in async context, return empty
            return []
        return loop.run_until_complete(_load_chats_async())
    except RuntimeError:
        return asyncio.run(_load_chats_async())


async def _load_chats_async() -> list[str]:
    """Load all contexts from graph store asynchronously."""
    graph_store = await _ensure_graph_store()
    chats = await graph_store.load_all_chats()

    ctxids = []
    for chat in chats:
        try:
            ctx = _deserialize_context_from_chat(chat)
            ctxids.append(ctx.id)
        except Exception as e:
            PrintStyle.error(f"Error loading chat {chat.id}: {e}")

    return ctxids


def load_json_chats(jsons: list[str]) -> list[str]:
    """
    Load contexts from JSON strings.

    Args:
        jsons: List of JSON strings representing contexts

    Returns:
        List of loaded context IDs
    """
    ctxids = []
    for js in jsons:
        data = json.loads(js)
        if "id" in data:
            del data["id"]
        ctx = _deserialize_context(data)
        ctxids.append(ctx.id)

        # Also save to graph store
        save_tmp_chat(ctx)

    return ctxids


def export_json_chat(context: AgentContext) -> str:
    """
    Export context as JSON string.

    Args:
        context: The context to export

    Returns:
        JSON string representation
    """
    data = _serialize_context(context)
    return _safe_json_serialize(data, ensure_ascii=False)


def remove_chat(ctxid: str) -> None:
    """
    Remove a chat from the graph store.

    Args:
        ctxid: The context ID to remove
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_remove_chat_async(ctxid))
        else:
            loop.run_until_complete(_remove_chat_async(ctxid))
    except RuntimeError:
        asyncio.run(_remove_chat_async(ctxid))


async def _remove_chat_async(ctxid: str) -> None:
    """Remove chat from graph store asynchronously."""
    graph_store = await _ensure_graph_store()
    await graph_store.delete_chat(ctxid)


def remove_msg_files(ctxid: str) -> None:
    """
    Remove message files for a context.

    Note: In graph implementation, messages are stored in the graph.
    This function is kept for compatibility but may handle file attachments.
    """
    from python.helpers import files
    path = get_chat_msg_files_folder(ctxid)
    files.delete_dir(path)


# =============================================================================
# Serialization Functions
# =============================================================================

def _serialize_context(context: AgentContext) -> dict:
    """Serialize a context to a dictionary."""
    agents = []
    agent = context.agent0
    while agent:
        agents.append(_serialize_agent(agent))
        agent = agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)

    data = {k: v for k, v in context.data.items() if not k.startswith("_")}
    output_data = {k: v for k, v in context.output_data.items() if not k.startswith("_")}

    return {
        "id": context.id,
        "name": context.name,
        "created_at": (
            context.created_at.isoformat()
            if context.created_at
            else datetime.fromtimestamp(0).isoformat()
        ),
        "type": context.type.value,
        "last_message": (
            context.last_message.isoformat()
            if context.last_message
            else datetime.fromtimestamp(0).isoformat()
        ),
        "agents": agents,
        "streaming_agent": (
            context.streaming_agent.number if context.streaming_agent else 0
        ),
        "log": _serialize_log(context.log),
        "data": data,
        "output_data": output_data,
    }


def _serialize_agent(agent: Agent) -> dict:
    """Serialize an agent to a dictionary."""
    data = {k: v for k, v in agent.data.items() if not k.startswith("_")}
    hist = agent.history.serialize()

    return {
        "number": agent.number,
        "data": data,
        "history": hist,
    }


def _serialize_log(log: Log) -> dict:
    """Serialize a log to a dictionary."""
    return {
        "guid": log.guid,
        "logs": [item.output() for item in log.logs[-LOG_SIZE:]],
        "progress": log.progress,
        "progress_no": log.progress_no,
    }


# =============================================================================
# Deserialization Functions
# =============================================================================

def _deserialize_context_from_chat(chat: ChatDocument) -> AgentContext:
    """Deserialize a ChatDocument to an AgentContext."""
    data = {
        "id": chat.id,
        "name": chat.name,
        "created_at": chat.created_at.isoformat(),
        "type": chat.context_type,
        "last_message": chat.last_message.isoformat(),
        "agents": chat.agents,
        "log": chat.log,
        "data": chat.data,
        "output_data": chat.output_data,
    }
    return _deserialize_context(data)


def _deserialize_context(data: dict) -> AgentContext:
    """Deserialize a dictionary to an AgentContext."""
    config = initialize_agent()
    log = _deserialize_log(data.get("log", {}))

    context = AgentContext(
        config=config,
        id=data.get("id", None),
        name=data.get("name", None),
        created_at=datetime.fromisoformat(
            data.get("created_at", datetime.fromtimestamp(0).isoformat())
        ),
        type=AgentContextType(data.get("type", AgentContextType.USER.value)),
        last_message=datetime.fromisoformat(
            data.get("last_message", datetime.fromtimestamp(0).isoformat())
        ),
        log=log,
        paused=False,
        data=data.get("data", {}),
        output_data=data.get("output_data", {}),
    )

    agents = data.get("agents", [])
    agent0 = _deserialize_agents(agents, config, context)
    streaming_agent = agent0

    while streaming_agent and streaming_agent.number != data.get("streaming_agent", 0):
        streaming_agent = streaming_agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)

    context.agent0 = agent0
    context.streaming_agent = streaming_agent

    return context


def _deserialize_agents(
    agents: list[dict[str, Any]],
    config: AgentConfig,
    context: AgentContext,
) -> Agent:
    """Deserialize a list of agent dictionaries to Agent objects."""
    prev: Optional[Agent] = None
    zero: Optional[Agent] = None

    for ag in agents:
        current = Agent(
            number=ag["number"],
            config=config,
            context=context,
        )
        current.data = ag.get("data", {})
        current.history = history.deserialize_history(
            ag.get("history", ""),
            agent=current,
        )

        if not zero:
            zero = current

        if prev:
            prev.set_data(Agent.DATA_NAME_SUBORDINATE, current)
            current.set_data(Agent.DATA_NAME_SUPERIOR, prev)

        prev = current

    return zero or Agent(0, config, context)


def _deserialize_log(data: dict[str, Any]) -> Log:
    """Deserialize a dictionary to a Log object."""
    log = Log()
    log.guid = data.get("guid", str(uuid.uuid4()))
    log.set_initial_progress()

    i = 0
    for item_data in data.get("logs", []):
        log.logs.append(
            LogItem(
                log=log,
                no=i,
                type=item_data["type"],
                heading=item_data.get("heading", ""),
                content=item_data.get("content", ""),
                kvps=OrderedDict(item_data["kvps"]) if item_data.get("kvps") else None,
                temp=item_data.get("temp", False),
            )
        )
        log.updates.append(i)
        i += 1

    return log


# =============================================================================
# Utility Functions
# =============================================================================

def _safe_json_serialize(obj: Any, **kwargs) -> str:
    """Safely serialize an object to JSON, skipping non-serializable values."""

    def serializer(o):
        if isinstance(o, dict):
            return {k: v for k, v in o.items() if is_json_serializable(v)}
        elif isinstance(o, (list, tuple)):
            return [item for item in o if is_json_serializable(item)]
        elif is_json_serializable(o):
            return o
        else:
            return None

    def is_json_serializable(item):
        try:
            json.dumps(item)
            return True
        except (TypeError, OverflowError):
            return False

    return json.dumps(obj, default=serializer, **kwargs)


def _get_chat_file_path(ctxid: str) -> str:
    """Get chat file path (legacy compatibility)."""
    from python.helpers import files
    return files.get_abs_path(CHATS_FOLDER, ctxid, CHAT_FILE_NAME)
