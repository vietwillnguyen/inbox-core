"""The on-demand eval command line, driven offline through an injected fake completion."""

from __future__ import annotations

import io
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from inbox_core.evals.cli import main
from tests.test_evals import GOLDEN

CONFIG_TOML = """
[organisation]
name = "Example Bike Workshop"
summary = "a made-up bicycle repair workshop"

[triage]
confidence_threshold = 0.6
fallback_category = "other"

[triage.languages]
en = "English"
es = "Spanish"

[[triage.categories]]
name = "faq"
auto_answer = true
description = "a general question about the workshop"

[[triage.categories]]
name = "booking"
description = "the sender wants to book a repair"

[[triage.categories]]
name = "refund"
escalates_to = "needs_executive"
description = "the sender wants money back"

[[triage.categories]]
name = "other"
description = "anything else"

[[triage.categories]]
name = "automated"
escalates_to = "skip"
description = "not written by a person"
"""

KNOWLEDGE = """# Example
## KB-01 Opening hours
Keywords: abren, sabado
We open at 9am on Saturdays.
"""


class FakeCompletion:
    """Answers like a perfect model: the expected signals, the entry text, a passing verdict."""

    def __init__(self, wrong: set[str] | None = None) -> None:
        self.cases = {case["text"]: case for case in tomllib.loads(GOLDEN)["cases"]}
        self.wrong = wrong or set()
        self.calls = 0

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        messages = kwargs["messages"]
        if "response_format" in kwargs:
            body = json.loads(messages[1]["content"])["body"]
            case = self.cases[body]
            category = "faq" if case["id"] in self.wrong else case["expected_category"]
            content = json.dumps(
                {
                    "category": category,
                    "language": case["language"],
                    "confidence": 0.95,
                    "asks_for_human": case.get("expected_asks_for_human", False),
                    "mentions_money_or_commitment": (
                        False
                        if case["id"] in self.wrong
                        else case.get("expected_mentions_money", False)
                    ),
                }
            )
        elif messages[0]["content"].startswith("You are grading"):
            prompt = messages[0]["content"]
            block = prompt.split("REQUIRED FACTS:\n", 1)[1].split("\n\n", 1)[0]
            facts = [line[2:] for line in block.splitlines() if line.startswith("- ")]
            content = json.dumps(
                {"mentions": dict.fromkeys(facts, True), "grounded": True, "violations": []}
            )
        else:
            content = "We open at 9am on Saturdays."
        return {"choices": [{"message": {"content": content}}]}


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "config": tmp_path / "client.toml",
        "golden": tmp_path / "golden.toml",
        "knowledge": tmp_path / "knowledge.md",
    }
    paths["config"].write_text(CONFIG_TOML, encoding="utf-8")
    paths["golden"].write_text(GOLDEN, encoding="utf-8")
    paths["knowledge"].write_text(KNOWLEDGE, encoding="utf-8")
    return paths


def run(argv: list[str], fake: FakeCompletion) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, completion=fake, sleep=lambda _: None, stdout=out)
    return code, out.getvalue()


def base(files: dict[str, Path], command: str) -> list[str]:
    return [command, "--config", str(files["config"]), "--golden", str(files["golden"])]


def test_triage_passes_the_gate_and_writes_numbers_only(
    files: dict[str, Path], tmp_path: Path
) -> None:
    out_path = tmp_path / "evidence" / "triage.json"
    code, printed = run([*base(files, "triage"), "--out", str(out_path)], FakeCompletion())
    assert code == 0
    assert "executive recall  100.0%" in printed
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["executive_gate_passed"] is True
    assert summary["golden_set"] == "golden.toml"
    dumped = out_path.read_text(encoding="utf-8")
    for case in tomllib.loads(GOLDEN)["cases"]:
        assert case["text"] not in dumped


def test_triage_exits_non_zero_on_a_missed_escalation(files: dict[str, Path]) -> None:
    code, printed = run(base(files, "triage"), FakeCompletion(wrong={"refund-en"}))
    assert code == 1
    assert "executive recall  50.0%" in printed


def test_groundedness_and_calibration(files: dict[str, Path], tmp_path: Path) -> None:
    answers = tmp_path / "answers.json"
    grounded = tmp_path / "grounded.json"
    code, printed = run(
        [
            *base(files, "groundedness"),
            "--knowledge",
            str(files["knowledge"]),
            "--min-score",
            "0.1",
            "--out",
            str(grounded),
            "--answers-out",
            str(answers),
        ],
        FakeCompletion(),
    )
    assert code == 0, printed
    assert "correctness 100.0%" in printed
    assert json.loads(grounded.read_text(encoding="utf-8"))["grounded"] == 2
    assert len(json.loads(answers.read_text(encoding="utf-8"))["answers"]) == 2

    sweep = tmp_path / "sweep.json"
    code, printed = run(
        [*base(files, "calibrate"), "--answers", str(answers), "--out", str(sweep)],
        FakeCompletion(),
    )
    assert code == 0
    assert "executive recall" in printed
    assert "min score" in printed
    payload = json.loads(sweep.read_text(encoding="utf-8"))
    assert payload["errors"] == 0
    assert len(payload["answer_sweep"]) > 0


def test_calibrate_without_answers(files: dict[str, Path]) -> None:
    code, printed = run(base(files, "calibrate"), FakeCompletion())
    assert code == 0
    assert "min score" not in printed


def test_without_litellm_the_command_explains_the_extra(
    files: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "litellm", None)
    assert main(base(files, "triage")) == 2
    assert "inbox-core[litellm]" in capsys.readouterr().err
