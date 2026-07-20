"""
Intelligence Pipeline — Domain Agents.

Four specialized ReActAgent implementations for the intelligence pipeline:
- MarketDataAgent      — market data collection and analysis
- CreditAnalysisAgent  — credit risk assessment
- DistributionAgent    — distribution gap analysis
- CompetitorAgent      — competitive intelligence
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import structlog

from app.agents.base import AgentDecision, AgentResult
from app.agents.loops import ReActAgent
from app.agents.pipeline_data import (
    _query_alama_score,
    _query_behavioral_data,
    _query_category_breakdown,
    _query_competitor_density,
    _query_distribution_data,
    _query_expansion_opportunities,
    _query_logistics_data,
    _query_market_prices,
    _query_repayment_data,
    _query_supply_demand,
    _query_transaction_history,
)

try:
    from app.services.ml.feature_engineering import FeatureEngineer
    from app.services.ml.xgboost_service import XGBoostService
    _ml_pipeline_available = True
    _ml_service_pipeline = XGBoostService()
except ImportError:
    _ml_pipeline_available = False
    _ml_service_pipeline = None

logger = structlog.get_logger(__name__)


class MarketDataAgent(ReActAgent):
    """Agent specialized in market data collection and analysis."""

    def __init__(self):
        super().__init__(
            name="MarketDataAgent",
            role="Market data collection and analysis specialist",
            capabilities=[
                "market_data", "price_analysis", "supply_demand",
                "market_data_collection", "price_collection",
                "trade_volume", "competitor_data",
            ],
        )

    async def _think_reasoning(self, context: dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        action = params.get("action", payload.get("action", "collect_market_data"))
        return AgentDecision(action=action, parameters=params, confidence=0.9,
                             reasoning=f"Market data agent executing: {action}")

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        try:
            action = decision.action
            params = decision.parameters
            region = params.get("region", "Nairobi")
            data: dict[str, Any] = {
                "action": action, "status": "completed",
                "timestamp": datetime.now(UTC).isoformat(),
            }

            if "price" in action:
                db_prices = await _query_market_prices(region)
                if db_prices["data_points"] > 0:
                    data["prices"] = db_prices["prices"]
                    data["data_points"] = db_prices["data_points"]
                else:
                    data["prices"] = {"avg": None, "min": None, "max": None}
                    data["data_points"] = 0
                    data["source"] = "no_data_available"
                if _ml_pipeline_available and _ml_service_pipeline:
                    try:
                        ml_features = {
                            "rfm_monetary_avg": data["prices"].get("avg", 0) or 0,
                            "derived_rev_7d": data["prices"].get("avg", 0) or 0,
                        }
                        ml_demand = _ml_service_pipeline.predict_demand(ml_features)
                        if ml_demand.get("available"):
                            data["ml_demand_forecast"] = {
                                "predicted_volume": ml_demand.get("predicted_volume"),
                                "confidence": ml_demand.get("confidence"),
                                "method": "xgboost",
                            }
                    except Exception as ml_err:
                        logger.debug("ml_demand_forecast_failed", error=str(ml_err))
            elif "supply" in action or "demand" in action:
                sd_data = await _query_supply_demand(region, params.get("product"))
                data["supply_demand"] = {
                    "supply_index": sd_data["supply_index"],
                    "demand_index": sd_data["demand_index"],
                    "gap": sd_data["gap"],
                    "supply_volume": sd_data.get("supply_volume"),
                    "demand_volume": sd_data.get("demand_volume"),
                }
                data["source"] = sd_data["source"]
            elif "trade" in action or "volume" in action:
                db_dist = await _query_distribution_data(params.get("product", ""))
                if db_dist["regions"]:
                    data["trade_volume"] = {
                        "total_volume": sum(r["volume"] for r in db_dist["regions"]),
                        "total_transactions": sum(r["txn_count"] for r in db_dist["regions"]),
                    }
                else:
                    data["trade_volume"] = {"total_volume": 0, "total_transactions": 0}
                    data["source"] = "no_data_available"
            elif "competitor" in action:
                comp_data = await _query_competitor_density(region, params.get("product"))
                data["competitors"] = {
                    "count": comp_data["distinct_sellers"],
                    "density": comp_data["competitor_density"],
                    "total_volume": comp_data.get("total_volume"),
                }
                data["source"] = comp_data["source"]
            else:
                data["market_overview"] = {"status": "data_driven", "volatility": "unknown"}

            return AgentResult(success=True, data=data, duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)


class CreditAnalysisAgent(ReActAgent):
    """Agent specialized in credit risk analysis."""

    def __init__(self):
        super().__init__(
            name="CreditAnalysisAgent",
            role="Credit risk assessment specialist",
            capabilities=[
                "credit_scoring", "risk_assessment", "credit_analysis",
                "transaction_history", "repayment_analysis",
                "behavioral_scoring", "creditworthiness",
            ],
        )

    async def _think_reasoning(self, context: dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        action = params.get("action", payload.get("action", "analyze_credit"))
        return AgentDecision(action=action, parameters=params, confidence=0.85,
                             reasoning=f"Credit analysis agent executing: {action}")

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        try:
            action = decision.action
            params = decision.parameters
            worker_id = params.get("worker_id", "unknown")
            data: dict[str, Any] = {
                "action": action, "status": "completed",
                "timestamp": datetime.now(UTC).isoformat(),
            }

            if "history" in action or "transaction" in action:
                history = await _query_transaction_history(worker_id)
                data["transaction_history"] = {
                    "total_transactions": history["total_transactions"],
                    "avg_amount": history.get("avg_amount", 0),
                    "first_transaction": history.get("first_transaction"),
                    "last_transaction": history.get("last_transaction"),
                    "source": history["source"],
                }
            elif "repay" in action:
                repay_data = await _query_repayment_data(worker_id)
                if repay_data["has_data"]:
                    data["repayment"] = {
                        "on_time_rate": repay_data["on_time_rate"],
                        "completed_loans": repay_data["completed_loans"],
                        "defaulted_loans": repay_data["defaulted_loans"],
                        "active_loans": repay_data["active_loans"],
                        "completion_rate": repay_data["completion_rate"],
                        "default_rate": repay_data["default_rate"],
                        "total_borrowed": repay_data["total_borrowed"],
                        "total_repaid": repay_data["total_repaid"],
                        "avg_streak": repay_data["avg_streak"],
                        "best_streak": repay_data["best_streak"],
                        "total_repayments": repay_data["total_repayments"],
                    }
                else:
                    data["repayment"] = {"on_time_rate": None, "completed_loans": 0, "defaulted_loans": 0}
                data["source"] = repay_data["source"]
            elif "behavior" in action:
                behav_data = await _query_behavioral_data(worker_id)
                if behav_data["has_data"]:
                    data["behavioral_score"] = {
                        "regularity": behav_data["regularity"],
                        "growth_trend": behav_data["growth_trend"],
                        "risk_flags": behav_data["risk_flags"],
                        "months_analyzed": behav_data["months_analyzed"],
                        "total_transactions": behav_data["total_transactions"],
                        "avg_transaction_amount": behav_data["avg_transaction_amount"],
                        "distinct_products": behav_data["distinct_products"],
                    }
                else:
                    data["behavioral_score"] = {"regularity": None, "growth_trend": "unknown", "risk_flags": []}
                data["source"] = behav_data["source"]
            elif "creditworthiness" in action or "credit_score" in action:
                score_data = await _query_alama_score(worker_id)
                if score_data["has_score"]:
                    band = score_data.get("band", "unknown")
                    data["credit_score"] = {
                        "score": score_data["score"], "rating": band,
                        "confidence": 0.85 if score_data["source"] == "database" else 0.7,
                        "percentile": score_data.get("percentile"),
                        "components": {
                            "activity": score_data.get("activity_score"),
                            "stability": score_data.get("stability_score"),
                            "growth": score_data.get("growth_score"),
                            "consistency": score_data.get("consistency_score"),
                            "diversity": score_data.get("diversity_score"),
                        },
                        "default_probability": score_data.get("default_probability"),
                        "recommended_credit_limit": score_data.get("recommended_credit_limit"),
                    }
                    if _ml_pipeline_available and _ml_service_pipeline:
                        try:
                            behav_data = await _query_behavioral_data(worker_id)
                            if behav_data.get("has_data"):
                                ml_features = FeatureEngineer.extract_all_features([])
                                ml_features["rfm_frequency"] = float(behav_data.get("total_transactions", 0))
                                ml_features["rfm_monetary_avg"] = float(behav_data.get("avg_transaction_amount", 0))
                                ml_credit = _ml_service_pipeline.predict_credit_score(
                                    ml_features, classical_score=score_data["score"],
                                )
                                if ml_credit.get("available"):
                                    data["credit_score"]["ml_enhancement"] = {
                                        "ml_score": ml_credit.get("ml_score"),
                                        "ensemble_score": ml_credit.get("ensemble_score"),
                                        "default_probability_ml": ml_credit.get("default_probability"),
                                        "shap_top_features": ml_credit.get("shap_explanation", {}).get("top_contributors", [])[:5],
                                    }
                        except Exception as ml_err:
                            logger.debug("ml_credit_enhancement_failed", error=str(ml_err))
                else:
                    data["credit_score"] = {"score": None, "rating": "no_data", "confidence": 0.0}
                data["source"] = score_data["source"]
            else:
                data["credit_overview"] = {"risk_level": "unknown", "creditworthy": None}

            return AgentResult(success=True, data=data, duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)


class DistributionAgent(ReActAgent):
    """Agent specialized in distribution gap analysis."""

    def __init__(self):
        super().__init__(
            name="DistributionAgent",
            role="Distribution gap analysis specialist",
            capabilities=[
                "distribution_analysis", "gap_analysis", "distribution_mapping",
                "coverage_analysis", "logistics_analysis",
                "demand_mapping", "expansion_planning",
            ],
        )

    async def _think_reasoning(self, context: dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        action = params.get("action", payload.get("action", "analyze_distribution"))
        return AgentDecision(action=action, parameters=params, confidence=0.88,
                             reasoning=f"Distribution agent executing: {action}")

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        try:
            action = decision.action
            params = decision.parameters
            product = params.get("product", "")
            data: dict[str, Any] = {
                "action": action, "status": "completed",
                "timestamp": datetime.now(UTC).isoformat(),
            }

            if "mapping" in action or "coverage" in action:
                dist_data = await _query_distribution_data(product)
                if dist_data["regions"]:
                    regions_covered = len(dist_data["regions"])
                    data["coverage"] = {
                        "regions_covered": regions_covered, "regions_total": 47,
                        "coverage_pct": round(regions_covered / 47 * 100, 1),
                        "regions": dist_data["regions"],
                    }
                else:
                    data["coverage"] = {"regions_covered": 0, "regions_total": 47, "coverage_pct": 0.0}
                    data["source"] = "no_data_available"
            elif "logistics" in action:
                log_data = await _query_logistics_data(product)
                if log_data["has_data"]:
                    data["logistics"] = {
                        "total_distribution_areas": log_data["total_distribution_areas"],
                        "total_volume": log_data["total_volume"],
                        "top_areas": log_data["top_areas"],
                        "bottlenecks": log_data["bottlenecks"],
                        "avg_volume_per_area": log_data["avg_volume_per_area"],
                    }
                else:
                    data["logistics"] = {"total_distribution_areas": 0, "bottlenecks": []}
                data["source"] = log_data["source"]
            elif "demand" in action:
                dist_data = await _query_distribution_data(product)
                if dist_data["regions"]:
                    sorted_regions = sorted(dist_data["regions"], key=lambda r: r["volume"], reverse=True)
                    data["demand_map"] = {
                        "high_demand": [r["region"] for r in sorted_regions[:5]],
                        "total_regions_with_data": len(sorted_regions),
                    }
                else:
                    data["demand_map"] = {"high_demand": [], "total_regions_with_data": 0}
                    data["source"] = "no_data_available"
            elif "expansion" in action:
                exp_data = await _query_expansion_opportunities(product)
                if exp_data["has_data"]:
                    data["expansion"] = {
                        "priority_regions": exp_data["priority_regions"],
                        "total_covered_regions": exp_data["total_covered_regions"],
                        "total_volume": exp_data["total_volume"],
                        "total_active_users": exp_data["total_active_users"],
                    }
                else:
                    data["expansion"] = {"priority_regions": [], "total_covered_regions": 0}
                data["source"] = exp_data["source"]
            else:
                data["distribution_overview"] = {"gaps_identified": None, "opportunities": None}

            return AgentResult(success=True, data=data, duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)


class CompetitorAgent(ReActAgent):
    """Agent specialized in competitive intelligence."""

    def __init__(self):
        super().__init__(
            name="CompetitorAgent",
            role="Competitive intelligence specialist",
            capabilities=[
                "competitor_analysis", "competitive_intelligence", "competitor_mapping",
                "pricing_analysis", "feature_comparison",
                "market_positioning", "threat_assessment",
            ],
        )

    async def _think_reasoning(self, context: dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        action = params.get("action", payload.get("action", "analyze_competitors"))
        return AgentDecision(action=action, parameters=params, confidence=0.87,
                             reasoning=f"Competitor agent executing: {action}")

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        try:
            action = decision.action
            params = decision.parameters
            market = params.get("market", "Kenya")
            data: dict[str, Any] = {
                "action": action, "status": "completed",
                "timestamp": datetime.now(UTC).isoformat(),
            }

            if "mapping" in action:
                comp_data = await _query_competitor_density(market, params.get("product"))
                data["competitor_map"] = {
                    "direct_competitors": comp_data["distinct_sellers"],
                    "density": comp_data["competitor_density"],
                    "total_market_volume": comp_data.get("total_volume"),
                }
                data["source"] = comp_data["source"]
            elif "pricing" in action:
                prices = await _query_market_prices(market, params.get("product"))
                if prices["data_points"] > 0:
                    data["pricing_analysis"] = {
                        "market_avg": prices["prices"].get("avg"),
                        "market_min": prices["prices"].get("min"),
                        "market_max": prices["prices"].get("max"),
                        "data_points": prices["data_points"],
                    }
                else:
                    data["pricing_analysis"] = {"market_avg": None, "data_points": 0}
                data["source"] = prices["source"]
            elif "feature" in action:
                cat_data = await _query_category_breakdown()
                data["feature_comparison"] = {
                    "market_categories": cat_data["market_categories"],
                    "total_categories": cat_data["total_categories"],
                }
                data["source"] = cat_data["source"]
            elif "positioning" in action:
                comp_data = await _query_competitor_density(market)
                data["positioning"] = {
                    "market_density": comp_data["competitor_density"],
                    "total_sellers": comp_data["distinct_sellers"],
                    "differentiator": "informal_economy_focus",
                }
                data["source"] = comp_data["source"]
            elif "threat" in action:
                comp_data = await _query_competitor_density(market)
                sd_data = await _query_supply_demand(market)
                threat_level = "low"
                if comp_data["competitor_density"] in ("very_high", "high"):
                    threat_level = "high"
                elif comp_data["competitor_density"] == "moderate":
                    threat_level = "medium"
                data["threats"] = [{
                    "type": "market_competition", "level": threat_level,
                    "competitors": comp_data["distinct_sellers"],
                    "supply_demand_gap": sd_data.get("gap"),
                }]
                data["source"] = comp_data["source"]
            else:
                comp_data = await _query_competitor_density(market)
                data["competitor_overview"] = {
                    "total_competitors": comp_data["distinct_sellers"],
                    "density": comp_data["competitor_density"],
                }
                data["source"] = comp_data["source"]

            return AgentResult(success=True, data=data, duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)
