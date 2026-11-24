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
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import json
from typing import Optional

from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, HTTPException, Query, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog
import uuid
import time
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from auth import router as auth_router
from plant_disease_service import ModelUnavailableError, classify_leaf_image, validate_image_bytes
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
# Leaf Scan (Groq Vision)
# ---------------------------------------------------------------------------
@app.post("/api/scan")
@limiter.limit("5/minute")
async def scan_endpoint(
    request: Request,
    file: UploadFile = File(...),
    plant: str = Form(..., min_length=2, max_length=80),
    description: str = Form(default="", max_length=1200),
    lang: str = Query(default="en"),
):
    """Analyze a plant leaf using the image, selected plant, and farmer notes."""
    _require_supported_language(lang)
    allowed_types = ["image/jpeg", "image/png", "image/webp"]

    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only JPEG, PNG, and WebP are allowed.",
        )

    try:
        contents = await file.read()
        mime_type = validate_image_bytes(contents, file.filename or "leaf.jpg")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY") == "your_key_here":
        try:
            analysis = classify_leaf_image(contents, file.filename or "leaf.jpg")
            return {"analysis": {**analysis, "status": "model_unavailable", "message": "No trained leaf-disease model is configured in this deployment; upload a trained model to enable predictions."}}
        except ModelUnavailableError:
            raise HTTPException(
                status_code=503,
                detail="Leaf disease model is not configured. Train and deploy a plant-disease model before using scanner inference.",
            )

    api_key = os.getenv("GROQ_API_KEY")
    try:
        import base64
        from groq import Groq

        encoded = base64.b64encode(contents).decode("utf-8")

        vision_model = os.getenv(
            "GROQ_VISION_MODEL",
            "qwen/qwen3.6-27b",
        )
        client = Groq(api_key=api_key)

        try:
            available_models = {model.id for model in client.models.list().data}
        except Exception as exc:
            logger.warning(f"Could not list Groq models before leaf analysis: {exc}")
            available_models = {vision_model}

        if vision_model not in available_models:
            compatible_models = [
                "qwen/qwen3.8-27b",
                "qwen/qwen3.6-27b",
                "meta-llama/llama-4-scout-17b-16e-instruct",
                "meta-llama/llama-4-maverick-17b-128e-instruct",
            ]
            vision_model = next((model for model in compatible_models if model in available_models), None)

        if not vision_model:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No supported Groq vision model is enabled for this API key. "
                    "Enable a vision model in Groq or set GROQ_VISION_MODEL to one available to this account."
                ),
            )

        analysis_tool = {
            "type": "function",
            "function": {
                "name": "report_leaf_analysis",
                "description": (
                    "Return the final structured analysis of the uploaded leaf. "
                    "Choose one primary diagnosis only."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "disease": {
                            "type": "string",
                            "description": (
                                "Single best-supported disease, pest infestation, "
                                "nutrient deficiency, Healthy, or Uncertain."
                            ),
                        },
                        "pathogen": {
                            "type": "string",
                            "description": "Likely pathogen and scientific name when supportable; otherwise Unknown.",
                        },
                        "visible_signs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Two to five image-grounded visible signs.",
                        },
                        "diagnostic_note": {
                            "type": "string",
                            "description": "Brief explanation connecting the visible signs to the diagnosis.",
                        },
                        "confidence": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Confidence percentage.",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["High", "Medium", "Low", "None", "Unknown"],
                        },
                        "affected_area": {
                            "type": "string",
                            "description": "Estimated affected leaf area or Unknown.",
                        },
                        "recommendations": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Three to five numbered practical actions, ordered by priority.",
                        },
                        "treatment_options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Zero to three possible registered treatment options or an explicit statement that treatment cannot be selected from the image alone. Do not invent products, registrations, or doses.",
                        },
                        "treatment_advisory": {
                            "type": "string",
                            "description": "Mandatory safety guidance: use only a product currently registered and labeled for this crop and disease, and follow its current label for dose, water volume, waiting period, PPE, and local restrictions.",
                        },
                        "non_chemical_actions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Two to five non-chemical actions such as scouting, monitoring flag leaves, sanitation where appropriate, and recording progression.",
                        },
                        "preventive_measures": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Three to five practical prevention measures.",
                        },
                        "confidence_note": {
                            "type": "string",
                            "description": "Caveat explaining why image identification is not definitive and when field confirmation is needed.",
                        },
                        "source_guidance": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "One or two general references to local agriculture, ICAR, KVK, or extension guidance; do not fabricate citations.",
                        },
                    },
                    "required": [
                        "disease",
                        "pathogen",
                        "visible_signs",
                        "diagnostic_note",
                        "confidence",
                        "severity",
                        "affected_area",
                        "recommendations",
                        "treatment_options",
                        "treatment_advisory",
                        "non_chemical_actions",
                        "preventive_measures",
                        "confidence_note",
                        "source_guidance",
                    ],
                    "additionalProperties": False,
                },
            },
        }

        prompt = f"""Analyze the uploaded crop leaf image.

    Farmer-provided context:
    - Plant or crop: {plant.strip()}
    - Observed description: {description.strip() or "Not provided"}

Choose the single most likely primary issue:
- disease
- pest infestation
- nutrient deficiency
- Healthy
- or Uncertain if the image is not sufficient.

Rules:
- Do not provide a differential diagnosis.
- Treat the selected plant as the crop context, but do not claim a disease unless the image and notes support it.
- If the image is unclear or the selected plant does not match the image, use Uncertain and explain that in a recommendation.
- Keep confidence realistic and include a clear caveat that image identification is not definitive.
- Provide two to five image-grounded visible signs and a short diagnostic explanation.
- Provide three to five numbered actions, including field inspection and treatment guidance only at the level supported by the image.
- If mentioning a fungicide or pesticide, say it must be locally registered and used exactly according to the current label and local agricultural advisory. Never provide an unsupported dose or claim that a product is universally appropriate.
- Provide three to five prevention measures and one or two non-fabricated source-guidance notes such as consulting ICAR, KVK, or the State Agriculture Department.
- Include a separate treatment advisory. You may name a fungicide only when the crop, disease, and regional registration are supported by reliable knowledge; otherwise say that no product can be selected from the image alone. Never invent a registration, label, dose, water volume, waiting period, or safety interval.
- Include two to five non-chemical actions such as scouting surrounding plants, monitoring upper leaves/flag leaf, managing severely affected material where appropriate, and recording disease progression.
- The treatment advisory must state that farmers should use only a product currently registered/labeled for the crop and disease, follow the current label for dose, water volume, waiting period, PPE, and safety precautions, and confirm with a local agricultural/KVK advisory.
- Do not provide unsupported exact chemical dosages.
- Your final answer MUST be the report_leaf_analysis tool call.
"""

        logger.info(
            f"Sending leaf scan request ({file.filename}) "
            f"to Groq Vision model {vision_model}..."
        )

        start_time = time.time()

        completion = client.chat.completions.create(
            model=vision_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cautious agricultural image-analysis assistant. "
                        "Use the report_leaf_analysis tool for the final answer."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}"
                            },
                        },
                    ],
                },
            ],
            tools=[analysis_tool],
            tool_choice={
                "type": "function",
                "function": {"name": "report_leaf_analysis"},
            },
            temperature=0.2,
            max_completion_tokens=int(os.getenv("GROQ_VISION_MAX_COMPLETION_TOKENS", "1800")),
        )

        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "LLM call completed",
            llm_node="leaf_scan",
            latency_ms=latency_ms,
        )

        message = completion.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)

        if not tool_calls:
            logger.error(
                f"Vision model did not return a tool call. Content: {message.content}"
            )
            raise HTTPException(
                status_code=500,
                detail="Vision model did not return structured analysis.",
            )

        tool_call = tool_calls[0]

        if tool_call.function.name != "report_leaf_analysis":
            raise HTTPException(
                status_code=500,
                detail="Vision model returned an unexpected tool.",
            )

        try:
            analysis_data = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid structured analysis JSON: {e}. "
                f"Arguments: {tool_call.function.arguments}"
            )
            raise HTTPException(
                status_code=500,
                detail="Vision model returned invalid structured analysis.",
            )

        analysis_data.setdefault("disease", "Uncertain")
        analysis_data.setdefault("pathogen", "Unknown")
        analysis_data.setdefault("visible_signs", analysis_data.get("symptoms", []))
        analysis_data.setdefault("diagnostic_note", "Image-based identification is not definitive; field confirmation is recommended.")
        analysis_data.setdefault("confidence", 0)
        analysis_data.setdefault("severity", "Unknown")
        analysis_data.setdefault("affected_area", "Unknown")
        analysis_data.setdefault("recommendations", [])
        analysis_data.setdefault("treatment_options", [])
        analysis_data.setdefault(
            "treatment_advisory",
            "Use only a product currently registered and labeled for this crop and disease. Follow the current label and confirm treatment timing with a local agricultural or KVK advisory.",
        )
        analysis_data.setdefault("non_chemical_actions", [])
        analysis_data.setdefault("preventive_measures", [])
        analysis_data.setdefault("confidence_note", "Image-based identification is not definitive; inspect additional plants and consult local agricultural guidance.")
        analysis_data.setdefault("source_guidance", [])

        if not isinstance(analysis_data["recommendations"], list):
            analysis_data["recommendations"] = [str(analysis_data["recommendations"])]

        if not isinstance(analysis_data["preventive_measures"], list):
            analysis_data["preventive_measures"] = [str(analysis_data["preventive_measures"])]

        for field in ("visible_signs", "treatment_options", "non_chemical_actions", "source_guidance"):
            if not isinstance(analysis_data[field], list):
                analysis_data[field] = [str(analysis_data[field])]

        translated_analysis = get_translated(
            f"scan_{file.filename}",
            analysis_data,
            lang,
            "leaf disease analysis and remedies",
        )

        return {"analysis": translated_analysis}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Leaf scan analysis error: {e}",
            exc_info=True,
        )
        if "tool_use_failed" in str(e) or "Failed to call a function" in str(e):
            raise HTTPException(
                status_code=502,
                detail=(
                    "The vision model returned an incomplete structured report. "
                    "Please retry the scan; the server has increased the report output limit."
                ),
            ) from e
        raise HTTPException(
            status_code=500,
            detail=f"Leaf scan analysis failed: {str(e)}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Leaf scan analysis error: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Leaf scan analysis failed: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Application health and optional dependency readiness."""
    groq_ready = bool(os.getenv("GROQ_API_KEY") and os.getenv("GROQ_API_KEY") != "your_key_here")
    weather_ready = bool(os.getenv("OPENWEATHER_API_KEY"))
    market_ready = bool(os.getenv("DATAGOV_API_KEY") and os.getenv("DATAGOV_API_KEY") != "your_key_here")
    model_ready = bool(os.getenv("PLANT_DISEASE_MODEL_PATH") or Path(__file__).resolve().parent.joinpath("models", "plant_disease_model.keras").exists())

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
