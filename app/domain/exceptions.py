class AppError(Exception):
    def __init__(self, message: str, code: str, http_status: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status

class VaultUnavailableError(AppError):
    def __init__(self, message: str):
        super().__init__(message, code="VAULT_UNAVAILABLE", http_status=500)
