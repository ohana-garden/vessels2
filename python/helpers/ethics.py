"""
Ethical Principles Framework for Vessels A0 Framework

This module implements a comprehensive ethical framework that validates all agent
actions, inputs, and outputs against a constitutional set of principles.

The framework follows a Constitutional AI approach where:
1. A constitution defines core ethical principles
2. Every action is validated against these principles
3. Violations are logged and can block or modify actions
4. All ethical decisions are recorded in collective memory
"""

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Module logger
logger = logging.getLogger(__name__)


class EthicalPrinciple(Enum):
    """Core ethical principles that govern all agent behavior."""

    # Safety Principles
    HARM_PREVENTION = "harm_prevention"
    HUMAN_OVERSIGHT = "human_oversight"
    FAIL_SAFE = "fail_safe"

    # Transparency Principles
    HONESTY = "honesty"
    EXPLAINABILITY = "explainability"
    AUDITABILITY = "auditability"

    # Privacy Principles
    DATA_MINIMIZATION = "data_minimization"
    CONSENT_RESPECT = "consent_respect"
    CONFIDENTIALITY = "confidentiality"

    # Fairness Principles
    NON_DISCRIMINATION = "non_discrimination"
    EQUAL_ACCESS = "equal_access"
    IMPARTIALITY = "impartiality"

    # Accountability Principles
    RESPONSIBILITY = "responsibility"
    TRACEABILITY = "traceability"
    CORRECTIVE_ACTION = "corrective_action"

    # Autonomy Principles
    HUMAN_AGENCY = "human_agency"
    INFORMED_CHOICE = "informed_choice"
    REVERSIBILITY = "reversibility"


class ValidationResult(Enum):
    """Result of an ethical validation check."""
    APPROVED = "approved"
    MODIFIED = "modified"
    BLOCKED = "blocked"
    WARNING = "warning"
    REQUIRES_REVIEW = "requires_review"


class Severity(Enum):
    """Severity level of an ethical violation."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EthicalViolation:
    """Represents a detected ethical violation."""
    principle: EthicalPrinciple
    severity: Severity
    description: str
    context: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    remediation: Optional[str] = None
    violation_id: Optional[str] = None

    def __post_init__(self):
        if not self.violation_id:
            # Generate unique ID for this violation
            content = f"{self.principle.value}:{self.description}:{self.timestamp.isoformat()}"
            self.violation_id = hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "principle": self.principle.value,
            "severity": self.severity.value,
            "description": self.description,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "remediation": self.remediation
        }


@dataclass
class EthicalValidation:
    """Result of an ethical validation operation."""
    result: ValidationResult
    violations: List[EthicalViolation] = field(default_factory=list)
    modifications: Dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    validated_at: datetime = field(default_factory=datetime.now)
    validator_name: str = ""

    @property
    def is_approved(self) -> bool:
        return self.result in (ValidationResult.APPROVED, ValidationResult.WARNING)

    @property
    def is_blocked(self) -> bool:
        return self.result == ValidationResult.BLOCKED

    @property
    def requires_modification(self) -> bool:
        return self.result == ValidationResult.MODIFIED and bool(self.modifications)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value,
            "violations": [v.to_dict() for v in self.violations],
            "modifications": self.modifications,
            "explanation": self.explanation,
            "validated_at": self.validated_at.isoformat(),
            "validator_name": self.validator_name
        }


class EthicalValidator(ABC):
    """Abstract base class for ethical validators."""

    def __init__(self, name: str, principles: List[EthicalPrinciple]):
        self.name = name
        self.principles = principles
        self.enabled = True

    @abstractmethod
    async def validate(self, action_type: str, data: Dict[str, Any], context: Dict[str, Any]) -> EthicalValidation:
        """Validate an action against ethical principles."""
        pass

    def covers_principle(self, principle: EthicalPrinciple) -> bool:
        """Check if this validator covers a specific principle."""
        return principle in self.principles


class HarmPreventionValidator(EthicalValidator):
    """Validates actions for potential harm prevention violations."""

    # Patterns that may indicate harmful content
    HARMFUL_PATTERNS = [
        "weapon", "explosive", "poison", "malware", "ransomware",
        "ddos", "attack", "exploit", "vulnerability", "hack into",
        "steal", "fraud", "impersonate", "blackmail", "extort"
    ]

    # Patterns that indicate harmful intent toward specific targets
    TARGETED_HARM_PATTERNS = [
        "kill", "hurt", "harm", "attack", "destroy", "damage"
    ]

    def __init__(self):
        super().__init__(
            name="HarmPreventionValidator",
            principles=[EthicalPrinciple.HARM_PREVENTION, EthicalPrinciple.FAIL_SAFE]
        )

    async def validate(self, action_type: str, data: Dict[str, Any], context: Dict[str, Any]) -> EthicalValidation:
        violations = []

        # Extract text content to analyze
        content = self._extract_content(data)
        content_lower = content.lower()

        # Check for harmful patterns
        for pattern in self.HARMFUL_PATTERNS:
            if pattern in content_lower:
                # Check for educational/defensive context
                if self._is_educational_context(content, context):
                    continue

                violations.append(EthicalViolation(
                    principle=EthicalPrinciple.HARM_PREVENTION,
                    severity=Severity.HIGH,
                    description=f"Potentially harmful content detected: '{pattern}'",
                    context={"pattern": pattern, "action_type": action_type},
                    remediation="Content should be reviewed for educational context or modified"
                ))

        # Check for targeted harm
        for pattern in self.TARGETED_HARM_PATTERNS:
            if pattern in content_lower and self._has_target_reference(content):
                violations.append(EthicalViolation(
                    principle=EthicalPrinciple.HARM_PREVENTION,
                    severity=Severity.CRITICAL,
                    description=f"Potentially targeted harmful content: '{pattern}'",
                    context={"pattern": pattern, "action_type": action_type},
                    remediation="Action blocked due to potential targeted harm"
                ))

        # Determine result
        if any(v.severity == Severity.CRITICAL for v in violations):
            return EthicalValidation(
                result=ValidationResult.BLOCKED,
                violations=violations,
                explanation="Action blocked due to critical harm prevention violation",
                validator_name=self.name
            )
        elif violations:
            return EthicalValidation(
                result=ValidationResult.WARNING,
                violations=violations,
                explanation="Action approved with warnings - review recommended",
                validator_name=self.name
            )

        return EthicalValidation(
            result=ValidationResult.APPROVED,
            explanation="No harm prevention issues detected",
            validator_name=self.name
        )

    def _extract_content(self, data: Dict[str, Any]) -> str:
        """Extract text content from data for analysis."""
        parts = []
        for key in ["content", "message", "text", "query", "input", "output", "args"]:
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    parts.append(val)
                elif isinstance(val, dict):
                    parts.append(json.dumps(val))
        return " ".join(parts)

    def _is_educational_context(self, content: str, context: Dict[str, Any]) -> bool:
        """Check if the content is in an educational/defensive context."""
        educational_indicators = [
            "how to prevent", "how to defend", "security research",
            "educational", "ctf", "capture the flag", "penetration test",
            "authorized", "defensive", "protection", "mitigation"
        ]
        content_lower = content.lower()
        return any(ind in content_lower for ind in educational_indicators)

    def _has_target_reference(self, content: str) -> bool:
        """Check if content references a specific target."""
        target_indicators = ["someone", "person", "people", "user", "target", "victim"]
        content_lower = content.lower()
        return any(ind in content_lower for ind in target_indicators)


class PrivacyValidator(EthicalValidator):
    """Validates actions for privacy principle violations."""

    # Patterns that may indicate PII
    PII_PATTERNS = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{16}\b',  # Credit card
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone
    ]

    def __init__(self):
        super().__init__(
            name="PrivacyValidator",
            principles=[
                EthicalPrinciple.DATA_MINIMIZATION,
                EthicalPrinciple.CONSENT_RESPECT,
                EthicalPrinciple.CONFIDENTIALITY
            ]
        )

    async def validate(self, action_type: str, data: Dict[str, Any], context: Dict[str, Any]) -> EthicalValidation:
        import re

        violations = []
        content = self._extract_content(data)

        # Check for PII patterns
        for pattern in self.PII_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                violations.append(EthicalViolation(
                    principle=EthicalPrinciple.DATA_MINIMIZATION,
                    severity=Severity.MEDIUM,
                    description=f"Potential PII detected in content",
                    context={"pattern_type": pattern[:20], "action_type": action_type},
                    remediation="Consider masking or removing PII before processing"
                ))

        # Check for data storage actions without consent context
        if action_type in ["memory_save", "store", "persist"] and not context.get("consent_verified"):
            violations.append(EthicalViolation(
                principle=EthicalPrinciple.CONSENT_RESPECT,
                severity=Severity.LOW,
                description="Data storage without explicit consent verification",
                context={"action_type": action_type},
                remediation="Ensure user consent before storing personal data"
            ))

        if violations:
            return EthicalValidation(
                result=ValidationResult.WARNING,
                violations=violations,
                explanation="Privacy considerations detected - review recommended",
                validator_name=self.name
            )

        return EthicalValidation(
            result=ValidationResult.APPROVED,
            explanation="No privacy issues detected",
            validator_name=self.name
        )

    def _extract_content(self, data: Dict[str, Any]) -> str:
        """Extract text content from data for analysis."""
        parts = []
        for key in ["content", "message", "text", "query", "input", "output", "args"]:
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    parts.append(val)
                elif isinstance(val, dict):
                    parts.append(json.dumps(val))
        return " ".join(parts)


class TransparencyValidator(EthicalValidator):
    """Validates actions for transparency and honesty violations."""

    DECEPTION_PATTERNS = [
        "pretend to be", "impersonate", "fake", "deceive", "trick",
        "mislead", "lie about", "false identity"
    ]

    def __init__(self):
        super().__init__(
            name="TransparencyValidator",
            principles=[
                EthicalPrinciple.HONESTY,
                EthicalPrinciple.EXPLAINABILITY,
                EthicalPrinciple.AUDITABILITY
            ]
        )

    async def validate(self, action_type: str, data: Dict[str, Any], context: Dict[str, Any]) -> EthicalValidation:
        violations = []
        content = self._extract_content(data)
        content_lower = content.lower()

        # Check for deception patterns
        for pattern in self.DECEPTION_PATTERNS:
            if pattern in content_lower:
                violations.append(EthicalViolation(
                    principle=EthicalPrinciple.HONESTY,
                    severity=Severity.HIGH,
                    description=f"Potential deception detected: '{pattern}'",
                    context={"pattern": pattern, "action_type": action_type},
                    remediation="Actions should be transparent and honest"
                ))

        # Check for auditability - actions should have proper logging
        if action_type in ["execute", "run", "call"] and not context.get("audit_enabled", True):
            violations.append(EthicalViolation(
                principle=EthicalPrinciple.AUDITABILITY,
                severity=Severity.LOW,
                description="Action executed without audit trail",
                context={"action_type": action_type},
                remediation="Enable audit logging for all significant actions"
            ))

        if any(v.severity in (Severity.HIGH, Severity.CRITICAL) for v in violations):
            return EthicalValidation(
                result=ValidationResult.BLOCKED,
                violations=violations,
                explanation="Action blocked due to transparency violation",
                validator_name=self.name
            )
        elif violations:
            return EthicalValidation(
                result=ValidationResult.WARNING,
                violations=violations,
                explanation="Transparency considerations detected",
                validator_name=self.name
            )

        return EthicalValidation(
            result=ValidationResult.APPROVED,
            explanation="No transparency issues detected",
            validator_name=self.name
        )

    def _extract_content(self, data: Dict[str, Any]) -> str:
        """Extract text content from data for analysis."""
        parts = []
        for key in ["content", "message", "text", "query", "input", "output", "args"]:
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    parts.append(val)
                elif isinstance(val, dict):
                    parts.append(json.dumps(val))
        return " ".join(parts)


class AccountabilityValidator(EthicalValidator):
    """Validates actions for accountability and responsibility."""

    def __init__(self):
        super().__init__(
            name="AccountabilityValidator",
            principles=[
                EthicalPrinciple.RESPONSIBILITY,
                EthicalPrinciple.TRACEABILITY,
                EthicalPrinciple.CORRECTIVE_ACTION
            ]
        )

    async def validate(self, action_type: str, data: Dict[str, Any], context: Dict[str, Any]) -> EthicalValidation:
        violations = []

        # Check for proper attribution
        if action_type in ["response", "output", "generate"]:
            if not context.get("agent_id"):
                violations.append(EthicalViolation(
                    principle=EthicalPrinciple.TRACEABILITY,
                    severity=Severity.LOW,
                    description="Action lacks proper agent attribution",
                    context={"action_type": action_type},
                    remediation="Ensure all actions are attributed to responsible agent"
                ))

        # Check for irreversible actions without confirmation
        irreversible_actions = ["delete", "remove", "destroy", "terminate", "shutdown"]
        if action_type in irreversible_actions and not context.get("confirmed"):
            violations.append(EthicalViolation(
                principle=EthicalPrinciple.CORRECTIVE_ACTION,
                severity=Severity.MEDIUM,
                description="Irreversible action without confirmation",
                context={"action_type": action_type},
                remediation="Confirm irreversible actions before execution"
            ))

        if violations:
            return EthicalValidation(
                result=ValidationResult.WARNING,
                violations=violations,
                explanation="Accountability considerations detected",
                validator_name=self.name
            )

        return EthicalValidation(
            result=ValidationResult.APPROVED,
            explanation="No accountability issues detected",
            validator_name=self.name
        )


class HumanOversightValidator(EthicalValidator):
    """Validates actions for human oversight requirements."""

    # Actions that require human oversight
    OVERSIGHT_REQUIRED_ACTIONS = [
        "financial_transfer", "system_modify", "access_grant",
        "data_export", "credential_change", "policy_update"
    ]

    def __init__(self):
        super().__init__(
            name="HumanOversightValidator",
            principles=[
                EthicalPrinciple.HUMAN_OVERSIGHT,
                EthicalPrinciple.HUMAN_AGENCY,
                EthicalPrinciple.INFORMED_CHOICE
            ]
        )

    async def validate(self, action_type: str, data: Dict[str, Any], context: Dict[str, Any]) -> EthicalValidation:
        violations = []

        # Check if action requires human oversight
        if action_type in self.OVERSIGHT_REQUIRED_ACTIONS:
            if not context.get("human_approved"):
                violations.append(EthicalViolation(
                    principle=EthicalPrinciple.HUMAN_OVERSIGHT,
                    severity=Severity.HIGH,
                    description=f"Action '{action_type}' requires human oversight",
                    context={"action_type": action_type},
                    remediation="Obtain human approval before proceeding"
                ))

                return EthicalValidation(
                    result=ValidationResult.REQUIRES_REVIEW,
                    violations=violations,
                    explanation="Action requires human review before execution",
                    validator_name=self.name
                )

        # Check for autonomous decision loops
        if context.get("autonomous_depth", 0) > 5:
            violations.append(EthicalViolation(
                principle=EthicalPrinciple.HUMAN_AGENCY,
                severity=Severity.MEDIUM,
                description="Deep autonomous decision chain detected",
                context={"depth": context.get("autonomous_depth")},
                remediation="Consider human checkpoint for long decision chains"
            ))

        if violations:
            return EthicalValidation(
                result=ValidationResult.WARNING,
                violations=violations,
                explanation="Human oversight considerations detected",
                validator_name=self.name
            )

        return EthicalValidation(
            result=ValidationResult.APPROVED,
            explanation="Human oversight requirements satisfied",
            validator_name=self.name
        )


@dataclass
class Constitution:
    """
    The ethical constitution that defines the principles and rules governing agent behavior.

    This is the central document that all validators reference and that defines
    the ethical boundaries of the system.
    """

    name: str = "Vessels Ethical Constitution"
    version: str = "1.0.0"

    # Core principles that cannot be overridden
    immutable_principles: List[EthicalPrinciple] = field(default_factory=lambda: [
        EthicalPrinciple.HARM_PREVENTION,
        EthicalPrinciple.HUMAN_OVERSIGHT,
        EthicalPrinciple.HONESTY
    ])

    # All principles with their weights (importance)
    principle_weights: Dict[EthicalPrinciple, float] = field(default_factory=lambda: {
        EthicalPrinciple.HARM_PREVENTION: 1.0,
        EthicalPrinciple.HUMAN_OVERSIGHT: 0.95,
        EthicalPrinciple.FAIL_SAFE: 0.9,
        EthicalPrinciple.HONESTY: 0.9,
        EthicalPrinciple.EXPLAINABILITY: 0.8,
        EthicalPrinciple.AUDITABILITY: 0.85,
        EthicalPrinciple.DATA_MINIMIZATION: 0.75,
        EthicalPrinciple.CONSENT_RESPECT: 0.8,
        EthicalPrinciple.CONFIDENTIALITY: 0.85,
        EthicalPrinciple.NON_DISCRIMINATION: 0.9,
        EthicalPrinciple.EQUAL_ACCESS: 0.7,
        EthicalPrinciple.IMPARTIALITY: 0.75,
        EthicalPrinciple.RESPONSIBILITY: 0.85,
        EthicalPrinciple.TRACEABILITY: 0.8,
        EthicalPrinciple.CORRECTIVE_ACTION: 0.7,
        EthicalPrinciple.HUMAN_AGENCY: 0.9,
        EthicalPrinciple.INFORMED_CHOICE: 0.75,
        EthicalPrinciple.REVERSIBILITY: 0.7,
    })

    # Rules derived from principles
    rules: List[str] = field(default_factory=lambda: [
        "Never assist in actions intended to cause harm to individuals or groups",
        "Always maintain transparency about being an AI system",
        "Respect user privacy and minimize data collection",
        "Ensure human oversight for significant decisions",
        "Maintain audit trails for all significant actions",
        "Refuse to impersonate humans or deceive about identity",
        "Provide honest and accurate information",
        "Enable users to correct or reverse AI decisions",
        "Avoid discrimination based on protected characteristics",
        "Prioritize safety over task completion"
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "immutable_principles": [p.value for p in self.immutable_principles],
            "principle_weights": {p.value: w for p, w in self.principle_weights.items()},
            "rules": self.rules
        }

    def get_principle_weight(self, principle: EthicalPrinciple) -> float:
        """Get the weight/importance of a principle."""
        return self.principle_weights.get(principle, 0.5)

    def is_immutable(self, principle: EthicalPrinciple) -> bool:
        """Check if a principle is immutable."""
        return principle in self.immutable_principles


class EthicsEngine:
    """
    Central ethics engine that coordinates all ethical validation.

    This is a singleton that manages all validators and provides a unified
    interface for ethical validation throughout the system.
    """

    _instance: Optional['EthicsEngine'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.constitution = Constitution()
        self.validators: List[EthicalValidator] = []
        self.violation_history: List[EthicalViolation] = []
        self.validation_cache: Dict[str, EthicalValidation] = {}
        self._memory_recorder: Optional[Callable] = None
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> 'EthicsEngine':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the ethics engine with default validators."""
        if self._initialized:
            return

        # Register default validators
        self.validators = [
            HarmPreventionValidator(),
            PrivacyValidator(),
            TransparencyValidator(),
            AccountabilityValidator(),
            HumanOversightValidator(),
        ]

        self._initialized = True
        logger.info(f"EthicsEngine initialized with {len(self.validators)} validators")

    def set_memory_recorder(self, recorder: Callable):
        """Set the callback function for recording to collective memory."""
        self._memory_recorder = recorder

    def register_validator(self, validator: EthicalValidator):
        """Register a new ethical validator."""
        self.validators.append(validator)
        logger.info(f"Registered validator: {validator.name}")

    def unregister_validator(self, validator_name: str):
        """Unregister a validator by name."""
        self.validators = [v for v in self.validators if v.name != validator_name]

    async def validate(
        self,
        action_type: str,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> EthicalValidation:
        """
        Validate an action against all ethical principles.

        Args:
            action_type: Type of action being performed
            data: Data associated with the action
            context: Additional context for validation

        Returns:
            Combined ethical validation result
        """
        context = context or {}
        all_violations: List[EthicalViolation] = []
        all_modifications: Dict[str, Any] = {}
        worst_result = ValidationResult.APPROVED
        explanations: List[str] = []

        # Run all validators
        for validator in self.validators:
            if not validator.enabled:
                continue

            try:
                validation = await validator.validate(action_type, data, context)

                all_violations.extend(validation.violations)
                all_modifications.update(validation.modifications)
                explanations.append(f"{validator.name}: {validation.explanation}")

                # Track worst result
                if validation.result == ValidationResult.BLOCKED:
                    worst_result = ValidationResult.BLOCKED
                elif validation.result == ValidationResult.REQUIRES_REVIEW and worst_result != ValidationResult.BLOCKED:
                    worst_result = ValidationResult.REQUIRES_REVIEW
                elif validation.result == ValidationResult.MODIFIED and worst_result in (ValidationResult.APPROVED, ValidationResult.WARNING):
                    worst_result = ValidationResult.MODIFIED
                elif validation.result == ValidationResult.WARNING and worst_result == ValidationResult.APPROVED:
                    worst_result = ValidationResult.WARNING

            except Exception as e:
                logger.error(f"Validator {validator.name} failed: {e}")
                # Continue with other validators

        # Record violations to history
        self.violation_history.extend(all_violations)

        # Create combined result
        combined = EthicalValidation(
            result=worst_result,
            violations=all_violations,
            modifications=all_modifications,
            explanation="; ".join(explanations),
            validator_name="EthicsEngine"
        )

        # Record to collective memory if recorder is set
        if self._memory_recorder:
            await self._record_validation(action_type, data, combined)

        return combined

    async def _record_validation(
        self,
        action_type: str,
        data: Dict[str, Any],
        validation: EthicalValidation
    ):
        """Record validation result to collective memory."""
        if not self._memory_recorder:
            return

        try:
            record = {
                "type": "ethical_validation",
                "action_type": action_type,
                "timestamp": datetime.now().isoformat(),
                "result": validation.result.value,
                "violations_count": len(validation.violations),
                "violations": [v.to_dict() for v in validation.violations],
                "explanation": validation.explanation
            }
            await self._memory_recorder(record)
        except Exception as e:
            logger.error(f"Failed to record validation to memory: {e}")

    def get_violation_stats(self) -> Dict[str, Any]:
        """Get statistics about ethical violations."""
        stats = {
            "total_violations": len(self.violation_history),
            "by_principle": {},
            "by_severity": {},
            "recent_violations": []
        }

        for violation in self.violation_history:
            # Count by principle
            p_name = violation.principle.value
            stats["by_principle"][p_name] = stats["by_principle"].get(p_name, 0) + 1

            # Count by severity
            s_name = violation.severity.value
            stats["by_severity"][s_name] = stats["by_severity"].get(s_name, 0) + 1

        # Get recent violations
        stats["recent_violations"] = [
            v.to_dict() for v in self.violation_history[-10:]
        ]

        return stats

    def get_constitution(self) -> Dict[str, Any]:
        """Get the current constitution as a dictionary."""
        return self.constitution.to_dict()

    async def check_principle(
        self,
        principle: EthicalPrinciple,
        action_type: str,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> EthicalValidation:
        """Check a specific principle for an action."""
        context = context or {}

        for validator in self.validators:
            if validator.covers_principle(principle) and validator.enabled:
                return await validator.validate(action_type, data, context)

        # No validator covers this principle
        return EthicalValidation(
            result=ValidationResult.APPROVED,
            explanation=f"No validator registered for principle: {principle.value}",
            validator_name="EthicsEngine"
        )


# Convenience functions for direct use
async def validate_ethics(
    action_type: str,
    data: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> EthicalValidation:
    """Convenience function to validate ethics."""
    engine = await EthicsEngine.get_instance()
    return await engine.validate(action_type, data, context)


async def is_ethical(
    action_type: str,
    data: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> bool:
    """Quick check if an action is ethical (approved or warning)."""
    validation = await validate_ethics(action_type, data, context)
    return validation.is_approved


async def get_ethics_engine() -> EthicsEngine:
    """Get the ethics engine instance."""
    return await EthicsEngine.get_instance()
