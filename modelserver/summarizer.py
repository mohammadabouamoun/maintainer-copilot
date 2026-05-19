import structlog
from transformers import pipeline
from typing import Dict, Any
from modelserver.config import get_settings

logger = structlog.get_logger()

class Summarizer:
    def __init__(self):
        self.settings = get_settings()
        self.mock_mode = self.settings.mock_mode or self.settings.mock_aux_models
        self.pipeline = None

    def load_pipeline(self) -> None:
        """
        Loads the pre-trained HuggingFace Summarization pipeline if mock_mode is False.
        """
        if self.mock_mode:
            logger.warn("Summarizer is in MOCK mode. Skipping HuggingFace summarizer pipeline load.")
            return

        # We use a lightweight distilbart model that is CPU-friendly and downloads fast
        model_name = "sshleifer/distilbart-cnn-12-6"
        logger.info("Loading pre-trained HuggingFace Summarization pipeline...", model=model_name)
        try:
            self.pipeline = pipeline(
                "summarization",
                model=model_name
            )
            logger.info("HuggingFace Summarizer pipeline loaded successfully.")
        except Exception as e:
            logger.warn("Failed to load pre-trained summarizer pipeline. Falling back to Mock summarizer.", error=str(e))
            self.mock_mode = True

    def summarize(self, text: str, max_length: int = 150) -> str:
        """
        Generates a summary of the provided text.
        Supports fallback mock summary generation and real local sequence-to-sequence summarization.
        """
        if not text.strip():
            return "No text provided to summarize."

        if self.mock_mode:
            # Smart mock summary: extract the first sentence, capitalize, and add a context message
            sentences = text.split('.')
            first_sentence = sentences[0].strip() if sentences else text
            
            # Simple summarization stub
            summary = f"SUMMARY (MOCK): {first_sentence}. Maintainer triage recommended. [Context: issue size {len(text)} chars]"
            logger.info("Generated mock summary successfully.")
            return summary

        if not self.pipeline:
            raise RuntimeError("Summarizer pipeline is not loaded.")

        logger.info("Running HuggingFace local summarization...", max_length=max_length)
        try:
            # We tune minimum and maximum lengths based on max_length input
            min_length = max(10, min(30, max_length // 4))
            
            # pipeline returns a list containing a dict with the summary_text key
            raw_summary = self.pipeline(
                text,
                max_length=max_length,
                min_length=min_length,
                do_sample=False
            )
            
            summary_text = raw_summary[0]["summary_text"]
            logger.info("Summarization completed successfully.")
            return summary_text
        except Exception as e:
            logger.error("Error during HuggingFace summarization", error=str(e))
            raise RuntimeError(f"Summarization processing failed: {e}")
