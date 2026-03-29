from __future__ import annotations

from src.services.study_service import create_study


def test_canonical_study_serializer_has_default_section_envelopes(db_session, test_settings):
    study = create_study(
        db_session,
        test_settings,
        study_mode=None,
        owner_user_id=None,
        owner_org_id=None,
    )

    assert study.study_id.startswith("std_")
    assert study.lifecycle_status == "draft"
    assert study.study_mode.status == "not_started"
    assert study.audience.status == "not_started"
    assert study.product.status == "not_started"
    assert study.market.status == "not_started"
    assert study.survey.status == "not_started"
    assert study.experiment.status == "not_started"
    assert study.derived.workflow.ready_for_persona_preview is False
