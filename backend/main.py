# main.py
"""FastAPI backend for AgriMitra AI Pro — Multi-RAG System.

Provides API endpoints for:
  - Multi-agent RAG chat
  - Agent listing
  - Geographic data
  - Market prices
  - Government schemes
  - Weather advisories
    - Leaf scan analysis

Serves the React frontend static files in production.
"""

import logging
from pathlib import Path
import os
import base64
import io
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import json
from typing import Literal, Optional

from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, HTTPException, Query, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError
import structlog
import uuid
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import run_in_threadpool
from prometheus_fastapi_instrumentator import Instrumentator

from auth import router as auth_router
from schemes_data import get_schemes

# Load environment variables
load_dotenv()

REDIS_CLIENT = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global REDIS_CLIENT
    try:
        import redis.asyncio as redis_async
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        
        # Configure connection kwargs, especially for Render/Upstash rediss:// URLs
        kwargs = {"decode_responses": True}
        if redis_url.startswith("rediss://"):
            kwargs["ssl_cert_reqs"] = "none"
            
        REDIS_CLIENT = redis_async.from_url(redis_url, **kwargs)
        await REDIS_CLIENT.ping()
        logger.info("Connected to Redis successfully.")
    except Exception as e:
        logger.warning(f"Could not connect to Redis: {e}. Caching disabled.")
        REDIS_CLIENT = None

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_key_here":
        # Retrieval, health checks, and the static frontend remain useful without
        # an LLM credential. Endpoints that require Groq return an explicit 503.
        logger.warning("GROQ_API_KEY is not configured; AI generation is unavailable.")
    yield
    if REDIS_CLIENT:
        await REDIS_CLIENT.aclose()

# Configure logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger(__name__)

# Import the Multi-RAG engine
from multi_rag import get_all_agents, stream_answer

app = FastAPI(
    title="AgriMitra AI Pro",
    description="Multi-RAG Agricultural Intelligence System",
    version="2.0.0",
    lifespan=lifespan,
)
app.include_router(auth_router)

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIdMiddleware)
Instrumentator().instrument(app).expose(app)

# CORS for local development
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Language Config
# ---------------------------------------------------------------------------
LANG_MAP = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "or": "Odia",
    "pa": "Punjabi",
    "ta": "Tamil",
}

# ---------------------------------------------------------------------------
# LLM Translation Cache & Engine
# ---------------------------------------------------------------------------
TRANSLATION_CACHE = {}  # key: f"{endpoint}_{lang}" -> translated data


def _get_llm():
    """Get a ChatGroq LLM instance (lazy, shared)."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model_name=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            groq_api_key=api_key,
            temperature=0.2,
        )
    except Exception:
        return None


def translate_json_via_llm(data, lang_full: str, context_hint: str = "agricultural data"):
    """Use Groq LLM to translate a JSON data structure into a target language.
    Preserves numeric values, keys, and structure — only translates string values.
    """
    llm = _get_llm()
    if not llm:
        return data

    try:
        prompt = f"""You are a professional translator specializing in Indian agricultural terminology.
Translate ALL string values in the following JSON into {lang_full}.
This is {context_hint} for Indian farmers.

RULES:
1. Keep all JSON keys EXACTLY as-is (do NOT translate keys).
2. Translate ONLY the string values into {lang_full}.
3. Keep numbers, currency symbols (₹), percentages, and units as-is.
4. Keep proper nouns like scheme names (PM-KISAN, PMFBY, etc.) as-is but translate their descriptions.
5. Keep URLs/links as-is.
6. Output ONLY valid JSON, no markdown formatting or extra text.

INPUT JSON:
{json.dumps(data, ensure_ascii=False, indent=2)}

OUTPUT (valid JSON only, translated to {lang_full}):"""

        start_time = time.time()
        response = llm.invoke(prompt)
        latency_ms = int((time.time() - start_time) * 1000)
        logger.info("LLM call completed", llm_node="translation", latency_ms=latency_ms)
        
        content = response.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        return json.loads(content)
    except Exception as e:
        logger.error(f"Translation LLM error for {lang_full}: {e}")
        return data


def get_translated(endpoint: str, original_data, lang: str, context_hint: str = ""):
    """Return cached translation or translate via LLM. English returns original data."""
    lang_full = LANG_MAP.get(lang, "English")
    if lang == "en" or lang_full == "English":
        return original_data

    # Include the data in the cache key: weather and scan payloads can change
    # while retaining the same endpoint/city/file name.
    cache_key = f"{endpoint}_{lang}_{json.dumps(original_data, ensure_ascii=False, sort_keys=True, default=str)}"
    if cache_key in TRANSLATION_CACHE:
        logger.info(f"Translation cache hit: {cache_key}")
        return TRANSLATION_CACHE[cache_key]

    logger.info(f"Translating {endpoint} to {lang_full}...")
    translated = translate_json_via_llm(original_data, lang_full, context_hint)
    TRANSLATION_CACHE[cache_key] = translated
    return translated


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User's question")
    language: str = Field(default="en", description="User's selected language")
    session_id: Optional[str] = Field(default=None, description="Session UUID for conversation memory")


def _require_supported_language(lang: str) -> str:
    """Validate API language codes consistently across all user-facing endpoints."""
    if lang not in LANG_MAP:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported language '{lang}'. Supported codes: {', '.join(LANG_MAP)}.",
        )
    return lang


class ChatResponse(BaseModel):
    answer: str
    sources: list
    agents_used: list


from fastapi.responses import StreamingResponse

# ---------------------------------------------------------------------------
# Chat Endpoint (Multi-RAG with Streaming)
# ---------------------------------------------------------------------------
@app.post("/api/chat")
@limiter.limit("10/minute")
async def chat_endpoint(request: Request, chat_request: ChatRequest):
    """Handle a chat query using the Multi-RAG pipeline.
    Routes the query to specialized agents, retrieves context (and live web search),
    and streams the synthesized answer via Server-Sent Events (SSE).
    """
    logger.info(f"Chat request: {chat_request.query[:80]}... Language: {chat_request.language} Session: {chat_request.session_id}")
    try:
        lang_full = LANG_MAP[_require_supported_language(chat_request.language)]
        
        return StreamingResponse(
            stream_answer(chat_request.query, language=lang_full, session_id=chat_request.session_id),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Chat streaming error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


# ---------------------------------------------------------------------------
# Audio Transcription (Whisper API)
# ---------------------------------------------------------------------------
@app.post("/api/transcribe")
@limiter.limit("10/minute")
async def transcribe_audio(request: Request, file: UploadFile = File(...)):
    """Transcribe audio using Groq's Whisper API."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")
        
    try:
        contents = await file.read()
        import httpx
        
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        files = {
            "file": (file.filename or "audio.webm", contents, file.content_type or "audio/webm")
        }
        data = {
            "model": "whisper-large-v3",
            "response_format": "json"
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, files=files, data=data, timeout=30.0)
            
        if resp.status_code != 200:
            logger.error(f"Groq Whisper API error: {resp.text}")
            raise HTTPException(status_code=500, detail="Failed to transcribe audio.")
            
        result = resp.json()
        return {"text": result.get("text", "")}
        
    except Exception as e:
        logger.error(f"Audio transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Agents Endpoint
# ---------------------------------------------------------------------------
@app.get("/api/agents")
async def list_agents(lang: str = Query(default="en")):
    """List all available Multi-RAG agents with their metadata."""
    _require_supported_language(lang)
    agents = get_all_agents()
    return get_translated("agents", agents, lang, "AI agent names and descriptions")


# ---------------------------------------------------------------------------
# Geographic Data
# ---------------------------------------------------------------------------
@app.get("/api/geo-data")
async def geo_data():
    """Return geographic and agricultural data for supported states."""
    return {
        "Andhra Pradesh": {
            "districts": ["Guntur", "Krishna", "Prakasam", "Nellore", "Visakhapatnam", "East Godavari", "West Godavari"],
            "soils": ["Black Cotton Soil", "Red Soil", "Alluvial Soil", "Laterite"],
            "seasons": ["Kharif", "Rabi", "Zaid"],
            "major_crops": ["Paddy", "Cotton", "Chillies", "Groundnut", "Tobacco"],
        },
        "Telangana": {
            "districts": ["Hyderabad", "Warangal", "Karimnagar", "Nizamabad", "Nalgonda", "Medak", "Adilabad"],
            "soils": ["Red Soil", "Black Soil", "Alluvial", "Laterite"],
            "seasons": ["Kharif", "Rabi"],
            "major_crops": ["Cotton", "Paddy", "Maize", "Turmeric", "Soybean"],
        },
        "Tamil Nadu": {
            "districts": ["Thanjavur", "Nagapattinam", "Cuddalore", "Coimbatore", "Madurai", "Salem"],
            "soils": ["Alluvial Soil", "Red Soil", "Black Soil", "Laterite"],
            "seasons": ["Samba", "Kuruvai", "Navarai"],
            "major_crops": ["Paddy", "Sugarcane", "Cotton", "Coconut", "Groundnut"],
        },
        "Karnataka": {
            "districts": ["Dharwad", "Shimoga", "Gulbarga", "Bellary", "Mysore", "Mandya"],
            "soils": ["Red Soil", "Black Soil", "Laterite", "Alluvial"],
            "seasons": ["Kharif", "Rabi"],
            "major_crops": ["Paddy", "Jowar", "Cotton", "Groundnut", "Sugarcane"],
        },
    }


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------
async def _get_market_data():
    """Fetch live daily mandi prices from the official data.gov.in AGMARKNET dataset.

    No mock/fallback market data is returned. If live data cannot be obtained,
    the endpoint fails explicitly instead of showing stale/fake prices.
    """
    import httpx

    api_key = os.getenv("DATAGOV_API_KEY")

    if not api_key or api_key == "your_key_here":
        logger.error("DATAGOV_API_KEY is not configured.")
        raise HTTPException(
            status_code=503,
            detail="Live market data is unavailable because DATAGOV_API_KEY is not configured.",
        )

    resource_id = os.getenv(
        "DATAGOV_MARKET_RESOURCE_ID",
        "9ef84268-d588-465a-a308-a864a43d0070",
    )

    url = (
        f"https://api.data.gov.in/resource/{resource_id}"
        f"?api-key={api_key}"
        f"&format=json"
        f"&limit=100"
    )

    try:
        async with httpx.AsyncClient(
            timeout=60.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/151.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        ) as client:
            response = await client.get(url)

        if response.status_code != 200:
            logger.error(
                f"data.gov.in market API failed: "
                f"status={response.status_code}, body={response.text[:500]}"
            )
            raise HTTPException(
                status_code=503,
                detail="Live mandi market data could not be fetched.",
            )

        payload = response.json()
        records = payload.get("records", [])

        if not records:
            logger.error("data.gov.in returned no market records.")
            raise HTTPException(
                status_code=503,
                detail="Live mandi market data returned no records.",
            )

        results = []

        for rec in records:
            commodity = rec.get("commodity")
            market_name = rec.get("market")
            state = rec.get("state")
            district = rec.get("district")
            min_price = rec.get("min_price")
            max_price = rec.get("max_price")
            modal_price = rec.get("modal_price")
            arrival_date = rec.get("arrival_date")
            variety = rec.get("variety")
            grade = rec.get("grade")

            if min_price is None and max_price is None and modal_price is None:
                continue

            results.append(
                {
                    "crop": str(commodity or "Unknown").title(),
                    "commodity": commodity or "Unknown",
                    "market": market_name or "Unknown",
                    "state": state or "Unknown",
                    "district": district or "Unknown",
                    "variety": variety or "Unknown",
                    "grade": grade or "Unknown",
                    "minPrice": min_price,
                    "maxPrice": max_price,
                    "modalPrice": modal_price,
                    "currentRange": (
                        f"₹{min_price} – ₹{max_price}"
                        if min_price is not None and max_price is not None
                        else "Unavailable"
                    ),
                    "msp": None,
                    "demand": "Unknown",
                    "trend": "Unknown",
                    "change": "Unknown",
                    "arrivalDate": arrival_date,
                    "unit": "per Quintal",
                    "source": "data.gov.in / AGMARKNET",
                    "isLive": True,
                }
            )

        if not results:
            raise HTTPException(
                status_code=503,
                detail="Live mandi market data contained no usable price records.",
            )

        logger.info(
            f"Fetched {len(results)} live mandi records from data.gov.in/AGMARKNET."
        )
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Live market API error: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Live mandi market data is temporarily unavailable.",
        )


@app.get("/api/market")
async def market_data(lang: str = Query(default="en")):
    """Return latest daily mandi pricing data with Redis caching."""
    _require_supported_language(lang)
    cache_key = "market_data_raw"
    raw_data = None

    if REDIS_CLIENT:
        try:
            cached_json = await REDIS_CLIENT.get(cache_key)
            if cached_json:
                raw_data = json.loads(cached_json)
                logger.info("Market data loaded from Redis cache")
        except Exception as e:
            logger.warning(f"Redis get error: {e}")

    if not raw_data:
        logger.info("Fetching fresh market data...")
        raw_data = await _get_market_data()

        if REDIS_CLIENT:
            try:
                await REDIS_CLIENT.set(
                    cache_key,
                    json.dumps(raw_data),
                    ex=3600,
                )
            except Exception as e:
                logger.warning(f"Redis set error: {e}")

    return get_translated(
        "market",
        raw_data,
        lang,
        "latest daily mandi market prices for farmers",
    )


@app.get("/api/schemes")
async def schemes_data(lang: str = Query(default="en")):
    """Return list of agricultural government schemes."""
    _require_supported_language(lang)
    data = get_schemes()
    return get_translated("schemes", data, lang, "government agricultural schemes for farmers")


# ---------------------------------------------------------------------------
# Weather Data
# ---------------------------------------------------------------------------
@app.get("/api/weather/{state}/{city}")
async def weather_data(state: str, city: str, lang: str = Query(default="en")):
    """Return weather and risk data for a given state and city using OpenWeatherMap and Groq API."""
    import httpx
    
    groq_api_key = os.getenv("GROQ_API_KEY")
    owm_api_key = os.getenv("OPENWEATHER_API_KEY")
    _require_supported_language(lang)
    lang_full = LANG_MAP[lang]

    if not owm_api_key:
        raise HTTPException(
            status_code=503,
            detail="Live weather is unavailable because OPENWEATHER_API_KEY is not configured.",
        )

    # Fetch real data from OpenWeatherMap
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={city},{state},IN&appid={owm_api_key}&units=metric"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            
        if response.status_code != 200:
            # Fallback to just city and IN if state+city fails
            url = f"https://api.openweathermap.org/data/2.5/forecast?q={city},IN&appid={owm_api_key}&units=metric"
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                
        if response.status_code != 200:
            logger.error(f"OpenWeatherMap API error: {response.text}")
            raise HTTPException(status_code=503, detail="Live weather data could not be fetched.")

        owm_data = response.json()
        current = owm_data["list"][0]
        
        temp = f"{round(current['main']['temp'])}°C"
        humidity = f"{current['main']['humidity']}%"
        wind = f"{round(current['wind']['speed'] * 3.6)} km/h"
        condition = current['weather'][0]['description'].title()
        
        # Get 5 day forecast (every 24 hours / 8 indices)
        forecast_list = []
        for i in range(0, 40, 8):
            if i < len(owm_data["list"]):
                f = owm_data["list"][i]
                forecast_list.append(f"{round(f['main']['temp'])}°C / {f['weather'][0]['description'].title()}")

        base_weather = {
            "district": city,
            "temp": temp,
            "humidity": humidity,
            "wind": wind,
            "condition": condition,
            "forecast": forecast_list
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch from OpenWeatherMap: {e}")
        raise HTTPException(status_code=503, detail="Live weather data is temporarily unavailable.")

    # Now use LLM to generate agricultural advisory based on REAL weather
    if not groq_api_key:
        base_weather["risk"] = "No AI advisory is available because GROQ_API_KEY is not configured."
        base_weather["advisory"] = "Use the measured forecast above and follow local IMD and agricultural-extension guidance."
        base_weather["suggested_crops"] = []
        return get_translated(f"weather_real_{city}", base_weather, lang, "weather advisory for farmers")

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(
            model_name=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            groq_api_key=groq_api_key,
            temperature=0.3,
        )

        lang_instruction = ""
        if lang != "en":
            lang_instruction = f"\nIMPORTANT: ALL string values in the JSON must be written in {lang_full} language. Keep JSON keys in English."

        prompt = f"""You are an agricultural meteorologist. I have the actual real-time weather forecast for {city}, {state}, India:
Temperature: {temp}
Humidity: {humidity}
Wind: {wind}
Condition: {condition}
5-Day Forecast: {', '.join(forecast_list)}

Based on this REAL data, provide an agricultural risk assessment, farmer advisory, and suggested crops.
Output ONLY valid JSON with no markdown formatting or extra text.{lang_instruction}

Required JSON structure:
{{
  "risk": "string (brief sentence about weather risks to crops based on the provided weather)",
  "advisory": "string (brief advisory for farmers based on the provided weather)",
  "suggested_crops": ["Crop Name 1", "Crop Name 2", "Crop Name 3"]
}}"""
        start_time = time.time()
        response = llm.invoke(prompt)
        latency_ms = int((time.time() - start_time) * 1000)
        logger.info("LLM call completed", llm_node="weather_advisory", latency_ms=latency_ms)
        
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        llm_data = json.loads(content)
        base_weather.update(llm_data)
        return base_weather
        
    except Exception as e:
        logger.error(f"Weather advisory Groq API error: {e}", exc_info=True)
        base_weather["risk"] = "AI weather risk assessment is temporarily unavailable."
        base_weather["advisory"] = "Use the measured forecast above and follow local IMD and agricultural-extension guidance."
        base_weather["suggested_crops"] = []
        return base_weather


# ---------------------------------------------------------------------------
# Leaf Scan (Gemini Vision)
# ---------------------------------------------------------------------------
class LeafScanAnalysis(BaseModel):
    plant_name: str
    plant_identification_note: str
    possible_disease: str
    diagnosis_status: Literal["possible", "uncertain", "plant_mismatch", "healthy"]
    observed_symptoms: list[str]
    explanation: str
    alternative_causes: list[str]
    severity: Literal["mild", "moderate", "severe", "unclear"]
    treatment: list[str]
    prevention: list[str]
    confidence_note: str
    when_to_consult_an_expert: str


LEAF_SCAN_MAX_BYTES = 10 * 1024 * 1024
LEAF_SCAN_SYMPTOMS = {
    "Black or brown spots",
    "Yellow leaves",
    "Holes or damaged leaves",
    "White powder or patches",
    "Leaves drying or falling",
    "Curling or twisted leaves",
    "Something else",
    "I don't know",
}
LEAF_SCAN_TIMELINES = {
    "Today",
    "A few days ago",
    "About a week ago",
    "More than two weeks ago",
    "Not sure",
}
LEAF_SCAN_SPREAD = {"Yes", "No", "Not sure"}
LEAF_SCAN_INSTRUCTIONS = """Act as a plant-health analysis assistant helping farmers.
Analyse the uploaded leaf image using the plant name and all additional information
supplied by the farmer. Answer in the requested language.

Consider the entered plant name, but do not blindly assume it is correct. Identify
visible symptoms from the image. Suggest possible diseases or other causes, including
pests or nutrient problems when appropriate. Explain likely causes in simple language
and give practical treatment and prevention suggestions. Clearly say when the image is
unclear or evidence is insufficient. Never invent a diagnosis or claim certainty
without evidence. Flag any mismatch between the image and plant name. If several
causes are possible, explain them as alternatives. Do not give unsafe pesticide
instructions; recommend local agricultural guidance and following product labels.

Match the certainty of every explanation to diagnosis_status. When the status is
"possible" or "uncertain", use cautious wording such as "may be consistent with".
Do not call symptoms "highly characteristic", a "key indicator", or say the
condition "strongly suggests" or confirms a disease. Separate visible observations
from possible causes, state what the image cannot establish, and name a specific
pathogen only when the image evidence supports that level of detail. In
confidence_note, clearly state when a photo alone cannot confirm the cause and
mention that other causes may look similar.

Return only the requested structured JSON. Use qualitative uncertainty, not a
numerical confidence score. Include every requested field and use concise,
farmer-friendly wording."""


def _validate_leaf_scan_image(contents: bytes) -> str:
    if not contents:
        raise ValueError("The uploaded image is empty.")
    if len(contents) > LEAF_SCAN_MAX_BYTES:
        raise ValueError("Image must be 10MB or smaller.")

    try:
        with Image.open(io.BytesIO(contents)) as image:
            image.verify()
        with Image.open(io.BytesIO(contents)) as image:
            if image.width < 80 or image.height < 80:
                raise ValueError("Image is too small. Upload a clearer leaf photo.")
            image_format = (image.format or "").upper()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc

    mime_type = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }.get(image_format)
    if mime_type is None:
        raise ValueError("Only JPEG, PNG, and WebP images are supported.")
    return mime_type


def _parse_leaf_scan_response(output_text: str) -> dict:
    try:
        json_text = output_text.strip()
        if json_text.startswith("```"):
            json_text = json_text.removeprefix("```json").removeprefix("```")
            json_text = json_text.removesuffix("```").strip()

        analysis_data = json.loads(json_text)
        if not isinstance(analysis_data, dict):
            raise ValueError("Leaf analysis must be a JSON object.")

        expected_fields = LeafScanAnalysis.model_fields
        missing_fields = expected_fields.keys() - analysis_data.keys()
        if missing_fields:
            raise ValueError(
                f"Leaf analysis is missing required fields: {', '.join(sorted(missing_fields))}."
            )

        normalized_data = {
            field: analysis_data[field] for field in expected_fields
        }
        return LeafScanAnalysis.model_validate(normalized_data).model_dump()
    except (ValidationError, ValueError) as exc:
        validation_errors = (
            [
                {"field": ".".join(map(str, error["loc"])), "type": error["type"]}
                for error in exc.errors(include_input=False)
            ]
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        logger.error(
            "Gemini returned an invalid leaf analysis.",
            validation_errors=validation_errors,
        )
        raise HTTPException(
            status_code=502,
            detail="The vision service returned an invalid leaf analysis. Please try again.",
        ) from exc


def _request_gemini_leaf_analysis(
    api_key: str,
    contents: bytes,
    mime_type: str,
    plant: str,
    observations: list[str],
    additional_symptoms: str,
    noticed_when: str,
    spreading: str,
    description: str,
    language: str,
) -> dict:
    context = "\n".join(
        [
            f"Plant name provided by farmer: {plant}",
            f"Observed symptoms selected: {', '.join(observations) or 'Not provided'}",
            f"Other symptoms described: {additional_symptoms or 'Not provided'}",
            f"When first noticed: {noticed_when or 'Not provided'}",
            f"Is the problem spreading: {spreading or 'Not provided'}",
            f"Additional notes: {description or 'Not provided'}",
            f"Respond in: {language}",
        ]
    )
    image_data = base64.b64encode(contents).decode("ascii")
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            api_version="v1beta",
            timeout=45_000,
            retry_options=types.HttpRetryOptions(
                attempts=3,
                initial_delay=1,
                max_delay=3,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        ),
    )
    response = client.models.generate_content(
        model=os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash"),
        contents=[
            types.Part.from_bytes(data=contents, mime_type=mime_type),
            context,
        ],
        config=types.GenerateContentConfig(
            system_instruction=LEAF_SCAN_INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=LeafScanAnalysis,
            max_output_tokens=1200,
        ),
    )
    output_text = response.text
    if not isinstance(output_text, str) or not output_text.strip():
        raise HTTPException(
            status_code=502,
            detail="The vision service returned no leaf analysis. Please try again.",
        )
    return _parse_leaf_scan_response(output_text)


@app.post("/api/scan")
@limiter.limit("5/minute")
async def scan_endpoint(
    request: Request,
    file: UploadFile = File(...),
    plant: str = Form(..., min_length=2, max_length=100),
    observations: list[str] = Form(default_factory=list),
    additional_symptoms: str = Form(default="", max_length=300),
    noticed_when: str = Form(default="", max_length=40),
    spreading: str = Form(default="", max_length=20),
    description: str = Form(default="", max_length=1200),
    lang: str = Query(default="en"),
):
    """Analyze an uploaded leaf and farmer-provided context with Gemini Vision."""
    _require_supported_language(lang)
    if len(plant.strip()) < 2:
        raise HTTPException(status_code=422, detail="Enter the plant name.")
    if len(observations) > len(LEAF_SCAN_SYMPTOMS) or any(
        symptom not in LEAF_SCAN_SYMPTOMS for symptom in observations
    ):
        raise HTTPException(status_code=422, detail="Choose only the listed symptom options.")
    if "I don't know" in observations and len(observations) > 1:
        raise HTTPException(
            status_code=422,
            detail="'I don't know' cannot be selected with other symptoms.",
        )
    if noticed_when and noticed_when not in LEAF_SCAN_TIMELINES:
        raise HTTPException(status_code=422, detail="Choose a listed time option.")
    if spreading and spreading not in LEAF_SCAN_SPREAD:
        raise HTTPException(status_code=422, detail="Choose a listed spreading option.")
    if file.content_type and file.content_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only JPEG, PNG, and WebP are allowed.",
        )

    try:
        contents = await file.read(LEAF_SCAN_MAX_BYTES + 1)
        mime_type = _validate_leaf_scan_image(contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        raise HTTPException(
            status_code=503,
            detail="Leaf analysis is unavailable because GEMINI_API_KEY is not configured.",
        )

    try:
        analysis = await run_in_threadpool(
            _request_gemini_leaf_analysis,
            api_key,
            contents,
            mime_type,
            plant.strip(),
            observations,
            additional_symptoms.strip(),
            noticed_when,
            spreading,
            description.strip(),
            LANG_MAP[lang],
        )
        return {"analysis": analysis}
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        logger.warning("Gemini leaf scan request timed out.")
        raise HTTPException(
            status_code=504,
            detail="Leaf analysis timed out. Please try again.",
        ) from exc
    except httpx.TransportError as exc:
        logger.warning("Could not connect to Gemini for leaf analysis.")
        raise HTTPException(
            status_code=503,
            detail="Leaf analysis is temporarily unavailable. Please try again.",
        ) from exc
    except genai_errors.APIError as exc:
        status_code = exc.code if isinstance(exc.code, int) else 502
        provider_error = exc.message[:500] if isinstance(exc.message, str) else None
        logger.error(
            "Gemini leaf scan request failed.",
            status_code=status_code,
            provider_status=exc.status,
            provider_error=provider_error,
        )
        if status_code == 503 or exc.status == "UNAVAILABLE":
            detail = "Gemini is temporarily busy. Please try again in a minute."
        elif status_code == 429:
            detail = "Gemini usage limit reached. Check your API quota and billing."
        else:
            detail = "Leaf analysis could not be completed. Please try again later."
        raise HTTPException(
            status_code=503 if status_code == 429 or status_code >= 500 else 502,
            detail=detail,
        ) from exc
    except (ValueError, TypeError) as exc:
        logger.error("Gemini returned an invalid leaf scan response.")
        raise HTTPException(
            status_code=502,
            detail="The vision service returned an invalid leaf analysis. Please try again.",
        ) from exc


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Application health and optional dependency readiness."""
    groq_ready = bool(os.getenv("GROQ_API_KEY") and os.getenv("GROQ_API_KEY") != "your_key_here")
    weather_ready = bool(os.getenv("OPENWEATHER_API_KEY"))
    market_ready = bool(os.getenv("DATAGOV_API_KEY") and os.getenv("DATAGOV_API_KEY") != "your_key_here")
    model_ready = bool(
        os.getenv("GEMINI_API_KEY", "").strip()
        and os.getenv("GEMINI_API_KEY") != "your_gemini_api_key_here"
    )

    return {
        "status": "ok",
        "version": "2.0.0",
        "system": "AgriMitra Multi-RAG",
        "agents_available": len(get_all_agents()),
        "services": {
            "groq": "ready" if groq_ready else "not_configured",
            "weather": "ready" if weather_ready else "not_configured",
            "market": "ready" if market_ready else "not_configured",
            "leaf_model": "ready" if model_ready else "not_configured",
        },
        "ready": True,
    }


@app.get("/ready")
async def readiness_check():
    """Readiness endpoint for required app components."""
    health = health_check()
    return {
        **health,
        "ready": health["services"]["groq"] == "ready" or True,
    }


# ---------------------------------------------------------------------------
# Serve static files (React build) in production
# ---------------------------------------------------------------------------
frontend_path = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_path.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
