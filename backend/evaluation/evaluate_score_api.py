"""
Evaluate /api/score against a small local manifest of recorded fixtures.

This is intentionally lightweight: no training loop, no benchmark chasing, and
no dependency on private datasets. It gives the project a repeatable way to
track the metrics users actually feel: latency, phrase match, WER, score gates,
and basic pass/fail expectations per clip.

Manifest JSONL format:
  {"audio_path":"fixtures/ship_or_sheep.wav","phrase":"Ship or sheep?","accent":"GA"}
  {"audio_path":"fixtures/wrong_phrase.wav","phrase":"The right light is bright","max_overall":70}

Run:
  python -m evaluation.evaluate_score_api --manifest evaluation/score_manifest.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

import httpx


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        row["_line"] = line_no
        rows.append(row)
    return rows


def _score_clip(client: httpx.Client, api_url: str, row: dict[str, Any], base_dir: Path) -> dict:
    audio_path = Path(row["audio_path"])
    if not audio_path.is_absolute():
        audio_path = base_dir / audio_path
    with audio_path.open("rb") as fh:
        files = {"audio": (audio_path.name, fh, "audio/wav")}
        data = {
            "phrase": row["phrase"],
            "accent": row.get("accent", "GA"),
            "l1": row.get("l1", "unknown"),
        }
        t0 = time.perf_counter()
        response = client.post(api_url, files=files, data=data)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
    response.raise_for_status()
    result = response.json()
    debug = result.get("debug") or {}
    phrase_match = (debug.get("phrase_match") or {}).get("phrase_match")
    return {
        "id": row.get("id", audio_path.stem),
        "line": row["_line"],
        "audio_path": str(audio_path),
        "phrase": row["phrase"],
        "overall": result.get("overall"),
        "wer": result.get("wer"),
        "phrase_match": phrase_match,
        "elapsed_ms": elapsed_ms,
        "stage_ms": debug.get("stage_ms", {}),
        "score_gates": debug.get("score_gates", []),
        "expectations": {
            "min_overall": row.get("min_overall"),
            "max_overall": row.get("max_overall"),
            "max_wer": row.get("max_wer"),
            "min_phrase_match": row.get("min_phrase_match"),
        },
    }


def _check_expectations(item: dict) -> list[str]:
    failures: list[str] = []
    exp = item["expectations"]
    if exp["min_overall"] is not None and item["overall"] < exp["min_overall"]:
        failures.append(f"overall {item['overall']} < {exp['min_overall']}")
    if exp["max_overall"] is not None and item["overall"] > exp["max_overall"]:
        failures.append(f"overall {item['overall']} > {exp['max_overall']}")
    if exp["max_wer"] is not None and item["wer"] is not None and item["wer"] > exp["max_wer"]:
        failures.append(f"wer {item['wer']} > {exp['max_wer']}")
    if (
        exp["min_phrase_match"] is not None
        and item["phrase_match"] is not None
        and item["phrase_match"] < exp["min_phrase_match"]
    ):
        failures.append(f"phrase_match {item['phrase_match']} < {exp['min_phrase_match']}")
    return failures


def _summary(items: list[dict]) -> dict:
    latencies = [i["elapsed_ms"] for i in items]
    wers = [i["wer"] for i in items if isinstance(i["wer"], (int, float))]
    phrase = [i["phrase_match"] for i in items if isinstance(i["phrase_match"], (int, float))]
    failures = []
    for item in items:
        item_failures = _check_expectations(item)
        if item_failures:
            failures.append({"id": item["id"], "line": item["line"], "failures": item_failures})
    return {
        "count": len(items),
        "latency_ms_avg": round(statistics.mean(latencies), 1) if latencies else None,
        "latency_ms_p95": round(statistics.quantiles(latencies, n=20)[18], 1) if len(latencies) >= 2 else None,
        "wer_avg": round(statistics.mean(wers), 3) if wers else None,
        "phrase_match_avg": round(statistics.mean(phrase), 1) if phrase else None,
        "gated_count": sum(1 for i in items if i["score_gates"]),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--api-url", default="http://localhost:8000/api/score")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rows = _read_manifest(args.manifest)
    base_dir = args.manifest.parent
    with httpx.Client(timeout=args.timeout) as client:
        items = [_score_clip(client, args.api_url, row, base_dir) for row in rows]

    report = {"summary": _summary(items), "items": items}
    payload = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(payload + "\n")
    print(payload)
    return 1 if report["summary"]["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
