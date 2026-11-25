"""
AgriMitra leaf scanner service: EfficientNet-B0 inference.

This module preserves the legacy names imported by backend/main.py:
- ModelUnavailableError
- validate_image_bytes(...)
- classify_leaf_image(...)

Checkpoint expected at:
backend/models/leaf_disease/efficientnet_b0_leaf_disease.pth

A trained checkpoint is NOT included. Train it with scripts/train_plant_disease_model.py.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from PIL import Image, UnidentifiedImageError
from torchvision import models, transforms


class ModelUnavailableError(RuntimeError):
    """Raised when the trained leaf classifier checkpoint is unavailable."""


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = Path(os.getenv(
    "LEAF_DISEASE_MODEL_PATH",
    str(BASE_DIR / "models" / "leaf_disease" / "efficientnet_b0_leaf_disease.pth"),
))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MIN_CONFIDENCE = float(os.getenv("LEAF_MIN_CONFIDENCE", "0.70"))
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_model: nn.Module | None = None
_class_names: list[str] = []

_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=(0.485, 0.456, 0.406),
        std=(0.229, 0.224, 0.225),
    ),
])


def _build_model(num_classes: int) -> nn.Module:
    model = models.efficientnet_b0(weights=None)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    return model


def validate_image_bytes(contents: bytes, filename: str = "leaf.jpg") -> str:
    """Validate actual image content and return a safe MIME type."""
    if not contents:
        raise ValueError("The uploaded image is empty.")
    if len(contents) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be 10MB or smaller.")

    try:
        with Image.open(io.BytesIO(contents)) as image:
            image.verify()
        with Image.open(io.BytesIO(contents)) as image:
            if image.width < 80 or image.height < 80:
                raise ValueError("Image is too small. Upload a clearer leaf photo.")
            fmt = (image.format or "").upper()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc

    mime_types = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    if fmt not in mime_types:
        raise ValueError("Only JPEG, PNG, and WebP images are supported.")
    return mime_types[fmt]


def load_model() -> None:
    """Load the trained checkpoint once per process."""
    global _model, _class_names
    if _model is not None:
        return
    if not MODEL_PATH.is_file():
        raise ModelUnavailableError(
            f"Trained leaf model not found at {MODEL_PATH}. "
            "Train it using backend/scripts/train_plant_disease_model.py."
        )

    try:
        checkpoint: dict[str, Any] = torch.load(
            MODEL_PATH, map_location=DEVICE, weights_only=True
        )
        _class_names = checkpoint["class_names"]
        if not isinstance(_class_names, list) or len(_class_names) < 2:
            raise ValueError("Checkpoint class_names must contain at least two classes.")
        _model = _build_model(len(_class_names))
        _model.load_state_dict(checkpoint["model_state_dict"])
        _model.to(DEVICE)
        _model.eval()
    except Exception as exc:
        _model = None
        _class_names = []
        raise ModelUnavailableError(f"Could not load leaf model checkpoint: {exc}") from exc


def classify_leaf_image(
    image_bytes: bytes,
    filename: str = "leaf.jpg",
    plant: str | None = None,
) -> dict[str, Any]:
    """
    Return a report compatible with the current Scanner.jsx fields.
    The classifier only recognizes labels represented in its training dataset.
    """
    validate_image_bytes(image_bytes, filename)
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc

    load_model()
    assert _model is not None

    tensor = _transform(image).unsqueeze(0).to(DEVICE)
    with torch.inference_mode():
        probabilities = torch.softmax(_model(tensor), dim=1)[0]

    count = min(3, len(_class_names))
    values, indices = torch.topk(probabilities, k=count)
    top_predictions = [
        {"label": _class_names[int(index)], "confidence": round(float(value), 4)}
        for value, index in zip(values.cpu(), indices.cpu())
    ]

    best = top_predictions[0]
    accepted = best["confidence"] >= MIN_CONFIDENCE
    predicted_label = best["label"] if accepted else "Uncertain"

    # Keep the frontend's existing result contract. Do not invent treatment data.
    note = (
        "Model prediction only; this is not a confirmed diagnosis. "
        "Inspect several plants and confirm with a local KVK/agricultural expert "
        "before selecting treatment."
    )
    if not accepted:
        note = (
            "The model confidence is below the configured display threshold. "
            "Upload a clear, well-lit image and seek local agricultural advice."
        )

    return {
        "disease": predicted_label,
        "pathogen": "Not established by the classifier",
        "visible_signs": [],
        "diagnostic_note": note,
        "confidence": round(best["confidence"] * 100),
        "severity": "Unknown",
        "affected_area": "Unknown",
        "recommendations": [
            "Inspect multiple leaves and nearby plants for similar symptoms.",
            "Take clear photographs of both sides of affected leaves.",
            "Record when symptoms first appeared and recent weather or irrigation.",
            "Confirm the diagnosis with a local KVK or agricultural extension expert.",
        ] if accepted else [
            "Retake the photo in natural light with the leaf in focus.",
            "Include the whole leaf and, if possible, both sides.",
            "Ask a local KVK or agricultural extension expert to inspect the crop.",
        ],
        "treatment_options": [],
        "treatment_advisory": (
            "No pesticide or fungicide is recommended from this model output alone. "
            "Use only products currently registered and labelled for the confirmed "
            "crop and disease, following the label and local agricultural advice."
        ),
        "non_chemical_actions": [
            "Monitor nearby plants for symptom spread.",
            "Avoid handling healthy plants immediately after affected plants.",
        ],
        "preventive_measures": [
            "Use clean tools and healthy planting material.",
            "Monitor crops regularly and maintain appropriate field hygiene.",
        ],
        "confidence_note": (
            f"EfficientNet-B0 top prediction: {best['label']} "
            f"({best['confidence']:.1%}). Softmax confidence is not a calibrated "
            "probability of correctness. Validate on real farm images."
        ),
        "source_guidance": [
            "Confirm with the local Krishi Vigyan Kendra (KVK) or State Agriculture Department."
        ],
        "status": "prediction_available" if accepted else "uncertain",
        "model": "EfficientNet-B0",
        "top_predictions": top_predictions,
        "selected_crop": plant or "Not provided",
    }
