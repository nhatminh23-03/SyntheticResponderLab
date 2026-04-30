"""Google Cloud Vision API helpers for product image analysis."""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

import requests


VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/cloud-vision"


def _clean_text(value: Any) -> str:
    """Normalize whitespace and coerce empty-ish values to an empty string."""
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _dedupe_strings(values: list[str], max_results: int | None = None) -> list[str]:
    """Deduplicate strings while preserving order, case-insensitively."""
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
        if max_results is not None and len(deduped) >= max_results:
            break
    return deduped


def _sorted_descriptions(
    items: list[dict[str, Any]],
    *,
    description_key: str,
    score_keys: tuple[str, ...],
    max_results: int,
) -> list[str]:
    """Return top descriptions sorted by confidence-like scores."""
    ranked: list[tuple[float, str]] = []
    for item in items:
        description = _clean_text(item.get(description_key))
        if not description:
            continue
        score = 0.0
        for score_key in score_keys:
            raw_score = item.get(score_key)
            if isinstance(raw_score, (int, float)):
                score = max(score, float(raw_score))
        ranked.append((score, description))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return _dedupe_strings([description for _, description in ranked], max_results=max_results)


def _extract_colors(response: dict[str, Any], max_results: int = 5) -> list[dict[str, Any]]:
    """Return dominant colors sorted by image share."""
    colors: list[dict[str, Any]] = []
    seen_hexes: set[str] = set()
    image_props = response.get("imagePropertiesAnnotation", {})
    dominant = image_props.get("dominantColors", {}).get("colors", [])
    dominant = sorted(
        dominant,
        key=lambda color: float(color.get("pixelFraction") or 0.0),
        reverse=True,
    )
    for color in dominant:
        rgb = color.get("color", {})
        r = max(0, min(255, int(rgb.get("red", 0) or 0)))
        g = max(0, min(255, int(rgb.get("green", 0) or 0)))
        b = max(0, min(255, int(rgb.get("blue", 0) or 0)))
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        if hex_color in seen_hexes:
            continue
        pixel_fraction = round(float(color.get("pixelFraction") or 0.0) * 100, 1)
        if pixel_fraction <= 0:
            continue
        seen_hexes.add(hex_color)
        colors.append({"hex": hex_color, "percentage": pixel_fraction})
        if len(colors) >= max_results:
            break
    return colors


def _build_jwt(service_account: dict[str, Any]) -> str:
    """Build a self-signed JWT for Google OAuth2 token exchange."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=")

    now = int(time.time())
    claim_set = {
        "iss": service_account["client_email"],
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    payload = base64.urlsafe_b64encode(
        json.dumps(claim_set).encode()
    ).rstrip(b"=")

    signing_input = header + b"." + payload

    # Use the cryptography library or PyJWT if available; fall back to error.
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(
            service_account["private_key"].encode(), password=None
        )
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]
    except ImportError:
        raise RuntimeError(
            "The 'cryptography' package is required for service account auth. "
            "Run: pip install cryptography"
        )

    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return (signing_input + b"." + sig_b64).decode()


def _get_access_token(service_account: dict[str, Any]) -> str:
    """Exchange a service account JSON key for a short-lived access token."""
    jwt = _build_jwt(service_account)
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()["access_token"]


def _call_vision_api(
    image_bytes: bytes,
    features: list[dict[str, Any]],
    service_account_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send an image to Google Cloud Vision with the given features.

    Returns the first response dict from the API.
    """
    payload = {
        "requests": [
            {
                "image": {"content": base64.b64encode(image_bytes).decode("utf-8")},
                "features": features,
            }
        ]
    }

    if service_account_info is not None:
        access_token = _get_access_token(service_account_info)
        resp = requests.post(
            VISION_API_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=15,
        )
    else:
        api_key = os.getenv("GOOGLE_CLOUD_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "No credentials provided. Upload a service account JSON key "
                "or set the GOOGLE_CLOUD_API_KEY environment variable."
            )
        resp = requests.post(
            VISION_API_URL,
            params={"key": api_key},
            json=payload,
            timeout=15,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Vision API returned {resp.status_code}: {resp.text}")

    payload = resp.json().get("responses", [{}])[0]
    error = payload.get("error", {})
    if error:
        message = _clean_text(error.get("message")) or "Unknown Google Vision error."
        code = error.get("code")
        if code:
            raise RuntimeError(f"Vision API error {code}: {message}")
        raise RuntimeError(f"Vision API error: {message}")
    return payload


def extract_labels(
    image_bytes: bytes,
    max_results: int = 15,
    service_account_info: dict[str, Any] | None = None,
) -> list[str]:
    """Send an image to Google Cloud Vision and return detected labels.

    Returns a list of label descriptions sorted by confidence (highest first).
    Raises ``RuntimeError`` on API errors.
    """
    features = [{"type": "LABEL_DETECTION", "maxResults": max_results}]
    response = _call_vision_api(image_bytes, features, service_account_info)
    annotations = response.get("labelAnnotations", [])
    return _sorted_descriptions(
        annotations,
        description_key="description",
        score_keys=("score", "topicality"),
        max_results=max_results,
    )


def extract_full_analysis(
    image_bytes: bytes,
    max_results: int = 15,
    service_account_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run multiple Vision detections and return a combined result.

    Returns a dict with keys:
    - labels: list of label strings
    - objects: list of object name strings
    - text: detected text (OCR) or empty string
    - colors: list of dominant color dicts with hex and percentage
    """
    features = [
        {"type": "LABEL_DETECTION", "maxResults": max_results},
        {"type": "OBJECT_LOCALIZATION", "maxResults": max_results},
        {"type": "LOGO_DETECTION", "maxResults": 5},
        {"type": "TEXT_DETECTION", "maxResults": 10},
        {"type": "IMAGE_PROPERTIES"},
        {"type": "WEB_DETECTION", "maxResults": 10},
    ]
    response = _call_vision_api(image_bytes, features, service_account_info)

    labels = _sorted_descriptions(
        response.get("labelAnnotations", []),
        description_key="description",
        score_keys=("score", "topicality"),
        max_results=max_results,
    )
    raw_objects = response.get("localizedObjectAnnotations", [])
    objects = _sorted_descriptions(
        raw_objects,
        description_key="name",
        score_keys=("score",),
        max_results=max_results,
    )
    logos = _sorted_descriptions(
        response.get("logoAnnotations", []),
        description_key="description",
        score_keys=("score",),
        max_results=5,
    )
    text_annotations = response.get("textAnnotations", [])
    detected_text = _clean_text(text_annotations[0].get("description")) if text_annotations else ""
    colors = _extract_colors(response)

    # Web entities (related topics from the web)
    web_detection = response.get("webDetection", {})
    web_entities = _sorted_descriptions(
        web_detection.get("webEntities", []),
        description_key="description",
        score_keys=("score",),
        max_results=10,
    )

    return {
        "labels": labels,
        "objects": objects,
        "logos": logos,
        "text": detected_text,
        "colors": colors,
        "web_entities": web_entities,
    }


def generate_description_from_labels(
    labels: list[str],
    product_name: str | None = None,
    objects: list[str] | None = None,
    detected_text: str | None = None,
    colors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Use an LLM to turn Vision analysis into a product description and key features.

    Returns ``{"description": str, "key_features": [str, ...]}``.
    Raises ``RuntimeError`` on failure.
    """
    from backend.simulation.llm_client import generate_text_with_openrouter

    name_hint = f' called "{product_name}"' if product_name else ""

    # Build a rich context from all Vision signals
    vision_context_parts = [f"Labels: {', '.join(labels)}"]
    if objects:
        vision_context_parts.append(f"Objects detected: {', '.join(objects)}")
    if detected_text:
        vision_context_parts.append(f"Text visible in image: {detected_text}")
    if colors:
        color_desc = ", ".join(
            f"{c['hex']} ({c['percentage']}%)" for c in colors
        )
        vision_context_parts.append(f"Dominant colors: {color_desc}")
    vision_context = "\n".join(vision_context_parts)

    system_prompt = (
        "You are a product analyst. Given visual analysis data detected from a product image "
        "(labels, identified objects, any visible text, and dominant colors), "
        "generate a concise product description and a list of key features. "
        "Use the color palette to describe the product's aesthetic. "
        "Use detected objects for specific physical attributes. "
        "Use any visible text for branding or model info. "
        "Return ONLY valid JSON with two keys: "
        '"description" (a 2-3 sentence product description) and '
        '"key_features" (a list of 5-8 short feature strings). '
        "No markdown, no extra keys."
    )
    user_prompt = (
        f"Visual analysis of a product image{name_hint}:\n\n"
        f"{vision_context}\n\n"
        "Based on all of these visual cues, generate a product description and key features."
    )

    raw = generate_text_with_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.5,
        max_tokens=600,
    )

    # Parse the JSON response
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").replace("json\n", "", 1).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"LLM did not return valid JSON: {text[:300]}")

    return {
        "description": result.get("description", ""),
        "key_features": result.get("key_features", []),
    }


# --- JSON output contract shared by full-context generators ---

_FULL_CONTEXT_FIELDS = (
    '"business_name", "industry", "product_name", "product_type", '
    '"product_description" (2-3 sentences), "target_customer", "price_range", '
    '"primary_goal", "key_features" (list of 5-8 strings), '
    '"main_use_cases" (list of 3-6 strings), '
    '"main_pain_points_solved" (list of 3-5 strings), '
    '"main_barriers_or_concerns" (list of 3-5 strings)'
)


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON from an LLM response."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").replace("json\n", "", 1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"LLM did not return valid JSON: {text[:300]}")


def generate_full_context_from_image(
    labels: list[str],
    product_name: str | None = None,
    objects: list[str] | None = None,
    detected_text: str | None = None,
    colors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Use an LLM to turn Vision analysis into a full BusinessProductContext.

    Returns a dict matching all BusinessProductContext fields.
    """
    from backend.simulation.llm_client import generate_text_with_openrouter

    name_hint = f' called "{product_name}"' if product_name else ""

    vision_context_parts = [f"Labels: {', '.join(labels)}"]
    if objects:
        vision_context_parts.append(f"Objects detected: {', '.join(objects)}")
    if detected_text:
        vision_context_parts.append(f"Text visible in image: {detected_text}")
    if colors:
        color_desc = ", ".join(f"{c['hex']} ({c['percentage']}%)" for c in colors)
        vision_context_parts.append(f"Dominant colors: {color_desc}")
    vision_context = "\n".join(vision_context_parts)

    system_prompt = (
        "You are a product analyst. Given visual analysis data from a product image, "
        "generate a complete product and business context. "
        "Return ONLY valid JSON with these keys: "
        f"{_FULL_CONTEXT_FIELDS}. "
        "Infer as much as you can from the visual cues. "
        "For fields you cannot determine, use a reasonable placeholder. "
        "No markdown, no extra keys."
    )
    user_prompt = (
        f"Visual analysis of a product image{name_hint}:\n\n"
        f"{vision_context}\n\n"
        "Generate a complete business and product context from these visual cues."
    )

    raw = generate_text_with_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.5,
        max_tokens=1000,
    )
    return _parse_llm_json(raw)


def generate_full_context_from_url(page_text: str) -> dict[str, Any]:
    """Use an LLM to turn scraped product page text into a full BusinessProductContext.

    Returns a dict matching all BusinessProductContext fields.
    """
    from backend.simulation.llm_client import generate_text_with_openrouter

    system_prompt = (
        "You are a product analyst. Given scraped text from a product webpage, "
        "extract and generate a complete product and business context. "
        "Return ONLY valid JSON with these keys: "
        f"{_FULL_CONTEXT_FIELDS}. "
        "Extract real information from the page content. "
        "For fields not found on the page, infer a reasonable value. "
        "No markdown, no extra keys."
    )
    user_prompt = (
        "Scraped product page content:\n\n"
        f"{page_text}\n\n"
        "Extract a complete business and product context from this page."
    )

    raw = generate_text_with_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=1000,
    )
    return _parse_llm_json(raw)
