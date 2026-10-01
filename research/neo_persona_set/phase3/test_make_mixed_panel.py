"""Materialising a mixed panel: the deal, arm compatibility, and what is carried across."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_mixed_panel  # noqa: E402

PIDS = [f"P{i:03d}" for i in range(1, 9)]
STYLES = "skeptical:0.25,enthusiastic:0.20"


def _write(path: Path, header: List[str], rows: List[Dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def _arm(root: Path, name: str, *, answer: str, trait_mix: Optional[str] = None, persona_sha: str = "a" * 64,
         answer_mode: Optional[str] = None, persona_kind: Optional[str] = None, seed: int = 202609091) -> Path:
    run = root / name
    run.mkdir(parents=True)
    (run / "questions.csv").write_text("question_id\nQ1\n", encoding="utf-8")
    _write(run / "answers_wide.csv", ["run_id", "model", "persona_id", "Q1"],
           [{"run_id": name, "model": name, "persona_id": pid, "Q1": answer} for pid in PIDS])
    _write(run / "answers_long.csv", ["run_id", "persona_id", "question_id", "answer", "is_fallback"],
           [{"run_id": name, "persona_id": pid, "question_id": "Q1", "answer": answer, "is_fallback": "false"} for pid in PIDS])
    manifest = {"run_id": name, "seed": seed, "trait_mix": trait_mix, "personas": {"sha256": persona_sha}}
    if answer_mode:
        manifest["answer_mode"] = answer_mode
    if persona_kind:
        manifest["persona_kind"] = persona_kind
    if answer_mode == "distribution":
        _write(run / "probabilities.csv", ["run_id", "persona_id", "question_id", "option", "probability", "drawn", "status"],
               [{"run_id": name, "persona_id": pid, "question_id": "Q1", "option": str(k), "probability": "0.2",
                 "drawn": answer, "status": "ok"} for pid in PIDS for k in range(1, 6)])
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run


def _mix(tmp_path: Path, arms: List[Path], *extra: str) -> int:
    return make_mixed_panel.main([*[a for arm in arms for a in ("--arm", str(arm))], "--out-dir", str(tmp_path / "out"),
                                  "--run-tag", "s1-test-mix", *extra])


def _only_run(tmp_path: Path) -> Path:
    (run,) = list((tmp_path / "out").iterdir())
    return run


def test_each_persona_comes_whole_from_one_arm_and_the_deal_is_seeded(tmp_path: Path) -> None:
    arms = [_arm(tmp_path / "arms", name, answer=answer) for name, answer in (("a_run", "1"), ("b_run", "2"), ("c_run", "3"), ("d_run", "4"))]
    assert _mix(tmp_path, arms) == 0
    run = _only_run(tmp_path)
    wide = list(csv.DictReader((run / "answers_wide.csv").open(encoding="utf-8-sig")))
    long = list(csv.DictReader((run / "answers_long.csv").open(encoding="utf-8-sig")))
    assert [r["persona_id"] for r in wide] == PIDS and {r["model"] for r in wide} == {"mixed panel"}
    assert {r["persona_id"]: r["answer"] for r in long} == {r["persona_id"]: r["Q1"] for r in wide}
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(manifest["model"]["personas_per_arm"].values()) == [2, 2, 2, 2]
    assert manifest["answer_mode"] == "single" and manifest["persona_kind"] == "synthetic" and manifest["trait_mix"] is None
    assert _mix(tmp_path / "again", arms) == 0
    again = list(csv.DictReader((_only_run(tmp_path / "again") / "answers_wide.csv").open(encoding="utf-8-sig")))
    assert [r["Q1"] for r in again] == [r["Q1"] for r in wide]


@pytest.mark.parametrize("field, other", [
    ("trait_mix", {"trait_mix": STYLES}),
    ("persona_sha256", {"persona_sha": "b" * 64}),
    ("answer_mode", {"answer_mode": "distribution"}),
    ("persona_kind", {"persona_kind": "hybrid"}),
    ("seed", {"seed": 202609092}),
])
def test_refuses_arms_that_differ(tmp_path: Path, capsys, field: str, other: dict) -> None:
    arms = [_arm(tmp_path / "arms", "a_run", answer="1"), _arm(tmp_path / "arms", "b_run", answer="2", **other)]
    assert _mix(tmp_path, arms) == 2
    assert field in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_styles_may_differ_only_when_allowed_and_it_is_recorded(tmp_path: Path) -> None:
    arms = [_arm(tmp_path / "arms", "a_run", answer="1"), _arm(tmp_path / "arms", "b_run", answer="2", trait_mix=STYLES)]
    assert _mix(tmp_path, arms, "--allow-mismatch", "trait_mix") == 0
    manifest = json.loads((_only_run(tmp_path) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["trait_mix"] == "differs by arm" and manifest["allowed_mismatch"] == ["trait_mix"]
    assert manifest["arm_settings"]["b_run"]["trait_mix"] == STYLES


def test_hybrid_and_answer_mode_can_never_be_allowed_to_differ(tmp_path: Path) -> None:
    arms = [_arm(tmp_path / "arms", "a_run", answer="1"), _arm(tmp_path / "arms", "b_run", answer="2")]
    with pytest.raises(SystemExit):
        _mix(tmp_path, arms, "--allow-mismatch", "persona_kind")


def test_distribution_arms_carry_their_odds_and_labels(tmp_path: Path) -> None:
    arms = [_arm(tmp_path / "arms", name, answer=answer, answer_mode="distribution", persona_kind="hybrid")
            for name, answer in (("a_run", "1"), ("b_run", "5"))]
    assert _mix(tmp_path, arms) == 0
    run = _only_run(tmp_path)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["answer_mode"] == "distribution" and manifest["persona_kind"] == "hybrid"
    odds = list(csv.DictReader((run / "probabilities.csv").open(encoding="utf-8-sig")))
    wide = {r["persona_id"]: r["Q1"] for r in csv.DictReader((run / "answers_wide.csv").open(encoding="utf-8-sig"))}
    assert len(odds) == len(PIDS) * 5
    assert all(row["drawn"] == wide[row["persona_id"]] and row["run_id"] == manifest["run_id"] for row in odds)
