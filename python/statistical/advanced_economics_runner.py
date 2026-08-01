#!/usr/bin/env python3
"""Runner script for advanced economics models — invoked by Rust bridge."""
import json
import sys

from advanced_economics import run_method

if __name__ == "__main__":
    input_data = json.loads(sys.argv[1])
    result = run_method(input_data["method"], input_data["args"])
    print(json.dumps(result, default=str))
