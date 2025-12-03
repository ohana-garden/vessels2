"""
Spider Scheduler for Vessels A0 Framework

This module manages scheduled crawling tasks for continuous
tool discovery and registry updates.

Features:
1. Schedule periodic crawls of registered sources
2. Track last crawl times and changes
3. Detect new or updated tools
4. Automatic re-registration of updated tools
5. Notification of significant discoveries
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from python.helpers.web_spider import WebSpider, CrawlConfig, CrawlResult
from python.helpers.tool_discovery import (
    ToolDiscoveryEngine,
    ToolQuality,
    RegisteredTool,
)

logger = logging.getLogger(__name__)


class ScheduleFrequency(Enum):
    """Frequency of scheduled crawls."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    MANUAL = "manual"


class SourceStatus(Enum):
    """Status of a monitored source."""
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    REMOVED = "removed"


@dataclass
class MonitoredSource:
    """A source being monitored for new tools."""
    source_id: str
    url: str
    name: str
    description: str
    frequency: ScheduleFrequency
    crawl_config: CrawlConfig
    auto_register: bool
    min_quality: ToolQuality
    status: SourceStatus
    created_at: datetime
    last_crawl: Optional[datetime]
    next_crawl: Optional[datetime]
    crawl_count: int
    tools_discovered: int
    content_hash: Optional[str]
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "name": self.name,
            "description": self.description,
            "frequency": self.frequency.value,
            "auto_register": self.auto_register,
            "min_quality": self.min_quality.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_crawl": self.last_crawl.isoformat() if self.last_crawl else None,
            "next_crawl": self.next_crawl.isoformat() if self.next_crawl else None,
            "crawl_count": self.crawl_count,
            "tools_discovered": self.tools_discovered,
            "tags": self.tags,
        }


@dataclass
class CrawlEvent:
    """Record of a crawl event."""
    event_id: str
    source_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    pages_crawled: int
    tools_found: int
    tools_registered: int
    new_tools: List[str]
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source_id": self.source_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "pages_crawled": self.pages_crawled,
            "tools_found": self.tools_found,
            "tools_registered": self.tools_registered,
            "new_tools": self.new_tools,
            "errors": self.errors[:10],
        }


class SpiderScheduler:
    """
    Manages scheduled crawling for continuous tool discovery.

    This scheduler maintains a list of monitored sources and
    periodically crawls them to discover new tools.
    """

    _instance: Optional['SpiderScheduler'] = None
    _lock = asyncio.Lock()

    # Frequency to timedelta mapping
    FREQUENCY_INTERVALS = {
        ScheduleFrequency.HOURLY: timedelta(hours=1),
        ScheduleFrequency.DAILY: timedelta(days=1),
        ScheduleFrequency.WEEKLY: timedelta(weeks=1),
        ScheduleFrequency.MONTHLY: timedelta(days=30),
        ScheduleFrequency.MANUAL: None,
    }

    def __init__(self):
        self._sources: Dict[str, MonitoredSource] = {}
        self._events: List[CrawlEvent] = []
        self._discovery_engine: Optional[ToolDiscoveryEngine] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._graph_store = None
        self._hooks: Dict[str, List[Callable]] = {
            "crawl_started": [],
            "crawl_completed": [],
            "new_tool_discovered": [],
            "source_updated": [],
        }
        self._check_interval = 60  # Check every minute

    @classmethod
    async def get_instance(cls) -> 'SpiderScheduler':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the scheduler."""
        self._discovery_engine = await ToolDiscoveryEngine.get_instance()
        logger.info("SpiderScheduler initialized")

    async def set_graph_store(self, graph_store):
        """Set graph store for persistence."""
        self._graph_store = graph_store
        await self._load_sources()

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

    async def add_source(
        self,
        url: str,
        name: Optional[str] = None,
        description: str = "",
        frequency: ScheduleFrequency = ScheduleFrequency.DAILY,
        auto_register: bool = False,
        min_quality: ToolQuality = ToolQuality.MEDIUM,
        depth: int = 2,
        max_pages: int = 50,
        tags: Optional[List[str]] = None,
    ) -> MonitoredSource:
        """
        Add a source to be monitored.

        Args:
            url: URL to monitor
            name: Display name for the source
            description: Description of what this source provides
            frequency: How often to crawl
            auto_register: Whether to auto-register discovered tools
            min_quality: Minimum quality for registration
            depth: Maximum crawl depth
            max_pages: Maximum pages per crawl
            tags: Tags for categorization

        Returns:
            The created MonitoredSource
        """
        source_id = hashlib.sha256(url.encode()).hexdigest()[:16]

        if source_id in self._sources:
            logger.info(f"Source already exists: {url}")
            return self._sources[source_id]

        crawl_config = CrawlConfig(
            max_depth=depth,
            max_pages=max_pages,
            extract_api_specs=True,
            parse_documentation=True,
        )

        source = MonitoredSource(
            source_id=source_id,
            url=url,
            name=name or url,
            description=description,
            frequency=frequency,
            crawl_config=crawl_config,
            auto_register=auto_register,
            min_quality=min_quality,
            status=SourceStatus.ACTIVE,
            created_at=datetime.now(),
            last_crawl=None,
            next_crawl=datetime.now(),  # Schedule immediately
            crawl_count=0,
            tools_discovered=0,
            content_hash=None,
            tags=tags or [],
        )

        self._sources[source_id] = source
        await self._save_source(source)
        await self._run_hooks("source_updated", source)

        logger.info(f"Added source: {name or url}")
        return source

    async def remove_source(self, source_id: str) -> bool:
        """Remove a source from monitoring."""
        if source_id not in self._sources:
            return False

        source = self._sources[source_id]
        source.status = SourceStatus.REMOVED
        del self._sources[source_id]

        await self._run_hooks("source_updated", source)
        return True

    async def pause_source(self, source_id: str) -> bool:
        """Pause a source."""
        if source_id not in self._sources:
            return False

        self._sources[source_id].status = SourceStatus.PAUSED
        await self._save_source(self._sources[source_id])
        return True

    async def resume_source(self, source_id: str) -> bool:
        """Resume a paused source."""
        if source_id not in self._sources:
            return False

        source = self._sources[source_id]
        source.status = SourceStatus.ACTIVE
        source.next_crawl = datetime.now()
        await self._save_source(source)
        return True

    async def trigger_crawl(self, source_id: str) -> Optional[CrawlEvent]:
        """Manually trigger a crawl for a source."""
        if source_id not in self._sources:
            return None

        source = self._sources[source_id]
        return await self._crawl_source(source)

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Spider scheduler started")

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Spider scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                now = datetime.now()

                # Find sources due for crawling
                for source in list(self._sources.values()):
                    if source.status != SourceStatus.ACTIVE:
                        continue

                    if source.next_crawl and source.next_crawl <= now:
                        try:
                            await self._crawl_source(source)
                        except Exception as e:
                            logger.error(f"Crawl failed for {source.name}: {e}")
                            source.status = SourceStatus.ERROR

                await asyncio.sleep(self._check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(self._check_interval)

    async def _crawl_source(self, source: MonitoredSource) -> CrawlEvent:
        """Crawl a source and process results."""
        event_id = hashlib.sha256(
            f"{source.source_id}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        event = CrawlEvent(
            event_id=event_id,
            source_id=source.source_id,
            started_at=datetime.now(),
            completed_at=None,
            status="in_progress",
            pages_crawled=0,
            tools_found=0,
            tools_registered=0,
            new_tools=[],
            errors=[],
        )

        await self._run_hooks("crawl_started", {"source": source, "event": event})

        try:
            # Create spider and crawl
            spider = WebSpider(source.crawl_config)
            result = await spider.crawl(source.url)
            await spider.close()

            event.pages_crawled = result.pages_crawled
            event.tools_found = result.tools_discovered
            event.errors = result.errors

            # Check for content changes
            content_signature = self._compute_content_signature(result)
            is_changed = content_signature != source.content_hash

            if is_changed or source.crawl_count == 0:
                # Process discoveries
                registered = await self._discovery_engine.process_crawl_result(
                    result,
                    auto_register=source.auto_register,
                    min_quality=source.min_quality,
                )

                event.tools_registered = len(registered)
                event.new_tools = [t.name for t in registered]

                for tool in registered:
                    await self._run_hooks("new_tool_discovered", {
                        "source": source,
                        "tool": tool,
                    })

                source.content_hash = content_signature

            # Update source
            source.last_crawl = datetime.now()
            source.crawl_count += 1
            source.tools_discovered += event.tools_found
            source.next_crawl = self._calculate_next_crawl(source)

            event.status = "completed"
            event.completed_at = datetime.now()

        except Exception as e:
            event.status = "failed"
            event.errors.append(str(e))
            event.completed_at = datetime.now()
            logger.error(f"Crawl failed for {source.name}: {e}")

        finally:
            self._events.append(event)
            await self._save_source(source)
            await self._save_event(event)
            await self._run_hooks("crawl_completed", {"source": source, "event": event})

        return event

    def _compute_content_signature(self, result: CrawlResult) -> str:
        """Compute a signature of the crawl content for change detection."""
        # Create signature from discovered tools and APIs
        signature_data = json.dumps({
            "tools": [t.tool_id for t in sorted(result.discovered_tools, key=lambda x: x.tool_id)],
            "apis": [a.api_id for a in sorted(result.discovered_apis, key=lambda x: x.api_id)],
        }, sort_keys=True)
        return hashlib.sha256(signature_data.encode()).hexdigest()

    def _calculate_next_crawl(self, source: MonitoredSource) -> Optional[datetime]:
        """Calculate next crawl time."""
        interval = self.FREQUENCY_INTERVALS.get(source.frequency)
        if interval is None:
            return None
        return datetime.now() + interval

    async def _save_source(self, source: MonitoredSource):
        """Save source to graph store."""
        if not self._graph_store:
            return

        try:
            await self._graph_store.add_memory(
                area="INSTRUMENTS",
                content=json.dumps(source.to_dict()),
                metadata={
                    "type": "monitored_source",
                    "source_id": source.source_id,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to save source: {e}")

    async def _save_event(self, event: CrawlEvent):
        """Save crawl event to graph store."""
        if not self._graph_store:
            return

        try:
            await self._graph_store.add_memory(
                area="INSTRUMENTS",
                content=json.dumps(event.to_dict()),
                metadata={
                    "type": "crawl_event",
                    "event_id": event.event_id,
                    "source_id": event.source_id,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to save event: {e}")

    async def _load_sources(self):
        """Load sources from graph store."""
        if not self._graph_store:
            return

        try:
            # Search for monitored sources
            results = await self._graph_store.search_memory(
                area="INSTRUMENTS",
                query="monitored_source",
                limit=100,
            )

            for result in results:
                try:
                    data = json.loads(result.get("content", "{}"))
                    if data.get("type") == "monitored_source":
                        source = MonitoredSource(
                            source_id=data["source_id"],
                            url=data["url"],
                            name=data["name"],
                            description=data.get("description", ""),
                            frequency=ScheduleFrequency(data["frequency"]),
                            crawl_config=CrawlConfig(),
                            auto_register=data.get("auto_register", False),
                            min_quality=ToolQuality(data.get("min_quality", "medium")),
                            status=SourceStatus(data["status"]),
                            created_at=datetime.fromisoformat(data["created_at"]),
                            last_crawl=datetime.fromisoformat(data["last_crawl"]) if data.get("last_crawl") else None,
                            next_crawl=datetime.fromisoformat(data["next_crawl"]) if data.get("next_crawl") else None,
                            crawl_count=data.get("crawl_count", 0),
                            tools_discovered=data.get("tools_discovered", 0),
                            content_hash=data.get("content_hash"),
                            tags=data.get("tags", []),
                        )
                        self._sources[source.source_id] = source
                except Exception as e:
                    logger.warning(f"Failed to load source: {e}")

            logger.info(f"Loaded {len(self._sources)} monitored sources")

        except Exception as e:
            logger.warning(f"Failed to load sources: {e}")

    # Query methods
    def get_sources(self) -> List[MonitoredSource]:
        """Get all monitored sources."""
        return list(self._sources.values())

    def get_source(self, source_id: str) -> Optional[MonitoredSource]:
        """Get a source by ID."""
        return self._sources.get(source_id)

    def get_events(
        self,
        source_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[CrawlEvent]:
        """Get crawl events, optionally filtered by source."""
        events = self._events
        if source_id:
            events = [e for e in events if e.source_id == source_id]
        return events[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        active = sum(1 for s in self._sources.values() if s.status == SourceStatus.ACTIVE)
        paused = sum(1 for s in self._sources.values() if s.status == SourceStatus.PAUSED)
        error = sum(1 for s in self._sources.values() if s.status == SourceStatus.ERROR)

        total_crawls = sum(s.crawl_count for s in self._sources.values())
        total_tools = sum(s.tools_discovered for s in self._sources.values())

        return {
            "sources_total": len(self._sources),
            "sources_active": active,
            "sources_paused": paused,
            "sources_error": error,
            "total_crawls": total_crawls,
            "total_tools_discovered": total_tools,
            "events_recorded": len(self._events),
            "scheduler_running": self._running,
        }


# Convenience functions
async def get_spider_scheduler() -> SpiderScheduler:
    """Get the spider scheduler instance."""
    return await SpiderScheduler.get_instance()


async def add_monitored_source(
    url: str,
    frequency: str = "daily",
    auto_register: bool = False,
) -> MonitoredSource:
    """Add a source to be monitored."""
    scheduler = await get_spider_scheduler()
    freq = ScheduleFrequency(frequency)
    return await scheduler.add_source(
        url=url,
        frequency=freq,
        auto_register=auto_register,
    )
