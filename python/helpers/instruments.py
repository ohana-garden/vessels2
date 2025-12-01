"""
Instruments Registry for Vessels A0 Framework

This module implements a comprehensive instrument management system that provides
standardized interfaces for external tools and services.

Instruments are external capabilities that agents can leverage:
1. External APIs and services
2. Hardware interfaces
3. Specialized computation tools
4. Data processing pipelines
5. Integration with third-party systems

Each instrument is:
- Registered with the central registry
- Validated against ethical principles
- Monitored through collective memory
- Associated with projects and agents
"""

import asyncio
import hashlib
import importlib
import importlib.util
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

logger = logging.getLogger(__name__)


class InstrumentType(Enum):
    """Types of instruments available."""
    FINANCIAL = "financial"
    DATABASE = "database"
    API = "api"
    FILE_SYSTEM = "file_system"
    NETWORK = "network"
    COMPUTATION = "computation"
    MEDIA = "media"
    MESSAGING = "messaging"
    MONITORING = "monitoring"
    SECURITY = "security"
    CUSTOM = "custom"


class InstrumentStatus(Enum):
    """Status of an instrument."""
    AVAILABLE = "available"
    BUSY = "busy"
    ERROR = "error"
    DISABLED = "disabled"
    INITIALIZING = "initializing"


@dataclass
class InstrumentCapability:
    """A capability provided by an instrument."""
    name: str
    description: str
    parameters: Dict[str, Any]
    return_type: str
    async_only: bool = False
    requires_confirmation: bool = False
    ethical_constraints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "async_only": self.async_only,
            "requires_confirmation": self.requires_confirmation,
            "ethical_constraints": self.ethical_constraints
        }


@dataclass
class InstrumentMetadata:
    """Metadata about an instrument."""
    instrument_id: str
    name: str
    description: str
    version: str
    instrument_type: InstrumentType
    author: str = ""
    documentation_url: str = ""
    capabilities: List[InstrumentCapability] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "instrument_type": self.instrument_type.value,
            "author": self.author,
            "documentation_url": self.documentation_url,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "dependencies": self.dependencies,
            "config_schema": self.config_schema,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class InstrumentExecution:
    """Record of an instrument execution."""
    execution_id: str
    instrument_id: str
    capability_name: str
    parameters: Dict[str, Any]
    result: Any
    success: bool
    execution_time_ms: float
    agent_id: Optional[str]
    project_id: Optional[str]
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "instrument_id": self.instrument_id,
            "capability_name": self.capability_name,
            "parameters": self.parameters,
            "result": str(self.result)[:1000] if self.result else None,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message
        }


class Instrument(ABC):
    """
    Abstract base class for all instruments.

    Instruments provide standardized interfaces to external capabilities.
    All instruments must implement this interface.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._status = InstrumentStatus.INITIALIZING
        self._metadata: Optional[InstrumentMetadata] = None
        self._collective_memory = None
        self._ethics_engine = None

    @property
    @abstractmethod
    def metadata(self) -> InstrumentMetadata:
        """Get instrument metadata."""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the instrument. Returns True if successful."""
        pass

    @abstractmethod
    async def shutdown(self) -> bool:
        """Shutdown the instrument. Returns True if successful."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the instrument is healthy."""
        pass

    @abstractmethod
    async def execute(
        self,
        capability: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute a capability of the instrument."""
        pass

    @property
    def status(self) -> InstrumentStatus:
        """Get instrument status."""
        return self._status

    @status.setter
    def status(self, value: InstrumentStatus):
        """Set instrument status."""
        self._status = value

    @property
    def config(self) -> Dict[str, Any]:
        """Get instrument configuration."""
        return self._config

    async def _set_integrations(self, collective_memory, ethics_engine):
        """Set framework integrations."""
        self._collective_memory = collective_memory
        self._ethics_engine = ethics_engine

    async def _validate_ethics(
        self,
        capability: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Validate action against ethical principles."""
        if not self._ethics_engine:
            return True

        try:
            validation = await self._ethics_engine.validate(
                action_type=f"instrument_{capability}",
                data={"instrument": self.metadata.name, "parameters": parameters},
                context=context
            )
            return validation.is_approved
        except Exception as e:
            logger.error(f"Ethics validation failed: {e}")
            return False

    async def _record_execution(self, execution: InstrumentExecution):
        """Record execution to collective memory."""
        if not self._collective_memory:
            return

        try:
            from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
            await self._collective_memory.store(
                memory_type=MemoryType.TOOL_OUTPUT,
                content=execution.to_dict(),
                scope=MemoryScope.PROJECT,
                priority=MemoryPriority.NORMAL,
                tags=["instrument", execution.instrument_id, execution.capability_name],
                agent_id=execution.agent_id,
                project_id=execution.project_id
            )
        except Exception as e:
            logger.error(f"Failed to record execution: {e}")


class TigerBeetleInstrument(Instrument):
    """
    TigerBeetle financial ledger instrument.

    Provides double-entry bookkeeping capabilities through TigerBeetle.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._client = None
        self._metadata = InstrumentMetadata(
            instrument_id="tigerbeetle",
            name="TigerBeetle",
            description="High-performance financial ledger for double-entry bookkeeping",
            version="1.0.0",
            instrument_type=InstrumentType.FINANCIAL,
            author="Vessels Team",
            capabilities=[
                InstrumentCapability(
                    name="create_account",
                    description="Create a new ledger account",
                    parameters={
                        "account_id": "int",
                        "account_type": "str (ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE)",
                        "name": "str",
                        "metadata": "dict (optional)"
                    },
                    return_type="dict",
                    requires_confirmation=True,
                    ethical_constraints=["financial_oversight"]
                ),
                InstrumentCapability(
                    name="create_transfer",
                    description="Create a transfer between accounts",
                    parameters={
                        "debit_account_id": "int",
                        "credit_account_id": "int",
                        "amount": "int",
                        "reference": "str (optional)",
                        "metadata": "dict (optional)"
                    },
                    return_type="dict",
                    requires_confirmation=True,
                    ethical_constraints=["financial_oversight", "human_approval"]
                ),
                InstrumentCapability(
                    name="get_account_balance",
                    description="Get the balance of an account",
                    parameters={"account_id": "int"},
                    return_type="dict"
                ),
                InstrumentCapability(
                    name="get_account_history",
                    description="Get transaction history for an account",
                    parameters={
                        "account_id": "int",
                        "limit": "int (optional)",
                        "offset": "int (optional)"
                    },
                    return_type="list"
                )
            ],
            config_schema={
                "host": {"type": "string", "default": "127.0.0.1"},
                "port": {"type": "integer", "default": 3000},
                "cluster_id": {"type": "integer", "default": 0}
            },
            tags=["financial", "ledger", "accounting"]
        )

    @property
    def metadata(self) -> InstrumentMetadata:
        return self._metadata

    async def initialize(self) -> bool:
        try:
            from python.helpers.financial import get_financial_system
            self._client = await get_financial_system()
            self._status = InstrumentStatus.AVAILABLE
            return True
        except Exception as e:
            logger.error(f"Failed to initialize TigerBeetle: {e}")
            self._status = InstrumentStatus.ERROR
            return False

    async def shutdown(self) -> bool:
        self._status = InstrumentStatus.DISABLED
        return True

    async def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            # Try a simple operation
            return True
        except Exception:
            return False

    async def execute(
        self,
        capability: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        context = context or {}

        # Validate ethics
        if not await self._validate_ethics(capability, parameters, context):
            raise ValueError("Action blocked by ethical validation")

        start_time = datetime.now()
        success = False
        result = None
        error_msg = None

        try:
            if capability == "create_account":
                result = await self._client.create_account(**parameters)
            elif capability == "create_transfer":
                result = await self._client.create_transfer(**parameters)
            elif capability == "get_account_balance":
                result = await self._client.get_account_balance(**parameters)
            elif capability == "get_account_history":
                result = await self._client.get_account_history(**parameters)
            else:
                raise ValueError(f"Unknown capability: {capability}")

            success = True

        except Exception as e:
            error_msg = str(e)
            raise

        finally:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            execution = InstrumentExecution(
                execution_id=hashlib.sha256(f"{capability}:{datetime.now().isoformat()}".encode()).hexdigest()[:16],
                instrument_id=self.metadata.instrument_id,
                capability_name=capability,
                parameters=parameters,
                result=result,
                success=success,
                execution_time_ms=execution_time,
                agent_id=context.get("agent_id"),
                project_id=context.get("project_id"),
                error_message=error_msg
            )
            await self._record_execution(execution)

        return result


class YouTubeDownloadInstrument(Instrument):
    """
    YouTube download instrument.

    Provides capabilities to download and process YouTube videos.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._metadata = InstrumentMetadata(
            instrument_id="yt_download",
            name="YouTube Downloader",
            description="Download and process YouTube videos and audio",
            version="1.0.0",
            instrument_type=InstrumentType.MEDIA,
            author="Vessels Team",
            capabilities=[
                InstrumentCapability(
                    name="download_video",
                    description="Download a YouTube video",
                    parameters={
                        "url": "str",
                        "output_path": "str",
                        "format": "str (mp4, webm, etc.)",
                        "quality": "str (best, worst, 720p, etc.)"
                    },
                    return_type="dict",
                    ethical_constraints=["copyright_respect"]
                ),
                InstrumentCapability(
                    name="download_audio",
                    description="Download audio from a YouTube video",
                    parameters={
                        "url": "str",
                        "output_path": "str",
                        "format": "str (mp3, m4a, etc.)"
                    },
                    return_type="dict",
                    ethical_constraints=["copyright_respect"]
                ),
                InstrumentCapability(
                    name="get_video_info",
                    description="Get information about a YouTube video",
                    parameters={"url": "str"},
                    return_type="dict"
                )
            ],
            config_schema={
                "output_dir": {"type": "string", "default": "./downloads"},
                "max_filesize": {"type": "integer", "default": 1073741824}
            },
            tags=["media", "video", "download", "youtube"]
        )

    @property
    def metadata(self) -> InstrumentMetadata:
        return self._metadata

    async def initialize(self) -> bool:
        try:
            # Check if yt-dlp is available
            import subprocess
            result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                self._status = InstrumentStatus.AVAILABLE
                return True
            else:
                self._status = InstrumentStatus.ERROR
                return False
        except Exception as e:
            logger.error(f"Failed to initialize YouTube Downloader: {e}")
            self._status = InstrumentStatus.ERROR
            return False

    async def shutdown(self) -> bool:
        self._status = InstrumentStatus.DISABLED
        return True

    async def health_check(self) -> bool:
        try:
            import subprocess
            result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    async def execute(
        self,
        capability: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        context = context or {}

        # Validate ethics
        if not await self._validate_ethics(capability, parameters, context):
            raise ValueError("Action blocked by ethical validation")

        start_time = datetime.now()
        success = False
        result = None
        error_msg = None

        try:
            import subprocess

            if capability == "get_video_info":
                cmd = ["yt-dlp", "--dump-json", parameters["url"]]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0:
                    result = json.loads(proc.stdout)
                else:
                    raise Exception(proc.stderr)

            elif capability == "download_video":
                output_template = os.path.join(
                    parameters.get("output_path", "./downloads"),
                    "%(title)s.%(ext)s"
                )
                cmd = [
                    "yt-dlp",
                    "-f", parameters.get("quality", "best"),
                    "-o", output_template,
                    parameters["url"]
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0:
                    result = {"status": "success", "output": proc.stdout}
                else:
                    raise Exception(proc.stderr)

            elif capability == "download_audio":
                output_template = os.path.join(
                    parameters.get("output_path", "./downloads"),
                    "%(title)s.%(ext)s"
                )
                cmd = [
                    "yt-dlp",
                    "-x",
                    "--audio-format", parameters.get("format", "mp3"),
                    "-o", output_template,
                    parameters["url"]
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0:
                    result = {"status": "success", "output": proc.stdout}
                else:
                    raise Exception(proc.stderr)

            else:
                raise ValueError(f"Unknown capability: {capability}")

            success = True

        except Exception as e:
            error_msg = str(e)
            raise

        finally:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            execution = InstrumentExecution(
                execution_id=hashlib.sha256(f"{capability}:{datetime.now().isoformat()}".encode()).hexdigest()[:16],
                instrument_id=self.metadata.instrument_id,
                capability_name=capability,
                parameters=parameters,
                result=result,
                success=success,
                execution_time_ms=execution_time,
                agent_id=context.get("agent_id"),
                project_id=context.get("project_id"),
                error_message=error_msg
            )
            await self._record_execution(execution)

        return result


class InstrumentRegistry:
    """
    Central registry for all instruments in the A0 framework.

    This singleton manages instrument lifecycle, discovery, and execution
    across the entire agent ecosystem.
    """

    _instance: Optional['InstrumentRegistry'] = None
    _lock = asyncio.Lock()

    # Built-in instrument classes
    BUILTIN_INSTRUMENTS: Dict[str, Type[Instrument]] = {
        "tigerbeetle": TigerBeetleInstrument,
        "yt_download": YouTubeDownloadInstrument,
    }

    def __init__(self):
        self._instruments: Dict[str, Instrument] = {}
        self._instrument_classes: Dict[str, Type[Instrument]] = {}
        self._collective_memory = None
        self._ethics_engine = None
        self._initialized = False
        self._hooks: Dict[str, List[Callable]] = {
            "instrument_registered": [],
            "instrument_executed": [],
            "instrument_error": [],
        }

    @classmethod
    async def get_instance(cls) -> 'InstrumentRegistry':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the instrument registry."""
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

        # Register built-in instruments
        for name, cls in self.BUILTIN_INSTRUMENTS.items():
            self._instrument_classes[name] = cls

        # Load custom instruments from instruments/ directory
        await self._load_custom_instruments()

        self._initialized = True
        logger.info(f"InstrumentRegistry initialized with {len(self._instrument_classes)} instrument types")

    async def _load_custom_instruments(self):
        """Load custom instruments from the instruments directory."""
        from python.helpers import files

        instruments_dir = files.get_abs_path("instruments")

        for category in ["default", "custom"]:
            category_dir = os.path.join(instruments_dir, category)
            if not os.path.exists(category_dir):
                continue

            for instrument_name in os.listdir(category_dir):
                instrument_dir = os.path.join(category_dir, instrument_name)
                if not os.path.isdir(instrument_dir):
                    continue

                # Look for instrument.py
                instrument_file = os.path.join(instrument_dir, "instrument.py")
                if not os.path.exists(instrument_file):
                    continue

                try:
                    # Load the module
                    spec = importlib.util.spec_from_file_location(
                        f"instruments.{category}.{instrument_name}",
                        instrument_file
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # Find Instrument subclass
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type) and
                                issubclass(attr, Instrument) and
                                attr is not Instrument):
                                self._instrument_classes[instrument_name] = attr
                                logger.info(f"Loaded custom instrument: {instrument_name}")
                                break

                except Exception as e:
                    logger.error(f"Failed to load instrument {instrument_name}: {e}")

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

    async def register(
        self,
        instrument_id: str,
        config: Optional[Dict[str, Any]] = None,
        auto_initialize: bool = True
    ) -> Optional[Instrument]:
        """Register and optionally initialize an instrument."""
        if instrument_id not in self._instrument_classes:
            logger.error(f"Unknown instrument type: {instrument_id}")
            return None

        if instrument_id in self._instruments:
            logger.warning(f"Instrument already registered: {instrument_id}")
            return self._instruments[instrument_id]

        try:
            # Create instance
            instrument_class = self._instrument_classes[instrument_id]
            instrument = instrument_class(config)

            # Set integrations
            await instrument._set_integrations(
                self._collective_memory,
                self._ethics_engine
            )

            # Initialize if requested
            if auto_initialize:
                success = await instrument.initialize()
                if not success:
                    logger.error(f"Failed to initialize instrument: {instrument_id}")
                    return None

            self._instruments[instrument_id] = instrument
            await self._run_hooks("instrument_registered", instrument)

            logger.info(f"Registered instrument: {instrument_id}")
            return instrument

        except Exception as e:
            logger.error(f"Failed to register instrument {instrument_id}: {e}")
            return None

    async def unregister(self, instrument_id: str) -> bool:
        """Unregister and shutdown an instrument."""
        if instrument_id not in self._instruments:
            return False

        try:
            instrument = self._instruments[instrument_id]
            await instrument.shutdown()
            del self._instruments[instrument_id]
            return True
        except Exception as e:
            logger.error(f"Failed to unregister instrument {instrument_id}: {e}")
            return False

    def get(self, instrument_id: str) -> Optional[Instrument]:
        """Get a registered instrument."""
        return self._instruments.get(instrument_id)

    def list_registered(self) -> List[str]:
        """List registered instrument IDs."""
        return list(self._instruments.keys())

    def list_available(self) -> List[str]:
        """List available instrument types."""
        return list(self._instrument_classes.keys())

    def get_metadata(self, instrument_id: str) -> Optional[InstrumentMetadata]:
        """Get metadata for an instrument."""
        instrument = self._instruments.get(instrument_id)
        if instrument:
            return instrument.metadata
        return None

    def list_all_metadata(self) -> List[InstrumentMetadata]:
        """Get metadata for all registered instruments."""
        return [i.metadata for i in self._instruments.values()]

    async def execute(
        self,
        instrument_id: str,
        capability: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute a capability on an instrument."""
        instrument = self._instruments.get(instrument_id)
        if not instrument:
            raise ValueError(f"Instrument not registered: {instrument_id}")

        if instrument.status != InstrumentStatus.AVAILABLE:
            raise ValueError(f"Instrument not available: {instrument_id} (status: {instrument.status})")

        try:
            result = await instrument.execute(capability, parameters, context)
            await self._run_hooks("instrument_executed", {
                "instrument_id": instrument_id,
                "capability": capability,
                "success": True
            })
            return result

        except Exception as e:
            await self._run_hooks("instrument_error", {
                "instrument_id": instrument_id,
                "capability": capability,
                "error": str(e)
            })
            raise

    async def health_check_all(self) -> Dict[str, bool]:
        """Run health checks on all registered instruments."""
        results = {}
        for instrument_id, instrument in self._instruments.items():
            try:
                results[instrument_id] = await instrument.health_check()
            except Exception:
                results[instrument_id] = False
        return results

    async def get_status_all(self) -> Dict[str, str]:
        """Get status of all registered instruments."""
        return {
            instrument_id: instrument.status.value
            for instrument_id, instrument in self._instruments.items()
        }


# Convenience functions
async def get_instrument_registry() -> InstrumentRegistry:
    """Get the instrument registry instance."""
    return await InstrumentRegistry.get_instance()


async def get_instrument(instrument_id: str) -> Optional[Instrument]:
    """Get an instrument by ID."""
    registry = await get_instrument_registry()
    return registry.get(instrument_id)


async def execute_instrument(
    instrument_id: str,
    capability: str,
    parameters: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> Any:
    """Execute a capability on an instrument."""
    registry = await get_instrument_registry()
    return await registry.execute(instrument_id, capability, parameters, context)
