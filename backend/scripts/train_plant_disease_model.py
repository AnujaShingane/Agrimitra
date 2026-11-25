"""Train EfficientNet-B0 using an ImageFolder dataset.

Dataset:
data/train/<class-name>/*.jpg
data/val/<same-class-name>/*.jpg
"""
from __future__ import annotations
import argparse
from pathlib import Path
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(
        "backend/models/leaf_disease/efficientnet_b0_leaf_disease.pth"))
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    args = parser.parse_args()

    train_dir, val_dir = args.data_dir / "train", args.data_dir / "val"
    if not train_dir.is_dir() or not val_dir.is_dir():
        raise SystemExit("Expected data-dir/train and data-dir/val folders.")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    normalize = transforms.Normalize((.485,.456,.406), (.229,.224,.225))
    train_tfms = transforms.Compose([
        transforms.Resize((224,224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(12),
        transforms.ColorJitter(brightness=.15, contrast=.15, saturation=.10),
        transforms.ToTensor(), normalize,
    ])
    val_tfms = transforms.Compose([
        transforms.Resize((224,224)), transforms.ToTensor(), normalize,
    ])
    train_ds = datasets.ImageFolder(train_dir, transform=train_tfms)
    val_ds = datasets.ImageFolder(val_dir, transform=val_tfms)
    if train_ds.classes != val_ds.classes:
        raise SystemExit("Train and validation must have identical class folders.")
    if len(train_ds.classes) < 2:
        raise SystemExit("At least two classes are required.")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size,
                              shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size,
                            shuffle=False, num_workers=0)

    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(train_ds.classes))
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    criterion = nn.CrossEntropyLoss()
    best_accuracy = -1.0
    args.output.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(args.epochs):
        model.train()
        loss_sum = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
            loss_sum += loss.item() * images.size(0)

        model.eval()
        correct = total = 0
        with torch.inference_mode():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                correct += (model(images).argmax(1) == labels).sum().item()
                total += labels.size(0)

        accuracy = correct / max(total, 1)
        print(f"Epoch {epoch+1}/{args.epochs} "
              f"train_loss={loss_sum/max(len(train_ds),1):.4f} "
              f"val_accuracy={accuracy:.4f}")

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            torch.save({
                "architecture": "efficientnet_b0",
                "model_state_dict": model.state_dict(),
                "class_names": train_ds.classes,
                "image_size": 224,
                "best_validation_accuracy": best_accuracy,
            }, args.output)

    print(f"Best validation accuracy: {best_accuracy:.4f}")
    print(f"Checkpoint saved to: {args.output}")
    print("Do not deploy until tested on a separate real-farm test set.")


if __name__ == "__main__":
    main()
