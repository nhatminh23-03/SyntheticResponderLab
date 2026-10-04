"""Merging Dr. Lin's driver columns onto the team's persona file, with every check before writing."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "phase2"))
import import_driver_personas as imp  # noqa: E402

TEAM_HEADER = ["persona_id", "exact_age", "hours_worked_per_week", "name"]
DRIVERS = {"prior_consideration_of_backyard_unit": "No, I have never considered this", "outdoor_recreation_frequency": "Never",
           "member_of_outdoor_club": "No", "most_likely_use_for_a_backyard_unit": "Other"}


def _write(path: Path, rows: List[Dict[str, str]]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _team() -> List[Dict[str, str]]:
    return [{"persona_id": f"P00{i}", "exact_age": str(40 + i), "hours_worked_per_week": "40", "name": f"Name {i}"} for i in (1, 2, 3)]


def _lin(team_ids=("P001", "P002", "P003"), full_ids=("P313", "P172", "P375"), donors=("aytm_0", "aytm_2", "aytm_3")) -> List[Dict[str, str]]:
    rows = []
    for tid, fid, donor in zip(team_ids, full_ids, donors):
        base = _team()[int(tid[-1]) - 1]
        rows.append({**base, "persona_id": fid, "hours_worked_per_week": "40.0", "team_s1_id": tid, **DRIVERS, "driver_donor_id": donor})
    return rows


SPLIT = {"aytm_0": "cal", "aytm_1": "val", "aytm_2": "cal", "aytm_3": "cal"}


def test_driver_columns_match_the_runner() -> None:
    import run_survey
    assert imp.DRIVER_COLUMNS == list(run_survey.DRIVER_COLUMNS)


def test_merge_keeps_the_team_columns_and_numbering_and_adds_the_drivers() -> None:
    merged = imp.merge(_lin(), _team(), SPLIT, "team_s1_id")
    assert [row["persona_id"] for row in merged] == ["P001", "P002", "P003"]
    assert merged[0]["hours_worked_per_week"] == "40"  # the team's string, not his 40.0
    assert merged[0]["member_of_outdoor_club"] == "No" and merged[2]["driver_donor_id"] == "aytm_3"
    assert "team_s1_id" not in merged[0]


@pytest.mark.parametrize("change, message", [
    (lambda rows: rows[1].update(exact_age="99"), "exact_age"),
    (lambda rows: rows[0].update(driver_donor_id="aytm_1"), "val half"),
    (lambda rows: rows[0].update(driver_donor_id="aytm_9"), "not in the split file"),
    (lambda rows: rows[2].update(outdoor_recreation_frequency=" "), "blank"),
    (lambda rows: rows[2].update(team_s1_id="P009"), "not in the team file"),
    (lambda rows: rows[2].update(team_s1_id="P001"), "duplicate"),
])
def test_merge_refuses_anything_that_does_not_line_up(change, message: str) -> None:
    rows = _lin()
    change(rows)
    with pytest.raises(ValueError, match=message):
        imp.merge(rows, _team(), SPLIT, "team_s1_id")


def test_a_subset_of_a_larger_team_file_keeps_its_own_ids() -> None:
    lin = [{**row, "persona_id": row["team_s1_id"]} for row in _lin()[:2]]  # S2 style: ids already in the team file's numbering
    merged = imp.merge(lin, _team(), SPLIT, "persona_id")
    assert [row["persona_id"] for row in merged] == ["P001", "P002"]


def test_main_writes_the_file_and_a_record_and_refuses_bad_input(tmp_path: Path, capsys) -> None:
    lin = _write(tmp_path / "personas_S1_drv.csv", _lin())
    team = _write(tmp_path / "team.csv", _team())
    split = tmp_path / "split.csv"
    split.write_text("respondent_id,rsplit,seed\n" + "".join(f"{k},{v},42\n" for k, v in SPLIT.items()), encoding="utf-8")
    out = tmp_path / "hybrid_personas" / "s1_drv.csv"
    args = ["--lin", str(lin), "--lin-id-column", "team_s1_id", "--team", str(team), "--split", str(split)]
    assert imp.main([*args, "--out", str(out)]) == 0
    rows = list(csv.DictReader(open(out, newline="", encoding="utf-8")))
    assert list(rows[0].keys()) == [*TEAM_HEADER, *imp.DRIVER_COLUMNS, "driver_donor_id"]
    record = json.loads(Path(f"{out}.json").read_text(encoding="utf-8"))
    assert record["persona_kind"] == "hybrid" and record["n_personas"] == 3 and len(record["inputs"]["driver_file"]["sha256"]) == 64

    bad = _lin()
    bad[0]["driver_donor_id"] = "aytm_1"
    _write(lin, bad)
    other = tmp_path / "other.csv"
    assert imp.main([*args, "--out", str(other)]) == 2
    assert "val half" in capsys.readouterr().err and not other.exists()


def test_refuses_to_write_inside_the_repository(tmp_path: Path) -> None:
    lin = _write(tmp_path / "lin.csv", _lin())
    team = _write(tmp_path / "team.csv", _team())
    split = tmp_path / "split.csv"
    split.write_text("respondent_id,rsplit,seed\naytm_0,cal,42\n", encoding="utf-8")
    inside = imp.make_real_split.REPO_ROOT / "research" / "hybrid.csv"
    with pytest.raises(SystemExit) as excinfo:
        imp.main(["--lin", str(lin), "--team", str(team), "--split", str(split), "--out", str(inside)])
    assert excinfo.value.code == 3 and not inside.exists()
