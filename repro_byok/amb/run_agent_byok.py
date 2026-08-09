#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MemoryAgentBench (ICLR'26) — BYOK orchestrator.

Unlike LoCoMo / LongMemEval (QA benchmarks with a swappable judge), MemoryAgentBench
is an AGENT benchmark graded by the OFFICIAL harness. The BYOK path is therefore:

  1. You clone the OFFICIAL MemoryAgentBench repo (public, ICLR'26).
  2. You drop `amb/adapter/t1mem_adapter.py` in as the agent implementation.
  3. You run the official harness with YOUR OWN API keys (DASHSCOPE_API_KEY for
     T1Mem's reader, plus whatever the harness needs). T1Mem never sees your keys.
  4. The official harness emits the four-dimension scores (AR/CR/TTL/LRU).

This script is the ENTRY POINT / CHECKLIST for that flow. It:
  * validates your environment (keys present, adapter importable),
  * optionally performs a dry-run that emits a schema-valid result scaffold,
  * prints the exact command to invoke the official harness once you have it.

It does NOT contain the official harness (that is the benchmark author's code) — we
only ship OUR agent adapter + config, which is the BYOK-correct boundary.

Usage:
  python amb/run_agent_byok.py --dry-run                 # emit schema-valid scaffold
  python amb/run_agent_byok.py --harness-dir <official_repo> --run   # invoke official harness
"""
import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "adapter"))
from t1mem_adapter import build_agent  # noqa: E402

DIMENSIONS = ["AR", "CR", "TTL", "LRU"]


def check_env():
    missing = []
    if not os.environ.get("DASHSCOPE_API_KEY"):
        missing.append("DASHSCOPE_API_KEY (DashScope/百炼, T1Mem reader — for live agent runs)")
    if not os.environ.get("OPENROUTER_API_KEY"):
        # Some MemoryAgentBench tasks may use a GPT-class grader; optional here.
        missing.append("(optional) OPENROUTER_API_KEY")
    return missing


def dry_run(output):
    """Emit a schema-valid result scaffold with null scores (no live calls)."""
    result = {
        "meta": {
            "package": "N1Mem-BYOK", "pillar": "amb",
            "mode": "dry-run-scaffold",
            "harness": "MemoryAgentBench (ICLR'26, official)",
            "agent": "T1Mem (multi-model reader + OR, local BGE-M3 retrieval)",
            "note": "Scores are NULL in dry-run. Run the official harness with your own keys to fill them.",
        },
        "dimensions": {d: {"score": None, "n_tasks": None} for d in DIMENSIONS},
        "overall_simple_mean": None,
        "overall_weighted": None,
    }
    json.dump(result, open(output, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[dry-run] Wrote schema-valid scaffold to " + output)
    return result


def run_official(harness_dir, output, adapter_config):
    """Invoke the official MemoryAgentBench harness with T1Mem as the agent.

    The exact entry point depends on the official repo; this is the integration
    point. Adjust the command to match the official harness's CLI.
    """
    agent = build_agent(adapter_config)
    print("[run] T1MemAgent loaded (reader=" + str(agent.reader_model) +
          ", embed=" + str(agent.embedding_backend) + ")")
    harness_entry = os.path.join(harness_dir, "run_eval.py")
    if not os.path.exists(harness_entry):
        print("[run] Expected official harness entry not found: " + harness_entry)
        print("       Adjust `harness_entry` in this script to the official repo's CLI.")
        print("       Typical invocation (pseudo):")
        print("         cd " + harness_dir)
        adapter_path = os.path.abspath(os.path.join(HERE, "adapter", "t1mem_adapter.py"))
        print("         python run_eval.py --agent t1mem --agent-path " + adapter_path + " --out " + output)
        return None
    import subprocess
    cmd = [sys.executable, harness_entry, "--agent", "t1mem",
           "--agent-path", os.path.abspath(os.path.join(HERE, "adapter", "t1mem_adapter.py")),
           "--out", output]
    print("[run] Invoking official harness:\n  " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Emit schema-valid scaffold")
    ap.add_argument("--harness-dir", help="Path to official MemoryAgentBench repo")
    ap.add_argument("--run", action="store_true", help="Invoke official harness (needs --harness-dir)")
    ap.add_argument("--agent-config", default=os.path.join(HERE, "adapter", "agent_config.json"))
    ap.add_argument("--output", default=os.path.join(HERE, "amb_byok_result.json"))
    args = ap.parse_args()

    print("=== T1Mem BYOK — MemoryAgentBench ===")
    missing = check_env()
    if missing:
        print("[env] The following are not set (BYOK requires YOUR keys):")
        for m in missing:
            print("   - " + m)
        if not args.dry_run:
            print("[env] Aborting live run. Use --dry-run to emit a scaffold, "
                  "or set the keys above.")
            return

    if args.dry_run:
        dry_run(args.output)
        return
    if args.run:
        if not args.harness_dir:
            print("[run] --harness-dir is required to invoke the official harness.")
            return
        run_official(args.harness_dir, args.output, args.agent_config)
        return
    print("Nothing to do. Use --dry-run or --run --harness-dir <official_repo>.")


if __name__ == "__main__":
    main()
