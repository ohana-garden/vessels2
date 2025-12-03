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
# COMBINED DEFAULTS - All content merged
# =============================================================================

def get_all_defaults():
    """Get all defaults combined."""
    all_defaults = {}
    all_defaults.update(TOOL_DEFAULTS)
    all_defaults.update(EXTENSION_DEFAULTS)
    all_defaults.update(MORAL_GEOMETRY_DEFAULTS)
    all_defaults.update(KALA_DEFAULTS)
    return all_defaults

def get_prompt_defaults():
    """Get prompt defaults."""
    return PROMPT_DEFAULTS
