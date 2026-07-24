"""
Angavu Intelligence — Python LLM Inference Module

Called via subprocess from Rust for LLM inference.
Models: DeepSeek (reasoning + chat), Qwen 7B (cloud)
"""
import json
import sys
import os
import requests

def query_deepseek_reasoner(prompt: str, context: dict = None) -> str:
    """Call DeepSeek Reasoner for complex analysis."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "DEEPSEEK_API_KEY not set", "model": "deepseek-reasoner"})
    
    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-reasoner",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048
            },
            timeout=30
        )
        result = resp.json()
        return json.dumps({"response": result["choices"][0]["message"]["content"], "model": "deepseek-reasoner"})
    except Exception as e:
        return json.dumps({"error": str(e), "model": "deepseek-reasoner"})

def query_deepseek_chat(prompt: str, context: dict = None) -> str:
    """Call DeepSeek Chat for conversational responses."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "DEEPSEEK_API_KEY not set", "model": "deepseek-chat"})
    
    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048
            },
            timeout=30
        )
        result = resp.json()
        return json.dumps({"response": result["choices"][0]["message"]["content"], "model": "deepseek-chat"})
    except Exception as e:
        return json.dumps({"error": str(e), "model": "deepseek-chat"})

def query_qwen_cloud(prompt: str, context: dict = None) -> str:
    """Call Qwen 7B cloud inference."""
    api_key = os.environ.get("QWEN_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "QWEN_API_KEY not set", "model": "qwen-7b"})
    
    try:
        resp = requests.post(
            "https://api.qwen.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "qwen-7b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048
            },
            timeout=30
        )
        result = resp.json()
        return json.dumps({"response": result["choices"][0]["message"]["content"], "model": "qwen-7b"})
    except Exception as e:
        return json.dumps({"error": str(e), "model": "qwen-7b"})

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "test"
    prompt = sys.argv[2] if len(sys.argv) > 2 else ""
    
    if action == "deepseek-reasoner":
        print(query_deepseek_reasoner(prompt))
    elif action == "deepseek-chat":
        print(query_deepseek_chat(prompt))
    elif action == "qwen":
        print(query_qwen_cloud(prompt))
    else:
        print(json.dumps({"status": "ready", "models": ["deepseek-reasoner", "deepseek-chat", "qwen-7b"]}))
