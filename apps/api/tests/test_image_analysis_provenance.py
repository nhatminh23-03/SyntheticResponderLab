"""R-02: the product image analysis did not say which engine produced it.

Two very different things can produce it -- Google Cloud Vision's label and object detection, or a
general-purpose language model looking at the image. They disagree in kind, not merely in quality, and
the result carried no record of which one ran. A researcher reading "labels" could not tell whether
they came from a detector or from a model's description of the picture.
"""

from __future__ import annotations

from src.adapters.legacy_backend import domain


def _stub_vision(monkeypatch, settings, payload):
    module = type("V", (), {"extract_full_analysis": staticmethod(lambda *a, **k: payload)})
    monkeypatch.setattr(domain, "load_module", lambda name, root: module)


def test_google_vision_results_are_labelled_as_such(test_settings, monkeypatch):
    settings = test_settings.model_copy(update={"google_cloud_api_key": "test-key"})
    _stub_vision(monkeypatch, settings, {"labels": ["chair"], "objects": [], "colors": []})

    result = domain.product_image_analysis(settings=settings, file_bytes=b"x")

    assert result["analysis_source"] == "google_vision"
    assert "Vision" in result["analysis_source_label"]


def test_model_read_results_are_labelled_as_such(test_settings, monkeypatch):
    settings = test_settings.model_copy(
        update={"google_cloud_api_key": "test-key", "openrouter_api_key": "test-openrouter-key"}
    )
    monkeypatch.setattr(
        domain,
        "_openrouter_product_image_analysis",
        lambda **kwargs: {"labels": ["a wooden chair"], "objects": [], "colors": []},
    )

    def _raises(*args, **kwargs):
        raise RuntimeError("vision unavailable")

    module = type("V", (), {"extract_full_analysis": staticmethod(_raises)})
    monkeypatch.setattr(domain, "load_module", lambda name, root: module)

    result = domain.product_image_analysis(settings=settings, file_bytes=b"x")

    assert result["analysis_source"] == "openrouter_model", (
        "a language model's reading of an image must not be reported as detection"
    )
    assert "language model" in result["analysis_source_label"]
