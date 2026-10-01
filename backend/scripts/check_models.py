"""Phase 0 model check: verify Groq + Gemini keys, list models, measure real token cost.

Usage (from repo root):
    python backend/scripts/check_models.py groq     # list models + 1 test call per GROQ_MODELS entry
    python backend/scripts/check_models.py gemini   # list models per key; 1 tiny call per (key, model) in GEMINI_MODELS
    python backend/scripts/check_models.py all

Reads backend/.env. Never prints API keys.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

GROQ_BASE = "https://api.groq.com/openai/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Representative agent-decision prompt (~400 tokens), roughly the shape of a real step.
SYSTEM_PROMPT = """You are simulating an IMPATIENT user testing a website. You skim, you click the most obvious button,
you hate waiting and give up quickly when stuck. Goal: buy a health insurance policy and reach the confirmation page.
Choose exactly ONE next action from the element list. Never invent element IDs.
Reply with JSON only: {"action": "click|type|select|scroll|back|wait|done|give_up", "element_id": int|null,
"text": str|null, "thought": str (<=200 chars, in persona), "confidence": float 0..1, "expects": str (<=100 chars)}"""

USER_PROMPT = """URL: https://demo.example/
TITLE: SurakshaSetu - Health cover for every family
HEADINGS: "Protect your family from medical bills", "Why SurakshaSetu?"
TEXT: Plans from Rs 299/month. Cashless at 5,000+ hospitals. Claim settlement in 7 days.
ELEMENTS:
[0] link "Home"
[1] link "Plans"
[2] link "Claims"
[3] button "Explore"
[4] button "Get Covered"
[5] link "Learn about insurance"
[6] link "Contact us"
HISTORY: (none - first step)
STATE: You just arrived. You feel calm."""


def load_env() -> None:
    if not ENV_PATH.exists():
        sys.exit(f"Missing {ENV_PATH}. Copy backend/.env.example to backend/.env and fill in keys.")
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def csv_env(name: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


def mask(key: str) -> str:
    return f"…{key[-4:]}" if len(key) >= 8 else "…"


# ---------------------------------------------------------------- Groq

def groq_call(key: str, model: str, extra: dict) -> requests.Response:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "temperature": 0.2,
        "max_completion_tokens": 400,
        "response_format": {"type": "json_object"},
        **extra,
    }
    return requests.post(
        f"{GROQ_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json=body,
        timeout=60,
    )


def reasoning_params(model: str) -> list[dict]:
    """Try the cheapest reasoning setting first, fall back if the model rejects it."""
    if "gpt-oss" in model:
        return [{"reasoning_effort": "low"}, {}]
    if "qwen" in model:
        return [{"reasoning_effort": "none"}, {"reasoning_format": "hidden"}, {}]
    return [{}]


def check_groq() -> None:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        print("❌ GROQ_API_KEY not set")
        return
    print(f"\n=== Groq (key {mask(key)}) ===")
    r = requests.get(f"{GROQ_BASE}/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    if r.status_code != 200:
        print(f"❌ list models: HTTP {r.status_code} {r.text[:200]}")
        return
    ids = sorted(m["id"] for m in r.json().get("data", []) if m.get("active", True))
    print(f"✅ {len(ids)} active models:")
    for i in ids:
        print(f"   - {i}")

    for model in csv_env("GROQ_MODELS"):
        print(f"\n--- {model}")
        if model not in ids:
            print("   ⚠️  not in model list, skipping")
            continue
        for extra in reasoning_params(model):
            t0 = time.monotonic()
            resp = groq_call(key, model, extra)
            dt = time.monotonic() - t0
            if resp.status_code == 400 and extra:
                print(f"   (param {extra} rejected, retrying without)")
                continue
            break
        if resp.status_code != 200:
            print(f"   ❌ HTTP {resp.status_code} {resp.text[:300]}")
            continue
        data = resp.json()
        usage = data.get("usage", {})
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        content = data["choices"][0]["message"].get("content") or ""
        try:
            parsed = json.loads(content)
            valid = "✅ valid JSON" if parsed.get("action") else "⚠️ JSON missing 'action'"
        except json.JSONDecodeError:
            parsed, valid = None, "❌ invalid JSON"
        h = resp.headers
        print(f"   params: {extra or 'default'}  latency: {dt:.2f}s  {valid}")
        print(
            f"   tokens: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')}"
            f" reasoning={reasoning} total={usage.get('total_tokens')}"
        )
        print(
            f"   limits: tpm={h.get('x-ratelimit-limit-tokens')} remaining={h.get('x-ratelimit-remaining-tokens')}"
            f" | rpd={h.get('x-ratelimit-limit-requests')} remaining={h.get('x-ratelimit-remaining-requests')}"
        )
        print(f"   output: {content[:300]}")


# ---------------------------------------------------------------- Gemini

def check_gemini() -> None:
    keys = csv_env("GEMINI_API_KEYS")
    models = csv_env("GEMINI_MODELS")
    if not keys:
        print("❌ GEMINI_API_KEYS not set")
        return

    for idx, key in enumerate(keys, 1):
        print(f"\n=== Gemini key #{idx} ({mask(key)}) ===")
        headers = {"x-goog-api-key": key}
        r = requests.get(f"{GEMINI_BASE}/models", headers=headers, params={"pageSize": 1000}, timeout=30)
        if r.status_code != 200:
            print(f"❌ list models: HTTP {r.status_code} {r.text[:200]}")
            continue
        flash = sorted(
            m["name"].removeprefix("models/")
            for m in r.json().get("models", [])
            if "flash" in m["name"] and "generateContent" in m.get("supportedGenerationMethods", [])
        )
        print(f"✅ key valid. Flash models with generateContent ({len(flash)}):")
        for m in flash:
            print(f"   - {m}")

        if not models:
            continue
        for model in models:
            if model not in flash:
                print(f"   ⚠️  {model}: not listed for this key, skipping")
                continue
            t0 = time.monotonic()
            resp = requests.post(
                f"{GEMINI_BASE}/models/{model}:generateContent",
                headers=headers,
                json={
                    "contents": [{"parts": [{"text": "Reply with the single word OK."}]}],
                    "generationConfig": {"maxOutputTokens": 512},
                },
                timeout=60,
            )
            dt = time.monotonic() - t0
            if resp.status_code != 200:
                print(f"   ❌ {model}: HTTP {resp.status_code} {resp.text[:200]}")
                continue
            u = resp.json().get("usageMetadata", {})
            print(
                f"   ✅ {model}: {dt:.2f}s prompt={u.get('promptTokenCount')}"
                f" output={u.get('candidatesTokenCount')} thinking={u.get('thoughtsTokenCount')}"
            )

    if not models:
        print("\nGEMINI_MODELS is empty: no generate calls made. Set it to the exact IDs above and re-run.")


if __name__ == "__main__":
    load_env()
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target in ("groq", "all"):
        check_groq()
    if target in ("gemini", "all"):
        check_gemini()
