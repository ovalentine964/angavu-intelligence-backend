# Python LLM Inference

This directory contains Python code for LLM inference ONLY.
The main backend is written in Rust (Axum).

Python is used for:
- DeepSeek API calls (reasoning + chat)
- Qwen 7B cloud inference
- XGBoost/sklearn ML pipelines

Called from Rust via PyO3 or subprocess.
