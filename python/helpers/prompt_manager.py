"""
Prompt Management System for Vessels A0 Framework

This module implements a comprehensive prompt management system that provides:

1. Versioned prompt templates
2. Dynamic prompt composition
3. Context-aware prompt generation
4. Ethical principle injection
5. Project-specific prompt customization
6. Prompt history and analytics
"""

import asyncio
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class PromptType(Enum):
    """Types of prompts."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    MEMORY = "memory"
    ETHICAL = "ethical"
    PROJECT = "project"
    CUSTOM = "custom"


class PromptPriority(Enum):
    """Priority levels for prompt composition."""
    HIGHEST = 0  # Core system prompts
    HIGH = 1  # Ethical principles
    NORMAL = 2  # Standard prompts
    LOW = 3  # Optional additions
    LOWEST = 4  # Background context


@dataclass
class PromptTemplate:
    """A versioned prompt template."""
    template_id: str
    name: str
    content: str
    prompt_type: PromptType
    priority: PromptPriority = PromptPriority.NORMAL
    version: str = "1.0.0"
    variables: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    description: str = ""
    author: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Extract variables from content
        if not self.variables:
            self.variables = re.findall(r'\{(\w+)\}', self.content)

    def render(self, variables: Dict[str, Any]) -> str:
        """Render the template with variables."""
        result = self.content
        for var_name, var_value in variables.items():
            result = result.replace(f"{{{var_name}}}", str(var_value))
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "content": self.content,
            "prompt_type": self.prompt_type.value,
            "priority": self.priority.value,
            "version": self.version,
            "variables": self.variables,
            "tags": self.tags,
            "description": self.description,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PromptTemplate':
        return cls(
            template_id=data["template_id"],
            name=data["name"],
            content=data["content"],
            prompt_type=PromptType(data["prompt_type"]),
            priority=PromptPriority(data.get("priority", 2)),
            version=data.get("version", "1.0.0"),
            variables=data.get("variables", []),
            tags=data.get("tags", []),
            description=data.get("description", ""),
            author=data.get("author", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata", {})
        )


@dataclass
class PromptVersion:
    """A specific version of a prompt template."""
    version_id: str
    template_id: str
    version: str
    content: str
    created_at: datetime = field(default_factory=datetime.now)
    change_log: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "template_id": self.template_id,
            "version": self.version,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "change_log": self.change_log
        }


@dataclass
class PromptComposition:
    """A composed prompt from multiple templates."""
    composition_id: str
    templates: List[PromptTemplate]
    final_content: str
    variables_used: Dict[str, Any]
    agent_id: Optional[str] = None
    project_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "templates": [t.template_id for t in self.templates],
            "final_content": self.final_content[:500] + "..." if len(self.final_content) > 500 else self.final_content,
            "variables_used": list(self.variables_used.keys()),
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "created_at": self.created_at.isoformat()
        }


class PromptManager:
    """
    Central prompt management system for the A0 framework.

    This singleton manages all prompt templates, versioning, composition,
    and integration with the ethics and collective memory systems.
    """

    _instance: Optional['PromptManager'] = None
    _lock = asyncio.Lock()

    # Core ethical prompts that are always included
    ETHICAL_PROMPTS = {
        "harm_prevention": """
## Harm Prevention Principle
You must never assist in actions intended to cause harm to individuals or groups.
This includes physical harm, psychological harm, financial harm, or reputational harm.
When in doubt, refuse the action and explain why.
""",
        "transparency": """
## Transparency Principle
You must always be transparent about being an AI system.
Never impersonate humans or deceive about your identity.
Provide honest and accurate information to the best of your ability.
""",
        "privacy": """
## Privacy Principle
Respect user privacy and minimize data collection.
Do not store or share personal information without explicit consent.
When handling sensitive data, apply data minimization principles.
""",
        "human_oversight": """
## Human Oversight Principle
Ensure human oversight for significant decisions.
Actions with major consequences should be confirmed by a human.
Maintain audit trails for all significant operations.
""",
        "accountability": """
## Accountability Principle
All actions must be traceable and attributable.
Provide explanations for decisions when asked.
Support corrective actions and reversibility where possible.
"""
    }

    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._versions: Dict[str, List[PromptVersion]] = {}
        self._profiles: Dict[str, List[str]] = {}  # profile -> template_ids
        self._collective_memory = None
        self._ethics_engine = None
        self._initialized = False
        self._hooks: Dict[str, List[Callable]] = {
            "template_created": [],
            "template_updated": [],
            "prompt_composed": [],
        }

    @classmethod
    async def get_instance(cls) -> 'PromptManager':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the prompt manager."""
        if self._initialized:
            return

        # Initialize framework integrations
        try:
            from python.helpers.collective_memory import CollectiveMemory
            self._collective_memory = await CollectiveMemory.get_instance()
        except Exception as e:
            logger.warning(f"Collective memory not available: {e}")

        try:
            from python.helpers.ethics import EthicsEngine
            self._ethics_engine = await EthicsEngine.get_instance()
        except Exception as e:
            logger.warning(f"Ethics engine not available: {e}")

        # Register core ethical prompts
        for name, content in self.ETHICAL_PROMPTS.items():
            template = PromptTemplate(
                template_id=f"ethical_{name}",
                name=f"Ethical: {name.replace('_', ' ').title()}",
                content=content,
                prompt_type=PromptType.ETHICAL,
                priority=PromptPriority.HIGH,
                tags=["ethical", "core", name]
            )
            self._templates[template.template_id] = template

        # Load prompts from file system
        await self._load_prompts_from_filesystem()

        self._initialized = True
        logger.info(f"PromptManager initialized with {len(self._templates)} templates")

    async def _load_prompts_from_filesystem(self):
        """Load prompts from the prompts/ directory."""
        from python.helpers import files

        prompts_dir = files.get_abs_path("prompts")
        if not os.path.exists(prompts_dir):
            return

        for filename in os.listdir(prompts_dir):
            if not filename.endswith(".md"):
                continue

            try:
                filepath = os.path.join(prompts_dir, filename)
                content = files.read_file(filepath)

                # Parse filename for metadata
                name = filename.replace(".md", "")
                parts = name.split(".")

                # Determine prompt type
                prompt_type = PromptType.SYSTEM
                if "user" in parts:
                    prompt_type = PromptType.USER
                elif "tool" in parts:
                    prompt_type = PromptType.TOOL
                elif "memory" in parts:
                    prompt_type = PromptType.MEMORY

                template_id = f"fs_{name}"
                template = PromptTemplate(
                    template_id=template_id,
                    name=name,
                    content=content,
                    prompt_type=prompt_type,
                    tags=parts,
                    metadata={"source": filepath}
                )

                self._templates[template_id] = template

            except Exception as e:
                logger.error(f"Failed to load prompt {filename}: {e}")

        # Load agent-specific prompts
        agents_dir = files.get_abs_path("agents")
        if os.path.exists(agents_dir):
            for agent_name in os.listdir(agents_dir):
                agent_prompts_dir = os.path.join(agents_dir, agent_name, "prompts")
                if not os.path.isdir(agent_prompts_dir):
                    continue

                profile_templates = []
                for filename in os.listdir(agent_prompts_dir):
                    if not filename.endswith(".md"):
                        continue

                    try:
                        filepath = os.path.join(agent_prompts_dir, filename)
                        content = files.read_file(filepath)
                        name = filename.replace(".md", "")

                        template_id = f"agent_{agent_name}_{name}"
                        template = PromptTemplate(
                            template_id=template_id,
                            name=f"{agent_name}: {name}",
                            content=content,
                            prompt_type=PromptType.SYSTEM,
                            tags=[agent_name, name],
                            metadata={"source": filepath, "profile": agent_name}
                        )

                        self._templates[template_id] = template
                        profile_templates.append(template_id)

                    except Exception as e:
                        logger.error(f"Failed to load agent prompt {filename}: {e}")

                self._profiles[agent_name] = profile_templates

    def add_hook(self, hook_name: str, callback: Callable):
        """Add a hook callback."""
        if hook_name in self._hooks:
            self._hooks[hook_name].append(callback)

    async def _run_hooks(self, hook_name: str, data: Any):
        """Run registered hooks."""
        for hook in self._hooks.get(hook_name, []):
            try:
                result = hook(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Hook {hook_name} failed: {e}")

    def _generate_id(self, prefix: str, name: str) -> str:
        """Generate a unique ID."""
        unique = f"{prefix}:{name}:{datetime.now().isoformat()}"
        return f"{prefix}_{hashlib.sha256(unique.encode()).hexdigest()[:12]}"

    async def create_template(
        self,
        name: str,
        content: str,
        prompt_type: PromptType = PromptType.CUSTOM,
        priority: PromptPriority = PromptPriority.NORMAL,
        tags: Optional[List[str]] = None,
        description: str = ""
    ) -> PromptTemplate:
        """Create a new prompt template."""
        template_id = self._generate_id("tpl", name)

        template = PromptTemplate(
            template_id=template_id,
            name=name,
            content=content,
            prompt_type=prompt_type,
            priority=priority,
            tags=tags or [],
            description=description
        )

        self._templates[template_id] = template
        self._versions[template_id] = [PromptVersion(
            version_id=self._generate_id("ver", name),
            template_id=template_id,
            version="1.0.0",
            content=content,
            change_log="Initial version"
        )]

        await self._run_hooks("template_created", template)

        # Record to memory
        if self._collective_memory:
            from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
            await self._collective_memory.store(
                memory_type=MemoryType.EVENT,
                content={"event": "template_created", "template_id": template_id, "name": name},
                scope=MemoryScope.GLOBAL,
                priority=MemoryPriority.LOW,
                tags=["prompt", "template", "created"]
            )

        return template

    async def update_template(
        self,
        template_id: str,
        content: str,
        change_log: str = ""
    ) -> Optional[PromptTemplate]:
        """Update a prompt template (creates new version)."""
        template = self._templates.get(template_id)
        if not template:
            return None

        # Increment version
        parts = template.version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)

        # Create version record
        version = PromptVersion(
            version_id=self._generate_id("ver", template.name),
            template_id=template_id,
            version=new_version,
            content=content,
            change_log=change_log
        )

        if template_id not in self._versions:
            self._versions[template_id] = []
        self._versions[template_id].append(version)

        # Update template
        template.content = content
        template.version = new_version
        template.updated_at = datetime.now()

        # Re-extract variables
        template.variables = re.findall(r'\{(\w+)\}', content)

        await self._run_hooks("template_updated", template)

        return template

    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        """Get a prompt template by ID."""
        return self._templates.get(template_id)

    def get_templates_by_type(self, prompt_type: PromptType) -> List[PromptTemplate]:
        """Get all templates of a specific type."""
        return [t for t in self._templates.values() if t.prompt_type == prompt_type and t.is_active]

    def get_templates_by_tags(self, tags: List[str]) -> List[PromptTemplate]:
        """Get templates that have any of the specified tags."""
        return [t for t in self._templates.values() if any(tag in t.tags for tag in tags) and t.is_active]

    def get_profile_templates(self, profile: str) -> List[PromptTemplate]:
        """Get all templates for a specific profile."""
        template_ids = self._profiles.get(profile, [])
        return [self._templates[tid] for tid in template_ids if tid in self._templates]

    def get_version_history(self, template_id: str) -> List[PromptVersion]:
        """Get version history for a template."""
        return self._versions.get(template_id, [])

    async def compose_prompt(
        self,
        template_ids: Optional[List[str]] = None,
        prompt_types: Optional[List[PromptType]] = None,
        tags: Optional[List[str]] = None,
        profile: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        include_ethics: bool = True,
        agent_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> PromptComposition:
        """
        Compose a prompt from multiple templates.

        Args:
            template_ids: Specific template IDs to include
            prompt_types: Types of prompts to include
            tags: Tags to filter templates
            profile: Agent profile to load templates from
            variables: Variables to substitute in templates
            include_ethics: Whether to include ethical prompts
            agent_id: Agent ID for tracking
            project_id: Project ID for context

        Returns:
            PromptComposition with the final prompt
        """
        variables = variables or {}
        selected_templates: List[PromptTemplate] = []

        # Include ethical prompts first (highest priority)
        if include_ethics:
            for template in self._templates.values():
                if template.prompt_type == PromptType.ETHICAL and template.is_active:
                    selected_templates.append(template)

        # Include specific templates
        if template_ids:
            for tid in template_ids:
                if tid in self._templates and self._templates[tid].is_active:
                    selected_templates.append(self._templates[tid])

        # Include by type
        if prompt_types:
            for ptype in prompt_types:
                selected_templates.extend(self.get_templates_by_type(ptype))

        # Include by tags
        if tags:
            selected_templates.extend(self.get_templates_by_tags(tags))

        # Include profile templates
        if profile:
            selected_templates.extend(self.get_profile_templates(profile))

        # Remove duplicates and sort by priority
        seen = set()
        unique_templates = []
        for t in selected_templates:
            if t.template_id not in seen:
                seen.add(t.template_id)
                unique_templates.append(t)

        unique_templates.sort(key=lambda t: t.priority.value)

        # Render and compose
        rendered_parts = []
        for template in unique_templates:
            try:
                rendered = template.render(variables)
                rendered_parts.append(rendered)
            except Exception as e:
                logger.error(f"Failed to render template {template.template_id}: {e}")

        final_content = "\n\n".join(rendered_parts)

        composition = PromptComposition(
            composition_id=self._generate_id("comp", str(len(unique_templates))),
            templates=unique_templates,
            final_content=final_content,
            variables_used=variables,
            agent_id=agent_id,
            project_id=project_id
        )

        await self._run_hooks("prompt_composed", composition)

        # Record to memory
        if self._collective_memory:
            from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
            await self._collective_memory.store(
                memory_type=MemoryType.EVENT,
                content=composition.to_dict(),
                scope=MemoryScope.AGENT,
                priority=MemoryPriority.LOW,
                tags=["prompt", "composition"],
                agent_id=agent_id,
                project_id=project_id
            )

        return composition

    async def get_ethical_prompt(self) -> str:
        """Get the combined ethical principles prompt."""
        ethical_templates = self.get_templates_by_type(PromptType.ETHICAL)
        return "\n\n".join(t.content for t in ethical_templates)

    def list_all_templates(self) -> List[PromptTemplate]:
        """List all templates."""
        return list(self._templates.values())

    async def get_statistics(self) -> Dict[str, Any]:
        """Get prompt manager statistics."""
        return {
            "total_templates": len(self._templates),
            "by_type": {
                ptype.value: len(self.get_templates_by_type(ptype))
                for ptype in PromptType
            },
            "profiles": list(self._profiles.keys()),
            "total_versions": sum(len(v) for v in self._versions.values())
        }


# Convenience functions
async def get_prompt_manager() -> PromptManager:
    """Get the prompt manager instance."""
    return await PromptManager.get_instance()


async def compose_prompt(
    profile: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
    include_ethics: bool = True,
    **kwargs
) -> str:
    """Compose a prompt and return the final content."""
    manager = await get_prompt_manager()
    composition = await manager.compose_prompt(
        profile=profile,
        variables=variables,
        include_ethics=include_ethics,
        **kwargs
    )
    return composition.final_content


async def get_ethical_prompt() -> str:
    """Get the ethical principles prompt."""
    manager = await get_prompt_manager()
    return await manager.get_ethical_prompt()
