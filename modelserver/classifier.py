import os
import json
import hashlib
import time
import torch
from typing import Dict, Any
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import structlog

from modelserver.config import ModelServerSettings, get_settings
from modelserver.exceptions import ModelArtifactError

logger = structlog.get_logger()

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

        logger.info("SHA-256 validation passed. Loading PyTorch model weights...", path=weights_path)
        
        try:
            # Load tokenizer and sequence classification model locally
            # In a real environment, the model weights folder must have config.json and vocabulary files.
            # We point AutoModel to load the directory containing the checkpoint.
            model_dir = os.path.dirname(weights_path)
            self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)
            self.model.eval() # Set to evaluation mode
            logger.info("PyTorch Sequence Classifier loaded successfully.")
        except Exception as e:
            logger.critical("Failed to load HuggingFace/PyTorch weights.", error=str(e))
            raise ModelArtifactError(f"Failed to load weights: {e}")

    def predict(self, text: str) -> Dict[str, Any]:
        """
        Performs issue classification.
        Supports fallback mock inference for development and real PyTorch inference.
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

        # Real PyTorch/HuggingFace Transformer Inference
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512
        )
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=1).flatten().tolist()
            predicted_class_id = torch.argmax(logits, dim=1).item()

        predicted_label = self.label_map.get(predicted_class_id, "question")
        confidence = probabilities[predicted_class_id]

        return {
            "label": predicted_label,
            "confidence": confidence
        }
