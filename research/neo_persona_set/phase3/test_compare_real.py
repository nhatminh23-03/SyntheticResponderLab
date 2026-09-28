"""End-to-end run of compare_real.main on the fake real CSV and fake run folders. No network."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_real  # noqa: E402


def _read(path: Path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _row(rows, **match):
    return next(r for r in rows if all(r[k] == v for k, v in match.items()))


def _run(tmp_path: Path, fake_real_csv: Path, run_dirs, *extra: str) -> Path:
    out = tmp_path / "comparison"
    assert compare_real.main(["--real", str(fake_real_csv), "--runs", *map(str, run_dirs), "--out", str(out), *extra]) == 0
    return out


def test_end_to_end_outputs_and_offset(tmp_path: Path, fake_real_csv: Path, fake_run_dir: Path, second_fake_run_dir: Path) -> None:
    out = _run(tmp_path, fake_real_csv, [fake_run_dir, second_fake_run_dir])
    names = {p.name for p in out.iterdir()}
    assert names == {"comparison_long.csv", "comparison_options.csv", "comparison_summary.csv", "comparison_by_question.md", "unmapped.md", "crosswalk.csv", "manifest.json"}
    long_rows = _read(out / "comparison_long.csv")
    assert list(long_rows[0].keys()) == compare_real.LONG_COLUMNS and len(long_rows) == 39 * 2

    q1 = _row(long_rows, run_id="fake_run_r1", our_id="Q1")
    assert q1["real_key"] == "Q6" and q1["status"] == "ok" and q1["n_real"] == "12" and q1["n_synth"] == "4"
    assert q1["real_shares"] == "0.1667|0.1667|0.3333|0.1667|0.1667" and q1["mean_real"] == "3.0000" and q1["mean_synth"] == "3.7500" and q1["mean_diff"] == "0.7500"
    assert q1["top_real"] == "3" and q1["chi2_df"] == "4" and q1["close"] == "false"

    assert _row(long_rows, run_id="fake_run_r1", our_id="Q7")["status"] == "unmapped"
    assert _row(long_rows, run_id="fake_run_r1", our_id="Q2")["status"] == "real_column_missing"
    assert _row(long_rows, run_id="fake_run_r1", our_id="Q0B")["status"] == "our_question_missing"
    assert _row(long_rows, run_id="fake_run_r1", our_id="Q30")["scored"] == "false"

    q18 = _row(long_rows, run_id="fake_run_r1", our_id="Q18")
    assert q18["real_off_list_share"] == "0.1667" and q18["n_real"] == "10" and q18["real_shares"] == "0.2000|0.3000|0.5000"
    q22 = _row(long_rows, run_id="fake_run_r1", our_id="Q22")
    assert q22["synth_off_list_share"] == "0.2500" and q22["categories"].split("|")[0] == "Under $50,000"
    q14 = _row(long_rows, run_id="fake_run_r1", our_id="Q14")
    assert q14["status"] == "ok" and q14["real_shares"] == "0.4167|0.2500|0.3333" and q14["top_match"] == "true"
    q26 = _row(long_rows, run_id="fake_run_r1", our_id="Q26")
    assert q26["real_shares"] == "0.3333|0.6667" and q26["n_real"] == "12"
    q21 = _row(long_rows, run_id="fake_run_r1", our_id="Q21")
    assert q21["n_real"] == "12" and q21["categories"].startswith("18–24|25–34")
    s3 = _row(long_rows, run_id="fake_run_r1", our_id="S3")
    assert s3["n_synth"] == "4" and s3["categories"] == "Yes|I'm not sure, but possibly.|No"

    options = _read(out / "comparison_options.csv")
    assert list(options[0].keys()) == compare_real.OPTIONS_COLUMNS
    a1 = _row(options, run_id="fake_run_r1", our_id="Q20", category="Outdoor club sponsorships / community events")
    assert a1["real_share"] == "0.5000" and a1["real_n"] == "12" and a1["synth_share"] == "0.5000" and a1["synth_n"] == "4"
    assert _row(options, run_id="fake_run_r1", our_id="Q20", category="Social media ads (Facebook, Instagram)")["real_share"] == "0.2500"
    q20 = _row(long_rows, run_id="fake_run_r1", our_id="Q20")
    assert q20["n_real_off_list"] == "2" and q20["real_off_list_share"] == "0.0952"

    summary = _read(out / "comparison_summary.csv")
    assert list(summary[0].keys()) == compare_real.SUMMARY_COLUMNS and [r["run_id"] for r in summary] == ["fake_run_r1", "fake_run_r2"]
    assert summary[0]["n_synth_after_filter"] == "4" and summary[0]["n_dropped_outdoor"] == "2"
    assert int(summary[0]["questions_compared"]) == sum(1 for r in long_rows if r["run_id"] == "fake_run_r1" and r["status"] == "ok" and r["scored"] == "true")

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["filters"]["require_outdoor_space"] is True and manifest["thresholds"]["close_tv"] == 0.1
    assert [r["n_after_outdoor_filter"] for r in manifest["runs"]] == [4, 4] and manifest["real"]["n_rows"] == 12
    assert set(manifest["outputs"]) == names - {"manifest.json"} and len(manifest["real"]["sha256"]) == 64

    by_question = (out / "comparison_by_question.md").read_text(encoding="utf-8")
    assert "## Q1 vs real Q6 (likert)" in by_question and "model-a r1 (n=4)" in by_question and "| mean (scale) | 3.00 | 3.75 | " in by_question
    unmapped = (out / "unmapped.md").read_text(encoding="utf-8")
    assert "| Q7 |" in unmapped and "| Q34 |" in unmapped and "| Q23 |" in unmapped and "Gender" in unmapped and "| Q6 |" not in unmapped
    crosswalk_rows = _read(out / "crosswalk.csv")
    assert _row(crosswalk_rows, our_id="Q18")["real_options"] == "Build quality and details|Installation speed|Permit-light positioning|Smart Technology"


def test_keep_all_and_exclude_fallback(tmp_path: Path, fake_real_csv: Path, fake_run_dir: Path) -> None:
    out = _run(tmp_path, fake_real_csv, [fake_run_dir], "--keep-all", "--exclude-fallback", "--close-tv", "0.5")
    long_rows = _read(out / "comparison_long.csv")
    assert _row(long_rows, our_id="Q1")["n_synth"] == "6"
    assert _row(long_rows, our_id="Q19")["n_synth"] == "5"
    assert _row(long_rows, our_id="S3")["real_shares"] == "0.8333|0.1667|0.0000"
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["filters"] == {"require_outdoor_space": False, "screener_id": "S3", "exclude_fallback": True}
    assert manifest["runs"][0]["n_fallback_blanked"] == 1 and manifest["thresholds"]["close_tv"] == 0.5


def test_output_guard_refuses_real_folder(tmp_path: Path, fake_real_csv: Path, fake_run_dir: Path) -> None:
    for bad in (fake_real_csv.parent / "comparison", tmp_path / "aytm" / "out"):
        with pytest.raises(SystemExit) as excinfo:
            compare_real.main(["--real", str(fake_real_csv), "--runs", str(fake_run_dir), "--out", str(bad)])
        assert excinfo.value.code == 3
        assert not bad.exists()
    assert compare_real.main(["--real", str(tmp_path / "missing.csv"), "--runs", str(fake_run_dir), "--out", str(tmp_path / "o")]) == 2


def test_item_set_limits_what_is_scored_but_reports_everything(tmp_path: Path, fake_real_csv: Path, fake_run_dir: Path) -> None:
    items = tmp_path / "items.txt"
    items.write_text("# three items\nQ1\nQ5_1\nQ2\n", encoding="utf-8")  # the fake real file has no Q2 column
    out = _run(tmp_path, fake_real_csv, [fake_run_dir], "--items", str(items))
    long_rows = _read(out / "comparison_long.csv")
    assert {r["our_id"] for r in long_rows if r["scored"] == "true"} == {"Q1", "Q5_1", "Q2"}
    q6 = _row(long_rows, our_id="Q6")
    assert q6["status"] == "ok" and q6["scored"] == "false" and q6["tv"]  # still computed, just not counted
    summary = _read(out / "comparison_summary.csv")[0]
    assert summary["questions_compared"] == "2" and summary["item_set"] == "items.txt" and summary["n_real_respondents"] == "12"
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["items"] == {"set": "items.txt", "ids": ["Q1", "Q5_1", "Q2"], "n": 3}
    by_question = (out / "comparison_by_question.md").read_text(encoding="utf-8")
    assert "## Q1 vs real Q6 (likert)" in by_question and "## Q6 vs real Q11 (single (report only))" in by_question


def test_default_item_set_is_unchanged(tmp_path: Path, fake_real_csv: Path, fake_run_dir: Path) -> None:
    out = _run(tmp_path, fake_real_csv, [fake_run_dir])
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["items"]["set"] == "all" and manifest["items"]["n"] == 36 and "Q15" in manifest["items"]["ids"]
    assert _read(out / "comparison_summary.csv")[0]["item_set"] == "all"


def test_real_ids_score_against_a_subset_of_respondents(tmp_path: Path, fake_real_csv: Path, fake_run_dir: Path) -> None:
    ids = tmp_path / "score_ids.txt"
    ids.write_text("# score half\n" + "\n".join(str(1000 + i) for i in range(6)) + "\n", encoding="utf-8")
    out = _run(tmp_path, fake_real_csv, [fake_run_dir], "--real-ids", str(ids), "--items", "lin13-validation")
    q1 = _row(_read(out / "comparison_long.csv"), our_id="Q1")
    assert q1["n_real"] == "6" and q1["real_shares"] == "0.3333|0.3333|0.3333|0.0000|0.0000" and q1["scored"] == "true"
    summary = _read(out / "comparison_summary.csv")[0]
    assert summary["n_real_respondents"] == "6" and summary["item_set"] == "lin13-validation"
    real = json.loads((out / "manifest.json").read_text())["real"]
    assert real["n_rows"] == 6 and real["n_rows_in_file"] == 12
    assert real["subset"]["ids_file"] == str(ids) and real["subset"]["n"] == 6 and len(real["subset"]["sha256"]) == 64


def test_bad_items_or_ids_stop_before_writing(tmp_path: Path, fake_real_csv: Path, fake_run_dir: Path) -> None:
    bad_ids = tmp_path / "bad_ids.txt"
    bad_ids.write_text("1000\n9999\n", encoding="utf-8")
    for extra in (["--real-ids", str(bad_ids)], ["--items", "no-such-set"]):
        out = tmp_path / ("out_" + extra[0].strip("-"))
        assert compare_real.main(["--real", str(fake_real_csv), "--runs", str(fake_run_dir), "--out", str(out), *extra]) == 2
        assert not out.exists()
