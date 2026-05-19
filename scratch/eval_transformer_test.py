import os
import sys
import json
import time
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, classification_report

# Add root directory to python path to resolve imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modelserver.config import ModelServerSettings
from modelserver.classifier import ClassifierModel

def evaluate_transformer():
    print("=== Starting Transformer Holdout Test Split Evaluation ===")
    
    settings = ModelServerSettings(
        model_path="models/classifier/model.safetensors",
        model_card_path="models/classifier/model_card.json",
        mock_mode=False
    )
    
    test_path = "data/test.jsonl"
    if not os.path.exists(test_path):
        print(f"FAILED: Test split not found at {test_path}")
        return

    # Load test set
    records = []
    with open(test_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    df_test = pd.DataFrame(records)
    print(f"Loaded {len(df_test)} test examples.")

    # Load model
    classifier = ClassifierModel(settings=settings)
    classifier.load_model()

    preds = []
    latencies = []

    print("Running predictions on test set...")
    for idx, row in df_test.iterrows():
        text = str(row["title"]) + " " + str(row["body"])
        
        start_time = time.perf_counter()
        res = classifier.predict(text)
        latency = (time.perf_counter() - start_time) * 1000
        
        preds.append(res["label"])
        latencies.append(latency)

    # Calculate metrics
    y_test = df_test["target"]
    accuracy = accuracy_score(y_test, preds)
    macro_f1 = f1_score(y_test, preds, average="macro")
    class_report = classification_report(y_test, preds, output_dict=True)
    avg_latency = sum(latencies) / len(latencies)

    metrics = {
        "Accuracy": accuracy,
        "Macro-F1": macro_f1,
        "Bug-F1": class_report.get("bug", {}).get("f1-score", 0.0),
        "Feature-F1": class_report.get("feature", {}).get("f1-score", 0.0),
        "Docs-F1": class_report.get("docs", {}).get("f1-score", 0.0),
        "Question-F1": class_report.get("question", {}).get("f1-score", 0.0),
        "Avg-Latency-MS": avg_latency,
        "Cost-Per-1k": 0.0
    }

    print("\n================ FINE-TUNED TRANSFORMER TEST SPLIT METRICS ================")
    print(f"Accuracy:        {metrics['Accuracy']:.4f}")
    print(f"Macro-F1:        {metrics['Macro-F1']:.4f}")
    print(f"Bug F1:          {metrics['Bug-F1']:.4f}")
    print(f"Feature F1:      {metrics['Feature-F1']:.4f}")
    print(f"Docs F1:         {metrics['Docs-F1']:.4f}")
    print(f"Question F1:     {metrics['Question-F1']:.4f}")
    print(f"Avg Latency:     {metrics['Avg-Latency-MS']:.4f} ms per sample")
    print(f"Cost per 1k:     ${metrics['Cost-Per-1k']:.4f}")
    print("===========================================================================\n")

    # Export to data/transformer_metrics.json for comparison use
    with open("data/transformer_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

if __name__ == "__main__":
    evaluate_transformer()
