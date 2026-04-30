"""Minimal simulation run manager for mock execution."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from backend.simulation.llm_client import generate_survey_response_with_openrouter
from backend.simulation.prompt_builder import build_openrouter_prompt_payload
from backend.schemas import (
	AudienceFilter,
	BusinessProductContext,
	MarketContext,
	MockResponseRecord,
	PersonaProfile,
	SimulationRunConfig,
	SimulationRunResult,
	SurveyQuestion,
	SurveySchema,
)
from backend.simulation.persona_generator import generate_persona_profiles


CONSTRAINT_KEYWORDS = [
	"cost",
	"budget",
	"afford",
	"permission",
	"landlord",
	"hoa",
	"approval",
	"restriction",
	"rules",
	"space",
	"feasible",
	"feasibility",
	"difficult",
	"hard",
	"complex",
	"install",
	"lease",
]
PRACTICAL_USE_CASE_KEYWORDS = [
	"home office",
	"office",
	"workspace",
	"productivity",
	"work",
	"guest",
	"storage",
	"organization",
]
ASPIRATIONAL_USE_CASE_KEYWORDS = [
	"wellness",
	"meditation",
	"retreat",
	"luxury",
	"spa",
	"calm",
	"relaxation",
]
POSITIVE_ADOPTION_KEYWORDS = [
	"very likely",
	"definitely",
	"ready",
	"yes",
	"adopt",
	"purchase",
	"buy",
	"high",
	"easy",
	"feasible",
	"immediately",
]
CAUTIOUS_ADOPTION_KEYWORDS = [
	"unlikely",
	"not likely",
	"not sure",
	"low",
	"later",
	"maybe",
	"depends",
	"difficult",
	"hard",
	"no",
]
PERMISSION_OBJECTION_KEYWORDS = [
	"permission",
	"landlord",
	"hoa",
	"approval",
	"rules",
	"lease",
]
SPACE_OBJECTION_KEYWORDS = ["space", "small", "layout", "footprint", "room"]
INSTALL_OBJECTION_KEYWORDS = ["install", "installation", "setup", "retrofit", "contractor"]
TRUST_OBJECTION_KEYWORDS = ["trust", "reliable", "reliability", "proven", "risk", "quality"]
COMPLEXITY_OBJECTION_KEYWORDS = ["complex", "complicated", "hard", "difficult", "learning"]


_LAST_LIVE_GENERATION_DEBUG: dict = {
	"generation_mode": "mock",
	"model": None,
	"respondents": 0,
	"questions_total": 0,
	"request_errors": 0,
	"questions_fallback_to_mock": 0,
	"questions_parsed_from_live": 0,
}


def get_last_live_generation_debug() -> dict:
	"""Return compact debug stats from the most recent live/mock generation pass."""
	return dict(_LAST_LIVE_GENERATION_DEBUG)


def run_mock_simulation(
	config: SimulationRunConfig,
	generation_mode: str = "mock",
	provider_model_name: str | None = None,
) -> SimulationRunResult:
	"""Execute a mock simulation run and return a completed result summary.

	This function intentionally does not call any model provider. It generates
	deterministic-looking placeholder output for app wiring and workflow tests.
	"""
	total_requested = config.sample_size
	total_generated = total_requested

	preview_count = min(total_generated, 10)
	fake_response_ids = [f"RESP_{index:03d}" for index in range(1, preview_count + 1)]

	return SimulationRunResult(
		run_id=config.run_id,
		status="completed",
		total_requested_responses=total_requested,
		total_generated_responses=total_generated,
		models_used=config.selected_models,
		experiment_mode=config.experiment_mode,
		survey_title=config.survey_title,
		question_count=config.survey_question_count,
		mock_records_generated=fake_response_ids,
		notes=(
			"Simulation result using mock generation path. No real LLM calls were made."
			if generation_mode == "mock"
			else f"Simulation result using OpenRouter live path with model={provider_model_name or 'unknown'}."
		),
		created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
	)


def generate_mock_response_records(
	config: SimulationRunConfig,
	survey_schema: SurveySchema,
	audience_filter: Optional[AudienceFilter] = None,
	persona_profiles: Optional[List[PersonaProfile]] = None,
	business_product_context: Optional[BusinessProductContext] = None,
	market_context: Optional[MarketContext] = None,
	generation_mode: str = "mock",
	openrouter_model_name: str | None = None,
	openrouter_timeout_sec: int = 45,
) -> List[MockResponseRecord]:
	"""Back-compatible entry point for response record generation.

	Supports:
	- mock (default)
	- openrouter_live
	"""
	return generate_response_records(
		config=config,
		survey_schema=survey_schema,
		audience_filter=audience_filter,
		persona_profiles=persona_profiles,
		business_product_context=business_product_context,
		market_context=market_context,
		generation_mode=generation_mode,
		openrouter_model_name=openrouter_model_name,
		openrouter_timeout_sec=openrouter_timeout_sec,
	)


def generate_response_records(
	config: SimulationRunConfig,
	survey_schema: SurveySchema,
	audience_filter: Optional[AudienceFilter] = None,
	persona_profiles: Optional[List[PersonaProfile]] = None,
	business_product_context: Optional[BusinessProductContext] = None,
	market_context: Optional[MarketContext] = None,
	generation_mode: str = "mock",
	openrouter_model_name: str | None = None,
	openrouter_timeout_sec: int = 45,
) -> List[MockResponseRecord]:
	"""Generate mock respondent-level records for every survey question.

	Behavior by mode:
	- split: distribute respondents across selected models (round-robin)
	- mirror: each base respondent appears under every selected model
	- stability: repeated runs per base respondent using the first selected model

	Realism behavior:
	- generate or reuse persona profiles
	- use persona traits to influence answers and segment labels
	"""
	global _LAST_LIVE_GENERATION_DEBUG
	if generation_mode == "openrouter_live":
		return _generate_openrouter_live_response_records(
			config=config,
			survey_schema=survey_schema,
			audience_filter=audience_filter,
			persona_profiles=persona_profiles,
			business_product_context=business_product_context,
			market_context=market_context,
			openrouter_model_name=openrouter_model_name,
			openrouter_timeout_sec=openrouter_timeout_sec,
		)

	_LAST_LIVE_GENERATION_DEBUG = {
		"generation_mode": "mock",
		"model": None,
		"respondents": int(config.sample_size),
		"questions_total": int(config.sample_size * len(survey_schema.questions)),
		"request_errors": 0,
		"questions_fallback_to_mock": 0,
		"questions_parsed_from_live": 0,
	}

	records: List[MockResponseRecord] = []
	personas = persona_profiles or generate_persona_profiles(
		audience_filter=audience_filter,
		sample_size=config.sample_size,
	)
	context_signals = _build_context_signals(business_product_context)
	market_signals = _build_market_signals(market_context, business_product_context)
	if not personas:
		personas = generate_persona_profiles(audience_filter=audience_filter, sample_size=max(1, config.sample_size))

	if config.experiment_mode == "mirror":
		respondent_model_pairs = []
		for respondent_index in range(1, config.sample_size + 1):
			for model in config.selected_models:
				respondent_model_pairs.append((f"RESP_{respondent_index:03d}", model, respondent_index, None))
	elif config.experiment_mode == "stability":
		model = config.selected_models[0]
		respondent_model_pairs = []
		for respondent_index in range(1, config.sample_size + 1):
			for rerun in range(1, config.reruns_per_persona + 1):
				respondent_id = f"RESP_{respondent_index:03d}_R{rerun}"
				respondent_model_pairs.append((respondent_id, model, respondent_index, rerun))
	else:
		respondent_model_pairs = []
		for respondent_index in range(1, config.sample_size + 1):
			model = config.selected_models[(respondent_index - 1) % len(config.selected_models)]
			respondent_model_pairs.append((f"RESP_{respondent_index:03d}", model, respondent_index, None))

	for respondent_id, model, respondent_index, rerun in respondent_model_pairs:
		persona = personas[(respondent_index - 1) % len(personas)]
		segment_label = persona.segment_label or "General Segment"
		for question_index, question in enumerate(survey_schema.questions, start=1):
			answer = _generate_mock_answer(
				question=question,
				persona=persona,
				model=model,
				context_signals=context_signals,
				market_signals=market_signals,
				respondent_index=respondent_index,
				question_index=question_index,
				rerun=rerun,
			)
			records.append(
				MockResponseRecord(
					respondent_id=respondent_id,
					model=model,
					experiment_mode=config.experiment_mode,
					survey_title=config.survey_title,
					question_id=question.id,
					question_text=question.text,
					question_type=question.question_type,
					answer=answer,
					segment_label=segment_label,
					run_id=config.run_id,
				)
			)

	return records


def _generate_openrouter_live_response_records(
	config: SimulationRunConfig,
	survey_schema: SurveySchema,
	audience_filter: Optional[AudienceFilter],
	persona_profiles: Optional[List[PersonaProfile]],
	business_product_context: Optional[BusinessProductContext],
	market_context: Optional[MarketContext],
	openrouter_model_name: str | None,
	openrouter_timeout_sec: int,
) -> List[MockResponseRecord]:
	"""Generate respondent-level records via OpenRouter per persona/respondent."""
	global _LAST_LIVE_GENERATION_DEBUG
	records: List[MockResponseRecord] = []
	personas = persona_profiles or generate_persona_profiles(
		audience_filter=audience_filter,
		sample_size=config.sample_size,
	)
	if not personas:
		personas = generate_persona_profiles(audience_filter=audience_filter, sample_size=max(1, config.sample_size))

	respondent_model_pairs: list[tuple[str, str, int, int | None]] = []
	if config.experiment_mode == "mirror":
		for respondent_index in range(1, config.sample_size + 1):
			for model in config.selected_models:
				respondent_model_pairs.append((f"RESP_{respondent_index:03d}", model, respondent_index, None))
	elif config.experiment_mode == "stability":
		model = config.selected_models[0]
		for respondent_index in range(1, config.sample_size + 1):
			for rerun in range(1, config.reruns_per_persona + 1):
				respondent_id = f"RESP_{respondent_index:03d}_R{rerun}"
				respondent_model_pairs.append((respondent_id, model, respondent_index, rerun))
	else:
		for respondent_index in range(1, config.sample_size + 1):
			model = config.selected_models[(respondent_index - 1) % len(config.selected_models)]
			respondent_model_pairs.append((f"RESP_{respondent_index:03d}", model, respondent_index, None))

	provider_model = (openrouter_model_name or config.selected_models[0]).strip()
	request_errors = 0
	fallback_count = 0
	parsed_count = 0
	total_questions = 0

	for respondent_id, _configured_model, respondent_index, rerun in respondent_model_pairs:
		persona = personas[(respondent_index - 1) % len(personas)]
		segment_label = persona.segment_label or "General Segment"

		prompt_payload = build_openrouter_prompt_payload(
			persona=persona,
			survey_schema=survey_schema,
			business_product_context=business_product_context,
			market_context=market_context,
			audience_filter=audience_filter,
		)

		result = generate_survey_response_with_openrouter(
			model_name=provider_model,
			prompt_payload=prompt_payload,
			timeout=openrouter_timeout_sec,
		)
		if not bool(result.get("ok")):
			request_errors += 1

		parsed_answers = _extract_answer_map_from_openrouter_result(result)

		for question_index, question in enumerate(survey_schema.questions, start=1):
			total_questions += 1
			answer_value = parsed_answers.get(question.id)
			validated_answer = _coerce_openrouter_answer_value(question, answer_value)
			if validated_answer is None:
				fallback_count += 1
				validated_answer = _generate_mock_answer(
					question=question,
					persona=persona,
					model=provider_model,
					context_signals=_build_context_signals(business_product_context),
					market_signals=_build_market_signals(market_context, business_product_context),
					respondent_index=respondent_index,
					question_index=question_index,
					rerun=rerun,
				)
			else:
				parsed_count += 1

			records.append(
				MockResponseRecord(
					respondent_id=respondent_id,
					model=provider_model,
					experiment_mode=config.experiment_mode,
					survey_title=config.survey_title,
					question_id=question.id,
					question_text=question.text,
					question_type=question.question_type,
					answer=validated_answer,
					segment_label=segment_label,
					run_id=config.run_id,
				)
			)

	_LAST_LIVE_GENERATION_DEBUG = {
		"generation_mode": "openrouter_live",
		"model": provider_model,
		"respondents": int(len(respondent_model_pairs)),
		"questions_total": int(total_questions),
		"request_errors": int(request_errors),
		"questions_fallback_to_mock": int(fallback_count),
		"questions_parsed_from_live": int(parsed_count),
	}
	return records


def _extract_answer_map_from_openrouter_result(result: dict) -> dict[str, object]:
	"""Parse and normalize LLM answer payload into {question_id: answer}."""
	if not result or not bool(result.get("ok")):
		return {}

	payload = result.get("parsed_json")
	if not isinstance(payload, dict):
		return {}

	# Supported shapes:
	# 1) {"answers": [{"question_id": "Q1", "answer": ...}, ...]}
	# 2) {"answers": {"Q1": ..., "Q2": ...}}
	# 3) {"Q1": ..., "Q2": ...}
	answer_map: dict[str, object] = {}
	answers = payload.get("answers")

	if isinstance(answers, list):
		for item in answers:
			if not isinstance(item, dict):
				continue
			qid = str(item.get("question_id") or "").strip()
			if not qid:
				continue
			answer_map[qid] = item.get("answer")
		return answer_map

	if isinstance(answers, dict):
		for qid, value in answers.items():
			qid_clean = str(qid).strip()
			if qid_clean:
				answer_map[qid_clean] = value
		return answer_map

	for qid, value in payload.items():
		qid_clean = str(qid).strip()
		if qid_clean:
			answer_map[qid_clean] = value
	return answer_map


def _coerce_openrouter_answer_value(question: SurveyQuestion, value):
	"""Validate and coerce live model answers into expected schema-compatible shapes."""
	if value is None:
		return None

	if question.question_type == "single_choice":
		text = str(value).strip()
		if not text:
			return None
		if question.options:
			for option in question.options:
				if text.lower() == option.lower():
					return option
			return None
		return text

	if question.question_type == "multi_choice":
		if not isinstance(value, list):
			return None
		values = [str(item).strip() for item in value if str(item).strip()]
		if question.options:
			allowed = {option.lower(): option for option in question.options}
			matched = []
			for item in values:
				if item.lower() in allowed:
					matched.append(allowed[item.lower()])
			return matched or None
		return values or None

	if question.question_type == "likert":
		try:
			number = int(float(value))
		except Exception:
			return None
		if question.min_value is not None and number < question.min_value:
			return None
		if question.max_value is not None and number > question.max_value:
			return None
		return number

	if question.question_type == "numeric":
		try:
			return float(value)
		except Exception:
			return None

	# open_text and fallback types
	text = str(value).strip()
	return text or None


def _generate_mock_answer(
	question: SurveyQuestion,
	persona: PersonaProfile,
	model: str,
	context_signals: dict,
	market_signals: dict,
	respondent_index: int,
	question_index: int,
	rerun: int | None,
):
	"""Create a deterministic persona-aware mock answer based on question type."""
	seed = respondent_index + question_index + (rerun or 0) + (sum(ord(ch) for ch in model) % 7)
	text = (question.text or "").lower()
	likely_use_case = (persona.likely_use_case or "").lower()
	likely_barrier = (persona.likely_barrier or "").lower()
	ownership = (persona.ownership or "").lower()
	intent = _question_intent(text)
	is_renter = ownership == "renter"
	is_owner = ownership == "owner"
	target_alignment = _target_alignment_score(context_signals, persona)
	context_remote_focus = bool(context_signals.get("remote_focus", False))
	context_wellness_focus = bool(context_signals.get("wellness_focus", False))
	context_feasibility_caution = bool(context_signals.get("feasibility_caution", False))
	context_premium_price = bool(context_signals.get("premium_price", False))
	context_pain_space_install = bool(context_signals.get("space_install_focus", False))
	context_install_dependency = bool(context_signals.get("install_dependency", False))
	context_practical_focus = bool(context_signals.get("practical_focus", False))
	context_aspirational_focus = bool(context_signals.get("aspirational_focus", False))
	context_remote_target = bool(context_signals.get("remote_target", False))
	market_cost_pressure = bool(market_signals.get("cost_pressure", False))
	market_premium_mismatch = bool(market_signals.get("premium_vs_market_caution", False))
	market_permission_objection = bool(market_signals.get("objection_permission", False))
	market_space_objection = bool(market_signals.get("objection_space", False))
	market_install_objection = bool(market_signals.get("objection_installation", False))
	market_trust_objection = bool(market_signals.get("objection_trust", False))
	market_complexity_objection = bool(market_signals.get("objection_complexity", False))
	market_alternatives_easier_or_cheaper = bool(market_signals.get("alternatives_easier_or_cheaper", False))
	market_relative_value_positive = bool(market_signals.get("relative_value_positive", False))
	market_expected_feature_gap = int(market_signals.get("expected_feature_gap_count", 0))
	market_expected_feature_match = int(market_signals.get("expected_feature_match_count", 0))
	market_budget_price_band = bool(market_signals.get("budget_price_band", False))
	is_low_income = (persona.income_bucket or "") == "low"
	is_high_income = (persona.income_bucket or "") == "high"
	is_remote_or_hybrid = (persona.work_mode or "") in {"remote", "hybrid"}
	is_wellness_oriented = any("wellness" in tag.lower() for tag in persona.lifestyle_tags)
	practical_use_case = any(keyword in likely_use_case for keyword in PRACTICAL_USE_CASE_KEYWORDS)
	aspirational_use_case = any(keyword in likely_use_case for keyword in ASPIRATIONAL_USE_CASE_KEYWORDS)
	high_constraint_profile = is_low_income or is_renter or "cost" in likely_barrier or "space" in likely_barrier
	wellness_support = is_wellness_oriented and (is_owner or (persona.home_type or "").lower() in {"single-family", "townhome"})
	affordability_impact = _compute_affordability_impact(persona)

	if question.question_type == "single_choice":
		if question.options:
			if intent == "use_case":
				if context_remote_focus and (persona.work_mode or "") == "remote":
					office_pick = _match_option_keywords(
						question.options,
						["office", "work", "productivity", "desk", "focus"],
					)
					if office_pick:
						return office_pick

				if context_wellness_focus and any("wellness" in tag.lower() for tag in persona.lifestyle_tags):
					wellness_pick = _match_option_keywords(question.options, ["wellness", "fitness", "yoga", "recovery"])
					if wellness_pick:
						return wellness_pick

			barrier_question = any(
				token in text
				for token in ["barrier", "challenge", "concern", "obstacle", "cost", "constraint", "blocker"]
			)
			if barrier_question:
				ranked_barriers = _rank_barrier_options(
					options=question.options,
					persona=persona,
					context_signals=context_signals,
					market_signals=market_signals,
					likely_barrier=likely_barrier,
					seed=seed,
				)
				if ranked_barriers:
					best_option, best_score = ranked_barriers[0]
					if len(ranked_barriers) > 1:
						second_option, second_score = ranked_barriers[1]
						# Keep deterministic diversity when top barrier scores are close.
						if (best_score - second_score) <= 0.8 and (seed % 4 == 0):
							return second_option
					return best_option

				# Fallbacks for sparse/odd option sets.
				if (context_premium_price and is_low_income) or market_cost_pressure or market_budget_price_band:
					cost_pick = _match_option_keywords(question.options, ["cost", "price", "budget", "afford"])
					if cost_pick:
						return cost_pick
				if market_permission_objection and is_renter:
					permission_pick = _match_option_keywords(question.options, PERMISSION_OBJECTION_KEYWORDS)
					if permission_pick:
						return permission_pick
				if context_feasibility_caution or context_pain_space_install or context_install_dependency:
					context_constraint_pick = _match_option_keywords(question.options, CONSTRAINT_KEYWORDS)
					if context_constraint_pick:
						return context_constraint_pick

			use_case_question = any(token in text for token in ["use case", "use-case", "usage", "purpose", "room"])
			if use_case_question:
				# Appeal can still be high for renters; keep likely use-case preference.
				matched = _match_option(question.options, likely_use_case)
				if matched:
					return matched

			adoption_question = intent in {"adoption", "feasibility"}
			if adoption_question:
				adoption_score = 0.0

				# Baseline persona fit.
				if is_owner:
					adoption_score += 0.8
				if is_renter:
					adoption_score -= 0.8
				if target_alignment >= 2:
					adoption_score += 1.0
				elif target_alignment <= -1:
					adoption_score -= 0.8

				# Business/product context influence.
				if context_practical_focus and is_remote_or_hybrid and (practical_use_case or context_remote_focus):
					adoption_score += 1.0
				if context_remote_target and target_alignment >= 1 and is_remote_or_hybrid:
					adoption_score += 0.5
				if context_aspirational_focus and aspirational_use_case and (not wellness_support or high_constraint_profile):
					adoption_score -= 0.7
				if context_feasibility_caution:
					adoption_score -= 0.6
				if context_premium_price and is_low_income:
					adoption_score -= 0.8

				# Market context influence.
				if market_cost_pressure:
					adoption_score -= 0.9
				if market_budget_price_band and context_premium_price:
					adoption_score -= 0.6
				if market_premium_mismatch:
					adoption_score -= 0.7
				if market_alternatives_easier_or_cheaper:
					adoption_score -= 0.8
				if market_permission_objection and is_renter:
					adoption_score -= 0.8
				if (market_space_objection or market_install_objection or market_complexity_objection):
					adoption_score -= 0.5
				if market_trust_objection:
					adoption_score -= 0.4
				if market_expected_feature_gap > market_expected_feature_match:
					adoption_score -= 0.5
				elif market_expected_feature_match > market_expected_feature_gap:
					adoption_score += 0.5
				if market_relative_value_positive:
					adoption_score += 0.4

				# CEX affordability traits: feasibility gets stronger drag; adoption remains somewhat flexible.
				if intent == "feasibility":
					adoption_score -= affordability_impact["feasibility_penalty"]
				else:
					adoption_score -= affordability_impact["adoption_penalty"]

				picked_option = _pick_graded_adoption_option(
					options=question.options,
					score=adoption_score,
					intent=intent,
					seed=seed,
				)
				if picked_option:
					return picked_option

			return question.options[seed % len(question.options)]
		return "Option A"

	if question.question_type == "multi_choice":
		if not question.options:
			return []

		picked: list[str] = []

		if intent in {"barrier", "feasibility", "adoption"}:
			ranked_barriers = _rank_barrier_options(
				options=question.options,
				persona=persona,
				context_signals=context_signals,
				market_signals=market_signals,
				likely_barrier=likely_barrier,
				seed=seed,
			)
			for option, _score in ranked_barriers[:2]:
				if option not in picked:
					picked.append(option)

		if intent == "use_case" and context_remote_focus and (persona.work_mode or "") == "remote":
			office_pick = _match_option_keywords(question.options, ["office", "work", "productivity"])
			if office_pick and office_pick not in picked:
				picked.append(office_pick)
		if intent == "use_case" and context_wellness_focus and any("wellness" in tag.lower() for tag in persona.lifestyle_tags):
			wellness_pick = _match_option_keywords(question.options, ["wellness", "fitness", "yoga"])
			if wellness_pick and wellness_pick not in picked:
				picked.append(wellness_pick)

		matched_use_case = _match_option(question.options, likely_use_case)
		if matched_use_case:
			picked.append(matched_use_case)

		for tag in persona.lifestyle_tags:
			matched = _match_option(question.options, tag)
			if matched and matched not in picked:
				picked.append(matched)
				break

		if not picked:
			picked.append(question.options[seed % len(question.options)])

		if len(question.options) > 1 and seed % 2 == 1:
			candidate = question.options[(seed + 1) % len(question.options)]
			if candidate not in picked:
				picked.append(candidate)

		return picked[:2]

	if question.question_type == "likert":
		if question.min_value is not None and question.max_value is not None:
			base = 3
			if persona.work_mode == "remote":
				base += 1
			if persona.ownership == "owner":
				base += 1
			if persona.ownership == "renter":
				base -= 1
			if persona.income_bucket == "high":
				base += 1
			if persona.income_bucket == "low":
				base -= 1
			if "cost" in likely_barrier or "space" in likely_barrier:
				base -= 1
			if any(token in text for token in ["afford", "budget", "cost"]):
				base -= 1 if persona.income_bucket == "low" else 0

			if context_premium_price and is_low_income:
				base -= 1
			if market_cost_pressure:
				base -= 1
				if is_low_income:
					base -= 1
			if market_premium_mismatch:
				base -= 1
			if market_alternatives_easier_or_cheaper and intent in {"adoption", "feasibility"}:
				base -= 1
			if market_permission_objection and is_renter and intent in {"adoption", "feasibility", "barrier"}:
				base -= 1
			if (market_space_objection or market_install_objection or market_complexity_objection) and intent in {"adoption", "feasibility", "barrier"}:
				base -= 1
			if market_trust_objection and intent in {"adoption", "feasibility", "barrier"}:
				base -= 1
			if intent in {"adoption", "feasibility"}:
				if market_expected_feature_gap > market_expected_feature_match:
					base -= 1
				elif market_expected_feature_match > market_expected_feature_gap:
					base += 1
				if market_relative_value_positive:
					base += 1
				if intent == "feasibility":
					base -= int(round(affordability_impact["feasibility_penalty"]))
				else:
					base -= int(round(affordability_impact["adoption_penalty"]))
			if context_feasibility_caution and intent in {"feasibility", "adoption", "barrier"}:
				base -= 1
			if context_pain_space_install and intent in {"feasibility", "adoption", "barrier"}:
				base -= 1

			if target_alignment >= 2:
				base += 1
			if target_alignment <= -1:
				base -= 1

			# Practical recurring contexts get stronger adoption/feasibility lift when persona fit is high.
			if intent in {"adoption", "feasibility"}:
				if context_practical_focus and practical_use_case and is_remote_or_hybrid:
					base += 2
				if context_remote_target and target_alignment >= 1 and is_remote_or_hybrid:
					base += 1

				# Aspirational contexts get less automatic adoption lift.
				if context_aspirational_focus and aspirational_use_case:
					base -= 1
					if wellness_support and not high_constraint_profile:
						base += 1

			if context_remote_focus and intent == "use_case" and (persona.work_mode or "") == "remote":
				base += 1
			if context_wellness_focus and intent == "use_case" and any("wellness" in tag.lower() for tag in persona.lifestyle_tags):
				base += 1

			# Separate appeal from realistic adoption/feasibility.
			if intent == "feasibility":
				if is_renter:
					base -= 1
				if is_owner:
					base += 1
			elif intent == "adoption":
				if is_renter:
					base -= 1
				if is_owner:
					base += 1
			elif intent == "barrier":
				if is_renter:
					base -= 1
			elif intent == "use_case":
				# Use-case appeal can remain positive even for renters.
				if persona.work_mode == "remote":
					base += 1

			jitter = (-1 if seed % 5 == 0 else 0) + (1 if seed % 7 == 0 else 0)
			value = base + jitter
			value = max(question.min_value, min(question.max_value, value))

			# Keep feasibility stricter than adoption while avoiding hard saturation.
			if is_renter and intent == "feasibility":
				value = min(value, max(question.min_value, question.max_value - 1))

			return value
		return 3

	if question.question_type == "numeric":
		base = 50
		if persona.work_mode == "remote":
			base += 15
		if persona.income_bucket == "high":
			base += 20
		if persona.income_bucket == "low":
			base -= 15
		if is_owner:
			base += 10
		if is_renter:
			base -= 15
		if "cost" in likely_barrier:
			base -= 10
		if "space" in likely_barrier:
			base -= 5
		if context_premium_price and is_low_income:
			base -= 10
		if market_cost_pressure:
			base -= 8
			if is_low_income:
				base -= 6
		if market_premium_mismatch:
			base -= 6
		if market_alternatives_easier_or_cheaper and intent in {"adoption", "feasibility", "barrier"}:
			base -= 6
		if market_permission_objection and is_renter and intent in {"adoption", "feasibility", "barrier"}:
			base -= 8
		if (market_space_objection or market_install_objection or market_complexity_objection) and intent in {"adoption", "feasibility", "barrier"}:
			base -= 5
		if market_trust_objection and intent in {"adoption", "feasibility", "barrier"}:
			base -= 5
		if context_feasibility_caution and intent in {"adoption", "feasibility", "barrier"}:
			base -= 8
		if context_pain_space_install and intent in {"adoption", "feasibility", "barrier"}:
			base -= 6
		if intent in {"adoption", "feasibility"}:
			if market_expected_feature_gap > market_expected_feature_match:
				base -= 7
			elif market_expected_feature_match > market_expected_feature_gap:
				base += 5
			if market_relative_value_positive:
				base += 4
			if intent == "feasibility":
				base -= int(round(affordability_impact["feasibility_penalty"] * 9))
			else:
				base -= int(round(affordability_impact["adoption_penalty"] * 7))
		if target_alignment >= 2:
			base += 8
		if target_alignment <= -1:
			base -= 8
		if intent in {"adoption", "feasibility"}:
			if context_practical_focus and practical_use_case and is_remote_or_hybrid:
				base += 12
			if context_remote_target and target_alignment >= 1 and is_remote_or_hybrid:
				base += 6
			if context_aspirational_focus and aspirational_use_case:
				base -= 8
				if wellness_support and not high_constraint_profile:
					base += 6
		if context_remote_focus and intent == "use_case" and (persona.work_mode or "") == "remote":
			base += 6
		if context_wellness_focus and intent == "use_case" and any("wellness" in tag.lower() for tag in persona.lifestyle_tags):
			base += 6
		if intent in {"adoption", "feasibility"} and is_renter:
			base -= 15
		if intent in {"adoption", "feasibility"} and is_owner:
			base += 8
		value = base + (seed % 11) - 5
		return max(0, value)

	if is_renter:
		market_note = ""
		if market_cost_pressure or market_alternatives_easier_or_cheaper:
			market_note = " Alternatives in the market feel cheaper or easier, so I am more cautious on value."
		if market_permission_objection:
			market_note += " I also need clear landlord/permission support to move forward."
		return (
			f"Mock response from {persona.persona_id}: I like the {persona.likely_use_case or 'use case'}, "
			f"but as a renter I need permission and a budget-friendly path. "
			f"Main constraint is {persona.likely_barrier or 'feasibility constraints'}. "
			f"Product context fit: {context_signals.get('product_type', 'general product')} / target {context_signals.get('target_customer', 'broad audience')}.{market_note}"
		)
	if is_owner:
		market_note = ""
		if market_expected_feature_gap > market_expected_feature_match:
			market_note = " I would still compare this with alternatives to ensure the feature set matches market expectations."
		elif market_relative_value_positive:
			market_note = " Relative to alternatives, this feels better aligned to my needs."
		return (
			f"Mock response from {persona.persona_id}: This feels practical for my home and I would likely move forward "
			f"if the value is clear. Primary watchout is {persona.likely_barrier or 'upfront cost'}. "
			f"Product context fit: {context_signals.get('product_type', 'general product')} / target {context_signals.get('target_customer', 'broad audience')}.{market_note}")

	market_note = ""
	if market_alternatives_easier_or_cheaper:
		market_note = " I am cautious because available alternatives seem easier or cheaper."
	elif market_relative_value_positive:
		market_note = " Compared with alternatives, this option feels reasonably aligned."
	return (
		f"Mock response from {persona.persona_id}: I see {persona.likely_use_case or 'this use case'} as relevant, "
		f"but {persona.likely_barrier or 'uncertainty'} remains a consideration.{market_note}"
	)


def _match_option(options: list[str], hint: str) -> str | None:
	"""Return option that best matches a hint string using simple token overlap."""
	hint_tokens = {token for token in hint.lower().replace("-", " ").split() if token}
	if not hint_tokens:
		return None

	for option in options:
		option_tokens = set(option.lower().replace("-", " ").split())
		if hint_tokens.intersection(option_tokens):
			return option

	if "office" in hint and options:
		for option in options:
			if "office" in option.lower():
				return option
	if "wellness" in hint and options:
		for option in options:
			if "wellness" in option.lower():
				return option
	if "guest" in hint and options:
		for option in options:
			if "guest" in option.lower():
				return option
	if "cost" in hint and options:
		for option in options:
			if any(token in option.lower() for token in ["cost", "price", "budget", "afford"]):
				return option

	return None


def _match_option_keywords(options: list[str], keywords: list[str]) -> str | None:
	"""Return first option that matches any keyword (case-insensitive)."""
	for option in options:
		option_lower = option.lower()
		if any(keyword in option_lower for keyword in keywords):
			return option
	return None


def _question_intent(question_text: str) -> str:
	"""Classify question intent for lightweight realism heuristics."""
	text = question_text.lower()
	if any(token in text for token in ["barrier", "challenge", "concern", "obstacle", "constraint"]):
		return "barrier"
	if any(token in text for token in ["feasible", "feasibility", "practical", "possible", "permission"]):
		return "feasibility"
	if any(token in text for token in ["adopt", "adoption", "purchase", "buy", "implement", "willing", "likely"]):
		return "adoption"
	if any(token in text for token in ["use case", "use-case", "usage", "purpose", "room", "appeal", "attractive"]):
		return "use_case"
	return "general"


def _build_context_signals(context: Optional[BusinessProductContext]) -> dict:
	"""Build lightweight normalized signals from business/product context."""
	if context is None:
		return {
			"product_type": "",
			"target_customer": "",
			"remote_focus": False,
			"wellness_focus": False,
			"feasibility_caution": False,
			"premium_price": False,
			"space_install_focus": False,
			"install_dependency": False,
			"target_text": "",
		}

	fields = [
		context.product_type or "",
		context.product_description or "",
		context.target_customer or "",
		context.price_range or "",
		context.primary_goal or "",
		" ".join(context.key_features),
		" ".join(context.main_use_cases),
		" ".join(context.main_pain_points_solved),
		" ".join(context.main_barriers_or_concerns),
		" ".join(context.product_image_labels),
		" ".join(context.product_image_objects),
	]
	blob = " ".join(fields).lower()

	remote_focus = any(token in blob for token in ["remote", "work from home", "home office", "productivity"])
	wellness_focus = any(token in blob for token in ["wellness", "fitness", "recovery", "mindfulness", "health"])
	feasibility_caution = any(
		token in blob
		for token in ["install", "installation", "space", "constraint", "permission", "landlord", "feasible", "feasibility"]
	)
	premium_price = any(token in blob for token in ["premium", "high-end", "luxury", "$", "expensive", "high price"])
	space_install_focus = any(token in blob for token in ["space", "layout", "setup", "installation", "retrofit"])
	install_dependency = any(
		token in blob
		for token in [
			"install",
			"installation",
			"setup",
			"retrofit",
			"permit",
			"landlord",
			"contractor",
			"site prep",
			"foundation",
			"electrical",
		]
	)
	practical_focus = any(token in blob for token in ["office", "workspace", "productivity", "focus", "work", "utility"])
	aspirational_focus = any(token in blob for token in ["wellness", "meditation", "retreat", "luxury", "relaxation", "calm"])
	remote_target = any(token in (context.target_customer or "").lower() for token in ["remote", "professional", "work from home", "wfh"])

	return {
		"product_type": context.product_type or "",
		"target_customer": context.target_customer or "",
		"remote_focus": remote_focus,
		"wellness_focus": wellness_focus,
		"feasibility_caution": feasibility_caution,
		"premium_price": premium_price,
		"space_install_focus": space_install_focus,
		"install_dependency": install_dependency,
		"practical_focus": practical_focus,
		"aspirational_focus": aspirational_focus,
		"remote_target": remote_target,
		"target_text": (context.target_customer or "").lower(),
	}


def _build_market_signals(
	market_context: Optional[MarketContext],
	business_product_context: Optional[BusinessProductContext],
) -> dict:
	"""Build readable rule-based signals from saved market context."""
	if market_context is None:
		return {
			"category": "",
			"typical_price_band": "",
			"budget_price_band": False,
			"premium_price_band": False,
			"cost_pressure": False,
			"premium_vs_market_caution": False,
			"objection_space": False,
			"objection_installation": False,
			"objection_permission": False,
			"objection_trust": False,
			"objection_complexity": False,
			"alternatives_easier_or_cheaper": False,
			"relative_value_positive": False,
			"expected_feature_gap_count": 0,
			"expected_feature_match_count": 0,
		}

	product_fields = []
	if business_product_context is not None:
		product_fields = [
			business_product_context.product_type or "",
			business_product_context.product_description or "",
			business_product_context.price_range or "",
			business_product_context.primary_goal or "",
			" ".join(business_product_context.key_features),
			" ".join(business_product_context.main_use_cases),
			" ".join(business_product_context.main_pain_points_solved),
			" ".join(business_product_context.product_image_labels),
			" ".join(business_product_context.product_image_objects),
		]
	product_blob = " ".join(product_fields).lower()

	competitor_blob = " ".join(
		[
			" ".join(
				[
					competitor.name or "",
					competitor.product_type or "",
					competitor.price_range or "",
					" ".join(competitor.key_features),
					" ".join(competitor.strengths),
					" ".join(competitor.weaknesses),
				]
			)
			for competitor in market_context.direct_competitors
		]
	).lower()

	market_fields = [
		market_context.category or "",
		market_context.typical_price_band or "",
		" ".join(market_context.substitutes),
		" ".join(market_context.common_expected_features),
		" ".join(market_context.common_objections),
		competitor_blob,
	]
	market_blob = " ".join(market_fields).lower()

	cost_pressure = _contains_any_token(
		market_blob,
		[
			"cheap",
			"cheaper",
			"low cost",
			"budget",
			"affordable",
			"price sensitive",
			"discount",
			"free",
			"diy",
			"cost",
		],
	)
	premium_product = _contains_any_token(
		product_blob,
		["premium", "high-end", "luxury", "concierge", "white glove", "expensive"],
	)
	market_budget_anchor = _contains_any_token(
		(market_context.typical_price_band or "").lower() + " " + market_blob,
		["budget", "affordable", "entry", "low", "cheap", "mid"],
	)
	market_premium_band = _contains_any_token(
		(market_context.typical_price_band or "").lower() + " " + market_blob,
		["premium", "high-end", "luxury", "upper", "top tier"],
	)
	premium_vs_market_caution = premium_product and market_budget_anchor

	objection_space = _contains_any_token(market_blob, ["space", "small", "layout", "footprint", "room"])
	objection_installation = _contains_any_token(market_blob, ["install", "installation", "setup", "retrofit", "contractor"])
	objection_permission = _contains_any_token(market_blob, ["permission", "landlord", "hoa", "approval", "lease", "rules"])
	objection_trust = _contains_any_token(market_blob, ["trust", "reliable", "reliability", "risk", "quality", "proven"])
	objection_complexity = _contains_any_token(market_blob, ["complex", "complicated", "hard", "difficult", "learning curve"])

	alternatives_easier_or_cheaper = _contains_any_token(
		" ".join(market_context.substitutes).lower() + " " + competitor_blob,
		["easy", "easier", "simple", "cheaper", "low cost", "budget", "no install", "diy", "portable"],
	)

	expected_features_blob = " ".join(market_context.common_expected_features).lower()
	expected_feature_tokens = {
		"turnkey": ["turnkey", "done for you", "full service", "white glove"],
		"warranty": ["warranty", "guarantee"],
		"financing": ["financing", "installments", "monthly", "payment plan"],
		"simplicity": ["simple", "easy", "plug and play", "low effort", "easy install"],
	}

	expected_feature_gap_count = 0
	expected_feature_match_count = 0
	for token_set in expected_feature_tokens.values():
		expected = _contains_any_token(expected_features_blob, token_set)
		matched = _contains_any_token(product_blob, token_set)
		if expected and matched:
			expected_feature_match_count += 1
		elif expected and not matched:
			expected_feature_gap_count += 1

	relative_value_positive = not alternatives_easier_or_cheaper
	if expected_feature_match_count > expected_feature_gap_count and product_blob:
		relative_value_positive = True

	return {
		"category": market_context.category or "",
		"typical_price_band": market_context.typical_price_band or "",
		"budget_price_band": market_budget_anchor,
		"premium_price_band": market_premium_band,
		"cost_pressure": cost_pressure,
		"premium_vs_market_caution": premium_vs_market_caution,
		"objection_space": objection_space,
		"objection_installation": objection_installation,
		"objection_permission": objection_permission,
		"objection_trust": objection_trust,
		"objection_complexity": objection_complexity,
		"alternatives_easier_or_cheaper": alternatives_easier_or_cheaper,
		"relative_value_positive": relative_value_positive,
		"expected_feature_gap_count": expected_feature_gap_count,
		"expected_feature_match_count": expected_feature_match_count,
	}


def _rank_barrier_options(
	options: list[str],
	persona: PersonaProfile,
	context_signals: dict,
	market_signals: dict,
	likely_barrier: str,
	seed: int,
) -> list[tuple[str, float]]:
	"""Return barrier options ranked by deterministic context-sensitive scores."""
	scored: list[tuple[str, float]] = []
	for index, option in enumerate(options):
		score = _score_barrier_option(
			option=option,
			persona=persona,
			context_signals=context_signals,
			market_signals=market_signals,
			likely_barrier=likely_barrier,
		)

		# Deterministic tie-breaker only (very small).
		tie_break = ((seed + index) % 5) * 0.01
		scored.append((option, score + tie_break))

	scored.sort(key=lambda item: item[1], reverse=True)
	return scored


def _score_barrier_option(
	option: str,
	persona: PersonaProfile,
	context_signals: dict,
	market_signals: dict,
	likely_barrier: str,
) -> float:
	"""Score one barrier option using simple deterministic weights."""
	option_lower = option.lower()
	likely_barrier_lower = (likely_barrier or "").lower()
	is_renter = (persona.ownership or "").lower() == "renter"
	is_low_income = (persona.income_bucket or "").lower() == "low"

	is_cost = any(token in option_lower for token in ["cost", "price", "budget", "afford", "value"])
	is_permission = any(token in option_lower for token in ["permit", "permission", "landlord", "hoa", "approval", "lease"])
	is_install = any(token in option_lower for token in ["install", "installation", "setup", "retrofit", "contractor"])
	is_space = any(token in option_lower for token in ["space", "layout", "room", "footprint"])
	is_complexity = any(token in option_lower for token in ["complex", "complicated", "hard", "difficult", "hassle"])
	is_trust = any(token in option_lower for token in ["trust", "reliability", "risk", "quality", "proven"])
	is_none = any(token in option_lower for token in ["no major", "none", "no concerns", "no concern"])

	score = 1.0

	# Personal baseline from persona profile hint.
	if likely_barrier_lower and any(token in likely_barrier_lower for token in option_lower.split()):
		score += 0.6
	if _match_option([option], likely_barrier_lower):
		score += 0.4

	# Cost pressure weighting for budget/alternative-heavy markets.
	if bool(market_signals.get("cost_pressure", False)) and is_cost:
		score += 2.3
	if bool(market_signals.get("budget_price_band", False)) and is_cost:
		score += 1.2
	if bool(market_signals.get("alternatives_easier_or_cheaper", False)) and is_cost:
		score += 1.4
	if bool(market_signals.get("premium_vs_market_caution", False)) and is_cost:
		score += 1.0
	if is_low_income and is_cost:
		score += 1.8

	# Permission/landlord weighting for renters and install-dependent products.
	if bool(market_signals.get("objection_permission", False)) and is_permission:
		score += 1.8
	if is_renter and is_permission:
		score += 1.6
	if is_renter and bool(context_signals.get("install_dependency", False)) and is_permission:
		score += 1.2

	# Install/setup and space still matter, but not globally dominant.
	if bool(market_signals.get("objection_installation", False)) and is_install:
		score += 1.5
	if bool(context_signals.get("space_install_focus", False)) and is_install:
		score += 0.8
	if bool(context_signals.get("install_dependency", False)) and is_install:
		score += 0.8
	if bool(market_signals.get("objection_space", False)) and is_space:
		score += 1.2

	# Complexity/trust as secondary but explicit market-driven barriers.
	if bool(market_signals.get("objection_complexity", False)) and is_complexity:
		score += 1.9
	if bool(market_signals.get("alternatives_easier_or_cheaper", False)) and is_complexity:
		score += 1.2
	if bool(market_signals.get("objection_trust", False)) and is_trust:
		score += 1.3

	# Scenario rebalancing:
	# - In budget/alternative-heavy contexts, cost/complexity should outrank install by default.
	if (bool(market_signals.get("budget_price_band", False)) or bool(market_signals.get("alternatives_easier_or_cheaper", False))) and is_install:
		score -= 0.9
	# - In premium competitive contexts, keep install/permits/cost all relevant.
	if bool(market_signals.get("premium_price_band", False)):
		if is_install or is_permission or is_cost:
			score += 0.5

	# "No concerns" should be unlikely when objections/cost pressure are present.
	if is_none and (
		bool(market_signals.get("objection_installation", False))
		or bool(market_signals.get("objection_permission", False))
		or bool(market_signals.get("objection_complexity", False))
		or bool(market_signals.get("cost_pressure", False))
	):
		score -= 3.0

	return score


def _compute_affordability_impact(persona: PersonaProfile) -> dict[str, float]:
	"""Return normalized affordability penalties from optional CEX-derived traits.

	Penalty interpretation:
	- higher value => stronger drag on positive adoption/feasibility answers
	- feasibility penalty is intentionally stronger than adoption penalty
	"""
	pressure = (persona.affordability_pressure or "").lower()
	housing_burden = (persona.housing_burden_proxy or "").lower()
	spend_intensity = (persona.spend_intensity_bucket or "").lower()

	pressure_score_map = {
		"high_pressure": 1.7,
		"stretched": 1.1,
		"moderate": 0.6,
		"low_pressure": -0.4,
		"comfortable": -0.5,
	}
	housing_score_map = {
		"high": 1.2,
		"medium": 0.6,
		"low": -0.3,
	}
	spend_score_map = {
		"stretched": 1.0,
		"high": 0.5,
		"moderate": 0.2,
		"low": -0.2,
		"conservative": -0.1,
	}

	raw_score = (
		pressure_score_map.get(pressure, 0.0)
		+ housing_score_map.get(housing_burden, 0.0)
		+ spend_score_map.get(spend_intensity, 0.0)
	)

	adoption_penalty = max(-0.6, min(3.6, raw_score * 0.8))
	feasibility_penalty = max(-0.8, min(4.2, raw_score * 1.0))

	return {
		"adoption_penalty": adoption_penalty,
		"feasibility_penalty": feasibility_penalty,
	}


def _pick_graded_adoption_option(options: list[str], score: float, intent: str, seed: int) -> str | None:
	"""Pick a graded single-choice option for adoption/feasibility without hard saturation."""
	if not options:
		return None

	# Keep feasibility stricter than adoption by shifting effective score down.
	effective_score = score - (0.35 if intent == "feasibility" else 0.0)

	strong_positive = _match_option_keywords(options, ["very likely", "definitely", "ready", "immediately"])
	positive = _match_option_keywords(options, ["likely", "yes", "positive", "interested", "willing"])
	neutral = _match_option_keywords(options, ["maybe", "depends", "not sure", "consider", "later"])
	cautious = _match_option_keywords(options, ["unlikely", "not likely", "no", "difficult", "hard"])

	if effective_score >= 2.2:
		return strong_positive or positive or neutral or cautious
	if effective_score >= 0.8:
		if seed % 4 == 0 and strong_positive:
			return strong_positive
		return positive or neutral or strong_positive or cautious
	if effective_score >= -0.8:
		if seed % 3 == 0 and positive:
			return positive
		return neutral or cautious or positive or strong_positive
	if effective_score >= -2.0:
		if seed % 3 == 0 and neutral:
			return neutral
		return cautious or neutral or positive or strong_positive
	return cautious or neutral or positive or strong_positive


def _contains_any_token(text: str, tokens: list[str]) -> bool:
	"""Return True if any token appears in lowercase text."""
	text_lower = (text or "").lower()
	return any(token in text_lower for token in tokens)


def _target_alignment_score(context_signals: dict, persona: PersonaProfile) -> int:
	"""Return a small alignment score between target customer text and persona traits."""
	target_text = str(context_signals.get("target_text", ""))
	if not target_text:
		return 0

	score = 0
	work_mode = (persona.work_mode or "").lower()
	ownership = (persona.ownership or "").lower()
	income = (persona.income_bucket or "").lower()
	lifestyle_text = " ".join(tag.lower() for tag in persona.lifestyle_tags)

	if any(token in target_text for token in ["remote", "wfh", "work from home"]) and work_mode == "remote":
		score += 1
	if "wellness" in target_text and "wellness" in lifestyle_text:
		score += 1
	if any(token in target_text for token in ["homeowner", "owner"]) and ownership == "owner":
		score += 1
	if any(token in target_text for token in ["renter", "renters"]) and ownership == "renter":
		score += 1
	if any(token in target_text for token in ["budget", "value", "affordable"]) and income == "low":
		score += 1
	if any(token in target_text for token in ["premium", "high income", "luxury"]) and income == "high":
		score += 1

	if any(token in target_text for token in ["homeowner", "owner"]) and ownership == "renter":
		score -= 1
	if any(token in target_text for token in ["renter", "renters"]) and ownership == "owner":
		score -= 1
	if "premium" in target_text and income == "low":
		score -= 1
	if any(token in target_text for token in ["budget", "affordable"]) and income == "high":
		score -= 1

	return score
