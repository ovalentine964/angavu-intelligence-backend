#!/usr/bin/env python3
"""Runner script for distributions module — called by Rust bridge via subprocess."""
import sys, json
sys.path.insert(0, "python/statistical")
from distributions import run_method

if __name__ == "__main__":
    input_data = json.loads(sys.argv[1])
    result = run_method(input_data["method"], input_data.get("args", {}))
    print(json.dumps(result))
