"""
Train a simple CNN anti-spoof / liveness classifier for the AI service.

This is a baseline deep-learning model for passive liveness detection.
It is intended to complement ArcFace, which remains the identity feature extractor.

Expected dataset layout (recommended):

    data/antispoof/
      train/
        live/
          *.jpg
        spoof/
          *.jpg
      val/
        live/
          *.jpg
        spoof/
          *.jpg

If `train/` and `val/` do not exist, the script also accepts:

    data/antispoof/
      live/
        *.jpg
      spoof/
        *.jpg

and performs an automatic train/validation split.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Tuple

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = AI_SERVICE_ROOT / "data" / "antispoof"
DEFAULT_OUTPUT_DIR = AI_SERVICE_ROOT / "checkpoints"

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms
from tqdm import tqdm


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class SimpleAntiSpoofCNN(nn.Module):
    """Small baseline CNN for binary live-vs-spoof classification."""

    def __init__(self, num_classes: int = 2):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.30),
            nn.Linear(256, 64),
            nn.ReLU(inplace=True),
            nn.Dropout(0.20),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        return self.classifier(x)


def build_transforms(image_size: int) -> Tuple[transforms.Compose, transforms.Compose]:
    train_tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.10),
        transforms.ToTensor(),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
    ])
    return train_tf, eval_tf


def validate_classes(classes: list[str]) -> None:
    normalized = [c.lower() for c in classes]
    if normalized != ["live", "spoof"]:
        raise ValueError(
            "Expected class folders named exactly 'live' and 'spoof'. "
            f"Found: {classes}"
        )


def load_datasets(data_dir: Path, image_size: int, train_split: float, seed: int):
    train_tf, eval_tf = build_transforms(image_size)

    train_root = data_dir / "train"
    val_root = data_dir / "val"

    if train_root.exists() and val_root.exists():
        train_dataset = datasets.ImageFolder(train_root, transform=train_tf)
        val_dataset = datasets.ImageFolder(val_root, transform=eval_tf)
        validate_classes(train_dataset.classes)
        validate_classes(val_dataset.classes)
        classes = train_dataset.classes
        return train_dataset, val_dataset, classes

    full_train = datasets.ImageFolder(data_dir, transform=train_tf)
    full_eval = datasets.ImageFolder(data_dir, transform=eval_tf)
    validate_classes(full_train.classes)

    indices = list(range(len(full_train)))
    rng = random.Random(seed)
    rng.shuffle(indices)

    split_idx = max(1, int(len(indices) * train_split))
    split_idx = min(split_idx, len(indices) - 1)
    train_indices = indices[:split_idx]
    val_indices = indices[split_idx:]

    train_dataset = Subset(full_train, train_indices)
    val_dataset = Subset(full_eval, val_indices)
    return train_dataset, val_dataset, full_train.classes


def accuracy_from_logits(logits: torch.Tensor, labels: torch.Tensor) -> float:
    preds = logits.argmax(dim=1)
    return float((preds == labels).float().mean().item())


def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    total_acc = 0.0

    for images, labels in tqdm(loader, desc="train", leave=False):
        images = images.to(device)
        labels = labels.to(device)

        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += float(loss.item())
        total_acc += accuracy_from_logits(logits, labels)

    count = max(1, len(loader))
    return total_loss / count, total_acc / count


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    total_acc = 0.0

    for images, labels in tqdm(loader, desc="val", leave=False):
        images = images.to(device)
        labels = labels.to(device)
        logits = model(images)
        loss = criterion(logits, labels)

        total_loss += float(loss.item())
        total_acc += accuracy_from_logits(logits, labels)

    count = max(1, len(loader))
    return total_loss / count, total_acc / count


def export_onnx(model: nn.Module, image_size: int, output_path: Path) -> None:
    model = model.cpu().eval()
    dummy = torch.randn(1, 3, image_size, image_size)
    torch.onnx.export(
        model,
        dummy,
        str(output_path),
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
    )


def _resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else (AI_SERVICE_ROOT / path).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train baseline CNN anti-spoof model")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Path to anti-spoof dataset (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to save weights (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--image-size", type=int, default=128)
    parser.add_argument("--train-split", type=float, default=0.8, help="Used only when val/ is absent")
    parser.add_argument("--num-workers", type=int, default=0, help="Use 0 on Windows for stability")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--export-onnx", action="store_true", help="Export best checkpoint to ONNX")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    args.data_dir = _resolve_project_path(args.data_dir)
    args.output_dir = _resolve_project_path(args.output_dir)

    if not args.data_dir.exists():
        raise FileNotFoundError(f"Dataset directory not found: {args.data_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    train_ds, val_ds, classes = load_datasets(
        data_dir=args.data_dir,
        image_size=args.image_size,
        train_split=args.train_split,
        seed=args.seed,
    )

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=torch.cuda.is_available(),
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SimpleAntiSpoofCNN(num_classes=2).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    print(f"Using device      : {device}")
    print(f"Train samples     : {len(train_ds)}")
    print(f"Validation samples: {len(val_ds)}")
    print(f"Classes           : {classes}")

    best_val_acc = -1.0
    best_path = args.output_dir / "best_cnn_antispoof.pt"
    history = []

    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)

        metrics = {
            "epoch": epoch,
            "train_loss": round(train_loss, 4),
            "train_acc": round(train_acc, 4),
            "val_loss": round(val_loss, 4),
            "val_acc": round(val_acc, 4),
        }
        history.append(metrics)
        print(json.dumps(metrics))

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "classes": classes,
                    "image_size": args.image_size,
                    "val_acc": val_acc,
                },
                best_path,
            )

    summary_path = args.output_dir / "training_summary.json"
    summary_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    print(f"Saved best checkpoint to: {best_path}")
    print(f"Saved training summary to: {summary_path}")

    if args.export_onnx:
        checkpoint = torch.load(best_path, map_location="cpu")
        model.load_state_dict(checkpoint["model_state"])
        onnx_path = args.output_dir / "custom-cnn-antispoof.onnx"
        export_onnx(model, args.image_size, onnx_path)
        print(f"Exported ONNX model to: {onnx_path}")


if __name__ == "__main__":
    main()
