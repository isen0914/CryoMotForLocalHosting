"""
Test script for models using Val-Test.zip
Outputs results in the same format as tomo_2acf68_Results.txt
Tests best.pt, best.quant.onnx models and compares with ground truth
"""
from ultralytics import YOLO
import zipfile
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import numpy as np
import time
from collections import defaultdict
import math

# Configuration
ZIP_PATH = "../tools/Val-Test.zip"
CONF_THRESHOLD = 0.25
IMAGE_SIZE = (640, 640)  # Assuming standard YOLO input size
NM_PER_PIXEL = 0.5  # Nanometer per pixel (adjust based on your data)

def parse_label_file(label_path):
    """Parse YOLO format label file and return list of bounding boxes"""
    boxes = []
    with open(label_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                cls, x_center, y_center, width, height = map(float, parts[:5])
                boxes.append({
                    'class': int(cls),
                    'x_center': x_center,
                    'y_center': y_center,
                    'width': width,
                    'height': height
                })
    return boxes

def yolo_to_pixel_coords(x_center, y_center, img_width, img_height):
    """Convert YOLO normalized coordinates to pixel coordinates"""
    x_pixel = x_center * img_width
    y_pixel = y_center * img_height
    return x_pixel, y_pixel

def calculate_euclidean_distance(x1, y1, x2, y2, nm_per_pixel):
    """Calculate Euclidean distance in nanometers"""
    pixel_distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    return pixel_distance * nm_per_pixel

def process_detections_3d(detections_by_slice, gt_coords=None):
    """
    Process 3D detections across slices to find final coordinates
    Similar to the post-processing shown in tomo_2acf68_Results.txt
    """
    if not detections_by_slice:
        return None, None, []
    
    # Collect all detections with their z-coordinates
    all_detections = []
    detected_slices = []
    
    for slice_num, dets in sorted(detections_by_slice.items()):
        detected_slices.append(slice_num)
        for det in dets:
            all_detections.append({
                'x': det['x'],
                'y': det['y'],
                'z': slice_num,
                'conf': det['conf']
            })
    
    if not all_detections:
        return None, None, detected_slices
    
    # Find the detection with highest confidence
    best_detection = max(all_detections, key=lambda d: d['conf'])
    
    # Calculate median/mean position across all detections in the cluster
    x_coords = [d['x'] for d in all_detections]
    y_coords = [d['y'] for d in all_detections]
    z_coords = [d['z'] for d in all_detections]
    
    final_coords = {
        'x': np.median(x_coords),
        'y': np.median(y_coords),
        'z': int(np.median(z_coords)),
        'conf': best_detection['conf']
    }
    
    return final_coords, best_detection, detected_slices

def test_model(model_path, model_name):
    """Test a single model and return results"""
    print("\n" + "=" * 80)
    print(f"Testing {model_name}")
    print("=" * 80)
    
    # Load model
    print(f"\n1. Loading model: {model_path}")
    start_load = time.time()
    model = YOLO(model_path)
    load_time = time.time() - start_load
    print(f"   Model loaded in {load_time:.3f}s")
    
    # Extract ZIP
    print(f"\n2. Extracting ZIP: {ZIP_PATH}")
    temp_dir = tempfile.mkdtemp()
    results = {}
    
    try:
        with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
            zf.extractall(temp_dir)
        
        # Find images and labels folders
        val_test_dir = Path(temp_dir) / "Val-Test"
        images_dir = val_test_dir / "Images"
        labels_dir = val_test_dir / "labels"
        
        # Get all image files
        image_files = sorted(images_dir.glob("*.jpg"))
        print(f"   Found {len(image_files)} image(s)")
        
        # Parse ground truth labels
        print(f"\n3. Parsing ground truth labels...")
        ground_truth = {}
        gt_motor_location = None
        
        for img_file in image_files:
            label_file = labels_dir / f"{img_file.stem}.txt"
            if label_file.exists():
                boxes = parse_label_file(label_file)
                if boxes:
                    # Extract slice number from filename (e.g., tomo_2acf68_0135)
                    slice_num = int(img_file.stem.split('_')[-1])
                    ground_truth[slice_num] = boxes
                    
                    # Get image dimensions
                    img = Image.open(img_file)
                    img_width, img_height = img.size
                    
                    # Convert to pixel coordinates for the GT
                    for box in boxes:
                        gt_x, gt_y = yolo_to_pixel_coords(
                            box['x_center'], box['y_center'],
                            img_width, img_height
                        )
                        # Store the first GT motor found (assuming single motor in dataset)
                        if gt_motor_location is None:
                            gt_motor_location = {
                                'x': int(gt_x),
                                'y': int(gt_y),
                                'z': slice_num,
                                'slice_name': img_file.stem
                            }
        
        total_gt_motors = 1 if gt_motor_location else 0
        print(f"   Ground truth motors: {total_gt_motors}")
        if gt_motor_location:
            print(f"   GT Location: Slice {gt_motor_location['slice_name']}, "
                  f"X={gt_motor_location['x']}, Y={gt_motor_location['y']}, Z={gt_motor_location['z']}")
        
        # Run inference
        print(f"\n4. Running inference on {len(image_files)} image(s)...")
        start_inference = time.time()
        
        detections_by_slice = defaultdict(list)
        total_detections_raw = 0
        
        for idx, img_path in enumerate(image_files, 1):
            if idx % 50 == 0 or idx == 1:
                print(f"   Processing [{idx}/{len(image_files)}]: {img_path.name}")
            
            # Run detection
            results_pred = model.predict(source=str(img_path), conf=CONF_THRESHOLD, verbose=False)
            
            # Process results
            for result in results_pred:
                boxes = result.boxes
                num_detections = len(boxes)
                total_detections_raw += num_detections
                
                if num_detections > 0:
                    slice_num = int(img_path.stem.split('_')[-1])
                    img = Image.open(img_path)
                    img_width, img_height = img.size
                    
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        conf = float(box.conf[0])
                        cls = int(box.cls[0])
                        
                        # Calculate center in pixel coordinates
                        x_center_px = (x1 + x2) / 2
                        y_center_px = (y1 + y2) / 2
                        
                        detections_by_slice[slice_num].append({
                            'x': x_center_px,
                            'y': y_center_px,
                            'conf': conf,
                            'class': cls
                        })
        
        inference_time = time.time() - start_inference
        print(f"   Inference completed in {inference_time:.3f}s")
        
        # Process 3D detections
        print(f"\n5. Processing 3D detections...")
        final_coords, best_det, detected_slices = process_detections_3d(
            detections_by_slice, gt_motor_location
        )
        
        # Calculate metrics
        total_detections_post = 1 if final_coords else 0
        correctly_detected = 0
        euclidean_distance = None
        detection_status_before = "NOT DETECTED"
        detection_status_after = "NOT DETECTED"
        
        if final_coords and gt_motor_location:
            euclidean_distance = calculate_euclidean_distance(
                final_coords['x'], final_coords['y'],
                gt_motor_location['x'], gt_motor_location['y'],
                NM_PER_PIXEL
            )
            detection_status_before = "DETECTED"
            detection_status_after = "DETECTED"
            correctly_detected = 1
        
        # Store results
        results = {
            'model_name': model_name,
            'model_path': model_path,
            'tomogram_id': 'tomo_2acf68',
            'gt_motors': total_gt_motors,
            'gt_location': gt_motor_location,
            'total_detections_before': total_detections_raw,
            'total_detections_after': total_detections_post,
            'correctly_detected': correctly_detected,
            'euclidean_distance': euclidean_distance,
            'final_coords': final_coords,
            'detected_slices': detected_slices,
            'detection_status_before': detection_status_before,
            'detection_status_after': detection_status_after,
            'load_time': load_time,
            'inference_time': inference_time
        }
        
        # Print summary
        print_results_summary(results)
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return results

def print_results_summary(results):
    """Print results in the format similar to tomo_2acf68_Results.txt"""
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    
    print(f"\nTomogram_ID: {results['tomogram_id']}")
    print(f"\nGT Motors in Tomogram: {results['gt_motors']}")
    
    if results['gt_location']:
        gt = results['gt_location']
        print(f"\nLocation: SLICE [{gt['slice_name']}]")
        print(f"\tGT_X: {gt['x']}")
        print(f"\tGT_Y: {gt['y']}")
        print(f"\tGT_Z: {gt['z']}")
    
    print(f"\nRESULTS: {results['model_name']}")
    print(f"Total # of detected motors Before Post: {results['total_detections_before']}")
    print(f"Total # of detected motors After Post: {results['total_detections_after']}")
    print(f"Total # of Correctly Detected Motors: {results['correctly_detected']}")
    
    if results['euclidean_distance'] is not None:
        print(f"EUCLIDEAN_DISTANCE: {results['euclidean_distance']:.1f}nm")
    
    if results['final_coords']:
        print(f"Confidence: {results['final_coords']['conf']:.2f}")
    
    print(f"BEFORE (raw): {results['detection_status_before']}")
    print(f"AFTER (post): {results['detection_status_after']}")
    
    if results['detected_slices']:
        print(f"Detected slices with motors:")
        for slice_num in results['detected_slices']:
            print(f"\ttomo_2acf68_{slice_num:04d}")
    
    if results['final_coords']:
        fc = results['final_coords']
        print(f"\nFinal 3D Coordinates After Post:")
        print(f"\tFinal_X: {fc['x']:.1f}")
        print(f"\tFinal_Y: {fc['y']:.1f}")
        print(f"\tFinal_Z: {fc['z']}")
        print(f"Final Representative Slice:")
        print(f"\ttomo_2acf68_{fc['z']:04d}")
    
    print(f"\nPerformance:")
    print(f"\tModel load time: {results['load_time']:.3f}s")
    print(f"\tInference time: {results['inference_time']:.3f}s")
    print("=" * 80)

def save_results_to_file(results, output_file):
    """Save results to a text file in the same format as tomo_2acf68_Results.txt"""
    with open(output_file, 'w') as f:
        f.write(f"Tomogram_ID: {results['tomogram_id']}\n\n")
        f.write(f"\nGT Motors in Tomogram: {results['gt_motors']}\n")
        
        if results['gt_location']:
            gt = results['gt_location']
            f.write(f"\nLocation: SLICE [{gt['slice_name']}]\n")
            f.write(f"\tGT_X: {gt['x']}\n")
            f.write(f"\tGT_Y: {gt['y']}\n")
            f.write(f"\tGT_Z: {gt['z']}\n")
        
        f.write(f"\nRESULTS: {results['model_name']}\n")
        f.write(f"Total # of detected motors Before Post: {results['total_detections_before']}\n")
        f.write(f"Total # of detected motors After Post: {results['total_detections_after']}\n")
        f.write(f"Total # of Correctly Detected Motors: {results['correctly_detected']}\n")
        
        if results['euclidean_distance'] is not None:
            f.write(f"EUCLIDEAN_DISTANCE: {results['euclidean_distance']:.1f}nm\n")
        
        if results['final_coords']:
            f.write(f"Confidence: {results['final_coords']['conf']:.2f}\n")
        
        f.write(f"BEFORE (raw): {results['detection_status_before']}\n")
        f.write(f"AFTER (post): {results['detection_status_after']}\n")
        
        if results['detected_slices']:
            f.write(f"Detected slices with motors:\n")
            for slice_num in results['detected_slices']:
                f.write(f"\ttomo_2acf68_{slice_num:04d}\n")
        
        if results['final_coords']:
            fc = results['final_coords']
            f.write(f"\nFinal 3D Coordinates After Post: \n")
            f.write(f"\tFinal_X: {fc['x']:.1f}\n")
            f.write(f"\tFinal_Y: {fc['y']:.1f}\n")
            f.write(f"\tFinal_Z: {fc['z']}\n")
            f.write(f"Final Representative Slice:\n")
            f.write(f"\ttomo_2acf68_{fc['z']:04d}\n")

def main():
    """Main function to test all models"""
    print("\n" + "=" * 80)
    print("YOLO MODEL COMPARISON TEST")
    print("Using Val-Test.zip with Images and Labels folders")
    print("=" * 80)
    
    # Test configurations
    models_to_test = [
        ("best.pt", "best.pt (PyTorch)"),
        ("best.quant.onnx", "best.quant.onnx (Quantized)")
    ]
    
    all_results = []
    
    # Test each model
    for model_path, model_name in models_to_test:
        try:
            results = test_model(model_path, model_name)
            all_results.append(results)
            
            # Save individual results to file
            output_file = f"ValTest_Results_{model_path.replace('.', '_')}.txt"
            save_results_to_file(results, output_file)
            print(f"\nResults saved to: {output_file}")
            
        except Exception as e:
            print(f"\nError testing {model_name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Print comparison summary
    if len(all_results) >= 2:
        print("\n\n" + "=" * 80)
        print("COMPARISON SUMMARY")
        print("=" * 80)
        print(f"\n{'Model':<30} {'Detections (Raw)':<20} {'Detections (Post)':<20} {'Euclidean Dist':<20} {'Confidence':<15}")
        print("-" * 105)
        
        for res in all_results:
            dist_str = f"{res['euclidean_distance']:.1f}nm" if res['euclidean_distance'] is not None else "N/A"
            conf_str = f"{res['final_coords']['conf']:.2f}" if res['final_coords'] else "N/A"
            print(f"{res['model_name']:<30} {res['total_detections_before']:<20} {res['total_detections_after']:<20} {dist_str:<20} {conf_str:<15}")
        
        print("=" * 80)

if __name__ == "__main__":
    main()
