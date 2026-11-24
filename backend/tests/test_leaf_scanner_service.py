from io import BytesIO

from PIL import Image

from plant_disease_service import classify_leaf_image


def _make_leaf_image(disease_style: str = "leaf_spot") -> bytes:
    image = Image.new("RGB", (512, 512), color=(255, 255, 255))

    # large leaf body
    for x in range(140, 372):
        for y in range(90, 420):
            if (x - 256) ** 2 / 166 ** 2 + (y - 256) ** 2 / 180 ** 2 <= 1:
                image.putpixel((x, y), (80, 170, 65))

    # disease-like lesions
    for center_x, center_y, radius in [
        (210, 190, 26),
        (260, 210, 24),
        (300, 260, 31),
        (220, 310, 29),
    ]:
        for x in range(max(0, center_x - radius), min(511, center_x + radius)):
            for y in range(max(0, center_y - radius), min(511, center_y + radius)):
                if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius ** 2:
                    image.putpixel((x, y), (180, 68, 52) if disease_style == "leaf_spot" else (214, 168, 48))

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_classify_leaf_image_returns_structured_disease_report():
    payload = classify_leaf_image(_make_leaf_image("leaf_spot"), "leaf.png")

    assert isinstance(payload, dict)
    assert payload["disease"]
    assert 0 <= payload["confidence"] <= 100
    assert payload["severity"] in {"High", "Medium", "Low", "Unknown"}
    assert isinstance(payload["recommendations"], list) and payload["recommendations"]
    assert isinstance(payload["preventive_measures"], list) and payload["preventive_measures"]
    assert isinstance(payload["symptoms"], list) and payload["symptoms"]
    assert isinstance(payload["treatment"], list) and payload["treatment"]
