# AgriMitra Change Log

## 2026-09-17 — Stability and contract repair

### Chat live-market integration

- **Problem:** The chat market route used static RAG/web links instead of the official live mandi data service.
- **Root cause:** The LangGraph corrective-search node had no AGMARKNET tool path.
- **Solution:** Current market queries now call the official AGMARKNET client, compact the structured records for grounded synthesis, and explicitly decline to provide current prices if the provider is unavailable.
- **Files changed:** `backend/market_service.py`, `backend/multi_rag.py`, `backend/tests/test_live_market_routing.py`.
- **Test performed:** Unit test with a mocked official response.
- **Result:** The market workflow is grounded in official structured records rather than third-party links.
- **Interview explanation:** Deterministic tools should supply live facts; the LLM formats and explains verified records.

### Live-data integrity

- **Problem:** Weather returned fixed temperatures, forecasts, and crop suggestions when OpenWeatherMap was unavailable.
- **Root cause:** A presentation fallback was used as if it were current provider data.
- **Solution:** The endpoint now returns `503` when the live provider is unavailable; when weather data is real but Groq is unavailable, it preserves the provider data and labels the advisory limitation.
- **Files changed:** `backend/main.py`, `frontend/src/components/Weather.jsx`.
- **Test performed:** Frontend production build; endpoint behavior reviewed against provider-error paths.
- **Result:** The application no longer represents fabricated weather values as live information. A market smoke test also returned a clear `503` when the live provider could not be reached.
- **Interview explanation:** Real-time facts must remain provider-backed; AI can explain a verified payload but must not replace it.

### Frontend error contracts

- **Problem:** Market, schemes, and weather screens parsed non-2xx JSON as successful data, producing broken render paths.
- **Root cause:** Fetch calls did not check `response.ok`.
- **Solution:** Each screen now converts failed responses into an error state before rendering data.
- **Files changed:** `frontend/src/components/Market.jsx`, `Schemes.jsx`, `Weather.jsx`.
- **Test performed:** `npm run build`.
- **Result:** API failures are visible and safe instead of causing data-shape errors.
- **Interview explanation:** HTTP success and valid JSON are separate concerns; clients must check both the status and the payload contract.

### Leaf scanner safety

- **Problem:** Failed analysis displayed a fabricated “Analysis Unavailable” result as a disease report; client validation was missing.
- **Root cause:** The error handler created a mock analysis object.
- **Solution:** Validate type and size before upload, preserve a genuine backend failure as an alert, and remove artificial delays.
- **Files changed:** `frontend/src/components/Scanner.jsx`.
- **Test performed:** Frontend lint/build.
- **Result:** No false diagnostic is displayed after a failed scan.
- **Interview explanation:** In agriculture, an explicit failure is safer than an invented inference.

### Configuration and maintainability

- **Problem:** No safe configuration template or root runbook existed; generated environments were not excluded.
- **Root cause:** Deployment configuration was implicit.
- **Solution:** Added `.env.example`, `.gitignore`, and README documentation; standardized language-code validation and translation cache keys.
- **Files changed:** `.env.example`, `.gitignore`, `README.md`, `backend/main.py`, `frontend/vite.config.js`.
- **Test performed:** Backend targeted pytest suite and frontend build.
- **Result:** Local setup, secrets handling, and API behavior are documented and repeatable.
- **Interview explanation:** Configuration must be explicit, secret-free, and consistent across frontend and backend.
