"""Export `best.pt` to ONNX and apply dynamic quantization using ONNX Runtime.

Run:
    python quantize_model.py

Produces `best.onnx` and `best.quant.onnx` in the `backend/` folder.
"""
import logging
from pathlib import Path
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("quantize")

MODEL_PT = Path("best.pt")
ONNX_OUT = Path("best.onnx")
QUANT_OUT = Path("best.quant.onnx")


def export_to_onnx():
    if not MODEL_PT.exists():
        logger.error(f"{MODEL_PT} not found in {Path.cwd()}")
        return False
    y = YOLO(str(MODEL_PT))
    logger.info("Exporting to ONNX (this may take a moment)...")
    # ultralytics' export returns path or list — rely on it to produce an .onnx file
    res = y.export(format="onnx")
    exported = None
    if isinstance(res, (list, tuple)):
        exported = Path(res[0]) if res else None
    else:
        exported = Path(res) if res else None

    if exported and exported.exists():
        logger.info(f"Exported ONNX: {exported}")
        if exported != ONNX_OUT:
            try:
                exported.rename(ONNX_OUT)
                logger.info(f"Renamed exported file to {ONNX_OUT}")
            except Exception:
                logger.warning("Could not rename exported ONNX file; leaving as-is")
        return True
    else:
        logger.error("ONNX export failed")
        return False


def quantize_onnx():
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType
    except Exception as e:
        logger.error("onnxruntime.quantization not available — ensure onnxruntime is installed")
        raise

    if not ONNX_OUT.exists():
        logger.error(f"ONNX model {ONNX_OUT} not found")
        return False

    logger.info("Running dynamic quantization (weights -> int8)...")
    logger.info("Quantizing ONLY MatMul / Gemm (linear layers), skipping Conv")
    # Quantize ONLY MatMul / Gemm (linear layers), skip Conv
    quantize_dynamic(
        model_input=str(ONNX_OUT),
        model_output=str(QUANT_OUT),
        weight_type=QuantType.QInt8,
        op_types_to_quantize=["MatMul", "Gemm"],  # Only quantize linear layers
    )
    logger.info(f"Quantized model written to {QUANT_OUT}")
    return True


def main():
    ok = export_to_onnx()
    if not ok:
        return
    quantize_onnx()


if __name__ == "__main__":
    main()
