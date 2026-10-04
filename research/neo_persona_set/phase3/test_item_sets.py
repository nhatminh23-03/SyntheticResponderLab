"""Named item sets: Dr. Lin's calibration / validation split, the set-aside items, and item files."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crosswalk  # noqa: E402
import item_sets  # noqa: E402


def test_validation_set_is_lins_thirteen() -> None:
    assert item_sets.LIN_VALIDATION == ["Q0B", "Q1", "Q2", "Q9A", "Q9B", "Q10A", "Q10B", "Q11A", "Q11B", "Q12A", "Q12B", "Q13A", "Q13B"]


def test_calibration_set_on_our_survey_has_ten_items() -> None:
    # 7 barriers + the value drivers our survey carries (Q16, Q17; Q15 is set aside) + sponsorship
    assert item_sets.LIN_CALIBRATION == ["Q5_1", "Q5_2", "Q5_3", "Q5_4", "Q5_5", "Q5_6", "Q5_7", "Q16", "Q17", "Q19"]
    assert not set(item_sets.LIN_CALIBRATION) & set(item_sets.LIN_VALIDATION)


def test_all_scored_drops_the_set_aside_items() -> None:
    comparable = [q.our_id for q in crosswalk.CROSSWALK if q.kind != "none" and q.scored]
    assert len(comparable) == 36
    assert item_sets.NAMED_SETS["all-scored"] == [q for q in comparable if q not in ("Q15", "Q24")]
    assert len(item_sets.NAMED_SETS["all-scored"]) == 34
    for name, ids in item_sets.NAMED_SETS.items():
        assert not set(ids) & set(item_sets.SET_ASIDE), name


def test_load_named_set() -> None:
    assert item_sets.load_item_set("lin13-validation") == ("lin13-validation", item_sets.LIN_VALIDATION)


def test_load_item_file(tmp_path: Path) -> None:
    path = tmp_path / "my_items.txt"
    path.write_text("# purchase items\nQ1\nQ2  # likelihood\n\nQ0B\n", encoding="utf-8")
    assert item_sets.load_item_set(str(path)) == ("my_items.txt", ["Q1", "Q2", "Q0B"])


@pytest.mark.parametrize("bad, message", [
    ("Q99", "not a survey item"),
    ("Q7", "no counterpart in the real survey"),
    ("Q30", "report-only"),
    ("Q15", "set aside"),
])
def test_rejects_items_that_cannot_be_scored(tmp_path: Path, bad: str, message: str) -> None:
    path = tmp_path / "items.txt"
    path.write_text(f"Q1\n{bad}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        item_sets.load_item_set(str(path))


def test_rejects_duplicates_empty_files_and_unknown_names(tmp_path: Path) -> None:
    (tmp_path / "dup.txt").write_text("Q1\nQ1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        item_sets.load_item_set(str(tmp_path / "dup.txt"))
    (tmp_path / "empty.txt").write_text("# nothing\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no items"):
        item_sets.load_item_set(str(tmp_path / "empty.txt"))
    with pytest.raises(ValueError, match="neither a named set"):
        item_sets.load_item_set("lin13-validaton")


# Dr. Lin's item_split.csv (registered 2026-09-20, shared 2026-09-30), copied by hand: item names only.
LIN_FILE_VALIDATION = ["Q0b", "Q1", "Q2", "Q9a", "Q9b", "Q10a", "Q10b", "Q11a", "Q11b", "Q12a", "Q12b", "Q13a", "Q13b"]
LIN_FILE_CALIBRATION = ["Q5_cost", "Q5_hoa", "Q5_permit", "Q5_space", "Q5_financing", "Q5_quality", "Q5_resale",
                        "Q15", "Q16", "Q17", "Q17b", "Q17c", "Q19"]


def test_lin_item_split_file_translates_to_our_sets() -> None:
    assert [item_sets.LIN_ITEM_NAMES[name] for name in LIN_FILE_VALIDATION] == item_sets.LIN_VALIDATION
    ours = [item_sets.LIN_ITEM_NAMES.get(name) for name in LIN_FILE_CALIBRATION]
    assert [name for name, our in zip(LIN_FILE_CALIBRATION, ours) if our is None] == sorted(item_sets.LIN_NOT_ON_OUR_SURVEY)
    kept = [our for our in ours if our is not None and our not in item_sets.SET_ASIDE]
    assert kept == item_sets.LIN_CALIBRATION
    assert "Q15" in ours and "Q15" in item_sets.SET_ASIDE  # his includes Q15; Dr. Wang set it aside


def test_barrier_names_follow_the_crosswalk_rows() -> None:
    rows = dict(zip(["Q5_cost", "Q5_hoa", "Q5_permit", "Q5_space", "Q5_financing", "Q5_quality", "Q5_resale"],
                    ["total cost", "hoa", "permit", "backyard space", "financing", "build quality", "resale"]))
    for name, keyword in rows.items():
        real_key = crosswalk.BY_OUR_ID[item_sets.LIN_ITEM_NAMES[name]].real_key
        assert keyword in real_key.lower(), (name, real_key)


def test_drivers_are_never_scored_in_lins_sets() -> None:
    assert item_sets.LIN_DRIVERS == ["Q0A", "Q3", "Q25", "Q26"]
    for name in ("lin13-validation", "lin13-calibration"):
        assert not set(item_sets.NAMED_SETS[name]) & set(item_sets.LIN_DRIVERS)
