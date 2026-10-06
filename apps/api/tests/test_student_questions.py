from __future__ import annotations

import pytest

from tests.test_studies_endpoints import _create_ready_to_run_study


def _questions(client, study_id):
    return client.get(f"/api/v1/studies/{study_id}").json()["data"]["study"]["survey"]["schema"]["questions"]


def test_add_likert_and_choice_questions_get_sq_ids(client):
    study_id = _create_ready_to_run_study(client)
    first = client.post(f"/api/v1/studies/{study_id}/survey/questions", json={"text": "How appealing is a solar roof?", "question_type": "likert"})
    assert first.status_code == 200
    second = client.post(f"/api/v1/studies/{study_id}/survey/questions",
                         json={"text": "Which colour would you pick?", "question_type": "single_choice", "options": ["Oak", "Slate", "White"]})
    assert second.status_code == 200
    added = [q for q in _questions(client, study_id) if q["id"].startswith("SQ")]
    assert [(q["id"], q["question_type"], len(q["options"])) for q in added] == [("SQ1", "likert", 5), ("SQ2", "single_choice", 3)]


@pytest.mark.parametrize("payload, phrase", [
    ({"text": "Tell us why", "question_type": "open_text"}, "listed options"),
    ({"text": "Pick one", "question_type": "single_choice", "options": ["Only"]}, "2 to 8"),
    ({"text": "Hi", "question_type": "likert"}, "at least 5 characters"),
    ({"text": "Rate it please", "question_type": "likert", "options": ["a", "b", ""]}, "five labels"),
])
def test_invalid_questions_are_refused(client, payload, phrase):
    study_id = _create_ready_to_run_study(client)
    response = client.post(f"/api/v1/studies/{study_id}/survey/questions", json=payload)
    assert response.status_code == 400 and phrase in response.text


def test_only_student_questions_can_be_removed(client):
    study_id = _create_ready_to_run_study(client)
    client.post(f"/api/v1/studies/{study_id}/survey/questions", json={"text": "How appealing is a solar roof?", "question_type": "likert"})
    assert client.delete(f"/api/v1/studies/{study_id}/survey/questions/Q1").status_code == 400
    assert client.delete(f"/api/v1/studies/{study_id}/survey/questions/SQ1").status_code == 200
    assert not any(q["id"] == "SQ1" for q in _questions(client, study_id))


def test_add_returns_survey_and_workflow_and_keeps_original_questions(client):
    study_id = _create_ready_to_run_study(client)
    before = _questions(client, study_id)
    response = client.post(
        f"/api/v1/studies/{study_id}/survey/questions",
        json={"text": "  How   appealing is a solar roof?  ", "question_type": "likert"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"survey", "workflow"}
    assert data["survey"]["question_count"] == len(before) + 1
    after = _questions(client, study_id)
    assert after[:-1] == before
    added = after[-1]
    assert added["text"] == "How appealing is a solar roof?"
    assert (added["min_value"], added["max_value"], added["required"]) == (1, 5, True)


def test_likert_accepts_custom_labels(client):
    study_id = _create_ready_to_run_study(client)
    labels = ["Hate it", "Dislike it", "Neutral", "Like it", "Love it"]
    response = client.post(
        f"/api/v1/studies/{study_id}/survey/questions",
        json={"text": "How do you feel about it?", "question_type": "likert", "options": labels},
    )
    assert response.status_code == 200
    assert _questions(client, study_id)[-1]["options"] == labels


@pytest.mark.parametrize("options", [["Same", "Same"], ["A", "B", " "], [str(n) for n in range(9)]])
def test_single_choice_needs_distinct_filled_options(client, options):
    study_id = _create_ready_to_run_study(client)
    response = client.post(
        f"/api/v1/studies/{study_id}/survey/questions",
        json={"text": "Pick one please", "question_type": "single_choice", "options": options},
    )
    assert response.status_code == 400 and "2 to 8" in response.text


def test_question_text_longer_than_300_is_refused(client):
    study_id = _create_ready_to_run_study(client)
    response = client.post(
        f"/api/v1/studies/{study_id}/survey/questions",
        json={"text": "x" * 301, "question_type": "likert"},
    )
    assert response.status_code == 400 and "at most 300" in response.text


def test_ids_continue_after_removal_without_reusing_a_live_id(client):
    study_id = _create_ready_to_run_study(client)
    for text in ("First added question", "Second added question"):
        client.post(f"/api/v1/studies/{study_id}/survey/questions", json={"text": text, "question_type": "likert"})
    assert client.delete(f"/api/v1/studies/{study_id}/survey/questions/SQ1").status_code == 200
    client.post(f"/api/v1/studies/{study_id}/survey/questions", json={"text": "Third added question", "question_type": "likert"})
    ids = [q["id"] for q in _questions(client, study_id) if q["id"].startswith("SQ")]
    assert ids == ["SQ2", "SQ3"]


def test_removing_a_missing_student_question_is_404(client):
    study_id = _create_ready_to_run_study(client)
    response = client.delete(f"/api/v1/studies/{study_id}/survey/questions/SQ9")
    assert response.status_code == 404


def test_adding_needs_a_saved_survey(client):
    study_id = client.post("/api/v1/studies", json={"study_mode": "neo_smart"}).json()["data"]["study"]["study_id"]
    response = client.post(f"/api/v1/studies/{study_id}/survey/questions", json={"text": "How appealing is a solar roof?", "question_type": "likert"})
    assert response.status_code == 409 and "Save a survey" in response.text
    assert client.delete(f"/api/v1/studies/{study_id}/survey/questions/SQ1").status_code == 409
