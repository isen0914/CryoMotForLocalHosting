"""
Test script for Val-Test dataset comparing best.pt and quantized models
Output format matches tomo_2acf68_Results.txt for easy comparison
"""

import os
import sys
import numpy as np
from pathlib import Path
from ultralytics import YOLO
from sklearn.cluster import DBSCAN
from collections import defaultdict

class ModelTester:
    def __init__(self, model_path, model_type='pt'):
        """
        Initialize model tester
        
        Args:
            model_path: Path to model file (best.pt or best.quant.onnx)
            model_type: 'pt' for PyTorch, 'onnx' for ONNX
        """
        self.model_path = model_path
        self.model_type = model_type
        
        # Parameters from readme.txt and codeForWeb.txt
        self.CONF_THRESHOLD = 0.25
        self.DBSCAN_EPS = 50
        self.DBSCAN_MIN_SAMPLES = 3
        self.MIN_CLUSTER_SIZE = 3
        self.MIN_DISTANCE = 100
        self.IMAGE_SIZE = 640
        
        # Load model - Ultralytics YOLO can handle both .pt and .onnx
        self.model = YOLO(model_path)
    
    def detect_in_image(self, image_path):
        """Run detection on a single image"""
        # Ultralytics YOLO handles both .pt and .onnx models
        results = self.model.predict(
            source=str(image_path),
            imgsz=self.IMAGE_SIZE,
            conf=self.CONF_THRESHOLD,
            iou=0.45,
            verbose=False,
            save=False
        )
        
        detections = []
        if len(results) > 0 and len(results[0].boxes) > 0:
            for box in results[0].boxes:
                xywh = box.xywh[0].cpu().numpy()
                detections.append({
                    'x': float(xywh[0]),
                    'y': float(xywh[1]),
                    'conf': float(box.conf[0])
                })
        
        return detections
    
    def load_ground_truth(self, label_path, image_size=640):
        """Load ground truth from YOLO label file"""
        gt_motors = []
        
        if not os.path.exists(label_path):
            return gt_motors
        
        with open(label_path, 'r') as f:
            lines = f.readlines()
            
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 5:
                # YOLO format: class x_center y_center width height (normalized)
                x_norm = float(parts[1])
                y_norm = float(parts[2])
                
                # Convert to pixel coordinates and round properly
                x_pixel = round(x_norm * image_size)
                y_pixel = round(y_norm * image_size)
                
                gt_motors.append({
                    'x': x_pixel,
                    'y': y_pixel
                })
        
        return gt_motors
    
    def organize_detections(self, images_folder):
        """Run detection on all images and organize by tomogram"""
        detections_by_tomo = defaultdict(lambda: {'detections': [], 'slices': []})
        
        image_paths = sorted(Path(images_folder).glob('*.jpg'))
        
        for img_path in image_paths:
            filename = img_path.stem
            parts = filename.split('_')
            
            if len(parts) >= 3:
                tomo_id = f"{parts[0]}_{parts[1]}"
                slice_num = int(parts[2])
                
                detections = self.detect_in_image(img_path)
                
                for det in detections:
                    detections_by_tomo[tomo_id]['detections'].append({
                        'x': det['x'],
                        'y': det['y'],
                        'z': slice_num,
                        'conf': det['conf'],
                        'slice_name': filename
                    })
                    
                    if filename not in detections_by_tomo[tomo_id]['slices']:
                        detections_by_tomo[tomo_id]['slices'].append(filename)
        
        return detections_by_tomo
    
    def cluster_3d(self, detections):
        """Apply DBSCAN clustering to group 2D detections into 3D motors"""
        if len(detections) < self.DBSCAN_MIN_SAMPLES:
            return []
        
        # Cluster in 3D space
        points = np.array([[d['x'], d['y'], d['z']] for d in detections])
        clustering = DBSCAN(
            eps=self.DBSCAN_EPS,
            min_samples=self.DBSCAN_MIN_SAMPLES
        )
        labels = clustering.fit_predict(points)
        
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        
        motors = []
        for cid in range(n_clusters):
            mask = (labels == cid)
            cluster_dets = [d for d, m in zip(detections, mask) if m]
            
            if len(cluster_dets) < self.MIN_CLUSTER_SIZE:
                continue
            
            # Compute 3D centroid
            x_pixel = np.mean([d['x'] for d in cluster_dets])
            y_pixel = np.mean([d['y'] for d in cluster_dets])
            z_avg = np.mean([d['z'] for d in cluster_dets])
            z_rounded = int(round(z_avg))
            
            # Use floor for both X and Y to match colleague's format (467.0, 225.0)
            x_pixel = float(np.floor(x_pixel))
            y_pixel = float(np.floor(y_pixel))
            
            # Get slices with detections in this cluster
            slices_in_cluster = sorted(set([d['slice_name'] for d in cluster_dets]))
            
            motors.append({
                'x': x_pixel,
                'y': y_pixel,
                'z': z_rounded,
                'conf': np.mean([d['conf'] for d in cluster_dets]),
                'cluster_size': len(cluster_dets),
                'slices': slices_in_cluster
            })
        
        # Remove duplicate motors (distance filtering)
        filtered = self.filter_duplicates(motors)
        return filtered
    
    def filter_duplicates(self, motors):
        """Remove duplicate motors that are too close together"""
        filtered = []
        
        for motor in motors:
            is_duplicate = False
            
            for existing in filtered:
                dist = np.sqrt(
                    (motor['x'] - existing['x'])**2 +
                    (motor['y'] - existing['y'])**2 +
                    (motor['z'] - existing['z'])**2
                )
                
                if dist < self.MIN_DISTANCE:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered.append(motor)
        
        return filtered
    
    def calculate_euclidean_distance(self, pred_x, pred_y, gt_x, gt_y, pixel_size_nm=0.8):
        """Calculate Euclidean distance in nanometers"""
        dist_pixels = np.sqrt((pred_x - gt_x)**2 + (pred_y - gt_y)**2)
        dist_nm = dist_pixels * pixel_size_nm
        return dist_nm
    
    def test_on_valtest(self, images_folder, labels_folder, output_file):
        """
        Test model on Val-Test dataset and generate formatted output
        
        Args:
            images_folder: Path to Images folder
            labels_folder: Path to labels folder
            output_file: Path to save results
        """
        print(f"\n{'='*80}")
        print(f"Testing Model: {self.model_path}")
        print(f"Model Type: {self.model_type.upper()}")
        print(f"{'='*80}\n")
        
        # Step 1: Run detection and organize by tomogram
        print("Step 1: Running detections on all images...")
        detections_by_tomo = self.organize_detections(images_folder)
        
        # Step 2: Load ground truth
        print("Step 2: Loading ground truth annotations...")
        ground_truth_by_tomo = defaultdict(list)
        
        for label_file in Path(labels_folder).glob('*.txt'):
            filename = label_file.stem
            parts = filename.split('_')
            
            if len(parts) >= 3:
                tomo_id = f"{parts[0]}_{parts[1]}"
                slice_num = int(parts[2])
                
                gt_motors = self.load_ground_truth(label_file)
                
                for gt in gt_motors:
                    ground_truth_by_tomo[tomo_id].append({
                        'x': gt['x'],
                        'y': gt['y'],
                        'z': slice_num,
                        'slice_name': filename
                    })
        
        # Step 3: Apply 3D clustering
        print("Step 3: Applying 3D clustering...")
        results_by_tomo = {}
        
        for tomo_id, data in detections_by_tomo.items():
            detections = data['detections']
            
            # Count raw detections
            num_raw_detections = len(detections)
            
            # Apply clustering
            clustered_motors = self.cluster_3d(detections)
            
            results_by_tomo[tomo_id] = {
                'raw_detections': num_raw_detections,
                'clustered_motors': clustered_motors,
                'detected_slices': sorted(data['slices'])
            }
        
        # Step 4: Match predictions with ground truth and generate report
        print("Step 4: Matching predictions with ground truth...\n")
        
        with open(output_file, 'w') as f:
            for tomo_id in sorted(set(list(ground_truth_by_tomo.keys()) + list(results_by_tomo.keys()))):
                gt_motors = ground_truth_by_tomo.get(tomo_id, [])
                results = results_by_tomo.get(tomo_id, {
                    'raw_detections': 0,
                    'clustered_motors': [],
                    'detected_slices': []
                })
                
                # Write header
                f.write(f"Tomogram_ID: {tomo_id}\n\n")
                f.write(f"\nGT Motors in Tomogram: {len(gt_motors)}\n")
                
                # Write ground truth locations
                for i, gt in enumerate(gt_motors, 1):
                    if i == 1:
                        f.write(f"\nLocation: SLICE [{gt['slice_name']}]\n")
                        f.write(f"\tGT_X: {int(gt['x'])}\n")
                        f.write(f"\tGT_Y: {int(gt['y'])}\n")
                        f.write(f"\tGT_Z: {gt['z']}\n")
                
                # Write results
                model_name = "best.pt" if self.model_type == 'pt' else "best.quant.onnx"
                f.write(f"\nRESULTS: {model_name}\n")
                f.write(f"Total # of detected motors Before Post: {results['raw_detections']}\n")
                f.write(f"Total # of detected motors After Post: {len(results['clustered_motors'])}\n")
                
                # Match predictions with ground truth
                correctly_detected = 0
                min_distance = float('inf')
                best_match = None
                
                for pred in results['clustered_motors']:
                    for gt in gt_motors:
                        # Check if Z is close
                        if abs(pred['z'] - gt['z']) <= 10:  # Within 10 slices
                            dist = self.calculate_euclidean_distance(
                                pred['x'], pred['y'], gt['x'], gt['y']
                            )
                            
                            if dist < min_distance:
                                min_distance = dist
                                best_match = pred
                
                # Determine if detected
                if best_match and min_distance < 20:  # Within 20nm threshold
                    correctly_detected = 1
                    f.write(f"Total # of Correctly Detected Motors: {correctly_detected}\n")
                    f.write(f"EUCLIDEAN_DISTANCE: {min_distance:.1f}nm\n")
                    f.write(f"Confidence: {best_match['conf']:.2f}\n")
                    f.write(f"BEFORE (raw): DETECTED\n")
                    f.write(f"AFTER (post): DETECTED\n")
                else:
                    f.write(f"Total # of Correctly Detected Motors: 0\n")
                    if best_match:
                        f.write(f"EUCLIDEAN_DISTANCE: {min_distance:.1f}nm (Too far)\n")
                        f.write(f"Confidence: {best_match['conf']:.2f}\n")
                    f.write(f"BEFORE (raw): {'DETECTED' if results['raw_detections'] > 0 else 'NOT DETECTED'}\n")
                    f.write(f"AFTER (post): NOT DETECTED\n")
                
                # Write detected slices
                if results['detected_slices']:
                    f.write(f"Detected slices with motors:\n")
                    for slice_name in results['detected_slices']:
                        f.write(f"\t{slice_name}\n")
                
                # Write final 3D coordinates
                if best_match:
                    f.write(f"\nFinal 3D Coordinates After Post: \n")
                    f.write(f"\tFinal_X: {best_match['x']:.1f}\n")
                    f.write(f"\tFinal_Y: {best_match['y']:.1f}\n")
                    f.write(f"\tFinal_Z: {best_match['z']:.1f}\n")
                    
                    # Find representative slice (closest to Z)
                    for slice_name in best_match['slices']:
                        slice_parts = slice_name.split('_')
                        if len(slice_parts) >= 3:
                            slice_z = int(slice_parts[2])
                            if slice_z == best_match['z']:
                                f.write(f"Final Representative Slice:\n")
                                f.write(f"\t{slice_name}\n")
                                break
                
                f.write("\n" + "="*80 + "\n\n")
        
        print(f"✓ Results saved to: {output_file}")
        print(f"\n{'='*80}\n")


def main():
    """Main function to test all models"""
    
    # Paths
    base_dir = Path(__file__).parent
    val_test_dir = base_dir.parent / "tools" / "Val-Test-extracted" / "Val-Test"
    images_folder = val_test_dir / "Images"
    labels_folder = val_test_dir / "labels"
    
    # Check if Val-Test is extracted
    if not images_folder.exists():
        print("ERROR: Val-Test dataset not found!")
        print(f"Please extract Val-Test.zip to: {val_test_dir}")
        sys.exit(1)
    
    # Model paths
    models_to_test = [
        {
            'path': base_dir / "best.pt",
            'type': 'pt',
            'output': base_dir / "ValTest_Results_best_pt.txt"
        },
        {
            'path': base_dir / "best.quant.onnx",
            'type': 'onnx',
            'output': base_dir / "ValTest_Results_quantized.txt"
        }
    ]
    
    # Test each model
    for model_config in models_to_test:
        model_path = model_config['path']
        
        if not model_path.exists():
            print(f"WARNING: Model not found: {model_path}")
            print(f"Skipping...\n")
            continue
        
        try:
            tester = ModelTester(str(model_path), model_config['type'])
            tester.test_on_valtest(
                str(images_folder),
                str(labels_folder),
                str(model_config['output'])
            )
        except Exception as e:
            print(f"ERROR testing {model_path}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*80)
    print("TESTING COMPLETE!")
    print("="*80)
    print("\nResults files:")
    for model_config in models_to_test:
        if model_config['output'].exists():
            print(f"  - {model_config['output'].name}")


if __name__ == "__main__":
    main()
