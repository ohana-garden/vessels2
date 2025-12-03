"""Unit tests for stuck session detection and recovery."""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock
import models
from agent import AgentContext, AgentConfig


def create_test_config():
    """Create a minimal config for testing."""
    return AgentConfig(
        chat_model=models.ModelConfig(
            type=models.ModelType.CHAT,
            provider="test",
            name="test-model",
        ),
        utility_model=models.ModelConfig(
            type=models.ModelType.CHAT,
            provider="test",
            name="test-model",
        ),
        embeddings_model=models.ModelConfig(
            type=models.ModelType.EMBEDDING,
            provider="test",
            name="test-model",
        ),
        browser_model=models.ModelConfig(
            type=models.ModelType.CHAT,
            provider="test",
            name="test-model",
        ),
        mcp_servers="",
    )


def test_is_stuck_healthy_session():
    """Test that a normal session is not detected as stuck."""
    config = create_test_config()
    context = AgentContext(config=config, id="test_healthy")

    # Fresh context with no task should be healthy
    result = context.is_stuck()
    assert not result["stuck"], f"Expected healthy but got: {result['reason']}"
    assert result["reason"] == "healthy"

    # Cleanup
    AgentContext.remove("test_healthy")
    print("✓ test_is_stuck_healthy_session passed")


def test_is_stuck_paused_no_task():
    """Test stuck detection when paused but no active task."""
    config = create_test_config()
    context = AgentContext(config=config, id="test_paused_no_task")
    context.paused = True

    result = context.is_stuck()
    assert result["stuck"], "Should be stuck when paused with no task"
    assert "paused but no active task" in result["reason"]

    # Cleanup
    AgentContext.remove("test_paused_no_task")
    print("✓ test_is_stuck_paused_no_task passed")


def test_is_stuck_streaming_agent_dead_task():
    """Test stuck detection when streaming_agent set but task is dead."""
    config = create_test_config()
    context = AgentContext(config=config, id="test_streaming_dead")

    # Simulate a dead task with streaming_agent still set
    mock_task = Mock()
    mock_task.is_alive.return_value = False
    context.task = mock_task
    context.streaming_agent = context.agent0  # Still set

    result = context.is_stuck()
    assert result["stuck"], "Should be stuck when streaming_agent set but task dead"
    assert "streaming_agent set but task is dead" in result["reason"]

    # Cleanup
    AgentContext.remove("test_streaming_dead")
    print("✓ test_is_stuck_streaming_agent_dead_task passed")


def test_is_stuck_stale_activity():
    """Test stuck detection when no activity for too long."""
    config = create_test_config()
    context = AgentContext(config=config, id="test_stale")

    # Simulate an active task with old last_message
    mock_task = Mock()
    mock_task.is_alive.return_value = True
    context.task = mock_task
    context.last_message = datetime.now(timezone.utc) - timedelta(seconds=120)

    result = context.is_stuck(stale_threshold_seconds=60.0)
    assert result["stuck"], "Should be stuck when no activity for 120s"
    assert "no activity for" in result["reason"]

    # Cleanup
    AgentContext.remove("test_stale")
    print("✓ test_is_stuck_stale_activity passed")


def test_nudge_resets_streaming_agent():
    """Test that nudge() properly resets streaming_agent."""
    config = create_test_config()
    context = AgentContext(config=config, id="test_nudge_reset")

    # Set up a stuck state
    context.streaming_agent = context.agent0
    context.paused = True

    # Create a mock task
    mock_task = Mock()
    mock_task.kill = Mock()
    context.task = mock_task

    # Mock run_task to avoid actually starting a task
    original_run_task = context.run_task
    context.run_task = Mock(return_value=Mock())

    # Nudge should reset everything
    context.nudge()

    assert context.streaming_agent is None, "nudge() should reset streaming_agent"
    assert context.paused is False, "nudge() should unpause"
    mock_task.kill.assert_called_once()

    # Cleanup
    AgentContext.remove("test_nudge_reset")
    print("✓ test_nudge_resets_streaming_agent passed")


def test_output_includes_stuck_info():
    """Test that output() includes stuck status information."""
    config = create_test_config()
    context = AgentContext(config=config, id="test_output_stuck")

    output = context.output()

    assert "stuck" in output, "output() should include 'stuck' field"
    assert "stuck_reason" in output, "output() should include 'stuck_reason' field"
    assert "task_alive" in output, "output() should include 'task_alive' field"

    # Cleanup
    AgentContext.remove("test_output_stuck")
    print("✓ test_output_includes_stuck_info passed")


if __name__ == "__main__":
    print("\nRunning stuck session tests...\n")
    test_is_stuck_healthy_session()
    test_is_stuck_paused_no_task()
    test_is_stuck_streaming_agent_dead_task()
    test_is_stuck_stale_activity()
    test_nudge_resets_streaming_agent()
    test_output_includes_stuck_info()
    print("\n✓ All tests passed!")
