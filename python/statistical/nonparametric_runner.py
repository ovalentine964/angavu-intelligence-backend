#!/usr/bin/env python3
"""
Nonparametric Runner — CLI bridge between Rust backend and statistical methods.

Called by Rust via subprocess with JSON input:
    python3 nonparametric_runner.py '{"method": "mann_whitney", "args": {...}}'

Returns JSON output to stdout.

This script imports from nonparametric.py and dispatches to the correct method.
"""

import json
import sys
import traceback

import numpy as np

# Import from the existing nonparametric module
from nonparametric import (
    BootstrapInference,
    KernelDensityEstimator,
    KruskalWallisTest,
    MannWhitneyTest,
    MarketConcentration,
    PermutationTest,
    PowerAnalysis,
)


def dispatch(method: str, args: dict) -> dict:
    """Dispatch method call to the appropriate class/function."""

    if method == "mann_whitney":
        sample1 = np.array(args["sample1"], dtype=float)
        sample2 = np.array(args["sample2"], dtype=float)
        alternative = args.get("alternative", "two-sided")
        return MannWhitneyTest.test(sample1, sample2, alternative=alternative)

    elif method == "kruskal_wallis":
        groups = [np.array(g, dtype=float) for g in args["groups"]]
        return KruskalWallisTest.test(*groups)

    elif method == "bootstrap_ci":
        data = np.array(args["data"], dtype=float)
        stat_name = args.get("statistic", "mean")
        n_bootstrap = args.get("n_bootstrap", 5000)
        confidence = args.get("confidence", 0.95)

        # Map statistic name to function
        stat_fn = {
            "mean": np.mean,
            "median": np.median,
            "std": np.std,
            "var": np.var,
        }.get(stat_name, np.mean)

        return BootstrapInference.percentile_ci(
            data, stat_fn, n_bootstrap=n_bootstrap, confidence=confidence
        )

    elif method == "permutation_test":
        sample1 = np.array(args["sample1"], dtype=float)
        sample2 = np.array(args["sample2"], dtype=float)
        n_permutations = args.get("n_permutations", 10000)
        alternative = args.get("alternative", "two-sided")
        return PermutationTest.two_sample(
            sample1, sample2,
            n_permutations=n_permutations,
            alternative=alternative
        )

    elif method == "power_analysis":
        effect_size = args["effect_size"]
        alpha = args.get("alpha", 0.05)
        power = args.get("power", 0.80)
        test_type = args.get("test_type", "t_test")

        if test_type == "mann_whitney":
            return PowerAnalysis.mann_whitney(effect_size, alpha=alpha, power=power)
        elif test_type == "proportion":
            p1 = args.get("p1", 0.5)
            p2 = p1 + effect_size
            return PowerAnalysis.proportion_test(p1, p2, alpha=alpha, power=power)
        else:
            return PowerAnalysis.two_sample_t_test(effect_size, alpha=alpha, power=power)

    elif method == "kde":
        data = np.array(args["data"], dtype=float)
        n_points = args.get("n_points", 200)

        points, density = KernelDensityEstimator.gaussian_kde(data, n_points=n_points)
        modality = KernelDensityEstimator.detect_multimodality(data)

        return {
            "evaluation_points": points.tolist(),
            "density_values": density.tolist(),
            "n_modes": modality["n_modes"],
            "mode_locations": modality["mode_locations"],
            "is_multimodal": modality["is_multimodal"],
        }

    elif method == "market_concentration":
        shares = np.array(args["market_shares"], dtype=float)
        hhi_result = MarketConcentration.hhi(shares)
        gini_result = MarketConcentration.gini(shares)

        return {
            "hhi": hhi_result["hhi"],
            "concentration_level": hhi_result["concentration_level"],
            "n_firms": hhi_result["n_firms"],
            "gini": gini_result["gini"],
            "gini_interpretation": gini_result["interpretation"],
        }

    else:
        return {"error": f"Unknown method: {method}", "method": method}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: nonparametric_runner.py '<json_input>'"}))
        sys.exit(1)

    try:
        input_data = json.loads(sys.argv[1])
        method = input_data["method"]
        args = input_data.get("args", {})

        result = dispatch(method, args)
        print(json.dumps(result))

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
