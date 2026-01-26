"""
Test script for best.pt model
Tests the PyTorch model with valtest.zip and displays results
"""
from ultralytics import YOLO
import zipfile
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import json
import time

# Configuration
MODEL_PATH = "best.pt"
ZIP_PATH = "../tools/valtest.zip"
OUTPUT_DIR = Path("test_outputs_pt")
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tif', '.tiff'}

def test_pt_model():
    print("=" * 80)
    print("Testing best.pt (PyTorch) Model")
    print("=" * 80)
    
    # Load model
    print(f"\n1. Loading model: {MODEL_PATH}")
    start_load = time.time()
    model = YOLO(MODEL_PATH)
    load_time = time.time() - start_load
    print(f"   Model loaded in {load_time:.3f}s")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Extract ZIP
    print(f"\n2. Extracting ZIP: {ZIP_PATH}")
    temp_dir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
            zf.extractall(temp_dir)
        
        # Find all images
        image_files = []
        for ext in IMAGE_EXTS:
            image_files.extend(Path(temp_dir).rglob(f"*{ext}"))
        
        print(f"   Found {len(image_files)} image(s)")
        
        # Run inference
        print(f"\n3. Running inference on {len(image_files)} image(s)...")
        start_inference = time.time()
        
        all_results = []
        total_detections = 0
        
        for idx, img_path in enumerate(sorted(image_files), 1):
            print(f"   Processing [{idx}/{len(image_files)}]: {img_path.name}")
            
            # Run detection
            results = model.predict(source=str(img_path), conf=0.25, verbose=False)
            
            # Process results
            for result in results:
                boxes = result.boxes
                num_detections = len(boxes)
                total_detections += num_detections
                
                print(f"      -> {num_detections} detection(s)")
                
                # Save annotated image
                annotated = result.plot()
                output_path = OUTPUT_DIR / f"annotated_{img_path.name}"
                Image.fromarray(annotated).save(output_path)
                
                # Collect box details
                box_data = []
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    box_data.append({
                        "box": [x1, y1, x2, y2],
                        "confidence": conf,
                        "class": cls
                    })
                
                all_results.append({
                    "image": img_path.name,
                    "num_detections": num_detections,
                    "boxes": box_data
                })
        
        inference_time = time.time() - start_inference
        
        # Summary
        print("\n" + "=" * 80)
        print("RESULTS SUMMARY (best.pt)")
        print("=" * 80)
        print(f"Total images processed: {len(image_files)}")
        print(f"Total detections: {total_detections}")
        print(f"Model load time: {load_time:.3f}s")
        print(f"Inference time: {inference_time:.3f}s")
        print(f"Average per image: {inference_time/len(image_files):.3f}s")
        print(f"\nAnnotated images saved to: {OUTPUT_DIR.absolute()}")
        
        # Save detailed results to JSON
        results_file = OUTPUT_DIR / "results.json"
        with open(results_file, 'w') as f:
            json.dump({
                "model": "best.pt",
                "total_images": len(image_files),
                "total_detections": total_detections,
                "load_time_s": load_time,
                "inference_time_s": inference_time,
                "avg_time_per_image_s": inference_time/len(image_files),
                "results": all_results
            }, f, indent=2)
        
        print(f"Detailed results saved to: {results_file.absolute()}")
        print("=" * 80)
        
        # Print detection details
        print("\nDetection Details:")
        print("-" * 80)
        for item in all_results:
            print(f"\n{item['image']}: {item['num_detections']} detection(s)")
            for idx, box in enumerate(item['boxes'], 1):
                print(f"  [{idx}] confidence={box['confidence']:.3f}, class={box['class']}, bbox={[f'{x:.1f}' for x in box['box']]}")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_pt_model()
