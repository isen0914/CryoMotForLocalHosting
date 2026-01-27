from fastapi import FastAPI, UploadFile, File, HTTPException
from starlette.responses import StreamingResponse, FileResponse
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from ultralytics import YOLO
import tempfile, zipfile, shutil, logging
import numpy as np
import math
from PIL import Image, ImageDraw
import gc
from pathlib import Path
import time
import uvicorn
from sklearn.cluster import DBSCAN
from collections import defaultdict
from skimage import io, transform, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YOLO FastAPI Detector")

# Root endpoint for Render health check
@app.get("/")
def read_root():
    return {"status": "ok"}
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
OUTPUT_DIR = Path("outputs"); OUTPUT_DIR.mkdir(exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# Mount frontend directory
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    logger.info(f"Frontend directory mounted at: {FRONTEND_DIR}")
else:
    logger.warning(f"Frontend directory not found at: {FRONTEND_DIR}")

# Prefer a quantized ONNX model if available, otherwise load the PyTorch .pt
from pathlib import Path
MODEL_PT = Path("best.pt")
QUANT_ONNX = Path("best.quant.onnx")

if QUANT_ONNX.exists():
    logger.info(f"Loading quantized ONNX model: {QUANT_ONNX}")
    model = YOLO(str(QUANT_ONNX))
elif MODEL_PT.exists():
    logger.info(f"Loading PyTorch model: {MODEL_PT}")
    model = YOLO(str(MODEL_PT))
else:
    logger.error("No model file found. Place `best.pt` or `best.quant.onnx` in the backend folder.")
    raise SystemExit("No model found")

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tif', '.tiff'}

# Clustering parameters
CONF_THRESHOLD = 0.25
DBSCAN_EPS = 50
DBSCAN_MIN_SAMPLES = 3
MIN_CLUSTER_SIZE = 3
MIN_DISTANCE = 100

def _evenly_spaced_indices(total: int, count: int) -> list[int]:
    if total <= 0:
        return []
    if total <= count:
        return list(range(total))
    step = total / count
    return [int(i * step) for i in range(count)]

def save_volume_previews(volume: np.ndarray, base: str, prefix: str, count: int = 4) -> list[str]:
    """Save a few representative slices from a (N,H,W) float volume as PNGs in OUTPUT_DIR."""
    if volume is None or not hasattr(volume, 'shape') or len(volume.shape) != 3:
        return []
    n_slices = int(volume.shape[0])
    idxs = _evenly_spaced_indices(n_slices, count)
    urls: list[str] = []

    for i, z in enumerate(idxs):
        try:
            slice_2d = volume[z]
            # normalize to 0..255 for visualization
            vmin = float(np.min(slice_2d))
            vmax = float(np.max(slice_2d))
            if vmax > vmin:
                norm = (slice_2d - vmin) / (vmax - vmin)
            else:
                norm = np.zeros_like(slice_2d, dtype=np.float32)
            img_u8 = np.clip(norm * 255.0, 0, 255).astype(np.uint8)
            out_name = f"{base}_{prefix}_preview_{i:02d}_z{z:04d}.png"
            out_path = OUTPUT_DIR / out_name
            Image.fromarray(img_u8, mode='L').save(out_path)
            urls.append(f"/outputs/{out_name}")
        except Exception as e:
            logger.exception(f"Failed saving volume preview slice z={z}: {e}")
            continue
    return urls

def organize_detections(results, image_paths):
    """Organize detections by tomogram ID"""
    detections_by_tomo = defaultdict(list)
    
    for r, img_path in zip(results, image_paths):
        filename = img_path.stem
        parts = filename.split('_')
        
        if len(parts) >= 3:
            tomo_id = f"{parts[0]}_{parts[1]}"
            try:
                slice_num = int(parts[2])
            except ValueError:
                slice_num = 0
            
            if hasattr(r, 'boxes') and len(r.boxes) > 0:
                for box in r.boxes:
                    xywh = box.xywh[0].cpu().numpy() if hasattr(box.xywh[0], 'cpu') else box.xywh[0]
                    det = {
                        'x': float(xywh[0]),
                        'y': float(xywh[1]),
                        'z': slice_num,
                        'conf': float(box.conf[0]),
                    }
                    detections_by_tomo[tomo_id].append(det)
    
    return detections_by_tomo

def filter_duplicates(motors, min_distance=MIN_DISTANCE):
    """Filter duplicate motors based on minimum distance"""
    filtered = []
    for motor in motors:
        is_duplicate = False
        for existing in filtered:
            dist = np.sqrt(
                (motor['x_pixel'] - existing['x_pixel'])**2 +
                (motor['y_pixel'] - existing['y_pixel'])**2 +
                (motor['z'] - existing['z'])**2
            )
            if dist < min_distance:
                is_duplicate = True
                break
        if not is_duplicate:
            filtered.append(motor)
    return filtered

def load_and_preprocess_images(image_paths, target_size=(250, 250)):
    """
    Load images, resize to target size, and stack into volume (from r.ipynb)
    Args:
        image_paths: list of image file paths
        target_size: tuple (height, width) for resizing
    Returns:
        volume array of shape (N, H, W)
    """
    logger.info(f"Loading and resizing {len(image_paths)} images to {target_size}")
    volume = []
    
    for img_path in image_paths:
        # Read image using skimage
        img = io.imread(str(img_path))
        
        # Convert to grayscale if needed
        if img.ndim == 3:
            img = img[..., 0]
        
        # Resize image (same as r.ipynb)
        img_resized = transform.resize(img, target_size, anti_aliasing=True, preserve_range=True)
        volume.append(img_resized)
    
    # Stack into 3D array: shape (N, H, W)
    volume = np.stack(volume, axis=0)
    logger.info(f'Volume shape after loading: {volume.shape}')
    
    return volume

def process_volume_with_masking(volume, threshold_method='otsu', manual_threshold=0.1):
    """
    Process volume with background removal and masking (EXACTLY from r.ipynb)
    Args:
        volume: numpy array of shape (N, H, W) with image slices
        threshold_method: 'otsu' or 'manual'
        manual_threshold: threshold value if method is 'manual'
    Returns:
        processed volume with masking applied
    """
    logger.info(f"Processing volume with masking (method: {threshold_method})")
    
    # Convert to float
    vol = volume.astype(np.float32)
    
    # Normalize 0-1
    vol = (vol - vol.min()) / (vol.max() - vol.min())
    
    # Determine threshold
    if threshold_method == 'otsu':
        base_thresh = filters.threshold_otsu(vol)
        thresh = base_thresh * 0.78  # same as r.ipynb
    else:
        thresh = manual_threshold
    
    # Apply mask (remove background)
    mask = vol <= thresh
    vol_masked = vol * mask
    
    logger.info(f'Applied masking with threshold: {thresh}')
    
    return vol_masked

def cluster_3d(detections_by_tomo):
    """Apply DBSCAN clustering to group 3D detections"""
    predictions_3d = {}
    
    for tomo_id, detections in detections_by_tomo.items():
        if len(detections) < DBSCAN_MIN_SAMPLES:
            predictions_3d[tomo_id] = [{
                'x_pixel': d['x'], 'y_pixel': d['y'], 'z': d['z'],
                'conf': d['conf'], 'cluster_size': 1
            } for d in detections]
            continue
        
        points = np.array([[d['x'], d['y'], d['z']] for d in detections])
        clustering = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES)
        labels = clustering.fit_predict(points)
        
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        
        motors = []
        for cid in range(n_clusters):
            mask = (labels == cid)
            cluster_dets = [d for d, m in zip(detections, mask) if m]
            
            if len(cluster_dets) < MIN_CLUSTER_SIZE:
                continue
            
            motors.append({
                'x_pixel': float(np.mean([d['x'] for d in cluster_dets])),
                'y_pixel': float(np.mean([d['y'] for d in cluster_dets])),
                'z': float(np.mean([d['z'] for d in cluster_dets])),
                'conf': float(np.mean([d['conf'] for d in cluster_dets])),
                'cluster_size': len(cluster_dets)
            })
        
        predictions_3d[tomo_id] = filter_duplicates(motors)
    
    return predictions_3d

@app.post("/detect/")
async def detect(zip_file: UploadFile = File(...)):
    if not zip_file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file")

    def gen():
        try:
            yield (json.dumps({"stage": "received"}) + "\n").encode('utf-8')
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                zip_path = tmpdir_path / "upload.zip"
                with open(zip_path, "wb") as f:
                    shutil.copyfileobj(zip_file.file, f)
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(tmpdir_path / "images")
                images_dir = tmpdir_path / "images"
                results = []
                proc_start = time.perf_counter()

                # find image files recursively
                if not images_dir.exists():
                    logger.info("No images directory created from zip")
                    yield (json.dumps({"results": []}) + "\n").encode('utf-8')
                    return

                image_paths = sorted([p for p in images_dir.rglob('*') if p.is_file() and p.suffix.lower() in IMAGE_EXTS])
                if not image_paths:
                    logger.info("No images found in uploaded zip")
                    yield (json.dumps({"results": []}) + "\n").encode('utf-8')
                    return

                depth = max(1, len(image_paths))
                
                # ===== STEP 1: PREPROCESS IMAGES (from r.ipynb) =====
                logger.info("[PREPROCESSING] Loading and resizing images to 250x250...")
                yield (json.dumps({"stage": "preprocessing", "message": "Loading images..."}) + "\n").encode('utf-8')
                
                # Load and resize images (exactly as r.ipynb)
                raw_volume = load_and_preprocess_images(image_paths, target_size=(250, 250))
                
                # Apply masking (exactly as r.ipynb)
                logger.info("[PREPROCESSING] Applying Otsu masking...")
                yield (json.dumps({"stage": "preprocessing", "message": "Applying masking..."}) + "\n").encode('utf-8')
                processed_volume = process_volume_with_masking(raw_volume, threshold_method='otsu')
                
                # Save processed volume (the clean volume for download)
                base = Path(zip_file.filename).stem
                processed_vol_name = f"{base}_processed_volume.npy"
                processed_vol_path = OUTPUT_DIR / processed_vol_name
                np.save(str(processed_vol_path), processed_volume)
                logger.info(f"[PREPROCESSING] Saved processed volume: {processed_vol_name} with shape {processed_volume.shape}")

                # Save preview PNGs for the preprocessing panel.
                # Generate one preview per slice so the UI "View All" can show the full stack.
                preprocessing_previews = save_volume_previews(
                    processed_volume,
                    base=base,
                    prefix='preprocessed',
                    count=int(getattr(processed_volume, 'shape', [0])[0] or 0),
                )
                
                yield (json.dumps({
                    "stage": "preprocessing_complete",
                    "processed_volume_url": f"/outputs/{processed_vol_name}",
                    "preprocessing_previews": preprocessing_previews,
                    "message": "Preprocessing complete. Starting detection..."
                }) + "\n").encode('utf-8')
                
                # ===== STEP 2: RUN YOLO DETECTION ON ORIGINAL IMAGES =====
                logger.info("[DETECTION] Starting YOLO inference...")
                
                # Store all YOLO results for clustering
                all_yolo_results = []

                with Image.open(image_paths[0]) as _fi:
                    target_w, target_h = _fi.size

                # Map (tomo_id, slice_num) -> volume index so we can later keep only representative slices.
                index_by_tomo_slice = {}
                for vol_idx, img_path in enumerate(image_paths):
                    try:
                        parts = img_path.stem.split('_')
                        if len(parts) >= 3:
                            tomo_id = f"{parts[0]}_{parts[1]}"
                            slice_num = int(parts[2])
                            index_by_tomo_slice[(tomo_id, slice_num)] = vol_idx
                    except Exception:
                        continue

                volume = np.zeros((depth, target_h, target_w, 4), dtype=np.uint8)
                
                # Prepare 3D volume for transparent PNGs (250x250) - RGBA format
                transparent_volume = np.zeros((depth, 250, 250, 4), dtype=np.uint8)

                for idx, img in enumerate(image_paths):
                    current_annotated_url = None
                    current_transparent_url = None
                    current_slice_url = None
                    try:
                        logger.info(f"Processing image: {img}")
                        with Image.open(img) as pil_src:
                            pil_rgb = pil_src.convert('RGB')
                            img_arr = np.array(pil_rgb)
                            orig = pil_src.convert('RGBA')

                        r = model(img_arr)[0]
                        all_yolo_results.append(r)  # Store for clustering
                        boxes = r.boxes.xyxy.tolist() if getattr(r, 'boxes', None) is not None else []
                        out_name = f"{img.stem}_annotated{img.suffix}"
                        out_path = OUTPUT_DIR / out_name
                        plotted = r.plot()
                        try:
                            if hasattr(plotted, 'save'):
                                plotted.save(str(out_path))
                            else:
                                im = Image.fromarray(plotted)
                                try:
                                    im.save(str(out_path))
                                finally:
                                    im.close()
                        finally:
                            try:
                                if hasattr(plotted, 'close'):
                                    plotted.close()
                            except Exception:
                                pass

                        results.append({
                            "image": str(img.relative_to(images_dir)),
                            "boxes": boxes,
                            "annotated_url": f"/outputs/{out_name}"
                        })

                        # Best-effort: include URLs for stage-specific UI panels
                        current_annotated_url = f"/outputs/{out_name}"

                        # Create transparent PNG with only bounding boxes visible (no shading/fill)
                        try:
                            with Image.open(img) as orig_img:
                                # Draw directly in 250x250 so there is no downsampling blur that can
                                # make boxes look "filled" when volume-rendered.
                                ow, oh = orig_img.size
                                target_size = (250, 250)
                                sx = (target_size[0] / float(ow)) if ow else 1.0
                                sy = (target_size[1] / float(oh)) if oh else 1.0

                                transparent_resized = Image.new('RGBA', target_size, (0, 0, 0, 0))
                                draw = ImageDraw.Draw(transparent_resized)
                                for box in boxes:
                                    x1, y1, x2, y2 = [float(v) for v in box]
                                    tx1 = int(round(x1 * sx))
                                    ty1 = int(round(y1 * sy))
                                    tx2 = int(round(x2 * sx))
                                    ty2 = int(round(y2 * sy))

                                    # Clamp to the image bounds
                                    tx1 = max(0, min(target_size[0] - 1, tx1))
                                    tx2 = max(0, min(target_size[0] - 1, tx2))
                                    ty1 = max(0, min(target_size[1] - 1, ty1))
                                    ty2 = max(0, min(target_size[1] - 1, ty2))

                                    draw.rectangle(
                                        [tx1, ty1, tx2, ty2],
                                        outline=(255, 227, 179, 255),
                                        width=1,
                                    )
                                
                                # Save transparent PNG
                                transparent_name = f"{img.stem}_transparent.png"
                                transparent_path = OUTPUT_DIR / transparent_name
                                transparent_resized.save(transparent_path, 'PNG')
                                
                                # Add to transparent volume - keep RGBA format
                                transparent_arr = np.array(transparent_resized)
                                if transparent_arr.ndim == 3 and transparent_arr.shape[2] == 4:
                                    # Store RGBA data directly without grayscale conversion
                                    transparent_volume[idx] = transparent_arr
                                elif transparent_arr.ndim == 2:
                                    # Handle grayscale input by converting to RGBA
                                    rgba = np.zeros((250, 250, 4), dtype=np.uint8)
                                    rgba[:, :, 0] = transparent_arr
                                    rgba[:, :, 1] = transparent_arr
                                    rgba[:, :, 2] = transparent_arr
                                    rgba[:, :, 3] = 255
                                    transparent_volume[idx] = rgba
                                
                                # Add to results
                                results[-1]["transparent_url"] = f"/outputs/{transparent_name}"

                                current_transparent_url = f"/outputs/{transparent_name}"
                                
                                transparent_resized.close()
                        except Exception as e:
                            logger.exception(f"Failed to create transparent PNG for {img}: {e}")
                            results[-1]["transparent_error"] = str(e)

                        # Create a per-slice preview image for the Post-processing panel.
                        # IMPORTANT: keep it opaque (original + overlays) so thumbnails are visible.
                        try:
                            with Image.open(img) as _orig_file:
                                orig = _orig_file.convert('RGBA')
                                iw, ih = orig.size

                            if (iw, ih) != (target_w, target_h):
                                scale_x = target_w / iw
                                scale_y = target_h / ih
                                base_img = orig.resize((target_w, target_h), Image.LANCZOS)
                                scaled_boxes = []
                                for box in boxes:
                                    try:
                                        x1, y1, x2, y2 = [float(v) for v in box]
                                        sx1 = int(round(x1 * scale_x))
                                        sy1 = int(round(y1 * scale_y))
                                        sx2 = int(round(x2 * scale_x))
                                        sy2 = int(round(y2 * scale_y))
                                        scaled_boxes.append((sx1, sy1, sx2, sy2))
                                    except Exception:
                                        continue
                            else:
                                base_img = orig.copy()
                                scaled_boxes = []
                                for box in boxes:
                                    try:
                                        x1, y1, x2, y2 = [int(round(float(v))) for v in box]
                                        scaled_boxes.append((x1, y1, x2, y2))
                                    except Exception:
                                        continue

                            draw_slice = ImageDraw.Draw(base_img)

                            # Draw boxes only (no center markers)
                            for (x1, y1, x2, y2) in scaled_boxes:
                                draw_slice.rectangle([x1, y1, x2, y2], outline=(255, 227, 179, 255), width=2)

                            slice_name = f"{img.stem}_slice_{idx:03d}.png"
                            slice_path = OUTPUT_DIR / slice_name
                            base_img.save(slice_path)

                            arr = np.array(base_img)
                            if arr.ndim != 3 or arr.shape[2] != 4:
                                arr = np.dstack([arr, np.full((target_h, target_w), 255, dtype=np.uint8)])
                            volume[idx] = arr

                            try:
                                base_img.close()
                            except Exception:
                                pass
                            try:
                                orig.close()
                            except Exception:
                                pass
                            try:
                                del img_arr
                            except Exception:
                                pass
                            gc.collect()

                            results[-1]["slice_url"] = f"/outputs/{slice_name}"
                            current_slice_url = f"/outputs/{slice_name}"
                        except Exception as e:
                            logger.exception(f"Failed to create slice for {img}: {e}")
                            results[-1]["slice_error"] = str(e)

                    except Exception as e:
                        logger.exception(f"Failed to process {img}: {e}")
                        results.append({"image": img.name, "error": str(e)})

                    # yield progress after each image
                    try:
                        progress = int(((idx + 1) / len(image_paths)) * 100)
                    except Exception:
                        progress = 0
                    yield (json.dumps({
                        "stage": "inference",
                        "progress": progress,
                        "image": str(img.name),
                        "annotated_url": current_annotated_url,
                        "transparent_url": current_transparent_url,
                        "slice_url": current_slice_url,
                    }) + "\n").encode('utf-8')

                # Perform 3D clustering
                logger.info("[CLUSTERING] Organizing detections...")
                detections_by_tomo = organize_detections(all_yolo_results, image_paths)
                logger.info(f"[CLUSTERING] Found {len(detections_by_tomo)} tomograms")
                
                logger.info("[CLUSTERING] Running DBSCAN clustering...")
                motors_3d = cluster_3d(detections_by_tomo)
                total_motors = sum(len(m) for m in motors_3d.values())
                logger.info(f"[CLUSTERING] Detected {total_motors} flagellar motors")

                # Keep only one representative slice per clustered motor in the 3D transparent volume.
                # This avoids showing the object across all slices where it was detected.
                try:
                    keep_indices = set()
                    slice_map_by_tomo = defaultdict(dict)
                    for (tomo_id, slice_num), vol_idx in index_by_tomo_slice.items():
                        slice_map_by_tomo[tomo_id][slice_num] = vol_idx

                    for tomo_id, motors in motors_3d.items():
                        slice_to_idx = slice_map_by_tomo.get(tomo_id, {})
                        for motor in motors:
                            try:
                                rep_slice = int(math.floor(float(motor.get('z', 0))))
                            except Exception:
                                rep_slice = 0

                            vol_idx = slice_to_idx.get(rep_slice)
                            if vol_idx is None and slice_to_idx:
                                # Fallback: pick closest available slice number for this tomo.
                                closest_slice = min(slice_to_idx.keys(), key=lambda s: abs(int(s) - rep_slice))
                                vol_idx = slice_to_idx.get(closest_slice)

                            if vol_idx is None:
                                # Last-resort fallback: assume z aligns with volume index.
                                vol_idx = max(0, min(depth - 1, rep_slice))

                            keep_indices.add(int(vol_idx))

                    if keep_indices:
                        filtered_tv = np.zeros_like(transparent_volume)
                        for i in keep_indices:
                            if 0 <= i < depth:
                                filtered_tv[i] = transparent_volume[i]
                        transparent_volume = filtered_tv
                        logger.info(
                            f"[POSTPROCESSING] Transparent volume filtered to representative slices: "
                            f"kept {len(keep_indices)} slice(s) out of {depth}"
                        )
                except Exception as e:
                    logger.exception(f"Failed filtering transparent volume to representative slices: {e}")

                # Emit a post-processing summary for the UI panel
                try:
                    yield (json.dumps({
                        "stage": "postprocessing_complete",
                        "total_motors": total_motors,
                        "motors_by_tomo": {k: len(v) for k, v in motors_3d.items()},
                    }) + "\n").encode('utf-8')
                except Exception:
                    pass
                
                try:
                    base = Path(zip_file.filename).stem
                    vol_name = f"{base}_volume.npy"
                    vol_path = OUTPUT_DIR / vol_name
                    np.save(str(vol_path), volume)
                    
                    # Save transparent 3D volume (RGBA - shows motor locations)
                    transparent_vol_name = f"{base}_transparent_volume.npy"
                    transparent_vol_path = OUTPUT_DIR / transparent_vol_name
                    np.save(str(transparent_vol_path), transparent_volume)
                    logger.info(f"Saved transparent 3D volume: {transparent_vol_name} with shape {transparent_volume.shape}")
                    
                    # Processed volume was already saved during preprocessing step
                    # Just verify it exists
                    processed_vol_name = f"{base}_processed_volume.npy"
                    processed_vol_path = OUTPUT_DIR / processed_vol_name
                    
                    # Verify file exists
                    if not transparent_vol_path.exists():
                        logger.error(f"Transparent volume file not found after save: {transparent_vol_path}")
                    else:
                        logger.info(f"Transparent volume file verified at: {transparent_vol_path}")
                    
                    if not processed_vol_path.exists():
                        logger.error(f"Processed volume file not found after save: {processed_vol_path}")
                    else:
                        logger.info(f"Processed volume file verified at: {processed_vol_path}")
                    
                    elapsed_ms = int((time.perf_counter() - proc_start) * 1000)
                    
                    # Get final 3D coordinates for each motor
                    motors_coordinates = {}
                    for tomo_id, motors in motors_3d.items():
                        motors_coordinates[tomo_id] = []
                        for motor in motors:
                            motors_coordinates[tomo_id].append({
                                'x': math.floor(motor['x_pixel']),
                                'y': math.floor(motor['y_pixel']),
                                'z': math.floor(motor['z']),
                                'confidence': round(motor['conf'], 2),
                                'representative_slice': f"{tomo_id}_{math.floor(motor['z']):04d}"
                            })
                    
                    final = {
                        "results": results, 
                        "volume_url": f"/outputs/{vol_name}",
                        "transparent_volume_url": f"/outputs/{transparent_vol_name}",
                        "processed_volume_url": f"/outputs/{processed_vol_name}",
                        "elapsed_ms": elapsed_ms,
                        "total_motors": total_motors,
                        "motors_by_tomo": {k: len(v) for k, v in motors_3d.items()},
                        "motors_coordinates": motors_coordinates
                    }
                    yield (json.dumps(final) + "\n").encode('utf-8')
                except Exception as e:
                    logger.exception(f"Failed to save combined volume: {e}")
                    elapsed_ms = int((time.perf_counter() - proc_start) * 1000)
                    
                    # Get final 3D coordinates for each motor
                    motors_coordinates = {}
                    for tomo_id, motors in motors_3d.items():
                        motors_coordinates[tomo_id] = []
                        for motor in motors:
                            motors_coordinates[tomo_id].append({
                                'x': math.floor(motor['x_pixel']),
                                'y': math.floor(motor['y_pixel']),
                                'z': math.floor(motor['z']),
                                'confidence': round(motor['conf'], 2),
                                'representative_slice': f"{tomo_id}_{math.floor(motor['z']):04d}"
                            })
                    
                    final = {
                        "results": results, 
                        "volume_error": str(e), 
                        "elapsed_ms": elapsed_ms,
                        "total_motors": total_motors,
                        "motors_by_tomo": {k: len(v) for k, v in motors_3d.items()},
                        "motors_coordinates": motors_coordinates
                    }
                    yield (json.dumps(final) + "\n").encode('utf-8')
        except Exception as e:
            logger.exception(f"Unhandled error in streaming detect: {e}")
            try:
                yield (json.dumps({"error": str(e)}) + "\n").encode('utf-8')
            except Exception:
                pass

    return StreamingResponse(gen(), media_type='application/x-ndjson')

@app.get("/download_volume/{filename}")
async def download_volume(filename: str):
    """Download a processed .npy volume file"""
    file_path = OUTPUT_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Volume file not found")
    
    if not file_path.suffix == '.npy':
        raise HTTPException(status_code=400, detail="Only .npy files can be downloaded")
    
    logger.info(f"Serving volume file: {filename}")
    
    return FileResponse(
        path=str(file_path),
        media_type='application/octet-stream',
        filename=filename
    )

# ============ LOCAL STORAGE API ENDPOINTS ============
HISTORY_FILE = Path(__file__).parent.parent / "history_data.json"

def load_history_data():
    """Load history data from JSON file"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return []

def save_history_data(data):
    """Save history data to JSON file"""
    with open(HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.post("/api/history")
async def add_history(data: dict):
    """Add a new history record"""
    try:
        records = load_history_data()
        
        # Create new record with auto-increment ID
        new_id = max([r.get('id', 0) for r in records], default=0) + 1
        new_record = {
            'id': new_id,
            'timestamp': data.get('timestamp'),
            'total_motors': data.get('total_motors'),
            'avg_distance': data.get('avg_distance'),
            'avg_fbeta': data.get('avg_fbeta'),
            'avg_proc_time': data.get('avg_proc_time'),
            'high_conf': data.get('high_conf', '0'),
            'med_conf': data.get('med_conf', '0'),
            'low_conf': data.get('low_conf', '0'),
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        records.append(new_record)
        save_history_data(records)
        
        logger.info(f"Added history record: {new_record}")
        return {"success": True, "data": new_record}
    except Exception as e:
        logger.error(f"Error adding history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history():
    """Get all history records"""
    try:
        records = load_history_data()
        # Sort by created_at descending
        records.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return {"data": records}
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/history/{record_id}")
async def delete_history(record_id: int):
    """Delete a history record"""
    try:
        records = load_history_data()
        records = [r for r in records if r.get('id') != record_id]
        save_history_data(records)
        
        logger.info(f"Deleted history record: {record_id}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Error deleting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import os
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
