from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402


def _summary(path: Path) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["run_id", "mean_tv", "questions_close", "share_top_match"])
        writer.writeheader()
        writer.writerow({"run_id": "run_a", "mean_tv": "0.20", "questions_close": "10", "share_top_match": "0.60"})
        writer.writerow({"run_id": "run_b", "mean_tv": "0.10", "questions_close": "14", "share_top_match": "0.80"})
        writer.writerow({"run_id": "run_c", "mean_tv": "0.90", "questions_close": "0", "share_top_match": "0.00"})
    return path


def test_add_fill_show(tmp_path: Path) -> None:
    reg = tmp_path / "registry.csv"
    first = registry.add_entry(reg, hypothesis="baseline", condition="temperature 0.2", runner_flags="--temperature 0.2", runs="run_a;run_b", date="2026-09-12")
    second = registry.add_entry(reg, hypothesis="higher temperature", condition="temperature 0.8", runner_flags="--temperature 0.8", date="2026-09-13")
    assert (first, second) == ("R001", "R002")
    rows = list(csv.DictReader(open(reg, newline="", encoding="utf-8-sig")))
    assert list(rows[0].keys()) == registry.COLUMNS and rows[1]["hypothesis"] == "higher temperature"
    metrics = registry.fill_metrics(reg, "R001", _summary(tmp_path / "comparison_summary.csv"))
    assert metrics == {"metric_tv_mean": "0.1500", "metric_close_count": "24", "metric_top_match_share": "0.7000"}
    rows = list(csv.DictReader(open(reg, newline="", encoding="utf-8-sig")))
    assert rows[0]["metric_tv_mean"] == "0.1500" and rows[1]["metric_tv_mean"] == ""
    table = registry.render_table(reg)
    assert "| R001 |" in table and "higher temperature" in table
    assert registry.main(["--registry", str(reg), "add", "--hypothesis", "h3", "--condition", "c3", "--flags", "-x"]) == 0
    assert registry.main(["--registry", str(reg), "show"]) == 0
    assert registry.main(["--registry", str(reg), "fill", "--registry-id", "R002", "--summary", str(tmp_path / "comparison_summary.csv")]) == 0


def test_next_id_follows_the_highest_number_and_explicit_ids_are_unique(tmp_path: Path) -> None:
    reg = tmp_path / "registry.csv"
    for rid in ("R001", "R019a", "R019b", "R017b", "R010"):
        registry.add_entry(reg, registry_id=rid, hypothesis=rid, condition="c")
    assert registry.add_entry(reg, hypothesis="next", condition="c") == "R020"
    assert registry.add_entry(reg, registry_id="R020b", hypothesis="variant", condition="c") == "R020b"
    try:
        registry.add_entry(reg, registry_id="R020b", hypothesis="again", condition="c")
    except ValueError as error:
        assert "R020b" in str(error)
    else:
        raise AssertionError("a duplicate registry id was accepted")
    assert registry.main(["--registry", str(reg), "add", "--registry-id", "R021", "--date", "2026-09-30",
                          "--hypothesis", "h", "--condition", "c", "--flags", "--hybrid"]) == 0
    row = list(csv.DictReader(open(reg, newline="", encoding="utf-8-sig")))[-1]
    assert (row["registry_id"], row["date"], row["runner_flags"]) == ("R021", "2026-09-30", "--hybrid")
