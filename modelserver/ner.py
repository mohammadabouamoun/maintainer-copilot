import re
import structlog
from transformers import pipeline
from typing import List, Dict, Any
from modelserver.config import get_settings

logger = structlog.get_logger()

class NerExtractor:
    def __init__(self):
        self.settings = get_settings()
        self.mock_mode = self.settings.mock_mode or self.settings.mock_aux_models
        self.nlp = None

    def load_pipeline(self) -> None:
        """
        Loads the pre-trained HuggingFace NER pipeline model if mock_mode is False.
        """
        if self.mock_mode:
            logger.warn("NER extractor is in MOCK mode. Skipping HuggingFace pipeline model load.")
            return

        logger.info("Loading pre-trained HuggingFace NER pipeline (dslim/bert-base-NER)...")
        try:
            # We use simpler aggregation to return full entity words instead of sub-word tokens
            self.nlp = pipeline(
                "ner",
                model="dslim/bert-base-NER",
                aggregation_strategy="simple"
            )
            logger.info("HuggingFace NER pipeline loaded successfully.")
        except Exception as e:
            logger.warn("Failed to load pre-trained NER pipeline. Falling back to Mock BERT + Regex-only extraction mode.", error=str(e))
            self.mock_mode = True

    def extract(self, text: str) -> List[Dict[str, Any]]:
        """
        Extracts entities from the text.
        Merges general-purpose natural language entities (BERT) with code-shaped tokens (Regex).
        """
        entities = []

        # 1. BERT NLP Entity Extraction (if loaded/active)
        if not self.mock_mode and self.nlp:
            try:
                raw_entities = self.nlp(text)
                for ent in raw_entities:
                    entities.append({
                        "text": str(ent["word"]),
                        "label": str(ent["entity_group"]),
                        "start": int(ent["start"]),
                        "end": int(ent["end"])
                    })
            except Exception as e:
                logger.error("Error during BERT NER extraction", error=str(e))

        # 2. Customized Code-Shaped Regex Extractors (Point 2.6 spec)

        # A. Version strings: v1.2.3, 0.19.0, 3.12.2-beta
        version_pattern = re.compile(r'\bv?\d+\.\d+(?:\.\d+)+(?:-[a-zA-Z0-9.]+)?\b')
        for match in version_pattern.finditer(text):
            entities.append({
                "text": match.group(),
                "label": "VERSION",
                "start": match.start(),
                "end": match.end()
            })

        # B. Error codes / common exceptions: HTTP 500, ENOENT, KeyError, RuntimeError
        error_pattern = re.compile(
            r'\b(?:HTTP \d{3}|[A-Z]{3,}_[A-Z0-9_]+|[A-Za-z]+Error|[A-Za-z]+Exception|ENOENT|EADDRINUSE|KeyError|TypeError|ValueError)\b'
        )
        for match in error_pattern.finditer(text):
            entities.append({
                "text": match.group(),
                "label": "ERROR_CODE",
                "start": match.start(),
                "end": match.end()
            })

        # C. Function/method calls: foo_bar(), df.groupby(), render_diffs()
        function_pattern = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*\(\)')
        for match in function_pattern.finditer(text):
            entities.append({
                "text": match.group(),
                "label": "FUNCTION_CALL",
                "start": match.start(),
                "end": match.end()
            })

        # Deduplicate overlaps by preferring index priority and coordinate sorting
        seen_coordinates = set()
        deduplicated = []

        # Sort by start index (ascending) and then by end index (descending - longest match first)
        for ent in sorted(entities, key=lambda x: (x["start"], -x["end"])):
            # Create a coordinate range signature
            coord_signature = (ent["start"], ent["end"])
            
            # Simple check: if this exactly overlaps or is completely subset of an already selected range, we skip
            overlap_found = False
            for prev_start, prev_end in seen_coordinates:
                # Check if current entity is completely swallowed by a previous entity
                if ent["start"] >= prev_start and ent["end"] <= prev_end:
                    overlap_found = True
                    break
                # Check if current entity swallows a previous entity (should not happen due to sorting longest-first)
                elif ent["start"] <= prev_start and ent["end"] >= prev_end:
                    overlap_found = True
                    break

            if not overlap_found:
                seen_coordinates.add(coord_signature)
                deduplicated.append(ent)

        return deduplicated
