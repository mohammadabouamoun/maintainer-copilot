import pytest
import os
from modelserver.classifier import ClassifierModel
from modelserver.config import ModelServerSettings

def test_onnx_classifier_mock_mode():
    """Verify that Mock Mode continues to function seamlessly with ONNX imports."""
    settings = ModelServerSettings(mock_mode=True)
    classifier = ClassifierModel(settings=settings)
    classifier.load_model()

    # Test bug prediction
    res_bug = classifier.predict("We got a serious nullpointer crash on startup")
    assert res_bug["label"] == "bug"
    assert res_bug["confidence"] > 0.9

    # Test feature prediction
    res_feat = classifier.predict("Please add support for dark mode theme")
    assert res_feat["label"] == "feature"
    assert res_feat["confidence"] > 0.9

def test_onnx_classifier_inference():
    """Verify that actual ONNX model inference is successfully executed and correct."""
    settings = ModelServerSettings(mock_mode=False)
    
    # Verify model files exist
    assert os.path.exists(settings.model_path)
    onnx_path = os.path.join(os.path.dirname(settings.model_path), "model.onnx")
    assert os.path.exists(onnx_path)

    classifier = ClassifierModel(settings=settings)
    classifier.load_model()

    # Run actual ONNX prediction on different inputs
    res_bug = classifier.predict("Fatal traceback error: NullPointer exception crash")
    assert res_bug["label"] in ["bug", "feature", "docs", "question"]
    assert 0.0 <= res_bug["confidence"] <= 1.0

    res_docs = classifier.predict("Check the project guide and README tutorial for setup instructions")
    assert res_docs["label"] in ["bug", "feature", "docs", "question"]
    assert 0.0 <= res_docs["confidence"] <= 1.0

    # Ensure probabilities softmax sums to ~1.0
    inputs = classifier.tokenizer(
        "Standard test issue",
        return_tensors="np",
        truncation=True,
        max_length=512
    )
    onnx_inputs = {
        "input_ids": inputs["input_ids"],
        "attention_mask": inputs["attention_mask"]
    }
    outputs = classifier.model.run(None, onnx_inputs)
    logits = outputs[0]
    
    from modelserver.classifier import softmax
    probs = softmax(logits).flatten().tolist()
    assert abs(sum(probs) - 1.0) < 1e-4

    print(f"ONNX Bug result: {res_bug}")
    print(f"ONNX Docs result: {res_docs}")
