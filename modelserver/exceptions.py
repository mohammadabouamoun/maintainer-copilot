class ModelServerError(Exception):
    """Base exception class for ModelServer errors."""
    def __init__(self, message: str, code: str = "MODEL_SERVER_ERROR", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code

class ModelArtifactError(ModelServerError):
    """Raised when model weights or artifacts are missing, corrupt, or hash-mismatched."""
    def __init__(self, message: str):
        super().__init__(message, code="MODEL_ARTIFACT_ERROR", status_code=500)
