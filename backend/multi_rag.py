# multi_rag.py
"""LangGraph CRAG Engine for AgriMitra AI.

Implements a Corrective RAG (CRAG) pipeline using LangGraph StateGraph:
  1. Route   — keyword-match the query to 1-2 specialized agents
  2. Retrieve — FAISS candidate retrieval + agent/source-focused reranking
  3. Evaluate — per-document LLM relevance filtering
  4. Conditional — if evidence is insufficient → web search
  5. Synthesize — LLM answers only the exact question from filtered evidence
  6. Reflect  — LLM rewrites weak/off-topic answers

Conversation memory is persisted per session via a local SQLite checkpointer.
The database is runtime state and is created outside the source data corpus.
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, AsyncGenerator, TypedDict

from dotenv import load_dotenv
from market_service import LiveMarketDataUnavailable, fetch_live_market_data
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import structlog
import time

load_dotenv()

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# AgriState — Typed state flowing through the LangGraph
# ---------------------------------------------------------------------------
class AgriState(TypedDict):
    query: str
    original_query: str
    retrieved_docs: List[Dict]
    retrieval_score: float
    needs_web_search: bool
    force_web_search: bool
    answer: str
    conversation_history: List[Dict]

    # Operational fields used internally by nodes
    agents_used: List[str]
    sources: List[str]
    web_context: str
    language: str
    answer_quality: str
    quality_note: str
    market_data_status: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FAISS_INDEX_PATH = Path(__file__).parent / "faiss_index"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
CROSS_ENCODER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

LLM_AVAILABLE = False
LLM = None
EMBEDDINGS = None
VECTORDB = None
CROSS_ENCODER = None


def _init_components():
    """Lazy initialization of LLM, embeddings, and vector store."""
    global LLM_AVAILABLE, LLM, EMBEDDINGS, VECTORDB, CROSS_ENCODER

    if EMBEDDINGS is not None:
        return

    try:
        import gc
        import torch

        torch.set_num_threads(1)
        torch.set_grad_enabled(False)

        from langchain_huggingface import HuggingFaceEmbeddings

        EMBEDDINGS = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
        )

        logger.info(f"Loaded embedding model: {EMBEDDING_MODEL_NAME}")
        gc.collect()

    except Exception as e:
        logger.error(f"Failed to load embeddings: {e}")
        return

    use_cross_encoder = (
        os.getenv("USE_CROSS_ENCODER", "false").lower()
        in {"1", "true", "yes"}
    )

    if CROSS_ENCODER is None and use_cross_encoder:
        try:
            from sentence_transformers import CrossEncoder

            CROSS_ENCODER = CrossEncoder(
                CROSS_ENCODER_MODEL_NAME,
                device="cpu",
            )

            logger.info(
                f"Loaded CrossEncoder model: {CROSS_ENCODER_MODEL_NAME}"
            )

        except Exception as e:
            logger.warning(
                f"CrossEncoder unavailable; continuing without it: {e}"
            )

    # Load FAISS index
    if FAISS_INDEX_PATH.exists():
        try:
            from langchain_community.vectorstores import FAISS

            VECTORDB = FAISS.load_local(
                str(FAISS_INDEX_PATH),
                EMBEDDINGS,
                allow_dangerous_deserialization=True,
            )

            logger.info(
                f"Loaded FAISS index from {FAISS_INDEX_PATH}"
            )

        except Exception as e:
            logger.error(f"Failed to load FAISS index: {e}")

    else:
        logger.warning(
            f"FAISS index not found at {FAISS_INDEX_PATH}. "
            f"Run ingest.py first."
        )

    # Try Groq LLM
    api_key = os.getenv("GROQ_API_KEY")

    if api_key:
        try:
            from langchain_groq import ChatGroq

            LLM = ChatGroq(
                model_name=os.getenv(
                    "GROQ_MODEL",
                    "llama-3.3-70b-versatile",
                ),
                groq_api_key=api_key,
                temperature=0.3,
            )

            LLM_AVAILABLE = True

            logger.info("Groq LLM initialized successfully")

        except Exception as e:
            logger.warning(
                f"Failed to initialize Groq LLM: {e}"
            )

    else:
        logger.warning(
            "GROQ_API_KEY not set. "
            "LLM features will use fallback mode."
        )


# ---------------------------------------------------------------------------
# Agent Definitions
# ---------------------------------------------------------------------------
from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Configuration for a single RAG agent."""

    id: str
    name: str
    emoji: str
    description: str
    keywords: List[str]
    retrieval_k: int = 4


AGENTS: Dict[str, AgentConfig] = {

    "crop_advisor": AgentConfig(
        id="crop_advisor",
        name="Crop Advisor",
        emoji="🌾",
        description=(
            "Expert in crop diseases, pest management, "
            "chemical & organic remedies, and cultivation best practices"
        ),
        keywords=[
            "crop", "disease", "pest", "fungus", "virus", "bacteria",
            "blast", "bollworm", "armyworm", "leaf", "wilt", "blight",
            "rot", "spray", "fungicide", "pesticide", "insecticide",
            "remedy", "organic", "chemical", "treatment", "symptom",
            "paddy", "rice", "cotton", "maize", "groundnut", "chilli",
            "wheat", "soybean", "cultivation", "sowing", "harvest",
            "fertilizer", "nitrogen", "phosphorus", "potassium",
            "urea", "DAP", "NPK", "seed", "variety", "hybrid",
            "yield", "irrigation", "plant", "farming",
        ],
        retrieval_k=5,
    ),

    "market_analyst": AgentConfig(
        id="market_analyst",
        name="Market Analyst",
        emoji="📊",
        description=(
            "Specialist in MSP rates, mandi prices, market trends, "
            "demand forecasts, storage, and export data"
        ),
        keywords=[
            "market", "price", "msp", "mandi", "rate", "cost", "sell",
            "buy", "demand", "supply", "export", "import", "trade",
            "quintal", "ton", "rupee", "₹", "storage", "warehouse",
            "cold storage", "apmc", "e-nam", "procurement", "profit",
            "income", "revenue", "value", "premium", "grade", "today",
            "live",
        ],
        retrieval_k=4,
    ),

    "schemes_expert": AgentConfig(
        id="schemes_expert",
        name="Schemes Expert",
        emoji="🏛️",
        description=(
            "Authority on government agricultural schemes, "
            "subsidies, eligibility criteria, and application processes"
        ),
        keywords=[
            "scheme", "subsidy", "government", "pm-kisan", "kisan",
            "pmfby", "insurance", "loan", "credit", "kcc", "rythu",
            "bharosa", "bandhu", "benefit", "eligibility", "apply",
            "application", "registration", "dbt", "transfer", "support",
            "assistance", "grant", "policy", "niti", "mission", "yojana",
            "pradhan", "mantri", "soil health", "micro irrigation",
            "horticulture",
        ],
        retrieval_k=4,
    ),

    "weather_analyst": AgentConfig(
        id="weather_analyst",
        name="Weather Analyst",
        emoji="🌦️",
        description=(
            "Expert on seasonal weather patterns, climate risks, "
            "monsoon forecasts, and agricultural weather advisories"
        ),
        keywords=[
            "weather", "rain", "rainfall", "monsoon", "temperature",
            "heat", "cold", "frost", "hail", "cyclone", "flood",
            "drought", "season", "kharif", "rabi", "zaid", "summer",
            "winter", "climate", "wind", "humidity", "forecast",
            "advisory", "risk", "hazard", "storm", "warning",
            "today", "tomorrow",
        ],
        retrieval_k=4,
    ),

    "leaf_scanner": AgentConfig(
        id="leaf_scanner",
        name="Leaf Scanner",
        emoji="🔬",
        description=(
            "Identifies plant diseases from symptom descriptions "
            "and provides targeted treatment recommendations"
        ),
        keywords=[
            "scan", "identify", "leaf", "spot", "curl", "yellow",
            "brown", "wilt", "deform", "hole", "damage", "image",
            "photo", "upload", "diagnose", "detection", "analysis",
            "appearance", "color", "shape", "pattern", "lesion",
        ],
        retrieval_k=5,
    ),
}


# ---------------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------------
SOURCE_AGENT_HINTS = {
    "government_schemes": "schemes_expert",
    "scheme": "schemes_expert",
    "weather_advisory": "weather_analyst",
    "weather": "weather_analyst",
    "market_data": "market_analyst",
    "market": "market_analyst",
    "price": "market_analyst",
    "crop": "crop_advisor",
    "cultivation": "crop_advisor",
    "fertilizer": "crop_advisor",
    "disease": "leaf_scanner",
    "leaf": "leaf_scanner",
    "pest": "crop_advisor",
}


def _tokenize(text: str) -> set[str]:
    """Small dependency-free tokenizer used for local relevance scoring."""
    import re

    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "what",
        "which", "who", "how", "why", "when", "where", "can",
        "could", "should", "would", "for", "to", "of", "in",
        "on", "and", "or", "with", "me", "my", "i", "we", "our",
        "about", "tell", "give", "please", "do", "does", "this",
        "that", "from", "be",
    }

    words = re.findall(
        r"[a-zA-Z][a-zA-Z0-9-]{1,}",
        text.lower(),
    )

    return {
        w for w in words
        if w not in stop_words
    }


def _source_name(source: str) -> str:
    return Path(source).name.lower() if source else "unknown"


def _source_agent(source: str) -> Optional[str]:
    """Infer a preferred agent from a document filename."""
    name = _source_name(source)

    for hint, agent_id in SOURCE_AGENT_HINTS.items():
        if hint in name:
            return agent_id

    return None


def _agent_source_match(agent_id: str, source: str) -> float:
    """Return a source-specific boost used to keep retrieval focused."""
    mapped = _source_agent(source)

    if mapped == agent_id:
        return 1.0

    if mapped is None:
        return 0.25

    return 0.0


def _local_relevance(
    agent_id: str,
    query: str,
    content: str,
    source: str,
) -> float:
    """Cheap local relevance score used when reranking FAISS results."""

    q_tokens = _tokenize(query)
    d_tokens = _tokenize(content)

    if not q_tokens or not d_tokens:
        overlap = 0.0
    else:
        overlap = len(q_tokens & d_tokens) / max(1, len(q_tokens))

    config = AGENTS[agent_id]

    keyword_hits = sum(
        1
        for kw in config.keywords
        if kw.lower() in query.lower()
    )

    keyword_strength = min(keyword_hits / 4.0, 1.0)
    source_match = _agent_source_match(agent_id, source)

    return (
        (0.55 * overlap)
        + (0.20 * keyword_strength)
        + (0.25 * source_match)
    )


# ---------------------------------------------------------------------------
# Conversation helper
# ---------------------------------------------------------------------------
def _build_contextual_query(
    query: str,
    history: List[Dict],
) -> str:
    """Add recent conversation context so follow-up queries
    can be routed/retrieved correctly.
    """

    if not history:
        return query

    recent = history[-4:]

    history_text = "\n".join(
        f"User: {turn.get('user', '')}\n"
        f"Assistant: {turn.get('assistant', '')[:800]}"
        for turn in recent
    )

    return (
        f"Previous conversation:\n"
        f"{history_text}\n\n"
        f"Current user question:\n"
        f"{query}"
    )


# ---------------------------------------------------------------------------
# Core Logic
# ---------------------------------------------------------------------------
def _is_time_sensitive_query(query: str) -> bool:
    """Return True when the user explicitly asks for information that can change over time.

    Time-sensitive queries must use fresh web retrieval even when the local RAG
    documents appear relevant. Static documents are retained for background
    explanations, but are never sufficient evidence for live prices, news,
    weather, current policies, or other changing facts.
    """
    q = query.lower()
    live_markers = [
        "today", "todays", "today's", "right now", "now", "currently",
        "current", "latest", "recent", "this week", "this month",
        "live", "real time", "realtime", "news", "headline", "headlines",
        "price today", "today's price", "current price", "mandi price",
        "market price", "current msp", "latest msp", "latest update",
        "latest updates", "what happened", "breaking",
        "forecast", "tomorrow", "this week", "deadline", "last date",
        "available now", "apply now", "new scheme", "new policy",
        "announcement", "announced", "outbreak", "advisory",
    ]
    return any(marker in q for marker in live_markers)


def route_query(query: str) -> List[str]:
    """Route a query to the most relevant 1-2 agents."""

    query_lower = query.lower()
    scores: Dict[str, float] = {}

    for agent_id, config in AGENTS.items():

        score = 0.0

        for kw in config.keywords:

            kw_lower = kw.lower()

            if kw_lower in query_lower:

                score += (
                    2.0
                    if " " in kw_lower
                    else 1.0
                )

        if score > 0:
            scores[agent_id] = score

    if not scores:
        return ["crop_advisor"]

    sorted_agents = sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    top_agents = [
        agent_id
        for agent_id, _score in sorted_agents[:2]
    ]

    logger.info(
        "Routed query",
        agents=top_agents,
        scores=scores,
    )

    return top_agents


def agent_retrieve(
    agent_id: str,
    query: str,
) -> List[Dict]:
    """Retrieve and rerank chunks for one routed agent."""

    _init_components()

    config = AGENTS[agent_id]
    results: List[Dict] = []

    if VECTORDB is None:
        return results

    candidate_k = int(
        os.getenv(
            "MAX_RETRIEVAL_CANDIDATES",
            "25",
        )
    )

    use_cross_encoder = (
        os.getenv(
            "USE_CROSS_ENCODER",
            "false",
        ).lower()
        in {"1", "true", "yes"}
    )

    try:

        docs = VECTORDB.similarity_search(
            query,
            k=candidate_k,
        )

        if not docs:
            return results

        semantic_scores = {
            id(doc): 0.0
            for doc in docs
        }

        if (
            use_cross_encoder
            and CROSS_ENCODER is not None
        ):

            pairs = [
                [query, doc.page_content]
                for doc in docs
            ]

            ce_scores = CROSS_ENCODER.predict(pairs)

            for doc, score in zip(
                docs,
                ce_scores,
            ):
                semantic_scores[id(doc)] = float(score)

        scored = []

        for rank, doc in enumerate(docs):

            source = doc.metadata.get(
                "source",
                "unknown",
            )

            local_score = _local_relevance(
                agent_id,
                query,
                doc.page_content,
                source,
            )

            rank_score = (
                1.0
                - (
                    rank
                    / max(
                        1,
                        len(docs),
                    )
                )
            )

            ce_score = semantic_scores[id(doc)]

            if (
                use_cross_encoder
                and CROSS_ENCODER is not None
            ):

                ce_norm = (
                    1.0
                    / (
                        1.0
                        + pow(
                            2.71828,
                            -ce_score,
                        )
                    )
                )

                semantic_component = ce_norm

            else:
                semantic_component = rank_score

            final_score = (
                0.55 * semantic_component
                + 0.45 * local_score
            )

            scored.append(
                (
                    final_score,
                    doc,
                )
            )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        min_score = float(
            os.getenv(
                "MIN_LOCAL_RETRIEVAL_SCORE",
                "0.34",
            )
        )

        seen = set()

        for score, doc in scored:

            if len(results) >= config.retrieval_k:
                break

            content = doc.page_content.strip()

            if not content:
                continue

            content_key = (
                content[:300].lower()
            )

            if content_key in seen:
                continue

            if score < min_score and results:
                continue

            seen.add(content_key)

            results.append(
                {
                    "content": content,
                    "source": doc.metadata.get(
                        "source",
                        "unknown",
                    ),
                    "agent": agent_id,
                    "retrieval_score": round(
                        float(score),
                        4,
                    ),
                }
            )

        logger.info(
            "Agent retrieval complete",
            agent=agent_id,
            candidates=len(docs),
            selected=len(results),
            sources=[
                _source_name(r["source"])
                for r in results
            ],
        )

    except Exception as e:
        logger.error(
            f"Agent {agent_id} retrieval error: {e}"
        )

    return results


def _duckduckgo_web_search(query: str) -> tuple[str, List[str]]:
    """Retrieve live web evidence from DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS

        logger.info(f"Live web search for: {query}")
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=6))

        if not results:
            return "", []

        web_sources: List[str] = []
        web_context = "\n--- 🌐 Live Web Search ---\n"

        for r in results:
            href = r.get("href", "")
            title = r.get("title", "Web result")
            body = r.get("body", "")
            if href and href not in web_sources:
                web_sources.append(href)
            web_context += f"[Source: {title}]\n{body}\nURL: {href}\n\n"

        return web_context, web_sources
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return "", []


def _web_search(query: str) -> tuple[str, List[str]]:
    """Retrieve live web evidence from DuckDuckGo."""
    return _duckduckgo_web_search(query)


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------
def route_node(state: AgriState) -> dict:
    """Node 1: Route using current question
    plus recent conversation context.
    """

    contextual_query = _build_contextual_query(
        state["original_query"],
        state.get(
            "conversation_history",
            [],
        ),
    )

    agents = route_query(
        contextual_query
    )

    force_web_search = _is_time_sensitive_query(
        state["original_query"]
    )

    logger.info(
        f"[route_node] Selected agents: {agents} "
        f"(context-aware query="
        f"{contextual_query[:150]})"
    )

    return {
        "query": contextual_query,
        "agents_used": agents,
        "force_web_search": force_web_search,
    }


def retrieve_node(state: AgriState) -> dict:
    """Node 2: Retrieve relevant documents from FAISS."""

    all_docs: List[Dict] = []
    all_sources: List[str] = []
    seen_content = set()

    for agent_id in state["agents_used"]:

        results = agent_retrieve(
            agent_id,
            state["query"],
        )

        for r in results:

            key = r["content"][:300].lower()

            if key in seen_content:
                continue

            seen_content.add(key)
            all_docs.append(r)

            source = (
                Path(r["source"]).name
                if r["source"] != "unknown"
                else "unknown"
            )

            if source not in all_sources:
                all_sources.append(source)

    max_chunks = int(
        os.getenv(
            "MAX_CONTEXT_CHUNKS",
            "6",
        )
    )

    all_docs = sorted(
        all_docs,
        key=lambda d: float(
            d.get(
                "retrieval_score",
                0.0,
            )
        ),
        reverse=True,
    )[:max_chunks]

    all_sources = []

    for r in all_docs:

        source = (
            Path(r["source"]).name
            if r["source"] != "unknown"
            else "unknown"
        )

        if source not in all_sources:
            all_sources.append(source)

    logger.info(
        "Focused retrieval completed",
        chunks=len(all_docs),
        sources=all_sources,
        agents=state["agents_used"],
    )

    return {
        "retrieved_docs": all_docs,
        "sources": all_sources,
    }


def _parse_json_object(text: str):
    """Parse JSON from an LLM response."""

    content = text.strip()

    if content.startswith("```"):

        parts = content.split(
            "\n",
            1,
        )

        content = (
            parts[1]
            if len(parts) == 2
            else content[3:]
        )

    if content.endswith("```"):
        content = content[:-3]

    return json.loads(
        content.strip()
    )


def _lexical_doc_score(
    query: str,
    content: str,
) -> float:
    """Fallback relevance score when LLM grading fails."""

    q = _tokenize(query)
    d = _tokenize(content)

    if not q:
        return 0.0

    return len(q & d) / len(q)


def evaluate_retrieval_node(
    state: AgriState,
) -> dict:
    """Node 3: filter chunks and grade retrieval."""

    _init_components()

    docs = state["retrieved_docs"]

    if not docs:

        logger.info(
            "[evaluate_retrieval_node] "
            "No docs retrieved → web search"
        )

        return {
            "retrieved_docs": [],
            "retrieval_score": 0.0,
            "needs_web_search": True,
        }

    min_doc_relevance = float(
        os.getenv(
            "MIN_DOC_RELEVANCE",
            "0.45",
        )
    )

    filtered_docs = docs
    overall_score = 0.0

    if LLM_AVAILABLE and LLM is not None:

        numbered = "\n\n".join(
            f"[DOC {i+1}] "
            f"source={Path(d['source']).name}\n"
            f"{d['content'][:900]}"
            for i, d in enumerate(docs)
        )

        grading_prompt = f"""You are a strict retrieval grader for an agricultural assistant.

USER QUESTION:
{state['query']}

CANDIDATE DOCUMENTS:
{numbered}

For EVERY document, score only its usefulness for answering the user's exact question.
Do not reward generic agricultural information that does not help answer the question.

Return ONLY valid JSON in this format:
{{
  "documents": [
    {{"index": 1, "score": 0.0}},
    {{"index": 2, "score": 0.0}}
  ]
}}

Score meaning:
1.0 = directly answers the question
0.8 = strongly useful supporting information
0.5 = somewhat related
0.2 = mostly irrelevant
0.0 = irrelevant
"""

        try:

            start_time = time.time()

            response = LLM.invoke(
                grading_prompt
            )

            latency_ms = int(
                (
                    time.time()
                    - start_time
                )
                * 1000
            )

            logger.info(
                "LLM call completed",
                llm_node="filter_retrieval",
                latency_ms=latency_ms,
            )

            graded = _parse_json_object(
                response.content
            )

            scores = {
                int(item["index"]):
                    float(item["score"])
                for item in graded.get(
                    "documents",
                    [],
                )
                if (
                    "index" in item
                    and "score" in item
                )
            }

            kept = []
            score_values = []

            for idx, doc in enumerate(
                docs,
                start=1,
            ):

                score = max(
                    0.0,
                    min(
                        1.0,
                        scores.get(
                            idx,
                            0.0,
                        ),
                    ),
                )

                doc["llm_relevance"] = round(
                    score,
                    3,
                )

                if score >= min_doc_relevance:

                    kept.append(doc)
                    score_values.append(score)

            filtered_docs = sorted(
                kept,
                key=lambda d: (
                    d.get(
                        "llm_relevance",
                        0.0,
                    ),
                    d.get(
                        "retrieval_score",
                        0.0,
                    ),
                ),
                reverse=True,
            )[
                : int(
                    os.getenv(
                        "MAX_CONTEXT_CHUNKS",
                        "6",
                    )
                )
            ]

            overall_score = (
                max(score_values)
                if score_values
                else 0.0
            )

        except Exception as e:

            logger.warning(
                "[evaluate_retrieval_node] "
                f"Per-document LLM grading failed: {e}; "
                f"using local scoring"
            )

            scored = []

            for doc in docs:

                score = _lexical_doc_score(
                    state["query"],
                    doc["content"],
                )

                doc["llm_relevance"] = round(
                    score,
                    3,
                )

                scored.append(
                    (
                        score,
                        doc,
                    )
                )

            scored.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            filtered_docs = [
                d
                for score, d in scored
                if score >= min_doc_relevance
            ][
                : int(
                    os.getenv(
                        "MAX_CONTEXT_CHUNKS",
                        "6",
                    )
                )
            ]

            overall_score = (
                scored[0][0]
                if scored
                else 0.0
            )

    else:

        scored = []

        for doc in docs:

            score = _lexical_doc_score(
                state["query"],
                doc["content"],
            )

            doc["llm_relevance"] = round(
                score,
                3,
            )

            scored.append(
                (
                    score,
                    doc,
                )
            )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        filtered_docs = [
            d
            for score, d in scored
            if score >= min_doc_relevance
        ][
            : int(
                os.getenv(
                    "MAX_CONTEXT_CHUNKS",
                    "6",
                )
            )
        ]

        overall_score = (
            scored[0][0]
            if scored
            else 0.0
        )

    kept_sources = []

    for doc in filtered_docs:

        source = (
            Path(doc["source"]).name
            if doc["source"] != "unknown"
            else "unknown"
        )

        if source not in kept_sources:
            kept_sources.append(source)

    # CRAG correction is mandatory for time-sensitive queries. A highly
    # relevant static document (for example market_data.txt) must not prevent
    # a live lookup for questions containing "today", "latest", "news", etc.
    needs_search = (
        state.get("force_web_search", False)
        or overall_score < 0.60
        or not filtered_docs
    )

    logger.info(
        "Focused retrieval evaluation",
        original_docs=len(docs),
        kept_docs=len(filtered_docs),
        score=round(
            overall_score,
            3,
        ),
        needs_web_search=needs_search,
        sources=kept_sources,
    )

    return {
        "retrieved_docs": filtered_docs,
        "sources": kept_sources,
        "retrieval_score": round(
            float(overall_score),
            3,
        ),
        "needs_web_search": needs_search,
    }


def _format_live_market_context(query: str, records: List[Dict]) -> str:
    """Keep the official live payload compact and relevant for synthesis."""
    ignored_terms = {"today", "live", "mandi", "market", "price", "prices", "rate", "rates"}
    filters = _tokenize(query) - ignored_terms

    def matches(record: Dict) -> bool:
        if not filters:
            return True
        haystack = " ".join(str(record.get(key, "")).lower() for key in ("crop", "market", "state", "district", "variety"))
        return any(term in haystack for term in filters)

    selected = [record for record in records if matches(record)][:20]
    if not selected:
        return ""
    return (
        "\n--- Official live mandi data (data.gov.in / AGMARKNET) ---\n"
        "Use only these records for current price claims. Prices are per quintal.\n"
        + json.dumps(selected, ensure_ascii=False, indent=2)
        + "\n"
    )


async def web_search_node(
    state: AgriState,
) -> dict:
    """Node 4: use AGMARKNET for current mandi prices, web search otherwise."""

    web_query = state.get("original_query", state["query"])

    if "market_analyst" in state.get("agents_used", []) and _is_time_sensitive_query(web_query):
        try:
            records = await fetch_live_market_data()
            market_context = _format_live_market_context(web_query, records)
            if not market_context:
                logger.info("[web_search_node] No AGMARKNET record matched the market query")
                return {
                    "web_context": "\n--- Official live mandi data ---\nAGMARKNET returned no record matching this crop/location request.\n",
                    "sources": ["data.gov.in / AGMARKNET"],
                    "market_data_status": "no_matching_record",
                }
            logger.info("[web_search_node] Added %s official live market records", len(records))
            return {
                "web_context": market_context,
                "sources": ["data.gov.in / AGMARKNET"],
                "market_data_status": "available",
            }
        except LiveMarketDataUnavailable as exc:
            logger.warning("[web_search_node] Live market data unavailable: %s", exc)
            return {
                "web_context": (
                    "\n--- Official live mandi data unavailable ---\n"
                    f"{exc} Do not provide third-party links or claim any current price.\n"
                ),
                "sources": [],
                "market_data_status": "unavailable",
            }

    web_context, web_sources = _web_search(web_query)

    updated_sources = list(
        state.get(
            "sources",
            [],
        )
    )

    updated_sources += [
        s
        for s in web_sources
        if s not in updated_sources
    ]

    logger.info(
        f"[web_search_node] Added "
        f"{len(web_sources)} web sources"
    )

    return {
        "web_context": web_context,
        "sources": updated_sources,
    }


def synthesize_node(
    state: AgriState,
) -> dict:
    """Node 5: Synthesize answer using evidence and conversation history."""

    _init_components()

    context_parts = []

    agents_used = state.get(
        "agents_used",
        [],
    )

    docs = state.get(
        "retrieved_docs",
        [],
    )

    for agent_id in agents_used:

        agent_docs = [
            d
            for d in docs
            if d.get("agent") == agent_id
        ]

        if not agent_docs:
            continue

        config = AGENTS[agent_id]

        agent_context = (
            f"\n--- "
            f"{config.emoji} "
            f"{config.name} "
            f"---\n"
        )

        for chunk in agent_docs:

            source = (
                Path(chunk["source"]).name
                if chunk["source"] != "unknown"
                else "unknown"
            )

            relevance = chunk.get(
                "llm_relevance",
                chunk.get(
                    "retrieval_score",
                    0.0,
                ),
            )

            agent_context += (
                f"[Source: {source} | "
                f"relevance: {relevance}]\n"
                f"{chunk['content']}\n\n"
            )

        context_parts.append(
            agent_context
        )

    web_context = state.get(
        "web_context",
        "",
    )

    full_context = (
        "\n".join(context_parts)
        + web_context
    )

    agents_consulted = ", ".join(
        f"{AGENTS[a].emoji} "
        f"{AGENTS[a].name}"
        for a in agents_used
        if a in AGENTS
    ) or "No specialist agent"

    if not full_context.strip():

        full_context = (
            "No reliable local or web "
            "evidence was retrieved."
        )

    language = state.get(
        "language",
        "English",
    )

    # -------------------------------------------------------
    # Conversation history
    # -------------------------------------------------------
    history = state.get(
        "conversation_history",
        [],
    )

    history_text = "\n".join(
        f"User: {turn.get('user', '')}\n"
        f"Assistant: {turn.get('assistant', '')}"
        for turn in history[-6:]
    )

    if not history_text:
        history_text = (
            "No previous conversation."
        )

    # A missing exact AGMARKNET row is a data result, not an invitation for the
    # LLM to suggest third-party sites. Keep this response deterministic.
    if state.get("market_data_status") in {"no_matching_record", "unavailable"}:
        unavailable_messages = {
            "Hindi": "मैं इस अनुरोध के लिए AGMARKNET से वर्तमान मंडी मूल्य सत्यापित नहीं कर सका। कोई अनुमान, पुराना मूल्य या तीसरे पक्ष का लिंक नहीं दिया जा रहा है। कृपया फसल, बाज़ार और स्थान की वर्तनी जाँचकर फिर प्रयास करें।",
            "Marathi": "या विनंतीसाठी AGMARKNET मधून सध्याचा मंडी भाव पडताळता आला नाही. अंदाजे किंवा जुने दर आणि तृतीय-पक्षाचे दुवे दिलेले नाहीत. कृपया पीक, बाजार आणि ठिकाणाचे शब्दलेखन तपासून पुन्हा प्रयत्न करा.",
        }
        answer = unavailable_messages.get(
            language,
            "I could not verify a current matching mandi price from AGMARKNET for this request. I will not substitute estimates, old prices, or third-party links. Please check the crop, market, and location spelling and try again later.",
        )
        updated_history = history + [{"user": state.get("original_query", state["query"]), "assistant": answer}]
        return {"answer": answer, "conversation_history": updated_history[-10:]}

    # -------------------------------------------------------
    # LLM Synthesis
    # -------------------------------------------------------
    if LLM_AVAILABLE and LLM is not None:

        try:

            prompt = SYNTHESIS_PROMPT.format(
                agents_consulted=agents_consulted,
                context=full_context,
                conversation_history=history_text,
                question=state.get(
                    "original_query",
                    state["query"],
                ),
                language=language,
            )

            start_time = time.time()

            response = LLM.invoke(prompt)

            latency_ms = int(
                (
                    time.time()
                    - start_time
                )
                * 1000
            )

            logger.info(
                "LLM call completed",
                llm_node="synthesize",
                latency_ms=latency_ms,
            )

            answer = response.content.strip()

            logger.info(
                "[synthesize_node] "
                f"Generated focused answer "
                f"({len(answer)} chars)"
            )

            # ------------------------------------------------
            # Save this conversation turn
            # ------------------------------------------------
            updated_history = history + [
                {
                    "user": state.get(
                        "original_query",
                        state["query"],
                    ),
                    "assistant": answer,
                }
            ]

            return {
                "answer": answer,
                "conversation_history": (
                    updated_history[-10:]
                ),
            }

        except Exception as e:

            logger.error(
                "[synthesize_node] "
                f"LLM synthesis failed: {e}"
            )

    # -------------------------------------------------------
    # Fallback
    # -------------------------------------------------------
    fallback = (
        "**Relevant information:**\n\n"
    )

    for doc in docs[:5]:

        source = (
            Path(doc["source"]).name
            if doc["source"] != "unknown"
            else "unknown"
        )

        fallback += (
            f"- [{source}] "
            f"{doc['content'][:700]}\n\n"
        )

    if not docs:

        fallback += (
            "I could not retrieve reliable "
            "information for this question."
        )

    updated_history = history + [
        {
            "user": state.get(
                "original_query",
                state["query"],
            ),
            "assistant": fallback,
        }
    ]

    return {
        "answer": fallback,
        "conversation_history": (
            updated_history[-10:]
        ),
    }


def reflect_node(
    state: AgriState,
) -> dict:
    """Node 6: Check directness and rewrite weak answers."""

    # Preserve deterministic live-data failure messages verbatim.
    if state.get("market_data_status") in {"no_matching_record", "unavailable"}:
        return {"answer_quality": "verified", "quality_note": "Official live market data unavailable."}

    _init_components()

    answer = state.get(
        "answer",
        "",
    )

    if (
        not answer
        or not LLM_AVAILABLE
        or LLM is None
    ):

        return {
            "answer_quality": "unverified",
            "quality_note": "",
        }

    try:

        reflect_prompt = f"""You are the final quality controller for an agricultural assistant.

USER QUESTION:
{state.get("original_query", state["query"])}

CURRENT ANSWER:
{answer[:4000]}

RELEVANT EVIDENCE:
Local retrieved evidence:
{state.get("retrieved_docs", [])}

Live web evidence:
{state.get("web_context", "")[:3500]}

Decide whether the answer is direct and specific to the user's question.
If it contains irrelevant material, overlong tangents, unsupported claims, or misses the question,
rewrite it into a concise, useful answer using only the supported evidence and clearly marked general knowledge.

Return ONLY valid JSON:
{{
  "quality": "good" or "needs_improvement",
  "note": "short reason",
  "rewritten_answer": "If needs_improvement, provide the complete corrected answer; otherwise return the original answer."
}}"""

        start_time = time.time()

        response = LLM.invoke(
            reflect_prompt
        )

        latency_ms = int(
            (
                time.time()
                - start_time
            )
            * 1000
        )

        logger.info(
            "LLM call completed",
            llm_node="reflect",
            latency_ms=latency_ms,
        )

        result = _parse_json_object(
            response.content
        )

        quality = result.get(
            "quality",
            "good",
        )

        note = result.get(
            "note",
            "",
        )

        rewritten = result.get(
            "rewritten_answer",
            "",
        )

        if (
            quality == "needs_improvement"
            and rewritten.strip()
        ):

            logger.info(
                f"[reflect_node] "
                f"Rewriting answer: {note}"
            )

            return {
                "answer": rewritten.strip(),
                "answer_quality": quality,
                "quality_note": note,
            }

        logger.info(
            f"[reflect_node] Quality: {quality}"
        )

        return {
            "answer_quality": quality,
            "quality_note": (
                note
                if quality != "good"
                else ""
            ),
        }

    except Exception as e:

        logger.warning(
            f"[reflect_node] "
            f"Reflection failed: {e}"
        )

        return {
            "answer_quality": "unverified",
            "quality_note": "",
        }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYNTHESIS_PROMPT = """You are AgriMitra AI, an expert agricultural assistant serving Indian farmers.

Your job is to answer the CURRENT USER QUESTION using the retrieved evidence
and relevant conversation history.

AGENTS CONSULTED: {agents_consulted}

CONVERSATION HISTORY:
{conversation_history}

RETRIEVED CONTEXT:
{context}

CURRENT USER QUESTION:
{question}

STRICT INSTRUCTIONS:

1. Answer ONLY the current user's question.

2. Use conversation history to understand follow-up questions and references
   such as "it", "this", "that", "they", "same scheme", "same crop",
   "again", "what about eligibility", and "who started it".

3. If the current question refers to something from the previous conversation,
   resolve that reference using the conversation history.

4. Use only information supported by the retrieved context.
   Do not invent facts.

5. If the retrieved context does not contain the requested fact, clearly say
   that the available information does not contain it rather than guessing.

6. For government schemes, do not invent eligibility rules, documents,
   deadlines, processing times, payment requirements, or other specific details.

7. For time-sensitive questions (for example today, latest, current, live,
   news, current prices, current weather, forecasts, deadlines, or recent
   announcements), the LIVE WEB SEARCH evidence is authoritative over static
   local documents. If live web evidence is unavailable, explicitly say that
   current information could not be verified. Never turn historical/static
   figures into today's facts.

8. For current mandi-price questions, only official data.gov.in / AGMARKNET
   records in the context can support a current price. If they are unavailable,
   say so plainly and do not substitute static RAG data, estimates, or third-party links.

9. When live web evidence is used, cite the relevant source URLs in the answer
   when useful. Do not fabricate URLs.

10. Keep the answer concise, practical, and easy for farmers to understand.

11. Translate the complete answer into {language}.
   Keep proper nouns, official scheme names, URLs, abbreviations, numbers,
   and technical terms unchanged when appropriate.

12. Do not mention internal routing, agents, conversation history, or
    retrieval mechanisms to the user.

ANSWER:"""


# ---------------------------------------------------------------------------
# Conditional Edge
# ---------------------------------------------------------------------------
def _should_web_search(
    state: AgriState,
) -> str:
    """Conditional edge."""

    if state.get("force_web_search", False):
        logger.info("[conditional] Live/current query → web_search")
        return "web_search"

    if state.get(
        "needs_web_search",
        False,
    ):

        logger.info(
            "[conditional] "
            "Retrieval insufficient → web_search"
        )

        return "web_search"

    logger.info(
        "[conditional] "
        "Retrieval sufficient → synthesize"
    )

    return "synthesize"


# ---------------------------------------------------------------------------
# Build & Compile LangGraph
# ---------------------------------------------------------------------------
workflow = StateGraph(
    AgriState
)

workflow.add_node(
    "route",
    route_node,
)

workflow.add_node(
    "retrieve",
    retrieve_node,
)

workflow.add_node(
    "evaluate",
    evaluate_retrieval_node,
)

workflow.add_node(
    "web_search",
    web_search_node,
)

workflow.add_node(
    "synthesize",
    synthesize_node,
)

workflow.add_node(
    "reflect",
    reflect_node,
)

workflow.set_entry_point(
    "route"
)

workflow.add_edge(
    "route",
    "retrieve",
)

workflow.add_edge(
    "retrieve",
    "evaluate",
)

workflow.add_conditional_edges(
    "evaluate",
    _should_web_search,
    {
        "web_search": "web_search",
        "synthesize": "synthesize",
    },
)

workflow.add_edge(
    "web_search",
    "synthesize",
)

workflow.add_edge(
    "synthesize",
    "reflect",
)

workflow.add_edge(
    "reflect",
    END,
)

crag_graph_base = workflow.compile()

DB_PATH = Path(
    os.getenv(
        "CHECKPOINT_DB_PATH",
        str(Path(__file__).parent / "runtime" / "checkpoints.db"),
    )
)

logger.info(
    "LangGraph CRAG pipeline base compiled"
)


# ---------------------------------------------------------------------------
# Streaming Entry Point
# ---------------------------------------------------------------------------
async def stream_answer(
    query: str,
    language: str = "English",
    session_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Process a query through the LangGraph CRAG pipeline.

    Previous conversation state is loaded from the SQLite checkpointer
    when a session_id is provided.
    """

    logger.info(
        f"Processing CRAG query: "
        f"{query[:100]}... "
        f"(session={session_id})"
    )

    # -------------------------------------------------------
    # Config with thread_id enables per-session persistence
    # -------------------------------------------------------
    config = {}

    if session_id:
        config = {
            "configurable": {
                "thread_id": session_id
            }
        }

    final_state = {}
    streamed_synthesis = False

    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        async with AsyncSqliteSaver.from_conn_string(
            str(DB_PATH)
        ) as checkpointer:

            # Recompile graph with checkpointer
            crag_graph = workflow.compile(
                checkpointer=checkpointer
            )

            # ------------------------------------------------
            # Load previous conversation state
            # ------------------------------------------------
            previous_state = {}

            if session_id:
                saved_state = await crag_graph.aget_state(config)

                if saved_state and saved_state.values:
                    previous_state = saved_state.values

            conversation_history = previous_state.get(
                "conversation_history",
                []
            )

            # ------------------------------------------------
            # Create new state using previous history
            # ------------------------------------------------
            initial_state: AgriState = {

                "query": query,

                "original_query": query,

                "retrieved_docs": [],

                "retrieval_score": 0.0,

                "needs_web_search": False,

                "force_web_search": _is_time_sensitive_query(query),

                "answer": "",

                "conversation_history": conversation_history,

                "agents_used": [],

                "sources": [],

                "web_context": "",

                "language": language,

                "answer_quality": "",

                "quality_note": "",

                "market_data_status": "",
            }

            # ------------------------------------------------
            # Run graph
            # ------------------------------------------------
            async for event in crag_graph.astream_events(
                initial_state,
                config=config,
                version="v2",
            ):

                kind = event.get(
                    "event",
                    "",
                )

                # Stream LLM tokens ONLY
                # from synthesize node
                if kind == "on_chat_model_stream":

                    node_name = (
                        event.get(
                            "metadata",
                            {},
                        ).get(
                            "langgraph_node",
                            "",
                        )
                    )

                    if node_name == "synthesize":

                        token = (
                            event["data"]
                            ["chunk"]
                            .content
                        )

                        if token:

                            streamed_synthesis = True

                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "chunk": token
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n\n"
                            )

                            await asyncio.sleep(
                                0.01
                            )

                # Capture final graph output
                if kind == "on_chain_end":

                    output = (
                        event.get(
                            "data",
                            {},
                        ).get(
                            "output",
                            {},
                        )
                    )

                    if (
                        isinstance(
                            output,
                            dict,
                        )
                        and "answer" in output
                    ):

                        final_state = output

    except Exception as e:

        logger.error(
            f"CRAG graph execution failed: {e}",
            exc_info=True,
        )

        yield (
            "data: "
            + json.dumps(
                {
                    "chunk":
                        f"Error processing query: {str(e)}"
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )

        yield "data: [DONE]\n\n"

        return

    # -------------------------------------------------------
    # Fallback streaming
    # -------------------------------------------------------
    if (
        not streamed_synthesis
        and final_state.get("answer")
    ):

        answer = final_state["answer"]

        chunk_size = 20

        for i in range(
            0,
            len(answer),
            chunk_size,
        ):

            yield (
                "data: "
                + json.dumps(
                    {
                        "chunk":
                            answer[
                                i:i + chunk_size
                            ]
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

            await asyncio.sleep(
                0.01
            )

    # -------------------------------------------------------
    # Final metadata
    # -------------------------------------------------------
    agents_used = final_state.get(
        "agents_used",
        [],
    )

    agents_info = []

    for agent_id in agents_used:

        if agent_id in AGENTS:

            config = AGENTS[agent_id]

            docs_for_agent = [
                d
                for d in final_state.get(
                    "retrieved_docs",
                    [],
                )
                if d.get(
                    "agent"
                ) == agent_id
            ]

            agents_info.append(
                {
                    "id": config.id,
                    "name": config.name,
                    "emoji": config.emoji,
                    "description": config.description,
                    "chunks_retrieved":
                        len(docs_for_agent),
                }
            )

    metadata = {

        "sources":
            final_state.get(
                "sources",
                [],
            ),

        "agents_used":
            agents_info,

        "retrieval_score":
            final_state.get(
                "retrieval_score",
                0.0,
            ),

        "web_search_used":
            final_state.get(
                "needs_web_search",
                False,
            ),

        "answer_quality":
            final_state.get(
                "answer_quality",
                "",
            ),

        "retrieved_chunks": [
            d.get(
                "content",
                "",
            )
            for d in final_state.get(
                "retrieved_docs",
                [],
            )
        ],
    }

    yield (
        "data: "
        + json.dumps(
            {
                "metadata":
                    metadata
            },
            ensure_ascii=False,
        )
        + "\n\n"
    )

    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_all_agents() -> List[Dict]:
    """Return metadata for all available agents."""

    return [
        {
            "id": config.id,
            "name": config.name,
            "emoji": config.emoji,
            "description": config.description,
        }
        for config in AGENTS.values()
    ]