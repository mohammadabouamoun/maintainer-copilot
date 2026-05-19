import httpx
from typing import Any, Dict, Optional
from app.config import Settings, get_settings
from app.domain.exceptions import VaultUnavailableError

class VaultClient:
    def __init__(self, settings: Optional[Settings] = None, client: Optional[httpx.AsyncClient] = None):
        """
        Initializes the Vault client. Supports HTTP client dependency injection.
        """
        self.settings = settings or get_settings()
        self.vault_addr = self.settings.vault_addr
        self.vault_token = self.settings.vault_root_token

        if not self.vault_addr or not self.vault_token:
            raise VaultUnavailableError("VAULT_ADDR and VAULT_ROOT_TOKEN configuration must be set")

        self.headers = {"X-Vault-Token": self.vault_token}
        
        # If an external client is injected, we reuse it (Standard 3). 
        # Otherwise, we manage an internal client for standalone usage.
        self._external_client = client is not None
        self.client = client or httpx.AsyncClient(headers=self.headers, timeout=5.0)

    async def ping(self) -> None:
        """Pings Vault to ensure it's available. Refuses to boot if down."""
        try:
            # sys/health is the standard Vault health-check endpoint
            response = await self.client.get(f"{self.vault_addr}/v1/sys/health")
            response.raise_for_status()
        except httpx.RequestError as e:
            raise VaultUnavailableError(f"Cannot connect to Vault at {self.vault_addr}: {e}")
        except httpx.HTTPStatusError as e:
            # Vault health can return 4xx/5xx depending on initialization/seal status, but we expect it to be responsive
            if e.response.status_code not in (200, 429, 472, 473):
                raise VaultUnavailableError(f"Vault health check failed with status {e.response.status_code}")

    async def get_secret(self, path: str) -> Dict[str, Any]:
        """Gets a secret from the Vault KV store."""
        try:
            url = f"{self.vault_addr}/v1/{path}"
            response = await self.client.get(url)
            response.raise_for_status()
            
            data = response.json().get("data", {})
            # Handle KV version 2 vs version 1 difference if needed
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return data
        except httpx.RequestError as e:
            raise VaultUnavailableError(f"Failed to fetch secret at {path}: {e}")
        except httpx.HTTPStatusError as e:
            raise VaultUnavailableError(f"Failed to fetch secret at {path}, status {e.response.status_code}")

    async def close(self):
        """Closes the underlying HTTP client if it was created internally."""
        if not self._external_client and self.client:
            await self.client.aclose()
