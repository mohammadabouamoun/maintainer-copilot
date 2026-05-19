import os
import json
import time
import requests
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, classification_report
import structlog

logger = structlog.get_logger()

def evaluate_golden_set():
    logger.info("Starting Golden Set Evaluation against live ModelServer...")
    
    url = "http://localhost:8000/classify"
    golden_path = "data/golden_classification.jsonl"
    output_path = "evals/golden_results.json"
    
    if not os.path.exists(golden_path):
        logger.critical("Golden set split not found!", path=golden_path)
        return

    # Load golden dataset
    records = []
    with open(golden_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    logger.info("Loaded golden dataset", count=len(records))

    predictions = []
    latencies = []
    results = []

    print("\n" + "="*80)
    print(f"{'ISSUE ID':<30} | {'TRUE':<8} | {'PREDICTED':<9} | {'CORRECT':<7} | {'LATENCY (ms)':<12}")
    print("="*80)

    total_start_time = time.perf_counter()

    for item in records:
        issue_id = item["id"]
        text = item["text"]
        true_label = item["true_label"]

        # Call endpoint and measure time
        start_time = time.perf_counter()
        try:
            response = requests.post(url, json={"text": text}, timeout=10)
            latency = (time.perf_counter() - start_time) * 1000
            
            if response.status_code == 200:
                pred_label = response.json()["label"]
            else:
                logger.error("Request failed", status=response.status_code, body=response.text)
                pred_label = "ERROR"
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000
            logger.error("Connection failed", error=str(e))
            pred_label = "CONNECTION_ERROR"

        predictions.append(pred_label)
        latencies.append(latency)
        
        is_correct = pred_label == true_label
        correct_str = "YES" if is_correct else "NO"
        
        print(f"{issue_id[:30]:<30} | {true_label:<8} | {pred_label:<9} | {correct_str:<7} | {latency:>10.2f} ms")
        
        results.append({
            "id": issue_id,
            "true_label": true_label,
            "predicted_label": pred_label,
            "correct": is_correct,
            "latency_ms": latency
        })

    total_duration_ms = (time.perf_counter() - total_start_time) * 1000
    print("="*80 + "\n")

    # Filter out failures for metrics calculations
    valid_y_true = [r["true_label"] for r in results if r["predicted_label"] not in ("ERROR", "CONNECTION_ERROR")]
    valid_y_pred = [r["predicted_label"] for r in results if r["predicted_label"] not in ("ERROR", "CONNECTION_ERROR")]

    accuracy = accuracy_score(valid_y_true, valid_y_pred) if valid_y_true else 0.0
    macro_f1 = f1_score(valid_y_true, valid_y_pred, average="macro") if valid_y_true else 0.0
    class_report = classification_report(valid_y_true, valid_y_pred, output_dict=True) if valid_y_true else {}

    report = {
        "summary": {
            "total_examples": len(records),
            "successful_requests": len(valid_y_true),
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "average_latency_ms": sum(latencies) / len(latencies),
            "total_latency_ms": total_duration_ms
        },
        "class_metrics": {
            "bug": {
                "f1-score": class_report.get("bug", {}).get("f1-score", 0.0),
                "precision": class_report.get("bug", {}).get("precision", 0.0),
                "recall": class_report.get("bug", {}).get("recall", 0.0)
            },
            "feature": {
                "f1-score": class_report.get("feature", {}).get("f1-score", 0.0),
                "precision": class_report.get("feature", {}).get("precision", 0.0),
                "recall": class_report.get("feature", {}).get("recall", 0.0)
            },
            "docs": {
                "f1-score": class_report.get("docs", {}).get("f1-score", 0.0),
                "precision": class_report.get("docs", {}).get("precision", 0.0),
                "recall": class_report.get("docs", {}).get("recall", 0.0)
            },
            "question": {
                "f1-score": class_report.get("question", {}).get("f1-score", 0.0),
                "precision": class_report.get("question", {}).get("precision", 0.0),
                "recall": class_report.get("question", {}).get("recall", 0.0)
            }
        },
        "predictions": results
    }

    print("================ GOLDEN SET METRICS ================")
    print(f"Accuracy:        {accuracy:.4f}")
    print(f"Macro-F1:        {macro_f1:.4f}")
    print(f"Avg Latency:     {report['summary']['average_latency_ms']:.2f} ms")
    print(f"Total Latency:   {total_duration_ms/1000:.2f} seconds")
    print("====================================================\n")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    logger.info("Golden set evaluation report saved.", path=output_path)

if __name__ == "__main__":
    evaluate_golden_set()
