"""Train EfficientNet-B0 using a torchvision ImageFolder dataset."""
from __future__ import annotations
import argparse
from pathlib import Path
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", required=True, type=Path)
    p.add_argument("--output", type=Path, default=Path(
        "backend/models/leaf_disease/efficientnet_b0_leaf_disease.pth"))
    p.add_argument("--epochs", type=int, default=12)
    p.add_argument("--batch-size", type=int, default=24)
    p.add_argument("--learning-rate", type=float, default=1e-4)
    a = p.parse_args()
    train_dir, val_dir = a.data_dir / "train", a.data_dir / "val"
    if not train_dir.is_dir() or not val_dir.is_dir():
        raise SystemExit("Expected dataset/train and dataset/val directories.")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_tfms = transforms.Compose([
        transforms.Resize((224, 224)), transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(12),
        transforms.ColorJitter(brightness=.15, contrast=.15, saturation=.10),
        transforms.ToTensor(),
        transforms.Normalize((.485,.456,.406), (.229,.224,.225))])
    val_tfms = transforms.Compose([
        transforms.Resize((224,224)), transforms.ToTensor(),
        transforms.Normalize((.485,.456,.406), (.229,.224,.225))])
    train_ds = datasets.ImageFolder(train_dir, transform=train_tfms)
    val_ds = datasets.ImageFolder(val_dir, transform=val_tfms)
    if train_ds.classes != val_ds.classes:
        raise SystemExit("Train and val must have identical class folders.")
    if len(train_ds.classes) < 2:
        raise SystemExit("At least two classes are required.")
    train_loader = DataLoader(train_ds, batch_size=a.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=a.batch_size, shuffle=False, num_workers=0)
    # ImageNet weights download on first run if not already cached.
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(train_ds.classes))
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=a.learning_rate)
    criterion = nn.CrossEntropyLoss()
    best = 0.0
    a.output.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(a.epochs):
        model.train()
        running = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
            running += loss.item() * x.size(0)
        model.eval()
        correct = total = 0
        with torch.inference_mode():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                correct += (model(x).argmax(1) == y).sum().item()
                total += y.size(0)
        acc = correct / max(total, 1)
        print(f"Epoch {epoch+1}/{a.epochs} loss={running/max(len(train_ds),1):.4f} val_acc={acc:.4f}")
        if acc > best:
            best = acc
            torch.save({"architecture":"efficientnet_b0",
                        "model_state_dict":model.state_dict(),
                        "class_names":train_ds.classes,
                        "image_size":224,
                        "best_validation_accuracy":best}, a.output)
    print(f"Best validation accuracy: {best:.4f}")
    print(f"Saved checkpoint: {a.output}")
    print("Evaluate on a separate real-farm test set before deployment.")

if __name__ == "__main__":
    main()
