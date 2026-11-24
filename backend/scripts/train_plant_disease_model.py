"""Documentation-only training scaffold for a plant disease classifier.

This project does not include a dataset or trained weights, so the script is a
reproducible template to run locally when the dataset becomes available.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.preprocessing.image import ImageDataGenerator


def build_model(num_classes: int) -> keras.Model:
    base_model = MobileNetV2(
        input_shape=(224, 224, 3),
        include_top=False,
        weights="imagenet",
    )
    base_model.trainable = False

    x = base_model.output
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.2)(x)
    x = layers.Dense(128, activation="relu")(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)
    return keras.Model(inputs=base_model.input, outputs=outputs)


def main() -> None:
    data_dir = Path(os.getenv("DATASET_DIR", "./data/plant_disease_dataset"))
    model_dir = Path(os.getenv("MODEL_OUTPUT_DIR", "./models"))
    model_dir.mkdir(parents=True, exist_ok=True)

    if not data_dir.exists():
        raise FileNotFoundError(
            "Plant disease dataset is not available. Download a public dataset such as PlantVillage and set DATASET_DIR."
        )

    train_dir = data_dir / "train"
    val_dir = data_dir / "val"
    if not train_dir.exists() or not val_dir.exists():
        raise FileNotFoundError(
            "Expected train/ and val/ directories under the dataset root."
        )

    class_names = sorted([p.name for p in train_dir.iterdir() if p.is_dir()])
    if not class_names:
        raise ValueError("No classes found in the training dataset.")

    with (model_dir / "class_labels.json").open("w", encoding="utf-8") as fh:
        json.dump(class_names, fh, indent=2)

    train_gen = ImageDataGenerator(
        rescale=1.0 / 255.0,
        rotation_range=20,
        width_shift_range=0.1,
        height_shift_range=0.1,
        brightness_range=(0.8, 1.2),
        horizontal_flip=True,
    )
    val_gen = ImageDataGenerator(rescale=1.0 / 255.0)

    train_flow = train_gen.flow_from_directory(
        train_dir,
        target_size=(224, 224),
        batch_size=32,
        class_mode="categorical",
    )
    val_flow = val_gen.flow_from_directory(
        val_dir,
        target_size=(224, 224),
        batch_size=32,
        class_mode="categorical",
    )

    model = build_model(len(class_names))
    model.compile(
        optimizer="adam",
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )

    model.fit(
        train_flow,
        validation_data=val_flow,
        epochs=10,
        callbacks=[keras.callbacks.ModelCheckpoint(model_dir / "plant_disease_model.keras", save_best_only=True)],
    )

    print(f"Model saved to {model_dir / 'plant_disease_model.keras'}")
    print(f"Labels saved to {model_dir / 'class_labels.json'}")


if __name__ == "__main__":
    main()
