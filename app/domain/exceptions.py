class AppError(Exception):
    """
    Base application exception class for all custom domain errors.
    Standardized payload formatting requires message, error code, and status.
    """
    def __init__(self, message: str, code: str, http_status: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


class NotFoundError(AppError):
    """Raised when a requested resource is missing (HTTP 404)."""
    def __init__(self, message: str = "The requested resource could not be found."):
        super().__init__(message=message, code="NOT_FOUND", http_status=404)


class PermissionDenied(AppError):
    """Raised when request credentials have insufficient scopes/roles (HTTP 403)."""
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(message=message, code="PERMISSION_DENIED", http_status=403)


class ToolFailure(AppError):
    """Raised when an internal LLM tool execution fails (HTTP 502)."""
    def __init__(self, message: str = "Internal tool execution failed."):
        super().__init__(message=message, code="TOOL_FAILURE", http_status=502)


class VaultUnavailableError(AppError):
    """Raised when connection to the HashiCorp Vault server fails (HTTP 503)."""
    def __init__(self, message: str = "HashiCorp Vault secret storage is unavailable."):
        super().__init__(message=message, code="VAULT_UNAVAILABLE", http_status=503)


class ModelServerError(AppError):
    """Raised when requests to the local ModelServer microservice fail or timeout (HTTP 502)."""
    def __init__(self, message: str = "Local ModelServer service is unavailable."):
        super().__init__(message=message, code="MODEL_SERVER_ERROR", http_status=502)


class TooManyRequestsError(AppError):
    """Raised when client requests exceed designated rate-limiting quotas (HTTP 429)."""
    def __init__(self, message: str = "Rate limit exceeded. Please try again later."):
        super().__init__(message=message, code="TOO_MANY_REQUESTS", http_status=429)


class RequestIDNotFoundError(AppError):
    """Raised when request ID generation or header resolution fails in correlation gates (HTTP 500)."""
    def __init__(self, message: str = "Request correlation ID was missing or could not be generated."):
        super().__init__(message=message, code="REQUEST_ID_NOT_FOUND", http_status=500)


class ConfigError(AppError):
    """Raised when application configuration or validation thresholds are invalid (HTTP 500)."""
    def __init__(self, message: str):
        super().__init__(message=message, code="CONFIG_ERROR", http_status=500)


class TracingError(AppError):
    """Raised when connection to the tracing backend fails (HTTP 500)."""
    def __init__(self, message: str):
        super().__init__(message=message, code="TRACING_ERROR", http_status=500)
