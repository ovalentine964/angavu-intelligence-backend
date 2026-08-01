#!/usr/bin/env python3
"""
Time Series Models Runner — CLI bridge between Rust backend and time series methods.

Called by Rust via subprocess with JSON input:
    python3 time_series_runner.py '{"method": "arima_fit", "args": {...}}'

Returns JSON output to stdout.
"""

import json
import sys
import traceback

import numpy as np

try:
    from time_series_models import ARIMAModel, SARIMAModel, ETSModel, StructuralBreakTests
except ImportError:
    from python.statistical.time_series_models import ARIMAModel, SARIMAModel, ETSModel, StructuralBreakTests


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
    elif isinstance(obj, tuple):
        return list(obj)
    return obj


def dispatch(method: str, args: dict) -> dict:
    """Dispatch method call to the appropriate class/function."""

    if method == "arima_identify":
        data = np.array(args["data"], dtype=float)
        max_p = args.get("max_p", 5)
        max_d = args.get("max_d", 2)
        max_q = args.get("max_q", 5)
        return _to_serializable(ARIMAModel.identify(data, max_p, max_d, max_q))

    elif method == "arima_fit":
        data = np.array(args["data"], dtype=float)
        order = tuple(args.get("order", [1, 1, 1]))
        return _to_serializable(ARIMAModel.fit(data, order))

    elif method == "arima_diagnose":
        residuals = np.array(args["residuals"], dtype=float)
        n_params = args.get("n_params", 2)
        return _to_serializable(ARIMAModel.diagnose(residuals, n_params))

    elif method == "sarima_fit":
        data = np.array(args["data"], dtype=float)
        order = tuple(args.get("order", [1, 1, 1]))
        seasonal_order = tuple(args.get("seasonal_order", [1, 1, 1, 12]))
        return _to_serializable(SARIMAModel.fit(data, order, seasonal_order))

    elif method == "ets_fit":
        data = np.array(args["data"], dtype=float)
        model_type = args.get("model_type", "AAN")
        seasonal_period = args.get("seasonal_period", 7)
        return _to_serializable(ETSModel.fit(data, model_type, seasonal_period))

    elif method == "ets_auto":
        data = np.array(args["data"], dtype=float)
        seasonal_period = args.get("seasonal_period", 7)
        return _to_serializable(ETSModel.auto_select(data, seasonal_period))

    elif method == "chow_test":
        y = np.array(args["y"], dtype=float)
        X = np.array(args["X"], dtype=float)
        break_point = int(args["break_point"])
        return _to_serializable(StructuralBreakTests.chow_test(y, X, break_point))

    elif method == "cusum_test":
        y = np.array(args["y"], dtype=float)
        X = np.array(args["X"], dtype=float)
        alpha = args.get("alpha", 0.05)
        return _to_serializable(StructuralBreakTests.cusum_test(y, X, alpha))

    elif method == "bai_perron":
        y = np.array(args["y"], dtype=float)
        X = np.array(args["X"], dtype=float)
        max_breaks = args.get("max_breaks", 5)
        min_segment = args.get("min_segment", 10)
        return _to_serializable(StructuralBreakTests.bai_perron(y, X, max_breaks, min_segment))

    else:
        return {"error": f"Unknown method: {method}", "method": method}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: time_series_runner.py '<json_input>'"}))
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
