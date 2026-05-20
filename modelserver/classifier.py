import os
import json
import hashlib
import time
import numpy as np
import onnxruntime as ort
from typing import Dict, Any
from transformers import AutoTokenizer
import structlog

from modelserver.config import ModelServerSettings, get_settings
from modelserver.exceptions import ModelArtifactError

logger = structlog.get_logger()

def softmax(x: np.ndarray) -> np.ndarray:
    """Computes softmax values for each sets of scores in x."""
    e_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return e_x / e_x.sum(axis=-1, keepdims=True)

class ClassifierModel:
    def __init__(self, settings: ModelServerSettings = None):
        self.settings = settings or get_settings()
        self.mock_mode = self.settings.mock_mode
        self.model = None
        self.tokenizer = None
        self.label_map = {0: "bug", 1: "feature", 2: "docs", 3: "question"}
        self.inv_label_map = {v: k for k, v in self.label_map.items()}

    def _compute_sha256(self, filepath: str) -> str:
        """Computes the SHA-256 hash of a file in chunks to avoid high memory usage."""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def load_model(self) -> None:
        """
        Loads the classifier model and runs startup validation checks.
        Refuses to boot if files are missing or SHA-256 hash mismatches (Standard Lifespan/Refuse-to-Boot).
        """
        logger.info("Initializing classifier model loader...", mock_mode=self.mock_mode)

        if self.mock_mode:
            logger.warn("ModelServer is booting in MOCK mode. Skipping real model loading and validation.")
            self.model = "mock"
            self.tokenizer = "mock"
            return

        # Check weights existence
        weights_path = self.settings.model_path
        card_path = self.settings.model_card_path

        if not os.path.exists(weights_path):
            logger.error("Classifier weights missing.", path=weights_path)
            raise ModelArtifactError("weights not found")

        if not os.path.exists(card_path):
            logger.error("Model card missing.", path=card_path)
            raise ModelArtifactError("model card not found")

        # SHA-256 Verification
        logger.info("Verifying model card weights checksum...")
        try:
            with open(card_path, "r", encoding="utf-8") as f:
                card_data = json.load(f)
        except Exception as e:
            raise ModelArtifactError(f"Failed to parse model card JSON: {e}")

        # The hash could be named 'weights_sha256', 'sha256', or 'weight_file_hash'
        expected_hash = card_data.get("weights_sha256") or card_data.get("sha256") or card_data.get("weight_file_hash")
        if not expected_hash:
            raise ModelArtifactError("Model card is missing the expected weights SHA-256 hash")

        logger.info("Computing actual SHA-256 of weights file...", path=weights_path)
        actual_hash = self._compute_sha256(weights_path)

        if actual_hash != expected_hash:
            logger.error("SHA-256 validation failed.", expected=expected_hash, actual=actual_hash)
            raise ModelArtifactError(f"weights hash mismatch. Expected {expected_hash}, got {actual_hash}")

        logger.info("SHA-256 validation passed. Loading ONNX model weights...")
        
        try:
            # Load tokenizer locally
            model_dir = os.path.dirname(weights_path)
            self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
            
            # Load ONNX model using ONNX Runtime
            onnx_path = os.path.join(model_dir, "model.onnx")
            if not os.path.exists(onnx_path):
                onnx_path = weights_path.replace(".safetensors", ".onnx")
                
            logger.info("Loading ONNX Inference Session...", path=onnx_path)
            self.model = ort.InferenceSession(onnx_path)
            logger.info("ONNX Sequence Classifier loaded successfully.")
        except Exception as e:
            logger.critical("Failed to load HuggingFace/ONNX weights.", error=str(e))
            raise ModelArtifactError(f"Failed to load weights: {e}")

    def predict(self, text: str) -> Dict[str, Any]:
        """
        Performs issue classification.
        Supports fallback mock inference for development and real ONNX inference.
        """
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model has not been loaded. Call load_model() first.")

        if self.mock_mode:
            # Intelligent mock inference based on keywords
            text_lower = text.lower()
            if any(k in text_lower for k in ["crash", "bug", "error", "fail", "nullpointer", "exception"]):
                predicted_label = "bug"
                confidence = 0.96
            elif any(k in text_lower for k in ["add", "feature", "request", "support", "implement"]):
                predicted_label = "feature"
                confidence = 0.91
            elif any(k in text_lower for k in ["document", "docs", "readme", "guide", "tutorial"]):
                predicted_label = "docs"
                confidence = 0.88
            else:
                predicted_label = "question"
                confidence = 0.85

            return {
                "label": predicted_label,
                "confidence": confidence
            }

        # Real ONNX/HuggingFace Transformer Inference
        inputs = self.tokenizer(
            text,
            return_tensors="np",  # Returns numpy arrays!
            truncation=True,
            max_length=512
        )
        
        onnx_inputs = {
            "input_ids": inputs["input_ids"],
            "attention_mask": inputs["attention_mask"]
        }
        
        # Run inference using ONNX Runtime InferenceSession
        outputs = self.model.run(None, onnx_inputs)
        logits = outputs[0]
        
        probabilities = softmax(logits).flatten().tolist()
        predicted_class_id = np.argmax(logits, axis=1).item()

        predicted_label = self.label_map.get(predicted_class_id, "question")
        confidence = probabilities[predicted_class_id]

        return {
            "label": predicted_label,
            "confidence": confidence
        }
