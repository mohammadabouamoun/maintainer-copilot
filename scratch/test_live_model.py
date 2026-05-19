import os
import sys

# Add root directory to python path to resolve imports correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modelserver.config import ModelServerSettings
from modelserver.classifier import ClassifierModel

settings = ModelServerSettings(
    model_path="models/classifier/model.safetensors",
    model_card_path="models/classifier/model_card.json",
    mock_mode=False
)

print("=== Starting ClassifierModel Validation Script ===")
try:
    classifier = ClassifierModel(settings=settings)
    classifier.load_model()
    print("✅ SUCCESS: Model loaded and SHA-256 validated successfully!")
    
    # Test a few samples representing each label class
    samples = [
        "This is a severe bug causing the application to crash on startup.",
        "Can we please add support for dark mode and user settings?",
        "Updating the README.md to fix spelling mistakes and add installation instructions.",
        "What is the best way to handle database connection pool size?"
    ]
    
    print("\n--- Running Predictions ---")
    for sample in samples:
        res = classifier.predict(sample)
        print(f"Text: '{sample}'")
        print(f"  ==> Predicted: '{res['label']}' | Confidence: {res['confidence']:.4f}\n")
except Exception as e:
    print(f"❌ FAILED: Exception occurred during validation: {e}")
    import traceback
    traceback.print_exc()
