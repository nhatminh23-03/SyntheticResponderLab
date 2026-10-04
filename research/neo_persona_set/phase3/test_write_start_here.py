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
FIRST = "2026-09-10_first_full_600_runs"


def _fake_assets(tmp_path: Path) -> Path:
    assets = tmp_path / "Assets"
    survey_runs = assets / "5_experiments" / FIRST / "plain_600" / "survey_runs"
    survey_runs.mkdir(parents=True)
    rows = [
        dict(zip(INDEX_HEADER, [KEEPER, "completed", "deepseek/deepseek-v4-pro-0813", "1", "202609091", "full", "", "600", "23400", "0", "0.0", "0", "0", "1", "1", "6.15", "3.5", "", "", "1", "abc", ""])),
        dict(zip(INDEX_HEADER, [SMOKE, "completed", "qwen/qwen3.7-plus", "1", "202609091", "full", "5", "5", "195", "0", "0.0", "0", "0", "1", "1", "0.01", "0.01", "", "", "1", "abc", ""])),
        dict(zip(INDEX_HEADER, [FAILED, "failed", "deepseek/deepseek-v4-pro-0813", "1", "202609091", "full", "", "600", "0", "0", "", "600", "0", "0", "0", "", "", "", "", "1", "abc", ""])),
    ]
    with open(survey_runs / "index.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    for folder in (KEEPER, SMOKE, FAILED + "_failed", "20261001T182508Z_mixed-panel_r1_s1-x"):
        (survey_runs / folder).mkdir()
        (survey_runs / folder / "questions.csv").write_text("question_id,question_type,min_value,max_value,options,text\nS3,single_choice,,,Yes|No,Space?\n", encoding="utf-8")
    (assets / "5_experiments" / "2026-11-01_something_new").mkdir()
    for section in ("0_logs", "1_reference", "4_persona_sets/plain_600_2026-08-25"):
        (assets / section).mkdir(parents=True)
    return assets


def _section(text: str, start: str, end: str) -> str:
    return text.split(start)[1].split(end)[0]


def test_lists_the_sections_that_exist_and_the_experiments_oldest_first(tmp_path: Path) -> None:
    assets = _fake_assets(tmp_path)
    assert write_start_here.main(["--assets", str(assets)]) == 0
    text = (assets / "START_HERE.md").read_text(encoding="utf-8")
    top = _section(text, "## What is where", "## How to score")
    for name in ("`0_logs/`", "`1_reference/`", "`4_persona_sets/`", "`5_experiments/`"):
        assert name in top
    assert "`2_real_data_aytm/`" not in top and "`9_outbox/`" not in top  # absent sections are not listed
    experiments = _section(text, "## Experiments", "## Inside an experiment folder")
    assert experiments.index(FIRST) < experiments.index("2026-11-01_something_new")
    assert "no description yet" in experiments  # a new round is listed even before it is described
    assert "1 keeper in index.csv" in experiments and "1 mixed panel" in experiments
    assert f"| `plain_600/survey_runs/{SMOKE}` | smoke test (5 personas) |" in experiments
    assert f"| `plain_600/survey_runs/{FAILED}_failed` | failed guardrail |" in experiments
    persona_sets = _section(text, "## Persona sets", "## Experiments")
    assert "`plain_600_2026-08-25/`" in persona_sets and "matched_600_v1" not in persona_sets
    for name in write_start_here.RUN_FILES:
        assert f"`{name}`" in text


def test_copies_codebook_and_crosswalk_into_reference_only_when_asked(tmp_path: Path) -> None:
    assets = _fake_assets(tmp_path)
    assert write_start_here.main(["--assets", str(assets)]) == 0
    assert not (assets / "1_reference" / "questions.csv").exists()  # no keeper given: nothing copied
    keeper = assets / "5_experiments" / FIRST / "plain_600" / "survey_runs" / KEEPER
    crosswalk = tmp_path / "cw.csv"
    crosswalk.write_text("our_id,real_column\nS3,PQ1\n", encoding="utf-8")
    assert write_start_here.main(["--assets", str(assets), "--keeper-run", str(keeper), "--crosswalk", str(crosswalk)]) == 0
    assert (assets / "1_reference" / "questions.csv").read_bytes() == (keeper / "questions.csv").read_bytes()
    assert (assets / "1_reference" / "crosswalk.csv").read_bytes() == crosswalk.read_bytes()
    assert f"copied from run `{KEEPER}`" in (assets / "START_HERE.md").read_text(encoding="utf-8")


def test_folders_without_an_index_are_classified_by_name(tmp_path: Path) -> None:
    assets = tmp_path / "Assets"
    runs = assets / "5_experiments" / "2026-09-24_copied_from_onedrive" / "survey_runs"
    for name in ("20260923T203058Z_deepseek-v4-pro-0813_r1_s1-baseline", "20260923T203312Z_deepseek-v4-pro-0813_r2_s1-baseline",
                 "20260924T212905Z_mixed-panel_r1_s1-R018b-prereg", "20260923T210904Z_mistral-large_r1_s1-R008_failed",
                 "20261001T174455Z_gemini-3-flash-preview_r1_n1_s1-smoke-hybrid"):
        (runs / name).mkdir(parents=True)
    assert write_start_here.main(["--assets", str(assets)]) == 0
    text = (assets / "START_HERE.md").read_text(encoding="utf-8")
    assert "no index.csv: 2 model runs, 1 mixed panel, 2 smoke / failed" in text
    assert "| `survey_runs/20260923T210904Z_mistral-large_r1_s1-R008_failed` | failed guardrail |" in text
    assert "| `survey_runs/20261001T174455Z_gemini-3-flash-preview_r1_n1_s1-smoke-hybrid` | smoke test |" in text
