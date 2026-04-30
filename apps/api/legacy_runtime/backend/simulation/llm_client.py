"""OpenRouter client helpers for live survey response generation."""

from __future__ import annotations

import json
import os
from typing import Any

import requests
from dotenv import load_dotenv


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_ENV_LOADED = False


def _ensure_env_loaded() -> None:
	global _ENV_LOADED
	if _ENV_LOADED:
		return
	load_dotenv()
	_ENV_LOADED = True


def openrouter_api_key_available() -> bool:
	"""Return True when OPENROUTER_API_KEY is configured."""
	_ensure_env_loaded()
	key = os.getenv("OPENROUTER_API_KEY", "").strip()
	return bool(key)


def generate_survey_response_with_openrouter(
	model_name: str,
	prompt_payload: dict[str, Any],
	timeout: int = 45,
) -> dict[str, Any]:
	"""Call OpenRouter chat completions and parse strict JSON response safely."""
	_ensure_env_loaded()
	api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
	base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip() or DEFAULT_OPENROUTER_BASE_URL

	if not api_key:
		return {
			"ok": False,
			"parsed_json": None,
			"raw_text": "",
			"error": "OPENROUTER_API_KEY is missing.",
			"status_code": None,
		}

	endpoint = f"{base_url.rstrip('/')}/chat/completions"
	request_body = {
		"model": model_name,
		"messages": prompt_payload.get("messages", []),
		"temperature": prompt_payload.get("temperature", 0.2),
		"max_tokens": prompt_payload.get("max_tokens", 1200),
	}
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
	}

	try:
		response = requests.post(
			endpoint,
			headers=headers,
			json=request_body,
			timeout=timeout,
		)
	except requests.Timeout:
		return {
			"ok": False,
			"parsed_json": None,
			"raw_text": "",
			"error": "OpenRouter request timed out.",
			"status_code": None,
		}
	except requests.RequestException as exc:
		return {
			"ok": False,
			"parsed_json": None,
			"raw_text": "",
			"error": f"OpenRouter request error: {exc}",
			"status_code": None,
		}

	status_code = response.status_code
	if status_code >= 400:
		return {
			"ok": False,
			"parsed_json": None,
			"raw_text": response.text[:2000],
			"error": f"OpenRouter HTTP {status_code}",
			"status_code": status_code,
		}

	try:
		data = response.json()
	except ValueError:
		return {
			"ok": False,
			"parsed_json": None,
			"raw_text": response.text[:4000],
			"error": "OpenRouter returned non-JSON HTTP payload.",
			"status_code": status_code,
		}

	raw_text = _extract_text_content(data)
	parsed_json = _parse_json_strict(raw_text)
	if parsed_json is None:
		return {
			"ok": False,
			"parsed_json": None,
			"raw_text": raw_text,
			"error": "Model output was not valid strict JSON.",
			"status_code": status_code,
		}

	return {
		"ok": True,
		"parsed_json": parsed_json,
		"raw_text": raw_text,
		"error": None,
		"status_code": status_code,
	}


def generate_text_with_openrouter(
	system_prompt: str,
	user_prompt: str,
	model_name: str = "google/gemini-2.5-flash",
	temperature: float = 0.7,
	max_tokens: int = 800,
	timeout: int = 30,
) -> str:
	"""Call OpenRouter and return the plain-text response.

	Raises ``RuntimeError`` on any failure so callers get a simple string-or-error
	interface without inspecting result dicts.
	"""
	_ensure_env_loaded()
	api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
	base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip() or DEFAULT_OPENROUTER_BASE_URL

	if not api_key:
		raise RuntimeError("OPENROUTER_API_KEY is not set.")

	endpoint = f"{base_url.rstrip('/')}/chat/completions"
	body = {
		"model": model_name,
		"messages": [
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
		],
		"temperature": temperature,
		"max_tokens": max_tokens,
	}
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
	}

	try:
		resp = requests.post(endpoint, headers=headers, json=body, timeout=timeout)
	except requests.RequestException as exc:
		raise RuntimeError(f"OpenRouter request failed: {exc}") from exc

	if resp.status_code >= 400:
		raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:500]}")

	text = _extract_text_content(resp.json())
	if not text:
		raise RuntimeError("OpenRouter returned an empty response.")
	return text


def list_openrouter_models(timeout: int = 20) -> dict[str, Any]:
	"""Fetch available OpenRouter models with lightweight pricing metadata."""
	_ensure_env_loaded()
	api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
	base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip() or DEFAULT_OPENROUTER_BASE_URL

	if not api_key:
		return {
			"ok": False,
			"models": [],
			"error": "OPENROUTER_API_KEY is missing.",
			"status_code": None,
		}

	endpoint = f"{base_url.rstrip('/')}/models"
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
	}

	try:
		response = requests.get(endpoint, headers=headers, timeout=timeout)
	except requests.Timeout:
		return {
			"ok": False,
			"models": [],
			"error": "OpenRouter models request timed out.",
			"status_code": None,
		}
	except requests.RequestException as exc:
		return {
			"ok": False,
			"models": [],
			"error": f"OpenRouter models request error: {exc}",
			"status_code": None,
		}

	status_code = response.status_code
	if status_code >= 400:
		return {
			"ok": False,
			"models": [],
			"error": f"OpenRouter models HTTP {status_code}",
			"status_code": status_code,
		}

	try:
		payload = response.json()
	except ValueError:
		return {
			"ok": False,
			"models": [],
			"error": "OpenRouter models response was not JSON.",
			"status_code": status_code,
		}

	items = payload.get("data") if isinstance(payload, dict) else []
	if not isinstance(items, list):
		items = []

	models: list[dict[str, Any]] = []
	for item in items:
		if not isinstance(item, dict):
			continue
		model_id = str(item.get("id") or "").strip()
		if not model_id:
			continue
		pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
		models.append(
			{
				"id": model_id,
				"name": str(item.get("name") or "").strip() or model_id,
				"prompt_price_per_million": _safe_price_to_million(pricing.get("prompt")),
				"completion_price_per_million": _safe_price_to_million(pricing.get("completion")),
			}
		)

	models.sort(key=lambda row: row.get("id", ""))
	return {
		"ok": True,
		"models": models,
		"error": None,
		"status_code": status_code,
	}


def _extract_text_content(payload: dict[str, Any]) -> str:
	try:
		choices = payload.get("choices") or []
		first = choices[0] if choices else {}
		message = first.get("message") or {}
		content = message.get("content")
		if isinstance(content, str):
			return content.strip()
	except Exception:
		return ""
	return ""


def _parse_json_strict(raw_text: str) -> dict[str, Any] | None:
	text = (raw_text or "").strip()
	if not text:
		return None

	if text.startswith("```"):
		text = text.strip("`")
		text = text.replace("json\n", "", 1).strip()

	try:
		parsed = json.loads(text)
	except Exception:
		return None

	if isinstance(parsed, dict):
		return parsed
	return None


def _safe_price_to_million(value: Any) -> float | None:
	"""Convert OpenRouter per-token USD price into USD per 1M tokens."""
	try:
		if value is None or value == "":
			return None
		unit_price = float(value)
		return round(unit_price * 1_000_000.0, 6)
	except Exception:
		return None
