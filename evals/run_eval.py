"""Eval runner using execution accuracy.

Reads evals/eval_set.jsonl, calls the agent at AGENT_URL on each question,
then compares the agent's SQL output to the gold SQL by *executed rows*
(canonicalized: sorted, stringified, None-coerced to empty).

Helpers (run_sql / canonicalize / matches) are provided. You implement
eval_one() and summarize().

Run:
    uv run python evals/run_eval.py --out results/eval_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_FILE = ROOT / "evals" / "eval_set.jsonl"
DEFAULT_OUT_FILE = ROOT / "results" / "eval_baseline.json"
DB_DIR = ROOT / "data" / "bird"
AGENT_URL_DEFAULT = "http://localhost:8001/answer"


# ---------- Helpers (provided) -----------------------------------------

def run_sql(db_id: str, sql: str, timeout: float = 5.0) -> tuple[bool, list[tuple] | None, str | None]:
    """Run sql against db_id in read-only mode. Returns (ok, rows, error)."""
    path = DB_DIR / f"{db_id}.sqlite"
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout) as conn:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            return True, rows, None
    except Exception as e:  # noqa: BLE001
        return False, None, f"{type(e).__name__}: {e}"


def canonicalize(rows: list[tuple] | None) -> list[tuple] | None:
    """Sort rows; coerce cells to str; None -> ''."""
    if rows is None:
        return None
    return sorted(tuple("" if c is None else str(c) for c in row) for row in rows)


def matches(gold_rows: list[tuple] | None, pred_rows: list[tuple] | None) -> bool:
    if gold_rows is None or pred_rows is None:
        return False
    return canonicalize(gold_rows) == canonicalize(pred_rows)


# ---------- Implement these (Phase 5) ----------------------------------

def eval_one(question: dict, agent_url: str) -> dict:
    """Score one question. Return a dict capturing per-iteration correctness."""
    db_id = question["db_id"]
    q_text = question["question"]
    gold_sql = question["gold_sql"]

    # Run gold SQL once
    gold_ok, gold_rows, gold_err = run_sql(db_id, gold_sql)

    # Call agent
    try:
        resp = httpx.post(
            agent_url,
            json={"question": q_text, "db": db_id, "tags": {"eval": "true", "db_id": db_id}},
            timeout=60.0,
        )
        resp.raise_for_status()
        agent_result = resp.json()
    except Exception as e:
        return {
            "question": q_text,
            "db_id": db_id,
            "gold_sql": gold_sql,
            "agent_sql": None,
            "iterations": 0,
            "correct_at": {},
            "error": str(e),
        }

    agent_sql = agent_result.get("sql")
    iterations = agent_result.get("iterations", 0)
    history = agent_result.get("history", [])

    # Check correctness at each iteration by running intermediate SQLs
    correct_at = {}
    seen_sqls = []
    for entry in history:
        seen_sqls.append(entry["sql"])

    # Build per-iteration correctness: iteration i = result after i-th LLM call
    for i, sql in enumerate(seen_sqls, 1):
        pred_ok, pred_rows, _ = run_sql(db_id, sql)
        correct_at[str(i)] = matches(gold_rows, pred_rows) if (gold_ok and pred_ok) else False

    # Fill forward for iterations beyond what agent ran (carry last result)
    last_correct = correct_at.get(str(len(seen_sqls)), False)
    for i in range(len(seen_sqls) + 1, 4):  # fill up to iteration 3
        correct_at[str(i)] = last_correct

    # Final correctness
    pred_ok, pred_rows, _ = run_sql(db_id, agent_sql) if agent_sql else (False, None, None)
    final_correct = matches(gold_rows, pred_rows) if (gold_ok and pred_ok) else False

    return {
        "question": q_text,
        "db_id": db_id,
        "gold_sql": gold_sql,
        "agent_sql": agent_sql,
        "iterations": iterations,
        "correct_at": correct_at,
        "final_correct": final_correct,
        "error": None,
    }


def summarize(results: list[dict]) -> dict:
    """Aggregate per-question results.

    Per-iteration carry-forward: if the agent terminated at iteration j < k
    (verify said ok at j, or it hit MAX_ITERATIONS at j < k), treat the
    question's iteration-k result as identical to its iteration-j result.
    The agent stopped emitting; whatever it had at termination is what
    would have been served had we polled at iteration k.
    """
    total = len(results)
    if total == 0:
        return {}

    # Per-iteration pass rates
    iter_correct = {"1": 0, "2": 0, "3": 0}
    final_correct = 0

    for r in results:
        if r.get("final_correct"):
            final_correct += 1
        for k in iter_correct:
            if r.get("correct_at", {}).get(k, False):
                iter_correct[k] += 1

    return {
        "total": total,
        "final_pass_rate": round(final_correct / total, 3),
        "pass_rate_at_iteration": {
            k: round(v / total, 3) for k, v in iter_correct.items()
        },
        "errors": sum(1 for r in results if r.get("error")),
    }


# ---------- Main (provided) --------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_FILE)
    parser.add_argument("--agent-url", default=AGENT_URL_DEFAULT)
    args = parser.parse_args()

    questions = [json.loads(line) for line in args.eval_set.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(questions)} eval questions from {args.eval_set}")

    results: list[dict] = []
    t0 = time.monotonic()
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['db_id']}: {q['question'][:60]}...", flush=True)
        results.append(eval_one(q, args.agent_url))
    elapsed = time.monotonic() - t0

    summary = summarize(results)
    out = {
        "summary": summary,
        "wall_clock_seconds": elapsed,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
