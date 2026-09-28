"""Splitting the real respondents into a fitting half and a scoring half, by Response ID."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_real_split  # noqa: E402
import realdata  # noqa: E402

IDS = [str(1000 + i) for i in range(12)]


def test_split_is_disjoint_complete_and_seeded() -> None:
    fit, score = make_real_split.split_ids(IDS, seed=42)
    assert len(fit) == len(score) == 6
    assert set(fit) | set(score) == set(IDS) and not set(fit) & set(score)
    assert fit == [i for i in IDS if i in set(fit)]  # kept in file order
    assert (fit, score) == make_real_split.split_ids(IDS, seed=42)
    assert fit != make_real_split.split_ids(IDS, seed=43)[0]
    assert len(make_real_split.split_ids(IDS, seed=42, fit_share=0.25)[0]) == 3


def test_read_id_file(tmp_path: Path) -> None:
    path = tmp_path / "ids.txt"
    path.write_text("# fit half\n1000\n1003  # note\n\n1005\n", encoding="utf-8")
    assert realdata.read_id_file(path) == ["1000", "1003", "1005"]
    (tmp_path / "dup.txt").write_text("1000\n1000\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        realdata.read_id_file(tmp_path / "dup.txt")
    (tmp_path / "empty.txt").write_text("# none\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no ids"):
        realdata.read_id_file(tmp_path / "empty.txt")


def test_subset_keeps_only_the_listed_respondents(fake_real_csv: Path) -> None:
    real = realdata.load_real_survey(fake_real_csv)
    half = realdata.subset_by_response_id(real, ["1000", "1001", "1002", "1003", "1004", "1005"])
    assert half.n == 6 and half.columns == real.columns
    assert half.values("Q6") == ["1 - Not interested", "1 - Not interested", "2", "2", "3", "3"]
    assert real.n == 12  # the original is untouched
    with pytest.raises(ValueError, match="not in the real file"):
        realdata.subset_by_response_id(real, ["1000", "9999"])


def test_main_writes_both_halves_and_a_record(fake_real_csv: Path, tmp_path: Path) -> None:
    out = tmp_path / "real_splits" / "provisional-seed42"
    assert make_real_split.main(["--real", str(fake_real_csv), "--out", str(out), "--seed", "42"]) == 0
    fit, score = realdata.read_id_file(out / "fit_ids.txt"), realdata.read_id_file(out / "score_ids.txt")
    assert (fit, score) == make_real_split.split_ids(IDS, seed=42)
    record = json.loads((out / "split.json").read_text(encoding="utf-8"))
    assert record["seed"] == 42 and record["n_fit"] == 6 and record["n_score"] == 6 and record["label"] == "provisional"
    assert len(record["real"]["sha256"]) == 64
    assert "PROVISIONAL" in (out / "score_ids.txt").read_text(encoding="utf-8")


def test_refuses_to_write_next_to_the_real_file_or_inside_the_repo(fake_real_csv: Path) -> None:
    for bad in (fake_real_csv.parent / "splits", make_real_split.REPO_ROOT / "research" / "splits"):
        with pytest.raises(SystemExit) as excinfo:
            make_real_split.main(["--real", str(fake_real_csv), "--out", str(bad)])
        assert excinfo.value.code == 3
        assert not bad.exists()
