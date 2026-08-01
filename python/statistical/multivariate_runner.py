#!/usr/bin/env python3
"""
Multivariate Runner — CLI bridge between Rust backend and multivariate methods.

Called by Rust via subprocess with JSON input:
    python3 multivariate_runner.py '{"method": "pca", "args": {...}}'

Returns JSON output to stdout.
"""

import json
import sys
import traceback

import numpy as np

try:
    from multivariate import PCAAnalysis, DBSCANClusterer, LDAClassifier, QDAClassifier, MANOVATest
except ImportError:
    from python.statistical.multivariate import PCAAnalysis, DBSCANClusterer, LDAClassifier, QDAClassifier, MANOVATest


def dispatch(method: str, args: dict) -> dict:
    """Dispatch method call to the appropriate class/function."""

    if method == "pca":
        data = np.array(args["data"], dtype=float)
        n_components = args.get("n_components")
        if n_components is not None:
            n_components = int(n_components)
        return PCAAnalysis.fit(data, n_components=n_components)

    elif method == "dbscan":
        data = np.array(args["data"], dtype=float)
        eps = args.get("eps", 0.5)
        min_pts = args.get("min_pts", 5)
        return DBSCANClusterer.fit(data, eps=eps, min_pts=int(min_pts))

    elif method == "lda":
        X = np.array(args["X"], dtype=float)
        y = np.array(args["y"], dtype=int)
        result = LDAClassifier.fit(X, y)

        # Predict on new data if provided
        if "X_new" in args:
            X_new = np.array(args["X_new"], dtype=float)
            pred = LDAClassifier.predict(X_new, result)
            result["new_predictions"] = pred["predictions"]

        return result

    elif method == "qda":
        X = np.array(args["X"], dtype=float)
        y = np.array(args["y"], dtype=int)
        return QDAClassifier.fit(X, y)

    elif method == "manova":
        groups = [np.array(g, dtype=float) for g in args["groups"]]
        return MANOVATest.test(groups)

    else:
        return {"error": f"Unknown method: {method}", "method": method}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: multivariate_runner.py '<json_input>'"}))
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
        print(json.dumps({"error": str(e), "traceback": traceback.format()}))
        sys.exit(1)


if __name__ == "__main__":
    main()
