"""
Spider Graph Store Integration for Vessels A0 Framework

This module provides integration between the web spider/tool discovery
system and the graph store for persistent storage of discoveries.

Features:
1. Store discovered APIs with full specifications
2. Store discovered tools with validation results
3. Track crawl events and source monitoring
4. Enable semantic search over discoveries
5. Maintain relationships between discoveries
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from python.helpers.graph_store import (
    GraphStore,
    VesselNodeType,
    MemoryArea,
)
from python.helpers.web_spider import (
    DiscoveredAPI,
    DiscoveredTool,
    DiscoveredPage,
    CrawlResult,
    SourceType,
)
from python.helpers.tool_discovery import (
    RegisteredTool,
    ToolValidation,
    ToolQuality,
    RegistrationStatus,
)
from python.helpers.spider_scheduler import (
    MonitoredSource,
    CrawlEvent,
)

logger = logging.getLogger(__name__)


class SpiderGraphIntegration:
    """
    Integration layer between spider discovery and graph storage.

    This class provides methods to store and query spider discoveries
    in the Vessels graph store, enabling persistent tracking of
    discovered APIs, tools, and crawl operations.
    """

    _instance: Optional['SpiderGraphIntegration'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._graph_store: Optional[GraphStore] = None
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> 'SpiderGraphIntegration':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the integration."""
        if self._initialized:
            return

        try:
            from python.helpers.graph_store import get_graph_store
            self._graph_store = await get_graph_store()
            self._initialized = True
            logger.info("SpiderGraphIntegration initialized")
        except Exception as e:
            logger.warning(f"Graph store not available: {e}")
            self._initialized = False

    async def store_discovered_api(
        self,
        api: DiscoveredAPI,
        vessel_id: str = "default",
    ) -> bool:
        """
        Store a discovered API in the graph.

        Args:
            api: The discovered API to store
            vessel_id: The vessel/agent context

        Returns:
            True if stored successfully
        """
        if not self._graph_store:
            logger.warning("Graph store not available")
            return False

        try:
            await self._graph_store.save_memory(
                content=json.dumps(api.to_dict()),
                area=MemoryArea.DISCOVERIES,
                metadata={
                    "node_type": VesselNodeType.DISCOVERED_API.value,
                    "api_id": api.api_id,
                    "name": api.name,
                    "spec_type": api.spec_type.value,
                    "base_url": api.base_url,
                    "endpoints_count": len(api.endpoints),
                    "vessel_id": vessel_id,
                    "discovered_at": api.discovered_at.isoformat(),
                }
            )
            logger.info(f"Stored discovered API: {api.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to store discovered API: {e}")
            return False

    async def store_discovered_tool(
        self,
        tool: DiscoveredTool,
        validation: Optional[ToolValidation] = None,
        vessel_id: str = "default",
    ) -> bool:
        """
        Store a discovered tool in the graph.

        Args:
            tool: The discovered tool to store
            validation: Optional validation results
            vessel_id: The vessel/agent context

        Returns:
            True if stored successfully
        """
        if not self._graph_store:
            logger.warning("Graph store not available")
            return False

        try:
            tool_data = tool.to_dict()
            if validation:
                tool_data["validation"] = {
                    "is_valid": validation.is_valid,
                    "quality": validation.quality.value,
                    "risk_level": validation.risk_level,
                    "issues": validation.issues,
                    "requires_auth": validation.requires_auth,
                }

            await self._graph_store.save_memory(
                content=json.dumps(tool_data),
                area=MemoryArea.DISCOVERIES,
                metadata={
                    "node_type": VesselNodeType.DISCOVERED_TOOL.value,
                    "tool_id": tool.tool_id,
                    "name": tool.name,
                    "source_type": tool.source_type,
                    "confidence": tool.confidence,
                    "quality": validation.quality.value if validation else "unknown",
                    "vessel_id": vessel_id,
                    "discovered_at": tool.discovered_at.isoformat(),
                }
            )
            logger.info(f"Stored discovered tool: {tool.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to store discovered tool: {e}")
            return False

    async def store_registered_tool(
        self,
        tool: RegisteredTool,
        vessel_id: str = "default",
    ) -> bool:
        """
        Store a registered tool in the graph.

        Args:
            tool: The registered tool to store
            vessel_id: The vessel/agent context

        Returns:
            True if stored successfully
        """
        if not self._graph_store:
            return False

        try:
            await self._graph_store.save_memory(
                content=json.dumps(tool.to_dict()),
                area=MemoryArea.INSTRUMENTS,
                metadata={
                    "node_type": VesselNodeType.REGISTERED_TOOL.value,
                    "tool_id": tool.tool_id,
                    "name": tool.name,
                    "source": tool.source,
                    "status": tool.status.value,
                    "quality": tool.validation.quality.value,
                    "vessel_id": vessel_id,
                    "registered_at": tool.registered_at.isoformat(),
                }
            )
            logger.info(f"Stored registered tool: {tool.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to store registered tool: {e}")
            return False

    async def store_crawl_source(
        self,
        source: MonitoredSource,
        vessel_id: str = "default",
    ) -> bool:
        """
        Store a monitored crawl source in the graph.

        Args:
            source: The monitored source to store
            vessel_id: The vessel/agent context

        Returns:
            True if stored successfully
        """
        if not self._graph_store:
            return False

        try:
            await self._graph_store.save_memory(
                content=json.dumps(source.to_dict()),
                area=MemoryArea.DISCOVERIES,
                metadata={
                    "node_type": VesselNodeType.CRAWL_SOURCE.value,
                    "source_id": source.source_id,
                    "url": source.url,
                    "name": source.name,
                    "frequency": source.frequency.value,
                    "status": source.status.value,
                    "vessel_id": vessel_id,
                }
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store crawl source: {e}")
            return False

    async def store_crawl_event(
        self,
        event: CrawlEvent,
        vessel_id: str = "default",
    ) -> bool:
        """
        Store a crawl event in the graph.

        Args:
            event: The crawl event to store
            vessel_id: The vessel/agent context

        Returns:
            True if stored successfully
        """
        if not self._graph_store:
            return False

        try:
            await self._graph_store.save_memory(
                content=json.dumps(event.to_dict()),
                area=MemoryArea.DISCOVERIES,
                metadata={
                    "node_type": VesselNodeType.CRAWL_EVENT.value,
                    "event_id": event.event_id,
                    "source_id": event.source_id,
                    "status": event.status,
                    "tools_found": event.tools_found,
                    "tools_registered": event.tools_registered,
                    "vessel_id": vessel_id,
                }
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store crawl event: {e}")
            return False

    async def store_crawl_result(
        self,
        result: CrawlResult,
        vessel_id: str = "default",
    ) -> Dict[str, int]:
        """
        Store all discoveries from a crawl result.

        Args:
            result: The complete crawl result
            vessel_id: The vessel/agent context

        Returns:
            Dict with counts of stored items
        """
        stored = {
            "apis": 0,
            "tools": 0,
            "pages": 0,
        }

        # Store discovered APIs
        for api in result.discovered_apis:
            if await self.store_discovered_api(api, vessel_id):
                stored["apis"] += 1

        # Store discovered tools
        for tool in result.discovered_tools:
            if await self.store_discovered_tool(tool, None, vessel_id):
                stored["tools"] += 1

        logger.info(
            f"Stored crawl result: {stored['apis']} APIs, "
            f"{stored['tools']} tools from {result.seed_url}"
        )

        return stored

    async def search_discovered_apis(
        self,
        query: str,
        spec_type: Optional[SourceType] = None,
        limit: int = 20,
        vessel_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        Search for discovered APIs.

        Args:
            query: Search query (name, description, endpoint paths)
            spec_type: Optional filter by spec type
            limit: Maximum results
            vessel_id: The vessel/agent context

        Returns:
            List of matching API records
        """
        if not self._graph_store:
            return []

        try:
            results = await self._graph_store.search_memories(
                query=query,
                area=MemoryArea.DISCOVERIES,
                limit=limit * 2,  # Fetch more to filter
            )

            apis = []
            for result in results:
                meta = result.get("metadata", {})
                if meta.get("node_type") != VesselNodeType.DISCOVERED_API.value:
                    continue
                if meta.get("vessel_id") != vessel_id:
                    continue
                if spec_type and meta.get("spec_type") != spec_type.value:
                    continue

                try:
                    api_data = json.loads(result.get("content", "{}"))
                    api_data["_score"] = result.get("score", 0)
                    apis.append(api_data)
                except:
                    pass

                if len(apis) >= limit:
                    break

            return apis

        except Exception as e:
            logger.error(f"Failed to search APIs: {e}")
            return []

    async def search_discovered_tools(
        self,
        query: str,
        source_type: Optional[str] = None,
        min_quality: Optional[ToolQuality] = None,
        limit: int = 20,
        vessel_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        Search for discovered tools.

        Args:
            query: Search query
            source_type: Optional filter by source type
            min_quality: Optional minimum quality filter
            limit: Maximum results
            vessel_id: The vessel/agent context

        Returns:
            List of matching tool records
        """
        if not self._graph_store:
            return []

        try:
            results = await self._graph_store.search_memories(
                query=query,
                area=MemoryArea.DISCOVERIES,
                limit=limit * 2,
            )

            quality_order = ["unknown", "low", "medium", "high"]
            min_quality_idx = quality_order.index(min_quality.value) if min_quality else 0

            tools = []
            for result in results:
                meta = result.get("metadata", {})
                if meta.get("node_type") != VesselNodeType.DISCOVERED_TOOL.value:
                    continue
                if meta.get("vessel_id") != vessel_id:
                    continue
                if source_type and meta.get("source_type") != source_type:
                    continue

                # Check quality
                tool_quality = meta.get("quality", "unknown")
                if quality_order.index(tool_quality) < min_quality_idx:
                    continue

                try:
                    tool_data = json.loads(result.get("content", "{}"))
                    tool_data["_score"] = result.get("score", 0)
                    tools.append(tool_data)
                except:
                    pass

                if len(tools) >= limit:
                    break

            return tools

        except Exception as e:
            logger.error(f"Failed to search tools: {e}")
            return []

    async def get_registered_tools(
        self,
        status: Optional[RegistrationStatus] = None,
        vessel_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        Get all registered tools.

        Args:
            status: Optional filter by status
            vessel_id: The vessel/agent context

        Returns:
            List of registered tool records
        """
        if not self._graph_store:
            return []

        try:
            results = await self._graph_store.search_memories(
                query="registered tool",
                area=MemoryArea.INSTRUMENTS,
                limit=100,
            )

            tools = []
            for result in results:
                meta = result.get("metadata", {})
                if meta.get("node_type") != VesselNodeType.REGISTERED_TOOL.value:
                    continue
                if meta.get("vessel_id") != vessel_id:
                    continue
                if status and meta.get("status") != status.value:
                    continue

                try:
                    tools.append(json.loads(result.get("content", "{}")))
                except:
                    pass

            return tools

        except Exception as e:
            logger.error(f"Failed to get registered tools: {e}")
            return []

    async def get_crawl_sources(
        self,
        vessel_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """Get all monitored crawl sources."""
        if not self._graph_store:
            return []

        try:
            results = await self._graph_store.search_memories(
                query="crawl source monitor",
                area=MemoryArea.DISCOVERIES,
                limit=100,
            )

            sources = []
            for result in results:
                meta = result.get("metadata", {})
                if meta.get("node_type") != VesselNodeType.CRAWL_SOURCE.value:
                    continue
                if meta.get("vessel_id") != vessel_id:
                    continue

                try:
                    sources.append(json.loads(result.get("content", "{}")))
                except:
                    pass

            return sources

        except Exception as e:
            logger.error(f"Failed to get crawl sources: {e}")
            return []

    async def get_discovery_statistics(
        self,
        vessel_id: str = "default",
    ) -> Dict[str, Any]:
        """
        Get statistics about discoveries.

        Returns counts of APIs, tools, sources, and recent activity.
        """
        if not self._graph_store:
            return {
                "total_apis": 0,
                "total_tools": 0,
                "registered_tools": 0,
                "crawl_sources": 0,
                "graph_available": False,
            }

        apis = await self.search_discovered_apis("", limit=1000, vessel_id=vessel_id)
        tools = await self.search_discovered_tools("", limit=1000, vessel_id=vessel_id)
        registered = await self.get_registered_tools(vessel_id=vessel_id)
        sources = await self.get_crawl_sources(vessel_id=vessel_id)

        # Count by quality
        quality_counts = {}
        for tool in tools:
            quality = tool.get("validation", {}).get("quality", "unknown")
            quality_counts[quality] = quality_counts.get(quality, 0) + 1

        # Count by source type
        source_type_counts = {}
        for tool in tools:
            source = tool.get("source_type", "unknown")
            source_type_counts[source] = source_type_counts.get(source, 0) + 1

        return {
            "total_apis": len(apis),
            "total_tools": len(tools),
            "registered_tools": len(registered),
            "crawl_sources": len(sources),
            "tools_by_quality": quality_counts,
            "tools_by_source": source_type_counts,
            "graph_available": True,
        }


# Convenience functions
async def get_spider_graph_integration() -> SpiderGraphIntegration:
    """Get the spider graph integration instance."""
    return await SpiderGraphIntegration.get_instance()


async def store_discovery(
    discovery: Any,
    vessel_id: str = "default",
) -> bool:
    """
    Store any type of discovery in the graph.

    Automatically determines the type and stores appropriately.
    """
    integration = await get_spider_graph_integration()

    if isinstance(discovery, DiscoveredAPI):
        return await integration.store_discovered_api(discovery, vessel_id)
    elif isinstance(discovery, DiscoveredTool):
        return await integration.store_discovered_tool(discovery, None, vessel_id)
    elif isinstance(discovery, RegisteredTool):
        return await integration.store_registered_tool(discovery, vessel_id)
    elif isinstance(discovery, MonitoredSource):
        return await integration.store_crawl_source(discovery, vessel_id)
    elif isinstance(discovery, CrawlEvent):
        return await integration.store_crawl_event(discovery, vessel_id)
    elif isinstance(discovery, CrawlResult):
        result = await integration.store_crawl_result(discovery, vessel_id)
        return result["apis"] > 0 or result["tools"] > 0
    else:
        logger.warning(f"Unknown discovery type: {type(discovery)}")
        return False
