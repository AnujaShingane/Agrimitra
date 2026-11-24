# Market Data Policy — Static vs Live

AgriMitra intentionally separates stable agricultural market knowledge from changing market facts.

## Static local RAG

`backend/data/docs/market_data.txt` is for concepts such as:

- mandi and APMC concepts
- MSP concepts
- price discovery
- supply and demand
- seasonality
- storage
- FPOs
- e-NAM concepts
- grading and market charges
- general market mechanics

These documents are background knowledge, not a live market feed.

## Live web retrieval

Questions asking for changing information force web retrieval, including:

- today's/latest/current mandi prices
- current commodity prices
- current MSP announcements or values
- today's agricultural news
- current arrivals and procurement status
- current export/import developments
- recent government market announcements
- current scheme deadlines or availability
- current weather/forecast and recent advisories

When `OPENAI_API_KEY` is configured, OpenAI's built-in `web_search` tool is used first. DuckDuckGo remains a fallback.

## Safety rule

The synthesis model must never convert a historical/static figure into a current fact. If current web evidence is unavailable or contradictory, the answer should clearly state that current information could not be verified.
