#!/usr/bin/env python3
"""
Econometrics Runner — CLI bridge between Rust backend and econometric methods.

Called by Rust via subprocess with JSON input:
    python3 econometrics_runner.py '{"method": "ols", "args": {...}}'

Returns JSON output to stdout.
"""

import json
import sys
import traceback

import numpy as np

try:
    from econometrics import (
        OLSRegression,
        HeteroskedasticityTests,
        IV2SLS,
        GMMEstimator,
        PanelDataEstimator,
        LimitedDependentVariable,
        VARModel,
        CointegrationTest,
        VECMModel,
        BootstrapHypothesisTest,
    )
except ImportError:
    from python.statistical.econometrics import (
        OLSRegression,
        HeteroskedasticityTests,
        IV2SLS,
        GMMEstimator,
        PanelDataEstimator,
        LimitedDependentVariable,
        VARModel,
        CointegrationTest,
        VECMModel,
        BootstrapHypothesisTest,
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

    if method == "ols":
        X = np.array(args["X"], dtype=float)
        y = np.array(args["y"], dtype=float)
        names = args.get("feature_names")
        result = OLSRegression.fit(X, y, feature_names=names)
        return _to_serializable({
            "coefficients": result.coefficients,
            "std_errors": result.std_errors,
            "t_statistics": result.t_statistics,
            "p_values": result.p_values,
            "r_squared": result.r_squared,
            "adj_r_squared": result.adj_r_squared,
            "f_statistic": result.f_statistic,
            "f_p_value": result.f_p_value,
            "n_obs": result.n_obs,
            "feature_names": result.feature_names,
            "aic": result.aic,
            "bic": result.bic,
        })

    elif method == "breusch_pagan":
        residuals = np.array(args["residuals"], dtype=float)
        X = np.array(args["X"], dtype=float)
        return _to_serializable(HeteroskedasticityTests.breusch_pagan(residuals, X))

    elif method == "white_test":
        residuals = np.array(args["residuals"], dtype=float)
        X = np.array(args["X"], dtype=float)
        return _to_serializable(HeteroskedasticityTests.white_test(residuals, X))

    elif method == "robust_se":
        X = np.array(args["X"], dtype=float)
        y = np.array(args["y"], dtype=float)
        residuals = np.array(args["residuals"], dtype=float)
        return _to_serializable(HeteroskedasticityTests.robust_standard_errors(X, y, residuals))

    elif method == "2sls":
        y = np.array(args["y"], dtype=float)
        X_endog = np.array(args["X_endog"], dtype=float)
        Z = np.array(args["Z"], dtype=float)
        X_exog = np.array(args.get("X_exog", []), dtype=float) if args.get("X_exog") else None
        names = args.get("feature_names")
        return _to_serializable(IV2SLS.two_stage_least_squares(y, X_endog, Z, X_exog, names))

    elif method == "gmm":
        y = np.array(args["y"], dtype=float)
        X = np.array(args["X"], dtype=float)
        Z = np.array(args["Z"], dtype=float)
        names = args.get("feature_names")
        return _to_serializable(GMMEstimator.two_step_gmm(y, X, Z, names))

    elif method == "panel_fe":
        y = np.array(args["y"], dtype=float)
        X = np.array(args["X"], dtype=float)
        groups = np.array(args["groups"])
        names = args.get("feature_names")
        return _to_serializable(PanelDataEstimator.fixed_effects(y, X, groups, names))

    elif method == "panel_re":
        y = np.array(args["y"], dtype=float)
        X = np.array(args["X"], dtype=float)
        groups = np.array(args["groups"])
        names = args.get("feature_names")
        return _to_serializable(PanelDataEstimator.random_effects(y, X, groups, names))

    elif method == "logit":
        X = np.array(args["X"], dtype=float)
        y = np.array(args["y"], dtype=float)
        names = args.get("feature_names")
        return _to_serializable(LimitedDependentVariable.logit(X, y, names))

    elif method == "probit":
        X = np.array(args["X"], dtype=float)
        y = np.array(args["y"], dtype=float)
        names = args.get("feature_names")
        return _to_serializable(LimitedDependentVariable.probit(X, y, names))

    elif method == "var":
        data = np.array(args["data"], dtype=float)
        max_lags = args.get("max_lags", 4)
        names = args.get("variable_names")
        return _to_serializable(VARModel.fit(data, max_lags, names))

    elif method == "cointegration":
        y = np.array(args["y"], dtype=float)
        x = np.array(args["x"], dtype=float)
        return _to_serializable(CointegrationTest.engle_granger(y, x))

    elif method == "vecm":
        data = np.array(args["data"], dtype=float)
        rank = args.get("cointegrating_rank", 1)
        max_lags = args.get("max_lags", 3)
        names = args.get("variable_names")
        return _to_serializable(VECMModel.fit(data, rank, max_lags, names))

    elif method == "bootstrap_test":
        X = np.array(args["X"], dtype=float)
        y = np.array(args["y"], dtype=float)
        coef_idx = args.get("coef_index", 1)
        n_boot = args.get("n_bootstrap", 2000)
        return _to_serializable(BootstrapHypothesisTest.bootstrap_t_test(X, y, coef_idx, n_boot))

    else:
        return {"error": f"Unknown method: {method}", "method": method}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: econometrics_runner.py '<json_input>'"}))
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
