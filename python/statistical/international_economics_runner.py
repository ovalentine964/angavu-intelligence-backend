#!/usr/bin/env python3
"""
International Economics & Public Finance Runner — CLI bridge.

Called by Rust via subprocess with JSON input:
    python3 international_economics_runner.py '{"method": "exchange_rate_convert", "args": {...}}'

Returns JSON output to stdout.
"""

import json
import sys
import traceback

import numpy as np

try:
    from international_economics import (
        ExchangeRateTracker,
        CrossBorderTradeAdvisor,
        FiscalPolicyAnalyzer,
        MarketStructureAnalyzer,
    )
except ImportError:
    from python.statistical.international_economics import (
        ExchangeRateTracker,
        CrossBorderTradeAdvisor,
        FiscalPolicyAnalyzer,
        MarketStructureAnalyzer,
    )


def _to_serializable(obj):
    """Convert numpy types for JSON."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    elif isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    elif isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_to_serializable(v) for v in obj]
    return obj


def dispatch(method: str, args: dict) -> dict:
    """Dispatch method call."""

    if method == "exchange_rate_convert":
        tracker = ExchangeRateTracker()
        amount = args["amount"]
        from_cur = args["from_currency"]
        to_cur = args.get("to_currency", "KES")
        rates = args.get("rates")
        return _to_serializable(tracker.convert(amount, from_cur, to_cur, rates))

    elif method == "real_exchange_rate":
        tracker = ExchangeRateTracker()
        return _to_serializable(tracker.real_exchange_rate(
            args["nominal_rate"], args["domestic_cpi"], args["foreign_cpi"]
        ))

    elif method == "ppp_implied_rate":
        tracker = ExchangeRateTracker()
        return _to_serializable(tracker.ppp_implied_rate(
            args["domestic_price"], args["foreign_price"]
        ))

    elif method == "trade_cost":
        advisor = CrossBorderTradeAdvisor()
        return _to_serializable(advisor.trade_cost_analysis(
            args["product_value_kes"],
            args["destination"],
            args.get("product_category", "finished_goods"),
            args.get("exchange_rates"),
        ))

    elif method == "comparative_advantage":
        advisor = CrossBorderTradeAdvisor()
        return _to_serializable(advisor.comparative_advantage(
            args["local_cost"], args["foreign_cost"], args["exchange_rate"]
        ))

    elif method == "tax_burden":
        analyzer = FiscalPolicyAnalyzer()
        return _to_serializable(analyzer.tax_burden_analysis(
            args["annual_revenue"],
            args.get("employee_count", 0),
            args.get("monthly_expenses", 0),
        ))

    elif method == "deadweight_loss":
        analyzer = FiscalPolicyAnalyzer()
        return _to_serializable(analyzer.deadweight_loss(
            args["tax_rate"], args["elasticity"], args["quantity"], args["price"]
        ))

    elif method == "fiscal_multiplier":
        analyzer = FiscalPolicyAnalyzer()
        return _to_serializable(analyzer.fiscal_multiplier(
            args["government_spending"], args["mpc"], args["tax_rate"]
        ))

    elif method == "market_structure":
        analyzer = MarketStructureAnalyzer()
        return _to_serializable(analyzer.market_structure_assessment(
            args["market_shares"],
            args["firm_count"],
            args.get("entry_cost_kes", 0),
            args.get("annual_revenue", 0),
        ))

    elif method == "lerner_index":
        analyzer = MarketStructureAnalyzer()
        return _to_serializable(analyzer.lerner_index(args["price"], args["marginal_cost"]))

    elif method == "hhi":
        analyzer = MarketStructureAnalyzer()
        return _to_serializable(analyzer.herfindahl_hirschman_index(args["market_shares"]))

    else:
        return {"error": f"Unknown method: {method}"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: international_economics_runner.py '<json>'"}))
        sys.exit(1)

    try:
        input_data = json.loads(sys.argv[1])
        method = input_data["method"]
        args = input_data.get("args", {})
        result = dispatch(method, args)
        print(json.dumps(result))
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
        sys.exit(1)


if __name__ == "__main__":
    main()
