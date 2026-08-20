from collections import Counter
import sys
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas import AudienceFilter, ExperimentPlan, SurveySchema, SurveyQuestion, SimulationRunConfig
from backend.simulation.persona_generator import generate_persona_profiles
from backend.simulation.run_manager import generate_mock_response_records


def run_case(name: str, audience: AudienceFilter) -> None:
    exp = ExperimentPlan(
        sample_size=18,
        selected_models=["GPT", "Gemini"],
        experiment_mode="split",
        reruns_per_persona=1,
    )
    survey = SurveySchema(
        survey_title="Feasibility Test",
        source_format="md",
        questions=[
            SurveyQuestion(
                id="Q1",
                text="Primary use case appeal?",
                question_type="single_choice",
                options=["Home Office", "Wellness Studio", "Guest Room"],
            ),
            SurveyQuestion(
                id="Q2",
                text="How feasible is this in your current home?",
                question_type="likert",
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="Q3",
                text="How likely are you to adopt this in the next 6 months?",
                question_type="single_choice",
                options=["Very likely", "Likely", "Maybe", "Unlikely"],
            ),
            SurveyQuestion(
                id="Q4",
                text="What is your biggest barrier?",
                question_type="single_choice",
                options=["Cost", "Permission / landlord rules", "Limited Space", "Unclear ROI"],
            ),
            SurveyQuestion(id="Q5", text="Tell us your thoughts.", question_type="open_text"),
        ],
    )

    personas = generate_persona_profiles(audience, exp.sample_size)
    cfg = SimulationRunConfig(
        run_id=f"RUN_{name}",
        survey_title=survey.survey_title,
        survey_question_count=len(survey.questions),
        sample_size=exp.sample_size,
        selected_models=exp.selected_models,
        experiment_mode=exp.experiment_mode,
        reruns_per_persona=exp.reruns_per_persona,
    )
    recs = generate_mock_response_records(cfg, survey, audience_filter=audience, persona_profiles=personas)

    q1 = Counter(str(r.answer) for r in recs if r.question_id == "Q1")
    q2 = [int(r.answer) for r in recs if r.question_id == "Q2"]
    q3 = Counter(str(r.answer) for r in recs if r.question_id == "Q3")
    q4 = Counter(str(r.answer) for r in recs if r.question_id == "Q4")
    q5 = [str(r.answer) for r in recs if r.question_id == "Q5"]

    print(f"{name}_Q1 {dict(q1)}")
    print(f"{name}_Q2_MEAN {round(mean(q2), 2)}")
    print(f"{name}_Q3 {dict(q3)}")
    print(f"{name}_Q4 {dict(q4)}")
    print(f"{name}_OPEN_TEXT_SAMPLE {q5[0] if q5 else ''}")


if __name__ == "__main__":
    run_case(
        "RENTER",
        AudienceFilter(
            state="California",
            renter_only=True,
            work_from_home=True,
            income_max=70000,
            lifestyle_tags=["Remote Worker"],
        ),
    )

    run_case(
        "OWNER",
        AudienceFilter(
            state="California",
            homeowner_only=True,
            work_from_home=True,
            income_min=120000,
            lifestyle_tags=["Remote Worker"],
        ),
    )
