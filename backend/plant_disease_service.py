"""AgriMitra EfficientNet-B0 leaf disease inference service."""
from __future__ import annotations
import io, os
from pathlib import Path
from typing import Any
import torch
import torch.nn as nn
from PIL import Image, UnidentifiedImageError
from torchvision import models, transforms

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = Path(os.getenv("LEAF_DISEASE_MODEL_PATH", str(
    BASE_DIR / "models" / "leaf_disease" / "efficientnet_b0_leaf_disease.pth"
)))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MIN_CONFIDENCE = float(os.getenv("LEAF_MIN_CONFIDENCE", "0.70"))
_model: nn.Module | None = None
_class_names: list[str] = []
_transform = transforms.Compose([
    transforms.Resize((224, 224)), transforms.ToTensor(),
    transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
])

def _build_model(num_classes: int) -> nn.Module:
    model = models.efficientnet_b0(weights=None)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    return model

def load_model() -> None:
    global _model, _class_names
    if _model is not None:
        return
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(
            f"Model weights missing: {MODEL_PATH}. Train the model first."
        )
    checkpoint: dict[str, Any] = torch.load(
        MODEL_PATH, map_location=DEVICE, weights_only=False
    )
    _class_names = checkpoint["class_names"]
    _model = _build_model(len(_class_names))
    _model.load_state_dict(checkpoint["model_state_dict"])
    _model.to(DEVICE).eval()

def predict_plant_disease(image_bytes: bytes) -> dict[str, Any]:
    """Predict from image bytes; abstain when confidence is below configured threshold."""
    if not image_bytes:
        raise ValueError("No image data was provided.")
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc
    if image.width < 80 or image.height < 80:
        raise ValueError("Image is too small. Upload a clearer leaf photo.")
    load_model()
    tensor = _transform(image).unsqueeze(0).to(DEVICE)
    with torch.inference_mode():
        probs = torch.softmax(_model(tensor), dim=1)[0]
    count = min(3, len(_class_names))
    values, indices = torch.topk(probs, k=count)
    top = [{"label": _class_names[int(i)], "confidence": round(float(v), 4)}
           for v, i in zip(values.cpu(), indices.cpu())]
    best = top[0]
    accepted = best["confidence"] >= MIN_CONFIDENCE
    return {
        "success": True, "model": "EfficientNet-B0", "device": str(DEVICE),
        "status": "prediction_available" if accepted else "uncertain",
        "is_reliable_enough_to_display": accepted,
        "predicted_class": best["label"] if accepted else None,
        "confidence": best["confidence"], "top_predictions": top,
        "message": (
            "AI-assisted prediction only; not a confirmed diagnosis. "
            "Confirm with an agricultural expert before treatment."
            if accepted else
            "The model is not confident enough. Try a clear, well-lit leaf photo "
            "and consult a local agricultural expert."
        ),
    }
