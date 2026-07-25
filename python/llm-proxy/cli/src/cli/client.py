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
        credit_model: str,
        budget_amount: int,
    ) -> Dict[str, Any]:
        """
        Register a new provider API key with budget configuration.

        Args:
            provider: Provider name (openai, anthropic, google).
            api_key: The raw API key value.
            owner_label: Human-readable owner label.
            priority: Key priority (higher = preferred).
            budget_type: Credit type: "one_time" or "monthly".
            budget_amount: Credit amount for this provider.

        Returns:
            The created provider metadata.
        """
        r = self._client.post("/admin/provider-keys", json={
            "owner_label": owner_label,
            "provider": provider,
            "api_key": api_key,
            "priority": priority,
            "credit_model": credit_model,
            "budget_amount": budget_amount,
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

    def provider_budget(
        self,
        provider_id: str,
        *,
        budget_amount: Optional[int] = None,
        credit_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update provider budget configuration (amount or type).

        Args:
            provider_id: Provider UUID.
            budget_amount: New budget amount (optional).
            budget_type: New budget type ("one_time" or "monthly") (optional).

        Returns:
            Updated provider metadata.
        """
        if budget_amount is None and credit_model is None:
            raise ValueError("Either budget_amount or credit_model must be provided")
        params: Dict[str, Any] = {}
        if budget_amount is not None:
            params["budget_amount"] = budget_amount
        if credit_model is not None:
            params["credit_model"] = credit_model
        r = self._client.patch(f"/admin/provider-keys/{provider_id}/budget", params=params)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Wallets (formerly access tokens)
    # ------------------------------------------------------------------

    def wallet_create(
        self,
        label: str,
        owner: str,
        *,
        valid_until: Optional[datetime] = None,
        allowed_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new wallet.

        Args:
            label: Human-readable label.
            owner: Owner identifier.
            valid_until: Optional expiry datetime.
            allowed_models: List of allowed abstractions ([] = all).

        Returns:
            Wallet metadata.
        """
        body: Dict[str, Any] = {
            "label": label,
            "owner": owner,
            "allowed_models": allowed_models or [],
        }
        if valid_until:
            body["valid_until"] = valid_until.isoformat()
        r = self._client.post("/admin/wallets", json=body)
        r.raise_for_status()
        return r.json()

    def wallet_list(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List wallets.

        Args:
            owner: Optional owner filter.

        Returns:
            List of wallet metadata.
        """
        params = {"owner": owner} if owner else {}
        r = self._client.get("/admin/wallets", params=params)
        r.raise_for_status()
        return r.json()

    def wallet_get(self, wallet_id: str) -> Dict[str, Any]:
        """
        Retrieve a single wallet by ID.

        Args:
            wallet_id: Wallet UUID.

        Returns:
            Wallet metadata.
        """
        r = self._client.get(f"/admin/wallets/{wallet_id}")
        r.raise_for_status()
        return r.json()

    def wallet_revoke(self, wallet_id: str) -> Dict[str, Any]:
        """
        Revoke a wallet.

        Args:
            wallet_id: Wallet UUID.

        Returns:
            Confirmation message.
        """
        r = self._client.patch(f"/admin/wallets/{wallet_id}/revoke")
        r.raise_for_status()
        return r.json()

    def wallet_add_provider(
        self,
        wallet_id: str,
        *,
        provider_id: str,
        credit_amount: int,
    ) -> Dict[str, Any]:
        """
        Link a provider to wallet and transfer credit.

        Args:
            wallet_id: Wallet UUID.
            provider_id: Provider UUID.
            credit_amount: Amount of credit to transfer from provider to wallet.

        Returns:
            Result of the operation.
        """
        r = self._client.post(
            f"/admin/wallets/{wallet_id}/providers",
            json={"provider_id": provider_id, "credit_amount": credit_amount},
        )
        r.raise_for_status()
        return r.json()

    def wallet_remove_provider(
        self,
        wallet_id: str,
        *,
        provider_id: str,
    ) -> None:
        """
        Unlink a provider from wallet (does not refund credit).

        Args:
            wallet_id: Wallet UUID.
            provider_id: Provider UUID.
        """
        r = self._client.delete(
            f"/admin/wallets/{wallet_id}/providers/{provider_id}"
        )
        r.raise_for_status()

    def wallet_list_providers(self, wallet_id: str) -> List[Dict[str, Any]]:
        """
        List providers linked to a wallet.

        Args:
            wallet_id: Wallet UUID.

        Returns:
            List of provider-link metadata.
        """
        r = self._client.get(f"/admin/wallets/{wallet_id}/providers")
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
        wallet_id: Optional[str] = None,
        provider: Optional[str] = None,
        abstraction: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Query the usage / audit log.

        Args:
            wallet_id: Optional wallet filter.
            provider: Optional provider filter.
            abstraction: Optional abstraction filter.
            limit: Max entries to return (max 500).

        Returns:
            List of usage log entries.
        """
        params: Dict[str, Any] = {"limit": limit}
        if wallet_id:
            params["wallet_id"] = wallet_id
        if provider:
            params["provider"] = provider
        if abstraction:
            params["abstraction"] = abstraction
        r = self._client.get("/admin/usage", params=params)
        r.raise_for_status()
        return r.json()

    def stats(self) -> Dict[str, Any]:
        """
        Aggregate wallet usage per abstraction and provider.

        Returns:
            Stats dict.
        """
        r = self._client.get("/admin/usage/stats")
        r.raise_for_status()
        return r.json()
