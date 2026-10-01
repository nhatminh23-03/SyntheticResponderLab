from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import write_start_here  # noqa: E402

INDEX_HEADER = ["run_id", "status", "model", "repeat", "seed", "prompt_variant", "limit", "respondents", "answers", "fallback_answers", "fallback_share",
                "request_errors", "provider_error_count", "prompt_tokens", "completion_tokens", "usd_reported", "usd_estimated", "started_at", "finished_at",
                "duration_sec", "git_commit", "run_dir"]
KEEPER = "20260910T014617Z_deepseek-v4-pro-0813_r1"
SMOKE = "20260910T012519Z_qwen3.7-plus_r1_n5_smoke"
FAILED = "20260910T013031Z_deepseek-v4-pro-0813_r1"


def _fake_assets(tmp_path: Path) -> Path:
    assets = tmp_path / "Assets"
    survey_runs = assets / "600_persona" / "survey_runs"
    survey_runs.mkdir(parents=True)
    rows = [
        dict(zip(INDEX_HEADER, [KEEPER, "completed", "deepseek/deepseek-v4-pro-0813", "1", "202609091", "full", "", "600", "23400", "0", "0.0", "0", "0", "1", "1", "6.15", "3.5", "", "", "1", "abc", str(survey_runs / KEEPER)])),
        dict(zip(INDEX_HEADER, [SMOKE, "completed", "qwen/qwen3.7-plus", "1", "202609091", "full", "5", "5", "195", "0", "0.0", "0", "0", "1", "1", "0.01", "0.01", "", "", "1", "abc", str(survey_runs / SMOKE)])),
        dict(zip(INDEX_HEADER, [FAILED, "failed", "deepseek/deepseek-v4-pro-0813", "1", "202609091", "full", "", "600", "0", "0", "", "600", "0", "0", "0", "", "", "", "", "1", "abc", str(survey_runs / (FAILED + "_failed"))])),
    ]
    with open(survey_runs / "index.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    for folder in (KEEPER, SMOKE, FAILED + "_failed"):
        (survey_runs / folder).mkdir()
        (survey_runs / folder / "questions.csv").write_text("question_id,question_type,min_value,max_value,options,text\nS3,single_choice,,,Yes|No,Space?\n", encoding="utf-8")
    return assets


def test_writes_start_here_and_copies_codebook_and_crosswalk(tmp_path: Path) -> None:
    assets = _fake_assets(tmp_path)
    crosswalk = tmp_path / "cw.csv"
    crosswalk.write_text("our_id,real_column,match_type,our_options,real_options,notes\nS3,PQ1,screener,,,\n", encoding="utf-8")
    assert write_start_here.main(["--assets", str(assets), "--crosswalk", str(crosswalk)]) == 0
    text = (assets / "START_HERE.md").read_text(encoding="utf-8")
    keepers = text.split("### 600_persona — keepers")[1].split("### 600_persona — smoke")[0]
    others = text.split("### 600_persona — smoke and failed")[1].split("## Question ids")[0]
    assert KEEPER in keepers and SMOKE not in keepers and FAILED not in keepers
    assert f"| {SMOKE} | smoke test (5 personas) |" in others and f"| {FAILED}_failed | failed guardrail |" in others
    assert f"Copied from keeper run `{KEEPER}`" in text and "Present." in text
    assert (assets / "questions.csv").read_bytes() == (assets / "600_persona" / "survey_runs" / KEEPER / "questions.csv").read_bytes()
    assert (assets / "crosswalk.csv").read_bytes() == crosswalk.read_bytes()
    for name in write_start_here.RUN_FILES:
        assert f"`{name}`" in text
    assert "### match_600_persona" not in text


def test_without_crosswalk_says_so_and_explicit_keeper_wins(tmp_path: Path) -> None:
    assets = _fake_assets(tmp_path)
    keeper = assets / "600_persona" / "survey_runs" / SMOKE
    assert write_start_here.main(["--assets", str(assets), "--keeper-run", str(keeper)]) == 0
    text = (assets / "START_HERE.md").read_text(encoding="utf-8")
    assert "Not yet present" in text and f"Copied from keeper run `{SMOKE}`" in text
    assert not (assets / "crosswalk.csv").exists()


def test_lists_the_other_folders_that_exist_and_the_scoring_standard(tmp_path: Path) -> None:
    assets = _fake_assets(tmp_path)
    for name in ("DrLinSplit", "real_splits", "discussion"):
        (assets / name).mkdir()
    (assets / "EXPERIMENT_LOG.md").write_text("# log\n", encoding="utf-8")
    assert write_start_here.main(["--assets", str(assets)]) == 0
    text = (assets / "START_HERE.md").read_text(encoding="utf-8")
    top = text.split("## What is at the top level")[1].split("## How to score")[0]
    for name in ("`DrLinSplit/`", "`real_splits/`", "`discussion/`", "`EXPERIMENT_LOG.md`"):
        assert name in top
    assert "`Sept24_real_vs_synthetic_experiments/`" not in top and "9:1 email.pdf" not in top
    scoring = text.split("## How to score")[1].split("## Inside a persona-set folder")[0]
    assert "real_splits/lin-seed42/score_ids.txt" in scoring and "lin13-validation" in scoring
