"""Shared client for official live AGMARKNET mandi-price data."""

import os
from typing import Any

import httpx


class LiveMarketDataUnavailable(RuntimeError):
    """Raised when verified live mandi data cannot be returned."""


async def fetch_live_market_data(limit: int = 100) -> list[dict[str, Any]]:
    """Fetch and normalize official data.gov.in AGMARKNET records."""
    api_key = os.getenv("DATAGOV_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise LiveMarketDataUnavailable("DATAGOV_API_KEY is not configured.")

    resource_id = os.getenv("DATAGOV_MARKET_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070")
    url = f"https://api.data.gov.in/resource/{resource_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params={"api-key": api_key, "format": "json", "limit": limit},
                headers={"Accept": "application/json", "User-Agent": "AgriMitra/2.0"},
            )
        response.raise_for_status()
        records = response.json().get("records", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise LiveMarketDataUnavailable("The official AGMARKNET provider is temporarily unavailable.") from exc

    results = []
    for record in records:
        min_price, max_price, modal_price = (record.get("min_price"), record.get("max_price"), record.get("modal_price"))
        if min_price is None and max_price is None and modal_price is None:
            continue
        results.append({
            "crop": str(record.get("commodity") or "Unknown").title(), "market": record.get("market") or "Unknown",
            "state": record.get("state") or "Unknown", "district": record.get("district") or "Unknown",
            "variety": record.get("variety") or "Unknown", "minPrice": min_price, "maxPrice": max_price,
            "modalPrice": modal_price, "arrivalDate": record.get("arrival_date") or "Unknown",
            "unit": "per Quintal", "source": "data.gov.in / AGMARKNET", "isLive": True,
        })

    if not results:
        raise LiveMarketDataUnavailable("AGMARKNET returned no usable live mandi records.")
    return results
