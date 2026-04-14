from __future__ import annotations

import argparse
import random
import statistics
from pathlib import Path
from typing import Sequence

from common import (
    DEFAULT_BASE_URL,
    DEFAULT_SERVICE_KEY,
    extract_prediction,
    list_image_files,
    resolve_image_dir,
)


def add_shared_args(
    parser: argparse.ArgumentParser,
    *,
    default_split: str,
    default_sample_size: int,
    default_min_blur: float | None,
) -> None:
    parser.add_argument("--split", default=default_split, help="Dataset split cần kiểm tra: train / val / test")
    parser.add_argument("--sample-size", type=int, default=default_sample_size, help="Số ảnh mỗi lớp cần lấy mẫu")
    parser.add_argument("--dataset-root", type=Path, default=None, help="Thư mục gốc dataset antispoof")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL của ai-service")
    parser.add_argument("--service-key", default=DEFAULT_SERVICE_KEY, help="X-Service-Key nội bộ")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout request (giây)")
    parser.add_argument("--min-blur", type=float, default=default_min_blur, help="Override min_blur gửi lên API")
    parser.add_argument("--seed", type=int, default=42, help="Seed cho random sampling / shuffle")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bộ công cụ kiểm tra anti-spoof / liveness qua ai-service"
    )
    subparsers = parser.add_subparsers(dest="command")

    samples_parser = subparsers.add_parser(
        "samples",
        help="Kiểm tra nhanh một số ảnh live/spoof và in ra score",
    )
    add_shared_args(samples_parser, default_split="val", default_sample_size=5, default_min_blur=None)
    samples_parser.add_argument("--shuffle", action="store_true", help="Lấy mẫu ngẫu nhiên thay vì lấy từ đầu danh sách")

    threshold_parser = subparsers.add_parser(
        "threshold",
        help="Thống kê phân phối liveness_score để hỗ trợ chọn threshold",
    )
    add_shared_args(threshold_parser, default_split="train", default_sample_size=30, default_min_blur=20.0)
    threshold_parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=[0.20, 0.30, 0.40, 0.50],
        help="Danh sách ngưỡng cần thống kê",
    )

    return parser


def run_samples(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)

    for class_name in ("live", "spoof"):
        folder = resolve_image_dir(args.split, class_name, args.dataset_root)
        files = list_image_files(folder)
        if args.shuffle:
            rng.shuffle(files)
        sample = files[: args.sample_size]

        print(f"\n## {class_name.upper()} ({len(sample)} samples) — {folder}")
        if not sample:
            print("Không tìm thấy ảnh nào.")
            continue

        for image_path in sample:
            status, data = extract_prediction(
                image_path,
                base_url=args.base_url,
                service_key=args.service_key,
                min_blur=args.min_blur,
                timeout=args.timeout,
            )
            if status == 200:
                meta = data.get("meta", {})
                print(
                    f"{image_path.name} | score={meta.get('liveness_score')} | "
                    f"live={meta.get('is_live')} | quality={data.get('quality')} | "
                    f"blur={meta.get('blur_variance')}"
                )
            else:
                print(f"{image_path.name} | status={status} | detail={data.get('detail', data)}")

    return 0


def run_threshold(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)

    for class_name in ("live", "spoof"):
        folder = resolve_image_dir(args.split, class_name, args.dataset_root)
        files = list_image_files(folder)
        sample = rng.sample(files, min(args.sample_size, len(files))) if files else []

        scores: list[float] = []
        errors = 0
        for image_path in sample:
            status, data = extract_prediction(
                image_path,
                base_url=args.base_url,
                service_key=args.service_key,
                min_blur=args.min_blur,
                timeout=args.timeout,
            )
            if status != 200:
                errors += 1
                continue

            meta = data.get("meta", {})
            score = meta.get("liveness_score")
            if score is not None:
                scores.append(float(score))

        print(f"{class_name}: ok={len(scores)} rejected={errors} — {folder}")
        if not scores:
            continue

        print(
            f"  min={min(scores):.4f} mean={statistics.mean(scores):.4f} "
            f"max={max(scores):.4f}"
        )
        for threshold in args.thresholds:
            passed = sum(score >= threshold for score in scores)
            print(f"  >={threshold:.2f}: {passed}/{len(scores)}")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "samples"):
        return run_samples(args)
    if args.command == "threshold":
        return run_threshold(args)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
