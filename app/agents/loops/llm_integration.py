"""
LLM Integration Points for Agent Loops.

Wires LLMService into the existing loop patterns:
- ReAct loop: LLM-powered reasoning step
- Reflexion loop: LLM-powered critique/reflection
- Content quality loop: LLM-powered quality assessment

This module provides wrapper classes and helpers that inject LLM
calls at the right points in each loop, without modifying the
core loop implementations.

Architecture:
    ┌──────────────────────────────────────────────────────┐
    │                  Agent Loop                           │
    │                                                      │
    │  ┌─────────┐    ┌─────────┐    ┌──────────┐         │
    │  │  Think   │───▶│   Act   │───▶│ Observe  │         │
    │  │(LLM ✓)  │    │         │    │          │         │
    │  └─────────┘    └─────────┘    └──────────┘         │
    │       ▲                              │               │
    │       │        ┌─────────┐           │               │
    │       └────────│ Reflect │◀──────────┘               │
    │                │(LLM ✓)  │                           │
    │                └─────────┘                           │
    └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.llm_service import LLMConfig, LLMMessage, LLMService, get_llm_service

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Prompt Templates
# ════════════════════════════════════════════════════════════════════

REACT_REASONING_PROMPT = """You are {agent_name}, a business intelligence agent for African micro-entrepreneurs.

Your role: {agent_role}
Your capabilities: {capabilities}

Current task context:
{context}

Previous reasoning steps:
{previous_steps}

Think step by step:
1. What information do I have?
2. What is the best action to take?
3. What confidence level do I assign?

Respond in JSON format:
{{"reasoning": "...", "action": "...", "parameters": {{...}}, "confidence": 0.0-1.0}}"""

REFLEXION_CRITIQUE_PROMPT = """You are a quality critic for a business intelligence agent.

Task: {task}
Result: {result}
Expected language: {language}

Evaluate the result quality:
1. Is the response accurate and helpful?
2. Is it in the correct language ({language})?
3. Is it appropriate for a micro-entrepreneur?
4. Are there any issues or improvements needed?

Respond in JSON format:
{{"score": 0.0-1.0, "issues": ["..."], "suggestions": ["..."], "should_retry": true/false}}"""

CONTENT_QUALITY_PROMPT = """Evaluate the quality of this business intelligence content:

Content: {content}
Content type: {content_type}
Target audience: African micro-entrepreneurs (small shop owners, farmers, transporters)

Assess:
1. Accuracy of business advice
2. Clarity and simplicity of language
3. Cultural appropriateness
4. Actionability (can the reader act on this?)
5. Correct language ({language})

Respond in JSON format:
{{"score": 0.0-1.0, "strengths": ["..."], "weaknesses": ["..."], "improvements": ["..."]}}"""


# ════════════════════════════════════════════════════════════════════
# LLM-Powered ReAct Reasoning
# ════════════════════════════════════════════════════════════════════


class LLMReActReasoner:
    """
    Injects LLM-powered reasoning into the ReAct loop's think phase.

    Instead of heuristic reasoning, the agent asks Qwen 2.5 to
    reason about the task and decide on an action.

    Usage:
        reasoner = LLMReActReasoner(llm_service)
        decision = await reasoner.reason(
            agent_name="IntelligenceGenerator",
            agent_role="Generate business insights",
            capabilities=["data_analysis", "pattern_detection"],
            context={"event_type": "transaction.processed", "payload": {...}},
            previous_steps=["Step 1: Analyzed sales data", "Step 2: Detected trend"],
        )
    """

    def __init__(self, llm_service: LLMService | None = None):
        self._llm = llm_service
        self._logger = logger.bind(component="llm_react_reasoner")

    async def _get_llm(self) -> LLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def reason(
        self,
        agent_name: str,
        agent_role: str,
        capabilities: list[str],
        context: dict[str, Any],
        previous_steps: list[str] | None = None,
        config: LLMConfig | None = None,
    ) -> dict[str, Any]:
        """
        Generate LLM-powered reasoning for the ReAct think phase.

        Returns dict with: reasoning, action, parameters, confidence
        Falls back to heuristic on LLM failure.
        """
        llm = await self._get_llm()

        prompt = REACT_REASONING_PROMPT.format(
            agent_name=agent_name,
            agent_role=agent_role,
            capabilities=", ".join(capabilities),
            context=json.dumps(context, default=str)[:2000],
            previous_steps="\n".join(previous_steps or ["(first step)"]),
        )

        llm_config = config or LLMConfig(
            temperature=0.3,  # Lower temp for more deterministic reasoning
            max_tokens=300,
        )

        result = await llm.complete(
            messages=[LLMMessage(role="user", content=prompt)],
            config=llm_config,
        )

        if result.success:
            try:
                # Parse JSON response
                parsed = json.loads(result.content)
                self._logger.info(
                    "llm_reasoning_success",
                    agent=agent_name,
                    action=parsed.get("action"),
                    confidence=parsed.get("confidence"),
                    tokens=result.usage.get("total_tokens", 0),
                )
                return {
                    "reasoning": parsed.get("reasoning", ""),
                    "action": parsed.get("action", "default"),
                    "parameters": parsed.get("parameters", {}),
                    "confidence": float(parsed.get("confidence", 0.5)),
                    "source": "llm",
                    "model": result.model,
                    "latency_ms": result.latency_ms,
                }
            except (json.JSONDecodeError, ValueError) as exc:
                self._logger.warning("llm_json_parse_failed", error=str(exc))
                return self._fallback_reasoning(agent_name, context)
        else:
            self._logger.warning("llm_reasoning_failed", error=result.error)
            return self._fallback_reasoning(agent_name, context)

    def _fallback_reasoning(
        self, agent_name: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Heuristic fallback when LLM is unavailable."""
        return {
            "reasoning": f"Heuristic reasoning for {agent_name} (LLM unavailable)",
            "action": "default",
            "parameters": context.get("payload", {}),
            "confidence": 0.5,
            "source": "heuristic",
            "model": "none",
            "latency_ms": 0,
        }


# ════════════════════════════════════════════════════════════════════
# LLM-Powered Reflexion Critique
# ════════════════════════════════════════════════════════════════════


class LLMReflexionCritic:
    """
    Injects LLM-powered critique into the Reflexion loop.

    Instead of heuristic scoring, asks Qwen 2.5 to evaluate
    the quality of the agent's output and suggest improvements.

    Usage:
        critic = LLMReflexionCritic(llm_service)
        critique = await critic.critique(
            task="Generate weekly sales report",
            result={"success": True, "data": "..."},
            language="sw",
        )
    """

    def __init__(self, llm_service: LLMService | None = None):
        self._llm = llm_service
        self._logger = logger.bind(component="llm_reflexion_critic")

    async def _get_llm(self) -> LLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def critique(
        self,
        task: str,
        result: dict[str, Any],
        language: str = "sw",
        attempt_number: int = 1,
        config: LLMConfig | None = None,
    ) -> dict[str, Any]:
        """
        Generate LLM-powered critique for the Reflexion loop.

        Returns dict with: score, issues, suggestions, should_retry
        Falls back to heuristic on LLM failure.
        """
        llm = await self._get_llm()

        # Truncate result for prompt
        result_str = json.dumps(result, default=str)[:1500]

        prompt = REFLEXION_CRITIQUE_PROMPT.format(
            task=task[:500],
            result=result_str,
            language=language,
        )

        llm_config = config or LLMConfig(
            temperature=0.2,  # Low temp for consistent scoring
            max_tokens=300,
        )

        llm_result = await llm.complete(
            messages=[LLMMessage(role="user", content=prompt)],
            config=llm_config,
        )

        if llm_result.success:
            try:
                parsed = json.loads(llm_result.content)
                score = float(parsed.get("score", 0.5))
                self._logger.info(
                    "llm_critique_success",
                    score=score,
                    should_retry=parsed.get("should_retry"),
                    issues_count=len(parsed.get("issues", [])),
                    tokens=llm_result.usage.get("total_tokens", 0),
                )
                return {
                    "score": score,
                    "issues": parsed.get("issues", []),
                    "suggestions": parsed.get("suggestions", []),
                    "should_retry": parsed.get("should_retry", score < 0.7),
                    "source": "llm",
                    "model": llm_result.model,
                }
            except (json.JSONDecodeError, ValueError) as exc:
                self._logger.warning("llm_critique_parse_failed", error=str(exc))
                return self._fallback_critique(result, attempt_number)
        else:
            self._logger.warning("llm_critique_failed", error=llm_result.error)
            return self._fallback_critique(result, attempt_number)

    def _fallback_critique(
        self, result: dict[str, Any], attempt_number: int
    ) -> dict[str, Any]:
        """Heuristic fallback critique."""
        score = 1.0
        issues = []
        suggestions = []

        if not result.get("success", False):
            score -= 0.5
            issues.append(f"Execution failed: {result.get('error', 'unknown')}")

        if result.get("duration_ms", 0) > 10000:
            score -= 0.1
            issues.append("Slow execution")

        if attempt_number > 1:
            score -= 0.05 * (attempt_number - 1)

        score = max(0.0, min(1.0, score))

        return {
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
            "should_retry": score < 0.7,
            "source": "heuristic",
            "model": "none",
        }


# ════════════════════════════════════════════════════════════════════
# LLM-Powered Content Quality Assessment
# ════════════════════════════════════════════════════════════════════


class LLMContentQualityAssessor:
    """
    Uses LLM to assess the quality of generated content.

    For reports, advice, and intelligence delivered to users.
    Can be used standalone or integrated into quality control pipelines.

    Usage:
        assessor = LLMContentQualityAssessor(llm_service)
        assessment = await assessor.assess(
            content="Your weekly sales increased by 15%...",
            content_type="weekly_report",
            language="sw",
        )
    """

    def __init__(self, llm_service: LLMService | None = None):
        self._llm = llm_service
        self._logger = logger.bind(component="llm_content_quality")

    async def _get_llm(self) -> LLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def assess(
        self,
        content: str,
        content_type: str = "general",
        language: str = "sw",
        config: LLMConfig | None = None,
    ) -> dict[str, Any]:
        """
        Assess content quality using LLM.

        Returns dict with: score, strengths, weaknesses, improvements
        Falls back to heuristic on LLM failure.
        """
        llm = await self._get_llm()

        prompt = CONTENT_QUALITY_PROMPT.format(
            content=content[:2000],
            content_type=content_type,
            language=language,
        )

        llm_config = config or LLMConfig(
            temperature=0.2,
            max_tokens=300,
        )

        result = await llm.complete(
            messages=[LLMMessage(role="user", content=prompt)],
            config=llm_config,
        )

        if result.success:
            try:
                parsed = json.loads(result.content)
                score = float(parsed.get("score", 0.5))
                self._logger.info(
                    "llm_quality_assessment",
                    content_type=content_type,
                    score=score,
                    language=language,
                )
                return {
                    "score": score,
                    "strengths": parsed.get("strengths", []),
                    "weaknesses": parsed.get("weaknesses", []),
                    "improvements": parsed.get("improvements", []),
                    "source": "llm",
                    "model": result.model,
                }
            except (json.JSONDecodeError, ValueError):
                return self._fallback_assessment(content, content_type)
        else:
            return self._fallback_assessment(content, content_type)

    def _fallback_assessment(
        self, content: str, content_type: str
    ) -> dict[str, Any]:
        """Heuristic fallback quality assessment."""
        score = 0.7  # Default decent score
        weaknesses = []

        if len(content) < 50:
            score -= 0.2
            weaknesses.append("Content too short")
        if len(content) > 3000:
            score -= 0.1
            weaknesses.append("Content may be too long for mobile users")

        return {
            "score": max(0.0, min(1.0, score)),
            "strengths": [],
            "weaknesses": weaknesses,
            "improvements": [],
            "source": "heuristic",
            "model": "none",
        }


# ════════════════════════════════════════════════════════════════════
# Convenience Integration Helper
# ════════════════════════════════════════════════════════════════════


class LLMLoopIntegrator:
    """
    Convenience class that bundles all LLM integration points.

    Create once, inject into agents, use across all loop types.

    Usage:
        integrator = LLMLoopIntegrator()

        # In ReAct loop think phase:
        decision = await integrator.reasoner.reason(...)

        # In Reflexion loop critique phase:
        critique = await integrator.critic.critique(...)

        # In content quality pipeline:
        quality = await integrator.quality_assessor.assess(...)
    """

    def __init__(self, llm_service: LLMService | None = None):
        self.llm_service = llm_service
        self.reasoner = LLMReActReasoner(llm_service)
        self.critic = LLMReflexionCritic(llm_service)
        self.quality_assessor = LLMContentQualityAssessor(llm_service)
        self._logger = logger.bind(component="llm_loop_integrator")

    async def health_check(self) -> dict[str, Any]:
        """Check LLM health for all integration points."""
        if self.llm_service:
            return await self.llm_service.health_check()
        return {"status": "no_llm_service"}

    def get_stats(self) -> dict[str, Any]:
        """Get stats from the LLM service."""
        if self.llm_service:
            return self.llm_service.get_stats()
        return {}
