"""
Manual prompt/provider smoke checks.

This file is intentionally script-only so pytest collection stays offline-safe.
Run it directly when you want to exercise live model credentials.
"""

import json
import os
import time
from pathlib import Path


def main():
    import httpx
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()

    def make_client():
        gemini_key = os.getenv("GEMINI_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        if gemini_key:
          return (
              OpenAI(
                  api_key=gemini_key,
                  base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
              ),
              os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
              "gemini",
          )
        if groq_key:
          return (
              OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1"),
              os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
              "groq",
          )
        raise RuntimeError("No API key found. Set GEMINI_API_KEY or GROQ_API_KEY in .env")

    jarvis = json.loads(Path("jarvis.json").read_text(encoding="utf-8"))
    local_model = os.getenv("OLLAMA_MODEL") or jarvis.get("ai_config", {}).get("local_model", "ollama/codellama")
    local_model_name = local_model.split("/")[-1]

    client, model, provider = make_client()
    print("\n=== JARVIS prompt smoke test ===")
    print(f"Provider: {provider} | Model: {model}")
    print(f"Local model: {local_model_name}\n")

    response = client.chat.completions.create(
      model=model,
      max_tokens=100,
      messages=[
          {"role": "system", "content": "Reply with exactly API_OK."},
          {"role": "user", "content": "ready"},
      ],
    )
    text = response.choices[0].message.content or ""
    print("API connectivity:", "PASS" if "API_OK" in text else f"FAIL ({text[:60]})")

    ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
    try:
      t0 = time.time()
      resp = httpx.get(f"{ollama_endpoint}/api/tags", timeout=3)
      latency = int((time.time() - t0) * 1000)
      models = [m["name"] for m in resp.json().get("models", [])]
      has_local_model = any(local_model_name in m for m in models)
      print("Ollama reachable:", "PASS" if resp.status_code == 200 else f"FAIL ({resp.status_code})")
      print("Configured local model available:", "PASS" if has_local_model else f"FAIL ({models})")
      print(f"Ollama latency: {latency}ms")
    except httpx.ConnectError:
      print("Ollama reachable: SKIP (not started)")


if __name__ == "__main__":
    main()
