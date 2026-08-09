#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BYOK OpenRouter Judge client — the shared core of the T1Mem reproduction package.

Design principles (Bring-Your-Own-Key):
  * NO hardcoded API key. The key is read from the environment variable
    OPENROUTER_API_KEY. If it is missing, the script fails loudly with a clear
    instruction instead of silently using someone else's key.
  * The judge MODEL defaults to openai/gpt-4o-mini — the de-facto standard
    judge-LLM of the LoCoMo benchmark (Mem0 eval framework default, confirmed
    by MemMachine / mflow-benchmarks). Override via BYOK_JUDGE_MODEL. A stricter
    openai/gpt-4o cross-check is also supported (see T1Mem dual-judge notes).
  * Stateless, standard-library only (urllib + ssl). No third-party dependency.
  * 5 independent votes per hypothesis, majority (>=3) wins, mirroring T1Mem's
    internal evaluation so a BYOK run is directly comparable to our published number.

Usage (as a library):
    from common.openrouter_judge import OpenRouterJudge
    j = OpenRouterJudge()                # reads OPENROUTER_API_KEY + BYOK_JUDGE_MODEL
    votes, passed = j.judge_votes(prompt, n_votes=5, threshold=3)
"""
import os
import json
import time
import ssl
import threading
import urllib.request
import concurrent.futures


class MissingKeyError(RuntimeError):
    """Raised when the required API key is not present in the environment."""


def get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise MissingKeyError(
            "OPENROUTER_API_KEY is not set.\n"
            "This is a BYOK (Bring-Your-Own-Key) package: supply YOUR OWN OpenRouter\n"
            "key so you (not us) pay for and control the judge calls.\n"
            "  1. Copy .env.example -> .env\n"
            "  2. Fill in OPENROUTER_API_KEY=sk-or-... (your key)\n"
            "  3. `export $(grep -v '^#' .env | xargs)`  (or `set -a; source .env; set +a`)\n"
        )
    return key


BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"  # LoCoMo de-facto standard judge (Mem0 framework default)


class OpenRouterJudge:
    """A minimal, key-isolated GPT-class judge client.

    Every call is authenticated with the caller's own OPENROUTER_API_KEY.
    The only variable vs T1Mem's internal run is *who owns the key* — the
    prompt, model, vote count and threshold are identical, so the reproduced
    score is directly comparable to our published claim.
    """

    def __init__(self, model: str = None, max_workers: int = 8, vote_workers: int = 5,
                 semaphore: int = 16, temperature: float = 0.0, max_tokens: int = 5,
                 timeout: int = 90):
        self.api_key = get_api_key()
        self.model = model or os.environ.get("BYOK_JUDGE_MODEL", DEFAULT_MODEL)
        self.max_workers = max_workers
        self.vote_workers = vote_workers
        self.sem = threading.Semaphore(semaphore)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._cost = 0.0
        self._lock = threading.Lock()
        self.success = 0
        self.fail = 0

    # ---- low-level completion -------------------------------------------
    def _complete(self, prompt: str):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE}/chat/completions", data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://t1mem.local",
                "X-Title": "N1Mem-BYOK-Repro",
            },
            method="POST",
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        cost = r.get("usage", {}).get("cost", 0.0)
        content = r["choices"][0]["message"]["content"].strip().lower()
        return content, cost

    def judge_one(self, prompt: str) -> bool:
        """Single yes/no judgement with retry/backoff. Returns True if 'yes'."""
        with self.sem:
            last = None
            for attempt in range(5):
                try:
                    text, cost = self._complete(prompt)
                    with self._lock:
                        self._cost += cost
                        self.success += 1
                    return any(text.startswith(p) for p in ("y", "yes", "correct", "true"))
                except Exception as e:  # noqa: BLE001
                    last = e
                    err = str(e).lower()
                    if "429" in err or "rate" in err or "too many" in err:
                        time.sleep(min(2 ** attempt * 4, 30))
                    else:
                        time.sleep(min(2 ** attempt, 8))
            with self._lock:
                self.fail += 1
            return False

    def judge_votes(self, prompt: str, n_votes: int = 5, threshold: int = 3):
        """Run n_votes independent judgements, return (votes, passed)."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.vote_workers) as ex:
            votes = list(ex.map(self.judge_one, [prompt] * n_votes))
        return votes, sum(votes) >= threshold

    @property
    def cost(self) -> float:
        with self._lock:
            return self._cost


def sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
