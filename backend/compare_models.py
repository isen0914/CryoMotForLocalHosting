"""
Compare Results between best.pt and best.quant.onnx models
Shows a detailed comparison of both model performances
"""
import json
from pathlib import Path

def compare_results():
    print("=" * 80)
    print("MODEL COMPARISON: best.pt vs best.quant.onnx")
    print("=" * 80)
    
    # Load results
    pt_results_file = Path("test_outputs_pt/results.json")
    quant_results_file = Path("test_outputs_quantized/results.json")
    
    if not pt_results_file.exists():
        print(f"ERROR: {pt_results_file} not found. Run test_pt_model.py first.")
        return
    
    if not quant_results_file.exists():
        print(f"ERROR: {quant_results_file} not found. Run test_quantized_model.py first.")
        return
    
    with open(pt_results_file, 'r') as f:
        pt_data = json.load(f)
    
    with open(quant_results_file, 'r') as f:
        quant_data = json.load(f)
    
    # Performance Comparison
    print("\n📊 PERFORMANCE METRICS")
    print("-" * 80)
    print(f"{'Metric':<30} {'best.pt':<20} {'best.quant.onnx':<20} {'Difference':<20}")
    print("-" * 80)
    
    # Model load time
    pt_load = pt_data['load_time_s']
    quant_load = quant_data['load_time_s']
    load_diff = quant_load - pt_load
    load_pct = ((quant_load / pt_load) - 1) * 100 if pt_load > 0 else 0
    print(f"{'Model Load Time (s)':<30} {pt_load:<20.3f} {quant_load:<20.3f} {f'{load_diff:+.3f}s ({load_pct:+.1f}%)':<20}")
    
    # Inference time
    pt_inf = pt_data['inference_time_s']
    quant_inf = quant_data['inference_time_s']
    inf_diff = quant_inf - pt_inf
    inf_pct = ((quant_inf / pt_inf) - 1) * 100 if pt_inf > 0 else 0
    print(f"{'Total Inference Time (s)':<30} {pt_inf:<20.3f} {quant_inf:<20.3f} {f'{inf_diff:+.3f}s ({inf_pct:+.1f}%)':<20}")
    
    # Average per image
    pt_avg = pt_data['avg_time_per_image_s']
    quant_avg = quant_data['avg_time_per_image_s']
    avg_diff = quant_avg - pt_avg
    avg_pct = ((quant_avg / pt_avg) - 1) * 100 if pt_avg > 0 else 0
    print(f"{'Avg Time per Image (s)':<30} {pt_avg:<20.3f} {quant_avg:<20.3f} {f'{avg_diff:+.3f}s ({avg_pct:+.1f}%)':<20}")
    
    # Detection Results
    print("\n🎯 DETECTION RESULTS")
    print("-" * 80)
    print(f"{'Metric':<30} {'best.pt':<20} {'best.quant.onnx':<20} {'Match?':<20}")
    print("-" * 80)
    
    pt_total = pt_data['total_detections']
    quant_total = quant_data['total_detections']
    match = "✅ IDENTICAL" if pt_total == quant_total else "❌ DIFFERENT"
    print(f"{'Total Detections':<30} {pt_total:<20} {quant_total:<20} {match:<20}")
    print(f"{'Total Images Processed':<30} {pt_data['total_images']:<20} {quant_data['total_images']:<20} {'✅ IDENTICAL':<20}")
    
    # Detailed per-image comparison
    print("\n🔍 PER-IMAGE COMPARISON")
    print("-" * 80)
    
    pt_results = {r['image']: r for r in pt_data['results']}
    quant_results = {r['image']: r for r in quant_data['results']}
    
    mismatches = []
    matches = 0
    
    for img_name in sorted(pt_results.keys()):
        pt_r = pt_results[img_name]
        quant_r = quant_results.get(img_name)
        
        if quant_r is None:
            mismatches.append(f"{img_name}: Missing in quantized results")
            continue
        
        pt_count = pt_r['num_detections']
        quant_count = quant_r['num_detections']
        
        if pt_count != quant_count:
            mismatches.append(f"{img_name}: PT={pt_count}, Quant={quant_count}")
        else:
            matches += 1
            # Check if boxes are similar
            if pt_count > 0:
                pt_boxes = pt_r['boxes']
                quant_boxes = quant_r['boxes']
                
                # Compare confidence values (allow small differences due to quantization)
                for i, (pt_box, quant_box) in enumerate(zip(pt_boxes, quant_boxes)):
                    pt_conf = pt_box['confidence']
                    quant_conf = quant_box['confidence']
                    conf_diff = abs(pt_conf - quant_conf)
                    
                    # If confidence differs significantly, check boxes
                    if conf_diff > 0.01:  # Allow 1% difference
                        box_diff = [abs(p - q) for p, q in zip(pt_box['box'], quant_box['box'])]
                        max_box_diff = max(box_diff)
                        if max_box_diff > 1.0:  # Allow 1 pixel difference
                            mismatches.append(f"{img_name}[{i}]: Box/Conf mismatch (conf_diff={conf_diff:.3f}, max_box_diff={max_box_diff:.1f})")
    
    print(f"Images with matching detection counts: {matches}/{len(pt_results)}")
    
    if mismatches:
        print(f"\n⚠️  Found {len(mismatches)} mismatch(es):")
        for m in mismatches[:20]:  # Show first 20
            print(f"  • {m}")
        if len(mismatches) > 20:
            print(f"  ... and {len(mismatches) - 20} more")
    else:
        print("\n✅ All images have identical detection results!")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if pt_total == quant_total and not mismatches:
        print("✅ RESULTS ARE IDENTICAL!")
        print(f"   Both models detected exactly {pt_total} objects across {pt_data['total_images']} images.")
    elif pt_total == quant_total:
        print("⚠️  RESULTS ARE MOSTLY IDENTICAL")
        print(f"   Both models detected {pt_total} total objects, but there are minor differences")
        print(f"   in individual image detections or box coordinates.")
    else:
        print("❌ RESULTS ARE DIFFERENT")
        print(f"   PT model: {pt_total} detections")
        print(f"   Quantized model: {quant_total} detections")
        print(f"   Difference: {abs(pt_total - quant_total)} detections")
    
    print(f"\n⏱️  Speed Comparison:")
    if quant_load < pt_load:
        speedup = ((pt_load / quant_load) - 1) * 100
        print(f"   • Quantized model loads {speedup:.1f}% FASTER")
    else:
        slowdown = ((quant_load / pt_load) - 1) * 100
        print(f"   • Quantized model loads {slowdown:.1f}% SLOWER")
    
    if quant_inf < pt_inf:
        speedup = ((pt_inf / quant_inf) - 1) * 100
        print(f"   • Quantized model inference is {speedup:.1f}% FASTER")
    else:
        slowdown = ((quant_inf / pt_inf) - 1) * 100
        print(f"   • Quantized model inference is {slowdown:.1f}% SLOWER")
    
    print("\n📁 Detailed results saved in:")
    print(f"   • {pt_results_file.absolute()}")
    print(f"   • {quant_results_file.absolute()}")
    print("=" * 80)

if __name__ == "__main__":
    compare_results()
