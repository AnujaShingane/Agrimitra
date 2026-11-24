import pytest

import multi_rag


@pytest.mark.asyncio
async def test_current_market_query_uses_official_structured_records(monkeypatch):
    async def fake_fetch():
        return [{
            "crop": "Paddy", "market": "Pune", "state": "Maharashtra",
            "district": "Pune", "variety": "Common", "minPrice": "2000",
            "maxPrice": "2200", "modalPrice": "2100", "arrivalDate": "2026-09-17",
            "unit": "per Quintal", "source": "data.gov.in / AGMARKNET", "isLive": True,
        }]

    monkeypatch.setattr(multi_rag, "fetch_live_market_data", fake_fetch)
    result = await multi_rag.web_search_node({
        "original_query": "today live mandi prices for paddy in Pune",
        "query": "today live mandi prices for paddy in Pune",
        "agents_used": ["market_analyst"],
        "sources": [],
    })

    assert result["sources"] == ["data.gov.in / AGMARKNET"]
    assert "Paddy" in result["web_context"]
    assert "2100" in result["web_context"]
