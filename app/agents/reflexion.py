"""
Reflexion Pattern for Angavu Intelligence Backend Agents.

Based on: Swarm 7 research — "Agent reflects on mistakes and improves"

The Reflexion pattern adds a self-critique loop to the agent lifecycle:
    observe → think → act → CRITIQUE → (revise → act → critique)* → reflect

This closes the gap between "the agent reflected" and
"the reflection actually changed behavior."

## Reflexion Flow
```
execute → critique → (revise → execute → critique)* → accept
```

## Integration with BiasharaAgent
The ReflexionLoop wraps the existing act() → reflect() cycle:
1. Agent produces output via act()
2. Critique evaluates quality (completeness, accuracy, format)
3. If quality < threshold, inject critique as feedback and retry
4. Store successful patterns and failure reflections in memory

## Cost Implications
- On-device reflexion: $0 (local inference)
- Cloud reflexion: Each retry = additional API call
- Budget-aware: Reflexion is disabled when user is over budget
- Max retries: Configurable (default 2) to cap cost impact

## Application to Informal Economy
For Msaidizi's use cases:
- Transaction recording: Critique checks amount, item, quantity completeness
- Financial advice: Critique checks language, relevance, actionability
- Credit assessment: Critique checks confidence level and reasoning chain
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Critique:
    """Quality assessment of an agent's output."""

    critique_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    score: float = 0.0           # 0.0 – 1.0 quality score
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    should_retry: bool = False
    revision_plan: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "critique_id": self.critique_id,
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "should_retry": self.should_retry,
            "revision_plan": self.revision_plan,
        }


@dataclass
class ReflexionResult:
    """Result of a Reflexion-enhanced execution."""

    result: Any
    critiques: List[Critique] = field(default_factory=list)
    attempts: int = 0
    final_score: float = 0.0
    success: bool = False
    total_duration_ms: float = 0.0


class ReflexionLoop:
    """
    Reflexion Loop Manager — wraps agent execution with self-critique.

    Usage with BiasharaAgent:
    ```python
    reflexion = ReflexionLoop()

    result = await reflexion.execute(
        task="Generate credit assessment",
        quality_threshold=0.7,
        max_retries=2,
        critique_fn=lambda output: critique_credit_assessment(output),
        execute_fn=lambda prev_critique: agent.act(decision),
    )

    if result.success:
        # Use result.result
        pass
    else:
        # Handle failure with best-effort result
        pass
    ```

    The agent critiques its own output and retries if quality is low,
    injecting the critique as feedback for the next attempt.
    """

    def __init__(self, max_critique_history: int = 100):
        self._critique_history: List[Critique] = []
        self._max_critique_history = max_critique_history

    async def execute(
        self,
        task: str,
        quality_threshold: float = 0.7,
        max_retries: int = 2,
        critique_fn: Optional[Callable] = None,
        execute_fn: Optional[Callable] = None,
    ) -> ReflexionResult:
        """
        Execute with Reflexion — self-critique and retry loop.

        Args:
            task: Description of the task
            quality_threshold: Minimum acceptable quality score
            max_retries: Maximum number of retry attempts
            critique_fn: Async function to evaluate result quality
            execute_fn: Async function to execute (receives critique feedback on retries)

        Returns:
            ReflexionResult with the final output and critique history
        """
        start_time = time.time()
        critiques: List[Critique] = []
        attempt = 0
        last_result = None
        last_critique = None

        while attempt <= max_retries:
            attempt += 1

            # Execute with optional critique feedback
            if execute_fn is not None:
                if asyncio.iscoroutinefunction(execute_fn):
                    last_result = await execute_fn(last_critique)
                else:
                    last_result = execute_fn(last_critique)
            else:
                break

            # Critique the result
            if critique_fn is not None:
                if asyncio.iscoroutinefunction(critique_fn):
                    critique = await critique_fn(last_result)
                else:
                    critique = critique_fn(last_result)
            else:
                critique = Critique(score=1.0)

            critiques.append(critique)
            self._critique_history.append(critique)
            last_critique = critique

            logger.debug(
                "reflexion_critique",
                task=task,
                attempt=attempt,
                score=critique.score,
                should_retry=critique.should_retry,
            )

            # If quality is acceptable, stop
            if critique.score >= quality_threshold:
                logger.debug(
                    "reflexion_quality_accepted",
                    task=task,
                    score=critique.score,
                    threshold=quality_threshold,
                )
                break

            # If max retries reached, stop
            if attempt > max_retries:
                logger.warning(
                    "reflexion_max_retries",
                    task=task,
                    best_score=max((c.score for c in critiques), default=0.0),
                )
                break

            logger.debug(
                "reflexion_retrying",
                task=task,
                score=critique.score,
                threshold=quality_threshold,
                revision_plan=critique.revision_plan,
            )

        # Trim history
        while len(self._critique_history) > self._max_critique_history:
            self._critique_history.pop(0)

        total_ms = (time.time() - start_time) * 1000
        final_score = critiques[-1].score if critiques else 0.0

        return ReflexionResult(
            result=last_result,
            critiques=critiques,
            attempts=attempt,
            final_score=final_score,
            success=final_score >= quality_threshold,
            total_duration_ms=total_ms,
        )

    def critique_response(
        self,
        response: str,
        expected_language: str = "sw",
        min_length: int = 10,
        max_length: int = 2000,
    ) -> Critique:
        """
        Critique a text response for quality.

        Checks for:
        - Completeness (non-empty, reasonable length)
        - Error indicators
        - Language consistency
        """
        issues: List[str] = []
        suggestions: List[str] = []
        score = 1.0

        # Check for errors
        if "⚠️" in response or "error" in response.lower():
            score -= 0.4
            issues.append("Response contains error indicators")

        # Check length
        if len(response) < min_length:
            score -= 0.3
            issues.append(f"Response too short ({len(response)} < {min_length})")
            suggestions.append("Provide more detail in the response")

        if len(response) > max_length:
            score -= 0.1
            issues.append(f"Response too long ({len(response)} > {max_length})")
            suggestions.append("Shorten the response for WhatsApp delivery")

        # Check for empty content
        if not response.strip():
            score -= 0.5
            issues.append("Response is empty")

        # Check for language consistency
        if expected_language == "sw" and response.isascii():
            score -= 0.05
            suggestions.add("Consider using Swahili for Swahili-speaking users")

        score = max(0.0, min(1.0, score))

        return Critique(
            score=score,
            issues=issues,
            suggestions=suggestions,
            should_retry=score < 0.7,
            revision_plan="; ".join(suggestions) if suggestions else "No changes needed",
        )

    def critique_transaction(
        self,
        item: Optional[str] = None,
        amount: Optional[float] = None,
        quantity: Optional[float] = None,
    ) -> Critique:
        """
        Critique a transaction recording for accuracy.

        Checks for:
        - Item name present
        - Amount is valid and positive
        - Quantity is reasonable
        - No suspicious values
        """
        issues: List[str] = []
        suggestions: List[str] = []
        score = 1.0

        if not item or not item.strip():
            score -= 0.3
            issues.append("Missing item name")
            suggestions.append("Ask user to specify the item")

        if amount is None or amount <= 0:
            score -= 0.4
            issues.append("Invalid or missing amount")
            suggestions.append("Ask user for the price")

        if quantity is None or quantity <= 0:
            score -= 0.1
            issues.append("Missing quantity — defaulting to 1")

        # Check for suspiciously high amounts
        if amount is not None and amount > 1_000_000:
            score -= 0.2
            issues.append(f"Unusually high amount: KSh {amount}")
            suggestions.append("Confirm the amount with the user")

        score = max(0.0, min(1.0, score))

        return Critique(
            score=score,
            issues=issues,
            suggestions=suggestions,
            should_retry=score < 0.7,
            revision_plan="; ".join(suggestions) if suggestions else "Transaction data acceptable",
        )

    def critique_credit_assessment(
        self,
        assessment: Dict[str, Any],
    ) -> Critique:
        """
        Critique a credit assessment for completeness and confidence.
        """
        issues: List[str] = []
        suggestions: List[str] = []
        score = 1.0

        if "credit_score" not in assessment and "score" not in assessment:
            score -= 0.3
            issues.append("Missing credit score")
            suggestions.append("Include a numeric credit score")

        if "risk_level" not in assessment and "rating" not in assessment:
            score -= 0.2
            issues.append("Missing risk level")
            suggestions.append("Include risk level assessment")

        confidence = assessment.get("confidence", 0.0)
        if confidence < 0.5:
            score -= 0.2
            issues.append(f"Low confidence: {confidence}")
            suggestions.append("Gather more data before assessment")

        score = max(0.0, min(1.0, score))

        return Critique(
            score=score,
            issues=issues,
            suggestions=suggestions,
            should_retry=score < 0.7,
            revision_plan="; ".join(suggestions) if suggestions else "Assessment acceptable",
        )

    def get_critique_history(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent critiques for analysis."""
        return [c.to_dict() for c in self._critique_history[-n:]]

    def get_average_score(self) -> float:
        """Get average critique score across all critiques."""
        if not self._critique_history:
            return 0.0
        return sum(c.score for c in self._critique_history) / len(self._critique_history)

    def get_critique_count(self) -> int:
        """Get total number of critiques performed."""
        return len(self._critique_history)


# Need asyncio for async function detection
import asyncio
