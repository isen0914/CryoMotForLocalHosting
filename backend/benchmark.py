"""Quick benchmark: compare inference time of PyTorch `best.pt` vs ONNX `best.quant.onnx`.

Usage: run from `backend/` with the project's virtualenv python.
"""
import time
from pathlib import Path
from ultralytics import YOLO


DEF_RUNS = 5
WARMUP = 2


def load_images(sample_dir: Path, max_images=5):
    imgs = [p for p in sample_dir.glob('*') if p.suffix.lower() in {'.jpg', '.jpeg', '.png'}]
    imgs = sorted(imgs)[:max_images]
    return imgs


def bench_model(model_path: Path, images, runs=DEF_RUNS, warmup=WARMUP):
    print(f"Loading model: {model_path}")
    model = YOLO(str(model_path))

    # Warmup
    for i in range(warmup):
        for img in images:
            _ = model(str(img))

    times = []
    for r in range(runs):
        t0 = time.perf_counter()
        for img in images:
            _ = model(str(img))
        t1 = time.perf_counter()
        times.append(t1 - t0)
        print(f" Run {r+1}/{runs}: {t1-t0:.3f}s for {len(images)} image(s)")

    total = sum(times)
    avg = total / (runs * len(images))
    print(f"Model {model_path.name}: total={total:.3f}s avg_per_image={avg:.4f}s\n")
    return total, avg


def main():
    backend = Path(__file__).parent
    sample_dir = backend.parent / 'tools' / 'sample_images'
    if not sample_dir.exists():
        print(f"Sample images directory not found: {sample_dir}")
        return

    images = load_images(sample_dir, max_images=3)
    if not images:
        print(f"No sample images found in {sample_dir}")
        return

    pt = backend / 'best.pt'
    onnxq = backend / 'best.quant.onnx'

    results = {}
    if pt.exists():
        results['pt'] = bench_model(pt, images)
    else:
        print('PyTorch model `best.pt` not found; skipping PT benchmark')

    if onnxq.exists():
        results['onnxq'] = bench_model(onnxq, images)
    else:
        print('Quantized ONNX `best.quant.onnx` not found; skipping ONNX benchmark')

    print('SUMMARY:')
    for k, v in results.items():
        print(f" {k}: total={v[0]:.3f}s avg_per_image={v[1]:.4f}s")


if __name__ == '__main__':
    main()
