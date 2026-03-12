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
from scipy.sparse.csgraph import minimum_spanning_tree, connected_components
from scipy.spatial.distance import pdist, squareform
from scipy.sparse import csr_matrix
from collections import defaultdict
from skimage import io, transform, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(title="YOLO FastAPI Detector")
# Add CORS middleware immediately after app creation
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001"],  # Only allow frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint for Render health check
@app.get("/")
def read_root():
    return {"status": "ok"}

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

# MST Clustering parameters
CONF_THRESHOLD = 0.285
MST_EDGE_THRESHOLD = 76.0
MST_MIN_CLUSTER_SIZE = 2
MST_CONNECTIVITY_METRIC = 'euclidean'
MST_EDGE_PERCENTILE = 73.5
MIN_DISTANCE = 104

# F-beta calculation parameters
DISTANCE_THRESHOLD_NM = 100  # Distance threshold in nanometers for matching predictions to ground truth
NM_PER_PIXEL = 0.8  # Nanometers per pixel conversion factor
FBETA_BETA = 2  # Beta value for F-beta score (2 prioritizes recall)

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
    """Organize detections by tomogram ID with normalized coordinates and metadata"""
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
                # Get original image dimensions
                orig_shape = r.orig_shape  # (height, width)
                img_h, img_w = orig_shape[0], orig_shape[1]
                
                for box in r.boxes:
                    xywh = box.xywh[0].cpu().numpy() if hasattr(box.xywh[0], 'cpu') else box.xywh[0]
                    x_center = float(xywh[0])
                    y_center = float(xywh[1])
                    w = float(xywh[2])
                    h = float(xywh[3])
                    
                    det = {
                        'x': x_center,
                        'y': y_center,
                        'z': slice_num,
                        'w': w,
                        'h': h,
                        'x_norm': x_center / img_w,
                        'y_norm': y_center / img_h,
                        'conf': float(box.conf[0]),
                        'image_path': str(img_path),
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

def calculate_fbeta_score(predictions_3d, ground_truth, tomo_id=None):
    """
    Calculate F-beta score, mAP@0.5, and Euclidean distance metrics.
    Based on fbetaEuclideanCode.txt implementation.
    
    Args:
        predictions_3d: Dictionary of predictions by tomo_id
        ground_truth: Dictionary of ground truth annotations by tomo_id
                     Each annotation should have: {'x_norm': float, 'y_norm': float, 'slice': int}
        tomo_id: Optional specific tomogram ID to calculate for (None = all)
    
    Returns:
        Dictionary with comprehensive metrics
    """
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    all_distances = []
    matched_predictions = {}  # Track which predictions are correct
    all_predictions_for_map = []  # For mAP calculation
    
    # Process single tomo or all tomos
    tomo_ids = [tomo_id] if tomo_id else set(list(ground_truth.keys()) + list(predictions_3d.keys()))
    
    for tid in tomo_ids:
        gt = ground_truth.get(tid, [])
        pred = predictions_3d.get(tid, [])
        
        matched_gt = set()
        
        for pred_idx, p in enumerate(pred):
            min_dist = float('inf')
            closest_gt_idx = None
            
            # Find closest ground truth
            for gt_idx, g in enumerate(gt):
                dx = (p['x_norm'] - g['x_norm']) * 640
                dy = (p['y_norm'] - g['y_norm']) * 640
                dz = p['z'] - g['slice']
                dist = np.sqrt(dx**2 + dy**2 + dz**2)
                
                if dist < min_dist:
                    min_dist = dist
                    closest_gt_idx = gt_idx
            
            # Check if match is within threshold
            if min_dist <= DISTANCE_THRESHOLD_NM and closest_gt_idx not in matched_gt:
                true_positives += 1
                matched_gt.add(closest_gt_idx)
                all_distances.append(min_dist)
                
                # Store as correct prediction
                if tid not in matched_predictions:
                    matched_predictions[tid] = {}
                matched_predictions[tid][pred_idx] = {'is_correct': True, 'distance': min_dist}
                
                # Add to mAP list (correct prediction)
                all_predictions_for_map.append({
                    'confidence': p['conf'],
                    'is_correct': True,
                    'distance': min_dist
                })
            else:
                false_positives += 1
                
                # Store as false positive
                if tid not in matched_predictions:
                    matched_predictions[tid] = {}
                matched_predictions[tid][pred_idx] = {'is_correct': False, 'distance': min_dist}
                
                # Add to mAP list (false positive)
                all_predictions_for_map.append({
                    'confidence': p['conf'],
                    'is_correct': False,
                    'distance': min_dist
                })
        
        # Unmatched ground truths = false negatives
        false_negatives += len(gt) - len(matched_gt)
    
    # Calculate metrics
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    
    # F-beta score with beta=2 (prioritizes recall)
    beta = FBETA_BETA
    f_beta = ((1 + beta**2) * precision * recall) / ((beta**2 * precision) + recall) if (precision + recall) > 0 else 0
    
    # Average Euclidean distance (only for correct matches)
    avg_euclidean = np.mean(all_distances) if all_distances else float('inf')
    
    # ============================================================================
    # CALCULATE mAP@0.5 (at 100nm threshold)
    # ============================================================================
    total_gt = sum(len(gt) for gt in ground_truth.values())
    map_50 = 0.0
    
    if len(all_predictions_for_map) > 0 and total_gt > 0:
        # Sort all predictions by confidence (descending)
        all_predictions_for_map.sort(key=lambda x: x['confidence'], reverse=True)
        
        precisions = []
        recalls = []
        tp_cumsum = 0
        fp_cumsum = 0
        
        for i, pred_info in enumerate(all_predictions_for_map):
            if pred_info['is_correct']:
                tp_cumsum += 1
            else:
                fp_cumsum += 1
            
            # Calculate precision and recall at this threshold
            current_precision = tp_cumsum / (tp_cumsum + fp_cumsum) if (tp_cumsum + fp_cumsum) > 0 else 0
            current_recall = tp_cumsum / total_gt if total_gt > 0 else 0
            
            precisions.append(current_precision)
            recalls.append(current_recall)
        
        # Calculate AP using 11-point interpolation (COCO standard for mAP@0.5)
        ap_11point = 0
        for recall_threshold in np.linspace(0, 1, 11):
            # Find precisions at recalls >= recall_threshold
            precisions_at_recall = [p for p, r in zip(precisions, recalls) if r >= recall_threshold]
            if len(precisions_at_recall) > 0:
                ap_11point += max(precisions_at_recall)
        ap_11point /= 11
        
        map_50 = ap_11point
    
    return {
        'true_positives': true_positives,
        'false_positives': false_positives,
        'false_negatives': false_negatives,
        'total_ground_truth': total_gt,
        'total_predictions': true_positives + false_positives,
        'precision': precision,
        'recall': recall,
        'f_beta': f_beta,
        'map_50': map_50,
        'avg_euclidean_nm': avg_euclidean,
        'min_distance_nm': min(all_distances) if all_distances else float('inf'),
        'max_distance_nm': max(all_distances) if all_distances else float('inf'),
        'median_distance_nm': float(np.median(all_distances)) if all_distances else float('inf'),
        'all_distances_nm': all_distances,
        'matched_predictions': matched_predictions
    }

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
    """Apply MST (Minimum Spanning Tree) clustering to group 3D detections"""
    predictions_3d = {}
    
    # First filter by confidence threshold
    detections_by_tomo_filtered = {}
    total_before = sum(len(d) for d in detections_by_tomo.values())
    total_after = 0
    
    for tomo_id, detections in detections_by_tomo.items():
        filtered = [d for d in detections if d['conf'] >= CONF_THRESHOLD]
        if len(filtered) > 0:
            detections_by_tomo_filtered[tomo_id] = filtered
            total_after += len(filtered)
    
    logger.info(f"[MST] Filtered detections: {total_before} -> {total_after} (≥{CONF_THRESHOLD} confidence)")
    
    # Apply MST clustering
    for tomo_id, detections in detections_by_tomo_filtered.items():
        if len(detections) < MST_MIN_CLUSTER_SIZE:
            predictions_3d[tomo_id] = [{
                'x_pixel': d['x'],
                'y_pixel': d['y'],
                'z': d['z'],
                'x_norm': d['x_norm'],
                'y_norm': d['y_norm'],
                'conf': d['conf'],
                'cluster_size': 1,
                'rep_image': d['image_path'],
                'rep_slice': d['z']
            } for d in detections]
            continue
        
        # Prepare data in PIXEL SPACE
        points = np.array([[d['x'], d['y'], d['z']] for d in detections])
        
        # Compute distance matrix
        if MST_CONNECTIVITY_METRIC == 'euclidean':
            dist_matrix = squareform(pdist(points, metric='euclidean'))
        elif MST_CONNECTIVITY_METRIC == 'manhattan':
            dist_matrix = squareform(pdist(points, metric='cityblock'))
        elif MST_CONNECTIVITY_METRIC == 'chebyshev':
            dist_matrix = squareform(pdist(points, metric='chebyshev'))
        else:
            dist_matrix = squareform(pdist(points, metric='euclidean'))
        
        # Build Minimum Spanning Tree
        mst = minimum_spanning_tree(dist_matrix)
        mst_array = mst.toarray()
        
        # Extract edges from MST
        edges = []
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                if mst_array[i, j] > 0:
                    edges.append((i, j, mst_array[i, j]))
                elif mst_array[j, i] > 0:
                    edges.append((i, j, mst_array[j, i]))
        
        # Calculate edge threshold (adaptive or fixed)
        edge_weights = [e[2] for e in edges]
        
        if MST_EDGE_PERCENTILE > 0 and len(edge_weights) > 0:
            # Use percentile-based threshold (adaptive)
            adaptive_threshold = np.percentile(edge_weights, MST_EDGE_PERCENTILE)
            final_threshold = min(adaptive_threshold, MST_EDGE_THRESHOLD)
        else:
            # Use fixed threshold
            final_threshold = MST_EDGE_THRESHOLD
        
        # Cut edges above threshold to form clusters
        adjacency = np.zeros_like(dist_matrix)
        for i, j, weight in edges:
            if weight <= final_threshold:
                adjacency[i, j] = 1
                adjacency[j, i] = 1
        
        # Find connected components
        n_components, labels = connected_components(
            csgraph=csr_matrix(adjacency),
            directed=False,
            return_labels=True
        )
        
        motors = []
        for comp_id in range(n_components):
            mask = (labels == comp_id)
            cluster_dets = [d for d, m in zip(detections, mask) if m]
            
            if len(cluster_dets) < MST_MIN_CLUSTER_SIZE:
                continue
            
            # Compute centroid
            x_norm = np.mean([d['x_norm'] for d in cluster_dets])
            y_norm = np.mean([d['y_norm'] for d in cluster_dets])
            z_avg = np.mean([d['z'] for d in cluster_dets])
            x_pixel = np.mean([d['x'] for d in cluster_dets])
            y_pixel = np.mean([d['y'] for d in cluster_dets])
            
            # Find representative detection (closest to z_avg)
            distances = [abs(d['z'] - z_avg) for d in cluster_dets]
            rep_idx = np.argmin(distances)
            rep_det = cluster_dets[rep_idx]
            
            motors.append({
                'x_norm': x_norm,
                'y_norm': y_norm,
                'z': z_avg,
                'x_pixel': x_pixel,
                'y_pixel': y_pixel,
                'cluster_size': len(cluster_dets),
                'conf': np.mean([d['conf'] for d in cluster_dets]),
                'rep_image': rep_det['image_path'],
                'rep_bbox': (rep_det['x'], rep_det['y'], rep_det['w'], rep_det['h']),
                'rep_slice': rep_det['z']
            })
        
        # Distance filtering
        predictions_3d[tomo_id] = filter_duplicates(motors)
    
    return predictions_3d

@app.post("/detect/")
async def detect(zip_file: UploadFile = File(...)):
    if not zip_file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file")

    def gen():
        # --- Timing variables ---
        t0_total = time.perf_counter()
        t0_preproc = None
        t1_preproc = None
        t0_infer = None
        t1_infer = None
        t0_post = None
        t1_post = None
        t0_dbscan = None
        t1_dbscan = None
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
                t0_preproc = time.perf_counter()
                logger.info("[PREPROCESSING] Loading and resizing images to 250x250...")
                yield (json.dumps({"stage": "preprocessing", "message": "Loading images..."}) + "\n").encode('utf-8')
                # Load and resize images (exactly as r.ipynb)
                raw_volume = load_and_preprocess_images(image_paths, target_size=(250, 250))
                # Apply masking (exactly as r.ipynb)
                logger.info("[PREPROCESSING] Applying Otsu masking...")
                yield (json.dumps({"stage": "preprocessing", "message": "Applying masking..."}) + "\n").encode('utf-8')
                processed_volume = process_volume_with_masking(raw_volume, threshold_method='otsu')
                t1_preproc = time.perf_counter()
                logger.info(f"[TIMING] Image extraction and preprocessing: ~{t1_preproc - t0_preproc:.2f} seconds")
                
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
                t0_infer = time.perf_counter()
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
                
                # --- Inference timing fix ---
                inference_start = time.perf_counter()
                # ground_truth_volume and ground_truth are commented out for now
                # ground_truth_volume = np.zeros((depth, 250, 250, 4), dtype=np.uint8)
                # ground_truth = {
                #     'tomo_7fbc49': [
                #         {'x_norm': 248/640, 'y_norm': 371/640, 'slice': 0}
                #     ]
                # }

                for idx, img in enumerate(image_paths):
                    current_annotated_url = None
                    current_transparent_url = None
                    current_slice_url = None
                    try:
                        logger.info(f"[INFERENCE] Starting processing for image {idx+1}/{len(image_paths)}: {img}")
                        with Image.open(img) as pil_src:
                            pil_rgb = pil_src.convert('RGB')
                            img_arr = np.array(pil_rgb)
                            orig = pil_src.convert('RGBA')

                        logger.info(f"[INFERENCE] Running model inference for {img}")
                        r = model(img_arr)[0]
                        logger.info(f"[INFERENCE] Model inference complete for {img}")
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

                        logger.info(f"[INFERENCE] Saved annotated image for {img}")
                        results.append({
                            "image": str(img.relative_to(images_dir)),
                            "boxes": boxes,
                            "annotated_url": f"/outputs/{out_name}"
                        })

                        # Best-effort: include URLs for stage-specific UI panels
                        current_annotated_url = f"/outputs/{out_name}"

                        # Create transparent PNG with only bounding boxes visible (no shading/fill)
                        try:
                            logger.info(f"[INFERENCE] Creating transparent PNG for {img}")
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
                                        outline=(0, 0, 255, 255),  # BLUE for motor detections
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
                            logger.info(f"[INFERENCE] Transparent PNG created for {img}")
                        except Exception as e:
                            logger.exception(f"Failed to create transparent PNG for {img}: {e}")
                            results[-1]["transparent_error"] = str(e)

                        # Create a per-slice preview image for the Post-processing panel.
                        # IMPORTANT: keep it opaque (original + overlays) so thumbnails are visible.
                        try:
                            logger.info(f"[INFERENCE] Creating post-processing slice for {img}")
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
                                draw_slice.rectangle([x1, y1, x2, y2], outline=(255, 0, 0, 255), width=2)

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
                            logger.info(f"[INFERENCE] Post-processing slice created for {img}")
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
                    logger.info(f"[INFERENCE] Yielding progress for image {img}: {progress}% done")
                    yield (json.dumps({
                        "stage": "inference",
                        "progress": progress,
                        "image": str(img.name),
                        "annotated_url": current_annotated_url,
                        "transparent_url": current_transparent_url,
                        "slice_url": current_slice_url,
                    }) + "\n").encode('utf-8')

                # --- End inference timing ---
                inference_end = time.perf_counter()
                inference_time = inference_end - inference_start
                t1_infer = time.perf_counter()
                logger.info(f"[TIMING] YOLO inference (quantized ONNX): ~{(t1_infer - t0_infer)/60:.2f} minutes ({t1_infer - t0_infer:.2f}s × 300 images)")

                t0_post = time.perf_counter()
                # Perform 3D clustering
                logger.info("[CLUSTERING] Organizing detections...")
                detections_by_tomo = organize_detections(all_yolo_results, image_paths)
                logger.info(f"[CLUSTERING] Found {len(detections_by_tomo)} tomograms")
                
                logger.info("[CLUSTERING] Running MST clustering...")
                t1_post = time.perf_counter()
                logger.info(f"[TIMING] Post-processing and volume generation: ~{t1_post - t0_post:.2f} seconds")
                t0_dbscan = t1_post
                motors_3d = cluster_3d(detections_by_tomo)
                t1_dbscan = time.perf_counter()
                logger.info(f"[TIMING] 3D MST clustering: ~{t1_dbscan - t0_dbscan:.2f} seconds")
                total_motors = sum(len(m) for m in motors_3d.values())
                logger.info(f"[CLUSTERING] Detected {total_motors} flagellar motors")
                
                # Log motor counts per tomogram
                for tomo_id, motors in motors_3d.items():
                    logger.info(f"[CLUSTERING] {tomo_id}: {len(motors)} motors detected")
                
                # --- Ground truth visualization and volume creation is commented out for now ---
                # try:
                #     logger.info("[GROUND TRUTH] Creating ground truth visualization volume...")
                #     ...existing code...
                #     logger.info("[GROUND TRUTH] Ground truth volume created")
                # except Exception as e:
                #     logger.exception(f"[GROUND TRUTH] Error creating ground truth volume: {e}")
                
                # --- F-beta score and Euclidean distance calculation/output is commented out for now ---
                # try:
                #     if ground_truth:
                #         logger.info(f"\n{'='*80}")
                #         logger.info("[F-BETA] CALCULATING METRICS")
                #         logger.info(f"{'='*80}")
                #         ...existing code...
                #         logger.info(f"\n{'='*80}\n")
                # except Exception as e:
                #     logger.exception(f"[F-BETA] Error calculating F-beta scores: {e}")

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
                    
                    # Save transparent 3D volume (RGBA - shows motor locations in BLUE)
                    transparent_vol_name = f"{base}_transparent_volume.npy"
                    transparent_vol_path = OUTPUT_DIR / transparent_vol_name
                    np.save(str(transparent_vol_path), transparent_volume)
                    logger.info(f"Saved transparent 3D volume: {transparent_vol_name} with shape {transparent_volume.shape}")
                    
                    # Save ground truth volume (commented out for now)
                    # ground_truth_vol_name = f"{base}_ground_truth_volume.npy"
                    # ground_truth_vol_path = OUTPUT_DIR / ground_truth_vol_name
                    # np.save(str(ground_truth_vol_path), ground_truth_volume)
                    # logger.info(f"Saved ground truth 3D volume: {ground_truth_vol_name} with shape {ground_truth_volume.shape}")
                    
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
                    t1_total = time.perf_counter()
                    logger.info(f"[TIMING] Total end-to-end time: ~{(t1_total - t0_total)/60:.2f} minutes")
                    
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
                        # "ground_truth_volume_url": f"/outputs/{ground_truth_vol_name}",
                        "processed_volume_url": f"/outputs/{processed_vol_name}",
                        "elapsed_ms": elapsed_ms,
                        "inference_time": round(inference_time, 3),
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
                        "inference_time": round(inference_time, 3) if 'inference_time' in locals() else None,
                        "total_motors": total_motors,
                        "motors_by_tomo": {k: len(v) for k, v in motors_3d.items()},
                        "motors_coordinates": motors_coordinates,
                        # "ground_truth_volume_url": f"/outputs/{base}_ground_truth_volume.npy" if 'ground_truth_volume' in locals() else None
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
    # Check in outputs directory first
    file_path = OUTPUT_DIR / filename
    
    # If not found, check in root directory
    if not file_path.exists():
        root_dir = Path(__file__).parent.parent
        file_path = root_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Volume file not found: {filename}")
    
    if not file_path.suffix == '.npy':
        raise HTTPException(status_code=400, detail="Only .npy files can be downloaded")
    
    logger.info(f"Serving volume file: {filename} from {file_path}")
    
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
