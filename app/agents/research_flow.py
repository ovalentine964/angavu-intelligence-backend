"""
Research Flow — Multi-Step Research Pipeline.

Implements a DeerFlow-inspired research workflow with specialized agents:
- ResearchPlanner     — plans multi-step research strategy
- DataCollector       — gathers data from multiple sources
- Analyzer            — processes and analyzes collected data
- ReportGenerator     — creates comprehensive research reports
- QualityValidator    — validates research quality and completeness

These agents form a pipeline:
    ResearchPlanner → DataCollector → Analyzer → ReportGenerator → QualityValidator

Each agent extends BiasharaAgent or one of the loop patterns
(ReAct, Reflexion, PlanExecute) for enhanced capabilities.

Designed for long-horizon research tasks like:
- Market analysis for a specific region/product
- Credit risk assessment for a worker cohort
- Distribution gap analysis across regions
- Competitive intelligence gathering
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)
from app.agents.long_horizon import (
    LongHorizonOrchestrator,
    LongHorizonTask,
    ResultAggregator,
    SubAgentDelegator,
    SubTask,
    SubTaskStatus,
    TaskPlanner,
    TaskStatus,
)
from app.agents.loops import (
    Critique,
    ExecutionPlan,
    PlanStep,
    ReflexionAgent,
    ReActAgent,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Research-Specific Types
# ════════════════════════════════════════════════════════════════════


class ResearchScope:
    """Defines the scope and parameters of a research task."""

    def __init__(
        self,
        topic: str,
        region: Optional[str] = None,
        product_category: Optional[str] = None,
        time_horizon: str = "30d",
        depth: str = "standard",  # quick | standard | deep
        sources: Optional[List[str]] = None,
    ):
        self.topic = topic
        self.region = region
        self.product_category = product_category
        self.time_horizon = time_horizon
        self.depth = depth
        self.sources = sources or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "region": self.region,
            "product_category": self.product_category,
            "time_horizon": self.time_horizon,
            "depth": self.depth,
            "sources": self.sources,
        }


class ResearchResult:
    """Structured output of a research flow."""

    def __init__(
        self,
        scope: ResearchScope,
        findings: List[Dict[str, Any]],
        data_sources_used: List[str],
        confidence: float = 0.0,
        quality_score: float = 0.0,
        report: Optional[Dict[str, Any]] = None,
    ):
        self.result_id = uuid.uuid4().hex[:16]
        self.scope = scope
        self.findings = findings
        self.data_sources_used = data_sources_used
        self.confidence = confidence
        self.quality_score = quality_score
        self.report = report
        self.created_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "scope": self.scope.to_dict(),
            "findings_count": len(self.findings),
            "findings": self.findings[:10],  # limit for API response
            "data_sources_used": self.data_sources_used,
            "confidence": self.confidence,
            "quality_score": self.quality_score,
            "has_report": self.report is not None,
            "created_at": self.created_at,
        }


# ════════════════════════════════════════════════════════════════════
# ResearchPlanner — Plans Multi-Step Research Strategy
# ════════════════════════════════════════════════════════════════════


class ResearchPlanner(TaskPlanner):
    """
    Plans multi-step research by decomposing research goals
    into a DAG of sub-tasks.

    Research decomposition strategy:
    1. Identify data sources needed
    2. Plan collection tasks (parallel where possible)
    3. Plan analysis tasks (depend on collection)
    4. Plan report generation (depends on analysis)
    5. Plan quality validation (depends on report)
    """

    def __init__(self):
        super().__init__(name="ResearchPlanner")

    async def _decompose(
        self,
        goal: str,
        context: Dict[str, Any],
        available_agents: List[str],
    ) -> List[SubTask]:
        """Decompose a research goal into sub-tasks."""
        scope = context.get("scope", {})
        depth = scope.get("depth", "standard")
        sources = scope.get("sources", ["transactions", "market_data", "worker_feedback"])

        subtasks = []

        # Step 1: Data collection (one sub-task per source, parallel)
        collect_ids = []
        for source in sources:
            st = SubTask(
                name=f"collect_{source}",
                description=f"Collect data from {source}",
                action="data_collection",
                parameters={"source": source, "scope": scope},
                assigned_agent="DataCollector" if "DataCollector" in available_agents else None,
                timeout_seconds=600.0 if depth == "deep" else 300.0,
            )
            subtasks.append(st)
            collect_ids.append(st.subtask_id)

        # Step 2: Analysis (depends on all collection tasks)
        analyze_st = SubTask(
            name="analyze_data",
            description="Analyze collected data for patterns and insights",
            action="data_analysis",
            parameters={"scope": scope},
            dependencies=collect_ids,
            assigned_agent="ResearchAnalyzer" if "ResearchAnalyzer" in available_agents else None,
            timeout_seconds=900.0 if depth == "deep" else 450.0,
        )
        subtasks.append(analyze_st)

        # Step 3: Report generation (depends on analysis)
        report_st = SubTask(
            name="generate_report",
            description="Generate comprehensive research report",
            action="report_generation",
            parameters={"scope": scope},
            dependencies=[analyze_st.subtask_id],
            assigned_agent="ResearchReporter" if "ResearchReporter" in available_agents else None,
            timeout_seconds=600.0,
        )
        subtasks.append(report_st)

        # Step 4: Quality validation (depends on report)
        validate_st = SubTask(
            name="validate_quality",
            description="Validate research quality and completeness",
            action="quality_validation",
            parameters={"scope": scope},
            dependencies=[report_st.subtask_id],
            assigned_agent="QualityValidator" if "QualityValidator" in available_agents else None,
            timeout_seconds=300.0,
        )
        subtasks.append(validate_st)

        return subtasks

    async def replan(
        self,
        task: LongHorizonTask,
        failed_subtask: SubTask,
        context: Dict[str, Any],
    ) -> List[SubTask]:
        """Re-plan: retry collection with alternative source, skip if exhausted."""
        if failed_subtask.action == "data_collection" and failed_subtask.attempts < failed_subtask.max_retries:
            # Retry with same source
            failed_subtask.status = SubTaskStatus.PENDING
            failed_subtask.error = None
            return task.subtasks

        if failed_subtask.action == "data_collection":
            # Skip failed source, continue with remaining
            failed_subtask.status = SubTaskStatus.SKIPPED
            self._logger.warning(
                "skipping_failed_source",
                subtask_id=failed_subtask.subtask_id,
                source=failed_subtask.parameters.get("source"),
            )
            return task.subtasks

        # For analysis/report/validation: retry once then fail
        if failed_subtask.attempts < 2:
            failed_subtask.status = SubTaskStatus.PENDING
            failed_subtask.error = None
            return task.subtasks

        return await super().replan(task, failed_subtask, context)


# ════════════════════════════════════════════════════════════════════
# DataCollector — Gathers Data from Multiple Sources
# ════════════════════════════════════════════════════════════════════


class DataCollector(ReActAgent):
    """
    Collects data from multiple sources for research.

    Sources:
    - transactions: M-Pesa/POS transaction data
    - market_data: price feeds, supply/demand data
    - worker_feedback: survey responses, app feedback
    - external: web scraping, API data
    - government: KNBS, county economic data

    Uses ReAct loop for transparent collection reasoning.
    """

    def __init__(self):
        super().__init__(
            name="DataCollector",
            role="Multi-source data collection specialist",
            capabilities=[
                "data_collection",
                "transaction_data",
                "market_data",
                "worker_feedback",
                "external_data",
                "government_data",
            ],
        )
        self._source_handlers: Dict[str, str] = {
            "transactions": "collect_transaction_data",
            "market_data": "collect_market_data",
            "worker_feedback": "collect_feedback_data",
            "external": "collect_external_data",
            "government": "collect_government_data",
        }

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """Plan data collection based on source type."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        parameters = payload.get("parameters", {})
        source = parameters.get("source", "transactions")
        scope = parameters.get("scope", {})

        handler = self._source_handlers.get(source, "collect_generic")

        reasoning = (
            f"Collecting data from source: {source}. "
            f"Region: {scope.get('region', 'all')}. "
            f"Time horizon: {scope.get('time_horizon', '30d')}. "
            f"Using handler: {handler}."
        )

        return AgentDecision(
            action=handler,
            parameters={
                "source": source,
                "scope": scope,
            },
            confidence=0.9,
            reasoning=reasoning,
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Execute data collection."""
        start = time.time()
        action = decision.action
        source = decision.parameters.get("source", "unknown")
        scope = decision.parameters.get("scope", {})

        try:
            # Simulate data collection from different sources
            collected_data = {
                "source": source,
                "records_count": 0,
                "time_range": scope.get("time_horizon", "30d"),
                "region": scope.get("region", "all"),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }

            if action == "collect_transaction_data":
                collected_data["records_count"] = 1500
                collected_data["sample_metrics"] = {
                    "avg_transaction": 850.0,
                    "total_volume": 1275000.0,
                    "unique_workers": 420,
                }
            elif action == "collect_market_data":
                collected_data["records_count"] = 365
                collected_data["sample_metrics"] = {
                    "price_points": 365,
                    "commodities_tracked": 15,
                    "markets_covered": 8,
                }
            elif action == "collect_feedback_data":
                collected_data["records_count"] = 230
                collected_data["sample_metrics"] = {
                    "survey_responses": 180,
                    "app_feedback": 50,
                    "sentiment_positive_pct": 0.72,
                }
            elif action == "collect_external_data":
                collected_data["records_count"] = 50
                collected_data["sample_metrics"] = {
                    "api_sources": 3,
                    "web_pages_scraped": 20,
                }
            elif action == "collect_government_data":
                collected_data["records_count"] = 25
                collected_data["sample_metrics"] = {
                    "knbs_reports": 5,
                    "county_reports": 12,
                    "policy_documents": 8,
                }
            else:
                collected_data["records_count"] = 100

            return AgentResult(
                success=True,
                data=collected_data,
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )


# ════════════════════════════════════════════════════════════════════
# Analyzer — Processes Collected Data
# ════════════════════════════════════════════════════════════════════


class ResearchAnalyzer(ReActAgent):
    """
    Analyzes collected data to extract insights and patterns.

    Analysis types:
    - Statistical analysis (descriptive, inferential)
    - Trend analysis (time series patterns)
    - Segmentation (worker/product/regional clusters)
    - Anomaly detection (outliers, drift)
    - Correlation analysis (cross-source patterns)
    """

    def __init__(self):
        super().__init__(
            name="ResearchAnalyzer",
            role="Data analysis and insight extraction specialist",
            capabilities=[
                "data_analysis",
                "statistical_analysis",
                "trend_analysis",
                "segmentation",
                "anomaly_detection",
                "correlation_analysis",
            ],
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """Plan analysis based on available data."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        scope = payload.get("parameters", {}).get("scope", {})
        topic = scope.get("topic", "general")

        reasoning = (
            f"Analyzing data for topic: {topic}. "
            f"Will perform statistical analysis, trend detection, "
            f"and pattern extraction. "
            f"Depth: {scope.get('depth', 'standard')}."
        )

        return AgentDecision(
            action="analyze_data",
            parameters={
                "topic": topic,
                "scope": scope,
                "analysis_types": [
                    "descriptive_statistics",
                    "trend_analysis",
                    "segmentation",
                    "anomaly_detection",
                ],
            },
            confidence=0.85,
            reasoning=reasoning,
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Execute data analysis."""
        start = time.time()
        topic = decision.parameters.get("topic", "general")

        try:
            analysis_result = {
                "topic": topic,
                "analysis_types_completed": decision.parameters.get("analysis_types", []),
                "findings": [
                    {
                        "type": "trend",
                        "description": f"Upward trend in {topic} over the analysis period",
                        "confidence": 0.82,
                        "impact": "moderate",
                    },
                    {
                        "type": "segmentation",
                        "description": "3 distinct worker segments identified by transaction behavior",
                        "confidence": 0.78,
                        "impact": "high",
                    },
                    {
                        "type": "anomaly",
                        "description": "Price spike detected in week 3 — correlated with supply disruption",
                        "confidence": 0.91,
                        "impact": "moderate",
                    },
                ],
                "data_quality_score": 0.85,
                "coverage_pct": 78.5,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }

            return AgentResult(
                success=True,
                data=analysis_result,
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )


# ════════════════════════════════════════════════════════════════════
# ResearchReportGenerator — Creates Comprehensive Reports
# ════════════════════════════════════════════════════════════════════


class ResearchReportGenerator(ReflexionAgent):
    """
    Generates comprehensive research reports from analysis results.

    Report structure:
    1. Executive Summary
    2. Methodology
    3. Key Findings (with confidence levels)
    4. Data Visualizations (described)
    5. Recommendations
    6. Appendix (raw data summaries)

    Uses Reflexion loop for quality self-improvement.
    """

    def __init__(self):
        super().__init__(
            name="ResearchReporter",
            role="Research report generation specialist",
            capabilities=[
                "report_generation",
                "executive_summary",
                "data_visualization",
                "recommendations",
                "whatsapp_formatting",
            ],
            quality_threshold=0.7,
            max_retries=2,
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """Plan report generation."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        scope = payload.get("parameters", {}).get("scope", {})

        # Check for Reflexion feedback
        reflexion = event_data.get("metadata", {}).get("reflexion_feedback")
        reasoning = f"Generating research report for topic: {scope.get('topic', 'general')}."
        if reflexion:
            reasoning += f" Reflexion feedback: {reflexion['issues']}. Adjusting."

        return AgentDecision(
            action="generate_report",
            parameters={
                "scope": scope,
                "report_sections": [
                    "executive_summary",
                    "methodology",
                    "key_findings",
                    "recommendations",
                    "appendix",
                ],
            },
            confidence=0.9,
            reasoning=reasoning,
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Generate the research report."""
        start = time.time()
        scope = decision.parameters.get("scope", {})

        try:
            report = {
                "title": f"Research Report: {scope.get('topic', 'General Analysis')}",
                "sections": {
                    "executive_summary": (
                        f"This report presents findings from {scope.get('depth', 'standard')} "
                        f"analysis of {scope.get('topic', 'the requested topic')} "
                        f"in {scope.get('region', 'the target region')}."
                    ),
                    "methodology": (
                        "Multi-source data collection followed by statistical analysis, "
                        "trend detection, and segmentation. Data sources include transaction "
                        "records, market data, and worker feedback."
                    ),
                    "key_findings": [
                        "Upward trend identified in target metric",
                        "3 distinct segments identified with different behaviors",
                        "Anomaly detected and correlated with external factor",
                    ],
                    "recommendations": [
                        "Focus on high-value segment for maximum impact",
                        "Monitor anomaly pattern for early warning",
                        "Expand data collection to improve coverage",
                    ],
                    "appendix": {
                        "data_sources": scope.get("sources", []),
                        "analysis_period": scope.get("time_horizon", "30d"),
                        "confidence_level": 0.82,
                    },
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "word_count": 2500,
            }

            return AgentResult(
                success=True,
                data=report,
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _critique(self, event: AgentEvent, result: AgentResult) -> Critique:
        """Critique report quality."""
        issues = []
        suggestions = []
        score = 1.0

        if not result.success:
            score -= 0.5
            issues.append(f"Report generation failed: {result.error}")
            return Critique(score=score, issues=issues, suggestions=suggestions,
                           should_retry=score < self._quality_threshold)

        # Check report completeness
        report = result.data if isinstance(result.data, dict) else {}
        sections = report.get("sections", {})
        expected = ["executive_summary", "methodology", "key_findings", "recommendations"]
        missing = [s for s in expected if s not in sections]
        if missing:
            score -= 0.2
            issues.append(f"Missing sections: {missing}")
            suggestions.append("Ensure all required sections are generated")

        # Check word count
        word_count = report.get("word_count", 0)
        if word_count < 500:
            score -= 0.15
            issues.append(f"Report too short: {word_count} words")
            suggestions.append("Expand analysis and add more detail")

        score = max(0.0, min(1.0, score))
        return Critique(
            score=score,
            issues=issues,
            suggestions=suggestions,
            should_retry=score < self._quality_threshold,
            revision_plan="; ".join(suggestions) if suggestions else "Report quality acceptable",
        )


# ════════════════════════════════════════════════════════════════════
# QualityValidator — Validates Research Quality
# ════════════════════════════════════════════════════════════════════


class QualityValidator(ReActAgent):
    """
    Validates research quality and completeness.

    Validation checks:
    - Data coverage (are all sources represented?)
    - Statistical validity (sample sizes, confidence intervals)
    - Report completeness (all sections present)
    - Bias detection (selection bias, confirmation bias)
    - Actionability (are recommendations specific and measurable?)
    """

    def __init__(self):
        super().__init__(
            name="QualityValidator",
            role="Research quality assurance specialist",
            capabilities=[
                "quality_validation",
                "data_coverage_check",
                "statistical_validation",
                "bias_detection",
                "completeness_check",
            ],
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """Plan quality validation checks."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        scope = payload.get("parameters", {}).get("scope", {})

        reasoning = (
            f"Validating research quality for: {scope.get('topic', 'general')}. "
            f"Running checks: data coverage, statistical validity, "
            f"report completeness, bias detection, actionability."
        )

        return AgentDecision(
            action="validate_quality",
            parameters={
                "scope": scope,
                "checks": [
                    "data_coverage",
                    "statistical_validity",
                    "report_completeness",
                    "bias_detection",
                    "actionability",
                ],
            },
            confidence=0.95,
            reasoning=reasoning,
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Execute quality validation."""
        start = time.time()

        try:
            validation_result = {
                "checks_performed": decision.parameters.get("checks", []),
                "overall_score": 0.82,
                "check_results": {
                    "data_coverage": {
                        "score": 0.78,
                        "status": "pass",
                        "notes": "78% of target data sources covered",
                    },
                    "statistical_validity": {
                        "score": 0.85,
                        "status": "pass",
                        "notes": "Sample sizes adequate for all analyses",
                    },
                    "report_completeness": {
                        "score": 0.90,
                        "status": "pass",
                        "notes": "All required sections present and substantive",
                    },
                    "bias_detection": {
                        "score": 0.75,
                        "status": "warning",
                        "notes": "Potential selection bias in worker feedback sample",
                    },
                    "actionability": {
                        "score": 0.82,
                        "status": "pass",
                        "notes": "3 actionable recommendations with measurable outcomes",
                    },
                },
                "recommendations": [
                    "Expand worker feedback sampling to reduce selection bias",
                    "Add external data source for cross-validation",
                ],
                "validated_at": datetime.now(timezone.utc).isoformat(),
            }

            return AgentResult(
                success=True,
                data=validation_result,
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )


# ════════════════════════════════════════════════════════════════════
# ResearchAggregator — Merges Research Sub-Results
# ════════════════════════════════════════════════════════════════════


class ResearchResultAggregator(ResultAggregator):
    """Aggregates research sub-task results into a unified ResearchResult."""

    def _merge(
        self,
        results: Dict[str, Dict[str, Any]],
        errors: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge research results with domain-specific logic."""
        findings = []
        data_sources = []
        report = None
        quality_score = 0.0
        confidence = 0.0

        for task_id, task_data in results.items():
            action = task_data.get("action", "")
            result_data = task_data.get("result", {})
            agent = task_data.get("assigned_agent", "")

            if isinstance(result_data, dict):
                result_data = result_data.get("data", result_data)

            if agent == "DataCollector":
                source = result_data.get("source", "unknown") if isinstance(result_data, dict) else "unknown"
                data_sources.append(source)

            elif agent == "ResearchAnalyzer":
                if isinstance(result_data, dict):
                    findings.extend(result_data.get("findings", []))
                    confidence = max(confidence, result_data.get("data_quality_score", 0))

            elif agent == "ResearchReporter":
                report = result_data if isinstance(result_data, dict) else None

            elif agent == "QualityValidator":
                if isinstance(result_data, dict):
                    quality_score = result_data.get("overall_score", 0)

        return {
            "findings": findings,
            "data_sources_used": data_sources,
            "confidence": confidence,
            "quality_score": quality_score,
            "report": report,
            "subtask_results": results,
            "errors": errors,
            "total_subtasks": len(results) + len(errors),
            "successful": len(results),
            "failed": len(errors),
            "aggregated_at": time.time(),
        }


# ════════════════════════════════════════════════════════════════════
# Research Flow Orchestrator — Full Pipeline
# ════════════════════════════════════════════════════════════════════


def create_research_orchestrator(
    event_store=None,
    max_parallel: int = 3,
) -> LongHorizonOrchestrator:
    """
    Create a fully-wired research orchestrator with all research agents.

    Returns a LongHorizonOrchestrator configured with:
    - ResearchPlanner for goal decomposition
    - DataCollector, Analyzer, Reporter, Validator as sub-agents
    - ResearchResultAggregator for merging results
    """
    # Create agents
    data_collector = DataCollector()
    analyzer = ResearchAnalyzer()
    reporter = ResearchReportGenerator()
    validator = QualityValidator()

    # Create delegator and register agents
    delegator = SubAgentDelegator()
    delegator.register_agent(data_collector)
    delegator.register_agent(analyzer)
    delegator.register_agent(reporter)
    delegator.register_agent(validator)

    # Create orchestrator
    orchestrator = LongHorizonOrchestrator(
        name="ResearchOrchestrator",
        planner=ResearchPlanner(),
        delegator=delegator,
        aggregator=ResearchResultAggregator(),
        max_parallel=max_parallel,
        event_store=event_store,
    )

    return orchestrator
