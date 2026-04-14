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
import csv
import json
import random
from pathlib import Path
from typing import Any, Tuple

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


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def round_metric(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def binary_roc_auc(scores: list[float], labels: list[int]) -> float | None:
    positive_count = sum(labels)
    negative_count = len(labels) - positive_count
    if positive_count == 0 or negative_count == 0:
        return None

    ranked = sorted(zip(scores, labels), key=lambda item: item[0])
    rank_sum = 0.0
    rank = 1
    index = 0

    while index < len(ranked):
        score = ranked[index][0]
        end = index
        positive_in_group = 0
        while end < len(ranked) and ranked[end][0] == score:
            positive_in_group += ranked[end][1]
            end += 1

        average_rank = (rank + (rank + (end - index) - 1)) / 2.0
        rank_sum += positive_in_group * average_rank
        rank += end - index
        index = end

    return (rank_sum - positive_count * (positive_count + 1) / 2.0) / (positive_count * negative_count)


def binary_pr_auc(scores: list[float], labels: list[int]) -> float | None:
    positive_count = sum(labels)
    if positive_count == 0:
        return None

    ranked = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    true_positive = 0
    false_positive = 0
    previous_recall = 0.0
    area = 0.0
    index = 0

    while index < len(ranked):
        score = ranked[index][0]
        end = index
        while end < len(ranked) and ranked[end][0] == score:
            if ranked[end][1] == 1:
                true_positive += 1
            else:
                false_positive += 1
            end += 1

        recall = true_positive / positive_count
        precision = safe_div(true_positive, true_positive + false_positive)
        area += (recall - previous_recall) * precision
        previous_recall = recall
        index = end

    return area


def threshold_metrics(scores: list[float], labels: list[int], threshold: float) -> dict[str, float]:
    true_positive = 0
    true_negative = 0
    false_positive = 0
    false_negative = 0

    for score, label in zip(scores, labels):
        predicted_live = score >= threshold
        actual_live = label == 1

        if predicted_live and actual_live:
            true_positive += 1
        elif predicted_live and not actual_live:
            false_positive += 1
        elif not predicted_live and actual_live:
            false_negative += 1
        else:
            true_negative += 1

    live_total = true_positive + false_negative
    spoof_total = true_negative + false_positive
    accuracy = safe_div(true_positive + true_negative, len(labels))
    precision = safe_div(true_positive, true_positive + false_positive)
    recall = safe_div(true_positive, live_total)
    f1_score = safe_div(2 * precision * recall, precision + recall)
    apcer = safe_div(false_positive, spoof_total)
    bpcer = safe_div(false_negative, live_total)
    acer = (apcer + bpcer) / 2.0
    tnr = safe_div(true_negative, spoof_total)

    return {
        "threshold": threshold,
        "tp": float(true_positive),
        "tn": float(true_negative),
        "fp": float(false_positive),
        "fn": float(false_negative),
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1_score,
        "apcer": apcer,
        "bpcer": bpcer,
        "acer": acer,
        "tnr": tnr,
    }


def build_thresholds(step: float) -> list[float]:
    thresholds = []
    current = 0.0
    while current < 1.0:
        thresholds.append(round(current, 4))
        current += step
    thresholds.append(1.0)
    return sorted(set(thresholds))


def summarize_evaluation(
    scores: list[float],
    labels: list[int],
    average_loss: float,
    eval_threshold: float,
    threshold_step: float,
) -> dict[str, Any]:
    thresholds = build_thresholds(threshold_step)
    sweep_rows = [threshold_metrics(scores, labels, threshold) for threshold in thresholds]
    default_row = threshold_metrics(scores, labels, eval_threshold)
    best_row = min(
        sweep_rows,
        key=lambda row: (row["acer"], row["apcer"], row["bpcer"], -row["accuracy"]),
    )

    return {
        "loss": average_loss,
        "accuracy": default_row["accuracy"],
        "precision": default_row["precision"],
        "recall": default_row["recall"],
        "f1": default_row["f1"],
        "apcer": default_row["apcer"],
        "bpcer": default_row["bpcer"],
        "acer": default_row["acer"],
        "tnr": default_row["tnr"],
        "roc_auc": binary_roc_auc(scores, labels),
        "pr_auc": binary_pr_auc(scores, labels),
        "live_count": int(sum(labels)),
        "spoof_count": int(len(labels) - sum(labels)),
        "threshold": eval_threshold,
        "recommended_threshold": best_row["threshold"],
        "recommended_accuracy": best_row["accuracy"],
        "recommended_precision": best_row["precision"],
        "recommended_recall": best_row["recall"],
        "recommended_f1": best_row["f1"],
        "recommended_apcer": best_row["apcer"],
        "recommended_bpcer": best_row["bpcer"],
        "recommended_acer": best_row["acer"],
        "recommended_tnr": best_row["tnr"],
        "tp": int(default_row["tp"]),
        "tn": int(default_row["tn"]),
        "fp": int(default_row["fp"]),
        "fn": int(default_row["fn"]),
        "sweep_rows": sweep_rows,
        "best_row": best_row,
    }


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
def evaluate(model, loader, criterion, device, eval_threshold: float, threshold_step: float, live_index: int):
    model.eval()
    total_loss = 0.0
    score_buffer: list[float] = []
    label_buffer: list[int] = []

    for images, labels in tqdm(loader, desc="val", leave=False):
        images = images.to(device)
        labels = labels.to(device)
        logits = model(images)
        loss = criterion(logits, labels)

        total_loss += float(loss.item())
        probabilities = torch.softmax(logits, dim=1)[:, live_index]
        score_buffer.extend(float(score) for score in probabilities.detach().cpu())
        label_buffer.extend(int(label == live_index) for label in labels.detach().cpu().tolist())

    count = max(1, len(loader))
    return summarize_evaluation(
        scores=score_buffer,
        labels=label_buffer,
        average_loss=total_loss / count,
        eval_threshold=eval_threshold,
        threshold_step=threshold_step,
    )


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


def write_live_metrics(output_dir: Path, metrics: dict, append_header: bool) -> None:
    """Persist per-epoch metrics immediately so they can be tailed live."""
    latest_path = output_dir / "training_metrics.latest.json"
    jsonl_path = output_dir / "training_metrics.jsonl"
    csv_path = output_dir / "training_metrics.csv"

    latest_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(metrics) + "\n")

    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics.keys()))
        if append_header:
            writer.writeheader()
        writer.writerow(metrics)


def write_threshold_reports(output_dir: Path, epoch: int, sweep_rows: list[dict[str, float]], best_row: dict[str, float]) -> None:
    sweep_path = output_dir / "threshold_sweep.latest.csv"
    best_latest_path = output_dir / "threshold_selection.latest.json"
    best_history_path = output_dir / "threshold_selection.jsonl"

    if sweep_rows:
        fieldnames = ["epoch"] + list(sweep_rows[0].keys())
        with sweep_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in sweep_rows:
                writer.writerow({"epoch": epoch, **row})

    best_payload = {"epoch": epoch, **best_row}
    best_latest_path.write_text(json.dumps(best_payload, indent=2), encoding="utf-8")
    with best_history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(best_payload) + "\n")


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
    parser.add_argument(
        "--eval-threshold",
        type=float,
        default=0.5,
        help="Validation threshold for classifying a sample as live (default: 0.5)",
    )
    parser.add_argument(
        "--threshold-step",
        type=float,
        default=0.05,
        help="Step size for threshold sweep report between 0.0 and 1.0 (default: 0.05)",
    )
    parser.add_argument(
        "--disable-live-metrics",
        action="store_true",
        help="Do not write per-epoch live metric files during training",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    args.data_dir = _resolve_project_path(args.data_dir)
    args.output_dir = _resolve_project_path(args.output_dir)

    if not 0.0 <= args.eval_threshold <= 1.0:
        raise ValueError("--eval-threshold must be between 0.0 and 1.0")
    if not 0.0 < args.threshold_step <= 1.0:
        raise ValueError("--threshold-step must be > 0.0 and <= 1.0")

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
    live_index = classes.index("live")

    print(f"Using device      : {device}")
    print(f"Train samples     : {len(train_ds)}")
    print(f"Validation samples: {len(val_ds)}")
    print(f"Classes           : {classes}")

    best_val_acc = -1.0
    best_path = args.output_dir / "best_cnn_antispoof.pt"
    history = []
    latest_path = args.output_dir / "training_metrics.latest.json"
    jsonl_path = args.output_dir / "training_metrics.jsonl"
    csv_path = args.output_dir / "training_metrics.csv"
    sweep_path = args.output_dir / "threshold_sweep.latest.csv"
    threshold_latest_path = args.output_dir / "threshold_selection.latest.json"
    threshold_history_path = args.output_dir / "threshold_selection.jsonl"

    if not args.disable_live_metrics:
        for stale_path in (
            latest_path,
            jsonl_path,
            csv_path,
            sweep_path,
            threshold_latest_path,
            threshold_history_path,
        ):
            if stale_path.exists():
                stale_path.unlink()

    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_eval = evaluate(
            model,
            val_loader,
            criterion,
            device,
            eval_threshold=args.eval_threshold,
            threshold_step=args.threshold_step,
            live_index=live_index,
        )

        metrics = {
            "epoch": epoch,
            "train_loss": round(train_loss, 4),
            "train_acc": round(train_acc, 4),
            "val_loss": round(val_eval["loss"], 4),
            "val_acc": round(val_eval["accuracy"], 4),
            "val_precision": round(val_eval["precision"], 4),
            "val_recall": round(val_eval["recall"], 4),
            "val_f1": round(val_eval["f1"], 4),
            "val_apcer": round(val_eval["apcer"], 4),
            "val_bpcer": round(val_eval["bpcer"], 4),
            "val_acer": round(val_eval["acer"], 4),
            "val_tnr": round(val_eval["tnr"], 4),
            "val_roc_auc": round_metric(val_eval["roc_auc"]),
            "val_pr_auc": round_metric(val_eval["pr_auc"]),
            "val_tp": val_eval["tp"],
            "val_tn": val_eval["tn"],
            "val_fp": val_eval["fp"],
            "val_fn": val_eval["fn"],
            "val_live_count": val_eval["live_count"],
            "val_spoof_count": val_eval["spoof_count"],
            "eval_threshold": round(val_eval["threshold"], 4),
            "recommended_threshold": round(val_eval["recommended_threshold"], 4),
            "recommended_acc": round(val_eval["recommended_accuracy"], 4),
            "recommended_f1": round(val_eval["recommended_f1"], 4),
            "recommended_apcer": round(val_eval["recommended_apcer"], 4),
            "recommended_bpcer": round(val_eval["recommended_bpcer"], 4),
            "recommended_acer": round(val_eval["recommended_acer"], 4),
        }
        history.append(metrics)
        print(json.dumps(metrics))

        if not args.disable_live_metrics:
            write_live_metrics(
                args.output_dir,
                metrics,
                append_header=(epoch == 1),
            )
            write_threshold_reports(
                args.output_dir,
                epoch,
                val_eval["sweep_rows"],
                val_eval["best_row"],
            )

        if val_eval["accuracy"] > best_val_acc:
            best_val_acc = val_eval["accuracy"]
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "classes": classes,
                    "image_size": args.image_size,
                    "val_acc": val_eval["accuracy"],
                    "eval_threshold": args.eval_threshold,
                    "recommended_threshold": val_eval["recommended_threshold"],
                    "recommended_metrics": {
                        "accuracy": val_eval["recommended_accuracy"],
                        "precision": val_eval["recommended_precision"],
                        "recall": val_eval["recommended_recall"],
                        "f1": val_eval["recommended_f1"],
                        "apcer": val_eval["recommended_apcer"],
                        "bpcer": val_eval["recommended_bpcer"],
                        "acer": val_eval["recommended_acer"],
                    },
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
