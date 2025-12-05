"""
Comprehensive tests for the Tool Registry module.

Tests cover:
- Data models and serialization
- ToolRegistry CRUD operations
- Registry source management
- Capability matching (domain and action)
- Guardian approval workflow
- MCP registry sync (mocked)
- OpenAPI import (mocked)
- Schema initialization
- System verification
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.helpers.tool_registry import (
    # Enums
    ToolSourceType,
    ToolTransport,
    RegistryOrigin,
    ToolStatus,
    ActionType,
    RiskLevel,
    AuthType,
    ApprovalDecision,
    OpenAPIStrategy,
    # Data models
    ToolSource,
    Capability,
    ToolOperation,
    AuthRequirement,
    ApprovalRecord,
    RegistrySource,
    SyncRun,
    AgentNode,
    # Registry class
    ToolRegistry,
    # Convenience functions
    get_tool_registry,
    find_tools_for_task,
    approve_tool,
    deny_tool,
    # Agent prompts
    SOURCE_AGENT_PROMPT,
    GUARDIAN_AGENT_PROMPT,
    SYNC_AGENT_PROMPT,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_graph_store():
    """Create a mock graph store for testing."""
    store = AsyncMock()
    store._content_store: Dict[str, str] = {}

    async def save_content(path: str, content: str, content_type: str = "tool_registry"):
        store._content_store[path] = content

    async def get_content(path: str):
        return store._content_store.get(path)

    async def list_content(content_type: str = None):
        return list(store._content_store.keys())

    async def delete_content(path: str):
        if path in store._content_store:
            del store._content_store[path]
            return True
        return False

    store.save_content = save_content
    store.get_content = get_content
    store.list_content = list_content
    store.delete_content = delete_content

    return store


@pytest.fixture
def sample_tool_source():
    """Create a sample tool source for testing."""
    return ToolSource(
        id="test.filesystem",
        name="Test Filesystem Tool",
        description="A tool for file operations",
        source_type=ToolSourceType.MCP,
        transport=ToolTransport.STDIO,
        registry_origin=RegistryOrigin.OFFICIAL,
        spec_url="https://github.com/test/filesystem",
        status=ToolStatus.ACTIVE,
    )


@pytest.fixture
def sample_capability():
    """Create a sample capability for testing."""
    return Capability(
        id="test.filesystem.read",
        name="file_read",
        domain="filesystem",
        action_type=ActionType.READ,
        description="Read files from the filesystem",
    )


@pytest.fixture
def sample_operation():
    """Create a sample operation for testing."""
    return ToolOperation(
        id="test.filesystem.read_file",
        name="read_file",
        description="Read a file from disk",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        output_schema={"type": "string"},
        risk_level=RiskLevel.LOW,
        tool_source_id="test.filesystem",
    )


@pytest.fixture
def sample_auth_requirement():
    """Create a sample auth requirement for testing."""
    return AuthRequirement(
        id="test.auth.1",
        type=AuthType.API_KEY,
        env_var="TEST_API_KEY",
        scope="read",
        required=True,
        tool_source_id="test.filesystem",
    )


@pytest.fixture
def sample_agent():
    """Create a sample agent for testing."""
    return AgentNode(
        id="test_agent",
        name="Test Agent",
        system_prompt="You are a test agent.",
        model="claude-sonnet-4-20250514",
        temperature=0.3,
        capabilities=["testing"],
    )


# =============================================================================
# Data Model Tests
# =============================================================================

class TestToolSource:
    """Tests for ToolSource data model."""

    def test_tool_source_creation(self, sample_tool_source):
        """Test basic ToolSource creation."""
        assert sample_tool_source.id == "test.filesystem"
        assert sample_tool_source.source_type == ToolSourceType.MCP
        assert sample_tool_source.status == ToolStatus.ACTIVE

    def test_tool_source_to_dict(self, sample_tool_source):
        """Test ToolSource serialization."""
        data = sample_tool_source.to_dict()
        assert data["id"] == "test.filesystem"
        assert data["source_type"] == "mcp"
        assert data["status"] == "active"
        assert "created_at" in data

    def test_tool_source_from_dict(self, sample_tool_source):
        """Test ToolSource deserialization."""
        data = sample_tool_source.to_dict()
        restored = ToolSource.from_dict(data)
        assert restored.id == sample_tool_source.id
        assert restored.source_type == sample_tool_source.source_type
        assert restored.status == sample_tool_source.status


class TestCapability:
    """Tests for Capability data model."""

    def test_capability_creation(self, sample_capability):
        """Test basic Capability creation."""
        assert sample_capability.id == "test.filesystem.read"
        assert sample_capability.domain == "filesystem"
        assert sample_capability.action_type == ActionType.READ

    def test_capability_to_dict(self, sample_capability):
        """Test Capability serialization."""
        data = sample_capability.to_dict()
        assert data["id"] == "test.filesystem.read"
        assert data["domain"] == "filesystem"
        assert data["action_type"] == "read"

    def test_capability_from_dict(self, sample_capability):
        """Test Capability deserialization."""
        data = sample_capability.to_dict()
        restored = Capability.from_dict(data)
        assert restored.id == sample_capability.id
        assert restored.action_type == sample_capability.action_type


class TestToolOperation:
    """Tests for ToolOperation data model."""

    def test_operation_creation(self, sample_operation):
        """Test basic ToolOperation creation."""
        assert sample_operation.id == "test.filesystem.read_file"
        assert sample_operation.risk_level == RiskLevel.LOW

    def test_operation_to_dict(self, sample_operation):
        """Test ToolOperation serialization."""
        data = sample_operation.to_dict()
        assert data["risk_level"] == "low"
        assert "input_schema" in data

    def test_operation_from_dict(self, sample_operation):
        """Test ToolOperation deserialization."""
        data = sample_operation.to_dict()
        restored = ToolOperation.from_dict(data)
        assert restored.risk_level == sample_operation.risk_level


class TestApprovalRecord:
    """Tests for ApprovalRecord data model."""

    def test_approval_record_creation(self):
        """Test ApprovalRecord creation."""
        record = ApprovalRecord(
            id="approval_1",
            decision=ApprovalDecision.APPROVE,
            risk_level=RiskLevel.LOW,
            reasoning="Safe tool",
            tool_source_id="test.tool",
        )
        assert record.decision == ApprovalDecision.APPROVE
        assert record.guardian_id == "guardian_agent"

    def test_approval_record_with_conditions(self):
        """Test ApprovalRecord with conditions."""
        record = ApprovalRecord(
            id="approval_2",
            decision=ApprovalDecision.APPROVE,
            risk_level=RiskLevel.MEDIUM,
            conditions=["Rate limit required", "Audit logging"],
            reasoning="Approved with conditions",
            tool_source_id="test.tool",
        )
        assert len(record.conditions) == 2
        assert "Rate limit required" in record.conditions


class TestAgentNode:
    """Tests for AgentNode data model."""

    def test_agent_node_creation(self, sample_agent):
        """Test AgentNode creation."""
        assert sample_agent.id == "test_agent"
        assert sample_agent.temperature == 0.3
        assert "testing" in sample_agent.capabilities

    def test_agent_node_to_dict(self, sample_agent):
        """Test AgentNode serialization."""
        data = sample_agent.to_dict()
        assert data["model"] == "claude-sonnet-4-20250514"
        assert data["status"] == "active"


# =============================================================================
# Enum Tests
# =============================================================================

class TestEnums:
    """Tests for enum definitions."""

    def test_tool_source_types(self):
        """Test ToolSourceType enum values."""
        assert ToolSourceType.MCP.value == "mcp"
        assert ToolSourceType.OPENAPI.value == "openapi"
        assert ToolSourceType.CUSTOM.value == "custom"

    def test_tool_status_values(self):
        """Test ToolStatus enum values."""
        assert ToolStatus.PENDING_APPROVAL.value == "pending_approval"
        assert ToolStatus.ACTIVE.value == "active"
        assert ToolStatus.DENIED.value == "denied"

    def test_risk_levels(self):
        """Test RiskLevel enum values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_action_types(self):
        """Test ActionType enum values."""
        assert ActionType.READ.value == "read"
        assert ActionType.WRITE.value == "write"
        assert ActionType.DELETE.value == "delete"


# =============================================================================
# Registry Operations Tests (with mocked store)
# =============================================================================

class TestToolRegistryOperations:
    """Tests for ToolRegistry operations with mocked graph store."""

    @pytest.fixture
    async def registry_with_mock(self, mock_graph_store):
        """Create a ToolRegistry instance with mocked store."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True
        return registry

    @pytest.mark.asyncio
    async def test_save_and_get_tool_source(self, registry_with_mock, sample_tool_source):
        """Test saving and retrieving a tool source."""
        registry = await registry_with_mock
        await registry.save_tool_source(sample_tool_source)

        retrieved = await registry.get_tool_source(sample_tool_source.id)
        assert retrieved is not None
        assert retrieved.id == sample_tool_source.id
        assert retrieved.name == sample_tool_source.name

    @pytest.mark.asyncio
    async def test_list_tool_sources(self, registry_with_mock, sample_tool_source):
        """Test listing tool sources."""
        registry = await registry_with_mock
        await registry.save_tool_source(sample_tool_source)

        # Create another tool with different status
        pending_tool = ToolSource(
            id="test.pending",
            name="Pending Tool",
            status=ToolStatus.PENDING_APPROVAL,
        )
        await registry.save_tool_source(pending_tool)

        # List all
        all_tools = await registry.list_tool_sources()
        assert len(all_tools) >= 1

        # List by status
        active_tools = await registry.list_tool_sources(status=ToolStatus.ACTIVE)
        assert all(t.status == ToolStatus.ACTIVE for t in active_tools)

    @pytest.mark.asyncio
    async def test_update_tool_status(self, registry_with_mock, sample_tool_source):
        """Test updating tool status."""
        registry = await registry_with_mock
        sample_tool_source.status = ToolStatus.PENDING_APPROVAL
        await registry.save_tool_source(sample_tool_source)

        success = await registry.update_tool_status(
            sample_tool_source.id,
            ToolStatus.ACTIVE
        )
        assert success is True

        updated = await registry.get_tool_source(sample_tool_source.id)
        assert updated.status == ToolStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_save_and_get_capability(self, registry_with_mock, sample_tool_source, sample_capability):
        """Test saving and retrieving capabilities."""
        registry = await registry_with_mock
        await registry.save_tool_source(sample_tool_source)
        await registry.save_capability(sample_capability, sample_tool_source.id)

        result = await registry.get_capability(sample_capability.id)
        assert result is not None
        cap, tool_id = result
        assert cap.id == sample_capability.id
        assert tool_id == sample_tool_source.id

    @pytest.mark.asyncio
    async def test_list_capabilities_for_tool(self, registry_with_mock, sample_tool_source, sample_capability):
        """Test listing capabilities for a tool."""
        registry = await registry_with_mock
        await registry.save_tool_source(sample_tool_source)
        await registry.save_capability(sample_capability, sample_tool_source.id)

        # Add another capability
        write_cap = Capability(
            id="test.filesystem.write",
            name="file_write",
            domain="filesystem",
            action_type=ActionType.WRITE,
        )
        await registry.save_capability(write_cap, sample_tool_source.id)

        capabilities = await registry.list_capabilities_for_tool(sample_tool_source.id)
        assert len(capabilities) >= 1

    @pytest.mark.asyncio
    async def test_save_and_get_operation(self, registry_with_mock, sample_operation):
        """Test saving and retrieving operations."""
        registry = await registry_with_mock
        await registry.save_operation(sample_operation)

        retrieved = await registry.get_operation(sample_operation.id)
        assert retrieved is not None
        assert retrieved.name == sample_operation.name

    @pytest.mark.asyncio
    async def test_save_agent(self, registry_with_mock, sample_agent):
        """Test saving and retrieving agents."""
        registry = await registry_with_mock
        await registry.save_agent(sample_agent)

        retrieved = await registry.get_agent(sample_agent.id)
        assert retrieved is not None
        assert retrieved.name == sample_agent.name


# =============================================================================
# Capability Matching Tests
# =============================================================================

class TestCapabilityMatching:
    """Tests for capability matching functionality."""

    @pytest.fixture
    async def registry_with_tools(self, mock_graph_store):
        """Create a registry with multiple tools for matching tests."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        # Create filesystem tool
        fs_tool = ToolSource(
            id="mcp.filesystem",
            name="Filesystem",
            description="File operations",
            status=ToolStatus.ACTIVE,
        )
        await registry.save_tool_source(fs_tool)

        fs_cap = Capability(
            id="mcp.filesystem.read",
            name="file_read",
            domain="filesystem",
            action_type=ActionType.READ,
        )
        await registry.save_capability(fs_cap, fs_tool.id)

        # Create database tool
        db_tool = ToolSource(
            id="mcp.database",
            name="Database",
            description="Database operations",
            status=ToolStatus.ACTIVE,
        )
        await registry.save_tool_source(db_tool)

        db_cap = Capability(
            id="mcp.database.query",
            name="db_query",
            domain="database",
            action_type=ActionType.SEARCH,
        )
        await registry.save_capability(db_cap, db_tool.id)

        # Create inactive tool
        inactive_tool = ToolSource(
            id="mcp.inactive",
            name="Inactive Tool",
            status=ToolStatus.DENIED,
        )
        await registry.save_tool_source(inactive_tool)

        inactive_cap = Capability(
            id="mcp.inactive.cap",
            name="inactive_cap",
            domain="filesystem",
            action_type=ActionType.READ,
        )
        await registry.save_capability(inactive_cap, inactive_tool.id)

        return registry

    @pytest.mark.asyncio
    async def test_find_by_domain(self, registry_with_tools):
        """Test finding tools by capability domain."""
        registry = await registry_with_tools

        # Find filesystem tools
        fs_tools = await registry.find_tools_by_domain("filesystem")
        assert len(fs_tools) >= 1
        assert all(t.status == ToolStatus.ACTIVE for t in fs_tools)
        assert any(t.id == "mcp.filesystem" for t in fs_tools)

        # Inactive tool should not be returned
        assert not any(t.id == "mcp.inactive" for t in fs_tools)

    @pytest.mark.asyncio
    async def test_find_by_action(self, registry_with_tools):
        """Test finding tools by action type."""
        registry = await registry_with_tools

        # Find search tools
        search_tools = await registry.find_tools_by_action(ActionType.SEARCH)
        assert len(search_tools) >= 1
        assert all(t.status == ToolStatus.ACTIVE for t in search_tools)

    @pytest.mark.asyncio
    async def test_get_tool_config(self, registry_with_tools):
        """Test getting full tool configuration."""
        registry = await registry_with_tools

        # Add operation and auth to filesystem tool
        op = ToolOperation(
            id="mcp.filesystem.read_file",
            name="read_file",
            risk_level=RiskLevel.LOW,
            tool_source_id="mcp.filesystem",
        )
        await registry.save_operation(op)

        auth = AuthRequirement(
            id="mcp.filesystem.auth",
            type=AuthType.NONE,
            tool_source_id="mcp.filesystem",
        )
        await registry.save_auth_requirement(auth)

        config = await registry.get_tool_config("mcp.filesystem")
        assert config is not None
        assert config["id"] == "mcp.filesystem"
        assert "operations" in config
        assert "capabilities" in config


# =============================================================================
# Guardian Workflow Tests
# =============================================================================

class TestGuardianWorkflow:
    """Tests for Guardian approval workflow."""

    @pytest.fixture
    async def registry_with_pending(self, mock_graph_store):
        """Create a registry with pending tools."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        # Create pending tools
        for i in range(3):
            tool = ToolSource(
                id=f"pending.tool.{i}",
                name=f"Pending Tool {i}",
                status=ToolStatus.PENDING_APPROVAL,
                registry_origin=RegistryOrigin.GITHUB if i > 0 else RegistryOrigin.OFFICIAL,
            )
            await registry.save_tool_source(tool)

            if i == 1:
                # Add auth requirement
                auth = AuthRequirement(
                    id=f"pending.tool.{i}.auth",
                    type=AuthType.API_KEY,
                    env_var="TEST_KEY",
                    required=True,
                    tool_source_id=tool.id,
                )
                await registry.save_auth_requirement(auth)

            if i == 2:
                # Add high risk operation
                op = ToolOperation(
                    id=f"pending.tool.{i}.delete",
                    name="delete_all",
                    risk_level=RiskLevel.HIGH,
                    tool_source_id=tool.id,
                )
                await registry.save_operation(op)

        return registry

    @pytest.mark.asyncio
    async def test_get_pending_tools(self, registry_with_pending):
        """Test getting pending tools for review."""
        registry = await registry_with_pending

        pending = await registry.get_pending_tools()
        assert len(pending) >= 1

        # Check structure
        for item in pending:
            assert "tool" in item
            assert "registry_origin" in item
            assert "auth_requirements" in item
            assert "operations" in item

    @pytest.mark.asyncio
    async def test_auto_approve_official_safe_tool(self, registry_with_pending):
        """Test auto-approval of official safe tools."""
        registry = await registry_with_pending

        # Get the official tool (index 0)
        tool = await registry.get_tool_source("pending.tool.0")
        assert tool.status == ToolStatus.PENDING_APPROVAL

        # Attempt auto-approve
        approved = await registry.auto_approve_tool(tool)
        assert approved is True

        # Verify status changed
        updated = await registry.get_tool_source("pending.tool.0")
        assert updated.status == ToolStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_auto_approve_fails_with_auth(self, registry_with_pending):
        """Test auto-approval fails for tools requiring auth."""
        registry = await registry_with_pending

        # Get the tool with auth (index 1)
        tool = await registry.get_tool_source("pending.tool.1")

        # Attempt auto-approve
        approved = await registry.auto_approve_tool(tool)
        assert approved is False

        # Status should remain pending
        unchanged = await registry.get_tool_source("pending.tool.1")
        assert unchanged.status == ToolStatus.PENDING_APPROVAL

    @pytest.mark.asyncio
    async def test_record_approval_decision(self, registry_with_pending):
        """Test recording approval decision."""
        registry = await registry_with_pending

        record = await registry.record_approval_decision(
            tool_id="pending.tool.1",
            decision=ApprovalDecision.APPROVE,
            risk_level=RiskLevel.MEDIUM,
            reasoning="Approved after manual review",
            conditions=["Rate limit: 100/min"],
        )

        assert record is not None
        assert record.decision == ApprovalDecision.APPROVE
        assert len(record.conditions) == 1

        # Check tool status updated
        tool = await registry.get_tool_source("pending.tool.1")
        assert tool.status == ToolStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_record_denial_decision(self, registry_with_pending):
        """Test recording denial decision."""
        registry = await registry_with_pending

        record = await registry.record_approval_decision(
            tool_id="pending.tool.2",
            decision=ApprovalDecision.DENY,
            risk_level=RiskLevel.HIGH,
            reasoning="High risk operations without justification",
        )

        assert record is not None
        assert record.decision == ApprovalDecision.DENY

        # Check tool status updated
        tool = await registry.get_tool_source("pending.tool.2")
        assert tool.status == ToolStatus.DENIED


# =============================================================================
# Sync Tests (Mocked HTTP)
# =============================================================================

class TestMCPRegistrySync:
    """Tests for MCP registry sync functionality."""

    @pytest.fixture
    def mock_mcp_response(self):
        """Create a mock MCP registry response."""
        return {
            "servers": [
                {
                    "name": "io.anthropic.filesystem",
                    "title": "Filesystem",
                    "description": "Read and write files",
                    "repository": "https://github.com/anthropic/mcp-filesystem",
                    "packages": [
                        {
                            "transport": {"type": "stdio"}
                        }
                    ],
                },
                {
                    "name": "io.anthropic.git",
                    "title": "Git",
                    "description": "Git operations for repositories",
                    "repository": "https://github.com/anthropic/mcp-git",
                    "packages": [
                        {
                            "transport": {"type": "stdio"}
                        }
                    ],
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_sync_creates_tools(self, mock_graph_store, mock_mcp_response):
        """Test that sync creates tool sources."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        # Seed the registry source
        source = RegistrySource(
            id="mcp_official",
            name="MCP Official",
            url="https://registry.modelcontextprotocol.io/v0/servers",
            auto_approve=True,
        )
        await registry.save_registry_source(source)

        # Mock HTTP response
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_mcp_response
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            # Run sync
            run = await registry.sync_mcp_registry("mcp_official")

        assert run is not None
        assert run.tools_added == 2
        assert len(run.errors) == 0

    @pytest.mark.asyncio
    async def test_sync_handles_errors(self, mock_graph_store):
        """Test that sync handles HTTP errors gracefully."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        source = RegistrySource(
            id="mcp_official",
            name="MCP Official",
            url="https://registry.modelcontextprotocol.io/v0/servers",
        )
        await registry.save_registry_source(source)

        # Mock HTTP error
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(side_effect=Exception("Network error"))
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            run = await registry.sync_mcp_registry("mcp_official")

        assert len(run.errors) > 0
        assert "Network error" in run.errors[0]


# =============================================================================
# OpenAPI Import Tests
# =============================================================================

class TestOpenAPIImport:
    """Tests for OpenAPI spec import."""

    @pytest.fixture
    def mock_openapi_spec(self):
        """Create a mock OpenAPI spec."""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": "Test API",
                "description": "A test API for testing",
                "version": "1.0.0",
            },
            "servers": [
                {"url": "https://api.example.com/v1"}
            ],
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "summary": "List all users",
                    },
                    "post": {
                        "operationId": "createUser",
                        "summary": "Create a user",
                    },
                },
                "/users/{id}": {
                    "delete": {
                        "operationId": "deleteUser",
                        "summary": "Delete a user",
                    },
                },
            },
        }

    @pytest.mark.asyncio
    async def test_import_openapi_direct_strategy(self, mock_graph_store, mock_openapi_spec):
        """Test importing OpenAPI with direct strategy."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_openapi_spec
            mock_response.text = json.dumps(mock_openapi_spec)
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            tool = await registry.import_openapi_spec(
                spec_url="https://api.example.com/openapi.json",
                name="test_api",
                strategy=OpenAPIStrategy.DIRECT,
            )

        assert tool is not None
        assert tool.source_type == ToolSourceType.OPENAPI
        assert "api.example.com" in tool.base_url

        # Check operations were created
        operations = await registry.list_operations_for_tool(tool.id)
        assert len(operations) >= 1

    @pytest.mark.asyncio
    async def test_import_openapi_meta_strategy(self, mock_graph_store, mock_openapi_spec):
        """Test importing OpenAPI with meta strategy."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_openapi_spec
            mock_response.text = json.dumps(mock_openapi_spec)
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            tool = await registry.import_openapi_spec(
                spec_url="https://api.example.com/openapi.json",
                name="test_api_meta",
                strategy=OpenAPIStrategy.META,
            )

        assert tool is not None

        # Check meta operations were created
        operations = await registry.list_operations_for_tool(tool.id)
        op_names = [op.name for op in operations]
        assert "list_endpoints" in op_names
        assert "get_schema" in op_names
        assert "invoke" in op_names


# =============================================================================
# Statistics and Verification Tests
# =============================================================================

class TestStatisticsAndVerification:
    """Tests for registry statistics and verification."""

    @pytest.fixture
    async def populated_registry(self, mock_graph_store):
        """Create a populated registry for statistics tests."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        # Create various tools
        for status in [ToolStatus.ACTIVE, ToolStatus.ACTIVE, ToolStatus.PENDING_APPROVAL, ToolStatus.DENIED]:
            tool = ToolSource(
                id=f"tool.{status.value}",
                name=f"Tool {status.value}",
                source_type=ToolSourceType.MCP,
                status=status,
            )
            await registry.save_tool_source(tool)

        # Create agents
        for agent_id in ["source_agent", "guardian_agent", "sync_agent"]:
            agent = AgentNode(
                id=agent_id,
                name=agent_id.replace("_", " ").title(),
                system_prompt=f"You are the {agent_id}",
            )
            await registry.save_agent(agent)

        return registry

    @pytest.mark.asyncio
    async def test_get_statistics(self, populated_registry):
        """Test getting registry statistics."""
        registry = await populated_registry

        stats = await registry.get_statistics()

        assert "total_tools" in stats
        assert "total_agents" in stats
        assert "tools_by_status" in stats
        assert stats["tools_by_status"]["active"] == 2
        assert stats["tools_by_status"]["pending_approval"] == 1
        assert stats["tools_by_status"]["denied"] == 1

    @pytest.mark.asyncio
    async def test_verify_system(self, populated_registry):
        """Test system verification."""
        registry = await populated_registry

        verification = await registry.verify_system()

        assert "tool_sources" in verification
        assert "agents" in verification
        assert "registry_sources" in verification
        assert "pending_count" in verification


# =============================================================================
# Agent Prompt Tests
# =============================================================================

class TestAgentPrompts:
    """Tests for agent system prompts."""

    def test_source_agent_prompt_contains_queries(self):
        """Test SourceAgent prompt contains required queries."""
        assert "FIND_BY_TASK" in SOURCE_AGENT_PROMPT
        assert "FIND_BY_DOMAIN" in SOURCE_AGENT_PROMPT
        assert "GET_TOOL_CONFIG" in SOURCE_AGENT_PROMPT
        assert "REQUEST_APPROVAL" in SOURCE_AGENT_PROMPT

    def test_guardian_agent_prompt_contains_queries(self):
        """Test GuardianAgent prompt contains required queries."""
        assert "REVIEW_PENDING" in GUARDIAN_AGENT_PROMPT
        assert "RECORD_DECISION" in GUARDIAN_AGENT_PROMPT
        assert "CHECK_DEPENDENCY_CHAIN" in GUARDIAN_AGENT_PROMPT
        assert "AUTO_APPROVE" in GUARDIAN_AGENT_PROMPT

    def test_sync_agent_prompt_contains_registry_url(self):
        """Test SyncAgent prompt contains registry URL."""
        assert "registry.modelcontextprotocol.io" in SYNC_AGENT_PROMPT
        assert "MERGE" in SYNC_AGENT_PROMPT


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_find_tools_for_task(self, mock_graph_store):
        """Test find_tools_for_task function."""
        # This test would require full registry initialization
        # For now, test the function exists and accepts correct parameters
        with patch("python.helpers.tool_registry.ToolRegistry.get_instance") as mock_get:
            mock_registry = AsyncMock()
            mock_registry.find_tools_by_domain = AsyncMock(return_value=[])
            mock_registry.get_tool_config = AsyncMock(return_value=None)
            mock_get.return_value = mock_registry

            results = await find_tools_for_task("read a file from disk")
            assert isinstance(results, list)


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_tool(self, mock_graph_store):
        """Test getting a non-existent tool returns None."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        result = await registry.get_tool_source("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_status_nonexistent_tool(self, mock_graph_store):
        """Test updating status of non-existent tool returns False."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        result = await registry.update_tool_status("nonexistent", ToolStatus.ACTIVE)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_domain_search(self, mock_graph_store):
        """Test searching for tools in non-existent domain."""
        registry = ToolRegistry()
        registry._store = mock_graph_store
        registry._initialized = True

        results = await registry.find_tools_by_domain("nonexistent_domain")
        assert results == []

    def test_tool_source_with_minimal_fields(self):
        """Test ToolSource with only required fields."""
        tool = ToolSource(id="minimal", name="Minimal Tool")
        assert tool.source_type == ToolSourceType.MCP
        assert tool.status == ToolStatus.PENDING_APPROVAL
        assert tool.transport == ToolTransport.STDIO


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
