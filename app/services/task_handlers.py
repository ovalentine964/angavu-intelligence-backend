"""
Registered task handlers for the background task queue.

Each handler is an async function that receives a payload dict
and returns a result dict. Register with @register_handler.

These run inside the worker process (app/worker.py).
"""

import logging

from app.services.task_queue import register_handler

logger = logging.getLogger(__name__)


@register_handler("report_generation")
async def handle_report_generation(payload: dict) -> dict:
    """
    Generate a report (monthly, weekly, etc.) in the background.

    Payload:
        business_id: str
        report_type: str ("monthly", "weekly", "custom")
        date_from: str (ISO date)
        date_to: str (ISO date)
    """
    logger.info("generating_report", payload=payload)
    # Heavy computation would go here — statistical analysis,
    # chart generation, PDF rendering, etc.
    # For now, this is a stub that the team fills in.
    return {
        "status": "generated",
        "report_type": payload.get("report_type", "unknown"),
        "business_id": payload.get("business_id"),
    }


@register_handler("model_training")
async def handle_model_training(payload: dict) -> dict:
    """
    Run a training cycle, typically triggered by drift detection.

    Payload:
        model_type: str (e.g. "credit_scoring", "market_forecast")
        trigger: str ("drift_alert", "scheduled", "manual")
        alert: dict (drift alert details, if triggered by drift)
    """
    from app.services.training.loop import TrainingLoop

    model_type = payload.get("model_type", "intent_classifier")
    trigger = payload.get("trigger", "scheduled")

    logger.info(
        "training_cycle_starting",
        model_type=model_type,
        trigger=trigger,
    )

    loop = TrainingLoop()
    summary = await loop.run_training_cycle(model_type)

    result = {
        "status": summary.status.value,
        "model_type": model_type,
        "trigger": trigger,
        "cycle_id": summary.cycle_id,
        "phases_completed": [p.value for p in summary.phases_completed],
        "improvement_achieved": summary.improvement_achieved,
        "deployed": summary.deployed,
        "signals_collected": summary.signals_collected,
    }

    if summary.error:
        result["error"] = summary.error

    logger.info("training_cycle_completed", **result)
    return result


@register_handler("data_aggregation")
async def handle_data_aggregation(payload: dict) -> dict:
    """
    Run daily / weekly / monthly data aggregation.

    Payload:
        aggregation_type: str ("daily", "weekly", "monthly")
        date: str (ISO date to aggregate)
        region: str (optional)
    """
    agg_type = payload.get("aggregation_type", "daily")
    logger.info("aggregating_data", type=agg_type, date=payload.get("date"))
    # Pre-compute aggregates for dashboards and analytics
    return {
        "status": "aggregated",
        "aggregation_type": agg_type,
        "date": payload.get("date"),
    }


@register_handler("intelligence_update")
async def handle_intelligence_update(payload: dict) -> dict:
    """
    Refresh intelligence products (Alama Score, Soko Pulse, etc.).

    Payload:
        product_type: str
        region: str (optional)
        force: bool (skip cache check)
    """
    logger.info("updating_intelligence", product=payload.get("product_type"))
    return {
        "status": "updated",
        "product_type": payload.get("product_type"),
    }


@register_handler("price_aggregation")
async def handle_price_aggregation(payload: dict) -> dict:
    """
    Aggregate market prices from transaction data.

    Payload:
        market_id: str
        period: str ("hourly", "daily")
    """
    logger.info("aggregating_prices", market=payload.get("market_id"))
    return {
        "status": "aggregated",
        "market_id": payload.get("market_id"),
    }


@register_handler("cache_warmup")
async def handle_cache_warmup(payload: dict) -> dict:
    """
    Pre-populate cache with hot data.

    Payload:
        regions: list of region IDs
        data_types: list of data types to warm ("prices", "profiles", "intelligence")
    """
    from app.services.cache import get_cache

    cache = get_cache()
    logger.info("cache_warmup_started", regions=payload.get("regions"))
    # In production, this would query the DB and populate Redis
    # for the most frequently accessed data
    return {
        "status": "warmed",
        "regions": payload.get("regions"),
    }
