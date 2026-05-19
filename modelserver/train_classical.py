import os
import json
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score, classification_report
import structlog

logger = structlog.get_logger()

def load_jsonl(filepath: str) -> pd.DataFrame:
    """Loads a JSONL dataset split file into a Pandas DataFrame."""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return pd.DataFrame(records)

def train_and_evaluate():
    logger.info("Starting Classical ML Baseline Training...")
    
    # Define paths
    data_dir = "data"
    train_path = os.path.join(data_dir, "train.jsonl")
    val_path = os.path.join(data_dir, "val.jsonl")
    test_path = os.path.join(data_dir, "test.jsonl")
    model_dir = "models/classical"
    model_output_path = os.path.join(model_dir, "model.pkl")

    # Ensure output directories exist
    os.makedirs(model_dir, exist_ok=True)

    # 1. Load splits
    logger.info("Loading dataset splits...")
    df_train = load_jsonl(train_path)
    df_val = load_jsonl(val_path)
    df_test = load_jsonl(test_path)

    logger.info(
        "Splits loaded successfully",
        train_count=len(df_train),
        val_count=len(df_val),
        test_count=len(df_test)
    )

    # Prepare inputs (title + body)
    # Handle possible missing titles or bodies gracefully
    def prepare_text(df: pd.DataFrame) -> pd.Series:
        titles = df["title"].fillna("").astype(str)
        bodies = df["body"].fillna("").astype(str)
        return titles + " " + bodies

    X_train = prepare_text(df_train)
    y_train = df_train["target"]

    X_test = prepare_text(df_test)
    y_test = df_test["target"]

    # 2. Build and train Pipeline
    logger.info("Building TF-IDF + Logistic Regression pipeline...")
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=2,
            max_features=10000,
            stop_words="english"
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=1.0,
            random_state=42,
            class_weight="balanced"
        ))
    ])

    logger.info("Fitting model on training set...")
    start_train_time = time.perf_counter()
    pipeline.fit(X_train, y_train)
    train_duration = time.perf_counter() - start_train_time
    logger.info("Training complete", duration_seconds=train_duration)

    # 3. Evaluate latency and metrics
    logger.info("Evaluating on test set...")
    
    # Measure average latency per sample
    start_eval_time = time.perf_counter()
    preds = pipeline.predict(X_test)
    total_eval_time = time.perf_counter() - start_eval_time
    
    avg_latency_ms = (total_eval_time / len(X_test)) * 1000
    
    # Calculate metrics
    accuracy = accuracy_score(y_test, preds)
    macro_f1 = f1_score(y_test, preds, average="macro")
    
    # Get per-class metrics
    class_report = classification_report(y_test, preds, output_dict=True)
    
    metrics = {
        "Accuracy": accuracy,
        "Macro-F1": macro_f1,
        "Bug-F1": class_report.get("bug", {}).get("f1-score", 0.0),
        "Feature-F1": class_report.get("feature", {}).get("f1-score", 0.0),
        "Docs-F1": class_report.get("docs", {}).get("f1-score", 0.0),
        "Question-F1": class_report.get("question", {}).get("f1-score", 0.0),
        "Avg-Latency-MS": avg_latency_ms,
        "Cost-Per-1k": 0.0  # CPU inference cost is essentially free ($0)
    }

    logger.info("Test Evaluation Metrics calculated:")
    print("\n================ CLASSICAL ML BASELINE METRICS ================")
    print(f"Accuracy:        {metrics['Accuracy']:.4f}")
    print(f"Macro-F1:        {metrics['Macro-F1']:.4f}")
    print(f"Bug F1:          {metrics['Bug-F1']:.4f}")
    print(f"Feature F1:      {metrics['Feature-F1']:.4f}")
    print(f"Docs F1:         {metrics['Docs-F1']:.4f}")
    print(f"Question F1:     {metrics['Question-F1']:.4f}")
    print(f"Avg Latency:     {metrics['Avg-Latency-MS']:.4f} ms per sample")
    print(f"Cost per 1k:     ${metrics['Cost-Per-1k']:.4f}")
    print("===============================================================\n")

    # 4. Save model pipeline
    logger.info("Saving trained pipeline...", path=model_output_path)
    joblib.dump(pipeline, model_output_path)
    logger.info("Model pipeline successfully saved to disk.")

    # Save metrics report for comparison
    metrics_path = os.path.join(data_dir, "classical_metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Metrics report exported.", path=metrics_path)

if __name__ == "__main__":
    train_and_evaluate()
