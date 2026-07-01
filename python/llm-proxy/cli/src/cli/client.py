"""
HTTP client for the LLM Proxy admin REST API.

Wraps ``httpx.AsyncClient`` with bearer-token auth, error handling, and
convenience methods for every admin endpoint.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from cli.config import get

# ====================================================================================================
# Constants
# ====================================================================================================

TIMEOUT_SECONDS : float = 15.0


# ====================================================================================================
# Client
# ====================================================================================================


class AdminClient:
    """
    A lightweight HTTP client for the LLM Proxy admin API.

    Reads ``proxy_url`` and ``admin_key`` from local config by default,
    but both can be overridden for one-off calls.
    """

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        admin_key: Optional[str] = None,
    ) -> None:
        """
        Args:
            proxy_url: Base URL of the proxy (e.g. ``http://localhost:8000``).
                       Falls back to config value.
            admin_key: Bearer token for admin endpoints. Falls back to config
                       value.
        """
        self._base_url  : str = (proxy_url or get("proxy_url")).rstrip("/")
        self._admin_key : str = admin_key or get("admin_key", "")

        headers = {"Authorization": f"Bearer {self._admin_key}"} if self._admin_key else {}
        self._client = httpx.Client(base_url=self._base_url, headers=headers, timeout=TIMEOUT_SECONDS)

    # ------------------------------------------------------------------
    # Provider Keys
    # ------------------------------------------------------------------

    def provider_add(
        self,
        provider: str,
        api_key: str,
        *,
        owner_label: str = "default",
        priority: int = 0,
    ) -> Dict[str, Any]:
        """
        Register a new provider API key.

        Args:
            provider: Provider name (openai, anthropic, google).
            api_key: The raw API key value.
            owner_label: Human-readable owner label.
            priority: Key priority (higher = preferred).

        Returns:
            The created key metadata.
        """
        r = self._client.post("/admin/provider-keys", json={
            "owner_label": owner_label,
            "provider": provider,
            "api_key": api_key,
            "priority": priority,
        })
        r.raise_for_status()
        return r.json()

    def provider_list(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List registered provider keys.

        Args:
            provider: Optional filter by provider name.

        Returns:
            List of provider key metadata.
        """
        params = {"provider": provider} if provider else {}
        r = self._client.get("/admin/provider-keys", params=params)
        r.raise_for_status()
        return r.json()

    def provider_toggle(self, key_id: str) -> Dict[str, Any]:
        """
        Toggle the active/inactive status of a provider key.

        Args:
            key_id: Provider key UUID.

        Returns:
            Confirmation with new active state.
        """
        r = self._client.patch(f"/admin/provider-keys/{key_id}/toggle")
        r.raise_for_status()
        return r.json()

    def provider_remove(self, key_id: str) -> None:
        """
        Delete a provider key.

        Args:
            key_id: Provider key UUID.
        """
        r = self._client.delete(f"/admin/provider-keys/{key_id}")
        r.raise_for_status()

    # ------------------------------------------------------------------
    # Access Tokens
    # ------------------------------------------------------------------

    def token_create(
        self,
        label: str,
        owner: str,
        *,
        budget_type: str = "fixed",
        token_budget: Optional[int] = None,
        valid_until: Optional[datetime] = None,
        allowed_models: Optional[List[str]] = None,
        refresh_period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new access token.

        Args:
            label: Human-readable label.
            owner: Owner identifier.
            budget_type: ``fixed``, ``time_based``, or ``unlimited``.
            token_budget: Max tokens (None = unlimited budget).
            valid_until: Optional expiry datetime.
            allowed_models: List of allowed abstractions ([] = all).
            refresh_period: ``daily`` | ``weekly`` | ``monthly``.

        Returns:
            Token metadata including the **raw token** (shown once).
        """
        body: Dict[str, Any] = {
            "label": label,
            "owner": owner,
            "budget_type": budget_type,
            "token_budget": token_budget,
            "allowed_models": allowed_models or [],
        }
        if valid_until:
            body["valid_until"] = valid_until.isoformat()
        if refresh_period:
            body["refresh_period"] = refresh_period

        r = self._client.post("/admin/tokens", json=body)
        r.raise_for_status()
        return r.json()

    def token_list(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List access tokens.

        Args:
            owner: Optional owner filter.

        Returns:
            List of token metadata.
        """
        params = {"owner": owner} if owner else {}
        r = self._client.get("/admin/tokens", params=params)
        r.raise_for_status()
        return r.json()

    def token_get(self, token_id: str) -> Dict[str, Any]:
        """
        Retrieve a single access token by ID.

        Args:
            token_id: Token UUID.

        Returns:
            Token metadata.
        """
        r = self._client.get(f"/admin/tokens/{token_id}")
        r.raise_for_status()
        return r.json()

    def token_revoke(self, token_id: str) -> Dict[str, Any]:
        """
        Revoke an access token.

        Args:
            token_id: Token UUID.

        Returns:
            Confirmation message.
        """
        r = self._client.patch(f"/admin/tokens/{token_id}/revoke")
        r.raise_for_status()
        return r.json()

    def token_budget(self, token_id: str, token_budget: int) -> Dict[str, Any]:
        """
        Update the token budget (and reactivate if exhausted).

        Args:
            token_id: Token UUID.
            token_budget: New budget value (must be positive).

        Returns:
            Confirmation with new budget.
        """
        r = self._client.patch(f"/admin/tokens/{token_id}/budget", params={"token_budget": token_budget})
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Model Mappings
    # ------------------------------------------------------------------

    def mapping_add(
        self,
        abstraction: str,
        provider: str,
        model_name: str,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """
        Create a new abstraction-to-model mapping.

        Args:
            abstraction: Virtual model name (coding, chat, reasoning, …).
            provider: Provider name (openai, anthropic, …).
            model_name: Real model identifier (gpt-4o, claude-3-5-sonnet, …).
            priority: Mapping priority (higher = tried first).

        Returns:
            The created mapping metadata.
        """
        r = self._client.post("/admin/model-mappings", json={
            "abstraction": abstraction,
            "provider": provider,
            "model_name": model_name,
            "priority": priority,
        })
        r.raise_for_status()
        return r.json()

    def mapping_list(self) -> List[Dict[str, Any]]:
        """
        List all model mappings.

        Returns:
            List of mapping metadata.
        """
        r = self._client.get("/admin/model-mappings")
        r.raise_for_status()
        return r.json()

    def mapping_toggle(self, mapping_id: str) -> Dict[str, Any]:
        """
        Toggle the active/inactive status of a mapping.

        Args:
            mapping_id: Mapping UUID.

        Returns:
            Confirmation with new active state.
        """
        r = self._client.patch(f"/admin/model-mappings/{mapping_id}/toggle")
        r.raise_for_status()
        return r.json()

    def mapping_remove(self, mapping_id: str) -> None:
        """
        Delete a model mapping.

        Args:
            mapping_id: Mapping UUID.
        """
        r = self._client.delete(f"/admin/model-mappings/{mapping_id}")
        r.raise_for_status()

    # ------------------------------------------------------------------
    # Usage & Stats
    # ------------------------------------------------------------------

    def usage(
        self,
        *,
        token_id: Optional[str] = None,
        provider: Optional[str] = None,
        abstraction: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Query the usage / audit log.

        Args:
            token_id: Optional access token filter.
            provider: Optional provider filter.
            abstraction: Optional abstraction filter.
            limit: Max entries to return (max 500).

        Returns:
            List of usage log entries.
        """
        params: Dict[str, Any] = {"limit": limit}
        if token_id:
            params["token_id"] = token_id
        if provider:
            params["provider"] = provider
        if abstraction:
            params["abstraction"] = abstraction
        r = self._client.get("/admin/usage", params=params)
        r.raise_for_status()
        return r.json()

    def stats(self) -> Dict[str, Any]:
        """
        Aggregate token usage per abstraction and provider.

        Returns:
            Stats dict.
        """
        r = self._client.get("/admin/usage/stats")
        r.raise_for_status()
        return r.json()
