"""Leaf scanner service with a concrete CV-first analysis pipeline.

The project does not ship trained weights, so the scanner uses a deterministic
image-analysis fallback when the model is not configured. This preserves the
app's API contract while still providing a realistic disease report pipeline.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
import numpy as np

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "plant_disease_model.keras"
CLASS_LABELS_PATH = MODEL_DIR / "class_labels.json"


class ModelUnavailableError(RuntimeError):
    """Raised when the plant disease model is not available."""


def _model_configured() -> bool:
    return os.getenv("PLANT_DISEASE_MODEL_PATH") is not None or MODEL_PATH.exists()


def _load_class_labels() -> list[str]:
    if CLASS_LABELS_PATH.exists():
        with CLASS_LABELS_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [str(item) for item in data]
        if isinstance(data, dict):
            labels = data.get("labels", [])
            if isinstance(labels, list):
                return [str(item) for item in labels]
    return []


def validate_image_bytes(contents: bytes, filename: str) -> str:
    """Validate an uploaded image and return a safe MIME type."""
    if not contents:
        raise ValueError("Empty file uploaded.")
    if len(contents) > 10 * 1024 * 1024:
        raise ValueError("File too large. Maximum size is 10MB.")

    try:
        image = Image.open(io.BytesIO(contents))
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Invalid image file. Please upload a valid JPEG, PNG, or WebP image.") from exc

    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Unsupported file type. Only JPEG, PNG, and WebP are allowed.")

    return "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix.lstrip('.')}"


def _preprocess_for_model(image_bytes: bytes, target_size: tuple[int, int] = (224, 224)) -> np.ndarray:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = image.resize(target_size)
    arr = np.asarray(image, dtype=np.float32) / 255.0
    return np.expand_dims(arr, axis=0)


def _heuristic_leaf_analysis(image_bytes: bytes) -> dict[str, Any]:
    """Image-based fallback diagnosis without a trained model."""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        rgb = np.asarray(image, dtype=np.float32)
    except Exception:
        rgb = np.zeros((224, 224, 3), dtype=np.float32)

    h, w, _ = rgb.shape
    pixels = max(1, h * w)
    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]

    brown_mask = ((r > 60) & (g < 150) & (b < 120) & (r > b) & (g < r))
    yellow_mask = ((r > 120) & (g > 100) & (b < 100))
    green_mask = (g > r) & (g > b)

    brown_ratio = float(np.count_nonzero(brown_mask)) / pixels
    yellow_ratio = float(np.count_nonzero(yellow_mask)) / pixels
    green_ratio = float(np.count_nonzero(green_mask)) / pixels

    if brown_ratio >= 0.10 or yellow_ratio >= 0.12:
        disease = "Leaf Spot / Fungal Infection"
        severity = "High" if brown_ratio >= 0.18 else "Medium"
        confidence = int(min(96, 62 + (brown_ratio * 110) + (yellow_ratio * 50)))
        affected_area = f"{max(12, round((brown_ratio + yellow_ratio) * 100, 1))}%"
        recommendations = [
            "Prune and remove heavily infected leaves to reduce spread.",
            "Apply a crop-safe fungicide according to the product label and local extension advice.",
        ]
        preventive_measures = [
            "Avoid overhead watering and improve airflow through the canopy.",
            "Rotate crops and sanitize pruning tools between operations.",
        ]
        symptoms = [
            "Dark brown or rust-like lesions with uneven spread across the leaf.",
            "Yellowing around affected tissues or visible leaf tissue collapse.",
        ]
        treatment = [
            "Remove affected foliage and dispose of it away from the crop.",
            "Use a fungicidal spray recommended for the target crop and disease stage.",
        ]
    elif yellow_ratio >= 0.06:
        disease = "Nutrient Stress / Yellowing"
        severity = "Medium"
        confidence = int(min(89, 58 + (yellow_ratio * 130)))
        affected_area = f"{max(8, round(yellow_ratio * 100, 1))}%"
        recommendations = [
            "Check soil moisture and nutrient balance before applying amendments.",
            "Validate whether the crop is under water stress or nutrient deficiency.",
        ]
        preventive_measures = [
            "Use balanced fertilization and avoid overwatering or waterlogging.",
            "Monitor the field regularly during early growth and flowering stages.",
        ]
        symptoms = [
            "Uniform yellowing or chlorosis across the leaf surface.",
            "Reduced vigor or slower growth in the affected crop section.",
        ]
        treatment = [
            "Apply the required nutrient correction based on soil or tissue testing.",
            "Adjust irrigation schedules to avoid prolonged drought or root stress.",
        ]
    elif green_ratio > 0.55:
        disease = "Healthy Leaf"
        severity = "Low"
        confidence = 80
        affected_area = "Minimal"
        recommendations = [
            "Continue normal crop monitoring and maintain current agronomic practices.",
            "Check for pests or environmental stress only if symptoms begin to change.",
        ]
        preventive_measures = [
            "Keep irrigation and nutrient schedules consistent with crop stage.",
            "Inspect the field weekly for early signs of disease or pest pressure.",
        ]
        symptoms = [
            "Leaf color remains predominantly healthy and uniform.",
            "No major lesion, chlorosis, or tissue collapse is visible.",
        ]
        treatment = [
            "Maintain routine field observation and preventive nutrition monitoring.",
            "Continue disease prevention practices to preserve plant vigor.",
        ]
    else:
        disease = "Uncertain – Retake Image"
        severity = "Unknown"
        confidence = 45
        affected_area = "Unknown"
        recommendations = [
            "Retake the photo in brighter daylight with a clean leaf background.",
            "Capture a close-up image showing the full leaf and lesion patterns clearly.",
        ]
        preventive_measures = [
            "Avoid glare, shadows, or a blurred leaf edge.",
            "Use a high-quality image with the leaf centered and well lit.",
        ]
        symptoms = [
            "The current image is not clear enough for a stable diagnosis.",
            "Symptoms are too ambiguous to support a reliable disease label.",
        ]
        treatment = [
            "Re-capture the leaf with consistent lighting and a clearer focus.",
            "Consult an agronomist if symptoms continue to spread or worsen.",
        ]

    return {
        "disease": disease,
        "pathogen": "Unknown; laboratory or field confirmation is required.",
        "visible_signs": symptoms,
        "diagnostic_note": (
            "The image shows color and tissue changes consistent with the reported pattern, "
            "but image-only analysis cannot confirm the causal organism."
        ),
        "confidence": max(0, min(99, confidence)),
        "severity": severity,
        "affected_area": affected_area,
        "recommendations": recommendations,
        "treatment_options": [],
        "treatment_advisory": (
            "Do not select a fungicide from image analysis alone. Use only a product currently registered "
            "and labeled for the crop and disease, follow the current label, and confirm with local agricultural guidance."
        ),
        "non_chemical_actions": [
            "Scout surrounding plants and monitor the upper leaves or flag leaf for new symptoms.",
            "Record disease progression and consult a local extension or KVK adviser if symptoms spread.",
        ],
        "preventive_measures": preventive_measures,
        "symptoms": symptoms,
        "treatment": treatment,
        "confidence_note": (
            "Image-based identification is not definitive. Inspect additional plants and consult "
            "a local extension agent before selecting treatment."
        ),
        "source_guidance": [
            "Use current ICAR, KVK, or State Agriculture Department guidance for confirmation and treatment timing.",
        ],
        "uncertain": disease.startswith("Uncertain") or disease == "Healthy Leaf" or severity == "Unknown",
        "explainability": {
            "leaf_color_ratio": round(green_ratio * 100, 1),
            "spot_ratio": round(brown_ratio * 100, 1),
            "yellowing_ratio": round(yellow_ratio * 100, 1),
            "method": "heuristic_cv_fallback",
        },
    }


def classify_leaf_image(image_bytes: bytes, filename: str) -> dict[str, Any]:
    """Classify the leaf using the trained model when available or the CV heuristic fallback otherwise."""
    model_path = os.getenv("PLANT_DISEASE_MODEL_PATH", str(MODEL_PATH))
    if not os.path.exists(model_path):
        return _heuristic_leaf_analysis(image_bytes)

    try:
        from tensorflow import keras  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise ModelUnavailableError(
            "A trained plant-disease model is available, but the required ML runtime is not installed."
        ) from exc

    try:
        model = keras.models.load_model(model_path)
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise ModelUnavailableError("The trained model file is invalid or unreadable.") from exc

    array = _preprocess_for_model(image_bytes)
    preds = model.predict(array, verbose=0)
    prob = float(np.max(preds))
    idx = int(np.argmax(preds))
    labels = _load_class_labels()
    label = labels[idx] if idx < len(labels) else f"Class {idx}"

    base = _heuristic_leaf_analysis(image_bytes)
    base["disease"] = str(label)
    base["confidence"] = int(round(prob * 100))
    base["uncertain"] = prob < 0.6
    base["explainability"] = {
        **base.get("explainability", {}),
        "method": "trained_model",
        "probability": round(prob, 3),
    }
    return base
