"""
Guardians - Input sanitization and validation for all data sources.

All external data flows through guardians before entering the agent system.
Guardians detect, neutralize, and log potential security threats.

Usage:
    from python.helpers.guardians import guard, GuardianType

    # Sanitize web content
    safe_content = guard(raw_html, GuardianType.WEB)

    # Sanitize file content
    safe_file = guard(file_data, GuardianType.FILE)

    # Sanitize with context for logging
    safe_input = guard(user_msg, GuardianType.INPUT, source="api_endpoint")
"""

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional, Callable
from datetime import datetime


# =============================================================================
# Configuration
# =============================================================================

class GuardianType(Enum):
    """Types of guardians for different data sources."""
    INPUT = auto()      # User/agent messages
    WEB = auto()        # Web scrapes, API responses
    FILE = auto()       # File system reads
    MEMORY = auto()     # Database/memory retrieval
    TOOL = auto()       # Tool execution outputs
    AGENT = auto()      # Agent-to-agent communication


@dataclass
class ThreatDetection:
    """Record of a detected threat."""
    threat_type: str
    pattern_matched: str
    original_content: str
    sanitized_content: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    severity: str = "medium"  # low, medium, high, critical


@dataclass
class GuardianResult:
    """Result of guardian processing."""
    content: Any
    was_modified: bool = False
    threats_detected: list[ThreatDetection] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.threats_detected) == 0


# =============================================================================
# Threat Patterns
# =============================================================================

# Template injection patterns
TEMPLATE_INJECTION_PATTERNS = [
    (r"\{\{.*?\}\}", "template_delimiter"),
    (r"\{%.*?%\}", "jinja_block"),
    (r"\$\{.*?\}", "shell_expansion"),
    (r"`[^`]+`", "backtick_execution"),
]

# Prompt injection patterns - attempts to override system instructions
PROMPT_INJECTION_PATTERNS = [
    (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)", "instruction_override"),
    (r"disregard\s+(all\s+)?(previous|above|prior)", "instruction_override"),
    (r"forget\s+(everything|all|your)\s+(above|previous|prior)?", "memory_wipe"),
    (r"you\s+are\s+now\s+(a|an|in)\s+", "role_injection"),
    (r"new\s+instructions?:", "new_instruction"),
    (r"system\s*:\s*", "system_role_injection"),
    (r"<\s*system\s*>", "xml_system_tag"),
    (r"\[\s*SYSTEM\s*\]", "bracket_system_tag"),
    (r"act\s+as\s+(if\s+)?(you\s+)?(are|were)", "role_play_injection"),
    (r"pretend\s+(that\s+)?(you\s+)?(are|were)", "role_play_injection"),
]

# Data exfiltration patterns
EXFILTRATION_PATTERNS = [
    (r"(show|reveal|display|print|output)\s+(me\s+)?(the\s+)?(system\s+)?(prompt|instructions?)", "prompt_extraction"),
    (r"(what|tell)\s+(are|me)\s+(your|the)\s+(system\s+)?(instructions?|rules?|prompt)", "prompt_extraction"),
    (r"repeat\s+(back\s+)?(your\s+)?(system\s+)?(prompt|instructions?)", "prompt_extraction"),
    (r"(api[_\s]?key|password|secret|token|credential)s?\s*[:=]", "credential_probe"),
]

# Code injection patterns
CODE_INJECTION_PATTERNS = [
    (r";\s*(rm|del|drop|truncate|delete)\s+", "destructive_command"),
    (r"(exec|eval|compile)\s*\(", "code_execution"),
    (r"__import__\s*\(", "python_import_injection"),
    (r"subprocess\.(run|call|Popen)", "subprocess_injection"),
    (r"os\.(system|popen|exec)", "os_command_injection"),
]

# Control character patterns
CONTROL_CHAR_PATTERNS = [
    (r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "control_characters"),
    (r"\x1b\[[\d;]*[a-zA-Z]", "ansi_escape"),
    (r"[\u2028\u2029]", "unicode_line_separator"),
    (r"[\u200b-\u200f\u2060-\u206f]", "unicode_format_char"),  # Except our own escapes
]


# =============================================================================
# Base Guardian
# =============================================================================

class Guardian(ABC):
    """Base class for all guardians."""

    def __init__(self, log_threats: bool = True):
        self.log_threats = log_threats
        self.logger = logging.getLogger(f"guardian.{self.__class__.__name__}")

    @abstractmethod
    def sanitize(self, content: Any, source: str = "unknown") -> GuardianResult:
        """Sanitize content and return result with any threats detected."""
        pass

    def _escape_template_delimiters(self, text: str) -> str:
        """Escape template delimiters using zero-width space."""
        if not isinstance(text, str):
            return text
        return text.replace("{{", "{\u200b{").replace("}}", "}\u200b}")

    def _detect_patterns(
        self,
        text: str,
        patterns: list[tuple[str, str]],
        source: str,
        case_insensitive: bool = True
    ) -> list[ThreatDetection]:
        """Detect threats matching given patterns."""
        threats = []
        flags = re.IGNORECASE if case_insensitive else 0

        for pattern, threat_type in patterns:
            matches = re.finditer(pattern, text, flags)
            for match in matches:
                threats.append(ThreatDetection(
                    threat_type=threat_type,
                    pattern_matched=pattern,
                    original_content=match.group(0)[:100],  # Truncate for logging
                    sanitized_content="[REDACTED]",
                    source=source,
                    severity=self._get_severity(threat_type)
                ))

        return threats

    def _get_severity(self, threat_type: str) -> str:
        """Map threat types to severity levels."""
        critical = {"instruction_override", "system_role_injection", "destructive_command"}
        high = {"role_injection", "code_execution", "credential_probe", "prompt_extraction"}
        medium = {"template_delimiter", "new_instruction", "role_play_injection"}

        if threat_type in critical:
            return "critical"
        elif threat_type in high:
            return "high"
        elif threat_type in medium:
            return "medium"
        return "low"

    def _log_threat(self, threat: ThreatDetection):
        """Log detected threat."""
        if self.log_threats:
            self.logger.warning(
                f"[{threat.severity.upper()}] {threat.threat_type} detected "
                f"from {threat.source}: {threat.original_content[:50]}..."
            )


# =============================================================================
# Specific Guardians
# =============================================================================

class InputGuardian(Guardian):
    """Guardian for user/agent input messages."""

    def sanitize(self, content: Any, source: str = "user_input") -> GuardianResult:
        if not isinstance(content, str):
            return GuardianResult(content=content)

        threats = []
        modified = False
        result = content

        # Detect prompt injection attempts
        threats.extend(self._detect_patterns(content, PROMPT_INJECTION_PATTERNS, source))

        # Detect exfiltration attempts
        threats.extend(self._detect_patterns(content, EXFILTRATION_PATTERNS, source))

        # Detect template injection
        template_threats = self._detect_patterns(content, TEMPLATE_INJECTION_PATTERNS, source)
        if template_threats:
            threats.extend(template_threats)
            result = self._escape_template_delimiters(result)
            modified = True

        # Log threats
        for threat in threats:
            self._log_threat(threat)

        return GuardianResult(content=result, was_modified=modified, threats_detected=threats)


class WebGuardian(Guardian):
    """Guardian for web scrapes and API responses."""

    def sanitize(self, content: Any, source: str = "web") -> GuardianResult:
        if not isinstance(content, str):
            return GuardianResult(content=content)

        threats = []
        modified = False
        result = content

        # Detect all injection patterns (web content is high risk)
        threats.extend(self._detect_patterns(content, TEMPLATE_INJECTION_PATTERNS, source))
        threats.extend(self._detect_patterns(content, PROMPT_INJECTION_PATTERNS, source))
        threats.extend(self._detect_patterns(content, CODE_INJECTION_PATTERNS, source))

        # Detect control characters
        threats.extend(self._detect_patterns(content, CONTROL_CHAR_PATTERNS, source, case_insensitive=False))

        # Always escape template delimiters from web content
        result = self._escape_template_delimiters(result)

        # Remove ANSI escapes FIRST (before stripping escape char)
        result = re.sub(r"\x1b\[[\d;]*[a-zA-Z]", "", result)
        result = re.sub(r"\x1b\[[^\x1b]*", "", result)
        # Then remove remaining dangerous control characters (keep newlines, tabs)
        result = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x1b]", "", result)

        if result != content:
            modified = True

        for threat in threats:
            self._log_threat(threat)

        return GuardianResult(content=result, was_modified=modified, threats_detected=threats)


class FileGuardian(Guardian):
    """Guardian for file system content."""

    def sanitize(self, content: Any, source: str = "file") -> GuardianResult:
        if not isinstance(content, str):
            return GuardianResult(content=content)

        threats = []
        modified = False
        result = content

        # Detect template injection
        template_threats = self._detect_patterns(content, TEMPLATE_INJECTION_PATTERNS, source)
        if template_threats:
            threats.extend(template_threats)
            result = self._escape_template_delimiters(result)
            modified = True

        # Detect code injection in files
        threats.extend(self._detect_patterns(content, CODE_INJECTION_PATTERNS, source))

        for threat in threats:
            self._log_threat(threat)

        return GuardianResult(content=result, was_modified=modified, threats_detected=threats)


class MemoryGuardian(Guardian):
    """Guardian for database/memory retrieval."""

    def sanitize(self, content: Any, source: str = "memory") -> GuardianResult:
        if not isinstance(content, str):
            # Handle dict/list from DB
            if isinstance(content, dict):
                return self._sanitize_dict(content, source)
            elif isinstance(content, list):
                return self._sanitize_list(content, source)
            return GuardianResult(content=content)

        threats = []
        modified = False
        result = content

        # Memory could contain previously stored malicious content
        threats.extend(self._detect_patterns(content, TEMPLATE_INJECTION_PATTERNS, source))
        threats.extend(self._detect_patterns(content, PROMPT_INJECTION_PATTERNS, source))

        # Escape templates
        result = self._escape_template_delimiters(result)
        if result != content:
            modified = True

        for threat in threats:
            self._log_threat(threat)

        return GuardianResult(content=result, was_modified=modified, threats_detected=threats)

    def _sanitize_dict(self, d: dict, source: str) -> GuardianResult:
        """Recursively sanitize dictionary values."""
        result = {}
        all_threats = []
        any_modified = False

        for k, v in d.items():
            if isinstance(v, str):
                sub_result = self.sanitize(v, source)
                result[k] = sub_result.content
                all_threats.extend(sub_result.threats_detected)
                any_modified = any_modified or sub_result.was_modified
            elif isinstance(v, dict):
                sub_result = self._sanitize_dict(v, source)
                result[k] = sub_result.content
                all_threats.extend(sub_result.threats_detected)
                any_modified = any_modified or sub_result.was_modified
            elif isinstance(v, list):
                sub_result = self._sanitize_list(v, source)
                result[k] = sub_result.content
                all_threats.extend(sub_result.threats_detected)
                any_modified = any_modified or sub_result.was_modified
            else:
                result[k] = v

        return GuardianResult(content=result, was_modified=any_modified, threats_detected=all_threats)

    def _sanitize_list(self, lst: list, source: str) -> GuardianResult:
        """Recursively sanitize list items."""
        result = []
        all_threats = []
        any_modified = False

        for item in lst:
            if isinstance(item, str):
                sub_result = self.sanitize(item, source)
                result.append(sub_result.content)
                all_threats.extend(sub_result.threats_detected)
                any_modified = any_modified or sub_result.was_modified
            elif isinstance(item, dict):
                sub_result = self._sanitize_dict(item, source)
                result.append(sub_result.content)
                all_threats.extend(sub_result.threats_detected)
                any_modified = any_modified or sub_result.was_modified
            elif isinstance(item, list):
                sub_result = self._sanitize_list(item, source)
                result.append(sub_result.content)
                all_threats.extend(sub_result.threats_detected)
                any_modified = any_modified or sub_result.was_modified
            else:
                result.append(item)

        return GuardianResult(content=result, was_modified=any_modified, threats_detected=all_threats)


class ToolOutputGuardian(Guardian):
    """Guardian for tool execution outputs."""

    def sanitize(self, content: Any, source: str = "tool") -> GuardianResult:
        if not isinstance(content, str):
            if isinstance(content, dict):
                return MemoryGuardian().sanitize(content, source)
            elif isinstance(content, list):
                return MemoryGuardian().sanitize(content, source)
            return GuardianResult(content=content)

        threats = []
        modified = False
        result = content

        # Tool output is medium risk - could come from external sources
        threats.extend(self._detect_patterns(content, TEMPLATE_INJECTION_PATTERNS, source))
        threats.extend(self._detect_patterns(content, PROMPT_INJECTION_PATTERNS, source))

        # Escape templates
        result = self._escape_template_delimiters(result)
        if result != content:
            modified = True

        for threat in threats:
            self._log_threat(threat)

        return GuardianResult(content=result, was_modified=modified, threats_detected=threats)


class AgentGuardian(Guardian):
    """Guardian for agent-to-agent communication."""

    def sanitize(self, content: Any, source: str = "agent") -> GuardianResult:
        if not isinstance(content, str):
            return GuardianResult(content=content)

        threats = []
        modified = False
        result = content

        # Agent output could propagate injections
        threats.extend(self._detect_patterns(content, TEMPLATE_INJECTION_PATTERNS, source))

        # Less strict on prompt injection for agents (they may legitimately discuss instructions)
        # But still detect critical patterns
        critical_patterns = [p for p in PROMPT_INJECTION_PATTERNS
                          if p[1] in ("instruction_override", "system_role_injection")]
        threats.extend(self._detect_patterns(content, critical_patterns, source))

        # Escape templates
        result = self._escape_template_delimiters(result)
        if result != content:
            modified = True

        for threat in threats:
            self._log_threat(threat)

        return GuardianResult(content=result, was_modified=modified, threats_detected=threats)


# =============================================================================
# Guardian Registry and Main Interface
# =============================================================================

_GUARDIANS: dict[GuardianType, Guardian] = {
    GuardianType.INPUT: InputGuardian(),
    GuardianType.WEB: WebGuardian(),
    GuardianType.FILE: FileGuardian(),
    GuardianType.MEMORY: MemoryGuardian(),
    GuardianType.TOOL: ToolOutputGuardian(),
    GuardianType.AGENT: AgentGuardian(),
}


def guard(content: Any, guardian_type: GuardianType, source: str = "unknown") -> Any:
    """
    Main entry point - sanitize content through appropriate guardian.

    Args:
        content: The content to sanitize
        guardian_type: Type of guardian to use
        source: Source identifier for logging

    Returns:
        Sanitized content (same type as input)
    """
    guardian = _GUARDIANS.get(guardian_type)
    if guardian is None:
        return content

    result = guardian.sanitize(content, source)
    return result.content


def guard_with_result(content: Any, guardian_type: GuardianType, source: str = "unknown") -> GuardianResult:
    """
    Sanitize content and return full result with threat details.

    Use this when you need to inspect what threats were detected.
    """
    guardian = _GUARDIANS.get(guardian_type)
    if guardian is None:
        return GuardianResult(content=content)

    return guardian.sanitize(content, source)


def register_guardian(guardian_type: GuardianType, guardian: Guardian):
    """Register a custom guardian for a type."""
    _GUARDIANS[guardian_type] = guardian


def get_guardian(guardian_type: GuardianType) -> Optional[Guardian]:
    """Get the guardian instance for a type."""
    return _GUARDIANS.get(guardian_type)


# =============================================================================
# Convenience Functions
# =============================================================================

def guard_input(content: str, source: str = "user") -> str:
    """Shorthand for guarding user input."""
    return guard(content, GuardianType.INPUT, source)


def guard_web(content: str, source: str = "web") -> str:
    """Shorthand for guarding web content."""
    return guard(content, GuardianType.WEB, source)


def guard_file(content: str, source: str = "file") -> str:
    """Shorthand for guarding file content."""
    return guard(content, GuardianType.FILE, source)


def guard_memory(content: Any, source: str = "memory") -> Any:
    """Shorthand for guarding memory/database content."""
    return guard(content, GuardianType.MEMORY, source)


def guard_tool(content: Any, source: str = "tool") -> Any:
    """Shorthand for guarding tool output."""
    return guard(content, GuardianType.TOOL, source)


def guard_agent(content: str, source: str = "agent") -> str:
    """Shorthand for guarding agent communication."""
    return guard(content, GuardianType.AGENT, source)
