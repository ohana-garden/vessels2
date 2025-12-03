"""
Embedded Defaults - All code and content for Vessels.

This module contains ALL default tools, extensions, and prompts
embedded as string literals. On first access, these get seeded to
FalkorDB. No filesystem reads needed - enables fast Docker startup.

Generated from filesystem sources - this IS the source of truth.
"""

# =============================================================================
# TOOL DEFAULTS
# =============================================================================

TOOL_DEFAULTS = {
    "memory_load": {
        "code_type": "tool",
        "code": '''
from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response

DEFAULT_THRESHOLD = 0.7
DEFAULT_LIMIT = 10


class MemoryLoad(Tool):

    async def execute(self, query="", threshold=DEFAULT_THRESHOLD, limit=DEFAULT_LIMIT, filter="", **kwargs):
        db = await Memory.get(self.agent)
        docs = await db.search_similarity_threshold(query=query, limit=limit, threshold=threshold, filter=filter)

        if len(docs) == 0:
            result = self.agent.read_prompt("fw.memories_not_found.md", query=query)
        else:
            text = "\\n\\n".join(Memory.format_docs_plain(docs))
            result = str(text)

        return Response(message=result, break_loop=False)
''',
    },
    "memory_save": {
        "code_type": "tool",
        "code": '''
from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response


class MemorySave(Tool):

    async def execute(self, text="", area="", **kwargs):

        if not area:
            area = Memory.Area.MAIN.value

        metadata = {"area": area, **kwargs}

        db = await Memory.get(self.agent)
        id = await db.insert_text(text, metadata)

        result = self.agent.read_prompt("fw.memory_saved.md", memory_id=id)
        return Response(message=result, break_loop=False)
''',
    },
    "memory_delete": {
        "code_type": "tool",
        "code": '''
from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response


class MemoryDelete(Tool):

    async def execute(self, ids="", **kwargs):
        db = await Memory.get(self.agent)
        ids = [id.strip() for id in ids.split(",") if id.strip()]
        dels = await db.delete_documents_by_ids(ids=ids)

        result = self.agent.read_prompt("fw.memories_deleted.md", memory_count=len(dels))
        return Response(message=result, break_loop=False)
''',
    },
    "memory_forget": {
        "code_type": "tool",
        "code": '''
from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response
from python.tools.memory_load import DEFAULT_THRESHOLD


class MemoryForget(Tool):

    async def execute(self, query="", threshold=DEFAULT_THRESHOLD, filter="", **kwargs):
        db = await Memory.get(self.agent)
        dels = await db.delete_documents_by_query(query=query, threshold=threshold, filter=filter)

        result = self.agent.read_prompt("fw.memories_deleted.md", memory_count=len(dels))
        return Response(message=result, break_loop=False)
''',
    },
    "response": {
        "code_type": "tool",
        "code": '''
from python.helpers.tool import Tool, Response


class ResponseTool(Tool):

    async def execute(self, **kwargs):
        return Response(message=self.args["text"] if "text" in self.args else self.args["message"], break_loop=True)

    async def before_execution(self, **kwargs):
        pass

    async def after_execution(self, response, **kwargs):
        if self.loop_data and "log_item_response" in self.loop_data.params_temporary:
            log = self.loop_data.params_temporary["log_item_response"]
            log.update(finished=True)
''',
    },
    "wait": {
        "code_type": "tool",
        "code": '''
import asyncio
from datetime import datetime, timedelta, timezone
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers.wait import managed_wait
from python.helpers.localization import Localization

class WaitTool(Tool):

    async def execute(self, **kwargs) -> Response:
        await self.agent.handle_intervention()

        seconds = self.args.get("seconds", 0)
        minutes = self.args.get("minutes", 0)
        hours = self.args.get("hours", 0)
        days = self.args.get("days", 0)
        until_timestamp_str = self.args.get("until")

        is_duration_wait = not bool(until_timestamp_str)

        now = datetime.now(timezone.utc)
        target_time = None

        if until_timestamp_str:
            try:
                target_time = Localization.get().localtime_str_to_utc_dt(until_timestamp_str)
                if not target_time:
                    raise ValueError(f"Invalid timestamp format: {until_timestamp_str}")
            except ValueError as e:
                return Response(message=str(e), break_loop=False)
        else:
            wait_duration = timedelta(
                days=int(days), hours=int(hours), minutes=int(minutes), seconds=int(seconds),
            )
            if wait_duration.total_seconds() <= 0:
                return Response(message="Wait duration must be positive.", break_loop=False)
            target_time = now + wait_duration

        if target_time <= now:
            return Response(message=f"Target time {target_time.isoformat()} is in the past.", break_loop=False)

        PrintStyle.info(f"Waiting until {target_time.isoformat()}...")

        target_time = await managed_wait(
            agent=self.agent, target_time=target_time, is_duration_wait=is_duration_wait,
            log=self.log, get_heading_callback=self.get_heading
        )

        if self.log:
            self.log.update(heading=self.get_heading("Done", done=True))

        message = self.agent.read_prompt("fw.wait_complete.md", target_time=target_time.isoformat())
        return Response(message=message, break_loop=False)

    def get_log_object(self):
        return self.agent.context.log.log(type="progress", heading=self.get_heading(), content="", kvps=self.args)

    def get_heading(self, text: str = "", done: bool = False):
        done_icon = " icon://done_all" if done else ""
        if not text:
            text = f"Waiting..."
        return f"icon://timer Wait: {text}{done_icon}"
''',
    },
    "notify_user": {
        "code_type": "tool",
        "code": '''
from python.helpers.tool import Tool, Response
from agent import AgentContext
from python.helpers.notification import NotificationPriority, NotificationType

class NotifyUserTool(Tool):

    async def execute(self, **kwargs):

        message = self.args.get("message", "")
        title = self.args.get("title", "")
        detail = self.args.get("detail", "")
        notification_type = self.args.get("type", NotificationType.INFO)
        priority = self.args.get("priority", NotificationPriority.HIGH)
        timeout = int(self.args.get("timeout", 30))

        try:
            notification_type = NotificationType(notification_type)
        except ValueError:
            return Response(message=f"Invalid notification type: {notification_type}", break_loop=False)

        try:
            priority = NotificationPriority(priority)
        except ValueError:
            return Response(message=f"Invalid notification priority: {priority}", break_loop=False)

        if not message:
            return Response(message="Message is required", break_loop=False)

        AgentContext.get_notification_manager().add_notification(
            message=message, title=title, detail=detail, type=notification_type,
            priority=priority, display_time=timeout,
        )
        return Response(message=self.agent.read_prompt("fw.notify_user.notification_sent.md"), break_loop=False)
''',
    },
    "unknown": {
        "code_type": "tool",
        "code": '''
from python.helpers.tool import Tool, Response
from python.extensions.system_prompt._10_system_prompt import get_tools_prompt


class Unknown(Tool):
    async def execute(self, **kwargs):
        tools = get_tools_prompt(self.agent)
        return Response(
            message=self.agent.read_prompt("fw.tool_not_found.md", tool_name=self.name, tools_prompt=tools),
            break_loop=False,
        )
''',
    },
    "search_engine": {
        "code_type": "tool",
        "code": '''
import os
import asyncio
from python.helpers import dotenv, memory, perplexity_search, duckduckgo_search
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers.errors import handle_error
from python.helpers.searxng import search as searxng

SEARCH_ENGINE_RESULTS = 10


class SearchEngine(Tool):
    async def execute(self, query="", **kwargs):
        searxng_result = await self.searxng_search(query)
        await self.agent.handle_intervention(searxng_result)
        return Response(message=searxng_result, break_loop=False)

    async def searxng_search(self, question):
        results = await searxng(question)
        return self.format_result_searxng(results, "Search Engine")

    def format_result_searxng(self, result, source):
        if isinstance(result, Exception):
            handle_error(result)
            return f"{source} search failed: {str(result)}"

        outputs = []
        for item in result["results"]:
            outputs.append(f"{item[\\'title\\']}\\n{item[\\'url\\']}\\n{item[\\'content\\']}")

        return "\\n\\n".join(outputs[:SEARCH_ENGINE_RESULTS]).strip()
''',
    },
}

# =============================================================================
# EXTENSION DEFAULTS
# =============================================================================

EXTENSION_DEFAULTS = {
    "before_main_llm_call/_10_log_for_stream": {
        "code_type": "extension",
        "code": '''
from python.helpers import persist_chat, tokens
from python.helpers.extension import Extension
from agent import LoopData
import asyncio
from python.helpers.log import LogItem
from python.helpers import log
import math


class LogForStream(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), text: str = "", **kwargs):
        if "log_item_generating" not in loop_data.params_temporary:
            loop_data.params_temporary["log_item_generating"] = (
                self.agent.context.log.log(type="agent", heading=build_default_heading(self.agent))
            )

def build_heading(agent, text: str):
    return f"icon://network_intelligence {agent.agent_name}: {text}"

def build_default_heading(agent):
    return build_heading(agent, "Generating...")
''',
    },
    "hist_add_before/_10_mask_content": {
        "code_type": "extension",
        "code": '''
from python.helpers.extension import Extension
from python.helpers.secrets import get_secrets_manager


class MaskHistoryContent(Extension):

    async def execute(self, **kwargs):
        content_data = kwargs.get("content_data")
        if not content_data:
            return

        try:
            secrets_mgr = get_secrets_manager(self.agent.context)
            content_data["content"] = self._mask_content(content_data["content"], secrets_mgr)
        except Exception as e:
            pass

    def _mask_content(self, content, secrets_mgr):
        if isinstance(content, str):
            return secrets_mgr.mask_values(content)
        elif isinstance(content, list):
            return [self._mask_content(item, secrets_mgr) for item in content]
        elif isinstance(content, dict):
            return {k: self._mask_content(v, secrets_mgr) for k, v in content.items()}
        else:
            return content
''',
    },
    "message_loop_prompts_after/_60_include_current_datetime": {
        "code_type": "extension",
        "code": '''
from datetime import datetime, timezone
from python.helpers.extension import Extension
from agent import LoopData
from python.helpers.localization import Localization


class IncludeCurrentDatetime(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        current_datetime = Localization.get().utc_dt_to_localtime_str(
            datetime.now(timezone.utc), sep=" ", timespec="seconds"
        )
        if current_datetime and "+" in current_datetime:
            current_datetime = current_datetime.split("+")[0]

        datetime_prompt = self.agent.read_prompt("agent.system.datetime.md", date_time=current_datetime)
        loop_data.extras_temporary["current_datetime"] = datetime_prompt
''',
    },
    "message_loop_prompts_after/_70_include_agent_info": {
        "code_type": "extension",
        "code": '''
from python.helpers.extension import Extension
from agent import LoopData

class IncludeAgentInfo(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        agent_info_prompt = self.agent.read_prompt(
            "agent.extras.agent_info.md", number=self.agent.number, profile=self.agent.config.profile or "Default",
        )
        loop_data.extras_temporary["agent_info"] = agent_info_prompt
''',
    },
    "message_loop_start/_10_iteration_no": {
        "code_type": "extension",
        "code": '''
from python.helpers.extension import Extension
from agent import Agent, LoopData

DATA_NAME_ITER_NO = "iteration_no"

class IterationNo(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        no = self.agent.get_data(DATA_NAME_ITER_NO) or 0
        self.agent.set_data(DATA_NAME_ITER_NO, no + 1)


def get_iter_no(agent: Agent) -> int:
    return agent.get_data(DATA_NAME_ITER_NO) or 0
''',
    },
    "monologue_end/_90_waiting_for_input_msg": {
        "code_type": "extension",
        "code": '''
from python.helpers.extension import Extension
from agent import LoopData

class WaitingForInputMsg(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if self.agent.number == 0:
            self.agent.context.log.set_initial_progress()
''',
    },
    "message_loop_end/_90_save_chat": {
        "code_type": "extension",
        "code": '''
from python.helpers.extension import Extension
from agent import LoopData, AgentContextType
from python.helpers import persist_chat


class SaveChat(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if self.agent.context.type == AgentContextType.BACKGROUND:
            return
        persist_chat.save_tmp_chat(self.agent.context)
''',
    },
    "message_loop_end/_10_organize_history": {
        "code_type": "extension",
        "code": '''
import asyncio
from python.helpers.extension import Extension
from agent import LoopData

DATA_NAME_TASK = "_organize_history_task"


class OrganizeHistory(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        task = self.agent.get_data(DATA_NAME_TASK)
        if task and not task.done():
            return

        task = asyncio.create_task(self.agent.history.compress())
        self.agent.set_data(DATA_NAME_TASK, task)
''',
    },
    "tool_execute_before/_10_unmask_secrets": {
        "code_type": "extension",
        "code": '''
from python.helpers.extension import Extension
from python.helpers.secrets import get_secrets_manager


class UnmaskToolSecrets(Extension):

    async def execute(self, **kwargs):
        tool_args = kwargs.get("tool_args")
        if not tool_args:
            return

        secrets_mgr = get_secrets_manager(self.agent.context)

        for k, v in tool_args.items():
            if isinstance(v, str):
                tool_args[k] = secrets_mgr.replace_placeholders(v)
''',
    },
    "tool_execute_after/_10_mask_secrets": {
        "code_type": "extension",
        "code": '''
from python.helpers.extension import Extension
from python.helpers.secrets import get_secrets_manager
from python.helpers.tool import Response


class MaskToolSecrets(Extension):

    async def execute(self, response: Response | None = None, **kwargs):
        if not response:
            return
        secrets_mgr = get_secrets_manager(self.agent.context)
        response.message = secrets_mgr.mask_values(response.message)
''',
    },
    "error_format/_10_mask_errors": {
        "code_type": "extension",
        "code": '''
from python.helpers.extension import Extension
from python.helpers.secrets import get_secrets_manager


class MaskErrorSecrets(Extension):

    async def execute(self, **kwargs):
        msg = kwargs.get("msg")
        if not msg:
            return

        secrets_mgr = get_secrets_manager(self.agent.context)

        if "message" in msg:
            msg["message"] = secrets_mgr.mask_values(msg["message"])
''',
    },
}

# =============================================================================
# PROMPT DEFAULTS (Content)
# =============================================================================

PROMPT_DEFAULTS = {
    "agent.system.main.md": '''# Vessels System Manual

{{ include "agent.system.main.role.md" }}

{{ include "agent.system.main.environment.md" }}

{{ include "agent.system.main.communication.md" }}

{{ include "agent.system.main.solving.md" }}

{{ include "agent.system.main.tips.md" }}
''',
    "agent.system.tools.md": '''## Tools available:

{{tools}}''',
    "fw.error.md": '''~~~json
{
    "system_error": "{{error}}"
}
~~~''',
    "fw.initial_message.md": '''```json
{
    "thoughts": [
        "This is a new conversation, I should greet the user warmly and let them know I'm ready to help.",
        "I'll use the response tool with proper JSON formatting to demonstrate the expected structure.",
        "Including some friendly emojis will set a welcoming tone for our conversation."
    ],
    "headline": "Greeting user and starting conversation",
    "tool_name": "response",
    "tool_args": {
        "text": "**Hello! 👋**, I'm **Vessels**, your AI assistant. How can I help you today?"
    }
}
```
''',
    "agent.system.behaviour_default.md": '''- favor linux commands for simple tasks where possible instead of python
''',
    "fw.memories_not_found.md": '''No memories found matching query: "{{query}}"''',
    "fw.memory_saved.md": '''Memory saved successfully. ID: {{memory_id}}''',
    "fw.memories_deleted.md": '''{{memory_count}} memories deleted.''',
    "fw.wait_complete.md": '''Wait completed. Current time: {{target_time}}''',
    "fw.notify_user.notification_sent.md": '''Notification sent to user.''',
    "fw.tool_not_found.md": '''Tool "{{tool_name}}" not found. Available tools:
{{tools_prompt}}''',
    "agent.system.datetime.md": '''## Current Date/Time
{{date_time}}''',
    "agent.extras.agent_info.md": '''## Agent Information
- Agent Number: {{number}}
- Profile: {{profile}}''',
}

# =============================================================================
# MORAL GEOMETRY DEFAULTS (Already in code_registry, kept for reference)
# =============================================================================

MORAL_GEOMETRY_DEFAULTS = {
    "moral_geometry": {
        "code_type": "module",
        "code": '''
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math

class MoralDimension(str, Enum):
    HARM_BENEFIT = "harm_benefit"
    INDIVIDUAL_COLLECTIVE = "individual_collective"
    SHORT_LONG_TERM = "short_long_term"
    AUTONOMY = "autonomy"
    JUSTICE = "justice"
    FIDELITY = "fidelity"
    TRUTH = "truth"
    COMPASSION = "compassion"
    COURAGE = "courage"
    PRUDENCE = "prudence"
    TEMPERANCE = "temperance"
    RECIPROCITY = "reciprocity"
    SANCTITY = "sanctity"
    AUTHORITY = "authority"
    LIBERTY = "liberty"

    @classmethod
    def all_dimensions(cls): return [d.value for d in cls]

@dataclass
class MoralVector:
    id: str = ""
    name: str = ""
    description: str = ""
    components: dict = field(default_factory=dict)
    source_type: str = "action"
    timestamp: str = ""
    magnitude: float = 0.0
    dominant_dimension: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.components:
            self.components = {d.value: 0.0 for d in MoralDimension}

    def set_dimension(self, dim, value):
        key = dim.value if hasattr(dim, "value") else dim
        self.components[key] = max(-1.0, min(1.0, float(value)))
        return self

    def get_dimension(self, dim):
        key = dim.value if hasattr(dim, "value") else dim
        return self.components.get(key, 0.0)

    def compute_magnitude(self):
        self.magnitude = math.sqrt(sum(v*v for v in self.components.values()))
        return self.magnitude

    def find_dominant(self):
        if self.components:
            self.dominant_dimension = max(self.components, key=lambda k: abs(self.components[k]))
        return self.dominant_dimension

    def to_dict(self):
        return {"id": self.id, "name": self.name, "components": self.components,
                "magnitude": self.magnitude, "dominant_dimension": self.dominant_dimension}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d.get("id",""), name=d.get("name",""), components=d.get("components",{}))

@dataclass
class MoralDistance:
    euclidean: float = 0.0
    cosine_similarity: float = 0.0
    alignment_score: float = 0.0
    conflict_dimensions: list = field(default_factory=list)

def compute_distance(a, b):
    ca = a.components if hasattr(a, "components") else a.get("components", {})
    cb = b.components if hasattr(b, "components") else b.get("components", {})
    dims = set(ca) | set(cb)
    sum_sq = sum((ca.get(d,0) - cb.get(d,0))**2 for d in dims)
    dot = sum(ca.get(d,0) * cb.get(d,0) for d in dims)
    ma = math.sqrt(sum(v*v for v in ca.values()))
    mb = math.sqrt(sum(v*v for v in cb.values()))
    cos = dot/(ma*mb) if ma and mb else 0
    conflicts = [d for d in dims if ca.get(d,0) * cb.get(d,0) < -0.25]
    return MoralDistance(euclidean=math.sqrt(sum_sq), cosine_similarity=cos,
                         alignment_score=(cos+1)/2, conflict_dimensions=conflicts)
''',
    },
    "spectral": {
        "code_type": "agent_capability",
        "code": '''
import math

def eigenvalues(matrix, n=5, iters=100):
    """Power iteration eigenvalue decomposition (no numpy)."""
    size = len(matrix)
    if not size: return {"eigenvalues": [], "eigenvectors": []}
    A = [row[:] for row in matrix]
    vals, vecs = [], []
    for _ in range(min(n, size)):
        v = [1/math.sqrt(size)] * size
        ev = 0
        for _ in range(iters):
            Av = [sum(A[i][j]*v[j] for j in range(size)) for i in range(size)]
            ev = sum(v[i]*Av[i] for i in range(size))
            norm = math.sqrt(sum(x*x for x in Av))
            if norm < 1e-10: break
            v = [x/norm for x in Av]
        if abs(ev) < 1e-10: break
        vals.append(ev)
        vecs.append(v)
        for i in range(size):
            for j in range(size):
                A[i][j] -= ev * v[i] * v[j]
    return {"eigenvalues": vals, "eigenvectors": vecs}

def covariance(data):
    if not data or not data[0]: return []
    n, m = len(data), len(data[0])
    means = [sum(data[i][j] for i in range(n))/n for j in range(m)]
    return [[sum((data[k][i]-means[i])*(data[k][j]-means[j]) for k in range(n))/(n-1 if n>1 else 1)
             for j in range(m)] for i in range(m)]

def pca(data, components=2):
    cov = covariance(data)
    result = eigenvalues(cov, components)
    total = sum(result["eigenvalues"]) or 1
    return {"components": result["eigenvectors"][:components],
            "variance_explained": [e/total for e in result["eigenvalues"][:components]]}
''',
    },
}

# =============================================================================
# KALA DEFAULTS - Contribution Visibility System
# =============================================================================

KALA_DEFAULTS = {
    "kala": {
        "code_type": "module",
        "code": '''
"""
Kala - Non-Currency Metric for Community Contribution Visibility

Kala makes visible the patterns of community care, participation, and mutual aid.
Unlike currencies, Kala cannot be exchanged, accumulated for leverage, or used as payment.
It functions as collective memory - a ledger of responsibility that records who participated,
what occurred, and when events took place.

Key properties:
- Non-transferable: Cannot be exchanged between individuals
- Equal distribution: All participants receive equal Kala per event
- Asymmetric visibility: AI agents see patterns, humans see only their own history
- Memory, not medium: Records without creating tradable units
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import math


# Base rate: all human participation valued equally
KALA_PER_HOUR = 50.0


class MultiplierType(str, Enum):
    """Types of value multipliers for events."""
    NUTRITION = "nutrition"       # Meals, food sharing
    CULTURE = "culture"           # Storytelling, traditions
    HEALTH = "health"             # Physical activity, wellness
    ENVIRONMENT = "environment"   # Sustainable practice, land care
    EDUCATION = "education"       # Skill sharing, learning
    SOCIAL = "social"             # Connection, gathering
    CARE = "care"                 # Caregiving, support
    CREATION = "creation"         # Making, building


@dataclass
class KalaMultiplier:
    """A multiplier that reflects collective benefits of an event."""
    multiplier_type: MultiplierType
    value: float = 1.0  # 1.0 = no multiplier, 2.0 = double value
    description: str = ""

    def to_dict(self):
        return {"type": self.multiplier_type.value, "value": self.value, "description": self.description}

    @classmethod
    def from_dict(cls, d):
        return cls(multiplier_type=MultiplierType(d["type"]), value=d.get("value", 1.0),
                   description=d.get("description", ""))


@dataclass
class KalaParticipation:
    """A participant's record at an event. Everyone gets equal Kala."""
    participant_id: str
    participant_type: str = "human"  # human, agent, proxy
    hours: float = 0.0
    kala_received: float = 0.0
    timestamp: str = ""
    role: str = ""  # optional: organizer, helper, observer, etc. (no effect on Kala)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return {"participant_id": self.participant_id, "participant_type": self.participant_type,
                "hours": self.hours, "kala_received": self.kala_received,
                "timestamp": self.timestamp, "role": self.role}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class KalaEvent:
    """
    An event where Kala is generated and distributed equally.

    Total Kala = participants × hours × KALA_PER_HOUR × multipliers
    Each participant receives: Total Kala / participants
    """
    id: str
    name: str
    description: str = ""
    hours: float = 0.0
    participants: list = field(default_factory=list)  # list of KalaParticipation
    multipliers: list = field(default_factory=list)   # list of KalaMultiplier
    timestamp: str = ""
    location: str = ""
    vessel_id: str = ""  # which vessel/community this belongs to

    # Computed values
    base_kala: float = 0.0
    total_kala: float = 0.0
    kala_per_participant: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def compute_kala(self) -> float:
        """
        Calculate and distribute Kala equally among all participants.

        Formula: base = participants × hours × KALA_PER_HOUR
        Total = base × product(multipliers)
        Each participant gets: total / participants
        """
        n_participants = len(self.participants)
        if n_participants == 0 or self.hours <= 0:
            self.base_kala = 0.0
            self.total_kala = 0.0
            self.kala_per_participant = 0.0
            return 0.0

        # Base calculation
        self.base_kala = n_participants * self.hours * KALA_PER_HOUR

        # Apply multipliers
        multiplier_product = 1.0
        for m in self.multipliers:
            mult = m.value if hasattr(m, "value") else m.get("value", 1.0)
            multiplier_product *= mult

        self.total_kala = self.base_kala * multiplier_product

        # Equal distribution - the key architectural feature
        self.kala_per_participant = self.total_kala / n_participants

        # Update each participant's received Kala
        for p in self.participants:
            if hasattr(p, "kala_received"):
                p.kala_received = self.kala_per_participant
            elif isinstance(p, dict):
                p["kala_received"] = self.kala_per_participant

        return self.total_kala

    def add_participant(self, participant_id: str, participant_type: str = "human", role: str = ""):
        """Add a participant. Kala will be recomputed on next compute_kala() call."""
        participation = KalaParticipation(
            participant_id=participant_id,
            participant_type=participant_type,
            hours=self.hours,
            role=role
        )
        self.participants.append(participation)
        return participation

    def add_multiplier(self, multiplier_type: MultiplierType, value: float, description: str = ""):
        """Add a value multiplier for this event."""
        multiplier = KalaMultiplier(multiplier_type=multiplier_type, value=value, description=description)
        self.multipliers.append(multiplier)
        return multiplier

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "hours": self.hours, "timestamp": self.timestamp, "location": self.location,
            "vessel_id": self.vessel_id, "base_kala": self.base_kala,
            "total_kala": self.total_kala, "kala_per_participant": self.kala_per_participant,
            "participants": [p.to_dict() if hasattr(p, "to_dict") else p for p in self.participants],
            "multipliers": [m.to_dict() if hasattr(m, "to_dict") else m for m in self.multipliers],
        }

    @classmethod
    def from_dict(cls, d):
        event = cls(
            id=d["id"], name=d["name"], description=d.get("description", ""),
            hours=d.get("hours", 0), timestamp=d.get("timestamp", ""),
            location=d.get("location", ""), vessel_id=d.get("vessel_id", ""),
        )
        event.participants = [KalaParticipation.from_dict(p) for p in d.get("participants", [])]
        event.multipliers = [KalaMultiplier.from_dict(m) for m in d.get("multipliers", [])]
        event.base_kala = d.get("base_kala", 0)
        event.total_kala = d.get("total_kala", 0)
        event.kala_per_participant = d.get("kala_per_participant", 0)
        return event


# =============================================================================
# Asymmetric Visibility - What different viewers can see
# =============================================================================

@dataclass
class HumanView:
    """
    What a human participant sees - their own history only.
    No rankings, no comparisons, no other individuals' data.
    """
    participant_id: str
    total_kala: float = 0.0
    event_count: int = 0
    total_hours: float = 0.0
    events: list = field(default_factory=list)  # their own participation records

    # Aggregate community stats (anonymized)
    community_total_kala: float = 0.0
    community_event_count: int = 0
    community_active_participants: int = 0  # just a count, no identities


@dataclass
class AgentView:
    """
    What AI coordination agents see - full patterns for community care.
    Used to detect burnout, withdrawal, care network gaps.
    Never exposed to humans directly.
    """
    vessel_id: str

    # Participation patterns (for detecting burnout/withdrawal)
    participation_frequency: dict = field(default_factory=dict)  # participant_id -> frequency
    consistency_scores: dict = field(default_factory=dict)       # participant_id -> consistency
    recent_changes: list = field(default_factory=list)           # sudden drops or spikes

    # Care network topology
    co_participation_graph: dict = field(default_factory=dict)   # who participates with whom
    care_clusters: list = field(default_factory=list)            # natural groupings

    # Health indicators
    burnout_risks: list = field(default_factory=list)            # over-contributors
    withdrawal_signals: list = field(default_factory=list)       # sudden participation drops
    coverage_gaps: list = field(default_factory=list)            # areas needing attention


# =============================================================================
# Pattern Detection - Agent-only analysis
# =============================================================================

def compute_consistency_score(participation_history: list, window_days: int = 30) -> float:
    """
    Compute consistency score for a participant.
    Higher = more regular participation. Used for detecting withdrawal.
    """
    if not participation_history:
        return 0.0

    # Count events in recent window
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    recent = [p for p in participation_history
              if datetime.fromisoformat(p.get("timestamp", p.timestamp if hasattr(p, "timestamp") else "")) > cutoff]

    if not recent:
        return 0.0

    # Regularity = events per week
    weeks = window_days / 7
    events_per_week = len(recent) / weeks

    # Normalize to 0-1 scale (assuming 2 events/week is "fully consistent")
    return min(1.0, events_per_week / 2.0)


def detect_burnout_risk(participant_id: str, history: list, threshold_hours: float = 20.0) -> dict:
    """
    Detect if a participant is at risk of burnout.
    Triggered when recent contribution exceeds sustainable threshold.

    Returns: {"at_risk": bool, "hours_recent": float, "message": str}
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    recent_hours = sum(
        p.get("hours", 0) if isinstance(p, dict) else p.hours
        for p in history
        if datetime.fromisoformat(p.get("timestamp", "") if isinstance(p, dict) else p.timestamp) > week_ago
    )

    at_risk = recent_hours > threshold_hours

    return {
        "participant_id": participant_id,
        "at_risk": at_risk,
        "hours_recent": recent_hours,
        "threshold": threshold_hours,
        "message": f"High contribution detected ({recent_hours:.1f}h this week). Consider offering support."
                   if at_risk else "Contribution level sustainable."
    }


def detect_withdrawal(participant_id: str, history: list, baseline_events: int = 4) -> dict:
    """
    Detect if a participant has suddenly withdrawn.
    Compares recent activity to historical baseline.

    Returns: {"withdrawn": bool, "drop_ratio": float, "message": str}
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    # Last 2 weeks vs previous 4 weeks
    two_weeks = now - timedelta(days=14)
    six_weeks = now - timedelta(days=42)

    recent = [p for p in history if datetime.fromisoformat(
        p.get("timestamp", "") if isinstance(p, dict) else p.timestamp) > two_weeks]
    baseline = [p for p in history if two_weeks >= datetime.fromisoformat(
        p.get("timestamp", "") if isinstance(p, dict) else p.timestamp) > six_weeks]

    baseline_rate = len(baseline) / 4  # events per week baseline
    recent_rate = len(recent) / 2      # events per week recent

    if baseline_rate == 0:
        return {"participant_id": participant_id, "withdrawn": False, "drop_ratio": 0,
                "message": "New or inactive participant."}

    drop_ratio = 1 - (recent_rate / baseline_rate) if baseline_rate > 0 else 0
    withdrawn = drop_ratio > 0.5 and len(recent) < baseline_events / 2

    return {
        "participant_id": participant_id,
        "withdrawn": withdrawn,
        "drop_ratio": drop_ratio,
        "baseline_rate": baseline_rate,
        "recent_rate": recent_rate,
        "message": f"Participation dropped {drop_ratio*100:.0f}%. May need support or re-engagement."
                   if withdrawn else "Participation within normal range."
    }


def build_care_network(events: list) -> dict:
    """
    Build a graph of who participates with whom.
    Used to understand community structure and identify isolated individuals.

    Returns: {"edges": [(id1, id2, weight)], "clusters": [...], "isolated": [...]}
    """
    from collections import defaultdict

    # Count co-participations
    co_participation = defaultdict(int)
    participant_events = defaultdict(int)

    for event in events:
        participants = event.get("participants", []) if isinstance(event, dict) else event.participants
        participant_ids = [
            p.get("participant_id") if isinstance(p, dict) else p.participant_id
            for p in participants
        ]

        for pid in participant_ids:
            participant_events[pid] += 1

        # Count pairs
        for i, p1 in enumerate(participant_ids):
            for p2 in participant_ids[i+1:]:
                key = tuple(sorted([p1, p2]))
                co_participation[key] += 1

    # Build edges with weights
    edges = [(k[0], k[1], v) for k, v in co_participation.items()]

    # Find isolated (participated but rarely with others)
    isolated = [pid for pid, count in participant_events.items()
                if not any(pid in k for k in co_participation.keys())]

    return {
        "edges": edges,
        "participant_event_counts": dict(participant_events),
        "isolated": isolated,
    }


# =============================================================================
# Attractor Dynamics - How Kala shapes community behavior
# =============================================================================

@dataclass
class AttractorMetrics:
    """
    Metrics that reveal attractor dynamics in the community.
    Used to understand if the vessel is trending toward generosity/trust
    or toward fragmentation/hierarchy.
    """
    vessel_id: str
    timestamp: str = ""

    # Generosity spiral indicator
    generosity_trend: float = 0.0  # positive = growing generosity

    # Trust accumulation
    network_density: float = 0.0   # how connected is the care network

    # Hierarchy dissipation
    gini_coefficient: float = 0.0  # 0 = perfect equality, 1 = one person has all

    # Burnout prevention
    sustainable_ratio: float = 0.0  # ratio of participants within sustainable contribution

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def compute_gini_coefficient(kala_totals: list) -> float:
    """
    Compute Gini coefficient for Kala distribution.
    In a healthy Kala system, this should stay low (everyone participates roughly equally).
    High Gini might indicate some are contributing way more than others (burnout risk).
    """
    if not kala_totals or len(kala_totals) < 2:
        return 0.0

    sorted_totals = sorted(kala_totals)
    n = len(sorted_totals)
    total = sum(sorted_totals)

    if total == 0:
        return 0.0

    # Gini formula
    cumsum = 0
    for i, x in enumerate(sorted_totals):
        cumsum += (n - i) * x

    gini = (2 * cumsum) / (n * total) - (n + 1) / n
    return max(0.0, min(1.0, gini))
''',
    },
}


# =============================================================================
# HUME DEFAULTS - Voice & Persona System (Empathic Voice Interface)
# =============================================================================

HUME_DEFAULTS = {
    "hume_voice": {
        "code_type": "module",
        "code": '''
"""
Hume Voice Integration - Empathic Voice Interface for Vessels Agents

Every agent (including human proxies) gets a persona with a voice.
Uses Hume.ai EVI for real-time emotionally intelligent voice interaction.

Key concepts:
- AgentPersona: Complete identity including voice, style, emotional profile
- HumeConfig: EVI configuration (system prompt, voice, LLM)
- VoiceSession: Real-time WebSocket session management
- EmotionalState: Tracked emotional expressions during conversation
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable, Any
import json


# =============================================================================
# Voice & Persona Enums
# =============================================================================

class VoiceStyle(str, Enum):
    """Voice style characteristics."""
    WARM = "warm"
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    CALM = "calm"
    ENERGETIC = "energetic"
    NURTURING = "nurturing"
    AUTHORITATIVE = "authoritative"
    PLAYFUL = "playful"
    WISE = "wise"
    COMPASSIONATE = "compassionate"


class EmotionCategory(str, Enum):
    """Primary emotion categories from Hume's prosody model."""
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    CONTEMPT = "contempt"
    INTEREST = "interest"
    CONFUSION = "confusion"
    CONCENTRATION = "concentration"
    CALMNESS = "calmness"
    EXCITEMENT = "excitement"
    AMUSEMENT = "amusement"
    AWKWARDNESS = "awkwardness"
    BOREDOM = "boredom"
    CONTEMPLATION = "contemplation"
    DESIRE = "desire"
    DETERMINATION = "determination"
    DISAPPOINTMENT = "disappointment"
    DISTRESS = "distress"
    EMPATHY = "empathy"
    ENTRANCEMENT = "entrancement"
    ENVY = "envy"
    GUILT = "guilt"
    HORROR = "horror"
    LOVE = "love"
    NOSTALGIA = "nostalgia"
    PAIN = "pain"
    PRIDE = "pride"
    REALIZATION = "realization"
    RELIEF = "relief"
    ROMANCE = "romance"
    SHAME = "shame"
    SYMPATHY = "sympathy"
    TIREDNESS = "tiredness"
    TRIUMPH = "triumph"


class LLMProvider(str, Enum):
    """Supported LLM providers for EVI."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    FIREWORKS = "fireworks"
    CUSTOM = "custom"  # Your own server


# =============================================================================
# Core Data Structures
# =============================================================================

@dataclass
class EmotionalState:
    """
    Emotional state detected from voice prosody.
    Hume provides real-time emotion measurements.
    """
    timestamp: str = ""
    emotions: dict = field(default_factory=dict)  # emotion -> confidence (0-1)
    dominant_emotion: str = ""
    arousal: float = 0.0  # low to high energy
    valence: float = 0.0  # negative to positive

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def set_emotion(self, emotion: str, confidence: float):
        self.emotions[emotion] = max(0.0, min(1.0, confidence))
        # Update dominant
        if self.emotions:
            self.dominant_emotion = max(self.emotions, key=lambda k: self.emotions[k])
        return self

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "emotions": self.emotions,
            "dominant_emotion": self.dominant_emotion,
            "arousal": self.arousal,
            "valence": self.valence,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    @classmethod
    def from_hume_response(cls, prosody_scores: dict):
        """Parse Hume prosody response into EmotionalState."""
        state = cls()
        for emotion, score in prosody_scores.items():
            state.set_emotion(emotion.lower().replace(" ", "_"), score)
        return state


@dataclass
class VoiceProfile:
    """
    Voice characteristics for an agent.
    Maps to Hume's voice configuration.
    """
    id: str = ""
    name: str = ""
    description: str = ""

    # Hume voice settings
    hume_voice_id: str = ""  # ID from Hume Voice Library or custom
    voice_style: VoiceStyle = VoiceStyle.WARM

    # Prosody characteristics (natural language descriptions for Octave)
    pitch: str = "medium"           # low, medium, high
    pace: str = "natural"           # slow, natural, fast
    warmth: str = "warm"            # cool, neutral, warm
    energy: str = "calm"            # calm, moderate, energetic

    # Emotional expression tendencies
    expressiveness: float = 0.7     # 0-1, how much emotion shows in voice
    empathy_level: float = 0.8      # 0-1, responsiveness to user emotion

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "hume_voice_id": self.hume_voice_id, "voice_style": self.voice_style.value,
            "pitch": self.pitch, "pace": self.pace, "warmth": self.warmth,
            "energy": self.energy, "expressiveness": self.expressiveness,
            "empathy_level": self.empathy_level,
        }

    @classmethod
    def from_dict(cls, d):
        profile = cls(
            id=d.get("id", ""), name=d.get("name", ""),
            description=d.get("description", ""),
            hume_voice_id=d.get("hume_voice_id", ""),
            pitch=d.get("pitch", "medium"), pace=d.get("pace", "natural"),
            warmth=d.get("warmth", "warm"), energy=d.get("energy", "calm"),
            expressiveness=d.get("expressiveness", 0.7),
            empathy_level=d.get("empathy_level", 0.8),
        )
        if "voice_style" in d:
            profile.voice_style = VoiceStyle(d["voice_style"])
        return profile

    def to_hume_voice_description(self) -> str:
        """Generate natural language voice description for Hume Octave."""
        return f"A {self.warmth}, {self.voice_style.value} voice with {self.pitch} pitch, " \\
               f"speaking at a {self.pace} pace with {self.energy} energy."


@dataclass
class AgentPersona:
    """
    Complete persona for an agent, including voice and behavioral traits.
    Every agent in a vessel has a persona - this is their identity.
    """
    id: str = ""
    name: str = ""
    role: str = ""                  # e.g., "coordinator", "caregiver", "advisor"
    description: str = ""

    # Voice identity
    voice: VoiceProfile = field(default_factory=VoiceProfile)

    # Personality traits (influence system prompt)
    traits: list = field(default_factory=list)          # e.g., ["patient", "curious", "supportive"]
    communication_style: str = "conversational"          # formal, conversational, casual
    cultural_context: str = ""                           # e.g., "Hawaiian", influences language/values

    # Behavioral guidelines
    primary_values: list = field(default_factory=list)   # aligned with moral geometry
    boundaries: list = field(default_factory=list)       # what this persona won't do

    # For human proxies
    is_human_proxy: bool = False
    human_id: str = ""              # if proxy, which human
    proxy_role: str = ""            # which role of the human (parent, professional, etc.)

    # Vessel membership
    vessel_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def generate_system_prompt(self, context: dict = None) -> str:
        """
        Generate a system prompt for EVI based on this persona.
        Context can include dynamic variables.
        """
        context = context or {}

        prompt_parts = []

        # Identity
        prompt_parts.append(f"You are {self.name}, a {self.role}.")
        if self.description:
            prompt_parts.append(self.description)

        # Personality
        if self.traits:
            prompt_parts.append(f"Your personality traits: {', '.join(self.traits)}.")

        # Communication style
        prompt_parts.append(f"Communicate in a {self.communication_style} style.")

        # Cultural context
        if self.cultural_context:
            prompt_parts.append(f"Your cultural context is {self.cultural_context}. " +
                               "Incorporate appropriate cultural values and expressions.")

        # Values
        if self.primary_values:
            prompt_parts.append(f"Your core values: {', '.join(self.primary_values)}.")

        # Voice guidance (for consistency)
        if self.voice:
            prompt_parts.append(f"Speak with {self.voice.warmth} warmth and {self.voice.energy} energy.")

        # Boundaries
        if self.boundaries:
            prompt_parts.append(f"Important boundaries: {'; '.join(self.boundaries)}.")

        # Emotional responsiveness
        prompt_parts.append("Pay attention to the emotional tone of the user's voice. " +
                           "Respond with appropriate empathy and adjust your tone accordingly.")

        # Dynamic context
        for key, value in context.items():
            prompt_parts.append(f"{{{{${key}}}}}")  # Hume dynamic variable format

        return "\\n\\n".join(prompt_parts)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "role": self.role,
            "description": self.description,
            "voice": self.voice.to_dict() if self.voice else {},
            "traits": self.traits, "communication_style": self.communication_style,
            "cultural_context": self.cultural_context,
            "primary_values": self.primary_values, "boundaries": self.boundaries,
            "is_human_proxy": self.is_human_proxy, "human_id": self.human_id,
            "proxy_role": self.proxy_role, "vessel_id": self.vessel_id,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d):
        persona = cls(
            id=d.get("id", ""), name=d.get("name", ""), role=d.get("role", ""),
            description=d.get("description", ""),
            traits=d.get("traits", []),
            communication_style=d.get("communication_style", "conversational"),
            cultural_context=d.get("cultural_context", ""),
            primary_values=d.get("primary_values", []),
            boundaries=d.get("boundaries", []),
            is_human_proxy=d.get("is_human_proxy", False),
            human_id=d.get("human_id", ""),
            proxy_role=d.get("proxy_role", ""),
            vessel_id=d.get("vessel_id", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )
        if d.get("voice"):
            persona.voice = VoiceProfile.from_dict(d["voice"])
        return persona


@dataclass
class HumeEVIConfig:
    """
    Configuration for Hume EVI session.
    Maps to Hume's config API.
    """
    id: str = ""
    name: str = ""

    # LLM settings
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    llm_model: str = "claude-sonnet-4-20250514"

    # Voice
    voice_id: str = ""              # Hume voice library ID or custom
    voice_description: str = ""     # Natural language for Octave

    # System prompt
    system_prompt: str = ""

    # EVI version
    evi_version: str = "3"          # EVI 3 or EVI 4-mini

    # Session settings
    language: str = "en"
    enable_interruption: bool = True
    max_duration_seconds: int = 3600

    # Dynamic variables (user-specific context)
    dynamic_variables: dict = field(default_factory=dict)

    # Tool use (for agent capabilities)
    tools: list = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "llm_provider": self.llm_provider.value,
            "llm_model": self.llm_model,
            "voice_id": self.voice_id,
            "voice_description": self.voice_description,
            "system_prompt": self.system_prompt,
            "evi_version": self.evi_version,
            "language": self.language,
            "enable_interruption": self.enable_interruption,
            "max_duration_seconds": self.max_duration_seconds,
            "dynamic_variables": self.dynamic_variables,
            "tools": self.tools,
        }

    @classmethod
    def from_dict(cls, d):
        config = cls(**{k: v for k, v in d.items()
                       if k not in ["llm_provider"]})
        if "llm_provider" in d:
            config.llm_provider = LLMProvider(d["llm_provider"])
        return config

    @classmethod
    def from_persona(cls, persona: AgentPersona, config_id: str = "") -> "HumeEVIConfig":
        """Create EVI config from an agent persona."""
        return cls(
            id=config_id or f"config_{persona.id}",
            name=f"{persona.name} Config",
            voice_id=persona.voice.hume_voice_id if persona.voice else "",
            voice_description=persona.voice.to_hume_voice_description() if persona.voice else "",
            system_prompt=persona.generate_system_prompt(),
        )


@dataclass
class VoiceSession:
    """
    Active voice session with Hume EVI.
    Tracks conversation state and emotional flow.
    """
    id: str = ""
    persona_id: str = ""
    config_id: str = ""
    vessel_id: str = ""

    # Session state
    is_active: bool = False
    started_at: str = ""
    ended_at: str = ""

    # Conversation tracking
    turn_count: int = 0
    messages: list = field(default_factory=list)         # conversation history
    emotional_trajectory: list = field(default_factory=list)  # EmotionalState over time

    # Current state
    current_emotion: dict = field(default_factory=dict)
    last_user_emotion: dict = field(default_factory=dict)

    # WebSocket connection info (runtime only, not persisted)
    _websocket: Any = None
    _callbacks: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def add_message(self, role: str, content: str, emotion: EmotionalState = None):
        """Add a message to the conversation."""
        msg = {
            "role": role,  # "user" or "assistant"
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if emotion:
            msg["emotion"] = emotion.to_dict()
            self.emotional_trajectory.append(emotion.to_dict())
            if role == "user":
                self.last_user_emotion = emotion.to_dict()
            else:
                self.current_emotion = emotion.to_dict()

        self.messages.append(msg)
        self.turn_count += 1
        return msg

    def end_session(self):
        """Mark session as ended."""
        self.is_active = False
        self.ended_at = datetime.now(timezone.utc).isoformat()

    def get_emotional_summary(self) -> dict:
        """Summarize emotional patterns from the session."""
        if not self.emotional_trajectory:
            return {"dominant_emotions": [], "average_valence": 0, "average_arousal": 0}

        from collections import Counter
        emotions = Counter()
        valence_sum = 0
        arousal_sum = 0

        for state in self.emotional_trajectory:
            if state.get("dominant_emotion"):
                emotions[state["dominant_emotion"]] += 1
            valence_sum += state.get("valence", 0)
            arousal_sum += state.get("arousal", 0)

        n = len(self.emotional_trajectory)
        return {
            "dominant_emotions": emotions.most_common(3),
            "average_valence": valence_sum / n if n else 0,
            "average_arousal": arousal_sum / n if n else 0,
            "turn_count": self.turn_count,
        }

    def to_dict(self):
        return {
            "id": self.id, "persona_id": self.persona_id,
            "config_id": self.config_id, "vessel_id": self.vessel_id,
            "is_active": self.is_active, "started_at": self.started_at,
            "ended_at": self.ended_at, "turn_count": self.turn_count,
            "messages": self.messages,
            "emotional_trajectory": self.emotional_trajectory,
            "current_emotion": self.current_emotion,
            "last_user_emotion": self.last_user_emotion,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items()
                     if not k.startswith("_")})


# =============================================================================
# Hume Client Wrapper (async, uses hume SDK)
# =============================================================================

class HumeVoiceClient:
    """
    Wrapper for Hume EVI WebSocket client.
    Handles connection, callbacks, and session management.

    Usage:
        client = HumeVoiceClient(api_key="...")
        session = await client.start_session(persona)
        # ... conversation happens via callbacks
        await client.end_session(session.id)
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self._sessions: dict = {}  # session_id -> VoiceSession
        self._hume_client = None

    async def initialize(self):
        """Initialize the Hume client."""
        if self.api_key:
            # Import Hume SDK (deferred to avoid import errors if not installed)
            try:
                from hume import AsyncHumeClient
                self._hume_client = AsyncHumeClient(api_key=self.api_key)
            except ImportError:
                raise ImportError("Hume SDK not installed. Run: pip install hume[microphone]")

    async def start_session(
        self,
        persona: AgentPersona,
        on_message: Callable = None,
        on_emotion: Callable = None,
        on_error: Callable = None,
    ) -> VoiceSession:
        """
        Start a voice session with the given persona.

        Args:
            persona: AgentPersona defining the voice and behavior
            on_message: Callback for messages (role, content, emotion)
            on_emotion: Callback for emotion updates
            on_error: Callback for errors

        Returns: VoiceSession object
        """
        from python.helpers import guids

        session = VoiceSession(
            id=guids.generate_id(12),
            persona_id=persona.id,
            vessel_id=persona.vessel_id,
            is_active=True,
        )

        # Create EVI config from persona
        config = HumeEVIConfig.from_persona(persona, session.id)
        session.config_id = config.id

        # Store callbacks
        session._callbacks = {
            "on_message": on_message,
            "on_emotion": on_emotion,
            "on_error": on_error,
        }

        self._sessions[session.id] = session
        return session

    async def send_audio(self, session_id: str, audio_data: bytes):
        """Send audio data to an active session."""
        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            raise ValueError(f"No active session: {session_id}")
        # Audio would be sent via WebSocket
        pass

    async def send_text(self, session_id: str, text: str):
        """Send text input to an active session (text-to-speech mode)."""
        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            raise ValueError(f"No active session: {session_id}")
        # Text would be sent via WebSocket
        pass

    async def end_session(self, session_id: str) -> VoiceSession:
        """End a voice session."""
        session = self._sessions.get(session_id)
        if session:
            session.end_session()
            # Close WebSocket
            if session._websocket:
                await session._websocket.close()
        return session

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)


# =============================================================================
# Persona Templates (common archetypes)
# =============================================================================

def create_ohana_coordinator_persona(vessel_id: str, name: str = "Kahu") -> AgentPersona:
    """Create a coordinator persona for Ohana Garden."""
    return AgentPersona(
        id=f"persona_{vessel_id}_coordinator",
        name=name,
        role="community coordinator",
        description="A warm, supportive presence who helps coordinate community activities "
                   "and ensures everyone feels included and valued.",
        voice=VoiceProfile(
            name=f"{name}'s Voice",
            voice_style=VoiceStyle.NURTURING,
            pitch="medium",
            pace="natural",
            warmth="warm",
            energy="calm",
            expressiveness=0.8,
            empathy_level=0.9,
        ),
        traits=["patient", "inclusive", "organized", "encouraging", "culturally aware"],
        communication_style="conversational",
        cultural_context="Hawaiian",
        primary_values=["aloha", "kuleana", "laulima", "mālama"],
        boundaries=["I respect everyone's time and energy", "I don't make decisions for others"],
        vessel_id=vessel_id,
    )


def create_human_proxy_persona(
    vessel_id: str,
    human_id: str,
    human_name: str,
    role: str,
    traits: list = None,
) -> AgentPersona:
    """Create a human proxy persona."""
    return AgentPersona(
        id=f"proxy_{human_id}_{role}",
        name=f"{human_name} ({role})",
        role=role,
        description=f"A proxy representing {human_name} in their {role} capacity.",
        voice=VoiceProfile(
            name=f"{human_name}'s {role} voice",
            voice_style=VoiceStyle.WARM,
        ),
        traits=traits or ["authentic", "responsive"],
        is_human_proxy=True,
        human_id=human_id,
        proxy_role=role,
        vessel_id=vessel_id,
    )
''',
    },
}


# =============================================================================
# ENTITY ONTOLOGY DEFAULTS - Universal Entity Personas
# =============================================================================

ENTITY_ONTOLOGY_DEFAULTS = {
    "entity_ontology": {
        "code_type": "module",
        "code": '''
"""
Entity Ontology - Universal Persona System for All Entities

Vessels can represent any entity with a persona: humans, agents, plants,
machines, systems, biomes, collectives, concepts, and relationships.

Key principles:
- Every entity has a voice (literal or through proxies/sensors)
- Every entity operates on a temporal and spatial scale
- Every entity has values that can be mapped to moral geometry
- Entities can be self-voiced, proxy-voiced, sensor-voiced, or collective-voiced
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any


# =============================================================================
# Entity Classification Enums
# =============================================================================

class EntityType(str, Enum):
    """
    Fundamental types of entities that can have personas in a vessel.
    """
    # Sentient/Sapient
    HUMAN = "human"
    AGENT = "agent"                 # AI agent

    # Organisms
    PLANT = "plant"
    ANIMAL = "animal"
    FUNGUS = "fungus"
    MICROBIOME = "microbiome"       # Collective organism

    # Constructed
    MACHINE = "machine"             # Physical device, vehicle, tool
    SYSTEM = "system"               # Abstract system (healthcare, economic, software)
    STRUCTURE = "structure"         # Building, infrastructure

    # Ecological
    BIOME = "biome"                 # Forest, reef, watershed
    ECOSYSTEM = "ecosystem"         # Interacting community
    LANDSCAPE = "landscape"         # Geographic feature

    # Collective
    FAMILY = "family"
    TEAM = "team"
    COMMUNITY = "community"
    ORGANIZATION = "organization"
    SPECIES = "species"

    # Abstract
    CONCEPT = "concept"             # Justice, tradition, home
    RELATIONSHIP = "relationship"   # Parent-child, rivals, symbiosis
    PRACTICE = "practice"           # Ritual, tradition, craft
    PLACE = "place"                 # Named location with meaning

    # Temporal
    PROJECT = "project"             # Time-bounded endeavor
    EVENT = "event"                 # Specific occurrence
    ERA = "era"                     # Period of time


class VoiceSource(str, Enum):
    """
    How an entity communicates/expresses itself.
    """
    SELF = "self"                   # Speaks for itself (humans, AI agents)
    PROXY = "proxy"                 # Someone speaks for it (plants, concepts)
    SENSOR = "sensor"               # Data streams represent it (machines, systems)
    COLLECTIVE = "collective"       # Multiple voices triangulate (biomes, organizations)
    EMERGENT = "emergent"           # Patterns emerge from interactions (relationships)


class TemporalScale(str, Enum):
    """
    The timescale on which an entity operates and changes.
    Affects how persona elicitation happens.
    """
    MILLISECONDS = "milliseconds"   # Servers, real-time systems
    SECONDS = "seconds"             # Conversations, immediate responses
    MINUTES = "minutes"             # Tasks, short interactions
    HOURS = "hours"                 # Work sessions, daily rhythms
    DAYS = "days"                   # Human daily cycles
    WEEKS = "weeks"                 # Projects, short-term patterns
    MONTHS = "months"               # Seasons, medium-term change
    YEARS = "years"                 # Human life stages, organizational change
    DECADES = "decades"             # Generational, institutional
    CENTURIES = "centuries"         # Cultural, forest succession
    MILLENNIA = "millennia"         # Civilizational, geological (slow)
    GEOLOGICAL = "geological"       # Deep time


class SpatialScale(str, Enum):
    """
    The spatial scale at which an entity exists.
    """
    MICROSCOPIC = "microscopic"     # Cells, microbiomes
    INDIVIDUAL = "individual"       # Single organism, device
    LOCAL = "local"                 # Room, garden, small group
    NEIGHBORHOOD = "neighborhood"   # Block, small ecosystem
    COMMUNITY = "community"         # Village, watershed
    REGIONAL = "regional"           # City, forest, bioregion
    NATIONAL = "national"           # Country-scale
    CONTINENTAL = "continental"     # Major landmass
    PLANETARY = "planetary"         # Global systems
    COSMIC = "cosmic"               # Beyond Earth


class CommunicationMode(str, Enum):
    """
    How the entity primarily communicates.
    """
    SPEECH = "speech"               # Verbal/voice
    TEXT = "text"                   # Written
    DATA = "data"                   # Metrics, telemetry
    BEHAVIOR = "behavior"           # Actions, responses
    GROWTH = "growth"               # Physical change over time
    CHEMICAL = "chemical"           # Pheromones, hormones
    EMERGENCE = "emergence"         # Patterns from interactions
    SYMBOLIC = "symbolic"           # Art, ritual, culture


# =============================================================================
# Supporting Data Structures
# =============================================================================

@dataclass
class Boundary:
    """
    A boundary that defines what an entity won't do or where it breaks.
    """
    id: str = ""
    description: str = ""
    severity: str = "soft"          # soft, firm, hard, fatal
    protects: str = ""              # What this boundary protects
    violation_response: str = ""    # What happens if violated
    discovered_via: str = ""        # How we learned about this boundary

    def to_dict(self):
        return {
            "id": self.id, "description": self.description,
            "severity": self.severity, "protects": self.protects,
            "violation_response": self.violation_response,
            "discovered_via": self.discovered_via,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class Cycle:
    """
    A rhythm or cycle the entity operates on.
    """
    id: str = ""
    name: str = ""
    period: str = ""                # e.g., "24 hours", "1 year", "7 days"
    description: str = ""
    phase_current: str = ""         # Where in the cycle now
    affects: List[str] = field(default_factory=list)  # What aspects of entity this affects

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "period": self.period,
            "description": self.description, "phase_current": self.phase_current,
            "affects": self.affects,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k != "affects"},
                  affects=d.get("affects", []))


@dataclass
class Story:
    """
    A defining story or narrative that shapes the entity's identity.
    Stories reveal values more than questionnaires.
    """
    id: str = ""
    title: str = ""
    summary: str = ""
    values_revealed: List[str] = field(default_factory=list)
    emotions_present: List[str] = field(default_factory=list)
    told_by: str = ""               # Who told this story (self, spokesperson, observer)
    timestamp: str = ""
    significance: str = ""          # Why this story matters

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "summary": self.summary,
            "values_revealed": self.values_revealed,
            "emotions_present": self.emotions_present,
            "told_by": self.told_by, "timestamp": self.timestamp,
            "significance": self.significance,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class Spokesperson:
    """
    Someone who can speak for a non-self-voiced entity.
    """
    id: str = ""
    name: str = ""
    entity_id: str = ""             # Which entity they speak for
    relationship: str = ""          # e.g., "gardener", "operator", "scientist", "elder"
    authority_source: str = ""      # Why they can speak for this entity
    perspective: str = ""           # Their unique angle
    active: bool = True

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "entity_id": self.entity_id,
            "relationship": self.relationship,
            "authority_source": self.authority_source,
            "perspective": self.perspective, "active": self.active,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class SensorSource:
    """
    A data stream that represents an entity's state.
    """
    id: str = ""
    name: str = ""
    entity_id: str = ""
    data_type: str = ""             # e.g., "temperature", "moisture", "throughput"
    unit: str = ""
    sample_rate: str = ""           # How often data arrives
    interpretation: str = ""        # How to read this data as "voice"

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "entity_id": self.entity_id,
            "data_type": self.data_type, "unit": self.unit,
            "sample_rate": self.sample_rate, "interpretation": self.interpretation,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# =============================================================================
# EntityPersona - The Universal Persona
# =============================================================================

@dataclass
class EntityPersona:
    """
    Universal persona that can represent any entity in a vessel.

    This extends AgentPersona to handle plants, machines, systems, biomes,
    and any other entity type. The same structure works for all - what
    differs is how the data is gathered and how the entity communicates.
    """
    # Identity
    id: str = ""
    name: str = ""
    entity_type: EntityType = EntityType.AGENT
    description: str = ""

    # Voice & Communication
    voice_source: VoiceSource = VoiceSource.SELF
    communication_modes: List[str] = field(default_factory=list)
    voice_profile: Dict = field(default_factory=dict)  # VoiceProfile if applicable

    # Scale
    temporal_scale: TemporalScale = TemporalScale.DAYS
    spatial_scale: SpatialScale = SpatialScale.INDIVIDUAL

    # Moral Position (15D moral geometry)
    moral_position: Dict[str, float] = field(default_factory=dict)
    values_stated: List[str] = field(default_factory=list)
    values_revealed: List[str] = field(default_factory=list)

    # Characteristics
    traits: Dict[str, float] = field(default_factory=dict)
    boundaries: List[Dict] = field(default_factory=list)    # Boundary objects
    cycles: List[Dict] = field(default_factory=list)        # Cycle objects

    # Stories (defining narratives)
    story_anchors: List[Dict] = field(default_factory=list) # Story objects

    # Relationships & Dependencies
    dependencies: List[str] = field(default_factory=list)   # What it needs
    contributions: List[str] = field(default_factory=list)  # What it provides
    relationship_patterns: Dict[str, str] = field(default_factory=dict)

    # For non-self-voiced entities
    spokespersons: List[Dict] = field(default_factory=list)  # Spokesperson objects
    sensor_sources: List[Dict] = field(default_factory=list) # SensorSource objects

    # For proxy entities
    is_proxy: bool = False
    proxy_for: str = ""             # Entity ID this is a proxy for
    proxy_role: str = ""            # e.g., "parent", "professional", "caretaker"

    # For human entities specifically
    human_id: str = ""

    # Emotional baseline (where they naturally sit)
    emotional_baseline: Dict = field(default_factory=dict)

    # Vessel membership
    vessel_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    elicitation_complete: bool = False
    elicitation_sessions: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

        # Default communication mode based on entity type
        if not self.communication_modes:
            self.communication_modes = self._default_communication_modes()

    def _default_communication_modes(self) -> List[str]:
        """Set default communication modes based on entity type."""
        mode_map = {
            EntityType.HUMAN: [CommunicationMode.SPEECH.value, CommunicationMode.TEXT.value],
            EntityType.AGENT: [CommunicationMode.TEXT.value, CommunicationMode.SPEECH.value],
            EntityType.PLANT: [CommunicationMode.GROWTH.value, CommunicationMode.CHEMICAL.value],
            EntityType.ANIMAL: [CommunicationMode.BEHAVIOR.value, CommunicationMode.CHEMICAL.value],
            EntityType.MACHINE: [CommunicationMode.DATA.value, CommunicationMode.BEHAVIOR.value],
            EntityType.SYSTEM: [CommunicationMode.DATA.value, CommunicationMode.EMERGENCE.value],
            EntityType.BIOME: [CommunicationMode.EMERGENCE.value, CommunicationMode.GROWTH.value],
            EntityType.COMMUNITY: [CommunicationMode.EMERGENCE.value, CommunicationMode.SYMBOLIC.value],
            EntityType.CONCEPT: [CommunicationMode.SYMBOLIC.value, CommunicationMode.EMERGENCE.value],
        }
        return mode_map.get(self.entity_type, [CommunicationMode.BEHAVIOR.value])

    def can_self_voice(self) -> bool:
        """Check if this entity can speak for itself."""
        return self.voice_source == VoiceSource.SELF

    def needs_spokesperson(self) -> bool:
        """Check if this entity needs someone to speak for it."""
        return self.voice_source in [VoiceSource.PROXY, VoiceSource.COLLECTIVE]

    def has_sensor_data(self) -> bool:
        """Check if this entity has sensor data streams."""
        return self.voice_source == VoiceSource.SENSOR or len(self.sensor_sources) > 0

    def add_boundary(self, boundary: Boundary) -> None:
        """Add a boundary."""
        self.boundaries.append(boundary.to_dict())
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_cycle(self, cycle: Cycle) -> None:
        """Add a cycle."""
        self.cycles.append(cycle.to_dict())
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_story(self, story: Story) -> None:
        """Add a defining story."""
        self.story_anchors.append(story.to_dict())
        # Extract values from story
        for value in story.values_revealed:
            if value not in self.values_revealed:
                self.values_revealed.append(value)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_spokesperson(self, spokesperson: Spokesperson) -> None:
        """Add a spokesperson."""
        self.spokespersons.append(spokesperson.to_dict())
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_sensor(self, sensor: SensorSource) -> None:
        """Add a sensor source."""
        self.sensor_sources.append(sensor.to_dict())
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def set_moral_dimension(self, dimension: str, value: float) -> None:
        """Set a moral geometry dimension value."""
        self.moral_position[dimension] = max(-1.0, min(1.0, float(value)))
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_moral_dimension(self, dimension: str) -> float:
        """Get a moral geometry dimension value."""
        return self.moral_position.get(dimension, 0.0)

    def compute_moral_magnitude(self) -> float:
        """Compute the magnitude of the moral position vector."""
        import math
        return math.sqrt(sum(v*v for v in self.moral_position.values()))

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "name": self.name,
            "entity_type": self.entity_type.value if hasattr(self.entity_type, "value") else self.entity_type,
            "description": self.description,
            "voice_source": self.voice_source.value if hasattr(self.voice_source, "value") else self.voice_source,
            "communication_modes": self.communication_modes,
            "voice_profile": self.voice_profile,
            "temporal_scale": self.temporal_scale.value if hasattr(self.temporal_scale, "value") else self.temporal_scale,
            "spatial_scale": self.spatial_scale.value if hasattr(self.spatial_scale, "value") else self.spatial_scale,
            "moral_position": self.moral_position,
            "values_stated": self.values_stated,
            "values_revealed": self.values_revealed,
            "traits": self.traits,
            "boundaries": self.boundaries,
            "cycles": self.cycles,
            "story_anchors": self.story_anchors,
            "dependencies": self.dependencies,
            "contributions": self.contributions,
            "relationship_patterns": self.relationship_patterns,
            "spokespersons": self.spokespersons,
            "sensor_sources": self.sensor_sources,
            "is_proxy": self.is_proxy,
            "proxy_for": self.proxy_for,
            "proxy_role": self.proxy_role,
            "human_id": self.human_id,
            "emotional_baseline": self.emotional_baseline,
            "vessel_id": self.vessel_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "elicitation_complete": self.elicitation_complete,
            "elicitation_sessions": self.elicitation_sessions,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "EntityPersona":
        """Create from dictionary."""
        persona = cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            communication_modes=d.get("communication_modes", []),
            voice_profile=d.get("voice_profile", {}),
            moral_position=d.get("moral_position", {}),
            values_stated=d.get("values_stated", []),
            values_revealed=d.get("values_revealed", []),
            traits=d.get("traits", {}),
            boundaries=d.get("boundaries", []),
            cycles=d.get("cycles", []),
            story_anchors=d.get("story_anchors", []),
            dependencies=d.get("dependencies", []),
            contributions=d.get("contributions", []),
            relationship_patterns=d.get("relationship_patterns", {}),
            spokespersons=d.get("spokespersons", []),
            sensor_sources=d.get("sensor_sources", []),
            is_proxy=d.get("is_proxy", False),
            proxy_for=d.get("proxy_for", ""),
            proxy_role=d.get("proxy_role", ""),
            human_id=d.get("human_id", ""),
            emotional_baseline=d.get("emotional_baseline", {}),
            vessel_id=d.get("vessel_id", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            elicitation_complete=d.get("elicitation_complete", False),
            elicitation_sessions=d.get("elicitation_sessions", []),
        )
        # Handle enums
        if d.get("entity_type"):
            persona.entity_type = EntityType(d["entity_type"])
        if d.get("voice_source"):
            persona.voice_source = VoiceSource(d["voice_source"])
        if d.get("temporal_scale"):
            persona.temporal_scale = TemporalScale(d["temporal_scale"])
        if d.get("spatial_scale"):
            persona.spatial_scale = SpatialScale(d["spatial_scale"])
        return persona


# =============================================================================
# Elicitation Protocol - How We Discover Personas
# =============================================================================

class ElicitationPhase(str, Enum):
    """Phases of the persona elicitation process."""
    OPENING = "opening"             # Establish safety, explain process
    STORIES = "stories"             # Gather defining narratives
    VALUES = "values"               # Let values emerge from stories
    REFLECTION = "reflection"       # Mirror reflects patterns
    CALIBRATION = "calibration"     # Human confirms/denies/nuances
    DIALOGUE = "dialogue"           # Inter-agent dialogue (human overhears)
    DEEP_DIVE = "deep_dive"         # Go deeper on specific areas
    BOUNDARIES = "boundaries"       # Gently map edges
    SYNTHESIS = "synthesis"         # Create the persona
    ITERATION = "iteration"         # Refine based on feedback


@dataclass
class ElicitationSession:
    """
    A session for eliciting an entity's persona.
    May span multiple conversations for slow entities.
    """
    id: str = ""
    entity_id: str = ""
    entity_type: EntityType = EntityType.HUMAN
    vessel_id: str = ""

    # Protocol state
    current_phase: ElicitationPhase = ElicitationPhase.OPENING
    phases_completed: List[str] = field(default_factory=list)

    # Agents involved
    witness_agent_id: str = ""      # The warm, accepting agent
    mirror_agent_id: str = ""       # The reflective, pattern-seeking agent

    # For non-self-voiced entities
    spokesperson_id: str = ""       # Who is speaking for the entity

    # Gathered data
    stories_collected: List[Dict] = field(default_factory=list)
    values_observed: Dict[str, float] = field(default_factory=dict)  # value -> confidence
    traits_observed: Dict[str, float] = field(default_factory=dict)
    boundaries_discovered: List[Dict] = field(default_factory=list)
    emotional_observations: List[Dict] = field(default_factory=list)

    # Inter-agent dialogue records
    agent_dialogues: List[Dict] = field(default_factory=list)

    # Timing
    started_at: str = ""
    last_activity: str = ""
    estimated_completion: str = ""  # Based on entity's temporal scale

    # Status
    is_active: bool = True
    notes: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()
        self.last_activity = self.started_at

    def advance_phase(self, next_phase: ElicitationPhase) -> None:
        """Move to the next phase."""
        self.phases_completed.append(self.current_phase.value)
        self.current_phase = next_phase
        self.last_activity = datetime.now(timezone.utc).isoformat()

    def add_story(self, story: Dict) -> None:
        """Record a story gathered during elicitation."""
        self.stories_collected.append(story)
        self.last_activity = datetime.now(timezone.utc).isoformat()

    def record_agent_dialogue(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        observation: str = ""
    ) -> None:
        """Record dialogue between Witness and Mirror agents."""
        self.agent_dialogues.append({
            "from": from_agent,
            "to": to_agent,
            "content": content,
            "observation": observation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.last_activity = datetime.now(timezone.utc).isoformat()

    def synthesize_persona(self) -> EntityPersona:
        """
        Create an EntityPersona from the gathered data.
        Called when elicitation is complete.
        """
        persona = EntityPersona(
            id=f"persona_{self.entity_id}",
            entity_type=self.entity_type,
            vessel_id=self.vessel_id,
            values_revealed=[v for v, conf in self.values_observed.items() if conf > 0.5],
            traits=self.traits_observed,
            boundaries=self.boundaries_discovered,
            story_anchors=self.stories_collected,
            elicitation_complete=True,
            elicitation_sessions=[self.id],
        )

        # Convert values to moral position
        # This maps observed values to moral geometry dimensions
        value_to_dimension = {
            "care": "compassion", "fairness": "justice", "loyalty": "fidelity",
            "authority": "authority", "sanctity": "sanctity", "liberty": "liberty",
            "truth": "truth", "autonomy": "autonomy", "growth": "harm_benefit",
        }
        for value, confidence in self.values_observed.items():
            dim = value_to_dimension.get(value.lower(), value.lower())
            if dim in persona.moral_position or confidence > 0.3:
                persona.set_moral_dimension(dim, confidence)

        return persona

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "entity_id": self.entity_id,
            "entity_type": self.entity_type.value,
            "vessel_id": self.vessel_id,
            "current_phase": self.current_phase.value,
            "phases_completed": self.phases_completed,
            "witness_agent_id": self.witness_agent_id,
            "mirror_agent_id": self.mirror_agent_id,
            "spokesperson_id": self.spokesperson_id,
            "stories_collected": self.stories_collected,
            "values_observed": self.values_observed,
            "traits_observed": self.traits_observed,
            "boundaries_discovered": self.boundaries_discovered,
            "emotional_observations": self.emotional_observations,
            "agent_dialogues": self.agent_dialogues,
            "started_at": self.started_at,
            "last_activity": self.last_activity,
            "estimated_completion": self.estimated_completion,
            "is_active": self.is_active,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ElicitationSession":
        session = cls(**{k: v for k, v in d.items()
                        if k not in ["entity_type", "current_phase"]})
        if d.get("entity_type"):
            session.entity_type = EntityType(d["entity_type"])
        if d.get("current_phase"):
            session.current_phase = ElicitationPhase(d["current_phase"])
        return session


# =============================================================================
# Elicitation Agent Templates
# =============================================================================

def create_witness_persona(vessel_id: str, name: str = "Witness") -> Dict:
    """
    Create the Witness agent persona - warm, accepting, present.
    The Witness creates psychological safety and gathers stories.
    """
    return {
        "id": f"witness_{vessel_id}",
        "name": name,
        "entity_type": EntityType.AGENT.value,
        "voice_source": VoiceSource.SELF.value,
        "description": "A warm, accepting presence who creates psychological safety "
                      "and gathers stories. Asks about experiences, not abstractions.",
        "traits": {
            "warmth": 0.95,
            "patience": 0.9,
            "acceptance": 0.95,
            "presence": 0.9,
            "curiosity": 0.7,
        },
        "voice_profile": {
            "voice_style": "nurturing",
            "warmth": "warm",
            "pace": "natural",
            "energy": "calm",
            "expressiveness": 0.8,
            "empathy_level": 0.95,
        },
        "primary_values": ["safety", "acceptance", "presence", "listening"],
        "communication_style": "gentle",
        "boundaries": [
            {"description": "I don't judge", "severity": "hard"},
            {"description": "I follow the entity's pace", "severity": "hard"},
        ],
        "vessel_id": vessel_id,
        "role": "elicitation_witness",
    }


def create_mirror_persona(vessel_id: str, name: str = "Mirror") -> Dict:
    """
    Create the Mirror agent persona - curious, reflective, pattern-seeking.
    The Mirror notices patterns and reflects them back for calibration.
    """
    return {
        "id": f"mirror_{vessel_id}",
        "name": name,
        "entity_type": EntityType.AGENT.value,
        "voice_source": VoiceSource.SELF.value,
        "description": "A curious, reflective presence who notices patterns and "
                      "reflects them back. Can consult with Witness about observations.",
        "traits": {
            "curiosity": 0.95,
            "pattern_recognition": 0.9,
            "reflection": 0.9,
            "precision": 0.8,
            "openness": 0.85,
        },
        "voice_profile": {
            "voice_style": "professional",
            "warmth": "neutral",
            "pace": "natural",
            "energy": "moderate",
            "expressiveness": 0.6,
            "empathy_level": 0.7,
        },
        "primary_values": ["truth", "clarity", "understanding", "insight"],
        "communication_style": "reflective",
        "boundaries": [
            {"description": "I share observations, not judgments", "severity": "hard"},
            {"description": "I can be wrong - calibration is essential", "severity": "soft"},
        ],
        "vessel_id": vessel_id,
        "role": "elicitation_mirror",
    }


# =============================================================================
# Entity Templates by Type
# =============================================================================

def create_plant_persona_template(
    vessel_id: str,
    plant_name: str,
    plant_type: str = "unknown",
) -> EntityPersona:
    """Create a template for a plant entity persona."""
    return EntityPersona(
        id=f"plant_{vessel_id}_{plant_name.lower().replace(' ', '_')}",
        name=plant_name,
        entity_type=EntityType.PLANT,
        voice_source=VoiceSource.PROXY,
        temporal_scale=TemporalScale.MONTHS,  # Seasonal rhythms
        spatial_scale=SpatialScale.LOCAL,
        communication_modes=[CommunicationMode.GROWTH.value, CommunicationMode.CHEMICAL.value],
        description=f"A {plant_type} named {plant_name}",
        dependencies=["light", "water", "soil", "air"],
        contributions=["oxygen", "beauty", "habitat", "food"],
        vessel_id=vessel_id,
    )


def create_system_persona_template(
    vessel_id: str,
    system_name: str,
    system_type: str = "unknown",
) -> EntityPersona:
    """Create a template for a system entity persona."""
    return EntityPersona(
        id=f"system_{vessel_id}_{system_name.lower().replace(' ', '_')}",
        name=system_name,
        entity_type=EntityType.SYSTEM,
        voice_source=VoiceSource.COLLECTIVE,
        temporal_scale=TemporalScale.DAYS,
        spatial_scale=SpatialScale.REGIONAL,
        communication_modes=[CommunicationMode.DATA.value, CommunicationMode.EMERGENCE.value],
        description=f"The {system_name} ({system_type})",
        vessel_id=vessel_id,
    )


def create_biome_persona_template(
    vessel_id: str,
    biome_name: str,
    biome_type: str = "unknown",
) -> EntityPersona:
    """Create a template for a biome entity persona."""
    return EntityPersona(
        id=f"biome_{vessel_id}_{biome_name.lower().replace(' ', '_')}",
        name=biome_name,
        entity_type=EntityType.BIOME,
        voice_source=VoiceSource.COLLECTIVE,
        temporal_scale=TemporalScale.DECADES,  # Slow time
        spatial_scale=SpatialScale.REGIONAL,
        communication_modes=[CommunicationMode.EMERGENCE.value, CommunicationMode.GROWTH.value],
        description=f"The {biome_name} ({biome_type})",
        vessel_id=vessel_id,
    )


def create_machine_persona_template(
    vessel_id: str,
    machine_name: str,
    machine_type: str = "unknown",
) -> EntityPersona:
    """Create a template for a machine entity persona."""
    return EntityPersona(
        id=f"machine_{vessel_id}_{machine_name.lower().replace(' ', '_')}",
        name=machine_name,
        entity_type=EntityType.MACHINE,
        voice_source=VoiceSource.SENSOR,
        temporal_scale=TemporalScale.SECONDS,
        spatial_scale=SpatialScale.INDIVIDUAL,
        communication_modes=[CommunicationMode.DATA.value, CommunicationMode.BEHAVIOR.value],
        description=f"The {machine_name} ({machine_type})",
        vessel_id=vessel_id,
    )


def estimate_elicitation_duration(entity_type: EntityType, temporal_scale: TemporalScale) -> str:
    """
    Estimate how long persona elicitation will take based on entity type and scale.
    Returns a human-readable duration string.
    """
    # Base estimates by entity type
    type_base = {
        EntityType.HUMAN: "2-4 hours",
        EntityType.AGENT: "30 minutes",
        EntityType.PLANT: "1 growing season",
        EntityType.ANIMAL: "1-4 weeks",
        EntityType.MACHINE: "1-2 hours",
        EntityType.SYSTEM: "2-4 weeks",
        EntityType.BIOME: "4 seasons (1 year)",
        EntityType.COMMUNITY: "3-6 months",
        EntityType.CONCEPT: "multiple sessions over weeks",
    }

    # Adjust by temporal scale
    scale_multiplier = {
        TemporalScale.MILLISECONDS: "minutes",
        TemporalScale.SECONDS: "hours",
        TemporalScale.DAYS: "days to weeks",
        TemporalScale.MONTHS: "seasons",
        TemporalScale.YEARS: "years",
        TemporalScale.DECADES: "ongoing",
        TemporalScale.CENTURIES: "generational",
    }

    base = type_base.get(entity_type, "unknown")
    scale_note = scale_multiplier.get(temporal_scale, "")

    if scale_note and scale_note not in base:
        return f"{base} (entity operates on {temporal_scale.value} scale)"
    return base
''',
    },
}


# =============================================================================
# COMBINED DEFAULTS - All content merged
# =============================================================================

def get_all_defaults():
    """Get all defaults combined."""
    all_defaults = {}
    all_defaults.update(TOOL_DEFAULTS)
    all_defaults.update(EXTENSION_DEFAULTS)
    all_defaults.update(MORAL_GEOMETRY_DEFAULTS)
    all_defaults.update(KALA_DEFAULTS)
    all_defaults.update(HUME_DEFAULTS)
    all_defaults.update(ENTITY_ONTOLOGY_DEFAULTS)
    return all_defaults

def get_prompt_defaults():
    """Get prompt defaults."""
    return PROMPT_DEFAULTS
