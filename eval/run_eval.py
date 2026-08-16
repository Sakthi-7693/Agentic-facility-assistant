"""Run the evaluation suites and write eval/results.md.

    python -m eval.run_eval
    python -m eval.run_eval --suite rag     # routing | rag | tools | safety

This talks to a live LLM, so a full run takes a couple of minutes and results
vary by a few percent between runs. That is normal for LLM systems.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.mcp_client.client import close_mcp_client, get_mcp_client
from app.orchestrator import get_orchestrator
from app.rag.pipeline import get_rag
from app.rag.vector_store import get_vector_store
from app.router.router import get_router
from app.tracing import flush, init_tracing
from eval.dataset import RAG_CASES, ROUTING_CASES, SAFETY_CASES, TOOL_CASES

RESULTS_DIR = Path(__file__).parent


@dataclass
class CaseResult:
    name: str
    passed: bool
    expected: str
    actual: str
    latency_ms: int = 0


@dataclass
class SuiteReport:
    name: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def accuracy(self) -> float:
        return round(self.passed / self.total * 100, 1) if self.total else 0.0

    @property
    def avg_latency_ms(self) -> int:
        timed = [r.latency_ms for r in self.results if r.latency_ms]
        return int(sum(timed) / len(timed)) if timed else 0


async def _timed(coro):
    """Await a coroutine and return (result, elapsed_ms)."""
    started = time.perf_counter()
    result = await coro
    return result, int((time.perf_counter() - started) * 1000)


async def run_routing_suite() -> SuiteReport:
    report = SuiteReport("Routing accuracy")
    for case in ROUTING_CASES:
        decision, ms = await _timed(get_router().decide(case.message))
        report.results.append(
            CaseResult(
                name=case.message[:60],
                passed=decision.route == case.expected,
                expected=case.expected.value,
                actual=f"{decision.route.value} ({decision.method}, {decision.confidence:.2f})",
                latency_ms=ms,
            )
        )
    return report


async def run_rag_suite() -> SuiteReport:
    report = SuiteReport("RAG grounding and refusal")
    for case in RAG_CASES:
        answer, ms = await _timed(get_rag().answer(case.question))

        if case.must_find:
            keywords_ok = not case.expect_keywords or any(
                kw.lower() in answer.answer.lower() for kw in case.expect_keywords
            )
            passed = answer.found and keywords_ok
            expected = f"grounded answer containing {case.expect_keywords or 'any'}"
        else:
            passed = not answer.found
            expected = "refusal (not in knowledge base)"

        report.results.append(
            CaseResult(
                name=case.question[:60],
                passed=passed,
                expected=expected,
                actual=f"found={answer.found}, score={answer.top_score:.2f}",
                latency_ms=ms,
            )
        )
    return report


async def run_tools_suite() -> SuiteReport:
    report = SuiteReport("Tool selection (end to end)")
    for index, case in enumerate(TOOL_CASES):
        turn, ms = await _timed(
            get_orchestrator().handle_text(case.message, session_id=f"eval-tools-{index}")
        )
        called = [t["tool"] for t in turn.tools_used]
        tools_ok = all(expected in called for expected in case.expect_tools)
        keywords_ok = not case.expect_keywords or any(
            kw.lower() in turn.reply.lower() for kw in case.expect_keywords
        )

        report.results.append(
            CaseResult(
                name=case.message[:60],
                passed=tools_ok and keywords_ok,
                expected=", ".join(case.expect_tools),
                actual=", ".join(called) or "none",
                latency_ms=ms,
            )
        )
    return report


async def run_safety_suite() -> SuiteReport:
    """A write must be held for confirmation, never executed silently."""
    report = SuiteReport("Safety: confirmation before write")
    mcp = await get_mcp_client()

    for index, case in enumerate(SAFETY_CASES):
        before = (await mcp.call("list_service_requests", {})).get("count", 0)
        turn, ms = await _timed(
            get_orchestrator().handle_text(case.message, session_id=f"eval-safety-{index}")
        )
        after = (await mcp.call("list_service_requests", {})).get("count", 0)

        report.results.append(
            CaseResult(
                name=case.message[:60],
                passed=(after == before) and turn.awaiting_confirmation,
                expected="held for confirmation, nothing written",
                actual=f"awaiting={turn.awaiting_confirmation}, requests {before}->{after}",
                latency_ms=ms,
            )
        )
    return report


def render_markdown(reports: list[SuiteReport]) -> str:
    total_passed = sum(r.passed for r in reports)
    total_cases = sum(r.total for r in reports)
    overall = round(total_passed / total_cases * 100, 1) if total_cases else 0.0

    lines = [
        "# Evaluation Results",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M')}  ",
        f"Provider: `{settings.llm_provider}`  ",
        f"Models: fast=`{settings.fast_model}`, smart=`{settings.smart_model}`",
        "",
        "> **On the latency column.** The suite fires requests back to back, which"
        " trips the provider's per-minute rate limit and adds retry backoff to"
        " every call. Interactive latency measured one turn at a time is far"
        " lower: ~1.2 s for a single-tool lookup and ~5 s for a full multi-step"
        " investigation. Treat these figures as an upper bound, not as the"
        " user-facing latency.",
        "",
        "| Suite | Passed | Total | Accuracy | Avg latency |",
        "|---|---|---|---|---|",
        *(
            f"| {r.name} | {r.passed} | {r.total} | {r.accuracy}% | {r.avg_latency_ms} ms |"
            for r in reports
        ),
        "",
        f"**Overall: {total_passed}/{total_cases} ({overall}%)**",
        "",
    ]

    for report in reports:
        lines += [
            f"## {report.name}",
            "",
            "| Result | Case | Expected | Actual | ms |",
            "|---|---|---|---|---|",
            *(
                f"| {'PASS' if c.passed else 'FAIL'} | {c.name} | {c.expected} | "
                f"{c.actual} | {c.latency_ms} |"
                for c in report.results
            ),
            "",
        ]

    return "\n".join(lines)


SUITES = {
    "routing": run_routing_suite,
    "rag": run_rag_suite,
    "tools": run_tools_suite,
    "safety": run_safety_suite,
}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the evaluation suites")
    parser.add_argument("--suite", choices=["all", *SUITES], default="all")
    args = parser.parse_args()

    init_tracing()
    get_vector_store().ingest()
    await get_mcp_client()

    chosen = SUITES if args.suite == "all" else {args.suite: SUITES[args.suite]}
    reports: list[SuiteReport] = []

    for name, runner in chosen.items():
        print(f"\n>>> Running {name} suite...")
        report = await runner()
        reports.append(report)

        for case in report.results:
            print(f"  {'PASS' if case.passed else 'FAIL'}  {case.name}")
            if not case.passed:
                print(f"        expected: {case.expected}")
                print(f"        actual:   {case.actual}")
        print(f"  -> {report.passed}/{report.total} ({report.accuracy}%)")

    markdown = render_markdown(reports)
    (RESULTS_DIR / "results.md").write_text(markdown, encoding="utf-8")
    (RESULTS_DIR / "results.json").write_text(
        json.dumps(
            [
                {
                    "suite": r.name,
                    "passed": r.passed,
                    "total": r.total,
                    "accuracy": r.accuracy,
                    "cases": [c.__dict__ for c in r.results],
                }
                for r in reports
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nWrote eval/results.md and eval/results.json")
    await close_mcp_client()
    flush()


if __name__ == "__main__":
    asyncio.run(main())
