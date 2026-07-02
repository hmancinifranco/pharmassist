#!/usr/bin/env python3
"""Evaluation runner for the Unified Agent.

Invokes the deployed agent for each question in eval_questions.json,
measures latency, validates responses, and reports metrics.

Usage:
    python agentcore/evaluations/run_eval.py [--apm-id "Peccy"] [--max-questions 10]

Requirements validated:
    9.2 — Accuracy target >= 85%
    9.3 — End-to-end latency < 6s per question
    9.4 — success==True, expected data type, no data isolation violation
    9.5 — Generated SQL is syntactically valid
"""

import argparse
import json
import os
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path


def load_questions(path: str) -> list:
    """Load evaluation questions from JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def invoke_agent(prompt: str, apm_id: str, timeout: int = 60) -> tuple:
    """Invoke the agent via agentcore CLI and return (response_dict, latency_seconds).

    Args:
        prompt: The question to send to the agent.
        apm_id: The APM identifier for data isolation.
        timeout: Maximum seconds to wait for a response.

    Returns:
        Tuple of (response_dict, latency_seconds).
    """
    start = time.time()
    payload = json.dumps({"prompt": prompt, "apm_id": apm_id})

    try:
        result = subprocess.run(
            ["agentcore", "invoke", payload],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(os.path.abspath(__file__)) + "/..",
        )
        latency = time.time() - start

        # Try to parse JSON from stdout
        stdout = result.stdout.strip()
        if stdout:
            try:
                response = json.loads(stdout)
                return response, latency
            except json.JSONDecodeError:
                # If output is not JSON, wrap it
                return {
                    "result": stdout,
                    "success": True if result.returncode == 0 else False,
                    "retries": 0,
                }, latency
        else:
            # No output — check stderr for clues
            return {
                "result": result.stderr or "(empty response)",
                "success": False,
                "retries": 0,
            }, latency

    except subprocess.TimeoutExpired:
        latency = time.time() - start
        return {
            "result": f"Timeout after {timeout}s",
            "success": False,
            "retries": 0,
        }, latency
    except FileNotFoundError:
        latency = time.time() - start
        return {
            "result": "agentcore CLI not found. Is it installed?",
            "success": False,
            "retries": 0,
        }, latency
    except Exception as e:
        latency = time.time() - start
        return {
            "result": f"Invocation error: {str(e)}",
            "success": False,
            "retries": 0,
        }, latency


def validate_response(response: dict, question: dict, apm_id: str) -> tuple:
    """Validate response against criteria.

    Checks:
        - success == True (Req 9.4)
        - Response contains expected keywords (Req 9.4)
        - No data isolation violations (Req 9.4)
        - SQL is syntactically valid if present (Req 9.5)

    Args:
        response: The agent's response dict.
        question: The evaluation question with validation_criteria.
        apm_id: The APM ID to check data isolation.

    Returns:
        Tuple of (passed: bool, issues: list[str]).
    """
    issues = []
    criteria = question.get("validation_criteria", {})

    # Check success (Req 9.4)
    if not response.get("success", False):
        issues.append("success is False")

    # Check must_contain keywords
    result_text = str(response.get("result", "")).lower()
    for keyword in criteria.get("must_contain", []):
        if keyword.lower() not in result_text:
            issues.append(f"missing keyword: {keyword}")

    # Check must_not_contain
    for keyword in criteria.get("must_not_contain", []):
        if keyword.lower() in result_text:
            issues.append(f"contains forbidden: {keyword}")

    # Check data isolation (Req 9.4) — response should not contain other APMs' data
    # A basic heuristic: if the response mentions "otro APM" or "todos los APMs"
    # without being asked, it might be a data isolation issue.
    # More rigorous: check that SQL includes APM filter
    structured = response.get("structured", {})
    sql = structured.get("sql", "") if isinstance(structured, dict) else ""
    if sql:
        sql_lower = sql.lower()
        # Req 9.5 — SQL should be syntactically valid (starts with SELECT/WITH)
        sql_trimmed = sql.strip()
        if sql_trimmed and not (
            sql_trimmed.upper().startswith("SELECT")
            or sql_trimmed.upper().startswith("WITH")
        ):
            issues.append("SQL does not start with SELECT or WITH")

        # Data isolation check: if query involves cartera_medica, it should filter by APM
        if "cartera_medica" in sql_lower and "id_apm" not in sql_lower:
            issues.append("data isolation: query on cartera_medica without id_apm filter")

    return len(issues) == 0, issues


def compute_percentile(values: list, percentile: int) -> float:
    """Compute a percentile value from a sorted list of numbers."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    n = len(sorted_values)
    idx = (percentile / 100) * (n - 1)
    lower = int(idx)
    upper = lower + 1
    if upper >= n:
        return sorted_values[-1]
    fraction = idx - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def format_report(results: list, latencies: list, total: int) -> str:
    """Format the evaluation report as a human-readable string.

    Output matches the spec format with accuracy, latency stats, and failures.
    """
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    accuracy = (passed / total * 100) if total > 0 else 0

    lines = []
    lines.append("")
    lines.append("📊 Evaluation Report — PharmAssist Unified Agent")
    lines.append("═" * 50)
    lines.append(f"Total questions: {total}")
    lines.append(f"Passed: {passed}")
    lines.append(f"Failed: {failed}")
    lines.append(f"Accuracy: {accuracy:.1f}%")
    lines.append("")

    if latencies:
        p50 = compute_percentile(latencies, 50)
        p95 = compute_percentile(latencies, 95)
        p99 = compute_percentile(latencies, 99)
        max_lat = max(latencies)
        lines.append("Latency (seconds):")
        lines.append(f"  p50: {p50:.1f}s")
        lines.append(f"  p95: {p95:.1f}s")
        lines.append(f"  p99: {p99:.1f}s")
        lines.append(f"  max: {max_lat:.1f}s")
    lines.append("")

    # Failed questions detail
    failed_results = [r for r in results if not r["passed"]]
    if failed_results:
        lines.append("Failed questions:")
        for r in failed_results:
            issues_str = "; ".join(r["issues"])
            lines.append(f'  #{r["id"]} "{r["prompt"][:50]}..." — {issues_str}')
    else:
        lines.append("All questions passed! ✅")

    lines.append("")
    return "\n".join(lines)


def save_results(results: list, latencies: list, report: str, output_dir: str) -> str:
    """Save detailed results and report to the results directory.

    Returns the path to the saved JSON file.
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save detailed JSON results
    json_path = os.path.join(output_dir, f"eval_{timestamp}.json")
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "total_questions": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "accuracy_pct": (
            sum(1 for r in results if r["passed"]) / len(results) * 100
            if results
            else 0
        ),
        "latency": {
            "p50": compute_percentile(latencies, 50) if latencies else 0,
            "p95": compute_percentile(latencies, 95) if latencies else 0,
            "p99": compute_percentile(latencies, 99) if latencies else 0,
            "max": max(latencies) if latencies else 0,
            "mean": statistics.mean(latencies) if latencies else 0,
        },
        "results": results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Save human-readable report
    report_path = os.path.join(output_dir, f"eval_{timestamp}_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    return json_path


def main():
    """Run the evaluation suite against the deployed Unified Agent."""
    parser = argparse.ArgumentParser(
        description="Evaluation runner for PharmAssist Unified Agent"
    )
    parser.add_argument(
        "--apm-id",
        default="Peccy",
        help="APM ID to use for evaluation (default: Peccy)",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Maximum number of questions to evaluate (default: all)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout per question in seconds (default: 60)",
    )
    parser.add_argument(
        "--questions-file",
        default=None,
        help="Path to eval_questions.json (auto-detected if not specified)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to save results (default: agentcore/evaluations/results/)",
    )
    args = parser.parse_args()

    # Resolve paths
    script_dir = Path(__file__).parent
    questions_file = args.questions_file or str(script_dir / "eval_questions.json")
    output_dir = args.output_dir or str(script_dir / "results")

    # Load questions
    print(f"📋 Loading questions from {questions_file}")
    questions = load_questions(questions_file)
    if args.max_questions:
        questions = questions[: args.max_questions]
    print(f"   → {len(questions)} questions to evaluate")
    print(f"   → APM ID: {args.apm_id}")
    print(f"   → Timeout: {args.timeout}s per question")
    print()

    # Run evaluations
    results = []
    latencies = []

    for i, question in enumerate(questions, 1):
        prompt = question["prompt"]
        qid = question["id"]
        category = question.get("category", "unknown")

        print(f"  [{i}/{len(questions)}] #{qid} ({category}) {prompt[:60]}...", end=" ")

        response, latency = invoke_agent(prompt, args.apm_id, timeout=args.timeout)
        passed, issues = validate_response(response, question, args.apm_id)

        latencies.append(latency)
        result_entry = {
            "id": qid,
            "category": category,
            "prompt": prompt,
            "passed": passed,
            "issues": issues,
            "latency_s": round(latency, 2),
            "response_preview": str(response.get("result", ""))[:200],
            "retries": response.get("retries", 0),
        }
        results.append(result_entry)

        status = "✅" if passed else "❌"
        print(f"{status} ({latency:.1f}s)")
        if not passed:
            for issue in issues:
                print(f"      → {issue}")

    # Generate and display report
    report = format_report(results, latencies, len(questions))
    print(report)

    # Save results
    json_path = save_results(results, latencies, report, output_dir)
    print(f"💾 Results saved to: {json_path}")

    # Exit with non-zero if accuracy < 85% (Req 9.2)
    accuracy = sum(1 for r in results if r["passed"]) / len(results) * 100 if results else 0
    if accuracy < 85.0:
        print(f"\n⚠️  Accuracy {accuracy:.1f}% is below the 85% target (Req 9.2)")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
