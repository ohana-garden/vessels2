"""
Tool Registry Schema - FalkorDB index and constraint setup.

This module handles:
1. Creating indexes for efficient queries
2. Creating vector indexes for semantic search
3. Schema verification and migration
4. System initialization

All schema operations use FalkorDB's Cypher dialect.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Schema Definitions (Cypher)
# =============================================================================

# Standard indexes for fast lookups
INDEX_DEFINITIONS = [
    # ToolSource indexes
    "CREATE INDEX IF NOT EXISTS FOR (t:ToolSource) ON (t.id)",
    "CREATE INDEX IF NOT EXISTS FOR (t:ToolSource) ON (t.status)",
    "CREATE INDEX IF NOT EXISTS FOR (t:ToolSource) ON (t.source_type)",
    "CREATE INDEX IF NOT EXISTS FOR (t:ToolSource) ON (t.registry_origin)",

    # Capability indexes
    "CREATE INDEX IF NOT EXISTS FOR (c:Capability) ON (c.id)",
    "CREATE INDEX IF NOT EXISTS FOR (c:Capability) ON (c.domain)",
    "CREATE INDEX IF NOT EXISTS FOR (c:Capability) ON (c.action_type)",

    # Agent indexes
    "CREATE INDEX IF NOT EXISTS FOR (a:Agent) ON (a.id)",
    "CREATE INDEX IF NOT EXISTS FOR (a:Agent) ON (a.name)",
    "CREATE INDEX IF NOT EXISTS FOR (a:Agent) ON (a.status)",

    # ToolOperation indexes
    "CREATE INDEX IF NOT EXISTS FOR (op:ToolOperation) ON (op.id)",
    "CREATE INDEX IF NOT EXISTS FOR (op:ToolOperation) ON (op.tool_source_id)",

    # AuthRequirement indexes
    "CREATE INDEX IF NOT EXISTS FOR (auth:AuthRequirement) ON (auth.id)",
    "CREATE INDEX IF NOT EXISTS FOR (auth:AuthRequirement) ON (auth.tool_source_id)",

    # ApprovalRecord indexes
    "CREATE INDEX IF NOT EXISTS FOR (ar:ApprovalRecord) ON (ar.id)",
    "CREATE INDEX IF NOT EXISTS FOR (ar:ApprovalRecord) ON (ar.tool_source_id)",
    "CREATE INDEX IF NOT EXISTS FOR (ar:ApprovalRecord) ON (ar.decision)",

    # RegistrySource indexes
    "CREATE INDEX IF NOT EXISTS FOR (rs:RegistrySource) ON (rs.id)",

    # SyncRun indexes
    "CREATE INDEX IF NOT EXISTS FOR (sr:SyncRun) ON (sr.id)",
    "CREATE INDEX IF NOT EXISTS FOR (sr:SyncRun) ON (sr.registry_source_id)",
]

# Vector index for semantic search on capabilities
# FalkorDB uses a specific syntax for vector indexes
VECTOR_INDEX_DEFINITION = """
CREATE VECTOR INDEX capability_embedding IF NOT EXISTS
FOR (c:Capability) ON (c.embedding)
OPTIONS {dimension: 1536, similarityFunction: 'cosine'}
"""

# Relationship types used in the schema
RELATIONSHIP_TYPES = [
    # Tool structure
    "HAS_CAPABILITY",      # (:ToolSource)-[:HAS_CAPABILITY]->(:Capability)
    "PROVIDES",            # (:ToolSource)-[:PROVIDES]->(:ToolOperation)
    "REQUIRES_AUTH",       # (:ToolSource)-[:REQUIRES_AUTH]->(:AuthRequirement)
    "DEPENDS_ON",          # (:ToolSource)-[:DEPENDS_ON]->(:ToolSource)
    "APPROVED_BY",         # (:ToolSource)-[:APPROVED_BY]->(:ApprovalRecord)
    "SYNCED_FROM",         # (:ToolSource)-[:SYNCED_FROM]->(:RegistrySource)
    "AWAITING_REVIEW",     # (:ToolSource)-[:AWAITING_REVIEW]->(:Agent)

    # Agent bindings
    "CAN_USE",             # (:Agent)-[:CAN_USE]->(:ToolSource)
    "SPAWNED_BY",          # (:Agent)-[:SPAWNED_BY]->(:Agent)

    # Sync tracking
    "HAD_RUN",             # (:RegistrySource)-[:HAD_RUN]->(:SyncRun)
    "ADDED",               # (:SyncRun)-[:ADDED]->(:ToolSource)
]


# =============================================================================
# Schema Manager
# =============================================================================

class SchemaManager:
    """
    Manages FalkorDB schema for the Tool Registry.

    Handles index creation, verification, and migrations.
    """

    def __init__(self):
        self._driver = None
        self._initialized = False

    async def _get_driver(self):
        """Get the FalkorDB driver from GraphStore."""
        if self._driver is None:
            from python.helpers.graph_store import get_graph_store
            store = await get_graph_store()
            self._driver = store._driver
        return self._driver

    async def initialize_schema(self) -> Dict[str, Any]:
        """
        Initialize the complete Tool Registry schema.

        Returns dict with results of each operation.
        """
        results = {
            "indexes_created": [],
            "indexes_failed": [],
            "vector_index": None,
            "errors": [],
        }

        driver = await self._get_driver()

        # Create standard indexes
        for index_query in INDEX_DEFINITIONS:
            try:
                await driver.execute_query(index_query)
                # Extract index name for reporting
                results["indexes_created"].append(index_query.split("FOR")[0].strip())
            except Exception as e:
                error_msg = str(e)
                # Ignore "already exists" errors
                if "already exists" not in error_msg.lower():
                    results["indexes_failed"].append({"query": index_query, "error": error_msg})
                    results["errors"].append(error_msg)

        # Create vector index (may not be supported in all FalkorDB versions)
        try:
            await driver.execute_query(VECTOR_INDEX_DEFINITION)
            results["vector_index"] = "created"
        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                results["vector_index"] = "exists"
            elif "not supported" in error_msg.lower() or "syntax" in error_msg.lower():
                results["vector_index"] = "not_supported"
                logger.warning("Vector index not supported in this FalkorDB version")
            else:
                results["vector_index"] = "failed"
                results["errors"].append(f"Vector index: {error_msg}")

        self._initialized = True
        logger.info(f"Schema initialization complete: {len(results['indexes_created'])} indexes created")

        return results

    async def verify_schema(self) -> Dict[str, Any]:
        """
        Verify the schema is properly set up.

        Returns dict with verification results.
        """
        results = {
            "indexes_present": [],
            "indexes_missing": [],
            "vector_index_present": False,
            "node_counts": {},
        }

        driver = await self._get_driver()

        # Check for indexes (FalkorDB specific query)
        try:
            index_result = await driver.execute_query("CALL db.indexes()")
            existing_indexes = set()
            for row in index_result or []:
                if isinstance(row, dict):
                    existing_indexes.add(row.get("name", ""))
                elif hasattr(row, "name"):
                    existing_indexes.add(row.name)

            # Check each expected index
            expected_labels = ["ToolSource", "Capability", "Agent", "ToolOperation",
                              "AuthRequirement", "ApprovalRecord", "RegistrySource", "SyncRun"]

            for label in expected_labels:
                # Check if any index exists for this label
                has_index = any(label.lower() in idx.lower() for idx in existing_indexes)
                if has_index:
                    results["indexes_present"].append(label)
                else:
                    results["indexes_missing"].append(label)

            # Check vector index
            results["vector_index_present"] = any("embedding" in idx.lower() for idx in existing_indexes)

        except Exception as e:
            logger.warning(f"Could not verify indexes: {e}")

        # Get node counts
        node_labels = ["ToolSource", "Capability", "Agent", "ToolOperation",
                       "AuthRequirement", "ApprovalRecord", "RegistrySource", "SyncRun"]

        for label in node_labels:
            try:
                count_result = await driver.execute_query(f"MATCH (n:{label}) RETURN count(n) as count")
                if count_result and len(count_result) > 0:
                    results["node_counts"][label] = count_result[0].get("count", 0)
                else:
                    results["node_counts"][label] = 0
            except Exception:
                results["node_counts"][label] = 0

        return results

    async def create_native_nodes(self) -> Dict[str, int]:
        """
        Create native graph nodes from the content-based storage.

        This converts Episode-based storage to native graph nodes
        for better query performance.
        """
        from python.helpers.tool_registry import get_tool_registry

        registry = await get_tool_registry()
        driver = await self._get_driver()
        created = {"tools": 0, "capabilities": 0, "agents": 0, "operations": 0}

        # Get all tool sources and create native nodes
        tools = await registry.list_tool_sources()
        for tool in tools:
            try:
                props = tool.to_dict()
                # Convert to Cypher-safe format
                props_str = ", ".join(f"{k}: ${k}" for k in props.keys() if props[k] is not None)

                query = f"""
                MERGE (t:ToolSource {{id: $id}})
                SET t.name = $name,
                    t.description = $description,
                    t.source_type = $source_type,
                    t.transport = $transport,
                    t.registry_origin = $registry_origin,
                    t.status = $status,
                    t.spec_url = $spec_url,
                    t.base_url = $base_url
                RETURN t
                """

                await driver.execute_query(query, parameters=props)
                created["tools"] += 1

                # Create capability nodes and relationships
                capabilities = await registry.list_capabilities_for_tool(tool.id)
                for cap in capabilities:
                    cap_props = cap.to_dict()
                    cap_query = f"""
                    MERGE (c:Capability {{id: $id}})
                    SET c.name = $name,
                        c.domain = $domain,
                        c.action_type = $action_type,
                        c.description = $description
                    WITH c
                    MATCH (t:ToolSource {{id: $tool_id}})
                    MERGE (t)-[:HAS_CAPABILITY]->(c)
                    RETURN c
                    """
                    cap_props["tool_id"] = tool.id
                    await driver.execute_query(cap_query, parameters=cap_props)
                    created["capabilities"] += 1

                # Create operation nodes
                operations = await registry.list_operations_for_tool(tool.id)
                for op in operations:
                    op_query = """
                    MERGE (o:ToolOperation {id: $id})
                    SET o.name = $name,
                        o.description = $description,
                        o.risk_level = $risk_level
                    WITH o
                    MATCH (t:ToolSource {id: $tool_id})
                    MERGE (t)-[:PROVIDES]->(o)
                    RETURN o
                    """
                    await driver.execute_query(op_query, parameters={
                        "id": op.id,
                        "name": op.name,
                        "description": op.description,
                        "risk_level": op.risk_level.value,
                        "tool_id": tool.id,
                    })
                    created["operations"] += 1

            except Exception as e:
                logger.warning(f"Failed to create native node for {tool.id}: {e}")

        # Create agent nodes
        agents = await registry.list_agents()
        for agent in agents:
            try:
                query = """
                MERGE (a:Agent {id: $id})
                SET a.name = $name,
                    a.model = $model,
                    a.temperature = $temperature,
                    a.status = $status
                RETURN a
                """
                await driver.execute_query(query, parameters={
                    "id": agent.id,
                    "name": agent.name,
                    "model": agent.model,
                    "temperature": agent.temperature,
                    "status": agent.status,
                })
                created["agents"] += 1
            except Exception as e:
                logger.warning(f"Failed to create native node for agent {agent.id}: {e}")

        logger.info(f"Created native nodes: {created}")
        return created


# =============================================================================
# Query Templates for Agents
# =============================================================================

class QueryTemplates:
    """
    Cypher query templates for agent operations.

    These are the graph queries referenced in agent system prompts.
    """

    # SourceAgent queries
    FIND_BY_DOMAIN = """
    MATCH (t:ToolSource)-[:HAS_CAPABILITY]->(c:Capability)
    WHERE c.domain = $domain AND t.status = 'active'
    RETURN DISTINCT t
    """

    FIND_BY_ACTION = """
    MATCH (t:ToolSource)-[:HAS_CAPABILITY]->(c:Capability)
    WHERE c.action_type = $action_type AND t.status = 'active'
    RETURN DISTINCT t
    """

    GET_TOOL_CONFIG = """
    MATCH (t:ToolSource {id: $tool_id})
    OPTIONAL MATCH (t)-[:REQUIRES_AUTH]->(auth:AuthRequirement)
    OPTIONAL MATCH (t)-[:PROVIDES]->(op:ToolOperation)
    OPTIONAL MATCH (t)-[:HAS_CAPABILITY]->(cap:Capability)
    RETURN t,
           collect(DISTINCT auth) as auth_requirements,
           collect(DISTINCT op) as operations,
           collect(DISTINCT cap) as capabilities
    """

    # Semantic search (requires vector index)
    FIND_BY_EMBEDDING = """
    CALL db.idx.vector.queryNodes('capability_embedding', $k, vecf32($embedding))
    YIELD node, score
    MATCH (t:ToolSource)-[:HAS_CAPABILITY]->(node)
    WHERE t.status = 'active'
    RETURN DISTINCT t, score
    ORDER BY score DESC
    LIMIT $limit
    """

    # GuardianAgent queries
    REVIEW_PENDING = """
    MATCH (t:ToolSource {status: 'pending_approval'})
    OPTIONAL MATCH (t)-[:SYNCED_FROM]->(r:RegistrySource)
    OPTIONAL MATCH (t)-[:REQUIRES_AUTH]->(auth:AuthRequirement)
    OPTIONAL MATCH (t)-[:PROVIDES]->(op:ToolOperation)
    OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:ToolSource)
    RETURN t, r,
           collect(DISTINCT auth) as auth_requirements,
           collect(DISTINCT op) as operations,
           collect(DISTINCT dep) as dependencies
    """

    RECORD_DECISION = """
    MATCH (t:ToolSource {id: $tool_id})
    CREATE (ar:ApprovalRecord {
        id: $record_id,
        decision: $decision,
        risk_level: $risk_level,
        reasoning: $reasoning,
        reviewed_at: datetime(),
        guardian_id: 'guardian_agent'
    })
    CREATE (t)-[:APPROVED_BY]->(ar)
    SET t.status = CASE $decision
        WHEN 'approve' THEN 'active'
        WHEN 'deny' THEN 'denied'
        ELSE t.status
    END
    RETURN t, ar
    """

    CHECK_DEPENDENCY_CHAIN = """
    MATCH path = (t:ToolSource {id: $tool_id})-[:DEPENDS_ON*1..5]->(dep:ToolSource)
    WHERE dep.status <> 'active'
    RETURN dep, length(path) as depth
    """

    # SyncAgent queries
    RECORD_SYNC_RUN = """
    CREATE (sr:SyncRun {
        id: $run_id,
        started_at: datetime($started_at),
        completed_at: datetime($completed_at),
        tools_added: $tools_added,
        tools_updated: $tools_updated
    })
    WITH sr
    MATCH (rs:RegistrySource {id: $source_id})
    CREATE (rs)-[:HAD_RUN]->(sr)
    RETURN sr
    """

    LINK_TOOL_TO_SYNC = """
    MATCH (sr:SyncRun {id: $run_id})
    MATCH (t:ToolSource {id: $tool_id})
    CREATE (sr)-[:ADDED]->(t)
    RETURN sr, t
    """

    # Agent relationship queries
    AGENT_CAN_USE = """
    MATCH (a:Agent {id: $agent_id})-[:CAN_USE]->(t:ToolSource)
    RETURN t
    """

    GRANT_TOOL_ACCESS = """
    MATCH (a:Agent {id: $agent_id})
    MATCH (t:ToolSource {id: $tool_id})
    MERGE (a)-[:CAN_USE]->(t)
    RETURN a, t
    """

    # Statistics
    GET_STATISTICS = """
    MATCH (t:ToolSource)
    WITH t.status as status, count(*) as count
    RETURN status, count
    UNION
    MATCH (a:Agent)
    RETURN 'agents' as status, count(*) as count
    UNION
    MATCH (c:Capability)
    RETURN 'capabilities' as status, count(*) as count
    """


# =============================================================================
# Initialization Functions
# =============================================================================

async def initialize_tool_registry_schema() -> Dict[str, Any]:
    """
    Initialize the complete Tool Registry schema in FalkorDB.

    This should be called during system startup.
    """
    manager = SchemaManager()
    return await manager.initialize_schema()


async def verify_tool_registry_schema() -> Dict[str, Any]:
    """
    Verify the Tool Registry schema is properly configured.
    """
    manager = SchemaManager()
    return await manager.verify_schema()


async def create_native_graph_nodes() -> Dict[str, int]:
    """
    Create native graph nodes from Episode-based storage.

    This enables efficient graph traversal queries.
    """
    manager = SchemaManager()
    return await manager.create_native_nodes()


async def full_system_initialization() -> Dict[str, Any]:
    """
    Perform complete system initialization.

    1. Initialize schema (indexes, constraints)
    2. Seed registry sources and core agents
    3. Optionally sync from MCP registry
    4. Create native graph nodes
    5. Verify system
    """
    from python.helpers.tool_registry import get_tool_registry

    results = {
        "schema": {},
        "registry": {},
        "native_nodes": {},
        "verification": {},
    }

    # Step 1: Initialize schema
    logger.info("Initializing Tool Registry schema...")
    results["schema"] = await initialize_tool_registry_schema()

    # Step 2: Initialize registry (seeds core agents and registry sources)
    logger.info("Initializing Tool Registry...")
    registry = await get_tool_registry()
    stats = await registry.get_statistics()
    results["registry"] = stats

    # Step 3: Create native graph nodes
    logger.info("Creating native graph nodes...")
    results["native_nodes"] = await create_native_graph_nodes()

    # Step 4: Verify system
    logger.info("Verifying system...")
    results["verification"] = await registry.verify_system()

    logger.info("Full system initialization complete")
    return results
