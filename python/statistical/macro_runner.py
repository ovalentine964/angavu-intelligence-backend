#!/usr/bin/env python3
"""
Macroeconomic Models Runner — CLI bridge between Rust backend and macro methods.

Called by Rust via subprocess with JSON input:
    python3 macro_runner.py '{"method": "phillips_curve", "args": {...}}'

Returns JSON output to stdout.
"""

import json
import sys
import traceback

import numpy as np

try:
    from macro_models import (
        PhillipsCurve, ISLMModel, SolowGrowthModel,
        DemographicModels, TaylorRule, OkunsLaw,
        FisherEquation, MoneyMultiplier,
    )
except ImportError:
    from python.statistical.macro_models import (
        PhillipsCurve, ISLMModel, SolowGrowthModel,
        DemographicModels, TaylorRule, OkunsLaw,
        FisherEquation, MoneyMultiplier,
    )


def _to_serializable(obj):
    """Convert numpy types to Python native types for JSON."""
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
    """Dispatch method call to the appropriate class/function."""

    if method == "phillips_estimate":
        inflation = np.array(args["inflation"], dtype=float)
        unemployment = np.array(args["unemployment"], dtype=float)
        expected = np.array(args["expected_inflation"], dtype=float) if args.get("expected_inflation") else None
        m = args.get("method", "adaptive")
        return _to_serializable(PhillipsCurve.estimate(inflation, unemployment, expected, m))

    elif method == "phillips_simulate":
        return _to_serializable(PhillipsCurve.simulate(
            args["nairu"], args["beta"], args["expected_inflation"],
            np.array(args["unemployment_path"], dtype=float),
            args.get("initial_inflation", 5.0),
        ))

    elif method == "islm_solve":
        params = {k: v for k, v in args.items() if k != "method"}
        return _to_serializable(ISLMModel.solve(**params))

    elif method == "islm_fiscal_shock":
        return _to_serializable(ISLMModel.fiscal_shock(args["base_params"], args["delta_g"]))

    elif method == "islm_monetary_shock":
        return _to_serializable(ISLMModel.monetary_shock(args["base_params"], args["delta_m"]))

    elif method == "solow_steady_state":
        params = {k: v for k, v in args.items() if k != "method"}
        return _to_serializable(SolowGrowthModel.solve_steady_state(**params))

    elif method == "solow_simulate":
        return _to_serializable(SolowGrowthModel.simulate_transition(
            args["initial_k"],
            args.get("savings_rate", 0.18),
            args.get("population_growth", 0.02),
            args.get("depreciation", 0.05),
            args.get("technology_growth", 0.02),
            args.get("capital_share", 0.33),
            args.get("n_periods", 100),
        ))

    elif method == "life_table":
        qx = np.array(args["age_specific_mortality"], dtype=float)
        radix = args.get("radix", 100000)
        return _to_serializable(DemographicModels.life_table(qx, radix))

    elif method == "population_projection":
        return _to_serializable(DemographicModels.population_projection(
            np.array(args["initial_population"], dtype=float),
            np.array(args["fertility_rates"], dtype=float),
            np.array(args["survival_rates"], dtype=float),
            args.get("n_years", 20),
            np.array(args["net_migration"], dtype=float) if args.get("net_migration") else None,
        ))

    elif method == "taylor_rule":
        params = {k: v for k, v in args.items() if k != "method"}
        return _to_serializable(TaylorRule.compute(**params))

    elif method == "taylor_estimate":
        return _to_serializable(TaylorRule.estimate_reaction_function(
            np.array(args["actual_rates"], dtype=float),
            np.array(args["inflation"], dtype=float),
            np.array(args["output_gap"], dtype=float),
        ))

    elif method == "okun_estimate":
        return _to_serializable(OkunsLaw.estimate(
            np.array(args["gdp_growth"], dtype=float),
            np.array(args["unemployment_change"], dtype=float),
        ))

    elif method == "okun_predict":
        return _to_serializable(OkunsLaw.predict_unemployment_change(
            args["gdp_growth"],
            args.get("okun_coefficient", -0.4),
            args.get("intercept", 0.5),
        ))

    elif method == "fisher":
        params = {k: v for k, v in args.items() if k != "method"}
        return _to_serializable(FisherEquation.compute(**params))

    elif method == "money_multiplier":
        params = {k: v for k, v in args.items() if k != "method"}
        return _to_serializable(MoneyMultiplier.compute(**params))

    elif method == "money_expansion":
        return _to_serializable(MoneyMultiplier.simulate_monetary_expansion(
            args["initial_base"], args["target_m1"],
            args.get("reserve_ratio", 0.0425),
            args.get("currency_deposit_ratio", 0.30),
            args.get("excess_reserve_ratio", 0.02),
        ))

    else:
        return {"error": f"Unknown method: {method}", "method": method}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: macro_runner.py '<json_input>'"}))
        sys.exit(1)

    try:
        input_data = json.loads(sys.argv[1])
        method = input_data["method"]
        args = input_data.get("args", {})
        result = dispatch(method, args)
        print(json.dumps(result))
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)
    except KeyError as e:
        print(json.dumps({"error": f"Missing field: {e}"}))
        sys.exit(1)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
        sys.exit(1)


if __name__ == "__main__":
    main()
