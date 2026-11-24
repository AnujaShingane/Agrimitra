# AgriMitra AI — Hybrid Web-First Architecture

## Goal

AgriMitra separates stable agricultural knowledge from information that changes over time.

- Stable/general questions use the local FAISS knowledge base.
- Current/live questions force fresh web retrieval.
- OpenAI's built-in `web_search` is preferred when `OPENAI_API_KEY` is configured.
- DuckDuckGo is retained as a fallback web-search provider.
- Groq remains the default answer-generation LLM so the existing application is not unnecessarily migrated.
- The leaf scanner and other specialized capabilities remain separate from the general RAG flow.

## Request flow

```text
Farmer Question
      |
      v
 Query / Agent Router
      |
      +-----------------------------+
      |                             |
      | current / live?             | stable knowledge?
      v                             v
 Live Web Search                FAISS / RAG
 (OpenAI preferred)                 |
      |                             |
      +--------------+--------------+
                     v
              Evidence Evaluation
                     |
                     v
               LLM Synthesis
                     |
                     v
              Reflection / QC
                     |
                     v
             Answer + Sources
```

## Current/live examples

Examples that should force web retrieval include:

- today / today's
- current / currently / right now
- latest / recent / this week
- live / real time
- news / headlines / announcement
- current prices / mandi prices / market prices
- current MSP / latest MSP
- weather forecast / tomorrow
- current scheme availability / deadline / last date
- recent crop advisory / outbreak

The detector is intentionally conservative: a question is sent to web search when it explicitly asks for changing information. Stable educational questions do not need a web call.

## Market data rule

`backend/data/docs/market_data.txt` contains stable concepts only. It must not be treated as a source for today's prices, today's news, current MSP values, current arrivals, or other changing market facts.

## Web source priority

When OpenAI web search is configured, AgriMitra uses the Responses API `web_search` tool and passes the resulting evidence and URLs into the synthesis stage. If OpenAI web search is unavailable, the system falls back to DuckDuckGo.

## Environment variables

See `backend/.env.example`.

Never commit real API keys. Use a local `.env` file or deployment secret store.
