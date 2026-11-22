r"""``python -m inbox_core.evals``: the on-demand runners against real models.

These spend real API calls (LiteLLM reads provider keys such as
``GEMINI_API_KEY`` from the environment), so they are never run in CI.

    python -m inbox_core.evals triage --config client.toml --golden golden.toml --out triage.json
    python -m inbox_core.evals groundedness --config client.toml --golden golden.toml \\
        --knowledge knowledge.md --out grounded.json --answers-out answers.json
    python -m inbox_core.evals calibrate --config client.toml --golden golden.toml \\
        --answers answers.json

Files written hold numbers, category names and case ids only.
``triage`` exits 1 when the executive recall gate fails, ``groundedness`` when
correctness is below 90 percent.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from inbox_core.adapters.litellm import (
    DEFAULT_MODEL,
    LiteLLMClassifier,
    LiteLLMGenerator,
    load_completion,
)
from inbox_core.config import load_config
from inbox_core.evals.golden import answerable_cases, load_golden_set
from inbox_core.evals.judge import LiteLLMJudge
from inbox_core.evals.metrics import format_table, percentage
from inbox_core.evals.runners import (
    classify_once,
    evaluate_groundedness,
    evaluate_triage,
    groundedness_summary,
    sweep_answer_threshold,
    sweep_triage_threshold,
    triage_summary,
)
from inbox_core.handlers import GroundedAnswer
from inbox_core.knowledge import InMemoryRetriever, load_markdown_knowledge
from inbox_core.triage import RetryingClassifier

__all__ = ["main"]

DEFAULT_JUDGE_MODEL = "gemini/gemini-3.5-flash"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m inbox_core.evals", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--config", required=True, type=Path)
        command.add_argument("--golden", required=True, type=Path)
        command.add_argument("--model", default=DEFAULT_MODEL)
        command.add_argument("--api-base", default=None, help="a LiteLLM gateway URL")
        command.add_argument("--out", type=Path, default=None, help="write a JSON summary here")
        command.add_argument("--require-every-language", action="store_true")

    triage = commands.add_parser("triage", help="may this classifier decide?")
    common(triage)
    triage.add_argument("--attempts", type=int, default=3)

    grounded = commands.add_parser("groundedness", help="are the answers grounded?")
    common(grounded)
    grounded.add_argument("--knowledge", required=True, type=Path)
    grounded.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    grounded.add_argument("--min-score", type=float, default=1.0)
    grounded.add_argument("--answers-out", type=Path, default=None)

    calibrate = commands.add_parser("calibrate", help="sweep both thresholds")
    common(calibrate)
    calibrate.add_argument("--answers", type=Path, default=None)
    return parser


def _write(path: Path | None, payload: dict[str, object]) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(
    argv: Sequence[str] | None = None,
    *,
    completion: Callable[..., Any] | None = None,
    sleep: Callable[[float], object] = time.sleep,
    stdout: TextIO | None = None,
) -> int:
    """Run one evaluation command. ``completion`` replaces ``litellm.completion`` (for tests)."""
    out = stdout or sys.stdout
    args = _parser().parse_args(argv)
    try:
        call = completion if completion is not None else load_completion()
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    config = load_config(args.config)
    cases = load_golden_set(args.golden, config, require_every_language=args.require_every_language)
    meta = {
        "evaluated_at": datetime.now(UTC).date().isoformat(),
        "golden_set": args.golden.name,
        "model": args.model,
    }

    def say(text: str = "") -> None:
        print(text, file=out)

    if args.command == "triage":
        classifier = RetryingClassifier(
            LiteLLMClassifier(config, model=args.model, completion=call, api_base=args.api_base),
            attempts=args.attempts,
            sleep=sleep,
        )
        metrics = evaluate_triage(classifier, cases, config.triage)
        summary = triage_summary(
            metrics,
            classifier=classifier.name,
            threshold=config.triage.confidence_threshold,
            cases=len(cases),
        )
        rows = [
            (
                name,
                str(values["support"]),
                percentage(values["precision"]),
                percentage(values["recall"]),
            )
            for name, values in summary["per_category"].items()  # type: ignore[attr-defined]
        ]
        say(format_table(rows, ("category", "cases", "precision", "recall")))
        say()
        say(f"category accuracy {percentage(metrics.category_accuracy)}")
        say(f"language accuracy {percentage(metrics.language_accuracy)}")
        say(f"executive recall  {percentage(metrics.executive_recall)} (the gate: 100.0%)")
        say(f"errors            {len(metrics.errors)}")
        _write(args.out, {**meta, **summary})
        return 0 if metrics.passes_executive_gate() else 1

    if args.command == "groundedness":
        entries = load_markdown_knowledge(args.knowledge)
        handler = GroundedAnswer(
            InMemoryRetriever(entries),
            LiteLLMGenerator(model=args.model, completion=call, api_base=args.api_base),
            min_score=args.min_score,
        )
        judge = LiteLLMJudge(
            config, model=args.judge_model, completion=call, api_base=args.api_base
        )
        grounded = evaluate_groundedness(
            handler, judge, cases, config, {entry.id: entry for entry in entries}
        )
        summary = groundedness_summary(
            grounded,
            generator=f"litellm:{args.model}",
            judge=f"litellm:{args.judge_model}",
            cases=len(answerable_cases(cases)),
        )
        say(f"correctness {percentage(grounded.correctness)} (the gate: 90.0%)")
        say(f"judged {grounded.judged}, grounded {grounded.grounded}, refused {grounded.refused}")
        _write(args.out, {**meta, **summary})
        _write(
            args.answers_out,
            {"answers": [{"id": i, "similarity": s, "passed": p} for i, s, p in grounded.answers]},
        )
        return 0 if grounded.passes_gate() else 1

    plain = LiteLLMClassifier(config, model=args.model, completion=call, api_base=args.api_base)
    answered, errors = classify_once(plain, cases)
    triage_rows = sweep_triage_threshold(answered, config.triage)
    say(
        format_table(
            [
                (
                    f"{row['threshold']:.2f}",
                    percentage(row["executive_recall"]),
                    percentage(row["answered_share"]),
                    str(int(row["missed_executive"])),
                )
                for row in triage_rows
            ],
            ("threshold", "executive recall", "auto-answered", "missed executive"),
        )
    )
    payload: dict[str, object] = {**meta, "errors": len(errors), "triage_sweep": triage_rows}
    if args.answers is not None:
        loaded = json.loads(args.answers.read_text(encoding="utf-8"))
        answers = [
            (str(item["id"]), float(item["similarity"]), bool(item["passed"]))
            for item in loaded["answers"]
        ]
        answer_rows = sweep_answer_threshold(answers)
        say()
        say(
            format_table(
                [
                    (
                        f"{row['threshold']:.2f}",
                        str(int(row["answered"])),
                        percentage(row["precision"]),
                        str(int(row["wrong_answers"])),
                    )
                    for row in answer_rows
                ],
                ("min score", "answered", "precision", "wrong answers"),
            )
        )
        payload["answer_sweep"] = answer_rows
    _write(args.out, payload)
    return 0
