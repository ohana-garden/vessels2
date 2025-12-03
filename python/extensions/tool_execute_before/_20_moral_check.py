"""
Moral Check Extension - Pre-execution moral evaluation

Evaluates the moral implications of tool calls before execution,
providing early warning for ethically significant actions.
"""

from typing import Any
from python.helpers.extension import Extension
from python.helpers.tool import Tool


# Tools that may have significant moral implications
MORALLY_SIGNIFICANT_TOOLS = {
    "code_execution_tool": ["shell", "python"],  # Code execution
    "browser_agent": [],  # Web actions
    "financial": [],  # Financial operations
    "call_subordinate": [],  # Delegation
    "scheduler": [],  # Scheduled actions
    "notify_user": [],  # User communication
}

# Actions that warrant moral attention
MORAL_ATTENTION_KEYWORDS = [
    "delete", "remove", "destroy", "terminate", "kill",
    "send", "post", "publish", "share", "transmit",
    "modify", "change", "alter", "update", "overwrite",
    "access", "read", "retrieve", "fetch", "download",
    "create", "generate", "produce", "build",
    "money", "payment", "transfer", "transaction",
    "user", "person", "people", "human", "customer",
    "private", "secret", "confidential", "sensitive",
]


class MoralCheck(Extension):
    """Extension to check moral implications before tool execution."""

    async def execute(
        self,
        tool: Tool = None,
        **kwargs: Any
    ):
        """
        Evaluate moral implications before tool execution.

        This extension:
        1. Checks if the tool is morally significant
        2. Evaluates the action's moral dimensions
        3. Logs moral considerations for awareness
        """
        if tool is None:
            return

        # Check if this tool warrants moral evaluation
        if not self._is_morally_significant(tool):
            return

        # Evaluate moral dimensions (lightweight check)
        moral_score = self._quick_moral_eval(tool)

        # If significant moral implications, log for awareness
        if moral_score["significance"] > 0.5:
            self._log_moral_awareness(tool, moral_score)

    def _is_morally_significant(self, tool: Tool) -> bool:
        """Check if the tool has potential moral significance."""
        tool_name = tool.name.lower()

        # Check against known significant tools
        if tool_name in MORALLY_SIGNIFICANT_TOOLS:
            methods = MORALLY_SIGNIFICANT_TOOLS[tool_name]
            if not methods or (tool.method and tool.method in methods):
                return True

        # Check arguments for attention keywords
        if tool.args:
            args_str = str(tool.args).lower()
            for keyword in MORAL_ATTENTION_KEYWORDS:
                if keyword in args_str:
                    return True

        return False

    def _quick_moral_eval(self, tool: Tool) -> dict:
        """
        Quick moral evaluation of tool call.

        Returns dict with significance score and dimensions affected.
        """
        score = {
            "significance": 0.0,
            "dimensions": [],
            "warnings": [],
        }

        args_str = str(tool.args).lower() if tool.args else ""
        message_str = tool.message.lower() if tool.message else ""
        combined = f"{args_str} {message_str}"

        # Check for harm potential
        harm_words = ["delete", "remove", "destroy", "kill", "terminate"]
        if any(w in combined for w in harm_words):
            score["significance"] += 0.3
            score["dimensions"].append("harm_benefit")
            score["warnings"].append("Potentially destructive action")

        # Check for autonomy implications
        autonomy_words = ["force", "require", "mandate", "compel"]
        if any(w in combined for w in autonomy_words):
            score["significance"] += 0.2
            score["dimensions"].append("autonomy")
            score["warnings"].append("May affect autonomy")

        # Check for privacy/truth implications
        privacy_words = ["private", "secret", "confidential", "personal"]
        if any(w in combined for w in privacy_words):
            score["significance"] += 0.3
            score["dimensions"].append("truth")
            score["dimensions"].append("sanctity")
            score["warnings"].append("Privacy-sensitive data involved")

        # Check for financial implications
        financial_words = ["money", "payment", "transfer", "transaction", "fund"]
        if any(w in combined for w in financial_words):
            score["significance"] += 0.4
            score["dimensions"].append("justice")
            score["dimensions"].append("fidelity")
            score["warnings"].append("Financial action")

        # Check for user impact
        user_words = ["user", "person", "people", "customer", "human"]
        if any(w in combined for w in user_words):
            score["significance"] += 0.2
            score["dimensions"].append("compassion")
            score["warnings"].append("Affects people directly")

        # Cap significance at 1.0
        score["significance"] = min(1.0, score["significance"])

        return score

    def _log_moral_awareness(self, tool: Tool, moral_score: dict) -> None:
        """Log moral considerations for awareness."""
        if not self.agent or not self.agent.context:
            return

        dimensions = ", ".join(set(moral_score["dimensions"]))
        warnings = "; ".join(moral_score["warnings"])

        # Store moral awareness in agent data for reference
        moral_log = self.agent.get_data("moral_awareness_log") or []
        moral_log.append({
            "tool": tool.name,
            "method": tool.method,
            "significance": moral_score["significance"],
            "dimensions": moral_score["dimensions"],
            "warnings": moral_score["warnings"],
        })
        self.agent.set_data("moral_awareness_log", moral_log[-100:])  # Keep last 100

        # Log to context if significance is high
        if moral_score["significance"] > 0.7:
            from python.helpers.print_style import PrintStyle
            PrintStyle(font_color="#FFD700", bold=True).print(
                f"[Moral Awareness] {tool.name}: {warnings} (dims: {dimensions})"
            )
