"""
Projects System for Vessels A0 Framework

This module implements a comprehensive project management system that serves
as the organizational backbone for all agent activities. Every agent, tool,
instrument, and memory operation is associated with a project.

Projects provide:
1. Organizational structure for tasks and goals
2. Shared context and memory scope
3. Agent team management
4. Resource allocation and tracking
5. Ethical oversight and compliance

This module maintains backwards compatibility with the legacy file-based project
system while adding graph-based storage and A0 framework integration.
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple, TypedDict, TYPE_CHECKING

from python.helpers import files, dirty_json, persist_chat, file_tree
from python.helpers.print_style import PrintStyle

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agent import AgentContext

# Legacy constants (backwards compatibility)
PROJECTS_PARENT_DIR = "usr/projects"
PROJECT_META_DIR = ".a0proj"
PROJECT_INSTRUCTIONS_DIR = "instructions"
PROJECT_KNOWLEDGE_DIR = "knowledge"
PROJECT_HEADER_FILE = "project.json"

CONTEXT_DATA_KEY_PROJECT = "project"


# ============================================================================
# A0 Framework Project System
# ============================================================================

class ProjectStatus(Enum):
    """Status of a project."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Status of a task within a project."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Priority levels for tasks."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5


class AgentRole(Enum):
    """Roles that agents can have in a project."""
    OWNER = "owner"
    LEAD = "lead"
    MEMBER = "member"
    REVIEWER = "reviewer"
    OBSERVER = "observer"


@dataclass
class ProjectGoal:
    """A goal within a project."""
    goal_id: str
    description: str
    success_criteria: List[str]
    priority: TaskPriority = TaskPriority.NORMAL
    deadline: Optional[datetime] = None
    status: str = "pending"
    progress: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "success_criteria": self.success_criteria,
            "priority": self.priority.value,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectGoal':
        return cls(
            goal_id=data["goal_id"],
            description=data["description"],
            success_criteria=data.get("success_criteria", []),
            priority=TaskPriority(data.get("priority", 2)),
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            status=data.get("status", "pending"),
            progress=data.get("progress", 0.0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            metadata=data.get("metadata", {})
        )


@dataclass
class ProjectTask:
    """A task within a project."""
    task_id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    assigned_agent: Optional[str] = None
    parent_task_id: Optional[str] = None
    goal_id: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    estimated_effort: Optional[float] = None
    actual_effort: Optional[float] = None
    deadline: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "assigned_agent": self.assigned_agent,
            "parent_task_id": self.parent_task_id,
            "goal_id": self.goal_id,
            "dependencies": self.dependencies,
            "subtasks": self.subtasks,
            "estimated_effort": self.estimated_effort,
            "actual_effort": self.actual_effort,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectTask':
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            description=data["description"],
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", 2)),
            assigned_agent=data.get("assigned_agent"),
            parent_task_id=data.get("parent_task_id"),
            goal_id=data.get("goal_id"),
            dependencies=data.get("dependencies", []),
            subtasks=data.get("subtasks", []),
            estimated_effort=data.get("estimated_effort"),
            actual_effort=data.get("actual_effort"),
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", [])
        )


@dataclass
class ProjectMember:
    """An agent member of a project."""
    agent_id: str
    role: AgentRole
    joined_at: datetime = field(default_factory=datetime.now)
    permissions: List[str] = field(default_factory=list)
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "joined_at": self.joined_at.isoformat(),
            "permissions": self.permissions,
            "active": self.active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectMember':
        return cls(
            agent_id=data["agent_id"],
            role=AgentRole(data["role"]),
            joined_at=datetime.fromisoformat(data["joined_at"]) if data.get("joined_at") else datetime.now(),
            permissions=data.get("permissions", []),
            active=data.get("active", True)
        )


@dataclass
class ProjectResource:
    """A resource associated with a project."""
    resource_id: str
    resource_type: str  # instrument, tool, mcp_server, knowledge_base, etc.
    name: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "name": self.name,
            "config": self.config,
            "enabled": self.enabled
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectResource':
        return cls(
            resource_id=data["resource_id"],
            resource_type=data["resource_type"],
            name=data["name"],
            config=data.get("config", {}),
            enabled=data.get("enabled", True)
        )


@dataclass
class A0Project:
    """
    A0 Framework Project that organizes agent activities.

    This is the new graph-based project system that provides comprehensive
    project management capabilities while maintaining backwards compatibility
    with the legacy file-based system.
    """

    # Identity
    project_id: str
    name: str
    description: str

    # Status
    status: ProjectStatus = ProjectStatus.DRAFT

    # Ownership
    owner_id: str = ""
    created_by: str = ""

    # Structure
    goals: List[ProjectGoal] = field(default_factory=list)
    tasks: List[ProjectTask] = field(default_factory=list)
    members: List[ProjectMember] = field(default_factory=list)
    resources: List[ProjectResource] = field(default_factory=list)

    # Configuration
    settings: Dict[str, Any] = field(default_factory=dict)
    ethical_constraints: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # Legacy compatibility
    legacy_name: Optional[str] = None  # Maps to legacy file-based project

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "owner_id": self.owner_id,
            "created_by": self.created_by,
            "goals": [g.to_dict() for g in self.goals],
            "tasks": [t.to_dict() for t in self.tasks],
            "members": [m.to_dict() for m in self.members],
            "resources": [r.to_dict() for r in self.resources],
            "settings": self.settings,
            "ethical_constraints": self.ethical_constraints,
            "tags": self.tags,
            "legacy_name": self.legacy_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'A0Project':
        return cls(
            project_id=data["project_id"],
            name=data["name"],
            description=data["description"],
            status=ProjectStatus(data.get("status", "draft")),
            owner_id=data.get("owner_id", ""),
            created_by=data.get("created_by", ""),
            goals=[ProjectGoal.from_dict(g) for g in data.get("goals", [])],
            tasks=[ProjectTask.from_dict(t) for t in data.get("tasks", [])],
            members=[ProjectMember.from_dict(m) for m in data.get("members", [])],
            resources=[ProjectResource.from_dict(r) for r in data.get("resources", [])],
            settings=data.get("settings", {}),
            ethical_constraints=data.get("ethical_constraints", []),
            tags=data.get("tags", []),
            legacy_name=data.get("legacy_name"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            metadata=data.get("metadata", {})
        )

    @property
    def progress(self) -> float:
        """Calculate overall project progress."""
        if not self.tasks:
            return 0.0
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
        return completed / len(self.tasks)

    def get_task(self, task_id: str) -> Optional[ProjectTask]:
        """Get a task by ID."""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None

    def get_goal(self, goal_id: str) -> Optional[ProjectGoal]:
        """Get a goal by ID."""
        for goal in self.goals:
            if goal.goal_id == goal_id:
                return goal
        return None

    def get_member(self, agent_id: str) -> Optional[ProjectMember]:
        """Get a member by agent ID."""
        for member in self.members:
            if member.agent_id == agent_id:
                return member
        return None

    def get_resource(self, resource_id: str) -> Optional[ProjectResource]:
        """Get a resource by ID."""
        for resource in self.resources:
            if resource.resource_id == resource_id:
                return resource
        return None


class ProjectManager:
    """
    Central project management system that coordinates all project activities.

    This is a singleton that manages project lifecycle, task assignment,
    and resource allocation across the agent ecosystem. It integrates with
    the ethics engine and collective memory for full A0 framework compliance.
    """

    _instance: Optional['ProjectManager'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._projects: Dict[str, A0Project] = {}
        self._graph_store = None
        self._collective_memory = None
        self._ethics_engine = None
        self._initialized = False
        self._hooks: Dict[str, List[Callable]] = {
            "project_created": [],
            "project_updated": [],
            "project_deleted": [],
            "task_created": [],
            "task_updated": [],
            "task_assigned": [],
            "task_completed": [],
            "member_added": [],
            "member_removed": [],
        }

    @classmethod
    async def get_instance(cls) -> 'ProjectManager':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the project manager."""
        if self._initialized:
            return

        # Initialize graph store
        try:
            from python.helpers.graph_store import GraphStore
            self._graph_store = await GraphStore.get_instance()
        except Exception as e:
            logger.warning(f"Graph store not available: {e}")

        # Initialize collective memory
        try:
            from python.helpers.collective_memory import CollectiveMemory
            self._collective_memory = await CollectiveMemory.get_instance()
        except Exception as e:
            logger.warning(f"Collective memory not available: {e}")

        # Initialize ethics engine
        try:
            from python.helpers.ethics import EthicsEngine
            self._ethics_engine = await EthicsEngine.get_instance()
        except Exception as e:
            logger.warning(f"Ethics engine not available: {e}")

        # Load existing projects from graph
        await self._load_projects()

        # Import legacy projects
        await self._import_legacy_projects()

        self._initialized = True
        logger.info("ProjectManager initialized")

    async def _load_projects(self):
        """Load existing projects from graph storage."""
        if not self._graph_store:
            return

        try:
            results = await self._graph_store.execute_query(
                "MATCH (p:A0_PROJECT) RETURN p",
                {}
            )
            for result in results:
                project = A0Project.from_dict(result["p"])
                self._projects[project.project_id] = project
            logger.info(f"Loaded {len(self._projects)} projects from graph")
        except Exception as e:
            logger.warning(f"Failed to load projects: {e}")

    async def _import_legacy_projects(self):
        """Import legacy file-based projects into the A0 system."""
        try:
            legacy_projects = get_active_projects_list()
            for legacy in legacy_projects:
                name = legacy["name"]
                # Check if already imported
                existing = [p for p in self._projects.values() if p.legacy_name == name]
                if existing:
                    continue

                # Import legacy project
                project_id = self._generate_id("proj", name)
                project = A0Project(
                    project_id=project_id,
                    name=legacy.get("title", name),
                    description=legacy.get("description", ""),
                    status=ProjectStatus.ACTIVE,
                    legacy_name=name,
                    tags=["legacy", "imported"]
                )
                self._projects[project_id] = project
                await self._save_project(project)
                logger.info(f"Imported legacy project: {name}")
        except Exception as e:
            logger.warning(f"Failed to import legacy projects: {e}")

    async def _save_project(self, project: A0Project):
        """Save a project to graph storage."""
        if not self._graph_store:
            return

        try:
            await self._graph_store.create_or_update_node(
                node_type="A0_PROJECT",
                node_id=project.project_id,
                properties=project.to_dict()
            )
        except Exception as e:
            logger.error(f"Failed to save project: {e}")

    async def _record_to_memory(self, event_type: str, data: Dict[str, Any]):
        """Record an event to collective memory."""
        if not self._collective_memory:
            return

        try:
            from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
            await self._collective_memory.store(
                memory_type=MemoryType.EVENT,
                content={"event_type": event_type, **data},
                scope=MemoryScope.PROJECT,
                priority=MemoryPriority.NORMAL,
                tags=["project", event_type],
                project_id=data.get("project_id")
            )
        except Exception as e:
            logger.error(f"Failed to record to memory: {e}")

    async def _run_hooks(self, hook_name: str, data: Any):
        """Run registered hooks."""
        for hook in self._hooks.get(hook_name, []):
            try:
                result = hook(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Hook {hook_name} failed: {e}")

    def add_hook(self, hook_name: str, callback: Callable):
        """Add a hook callback."""
        if hook_name in self._hooks:
            self._hooks[hook_name].append(callback)

    def _generate_id(self, prefix: str, name: str) -> str:
        """Generate a unique ID."""
        unique = f"{prefix}:{name}:{datetime.now().isoformat()}"
        return f"{prefix}_{hashlib.sha256(unique.encode()).hexdigest()[:12]}"

    # Project CRUD

    async def create_a0_project(
        self,
        name: str,
        description: str,
        owner_id: str,
        goals: Optional[List[Dict[str, Any]]] = None,
        settings: Optional[Dict[str, Any]] = None,
        ethical_constraints: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        create_legacy: bool = True
    ) -> A0Project:
        """Create a new A0 project."""
        project_id = self._generate_id("proj", name)

        # Validate with ethics engine
        if self._ethics_engine:
            validation = await self._ethics_engine.validate(
                action_type="project_create",
                data={"name": name, "description": description},
                context={"agent_id": owner_id}
            )
            if validation.is_blocked:
                raise ValueError(f"Project creation blocked: {validation.explanation}")

        # Create legacy project for backwards compatibility
        legacy_name = None
        if create_legacy:
            try:
                legacy_name = files.sanitize_filename(name)
                create_project(legacy_name, BasicProjectData(
                    title=name,
                    description=description,
                    instructions="",
                    color="",
                    memory="own",
                    file_structure=_default_file_structure_settings()
                ))
            except Exception as e:
                logger.warning(f"Failed to create legacy project: {e}")
                legacy_name = None

        project = A0Project(
            project_id=project_id,
            name=name,
            description=description,
            owner_id=owner_id,
            created_by=owner_id,
            settings=settings or {},
            ethical_constraints=ethical_constraints or [],
            tags=tags or [],
            legacy_name=legacy_name
        )

        # Add owner as member
        project.members.append(ProjectMember(
            agent_id=owner_id,
            role=AgentRole.OWNER,
            permissions=["*"]
        ))

        # Add goals if provided
        if goals:
            for goal_data in goals:
                goal = ProjectGoal(
                    goal_id=self._generate_id("goal", goal_data.get("description", "")),
                    description=goal_data["description"],
                    success_criteria=goal_data.get("success_criteria", []),
                    priority=TaskPriority(goal_data.get("priority", 2))
                )
                project.goals.append(goal)

        # Store project
        self._projects[project_id] = project
        await self._save_project(project)

        # Record and notify
        await self._record_to_memory("project_created", {
            "project_id": project_id,
            "name": name,
            "owner_id": owner_id
        })
        await self._run_hooks("project_created", project)

        logger.info(f"Created A0 project: {project_id}")
        return project

    async def get_a0_project(self, project_id: str) -> Optional[A0Project]:
        """Get an A0 project by ID."""
        return self._projects.get(project_id)

    async def get_project_by_legacy_name(self, legacy_name: str) -> Optional[A0Project]:
        """Get an A0 project by its legacy name."""
        for project in self._projects.values():
            if project.legacy_name == legacy_name:
                return project
        return None

    async def list_a0_projects(
        self,
        status: Optional[ProjectStatus] = None,
        owner_id: Optional[str] = None,
        member_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[A0Project]:
        """List A0 projects with optional filters."""
        projects = list(self._projects.values())

        if status:
            projects = [p for p in projects if p.status == status]
        if owner_id:
            projects = [p for p in projects if p.owner_id == owner_id]
        if member_id:
            projects = [p for p in projects if any(m.agent_id == member_id for m in p.members)]
        if tags:
            projects = [p for p in projects if any(t in p.tags for t in tags)]

        return projects

    async def create_task(
        self,
        project_id: str,
        title: str,
        description: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        goal_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[ProjectTask]:
        """Create a new task in a project."""
        project = self._projects.get(project_id)
        if not project:
            return None

        task_id = self._generate_id("task", title)
        task = ProjectTask(
            task_id=task_id,
            title=title,
            description=description,
            priority=priority,
            goal_id=goal_id,
            tags=tags or []
        )

        project.tasks.append(task)
        project.updated_at = datetime.now()
        await self._save_project(project)

        await self._record_to_memory("task_created", {
            "project_id": project_id,
            "task_id": task_id,
            "title": title
        })
        await self._run_hooks("task_created", task)

        return task

    async def assign_task(
        self,
        project_id: str,
        task_id: str,
        agent_id: str
    ) -> Optional[ProjectTask]:
        """Assign a task to an agent."""
        project = self._projects.get(project_id)
        if not project:
            return None

        task = project.get_task(task_id)
        if not task:
            return None

        task.assigned_agent = agent_id
        task.updated_at = datetime.now()
        await self._save_project(project)

        await self._record_to_memory("task_assigned", {
            "project_id": project_id,
            "task_id": task_id,
            "agent_id": agent_id
        })
        await self._run_hooks("task_assigned", {"task": task, "agent_id": agent_id})

        return task

    async def complete_task(self, project_id: str, task_id: str) -> Optional[ProjectTask]:
        """Mark a task as completed."""
        project = self._projects.get(project_id)
        if not project:
            return None

        task = project.get_task(task_id)
        if not task:
            return None

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        task.updated_at = datetime.now()
        await self._save_project(project)

        await self._record_to_memory("task_completed", {
            "project_id": project_id,
            "task_id": task_id
        })
        await self._run_hooks("task_completed", task)

        return task


# Convenience functions for A0 ProjectManager
async def get_project_manager() -> ProjectManager:
    """Get the project manager instance."""
    return await ProjectManager.get_instance()


async def create_a0_project(name: str, description: str, owner_id: str, **kwargs) -> A0Project:
    """Create a new A0 project."""
    manager = await get_project_manager()
    return await manager.create_a0_project(name, description, owner_id, **kwargs)


async def get_a0_project(project_id: str) -> Optional[A0Project]:
    """Get an A0 project by ID."""
    manager = await get_project_manager()
    return await manager.get_a0_project(project_id)


# ============================================================================
# Legacy Project System (Backwards Compatibility)
# ============================================================================


class FileStructureInjectionSettings(TypedDict):
    enabled: bool
    max_depth: int
    max_files: int
    max_folders: int
    max_lines: int
    gitignore: str


class BasicProjectData(TypedDict):
    title: str
    description: str
    instructions: str
    color: str
    memory: Literal[
        "own", "global"
    ]  # in the future we can add cutom and point to another existing folder
    file_structure: FileStructureInjectionSettings


class EditProjectData(BasicProjectData):
    name: str
    instruction_files_count: int
    knowledge_files_count: int
    variables: str
    secrets: str


def get_projects_parent_folder():
    return files.get_abs_path(PROJECTS_PARENT_DIR)


def get_project_folder(name: str):
    return files.get_abs_path(get_projects_parent_folder(), name)


def get_project_meta_folder(name: str, *sub_dirs: str):
    return files.get_abs_path(get_project_folder(name), PROJECT_META_DIR, *sub_dirs)


def delete_project(name: str):
    abs_path = files.get_abs_path(PROJECTS_PARENT_DIR, name)
    files.delete_dir(abs_path)
    deactivate_project_in_chats(name)
    return name


def create_project(name: str, data: BasicProjectData):
    abs_path = files.create_dir_safe(
        files.get_abs_path(PROJECTS_PARENT_DIR, name), rename_format="{name}_{number}"
    )
    create_project_meta_folders(name)
    data = _normalizeBasicData(data)
    save_project_header(name, data)
    return name


def load_project_header(name: str):
    abs_path = files.get_abs_path(
        PROJECTS_PARENT_DIR, name, PROJECT_META_DIR, PROJECT_HEADER_FILE
    )
    header: dict = dirty_json.parse(files.read_file(abs_path))  # type: ignore
    header["name"] = name
    return header


def _default_file_structure_settings():
    try:
        gitignore = files.read_file("conf/projects.default.gitignore")
    except Exception:
        gitignore = ""
    return FileStructureInjectionSettings(
        enabled=True,
        max_depth=5,
        max_files=20,
        max_folders=20,
        max_lines=250,
        gitignore=gitignore,
    )


def _normalizeBasicData(data: BasicProjectData):
    return BasicProjectData(
        title=data.get("title", ""),
        description=data.get("description", ""),
        instructions=data.get("instructions", ""),
        color=data.get("color", ""),
        memory=data.get("memory", "own"),
        file_structure=data.get(
            "file_structure",
            _default_file_structure_settings(),
        ),
    )


def _normalizeEditData(data: EditProjectData):
    return EditProjectData(
        name=data.get("name", ""),
        title=data.get("title", ""),
        description=data.get("description", ""),
        instructions=data.get("instructions", ""),
        variables=data.get("variables", ""),
        color=data.get("color", ""),
        instruction_files_count=data.get("instruction_files_count", 0),
        knowledge_files_count=data.get("knowledge_files_count", 0),
        secrets=data.get("secrets", ""),
        memory=data.get("memory", "own"),
        file_structure=data.get(
            "file_structure",
            _default_file_structure_settings(),
        ),
    )


def _edit_data_to_basic_data(data: EditProjectData):
    return _normalizeBasicData(data)


def _basic_data_to_edit_data(data: BasicProjectData):
    return _normalizeEditData(data)  # type: ignore


def update_project(name: str, data: EditProjectData):
    # merge with current state
    current = load_edit_project_data(name)
    current.update(data)
    current = _normalizeEditData(current)

    # save header data
    header = _edit_data_to_basic_data(current)
    save_project_header(name, header)

    # save secrets
    save_project_variables(name, current["variables"])
    save_project_secrets(name, current["secrets"])

    reactivate_project_in_chats(name)
    return name


def load_basic_project_data(name: str) -> BasicProjectData:
    data = BasicProjectData(**load_project_header(name))
    normalized = _normalizeBasicData(data)
    return normalized


def load_edit_project_data(name: str) -> EditProjectData:
    data = load_basic_project_data(name)
    additional_instructions = get_additional_instructions_files(
        name
    )  # for additional info
    variables = load_project_variables(name)
    secrets = load_project_secrets_masked(name)
    knowledge_files_count = get_knowledge_files_count(name)
    data = EditProjectData(
        **data,
        name=name,
        instruction_files_count=len(additional_instructions),
        knowledge_files_count=knowledge_files_count,
        variables=variables,
        secrets=secrets,
    )
    data = _normalizeEditData(data)
    return data


def save_project_header(name: str, data: BasicProjectData):
    # save project header file
    header = dirty_json.stringify(data)
    abs_path = files.get_abs_path(
        PROJECTS_PARENT_DIR, name, PROJECT_META_DIR, PROJECT_HEADER_FILE
    )

    files.write_file(abs_path, header)


def get_active_projects_list():
    return _get_projects_list(get_projects_parent_folder())


def _get_projects_list(parent_dir):
    projects = []

    # folders in project directory
    for name in os.listdir(parent_dir):
        try:
            abs_path = os.path.join(parent_dir, name)
            if os.path.isdir(abs_path):
                project_data = load_basic_project_data(name)
                projects.append(
                    {
                        "name": name,
                        "title": project_data.get("title", ""),
                        "description": project_data.get("description", ""),
                        "color": project_data.get("color", ""),
                    }
                )
        except Exception as e:
            PrintStyle.error(f"Error loading project {name}: {str(e)}")

    # sort projects by name
    projects.sort(key=lambda x: x["name"])
    return projects


def activate_project(context_id: str, name: str):
    from agent import AgentContext

    data = load_edit_project_data(name)
    context = AgentContext.get(context_id)
    if context is None:
        raise Exception("Context not found")
    display_name = str(data.get("title", name))
    display_name = display_name[:22] + "..." if len(display_name) > 25 else display_name
    context.set_data(CONTEXT_DATA_KEY_PROJECT, name)
    context.set_output_data(
        CONTEXT_DATA_KEY_PROJECT,
        {"name": name, "title": display_name, "color": data.get("color", "")},
    )

    # persist
    persist_chat.save_tmp_chat(context)


def deactivate_project(context_id: str):
    from agent import AgentContext

    context = AgentContext.get(context_id)
    if context is None:
        raise Exception("Context not found")
    context.set_data(CONTEXT_DATA_KEY_PROJECT, None)
    context.set_output_data(CONTEXT_DATA_KEY_PROJECT, None)

    # persist
    persist_chat.save_tmp_chat(context)


def reactivate_project_in_chats(name: str):
    from agent import AgentContext

    for context in AgentContext.all():
        if context.get_data(CONTEXT_DATA_KEY_PROJECT) == name:
            activate_project(context.id, name)
        persist_chat.save_tmp_chat(context)


def deactivate_project_in_chats(name: str):
    from agent import AgentContext

    for context in AgentContext.all():
        if context.get_data(CONTEXT_DATA_KEY_PROJECT) == name:
            deactivate_project(context.id)
        persist_chat.save_tmp_chat(context)


def build_system_prompt_vars(name: str):
    project_data = load_basic_project_data(name)
    main_instructions = project_data.get("instructions", "") or ""
    additional_instructions = get_additional_instructions_files(name)
    complete_instructions = (
        main_instructions
        + "\n\n".join(
            additional_instructions[k] for k in sorted(additional_instructions)
        )
    ).strip()
    return {
        "project_name": project_data.get("title", ""),
        "project_description": project_data.get("description", ""),
        "project_instructions": complete_instructions or "",
        "project_path": files.normalize_a0_path(get_project_folder(name)),
    }


def get_additional_instructions_files(name: str):
    instructions_folder = files.get_abs_path(
        get_project_folder(name), PROJECT_META_DIR, PROJECT_INSTRUCTIONS_DIR
    )
    return files.read_text_files_in_dir(instructions_folder)


def get_context_project_name(context: "AgentContext") -> str | None:
    return context.get_data(CONTEXT_DATA_KEY_PROJECT)


def load_project_variables(name: str):
    try:
        abs_path = files.get_abs_path(get_project_meta_folder(name), "variables.env")
        return files.read_file(abs_path)
    except Exception:
        return ""


def save_project_variables(name: str, variables: str):
    abs_path = files.get_abs_path(get_project_meta_folder(name), "variables.env")
    files.write_file(abs_path, variables)


def load_project_secrets_masked(name: str, merge_with_global=False):
    from python.helpers import secrets

    mgr = secrets.get_project_secrets_manager(name, merge_with_global)
    return mgr.get_masked_secrets()


def save_project_secrets(name: str, secrets: str):
    from python.helpers.secrets import get_project_secrets_manager

    secrets_manager = get_project_secrets_manager(name)
    secrets_manager.save_secrets_with_merge(secrets)


def get_context_memory_subdir(context: "AgentContext") -> str | None:
    # if a project is active and has memory isolation set, return the project memory subdir
    project_name = get_context_project_name(context)
    if project_name:
        project_data = load_basic_project_data(project_name)
        if project_data["memory"] == "own":
            return "projects/" + project_name
    return None  # no memory override


def create_project_meta_folders(name: str):
    # create instructions folder
    files.create_dir(get_project_meta_folder(name, PROJECT_INSTRUCTIONS_DIR))

    # create knowledge folders
    files.create_dir(get_project_meta_folder(name, PROJECT_KNOWLEDGE_DIR))
    from python.helpers import memory

    for memory_type in memory.Memory.Area:
        files.create_dir(
            get_project_meta_folder(name, PROJECT_KNOWLEDGE_DIR, memory_type.value)
        )


def get_knowledge_files_count(name: str):
    knowledge_folder = files.get_abs_path(
        get_project_meta_folder(name, PROJECT_KNOWLEDGE_DIR)
    )
    return len(files.list_files_in_dir_recursively(knowledge_folder))

def get_file_structure(name: str, basic_data: BasicProjectData|None=None) -> str:
    project_folder = get_project_folder(name)
    if basic_data is None:
        basic_data = load_basic_project_data(name)
    
    tree = str(file_tree.file_tree(
        project_folder,
        max_depth=basic_data["file_structure"]["max_depth"],
        max_files=basic_data["file_structure"]["max_files"],
        max_folders=basic_data["file_structure"]["max_folders"],
        max_lines=basic_data["file_structure"]["max_lines"],
        ignore=basic_data["file_structure"]["gitignore"],
        output_mode=file_tree.OUTPUT_MODE_STRING
    ))

    # empty?
    if "\n" not in tree:
        tree += "\n # Empty"

    return tree

    