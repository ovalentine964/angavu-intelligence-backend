#!/usr/bin/env python3
"""
Nonparametric Extended Runner — CLI bridge for advanced non-parametric methods.

Called by Rust via subprocess with JSON input:
    python3 nonparametric_extended_runner.py '{"method": "friedman", "args": {...}}'

Returns JSON output to stdout.
"""

import json
import sys
import traceback

import numpy as np

try:
    from nonparametric_extended import (
        FriedmanTest,
        KolmogorovSmirnovTest,
        AndersonDarlingTest,
        LOESSRegression,
        BootstrapBCa,
        NonparametricSplineRegression,
    )
except ImportError:
    from python.statistical.nonparametric_extended import (
        FriedmanTest,
        KolmogorovSmirnovTest,
        AndersonDarlingTest,
        LOESSRegression,
        BootstrapBCa,
        NonparametricSplineRegression,
    )


def dispatch(method: str, args: dict) -> dict:
    """Dispatch method call to the appropriate class/function."""

    if method == "friedman":
        data = [list(map(float, row)) for row in args["data"]]
        return FriedmanTest.test(data)

    elif method == "ks_one_sample":
        data = list(map(float, args["data"]))
        distribution = args.get("distribution", "norm")
        params = args.get("params")
        return KolmogorovSmirnovTest.one_sample(data, distribution=distribution, params=params)

    elif method == "ks_two_sample":
        sample1 = list(map(float, args["sample1"]))
        sample2 = list(map(float, args["sample2"]))
        return KolmogorovSmirnovTest.two_sample(sample1, sample2)

    elif method == "anderson_darling":
        data = list(map(float, args["data"]))
        distribution = args.get("distribution", "norm")
        return AndersonDarlingTest.test(data, distribution=distribution)

    elif method == "loess":
        x = list(map(float, args["x"]))
        y = list(map(float, args["y"]))
        span = args.get("span", 0.3)
        degree = args.get("degree", 1)
        n_points = args.get("n_points", 100)
        return LOESSRegression.fit(x, y, span=span, degree=int(degree), n_points=int(n_points))

    elif method == "bootstrap_bca":
        data = list(map(float, args["data"]))
        stat_name = args.get("statistic", "mean")
        n_bootstrap = args.get("n_bootstrap", 5000)
        confidence = args.get("confidence", 0.95)

        stat_fn_map = {
            "mean": np.mean,
            "median": np.median,
            "std": np.std,
            "var": np.var,
        }
        stat_fn = stat_fn_map.get(stat_name, np.mean)
        return BootstrapBCa.confidence_interval(
            data, statistic_fn=stat_fn,
            n_bootstrap=int(n_bootstrap), confidence=confidence
        )

    elif method == "spline_regression":
        x = list(map(float, args["x"]))
        y = list(map(float, args["y"]))
        smoothing = args.get("smoothing_factor")
        n_points = args.get("n_points", 200)
        return NonparametricSplineRegression.fit(
            x, y, smoothing_factor=smoothing, n_points=int(n_points)
        )

    else:
        return {"error": f"Unknown method: {method}", "method": method}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: nonparametric_extended_runner.py '<json_input>'"}))
        sys.exit(1)

    try:
        input_data = json.loads(sys.argv[1])
        method = input_data["method"]
        args = input_data.get("args", {})
        result = dispatch(method, args)
        print(json.dumps(result, default=str))
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)
    except KeyError as e:
        print(json.dumps({"error": f"Missing required field: {e}"}))
        sys.exit(1)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
        sys.exit(1)


if __name__ == "__main__":
    main()
