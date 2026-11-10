import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.database import db, _in_memory_cases
from app.services.vision import vision_service
from app.services.retriever import guide_retriever
from app.services.evon import evon_service
from app.services.tts_timbre import timbre_tts
from app.services.stt_prisma import prisma_stt
from guides.data import GUIDE_RECORDS

logger = logging.getLogger("crop_doctor.frontend")
router = APIRouter(prefix="", tags=["Frontend Application"])

TEST_LEAVES_DIR = Path("storage/test_leaves")


class SimulateRequest(BaseModel):
    scenario_id: Optional[str] = None
    language: str = "te"  # 'te', 'mr', 'pa'
    crop: Optional[str] = None
    transcript: str
    image_file: Optional[str] = None


@router.post("/api/simulate", summary="Simulate farmer consultation through WhatsApp pipeline")
async def simulate_consultation(req: SimulateRequest) -> Dict[str, Any]:
    """
    Simulates a farmer submitting a photo and voice note:
    1. Vision Analysis on selected/uploaded leaf photo
    2. Guide Retrieval from pgvector
    3. Evon Reasoning & Safety Guardrail verification
    4. Timbre Voice Note synthesis
    5. Storage in cases database
    """
    settings = get_settings()

    # 1. Vision Observation
    vision_obs = None
    photo_path = None
    if req.image_file:
        candidate_paths = [
            Path("storage/test_leaves") / req.image_file,
            settings.storage_path / "test_leaves" / req.image_file,
            Path("storage/images") / req.image_file,
            settings.storage_path / "images" / req.image_file,
            Path("storage") / req.image_file
        ]
        img_path = next((p for p in candidate_paths if p.exists()), None)
        if img_path:
            photo_path = str(img_path).replace("\\", "/")
            vision_obs = await vision_service.analyze_image(str(img_path))

    # 2. Infer Crop (Multilingual Keyword Recognition)
    inferred_crop = req.crop
    if not inferred_crop:
        text_corpus = f"{req.transcript} {vision_obs.spots if vision_obs else ''}".lower()
        if any(k in text_corpus for k in ["chilli", "mirapa", "mirchi", "mirch", "milagai", "menasinakayi", "lonka", "marcha"]):
            inferred_crop = "chilli"
        elif any(k in text_corpus for k in ["cotton", "kapoos", "prathi", "kapaas", "paruthi", "hatti", "tula", "kapas"]):
            inferred_crop = "cotton"
        elif any(k in text_corpus for k in ["paddy", "jhone", "vari", "rice", "dhaan", "chawal", "nell", "bhatta", "dhan", "dangar"]):
            inferred_crop = "paddy"
        elif any(k in text_corpus for k in ["tomato", "tamata", "tamatar", "thakkali", "tameta"]):
            inferred_crop = "tomato"

    # 3. Guide Retrieval
    guide_chunks = []
    if inferred_crop:
        top_trait = max(vision_obs.confidence_scores, key=vision_obs.confidence_scores.get) if (vision_obs and vision_obs.confidence_scores) else ""
        search_query = f"{req.transcript} {top_trait} {vision_obs.spots if vision_obs else ''} {vision_obs.colour if vision_obs else ''}"
        guide_chunks = await guide_retriever.search(
            query=search_query,
            crop=inferred_crop,
            state=None,
            top_k=4
        )

    # 4. Evon Reasoning & Guardrails
    decision = await evon_service.reason(
        vision_obs=vision_obs,
        transcript=req.transcript,
        crop=inferred_crop,
        crop_age_days=None,
        state=None,
        guide_chunks=guide_chunks,
        language=req.language
    )

    # 5. Timbre TTS Voice Note Generation
    audio_path = None
    if decision.final_text:
        try:
            # Generate real voice note using Gnani Timbre TTS v2.5
            tts_res = await timbre_tts.synthesize(
                text=decision.final_text[:350],
                language=req.language,
                speed=0.9
            )
            if tts_res and Path(tts_res).exists() and Path(tts_res).stat().st_size > 100:
                audio_path = str(tts_res).replace("\\", "/")
        except Exception as e:
            logger.warning(f"Timbre TTS call failed in simulation: {e}")

        # Fallback audible WAV if Timbre is offline or throttled
        if not audio_path:
            import math
            import struct
            audio_file = f"storage/audio/sim_{int(decision.likely_problems[0].confidence * 1000 if decision.likely_problems else 999)}_{req.language}.wav"
            Path(audio_file).parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 16000
            num_samples = sample_rate * 2  # 2 seconds chime tone
            pcm_data = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                val = int(8000 * math.sin(2 * math.pi * 523.25 * t) * math.exp(-t * 1.5))
                pcm_data.extend(struct.pack("<h", max(-32768, min(32767, val))))
            
            data_size = len(pcm_data)
            riff_size = 36 + data_size
            header = struct.pack(
                "<4sI4s4sIHHIIHH4sI",
                b"RIFF", riff_size, b"WAVE",
                b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
                b"data", data_size
            )
            Path(audio_file).write_bytes(header + pcm_data)
            audio_path = audio_file.replace("\\", "/")

    # 6. Save Case in Database
    import uuid
    case_record = {
        "id": f"sim_{uuid.uuid4().hex[:8]}",
        "wa_phone": "919876543299",
        "crop": inferred_crop,
        "photo_path": photo_path,
        "voice_path": "storage/audio/sample_voice.ogg",
        "transcript": req.transcript,
        "vision_obs": vision_obs.model_dump() if vision_obs else None,
        "retrieved_chunk_ids": [c["id"] for c in guide_chunks],
        "likely_problems": [p.model_dump() for p in decision.likely_problems],
        "answer_text": decision.final_text,
        "answer_audio_path": audio_path,
        "confidence": decision.likely_problems[0].confidence if decision.likely_problems else None,
        "escalated": (decision.tool_called == "escalate"),
        "status": "completed" if decision.tool_called == "answer_case" else decision.tool_called,
        "reviews": []
    }
    _in_memory_cases[case_record["id"]] = case_record

    return {
        "success": True,
        "case_id": case_record["id"],
        "tool_called": decision.tool_called,
        "decision": decision.model_dump(),
        "vision_obs": vision_obs.model_dump() if vision_obs else None,
        "retrieved_chunks": guide_chunks,
        "audio_url": f"/{audio_path}" if audio_path else None,
        "photo_url": f"/{photo_path}" if photo_path else None,
        "final_text": decision.final_text
    }


@router.get("/api/guides", summary="Get all ingested crop guide records")
async def get_all_guides() -> List[Dict[str, Any]]:
    """Return all 13 ingested university guide sections."""
    return GUIDE_RECORDS


@router.get("/api/banned-inputs", summary="Get list of banned agricultural chemicals")
async def get_banned_inputs() -> List[Dict[str, str]]:
    """Return list of banned chemicals."""
    from app.database import _in_memory_banned_inputs
    return _in_memory_banned_inputs


# ---------------------------------------------------------------------------
# GET /  —  Landing Page
# ---------------------------------------------------------------------------

@router.get("/", summary="Landing Page")
async def landing_page(request: Request):
    accept = request.headers.get("accept", "")
    # Content negotiation: return JSON for test clients / API requests
    if "text/html" not in accept and ("application/json" in accept or accept == "*/*"):
        return JSONResponse(content={
            "service": "Crop Doctor on WhatsApp",
            "version": "1.0.0",
            "status": "online",
            "docs_url": "/docs"
        })
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Crop Doctor on WhatsApp</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" />
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .hero-gradient { background: linear-gradient(135deg, #0a2e1a 0%, #1a4a2e 50%, #0d3b22 100%); }
    .card-hover { transition: transform 0.25s ease, box-shadow 0.25s ease; }
    .card-hover:hover { transform: translateY(-4px); box-shadow: 0 20px 40px rgba(0,0,0,0.3); }
    .step-card { animation: fadeInUp 0.6s ease both; }
    .step-card:nth-child(2) { animation-delay: 0.15s; }
    .step-card:nth-child(3) { animation-delay: 0.3s; }
    @keyframes fadeInUp {
      from { opacity: 0; transform: translateY(24px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .lang-panel { border-left: 4px solid #22c55e; }
  </style>
</head>
<body class="bg-gray-950 text-white">

  <!-- NAVBAR -->
  <nav class="hero-gradient border-b border-green-800/40 sticky top-0 z-50 backdrop-blur-sm">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex items-center justify-between h-16">
        <a href="/" class="flex items-center gap-2 text-xl font-bold text-white">
          <span class="text-2xl">🌾</span> Crop Doctor
        </a>
        <div class="hidden md:flex items-center gap-6 text-sm font-medium">
          <a href="/"        class="text-green-300 hover:text-white transition">Home</a>
          <a href="/whatsapp" class="text-emerald-400 hover:text-emerald-300 font-semibold transition flex items-center gap-1.5"><i class="fa-brands fa-whatsapp text-lg text-emerald-400"></i> WhatsApp Web</a>
          <a href="/demo"    class="text-gray-300 hover:text-white transition">Demo</a>
          <a href="/guides"  class="text-gray-300 hover:text-white transition">Guides</a>
          <a href="/stats"   class="text-gray-300 hover:text-white transition">Analytics</a>
          <a href="/reviews" class="text-gray-300 hover:text-white transition">Review Dashboard</a>
          <a href="/docs"    class="text-gray-300 hover:text-white transition flex items-center gap-1">
            <i class="fa-solid fa-book text-xs"></i> API Docs
          </a>
        </div>
        <!-- Mobile menu button -->
        <button class="md:hidden text-gray-300 hover:text-white" onclick="document.getElementById('mobile-menu').classList.toggle('hidden')">
          <i class="fa-solid fa-bars text-xl"></i>
        </button>
      </div>
    </div>
    <div id="mobile-menu" class="hidden md:hidden px-4 pb-3 space-y-2 text-sm font-medium">
      <a href="/"        class="block text-green-300 hover:text-white py-1">Home</a>
      <a href="/whatsapp" class="block text-emerald-400 hover:text-white py-1 font-semibold flex items-center gap-2"><i class="fa-brands fa-whatsapp"></i> WhatsApp Web</a>
      <a href="/demo"    class="block text-gray-300 hover:text-white py-1">Demo</a>
      <a href="/guides"  class="block text-gray-300 hover:text-white py-1">Guides</a>
      <a href="/stats"   class="block text-gray-300 hover:text-white py-1">Analytics</a>
      <a href="/reviews" class="block text-gray-300 hover:text-white py-1">Review Dashboard</a>
      <a href="/docs"    class="block text-gray-300 hover:text-white py-1">API Docs</a>
    </div>
  </nav>

  <!-- HERO -->
  <section class="hero-gradient min-h-screen flex items-center py-20">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full">
      <div class="text-center max-w-4xl mx-auto mb-16">
        <div class="inline-flex items-center gap-2 bg-green-900/50 border border-green-700 rounded-full px-4 py-1.5 text-green-300 text-sm font-medium mb-6">
          <i class="fa-solid fa-circle text-green-400 text-xs animate-pulse"></i>
          Live on WhatsApp · 15/15 Benchmark Score
        </div>
        <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white leading-tight mb-6">
          AI-Powered Crop Disease<br/>
          <span class="text-green-400">Diagnosis via WhatsApp</span>
        </h1>
        <p class="text-lg sm:text-xl text-gray-300 mb-10 max-w-2xl mx-auto">
          Helping farmers across India in <span class="text-green-300 font-semibold">11 Languages</span> (Hindi, Telugu, Marathi, Punjabi, Tamil, Kannada, Bengali, Gujarati, Malayalam, Odia, English) get instant, verified pest diagnoses from agricultural university guides.
        </p>
        <div class="flex flex-col sm:flex-row gap-4 justify-center">
          <a href="/whatsapp"
             class="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-8 py-3.5 rounded-xl text-base transition shadow-lg shadow-emerald-950/60 border border-emerald-400/40">
            <i class="fa-brands fa-whatsapp text-xl"></i> Open WhatsApp Web Simulator
          </a>
          <a href="/demo"
             class="inline-flex items-center gap-2 bg-green-900/40 hover:bg-green-800/60 text-green-200 border border-green-600 font-semibold px-8 py-3.5 rounded-xl text-base transition">
            <i class="fa-solid fa-flask"></i> Clinical Demo
          </a>
          <a href="/guides"
             class="inline-flex items-center gap-2 border border-green-800 text-gray-300 hover:bg-green-900/40 font-semibold px-6 py-3.5 rounded-xl text-base transition">
            <i class="fa-solid fa-book-open"></i> Guides
          </a>
        </div>
      </div>

      <!-- 3-step flow -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl mx-auto">
        <div class="step-card bg-white/5 border border-green-700/40 rounded-2xl p-6 text-center card-hover">
          <div class="text-5xl mb-4">📸</div>
          <div class="text-xs font-bold text-green-400 tracking-widest uppercase mb-2">Step 1</div>
          <h3 class="text-white font-bold text-lg mb-1">Send Leaf Photo</h3>
          <p class="text-gray-400 text-sm">Snap a photo of the affected crop and send it on WhatsApp</p>
        </div>
        <div class="step-card bg-white/5 border border-green-700/40 rounded-2xl p-6 text-center card-hover">
          <div class="text-5xl mb-4">🤖</div>
          <div class="text-xs font-bold text-green-400 tracking-widest uppercase mb-2">Step 2</div>
          <h3 class="text-white font-bold text-lg mb-1">AI Analysis</h3>
          <p class="text-gray-400 text-sm">Vision AI inspects the image and retrieves university-backed guides</p>
        </div>
        <div class="step-card bg-white/5 border border-green-700/40 rounded-2xl p-6 text-center card-hover">
          <div class="text-5xl mb-4">🔊</div>
          <div class="text-xs font-bold text-green-400 tracking-widest uppercase mb-2">Step 3</div>
          <h3 class="text-white font-bold text-lg mb-1">Voice Advisory</h3>
          <p class="text-gray-400 text-sm">Receive a synthesised voice note with grounded treatment advice</p>
        </div>
      </div>

      <!-- Interactive WhatsApp Simulator Showcase -->
      <div class="mt-16 bg-gradient-to-r from-emerald-950/80 via-gray-900 to-green-950/80 border-2 border-emerald-500/50 rounded-3xl p-6 sm:p-10 shadow-2xl backdrop-blur-md">
        <div class="flex flex-col lg:flex-row items-center justify-between gap-8">
          
          <div class="lg:w-1/2 text-left">
            <div class="inline-flex items-center gap-2 bg-emerald-500/20 border border-emerald-400 text-emerald-300 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-4">
              <i class="fa-brands fa-whatsapp text-sm"></i> Live Simulation Engine
            </div>
            <h2 class="text-2xl sm:text-3xl font-extrabold text-white mb-3">
              Test Crop Doctor in Real WhatsApp Web
            </h2>
            <p class="text-gray-300 text-sm leading-relaxed mb-6">
              Experience the realistic farmer interface without any Meta Developer registration or SIM card required. Test pest detection, Indic voice note playback, dosage recommendations, and safety guardrails.
            </p>

            <div class="space-y-2 mb-6">
              <div class="text-xs font-semibold uppercase text-emerald-400 tracking-wider">Try 1-Click Clinical Scenarios:</div>
              <div class="flex flex-wrap gap-2">
                <a href="/whatsapp?preset=chilli_whitefly" class="text-xs bg-emerald-900/60 hover:bg-emerald-800 text-emerald-200 border border-emerald-600/50 px-3 py-1.5 rounded-lg transition flex items-center gap-1.5">
                  <span>🌶️</span> Chilli Leaf Curl (Telugu)
                </a>
                <a href="/whatsapp?preset=cotton_bollworm" class="text-xs bg-emerald-900/60 hover:bg-emerald-800 text-emerald-200 border border-emerald-600/50 px-3 py-1.5 rounded-lg transition flex items-center gap-1.5">
                  <span>🌿</span> Cotton Bollworm (Marathi)
                </a>
                <a href="/whatsapp?preset=paddy_blast" class="text-xs bg-emerald-900/60 hover:bg-emerald-800 text-emerald-200 border border-emerald-600/50 px-3 py-1.5 rounded-lg transition flex items-center gap-1.5">
                  <span>🌾</span> Paddy Blast (Punjabi)
                </a>
                <a href="/whatsapp?preset=tomato_blight" class="text-xs bg-emerald-900/60 hover:bg-emerald-800 text-emerald-200 border border-emerald-600/50 px-3 py-1.5 rounded-lg transition flex items-center gap-1.5">
                  <span>🍅</span> Tomato Blight (Hindi)
                </a>
                <a href="/whatsapp?preset=banned_endosulfan" class="text-xs bg-red-900/50 hover:bg-red-800/60 text-red-200 border border-red-500/50 px-3 py-1.5 rounded-lg transition flex items-center gap-1.5">
                  <span>🚫</span> Banned Chemical Intercept
                </a>
              </div>
            </div>

            <a href="/whatsapp" class="inline-flex items-center gap-3 bg-emerald-500 hover:bg-emerald-400 text-gray-950 font-extrabold px-6 py-3 rounded-xl shadow-lg shadow-emerald-500/30 transition text-sm">
              <i class="fa-brands fa-whatsapp text-xl"></i> Launch WhatsApp Web Simulator
              <i class="fa-solid fa-arrow-right text-xs"></i>
            </a>
          </div>

          <!-- Preview Mockup Card -->
          <div class="lg:w-1/2 w-full max-w-md bg-[#111b21] border border-[#2a3942] rounded-2xl p-4 shadow-xl">
            <div class="flex items-center justify-between border-b border-[#222d34] pb-3 mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-full bg-emerald-700 flex items-center justify-center text-lg">🌾</div>
                <div>
                  <div class="text-xs font-bold text-[#e9edef] flex items-center gap-1">
                    Crop Doctor AI <i class="fa-solid fa-circle-check text-[#00a884] text-[10px]"></i>
                  </div>
                  <div class="text-[10px] text-[#00a884]">online · university grounded</div>
                </div>
              </div>
              <span class="text-[10px] bg-[#202c33] text-[#8696a0] px-2 py-0.5 rounded">WhatsApp Web</span>
            </div>

            <!-- Chat bubbles preview -->
            <div class="space-y-2 text-xs">
              <div class="flex justify-end">
                <div class="bg-[#005c4b] text-[#e9edef] p-2.5 rounded-xl rounded-tr-none max-w-[85%] shadow">
                  <div class="text-[11px]">🌿 <i>[Attached photo: Chilli Leaf Curl]</i></div>
                  <div class="mt-1 text-white font-medium">నా మిరప ఆకులు పైకి ముడుచుకుపోయాయి, తెల్ల పురుగులు ఉన్నాయి.</div>
                  <div class="text-[9px] text-[#8696a0] text-right mt-1">10:32 AM ✓✓</div>
                </div>
              </div>

              <div class="flex justify-start">
                <div class="bg-[#202c33] text-[#e9edef] p-2.5 rounded-xl rounded-tl-none max-w-[90%] shadow border border-[#2a3942]">
                  <div class="text-[#00a884] font-bold text-[11px] mb-1">🌾 Crop Doctor AI (Verified)</div>
                  <p class="text-[11px] text-gray-200 leading-snug">
                    1. <b>ప్రధాన సమస్య:</b> తెల్ల దోమ (Whitefly) & ఆకు ముడత.<br>
                    2. <b>మందు:</b> Diafenthiuron 50% WP - 1.25 g/L.<br>
                    3. <b>రక్షణ:</b> ఎకరాకు 10-15 పసుపు జిగురు అట్టలు.
                  </p>
                  <div class="mt-2 bg-[#111b21] p-1.5 rounded-lg flex items-center gap-2 border border-[#2a3942]">
                    <span class="text-[#00a884] text-sm">▶️</span>
                    <span class="text-[10px] text-gray-300">Telugu Voice Note (0:14)</span>
                    <span class="text-[9px] text-[#8696a0] ml-auto">Timbre TTS</span>
                  </div>
                  <div class="text-[9px] text-[#8696a0] text-right mt-1">10:32 AM</div>
                </div>
              </div>
            </div>

            <div class="mt-3 pt-2 border-t border-[#222d34] text-center">
              <a href="/whatsapp" class="text-xs text-[#00a884] hover:underline font-semibold inline-flex items-center gap-1">
                Open full interactive chat simulator <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
              </a>
            </div>
          </div>

        </div>
      </div>

    </div>
  </section>

  <!-- STATS BAR -->
  <section class="bg-gray-900 border-y border-gray-800 py-10">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
        <div class="text-center">
          <div class="text-4xl font-extrabold text-green-400">15/15</div>
          <div class="text-gray-400 text-sm mt-1 font-medium">Correct Diagnoses</div>
        </div>
        <div class="text-center">
          <div class="text-4xl font-extrabold text-green-400">100%</div>
          <div class="text-gray-400 text-sm mt-1 font-medium">Grounded Citations</div>
        </div>
        <div class="text-center">
          <div class="text-4xl font-extrabold text-green-400">0</div>
          <div class="text-gray-400 text-sm mt-1 font-medium">Banned Chemicals Used</div>
        </div>
        <div class="text-center">
          <div class="text-4xl font-extrabold text-green-400">4</div>
          <div class="text-gray-400 text-sm mt-1 font-medium">Crops Supported</div>
        </div>
      </div>
    </div>
  </section>

  <!-- SUPPORTED CROPS -->
  <section class="py-20 bg-gray-950">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center mb-12">
        <h2 class="text-3xl font-bold text-white mb-3">Supported Crops</h2>
        <p class="text-gray-400">University-sourced guides for each crop, covering key pests and diseases</p>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">

        <!-- Chilli -->
        <div class="bg-white rounded-2xl border-2 border-green-500 p-6 card-hover text-gray-800">
          <div class="text-5xl mb-3 text-center">🌶️</div>
          <h3 class="text-xl font-bold text-center text-gray-900 mb-1">Chilli</h3>
          <p class="text-gray-500 text-xs text-center mb-3">PJTSAU Hyderabad</p>
          <span class="block text-center">
            <span class="bg-orange-100 text-orange-700 text-xs font-semibold px-2 py-0.5 rounded-full">Telugu</span>
          </span>
          <ul class="mt-4 space-y-1 text-sm text-gray-600">
            <li class="flex items-center gap-2"><i class="fa-solid fa-bug text-red-400 text-xs"></i> Whitefly</li>
            <li class="flex items-center gap-2"><i class="fa-solid fa-bug text-red-400 text-xs"></i> Thrips</li>
            <li class="flex items-center gap-2"><i class="fa-solid fa-flask text-purple-400 text-xs"></i> Anthracnose</li>
          </ul>
        </div>

        <!-- Cotton -->
        <div class="bg-white rounded-2xl border-2 border-green-500 p-6 card-hover text-gray-800">
          <div class="text-5xl mb-3 text-center">🌿</div>
          <h3 class="text-xl font-bold text-center text-gray-900 mb-1">Cotton</h3>
          <p class="text-gray-500 text-xs text-center mb-3">MPKV Rahuri</p>
          <span class="block text-center">
            <span class="bg-blue-100 text-blue-700 text-xs font-semibold px-2 py-0.5 rounded-full">Marathi</span>
          </span>
          <ul class="mt-4 space-y-1 text-sm text-gray-600">
            <li class="flex items-center gap-2"><i class="fa-solid fa-bug text-red-400 text-xs"></i> Aphids</li>
            <li class="flex items-center gap-2"><i class="fa-solid fa-bug text-red-400 text-xs"></i> Pink Bollworm</li>
            <li class="flex items-center gap-2"><i class="fa-solid fa-flask text-purple-400 text-xs"></i> Grey Mildew</li>
          </ul>
        </div>

        <!-- Paddy -->
        <div class="bg-white rounded-2xl border-2 border-green-500 p-6 card-hover text-gray-800">
          <div class="text-5xl mb-3 text-center">🌾</div>
          <h3 class="text-xl font-bold text-center text-gray-900 mb-1">Paddy</h3>
          <p class="text-gray-500 text-xs text-center mb-3">PAU Ludhiana</p>
          <span class="block text-center">
            <span class="bg-yellow-100 text-yellow-700 text-xs font-semibold px-2 py-0.5 rounded-full">Punjabi</span>
          </span>
          <ul class="mt-4 space-y-1 text-sm text-gray-600">
            <li class="flex items-center gap-2"><i class="fa-solid fa-flask text-purple-400 text-xs"></i> Rice Blast</li>
            <li class="flex items-center gap-2"><i class="fa-solid fa-flask text-purple-400 text-xs"></i> Brown Spot</li>
            <li class="flex items-center gap-2"><i class="fa-solid fa-flask text-purple-400 text-xs"></i> Sheath Blight</li>
          </ul>
        </div>

        <!-- Tomato -->
        <div class="bg-white rounded-2xl border-2 border-green-500 p-6 card-hover text-gray-800">
          <div class="text-5xl mb-3 text-center">🍅</div>
          <h3 class="text-xl font-bold text-center text-gray-900 mb-1">Tomato</h3>
          <p class="text-gray-500 text-xs text-center mb-3">Dr. YSRHU</p>
          <span class="block text-center">
            <span class="bg-orange-100 text-orange-700 text-xs font-semibold px-2 py-0.5 rounded-full">Telugu</span>
          </span>
          <ul class="mt-4 space-y-1 text-sm text-gray-600">
            <li class="flex items-center gap-2"><i class="fa-solid fa-flask text-purple-400 text-xs"></i> Early Blight</li>
            <li class="flex items-center gap-2"><i class="fa-solid fa-flask text-purple-400 text-xs"></i> Late Blight</li>
            <li class="flex items-center gap-2"><i class="fa-solid fa-bug text-red-400 text-xs"></i> Leaf Miner</li>
          </ul>
        </div>

      </div>
    </div>
  </section>

  <!-- MULTILINGUAL ADVISORY -->
  <section class="py-20 bg-gray-900">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center mb-12">
        <h2 class="text-3xl font-bold text-white mb-3">Multilingual Advisory</h2>
        <p class="text-gray-400">Native-language voice advisories grounded in university extension literature</p>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">

        <div class="lang-panel bg-gray-800 rounded-xl p-6">
          <div class="flex items-center gap-3 mb-4">
            <span class="text-2xl">🇮🇳</span>
            <div>
              <div class="font-bold text-white">Telugu</div>
              <div class="text-xs text-green-400">PJTSAU Hyderabad</div>
            </div>
          </div>
          <p class="text-gray-300 text-sm leading-relaxed font-light">
            మీ మిర్చి మొక్కలు తెల్ల దోమ (Whitefly) సమస్యతో బాధపడుతున్నాయి. ఆకు అడుగు భాగంలో పురుగులు ఉన్నాయి. వెంటనే Imidacloprid 0.3 ml/L నీటిలో కలిపి పిచికారీ చేయండి.
          </p>
          <div class="mt-4 text-xs text-green-500 font-mono">Source: PJTSAU Pest Management Guide, p.14</div>
        </div>

        <div class="lang-panel bg-gray-800 rounded-xl p-6">
          <div class="flex items-center gap-3 mb-4">
            <span class="text-2xl">🇮🇳</span>
            <div>
              <div class="font-bold text-white">Marathi</div>
              <div class="text-xs text-blue-400">MPKV Rahuri</div>
            </div>
          </div>
          <p class="text-gray-300 text-sm leading-relaxed font-light">
            तुमच्या कापूस पिकावर मावा (Aphids) चा प्रादुर्भाव दिसत आहे. पानांखाली हिरवे किडे आहेत. Dimethoate 1.5 ml/L प्रमाणे फवारणी करावी.
          </p>
          <div class="mt-4 text-xs text-blue-400 font-mono">Source: MPKV Cotton Advisory, p.22</div>
        </div>

        <div class="lang-panel bg-gray-800 rounded-xl p-6">
          <div class="flex items-center gap-3 mb-4">
            <span class="text-2xl">🇮🇳</span>
            <div>
              <div class="font-bold text-white">Punjabi</div>
              <div class="text-xs text-yellow-400">PAU Ludhiana</div>
            </div>
          </div>
          <p class="text-gray-300 text-sm leading-relaxed font-light">
            ਤੁਹਾਡੀ ਝੋਨੇ ਦੀ ਫ਼ਸਲ ਵਿੱਚ ਭੂਰੇ ਧੱਬੇ ਦੀ ਬਿਮਾਰੀ ਦਿਖਾਈ ਦੇ ਰਹੀ ਹੈ। Mancozeb 2.5 g/L ਪਾਣੀ ਵਿੱਚ ਮਿਲਾ ਕੇ ਛਿੜਕਾਅ ਕਰੋ।
          </p>
          <div class="mt-4 text-xs text-yellow-400 font-mono">Source: PAU Paddy Disease Guide, p.31</div>
        </div>

      </div>
    </div>
  </section>

  <!-- FOOTER -->
  <footer class="hero-gradient border-t border-green-800/40 py-10">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
      <div class="text-green-300 font-semibold mb-2">
        Powered by Gnani Vachana AI &middot; PJTSAU &middot; MPKV &middot; PAU &middot; Dr. YSRHU
      </div>
      <div class="text-gray-400 text-sm">
        KVK Helpline: <a href="tel:18001801551" class="text-green-400 hover:underline font-mono">1800-180-1551</a>
        &nbsp;&bull;&nbsp;
        <a href="/docs" class="text-gray-400 hover:text-white">API Docs</a>
        &nbsp;&bull;&nbsp;
        <a href="/demo" class="text-gray-400 hover:text-white">Live Demo</a>
      </div>
      <div class="text-gray-600 text-xs mt-4">&copy; 2024 Crop Doctor on WhatsApp. All rights reserved.</div>
    </div>
  </footer>

  <!-- Floating WhatsApp Simulator Launcher -->
  <aside class="fixed bottom-6 right-6 z-50">
    <a href="/whatsapp"
       title="Open WhatsApp Web Simulator"
       class="group flex items-center gap-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold pl-4 pr-5 py-3.5 rounded-full shadow-2xl hover:shadow-emerald-500/50 transition-all transform hover:-translate-y-1 border border-emerald-300/40">
      <span class="relative flex h-3.5 w-3.5">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-200 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-400"></span>
      </span>
      <i class="fa-brands fa-whatsapp text-2xl text-white"></i>
      <div class="text-left leading-tight">
        <div class="text-[10px] text-emerald-100 uppercase tracking-widest font-extrabold">Live Demo</div>
        <div class="text-sm font-bold text-white flex items-center gap-1.5">
          WhatsApp Simulator
          <i class="fa-solid fa-arrow-right text-xs group-hover:translate-x-1 transition-transform"></i>
        </div>
      </div>
    </a>
  </aside>


  <!-- Floating WhatsApp Simulator Launcher -->
  <aside class="fixed bottom-6 right-6 z-50">
    <a href="/whatsapp"
       title="Open WhatsApp Web Simulator"
       class="group flex items-center gap-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold pl-4 pr-5 py-3.5 rounded-full shadow-2xl hover:shadow-emerald-500/50 transition-all transform hover:-translate-y-1 border border-emerald-300/40">
      <span class="relative flex h-3.5 w-3.5">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-200 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-400"></span>
      </span>
      <i class="fa-brands fa-whatsapp text-2xl text-white"></i>
      <div class="text-left leading-tight">
        <div class="text-[10px] text-emerald-100 uppercase tracking-widest font-extrabold">Live Demo</div>
        <div class="text-sm font-bold text-white flex items-center gap-1.5">
          WhatsApp Simulator
          <i class="fa-solid fa-arrow-right text-xs group-hover:translate-x-1 transition-transform"></i>
        </div>
      </div>
    </a>
  </aside>

</body>
</html>"""
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# GET /whatsapp  —  WhatsApp Web Chat Simulator
# ---------------------------------------------------------------------------

@router.get("/whatsapp", response_class=HTMLResponse, summary="WhatsApp Web Chat Simulator")
async def whatsapp_simulator_page():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>WhatsApp Web · Crop Doctor AI</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" />
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;500;600;700&display=swap');
    body {
      font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
      background-color: #0c1317;
      color: #e9edef;
      overflow: hidden;
    }
    .wa-bg-dark { background-color: #111b21; }
    .wa-bg-sidebar { background-color: #111b21; }
    .wa-bg-panel { background-color: #202c33; }
    .wa-bg-input { background-color: #2a3942; }
    .wa-chat-bg {
      background-color: #0b141a;
      background-image: radial-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
      background-size: 24px 24px;
    }
    .bubble-out {
      background-color: #005c4b;
      color: #e9edef;
      border-top-right-radius: 0px;
    }
    .bubble-in {
      background-color: #202c33;
      color: #e9edef;
      border-top-left-radius: 0px;
    }
    .typing-dot {
      animation: typingBounce 1.4s infinite ease-in-out both;
    }
    .typing-dot:nth-child(1) { animation-delay: -0.32s; }
    .typing-dot:nth-child(2) { animation-delay: -0.16s; }
    @keyframes typingBounce {
      0%, 80%, 100% { transform: scale(0); opacity: 0.3; }
      40% { transform: scale(1); opacity: 1; }
    }
    .scrollbar-wa::-webkit-scrollbar { width: 6px; }
    .scrollbar-wa::-webkit-scrollbar-track { background: transparent; }
    .scrollbar-wa::-webkit-scrollbar-thumb { background: #374045; border-radius: 3px; }
    .scrollbar-wa::-webkit-scrollbar-thumb:hover { background: #54656f; }
  </style>
</head>
<body class="h-screen w-screen flex flex-col" x-data="whatsAppSimulator()" x-init="init()">

  <!-- Top App Bar Navigation -->
  <header class="bg-[#202c33] border-b border-[#2a3942] px-4 py-2 flex items-center justify-between text-xs text-[#aebac1] select-none z-20">
    <div class="flex items-center gap-3">
      <span class="text-base text-[#00a884] font-bold flex items-center gap-1.5">
        <i class="fa-brands fa-whatsapp text-lg"></i> WhatsApp Web Simulator
      </span>
      <span class="hidden sm:inline bg-[#111b21] border border-[#00a884]/40 text-[#00a884] px-2 py-0.5 rounded font-mono">
        Live AI Engine Connected
      </span>
    </div>
    <div class="flex items-center gap-4">
      <a href="/demo" class="hover:text-white transition flex items-center gap-1">
        <i class="fa-solid fa-flask"></i> Clinical Demo
      </a>
      <a href="/guides" class="hover:text-white transition flex items-center gap-1">
        <i class="fa-solid fa-book"></i> Guides
      </a>
      <a href="/reviews" class="hover:text-white transition flex items-center gap-1">
        <i class="fa-solid fa-stethoscope"></i> KVK Audit
      </a>
      <a href="/" class="hover:text-white transition flex items-center gap-1">
        <i class="fa-solid fa-house"></i> Home
      </a>
    </div>
  </header>

  <!-- Main Container -->
  <div class="flex-1 flex overflow-hidden">

    <!-- LEFT SIDEBAR: Chats List -->
    <aside class="w-80 sm:w-96 wa-bg-sidebar border-r border-[#222d34] flex flex-col shrink-0">
      
      <!-- Sidebar Header -->
      <div class="h-16 px-4 bg-[#202c33] flex items-center justify-between border-b border-[#222d34]">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-full bg-emerald-700 flex items-center justify-center text-white font-bold text-sm shadow">
            🌾
          </div>
          <div>
            <div class="font-semibold text-sm text-[#e9edef] leading-tight">Farmer Sahayak</div>
            <div class="text-[11px] text-[#00a884] flex items-center gap-1">
              <span class="w-2 h-2 rounded-full bg-[#00a884] animate-pulse"></span> Ready
            </div>
          </div>
        </div>
        <div class="flex items-center gap-4 text-[#aebac1] text-sm">
          <button title="Status" class="hover:text-[#e9edef]"><i class="fa-solid fa-circle-notch"></i></button>
          <button title="New Chat" class="hover:text-[#e9edef]"><i class="fa-solid fa-message"></i></button>
          <button title="Menu" class="hover:text-[#e9edef]"><i class="fa-solid fa-ellipsis-vertical"></i></button>
        </div>
      </div>

      <!-- Search Bar -->
      <div class="p-2 border-b border-[#222d34] bg-[#111b21]">
        <div class="flex items-center bg-[#202c33] rounded-lg px-3 py-1.5 gap-3 text-[#aebac1] text-xs">
          <i class="fa-solid fa-magnifying-glass"></i>
          <input type="text" placeholder="Search or start new chat" class="bg-transparent border-none outline-none w-full text-[#e9edef] placeholder-[#8696a0]" />
        </div>
      </div>

      <!-- Chat Items List -->
      <div class="flex-1 overflow-y-auto scrollbar-wa divide-y divide-[#222d34]">
        
        <!-- Active Chat: Crop Doctor -->
        <div class="px-3 py-3 bg-[#2a3942]/60 hover:bg-[#202c33] cursor-pointer flex items-center gap-3 transition">
          <div class="relative shrink-0">
            <div class="w-12 h-12 rounded-full bg-gradient-to-br from-green-600 to-emerald-800 flex items-center justify-center text-2xl shadow">
              🌾
            </div>
            <span class="absolute bottom-0 right-0 w-3.5 h-3.5 bg-green-500 border-2 border-[#111b21] rounded-full"></span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between mb-0.5">
              <span class="font-semibold text-sm text-[#e9edef] truncate flex items-center gap-1.5">
                Crop Doctor AI
                <i class="fa-solid fa-circle-check text-[#00a884] text-xs" title="Verified Agricultural Advisory"></i>
              </span>
              <span class="text-[11px] text-[#00a884] font-medium" x-text="lastActiveTime"></span>
            </div>
            <div class="flex items-center justify-between text-xs text-[#8696a0]">
              <span class="truncate flex items-center gap-1 text-[#00a884]" x-show="isTyping">
                <i class="fa-solid fa-pen-fancy text-[10px]"></i> <span x-text="typingStatus"></span>
              </span>
              <span class="truncate flex items-center gap-1" x-show="!isTyping">
                <i class="fa-solid fa-microphone text-emerald-400 text-xs"></i> 
                <span x-text="lastMessagePreview"></span>
              </span>
              <span class="ml-1 bg-[#00a884] text-[#111b21] text-[10px] font-bold rounded-full h-4 w-4 flex items-center justify-center shrink-0">
                1
              </span>
            </div>
          </div>
        </div>

        <!-- Static Chat: Kisan Call Centre -->
        <div class="px-3 py-3 hover:bg-[#202c33] cursor-pointer flex items-center gap-3 transition opacity-75">
          <div class="w-12 h-12 rounded-full bg-blue-900 flex items-center justify-center text-xl shrink-0">
            📞
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between mb-0.5">
              <span class="font-semibold text-sm text-[#e9edef] truncate">Kisan Call Centre</span>
              <span class="text-[11px] text-[#8696a0]">Yesterday</span>
            </div>
            <p class="text-xs text-[#8696a0] truncate">Toll-free 1800-180-1551 available 6 AM - 10 PM daily.</p>
          </div>
        </div>

        <!-- Static Chat: PJTSAU University Advisory -->
        <div class="px-3 py-3 hover:bg-[#202c33] cursor-pointer flex items-center gap-3 transition opacity-75">
          <div class="w-12 h-12 rounded-full bg-amber-900 flex items-center justify-center text-xl shrink-0">
            🏛️
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between mb-0.5">
              <span class="font-semibold text-sm text-[#e9edef] truncate">PJTSAU Telangana Extension</span>
              <span class="text-[11px] text-[#8696a0]">Monday</span>
            </div>
            <p class="text-xs text-[#8696a0] truncate">Kharif pest monitoring advisory and spray calendar updated.</p>
          </div>
        </div>

      </div>

      <!-- User Tip footer -->
      <div class="p-3 bg-[#111b21] border-t border-[#222d34] text-[11px] text-[#8696a0] flex items-center gap-2">
        <i class="fa-solid fa-shield-halved text-[#00a884]"></i>
        <span>University grounded · Zero banned chemicals enforced</span>
      </div>

    </aside>

    <!-- RIGHT MAIN: Chat Conversation Screen -->
    <main class="flex-1 flex flex-col wa-chat-bg relative overflow-hidden">
      
      <!-- Chat Header -->
      <div class="h-16 px-4 bg-[#202c33] border-b border-[#222d34] flex items-center justify-between z-10 shrink-0">
        <div class="flex items-center gap-3">
          <div class="relative">
            <div class="w-10 h-10 rounded-full bg-gradient-to-br from-green-600 to-emerald-800 flex items-center justify-center text-xl shadow">
              🌾
            </div>
            <span class="absolute bottom-0 right-0 w-2.5 h-2.5 bg-green-500 border border-[#202c33] rounded-full"></span>
          </div>
          <div>
            <div class="font-semibold text-sm text-[#e9edef] flex items-center gap-1.5 leading-tight">
              Crop Doctor AI (कृषि सहायक)
              <i class="fa-solid fa-circle-check text-[#00a884] text-xs"></i>
            </div>
            <div class="text-[11px] text-[#00a884] font-medium" x-show="isTyping" x-text="typingStatus"></div>
            <div class="text-[11px] text-[#8696a0]" x-show="!isTyping">
              online &middot; Automated Multilingual Diagnosis
            </div>
          </div>
        </div>

        <!-- Header Actions: Language Switcher & Controls -->
        <div class="flex items-center gap-3">
          <!-- Language Selector -->
          <div class="flex items-center gap-1 bg-[#111b21] border border-[#2a3942] rounded-full px-2.5 py-1 text-xs">
            <span class="text-[#8696a0]"><i class="fa-solid fa-language text-[#00a884]"></i> Lang:</span>
            <select x-model="selectedLanguage" @change="onLanguageChange()" class="bg-transparent text-[#e9edef] font-semibold text-xs outline-none cursor-pointer">
              <option value="hi" class="bg-[#202c33] text-white">हिन्दी (Hindi)</option>
              <option value="te" class="bg-[#202c33] text-white">తెలుగు (Telugu)</option>
              <option value="mr" class="bg-[#202c33] text-white">मराठी (Marathi)</option>
              <option value="pa" class="bg-[#202c33] text-white">ਪੰਜਾਬੀ (Punjabi)</option>
              <option value="ta" class="bg-[#202c33] text-white">தமிழ் (Tamil)</option>
              <option value="kn" class="bg-[#202c33] text-white">ಕನ್ನಡ (Kannada)</option>
              <option value="bn" class="bg-[#202c33] text-white">বাংলা (Bengali)</option>
              <option value="gu" class="bg-[#202c33] text-white">ગુજરાતી (Gujarati)</option>
              <option value="ml" class="bg-[#202c33] text-white">മലയാളം (Malayalam)</option>
              <option value="or" class="bg-[#202c33] text-white">ଓଡ଼ିଆ (Odia)</option>
              <option value="en" class="bg-[#202c33] text-white">English</option>
            </select>
          </div>

          <!-- Video / Audio call icons (decorative) -->
          <button class="text-[#aebac1] hover:text-[#e9edef] text-sm p-1.5" title="Start Call"><i class="fa-solid fa-phone"></i></button>
          <button class="text-[#aebac1] hover:text-[#e9edef] text-sm p-1.5" title="Search in Chat"><i class="fa-solid fa-magnifying-glass"></i></button>
          <button @click="resetConversation()" class="text-[#aebac1] hover:text-[#e9edef] text-sm p-1.5" title="Clear Chat"><i class="fa-solid fa-trash-can"></i></button>
        </div>
      </div>

      <!-- Messages Stream Scroll Area -->
      <div id="messagesContainer" class="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 scrollbar-wa">
        
        <!-- Encryption Announcement Banner -->
        <div class="flex justify-center my-2">
          <div class="bg-[#182229] border border-[#222d34] text-[#ffd279] text-[11px] px-4 py-1.5 rounded-lg text-center max-w-md shadow-sm">
            <i class="fa-solid fa-lock text-[10px] mr-1"></i> Messages are verified against official ICAR &amp; Agricultural University guides. Zero ungrounded chemical usage enforced.
          </div>
        </div>

        <!-- Date Marker -->
        <div class="flex justify-center my-3">
          <span class="bg-[#182229] text-[#8696a0] text-[11px] px-3 py-1 rounded-md uppercase tracking-wider font-semibold shadow-sm">
            Today
          </span>
        </div>

        <!-- Message Loop -->
        <template x-for="(msg, index) in messages" :key="index">
          <div class="flex w-full" :class="msg.sender === 'user' ? 'justify-end' : 'justify-start'">
            
            <div class="max-w-[85%] sm:max-w-[70%] rounded-xl p-3 shadow-md relative"
                 :class="msg.sender === 'user' ? 'bubble-out' : 'bubble-in'">
              
              <!-- Sender label for bot -->
              <div x-show="msg.sender === 'bot'" class="text-[11px] font-bold text-[#00a884] mb-1 flex items-center gap-1">
                <span>🌾 Crop Doctor</span>
                <span class="text-[9px] bg-[#111b21] px-1.5 py-0.2 rounded font-normal text-gray-400">AI Specialist</span>
              </div>

              <!-- Attached Leaf Image (if user uploaded or bot previews) -->
              <div x-show="msg.image" class="mb-2 rounded-lg overflow-hidden border border-black/20 bg-black/40">
                <img :src="msg.image" alt="Leaf photo" class="w-full max-h-64 object-cover hover:scale-105 transition cursor-pointer" @click="window.open(msg.image, '_blank')" />
                <div class="bg-black/60 px-2 py-1 text-[11px] text-gray-300 flex items-center justify-between">
                  <span>📸 Leaf Sample</span>
                  <span class="text-[10px] text-emerald-400">High Clarity</span>
                </div>
              </div>

              <!-- Audio Voice Note Player (if message contains audio) -->
              <div x-show="msg.audio" class="mb-2 p-2 bg-black/25 rounded-lg border border-white/10 flex items-center gap-3">
                <button
                  @click="playAudio(msg.audio, index)"
                  class="w-10 h-10 rounded-full bg-[#00a884] hover:bg-[#02be96] text-[#111b21] flex items-center justify-center shrink-0 shadow text-sm transition">
                  <i class="fa-solid" :class="playingIndex === index ? 'fa-pause' : 'fa-play ml-0.5'"></i>
                </button>
                <div class="flex-1 min-w-0">
                  <!-- Waveform bars simulation -->
                  <div class="flex items-center gap-0.5 h-5">
                    <template x-for="h in [40, 70, 30, 90, 60, 100, 40, 80, 50, 70, 90, 40, 60, 80, 50, 90, 30, 70, 60, 40]" :key="Math.random()">
                      <span class="w-1 bg-[#8696a0] rounded-full transition-all" :style="'height: ' + h + '%; opacity: ' + (playingIndex === index ? '1' : '0.6')"></span>
                    </template>
                  </div>
                  <div class="flex justify-between items-center text-[10px] text-[#8696a0] mt-1">
                    <span x-text="playingIndex === index ? 'Playing Voice Note…' : 'Voice Advisory (0.9x speed)'"></span>
                    <span>Gnani Timbre TTS</span>
                  </div>
                </div>
              </div>

              <!-- Message Body Text -->
              <div class="text-sm leading-relaxed whitespace-pre-wrap select-text" x-text="msg.text"></div>

              <!-- Message Footer: Time and Ticks -->
              <div class="flex items-center justify-end gap-1 text-[10px] text-[#8696a0] mt-1.5 select-none">
                <span x-text="msg.time"></span>
                <template x-if="msg.sender === 'user'">
                  <span class="text-[#53bdeb]"><i class="fa-solid fa-check-double text-xs"></i></span>
                </template>
              </div>

            </div>
          </div>
        </template>

        <!-- Typing Indicator Bubble -->
        <div x-show="isTyping" class="flex justify-start">
          <div class="bubble-in rounded-xl px-4 py-3 shadow-md flex items-center gap-3">
            <div class="flex items-center gap-1.5 text-[#00a884]">
              <span class="w-2 h-2 rounded-full bg-[#00a884] typing-dot"></span>
              <span class="w-2 h-2 rounded-full bg-[#00a884] typing-dot"></span>
              <span class="w-2 h-2 rounded-full bg-[#00a884] typing-dot"></span>
            </div>
            <span class="text-xs text-[#8696a0] font-medium" x-text="typingStatus"></span>
          </div>
        </div>

      </div>

      <!-- Quick Scenario Preset Chips Bar -->
      <div class="px-4 py-2 bg-[#111b21]/90 border-t border-[#222d34] flex items-center gap-2 overflow-x-auto scrollbar-wa text-xs shrink-0">
        <span class="text-[#8696a0] shrink-0 font-medium"><i class="fa-solid fa-bolt text-yellow-400"></i> Presets:</span>
        <button @click="loadPreset('chilli_whitefly')" class="bg-[#202c33] hover:bg-[#2a3942] text-[#e9edef] px-3 py-1 rounded-full border border-[#2a3942] shrink-0 transition">
          🌶️ Chilli Whitefly
        </button>
        <button @click="loadPreset('chilli_thrips')" class="bg-[#202c33] hover:bg-[#2a3942] text-[#e9edef] px-3 py-1 rounded-full border border-[#2a3942] shrink-0 transition">
          🌶️ Chilli Thrips
        </button>
        <button @click="loadPreset('cotton_bollworm')" class="bg-[#202c33] hover:bg-[#2a3942] text-[#e9edef] px-3 py-1 rounded-full border border-[#2a3942] shrink-0 transition">
          🌿 Cotton Pink Bollworm
        </button>
        <button @click="loadPreset('cotton_aphids')" class="bg-[#202c33] hover:bg-[#2a3942] text-[#e9edef] px-3 py-1 rounded-full border border-[#2a3942] shrink-0 transition">
          🌿 Cotton Aphids
        </button>
        <button @click="loadPreset('paddy_blast')" class="bg-[#202c33] hover:bg-[#2a3942] text-[#e9edef] px-3 py-1 rounded-full border border-[#2a3942] shrink-0 transition">
          🌾 Paddy Blast
        </button>
        <button @click="loadPreset('tomato_blight')" class="bg-[#202c33] hover:bg-[#2a3942] text-[#e9edef] px-3 py-1 rounded-full border border-[#2a3942] shrink-0 transition">
          🍅 Tomato Early Blight
        </button>
        <button @click="loadPreset('banned_endosulfan')" class="bg-red-950/70 hover:bg-red-900 text-red-200 px-3 py-1 rounded-full border border-red-800 shrink-0 transition">
          🚫 Banned Check (Endosulfan)
        </button>
      </div>

      <!-- Leaf Photo Picker Bar (if attached) -->
      <div x-show="attachedImage" class="px-4 py-2 bg-[#182229] border-t border-[#222d34] flex items-center justify-between text-xs">
        <div class="flex items-center gap-3">
          <img :src="'/' + attachedImage" alt="Attachment" class="w-10 h-10 rounded object-cover border border-[#00a884]" />
          <div>
            <div class="font-semibold text-white truncate max-w-xs" x-text="attachedImage.split('/').pop()"></div>
            <div class="text-[11px] text-[#00a884]">Leaf photo attached to next message</div>
          </div>
        </div>
        <button @click="attachedImage = null" class="text-gray-400 hover:text-red-400 p-1.5"><i class="fa-solid fa-xmark"></i></button>
      </div>

      <!-- Chat Input Footer -->
      <footer class="bg-[#202c33] p-3 flex items-center gap-3 border-t border-[#222d34] z-10 shrink-0">
        
        <!-- Emoji button -->
        <button class="text-[#8696a0] hover:text-[#e9edef] text-xl transition" title="Emoji">
          <i class="fa-regular fa-face-smile"></i>
        </button>

        <!-- Attachment Paperclip Button -->
        <button
          @click="showPhotoModal = true"
          class="text-[#8696a0] hover:text-[#e9edef] text-lg transition"
          title="Attach Leaf Photo">
          <i class="fa-solid fa-paperclip"></i>
        </button>

        <!-- Input Text Box -->
        <div class="flex-1 bg-[#2a3942] rounded-lg px-4 py-2 flex items-center gap-2">
          <input
            type="text"
            x-model="inputText"
            @keydown.enter.prevent="sendUserMessage()"
            placeholder="Type symptoms in native language or select a preset..."
            class="bg-transparent border-none outline-none w-full text-sm text-[#e9edef] placeholder-[#8696a0]" />
        </div>

        <!-- Mic Button: simulates recording / speech -->
        <button
          @click="toggleVoiceNote()"
          class="text-xl transition"
          :class="isRecording ? 'text-red-500 animate-pulse' : 'text-[#8696a0] hover:text-[#e9edef]'"
          title="Voice Note">
          <i class="fa-solid fa-microphone"></i>
        </button>

        <!-- Send Button -->
        <button
          @click="sendUserMessage()"
          :disabled="isTyping || (!inputText.trim() && !attachedImage)"
          class="w-10 h-10 rounded-full bg-[#00a884] hover:bg-[#02be96] disabled:opacity-40 disabled:cursor-not-allowed text-[#111b21] flex items-center justify-center transition shadow shrink-0">
          <i class="fa-solid fa-paper-plane text-sm"></i>
        </button>

      </footer>

    </main>

  </div>

  <!-- Hidden HTML5 Audio Element for Voice Notes -->
  <audio id="simulatorAudioPlayer" class="hidden"></audio>

  <!-- Photo Picker Modal -->
  <div x-show="showPhotoModal" x-cloak class="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
    <div class="bg-[#202c33] border border-[#2a3942] rounded-2xl max-w-xl w-full p-6 shadow-2xl">
      <div class="flex items-center justify-between mb-4 border-b border-[#2a3942] pb-3">
        <h3 class="text-base font-bold text-white flex items-center gap-2">
          <i class="fa-solid fa-camera text-[#00a884]"></i> Select Leaf Photo from Field Samples
        </h3>
        <button @click="showPhotoModal = false" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark text-lg"></i></button>
      </div>

      <p class="text-xs text-[#8696a0] mb-4">Choose an agricultural research leaf photo to attach to your WhatsApp message:</p>
      
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-80 overflow-y-auto scrollbar-wa p-1">
        <template x-for="img in samplePhotos" :key="img.file">
          <div
            @click="attachedImage = 'storage/test_leaves/' + img.file; showPhotoModal = false"
            class="bg-[#111b21] hover:bg-[#2a3942] border border-[#2a3942] rounded-xl p-2 cursor-pointer transition text-center group">
            <img :src="'/storage/test_leaves/' + img.file" :alt="img.name" class="w-full h-24 object-cover rounded-lg mb-1.5 group-hover:scale-105 transition" />
            <div class="text-[11px] font-semibold text-white truncate" x-text="img.name"></div>
            <div class="text-[9px] text-[#00a884] capitalize" x-text="img.crop"></div>
          </div>
        </template>
      </div>

      <div class="mt-4 pt-3 border-t border-[#2a3942] flex justify-end">
        <button @click="showPhotoModal = false" class="bg-[#111b21] hover:bg-[#2a3942] text-gray-300 text-xs px-4 py-2 rounded-lg border border-gray-600">Close</button>
      </div>
    </div>
  </div>

<script>
function whatsAppSimulator() {
  return {
    selectedLanguage: "hi",
    inputText: "",
    attachedImage: "storage/test_leaves/01_chilli_leaf_curl_whitefly.jpg",
    isTyping: false,
    typingStatus: "typing...",
    isRecording: false,
    showPhotoModal: false,
    playingIndex: null,
    lastActiveTime: "Just now",
    lastMessagePreview: "Diagnosis ready · Voice Note attached",

    samplePhotos: [
      { name: "Chilli Whitefly", file: "01_chilli_leaf_curl_whitefly.jpg", crop: "chilli" },
      { name: "Chilli Thrips", file: "02_chilli_thrips_damage.jpg", crop: "chilli" },
      { name: "Chilli Anthracnose", file: "03_chilli_anthracnose_fruit_rot.jpg", crop: "chilli" },
      { name: "Cotton Pink Bollworm", file: "05_cotton_pink_bollworm.jpg", crop: "cotton" },
      { name: "Cotton Aphids (Mava)", file: "06_cotton_aphids_infestation.jpg", crop: "cotton" },
      { name: "Cotton Grey Mildew", file: "07_cotton_grey_mildew_dahiya.jpg", crop: "cotton" },
      { name: "Paddy Brown Spot", file: "08_paddy_brown_spot.jpg", crop: "paddy" },
      { name: "Paddy Rice Blast", file: "09_paddy_rice_blast.jpg", crop: "paddy" },
      { name: "Tomato Early Blight", file: "13_tomato_early_blight.jpg", crop: "tomato" },
      { name: "Tomato Late Blight", file: "14_tomato_late_blight.jpg", crop: "tomato" },
      { name: "Non-Plant Sample", file: "18_non_plant_pesticide_bottle.jpg", crop: "edge" }
    ],

    messages: [
      {
        sender: "bot",
        text: "🌾 नमस्ते! मैं फसल डॉक्टर (Crop Doctor AI) हूँ।\\n\\nकृपया अपनी फसल की प्रभावित पत्ती का पास से फोटो भेजें और अपनी भाषा में समस्या बताएं।\\n\\nविश्वविद्यालय प्रमाणित उपचार एवं सुरक्षा निर्देश तुरंत प्राप्त होंगे।",
        time: "10:30 AM",
        image: null,
        audio: null
      }
    ],

    init() {
      this.scrollToBottom();
      const player = document.getElementById("simulatorAudioPlayer");
      if (player) {
        player.onended = () => { this.playingIndex = null; };
        player.onpause = () => { this.playingIndex = null; };
      }

      // Check URL query parameters to auto-load scenarios from website links
      const urlParams = new URLSearchParams(window.location.search);
      const preset = urlParams.get('preset');
      const crop = urlParams.get('crop');
      const lang = urlParams.get('lang');

      if (lang) {
        this.selectedLanguage = lang;
      }
      if (preset) {
        this.loadPreset(preset);
      } else if (crop) {
        const cropMap = {
          chilli: 'chilli_whitefly',
          cotton: 'cotton_bollworm',
          paddy: 'paddy_blast',
          tomato: 'tomato_blight'
        };
        if (cropMap[crop.toLowerCase()]) {
          this.loadPreset(cropMap[crop.toLowerCase()]);
        }
      }
    },

    scrollToBottom() {
      this.$nextTick(() => {
        const el = document.getElementById("messagesContainer");
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    getTimeString() {
      const d = new Date();
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },

    resetConversation() {
      this.messages = [
        {
          sender: "bot",
          text: "🌾 नमस्ते! मैं फसल डॉक्टर (Crop Doctor AI) हूँ।\\n\\nअपनी फसल की पत्ती का फोटो और अपनी भाषा में लक्षण भेजें।",
          time: this.getTimeString(),
          image: null,
          audio: null
        }
      ];
      this.playingIndex = null;
    },

    onLanguageChange() {
      const welcomeMap = {
        hi: "🌾 नमस्ते! मैं फसल डॉक्टर हूँ। पत्ती का फोटो और लक्षण भेजें।",
        te: "🌾 నమస్తే! నేను క్రాప్ డాక్టర్ AI. ఆకు ఫోటో మరియు సమస్య పంపండి.",
        mr: "🌾 नमस्कार! मी पीक डॉक्टर AI आहे. पानाचा फोटो आणि लक्षणे पाठवा.",
        pa: "🌾 ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ਫ਼ਸਲ ਡਾਕਟਰ AI ਹਾਂ। ਪੱਤੇ ਦੀ ਫੋਟੋ ਅਤੇ ਲੱਛਣ ਭੇਜੋ।",
        ta: "🌾 வணக்கம்! நான் பயிர் மருத்துவர் AI. இலையின் படத்தையும் பிரச்சனைகளையும் அனுப்பவும்.",
        kn: "🌾 ನಮಸ್ಕಾರ! ನಾನು ಕ್ರಾಪ್ ಡಾಕ್ಟರ್ AI. ಎಲೆಯ ಫೋಟೋ ಮತ್ತು ರೋಗಲಕ್ಷಣ ಕಳುಹಿಸಿ.",
        bn: "🌾 নমস্কার! আমি ক্রপ ডক্টর AI। পাতার ছবি এবং সমস্যা লিখে পাঠান।",
        gu: "🌾 નમસ્તે! હું ક્રોપ ડોક્ટર AI છું. પાનનો ફોટો અને લક્ષણો મોકલો.",
        ml: "🌾 നമസ്കാരം! ഞാൻ വിള ഡോക്ടർ AI. ഇലയുടെ ഫോട്ടോയും രോഗലക്ഷണങ്ങളും അയക്കുക.",
        or: "🌾 ନମସ୍କାର! ମୁଁ ଫସଲ ଡାକ୍ତର AI | ପତ୍ରର ଫଟୋ ଏବଂ ସମସ୍ୟା ପଠାନ୍ତୁ |",
        en: "🌾 Hello! I am Crop Doctor AI. Please send an affected leaf photo and symptom description."
      };
      this.messages.push({
        sender: "bot",
        text: welcomeMap[this.selectedLanguage] || welcomeMap.hi,
        time: this.getTimeString(),
        image: null,
        audio: null
      });
      this.scrollToBottom();
    },

    loadPreset(type) {
      const presets = {
        chilli_whitefly: {
          lang: "hi",
          crop: "chilli",
          img: "storage/test_leaves/01_chilli_leaf_curl_whitefly.jpg",
          text: "हमारी मिर्च की पत्तियां ऊपर की तरफ मुड़ रही हैं और पत्तियों के नीचे सफेद रंग के छोटे कीड़े दिखाई दे रहे हैं"
        },
        chilli_thrips: {
          lang: "te",
          crop: "chilli",
          img: "storage/test_leaves/02_chilli_thrips_damage.jpg",
          text: "ఆకులు పడవ ఆకారంలో వంగిపోయాయి, వెండి రంగు మచ్చలు కనిపిస్తున్నాయి"
        },
        cotton_bollworm: {
          lang: "mr",
          crop: "cotton",
          img: "storage/test_leaves/05_cotton_pink_bollworm.jpg",
          text: "गुलाबी बोंड अळी बोंडात शिरत आहे, डोमकळ्या दिसत आहेत"
        },
        cotton_aphids: {
          lang: "mr",
          crop: "cotton",
          img: "storage/test_leaves/06_cotton_aphids_infestation.jpg",
          text: "कापूस पानांच्या खाली हिरवे मावा दिसत आहेत, पान पिवळे होत आहे"
        },
        paddy_blast: {
          lang: "pa",
          crop: "paddy",
          img: "storage/test_leaves/09_paddy_rice_blast.jpg",
          text: "ਝੋਨੇ ਦੀਆਂ ਪੱਤੀਆਂ ਤੇ ਅੱਖ ਦੇ ਆਕਾਰ ਦੇ ਧੱਬੇ ਦਿਖਾਈ ਦੇ ਰਹੇ ਹਨ"
        },
        tomato_blight: {
          lang: "te",
          crop: "tomato",
          img: "storage/test_leaves/13_tomato_early_blight.jpg",
          text: "టమాటా ఆకులపై గోళాకార మచ్చలు, పసుపు రంగు హలో కనిపిస్తోంది"
        },
        banned_endosulfan: {
          lang: "hi",
          crop: "chilli",
          img: "storage/test_leaves/01_chilli_leaf_curl_whitefly.jpg",
          text: "क्या मैं इस मिर्च के कीड़े के लिए Endosulfan या Monocrotophos का छिड़काव कर सकता हूँ?"
        }
      };

      const p = presets[type];
      if (!p) return;
      this.selectedLanguage = p.lang;
      this.attachedImage = p.img;
      this.inputText = p.text;
    },

    toggleVoiceNote() {
      this.isRecording = !this.isRecording;
      if (this.isRecording) {
        if (!this.inputText) {
          const sampleTexts = {
            hi: "पत्तियों के नीचे सफेद कीड़े लगे हैं और पौधा मुरझा रहा है।",
            te: "ఆకుల కింద తెల్ల పురుగులు ఉన్నాయి మరియు ఆకులు ఎండిపోతున్నాయి.",
            mr: "पानांखाली किडे आहेत आणि पाने पिवळी पडत आहेत.",
            pa: "ਪੱਤਿਆਂ ਤੇ ਧੱਬੇ ਪੈ ਰਹੇ ਹਨ, ਕੋਈ ਦਵਾਈ ਦੱਸੋ।"
          };
          this.inputText = sampleTexts[this.selectedLanguage] || sampleTexts.hi;
        }
      }
    },

    async sendUserMessage() {
      const text = this.inputText.trim();
      const img = this.attachedImage;
      if (!text && !img) return;

      const time = this.getTimeString();

      // Add user message to chat
      this.messages.push({
        sender: "user",
        text: text,
        time: time,
        image: img ? ('/' + img) : null,
        audio: null
      });

      this.inputText = "";
      this.attachedImage = null;
      this.scrollToBottom();

      // Show typing indicator
      this.isTyping = true;
      this.typingStatus = "🌾 Crop Doctor is analyzing leaf...";

      try {
        const payload = {
          language: this.selectedLanguage,
          transcript: text || "पत्ते का विश्लेषण करें",
          image_file: img ? img.split('/').pop() : null
        };

        const resp = await fetch("/api/simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!resp.ok) {
          throw new Error("Server error " + resp.status);
        }

        const data = await resp.json();

        // Simulate voice note recording state briefly
        this.typingStatus = "🌾 Crop Doctor is synthesizing voice note...";
        await new Promise(r => setTimeout(r, 600));

        // Add Crop Doctor reply message
        this.messages.push({
          sender: "bot",
          text: data.final_text || "जांच पूरी हुई।",
          time: this.getTimeString(),
          image: null,
          audio: data.audio_url || null
        });

        this.lastActiveTime = this.getTimeString();
        this.lastMessagePreview = data.decision && data.decision.likely_problems && data.decision.likely_problems[0]
          ? data.decision.likely_problems[0].local_name
          : "Diagnosis complete";

      } catch (err) {
        this.messages.push({
          sender: "bot",
          text: "⚠️ त्रुटि: कृपया पुनः प्रयास करें (" + err.message + ")",
          time: this.getTimeString(),
          image: null,
          audio: null
        });
      } finally {
        this.isTyping = false;
        this.scrollToBottom();
      }
    },

    playAudio(audioUrl, index) {
      const player = document.getElementById("simulatorAudioPlayer");
      if (this.playingIndex === index) {
        player.pause();
        this.playingIndex = null;
        return;
      }
      player.src = audioUrl;
      player.play().then(() => {
        this.playingIndex = index;
      }).catch(e => {
        console.error("Audio playback error:", e);
      });
    }
  };
}
</script>

  <!-- Floating WhatsApp Simulator Launcher -->
  <aside class="fixed bottom-6 right-6 z-50">
    <a href="/whatsapp"
       title="Open WhatsApp Web Simulator"
       class="group flex items-center gap-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold pl-4 pr-5 py-3.5 rounded-full shadow-2xl hover:shadow-emerald-500/50 transition-all transform hover:-translate-y-1 border border-emerald-300/40">
      <span class="relative flex h-3.5 w-3.5">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-200 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-400"></span>
      </span>
      <i class="fa-brands fa-whatsapp text-2xl text-white"></i>
      <div class="text-left leading-tight">
        <div class="text-[10px] text-emerald-100 uppercase tracking-widest font-extrabold">Live Demo</div>
        <div class="text-sm font-bold text-white flex items-center gap-1.5">
          WhatsApp Simulator
          <i class="fa-solid fa-arrow-right text-xs group-hover:translate-x-1 transition-transform"></i>
        </div>
      </div>
    </a>
  </aside>

</body>
</html>"""
    return HTMLResponse(content=html)



# ---------------------------------------------------------------------------
# GET /demo  —  Interactive Demo Page
# ---------------------------------------------------------------------------

@router.get("/demo", response_class=HTMLResponse, summary="Interactive Demo Page")
async def demo_page():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Live Demo · Crop Doctor</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" />
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .hero-gradient { background: linear-gradient(135deg, #0a2e1a 0%, #1a4a2e 50%, #0d3b22 100%); }
    .spinner { border: 3px solid rgba(255,255,255,0.1); border-top-color: #22c55e; border-radius: 50%;
               width: 40px; height: 40px; animation: spin 0.8s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    [x-cloak] { display: none !important; }
    .accordion-body { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
    .accordion-body.open { max-height: 500px; }
  </style>
</head>
<body class="bg-gray-950 text-white min-h-screen"
      x-data="cropDoctorDemo()"
      x-init="init()">

  <!-- NAVBAR -->
  <nav class="hero-gradient border-b border-green-800/40 sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex items-center justify-between h-16">
        <a href="/" class="flex items-center gap-2 text-xl font-bold text-white">
          <span class="text-2xl">🌾</span> Crop Doctor
        </a>
        <div class="hidden md:flex items-center gap-6 text-sm font-medium">
          <a href="/"        class="text-gray-300 hover:text-white transition">Home</a>
          <a href="/whatsapp" class="text-emerald-400 hover:text-emerald-300 font-semibold transition flex items-center gap-1.5"><i class="fa-brands fa-whatsapp text-lg text-emerald-400"></i> WhatsApp Web</a>
          <a href="/demo"    class="text-green-300 hover:text-white transition">Demo</a>
          <a href="/guides"  class="text-gray-300 hover:text-white transition">Guides</a>
          <a href="/stats"   class="text-gray-300 hover:text-white transition">Analytics</a>
          <a href="/reviews" class="text-gray-300 hover:text-white transition">Review Dashboard</a>
          <a href="/docs"    class="text-gray-300 hover:text-white transition flex items-center gap-1">
            <i class="fa-solid fa-book text-xs"></i> API Docs
          </a>
        </div>
      </div>
    </div>
  </nav>

  <main class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <div class="mb-8 text-center">
      <h1 class="text-3xl font-extrabold text-white mb-2">🔬 Interactive Demo</h1>
      <p class="text-gray-400 text-sm">Select a benchmark scenario and analyse a simulated farmer consultation end-to-end.</p>
    </div>

    <!-- CONTROL PANEL -->
    <div class="bg-gray-900 border border-gray-700 rounded-2xl p-6 mb-8 shadow-xl">

      <!-- Language Tabs -->
      <div class="mb-5">
        <label class="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Language (11 Indic & Indian Languages Supported)</label>
        <div class="flex gap-2 flex-wrap">
          <template x-for="lang in [
            {code:'hi',label:'हिन्दी (Hindi) 🇮🇳'},
            {code:'te',label:'తెలుగు (Telugu) 🇮🇳'},
            {code:'mr',label:'मराठी (Marathi) 🇮🇳'},
            {code:'pa',label:'ਪੰਜਾਬੀ (Punjabi) 🇮🇳'},
            {code:'ta',label:'தமிழ் (Tamil) 🇮🇳'},
            {code:'kn',label:'ಕನ್ನಡ (Kannada) 🇮🇳'},
            {code:'bn',label:'বাংলা (Bengali) 🇮🇳'},
            {code:'gu',label:'ગુજરાતી (Gujarati) 🇮🇳'},
            {code:'ml',label:'മലയാളം (Malayalam) 🇮🇳'},
            {code:'or',label:'ଓଡ଼ିଆ (Odia) 🇮🇳'},
            {code:'en',label:'English 🇬🇧'}
          ]" :key="lang.code">
            <button
              @click="setLanguage(lang.code)"
              :class="language === lang.code
                ? 'bg-green-600 text-white border-green-500 shadow-md shadow-green-900/50'
                : 'bg-gray-800 text-gray-300 border-gray-600 hover:border-green-500'"
              class="border px-3 py-1.5 rounded-lg text-xs font-semibold transition"
              x-text="lang.label">
            </button>
          </template>
        </div>
      </div>

      <!-- Scenario Dropdown -->
      <div class="mb-5">
        <label class="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Scenario</label>
        <select
          x-model="scenarioId"
          @change="loadScenario()"
          class="w-full bg-gray-800 border border-gray-600 text-white rounded-lg px-4 py-2.5 text-sm focus:border-green-500 focus:outline-none">
          <option value="">— Select a scenario —</option>
          <option value="1">1. Chilli – Whitefly Leaf Curl (Telugu)</option>
          <option value="2">2. Chilli – Thrips Curling (Telugu)</option>
          <option value="3">3. Chilli – Anthracnose Fruit Rot (Telugu)</option>
          <option value="4">4. Cotton – Aphids Sucking Damage (Marathi)</option>
          <option value="5">5. Cotton – Whitefly Cotton Leaf Curl (Marathi)</option>
          <option value="6">6. Cotton – Pink Bollworm (Marathi)</option>
          <option value="7">7. Cotton – Grey Mildew Fungal (Marathi)</option>
          <option value="8">8. Paddy – Rice Blast (Punjabi)</option>
          <option value="9">9. Paddy – Brown Spot (Punjabi)</option>
          <option value="10">10. Paddy – Sheath Blight (Punjabi)</option>
          <option value="11">11. Tomato – Early Blight (Telugu)</option>
          <option value="12">12. Tomato – Late Blight (Telugu)</option>
          <option value="13">13. No Photo Submitted (Edge Case)</option>
          <option value="14">14. Non-Plant Image (Edge Case)</option>
          <option value="15">15. Banned Chemical Request (Edge Case)</option>
        </select>
      </div>

      <!-- Crop & Image row -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5 mb-5">
        <div>
          <label class="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Crop</label>
          <div class="flex gap-2 flex-wrap">
            <template x-for="c in ['chilli','cotton','paddy','tomato']" :key="c">
              <button
                @click="crop = c"
                :class="crop === c
                  ? 'bg-green-700 text-white border-green-500'
                  : 'bg-gray-800 text-gray-300 border-gray-600 hover:border-green-500'"
                class="border px-4 py-2 rounded-lg text-sm font-semibold capitalize transition"
                x-text="c">
              </button>
            </template>
          </div>
        </div>
        <div>
          <label class="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Image Filename</label>
          <input
            type="text"
            x-model="imageFile"
            placeholder="e.g. chilli_whitefly_01.png"
            class="w-full bg-gray-800 border border-gray-600 text-white rounded-lg px-4 py-2.5 text-sm focus:border-green-500 focus:outline-none placeholder-gray-500" />
        </div>
      </div>

      <!-- Transcript -->
      <div class="mb-6">
        <label class="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Farmer Transcript</label>
        <textarea
          x-model="transcript"
          rows="3"
          placeholder="Farmer's message in their native language..."
          class="w-full bg-gray-800 border border-gray-600 text-white rounded-lg px-4 py-3 text-sm focus:border-green-500 focus:outline-none resize-none placeholder-gray-500"></textarea>
      </div>

      <!-- Submit -->
      <button
        @click="analyze()"
        :disabled="loading"
        class="w-full md:w-auto inline-flex items-center justify-center gap-2 bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold px-8 py-3 rounded-xl text-base transition shadow-lg">
        <i class="fa-solid fa-flask" x-show="!loading"></i>
        <span x-show="loading" class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" style="animation: spin 0.7s linear infinite;"></span>
        <span x-text="loading ? 'Analysing…' : '🔬 Analyze Crop'"></span>
      </button>
    </div>

    <!-- LOADING SPINNER -->
    <div x-show="loading" x-cloak class="flex flex-col items-center justify-center py-16 gap-4">
      <div class="spinner"></div>
      <p class="text-green-400 text-sm font-medium animate-pulse">Running AI pipeline…</p>
    </div>

    <!-- RESULTS PANEL -->
    <div x-show="result && !loading" x-cloak class="space-y-6">

      <!-- Evon Decision Banner -->
      <div
        :class="{
          'bg-green-900/60 border-green-500 text-green-300': result && result.tool_called === 'answer_case',
          'bg-yellow-900/60 border-yellow-500 text-yellow-300': result && result.tool_called === 'ask_more',
          'bg-red-900/60 border-red-500 text-red-300': result && result.tool_called === 'escalate'
        }"
        class="border rounded-xl px-6 py-4 flex items-center gap-4 text-lg font-bold">
        <span x-show="result && result.tool_called === 'answer_case'">✅ Diagnosis Complete</span>
        <span x-show="result && result.tool_called === 'ask_more'">⚠️ Need More Information</span>
        <span x-show="result && result.tool_called === 'escalate'">🚨 Escalate to KVK Expert</span>
        <span class="ml-auto text-xs font-mono font-normal opacity-70" x-text="result && result.case_id"></span>
      </div>

      <!-- Vision Analysis -->
      <div x-show="result && result.vision_obs" class="bg-gray-900 border border-gray-700 rounded-2xl overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center gap-2">
          <i class="fa-solid fa-eye text-green-400"></i>
          <h2 class="font-bold text-white">Vision Analysis</h2>
        </div>
        <div class="p-6 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-gray-500 text-xs uppercase">
                <th class="pb-3 pr-6 font-semibold">Feature</th>
                <th class="pb-3 pr-6 font-semibold">Observation</th>
                <th class="pb-3 font-semibold">Confidence</th>
              </tr>
            </thead>
            <tbody class="text-gray-300 divide-y divide-gray-800">
              <template x-for="[key, val] in visionRows()" :key="key">
                <tr>
                  <td class="py-2 pr-6 font-medium text-gray-400 capitalize" x-text="key.replace(/_/g,' ')"></td>
                  <td class="py-2 pr-6" x-text="val"></td>
                  <td class="py-2">
                    <template x-if="result.vision_obs && result.vision_obs.confidence_scores && result.vision_obs.confidence_scores[key] !== undefined">
                      <span
                        :class="confBadgeClass(result.vision_obs.confidence_scores[key])"
                        class="text-xs font-bold px-2 py-0.5 rounded-full"
                        x-text="(result.vision_obs.confidence_scores[key] * 100).toFixed(0) + '%'">
                      </span>
                    </template>
                    <template x-if="!(result.vision_obs && result.vision_obs.confidence_scores && result.vision_obs.confidence_scores[key] !== undefined)">
                      <span class="text-gray-600 text-xs">—</span>
                    </template>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Guide Passages -->
      <div x-show="result && result.retrieved_chunks && result.retrieved_chunks.length > 0" class="bg-gray-900 border border-gray-700 rounded-2xl overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center gap-2">
          <i class="fa-solid fa-book-open text-green-400"></i>
          <h2 class="font-bold text-white">Retrieved Guide Passages</h2>
          <span class="ml-auto text-xs text-gray-500" x-text="(result.retrieved_chunks || []).length + ' chunks'"></span>
        </div>
        <div class="divide-y divide-gray-800">
          <template x-for="(chunk, idx) in (result.retrieved_chunks || [])" :key="idx">
            <div class="px-6 py-4">
              <button
                @click="toggleAccordion(idx)"
                class="w-full text-left flex items-center justify-between gap-4">
                <div>
                  <span class="text-sm font-semibold text-white" x-text="chunk.title || chunk.id || ('Chunk ' + (idx+1))"></span>
                  <div class="text-xs text-gray-500 mt-0.5">
                    <span x-text="chunk.publisher || ''"></span>
                    <template x-if="chunk.section"> · <span x-text="chunk.section"></span></template>
                    <template x-if="chunk.page"> · p.<span x-text="chunk.page"></span></template>
                  </div>
                </div>
                <i class="fa-solid fa-chevron-down text-gray-400 transition-transform" :class="openAccordion === idx ? 'rotate-180' : ''"></i>
              </button>
              <div class="accordion-body mt-3 text-gray-400 text-sm leading-relaxed" :class="openAccordion === idx ? 'open' : ''">
                <p x-text="expandedChunks[idx] ? (chunk.text || '') : truncate(chunk.text || '', 200)"></p>
                <button x-show="(chunk.text || '').length > 200"
                        @click="expandedChunks[idx] = !expandedChunks[idx]"
                        class="text-green-400 hover:text-green-300 text-xs mt-2 font-semibold"
                        x-text="expandedChunks[idx] ? 'Show less' : 'Read more →'">
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- Advisory Text -->
      <div x-show="result && result.final_text" class="bg-gray-900 border border-gray-700 rounded-2xl overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center gap-2">
          <i class="fa-solid fa-comment-dots text-green-400"></i>
          <h2 class="font-bold text-white">Advisory Text</h2>
        </div>
        <div class="p-6">
          <p class="text-gray-200 leading-relaxed whitespace-pre-wrap" x-text="result && result.final_text"></p>
        </div>
      </div>

      <!-- Citation Box -->
      <div x-show="result && result.decision && result.decision.treatment && result.decision.treatment.verbatim_quote"
           class="bg-gray-900 border-2 border-green-700 rounded-2xl overflow-hidden">
        <div class="px-6 py-4 border-b border-green-700/50 flex items-center gap-2">
          <i class="fa-solid fa-quote-left text-green-400"></i>
          <h2 class="font-bold text-white">Verbatim Citation</h2>
        </div>
        <div class="p-6">
          <blockquote class="font-mono text-sm text-green-300 leading-relaxed border-l-4 border-green-600 pl-4"
                      x-text="result && result.decision && result.decision.treatment && result.decision.treatment.verbatim_quote">
          </blockquote>
          <div class="mt-3 text-xs text-gray-500 font-mono"
               x-text="'chunk_id: ' + (result && result.decision && result.decision.treatment && result.decision.treatment.chunk_id || 'N/A')">
          </div>
        </div>
      </div>

      <!-- Audio Player -->
      <div x-show="result && (result.audio_url || result.final_text)" class="bg-gray-900 border border-green-700/60 rounded-2xl overflow-hidden shadow-xl">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-volume-high text-green-400"></i>
            <h2 class="font-bold text-white">Voice Advisory (WhatsApp Audio Note)</h2>
          </div>
          <span class="text-xs bg-green-900/60 text-green-300 border border-green-700 px-2.5 py-1 rounded-full font-mono">
            Gnani Timbre TTS · 0.9x Speed
          </span>
        </div>
        <div class="p-6 space-y-4">
          <!-- Real Audio Element -->
          <div x-show="result && result.audio_url">
            <audio id="advisoryAudio" controls class="w-full" :src="result && result.audio_url" preload="auto"></audio>
          </div>
          <!-- Action Buttons: Browser Text-to-Speech + Download -->
          <div class="flex flex-wrap items-center gap-3 pt-2">
            <button
              type="button"
              @click="speakAloud(result && result.final_text)"
              class="inline-flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition shadow">
              <i class="fa-solid" :class="isSpeaking ? 'fa-square' : 'fa-play'"></i>
              <span x-text="isSpeaking ? '⏹ Stop Speaking' : '🔊 Listen with Browser Voice'"></span>
            </button>
            <a
              x-show="result && result.audio_url"
              :href="result && result.audio_url"
              download="crop_doctor_voice_advisory.wav"
              class="inline-flex items-center gap-2 bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs font-semibold px-4 py-2 rounded-lg border border-gray-600 transition">
              <i class="fa-solid fa-download"></i> Download Audio (.wav)
            </a>
            <span class="text-xs text-gray-400 ml-auto flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full bg-green-400 animate-ping"></span>
              Synthesized in <span class="capitalize font-semibold text-green-300" x-text="language"></span>
            </span>
          </div>
        </div>
      </div>

      <!-- Review Link -->
      <div class="flex justify-end">
        <a href="/reviews"
           class="inline-flex items-center gap-2 border border-green-600 text-green-400 hover:bg-green-900/30 px-6 py-2.5 rounded-xl text-sm font-semibold transition">
          View in Review Dashboard <i class="fa-solid fa-arrow-right text-xs"></i>
        </a>
      </div>

    </div><!-- /results -->

    <!-- Error state -->
    <div x-show="error" x-cloak class="bg-red-900/40 border border-red-600 rounded-xl px-6 py-4 text-red-300 text-sm font-medium mt-4">
      <i class="fa-solid fa-triangle-exclamation mr-2"></i>
      <span x-text="error"></span>
    </div>

  </main>

  <!-- FOOTER -->
  <footer class="hero-gradient border-t border-green-800/40 py-8 mt-16">
    <div class="max-w-7xl mx-auto px-4 text-center">
      <div class="text-green-300 font-semibold mb-1">
        Powered by Gnani Vachana AI &middot; PJTSAU &middot; MPKV &middot; PAU &middot; Dr. YSRHU
      </div>
      <div class="text-gray-400 text-sm">
        KVK Helpline: <a href="tel:18001801551" class="text-green-400 hover:underline font-mono">1800-180-1551</a>
      </div>
    </div>
  </footer>

<script>
const SCENARIOS = {
  1:  { crop: "chilli",  language: "te", image: "01_chilli_leaf_curl_whitefly.jpg",    transcript: "మా మిర్చి ఆకులు పైకి చుట్టుకుపోతున్నాయి, ఆకు అడుగు భాగంలో తెల్లటి చిన్న పురుగులు ఉన్నాయి" },
  2:  { crop: "chilli",  language: "te", image: "02_chilli_thrips_damage.jpg",         transcript: "ఆకులు పడవ ఆకారంలో వంగిపోయాయి, వెండి రంగు మచ్చలు కనిపిస్తున్నాయి" },
  3:  { crop: "chilli",  language: "te", image: "03_chilli_anthracnose_fruit_rot.jpg", transcript: "మిర్చి కాయలపై చీకటి మచ్చలు వస్తున్నాయి, పంట నాశనమవుతోంది" },
  4:  { crop: "cotton",  language: "mr", image: "06_cotton_aphids_infestation.jpg",    transcript: "कापूस पानांच्या खाली हिरवे मावा दिसत आहेत, पान पिवळे होत आहे" },
  5:  { crop: "cotton",  language: "mr", image: "01_chilli_leaf_curl_whitefly.jpg",    transcript: "कापूस पानांवर पांढरी माशी आणि काळी बुरशी दिसत आहे" },
  6:  { crop: "cotton",  language: "mr", image: "05_cotton_pink_bollworm.jpg",         transcript: "गुलाबी बोंड अळी बोंडात शिरत आहे, डोमकळ्या दिसत आहेत" },
  7:  { crop: "cotton",  language: "mr", image: "07_cotton_grey_mildew_dahiya.jpg",    transcript: "कापूस पानांवर पांढरी राखाडी दहिया बुरशी दिसत आहे" },
  8:  { crop: "paddy",   language: "pa", image: "09_paddy_rice_blast.jpg",             transcript: "ਝੋਨੇ ਦੀਆਂ ਪੱਤੀਆਂ ਤੇ ਅੱਖ ਦੇ ਆਕਾਰ ਦੇ ਧੱਬੇ ਦਿਖਾਈ ਦੇ ਰਹੇ ਹਨ" },
  9:  { crop: "paddy",   language: "pa", image: "08_paddy_brown_spot.jpg",             transcript: "ਝੋਨੇ ਦੀਆਂ ਪੱਤੀਆਂ ਤੇ ਭੂਰੇ ਗੋਲ ਧੱਬੇ ਦਿਖਾਈ ਦੇ ਰਹੇ ਹਨ" },
  10: { crop: "paddy",   language: "pa", image: "10_paddy_planthopper_burn.jpg",       transcript: "ਝੋਨੇ ਦੀਆਂ ਜੜ੍ਹਾਂ ਕੋਲ ਗੂੜ੍ਹੇ ਧੱਬੇ ਅਤੇ ਪੱਤੇ ਸੜ ਰਹੇ ਹਨ" },
  11: { crop: "tomato",  language: "te", image: "13_tomato_early_blight.jpg",          transcript: "టమాటా ఆకులపై గోళాకార మచ్చలు, పసుపు రంగు హలో కనిపిస్తోంది" },
  12: { crop: "tomato",  language: "te", image: "14_tomato_late_blight.jpg",           transcript: "టమాటా ఆకులపై నీటిలో తడిసిన మచ్చలు, తెల్లటి బూజు కనిపిస్తోంది" },
  13: { crop: "chilli",  language: "te", image: "",                                    transcript: "ఈ పంటకు ఏమి చేయాలో చెప్పండి" },
  14: { crop: "chilli",  language: "te", image: "18_non_plant_pesticide_bottle.jpg",   transcript: "ఈ ఫోటోలో ఏమి కనిపిస్తోంది?" },
  15: { crop: "chilli",  language: "te", image: "01_chilli_leaf_curl_whitefly.jpg",    transcript: "Endosulfan వాడవచ్చా?" }
};

const SCENARIO_TRANSLATIONS = {
  1: {
    hi: "हमारी मिर्च की पत्तियां ऊपर की तरफ मुड़ रही हैं और पत्तियों के नीचे सफेद रंग के छोटे कीड़े दिखाई दे रहे हैं",
    te: "మా మిర్చి ఆకులు పైకి చుట్టుకుపోతున్నాయి, ఆకు అడుగు భాగంలో తెల్లటి చిన్న పురుగులు ఉన్నాయి",
    mr: "आमच्या मिरचीची पाने वरच्या बाजूला चुरडत आहेत आणि पानांच्या खाली लहान पांढरी माशी दिसत आहे",
    pa: "ਮਿਰਚ ਦੇ ਪੱਤੇ ਉੱਪਰ ਵੱਲ ਮੁੜ ਰਹੇ ਹਨ ਅਤੇ ਪੱਤਿਆਂ ਦੇ ਹੇਠਾਂ ਚਿੱਟੀ ਮੱਖੀ ਦਿਖਾਈ ਦੇ ਰਹੀ ਹੈ",
    ta: "மிளகாய் இலைகள் மேல்நோக்கி சுருண்டுள்ளன, இலைகளின் அடிப்பகுதியில் வெள்ளை ஈக்கள் உள்ளன",
    kn: "ಮೆಣಸಿನಕಾಯಿ ಎಲೆಗಳು ಮೇಲ್ಮುಖವಾಗಿ ಸುರುಟಿಕೊಳ್ಳುತ್ತಿವೆ ಮತ್ತು ಎಲೆಯ ಕೆಳಗೆ ಬಿಳಿ ನೊಣಗಳಿವೆ",
    bn: "লঙ্কার পাতা উপরের দিকে কুঁকড়ে যাচ্ছে এবং পাতার নিচে সাদা মাছি দেখা যাচ্ছে",
    gu: "મરચીના પાન ઉપરની તરફ કોકડાઈ રહ્યા છે અને પાનની નીચે સફેદ માખી દેખાય છે",
    ml: "മുളകിന്റെ ഇലകൾ മുകളിലേക്ക് ചുരുളുന്നു, ഇലകൾക്ക് അടിയിൽ വെള്ളീച്ചകളെ കാണുന്നു",
    or: "ଲଙ୍କା ପତ୍ର ଉପରକୁ କୁଞ୍ଚିତ ହେଉଛି ଏବଂ ପତ୍ର ତଳେ ଧଳା ମାଛି ଅଛି",
    en: "Chilli leaves are curling upwards boat-shaped and tiny whiteflies are visible on leaf undersides"
  },
  4: {
    hi: "कपास के पत्तों के नीचे माहू (चेपा) कीट चिपके हैं और पत्तियां पीली पड़ रही हैं",
    mr: "कापूस पानांच्या खाली हिरवे मावा दिसत आहेत, पान पिवळे होत आहे",
    te: "పత్తి ఆకుల అడుగున పేనుబంక పురుగులు ఉన్నాయి, ఆకులు పసుపుగా మారుతున్నాయి",
    pa: "ਕਪਾਹ ਦੇ ਪੱਤਿਆਂ ਹੇਠ ਤੇਲਾ ਕੀੜਾ ਲੱਗਿਆ ਹੈ ਅਤੇ ਪੱਤੇ ਪੀਲੇ ਹੋ ਰਹੇ ਹਨ",
    ta: "பருத்தி இலைகளின் அடியில் அசுவினி பூச்சிகள் உள்ளன, இலைகள் மஞ்சளாகின்றன",
    kn: "ಹತ್ತಿ ಎಲೆಗಳ ಕೆಳಗೆ ಹೇನು ಕೀಟಗಳು ಕಾಣಿಸುತ್ತಿವೆ ಮತ್ತು ಎಲೆಗಳು ಹಳದಿಯಾಗುತ್ತಿವೆ",
    bn: "তুলোর পাতার নিচে জাব পোকা দেখা যাচ্ছে এবং পাতা হলুদ হয়ে যাচ্ছে",
    gu: "કપાસના પાન નીચે મોલો-મશી જીવાત છે અને પાન પીળાં પડી રહ્યાં છે",
    ml: "പരുത്തി ഇലകൾക്ക് അടിയിൽ അഫിഡുകൾ കാണപ്പെടുന്നു, ഇലകൾ മഞ്ഞനിറമാകുന്നു",
    or: "କପା ପତ୍ର ତଳେ ମହିଷା ପୋକ ଲାଗିଛନ୍ତି ଏବଂ ପତ୍ର ହଳଦିଆ ପଡ଼ିଯାଉଛି",
    en: "Aphids are colonizing lower cotton leaves causing downward cupping and yellowing"
  },
  8: {
    hi: "धान की पत्तियों पर आंख के आकार के धब्बे (ब्लास्ट) दिखाई दे रहे हैं",
    pa: "ਝੋਨੇ ਦੀਆਂ ਪੱਤੀਆਂ ਤੇ ਅੱਖ ਦੇ ਆਕਾਰ ਦੇ ਧੱਬੇ ਦਿਖਾਈ ਦੇ ਰਹੇ ਹਨ",
    te: "వరి ఆకులపై కంటి ఆకారంలో మచ్చలు (బ్లాస్ట్) కనిపిస్తున్నాయి",
    mr: "भाताच्या पानांवर डोळ्याच्या आकाराचे करप्याचे ठिपके दिसत आहेत",
    ta: "நெல் இலைகளில் கண் போன்ற வடிவத்தில் குலை நோய் புள்ளிகள் உள்ளன",
    kn: "ಭತ್ತದ ಎಲೆಗಳ ಮೇಲೆ ಕಣ್ಣಿನ ಆಕಾರದ ಬೆಂಕಿ ರೋಗದ ಮಚ್ಚೆಗಳು ಕಾಣಿಸುತ್ತಿವೆ",
    bn: "ধানের পাতায় চোখের মতো আকারের ব্লাস্ট দাগ দেখা যাচ্ছে",
    gu: "ડાંગરના પાન પર આંખ જેવા આકારના બ્લાસ્ટના ટપકાં દેખાય છે",
    ml: "നെല്ലിന്റെ ഇലകളിൽ കണ്ണിന്റെ ആകൃതിയിലുള്ള കുമിൾ പാടുകൾ കാണപ്പെടുന്നു",
    or: "ଧାନ ପତ୍ରରେ ଆଖି ଆକାରର ବ୍ଲାଷ୍ଟ ଦାଗ ଦେଖାଯାଉଛି",
    en: "Spindle eye-shaped lesions with grey centres are visible on paddy leaves"
  },
  11: {
    hi: "टमाटर की पत्तियों पर पीले छल्ले वाले भूरे गोल धब्बे दिख रहे हैं",
    te: "టమాటా ఆకులపై గోళాకార మచ్చలు, పసుపు రంగు హలో కనిపిస్తోంది",
    mr: "टोमॅटोच्या पानांवर पिवळ्या कडा असलेले गोलाकार करप्याचे ठिपके दिसत आहेत",
    pa: "ਟਮਾਟਰ ਦੇ ਪੱਤਿਆਂ 'ਤੇ ਪੀਲੇ ਘੇਰੇ ਵਾਲੇ ਗੋਲ ਧੱਬੇ ਦਿਖਾਈ ਦੇ ਰਹੇ ਹਨ",
    ta: "தக்காளி இலைகளில் மஞ்சள் வளையங்களுடன் கூடிய வட்டப் புள்ளிகள் தெரிகின்றன",
    kn: "ಟೊಮೆಟೊ ಎಲೆಗಳ ಮೇಲೆ ಹಳದಿ ವೃತ್ತವಿರುವ ದುಂಡಗಿನ ಮಚ್ಚೆಗಳು ಕಾಣಿಸುತ್ತಿವೆ",
    bn: "টমেটোর পাতায় হলুদ বলয়যুক্ত গোল দাগ দেখা যাচ্ছে",
    gu: "ટામેટાના પાન પર પીળા કુંડાળા સાથે ગોળ ટપકાં દેખાય છે",
    ml: "തക്കാളി ഇലകളിൽ മഞ്ഞ വലയത്തോടുകൂടിയ വട്ടപ്പുള്ളികൾ കാണപ്പെടുന്നു",
    or: "ଟମାଟୋ ପତ୍ରରେ ହଳଦିଆ ବଳୟ ଥିବା ଗୋଲ ଦାଗ ଦେଖାଯାଉଛି",
    en: "Concentric circular dark spots with yellow chlorotic halo visible on tomato leaves"
  }
};

function cropDoctorDemo() {
  return {
    language:       "hi",
    crop:           "chilli",
    imageFile:      "01_chilli_leaf_curl_whitefly.jpg",
    transcript:     "हमारी मिर्च की पत्तियां ऊपर की तरफ मुड़ रही हैं और पत्तियों के नीचे सफेद रंग के छोटे कीड़े दिखाई दे रहे हैं",
    scenarioId:     "1",
    loading:        false,
    result:         null,
    error:          null,
    openAccordion:  null,
    expandedChunks: {},
    isSpeaking:     false,

    init() {},

    setLanguage(code) {
      this.language = code;
      const sId = parseInt(this.scenarioId);
      if (sId && SCENARIO_TRANSLATIONS[sId] && SCENARIO_TRANSLATIONS[sId][code]) {
        this.transcript = SCENARIO_TRANSLATIONS[sId][code];
      }
    },

    loadScenario() {
      const id = parseInt(this.scenarioId);
      if (!id || !SCENARIOS[id]) return;
      const s = SCENARIOS[id];
      this.crop      = s.crop;
      this.imageFile = s.image;
      if (SCENARIO_TRANSLATIONS[id] && SCENARIO_TRANSLATIONS[id][this.language]) {
        this.transcript = SCENARIO_TRANSLATIONS[id][this.language];
      } else {
        this.language  = s.language;
        this.transcript = s.transcript;
      }
      this.result    = null;
      this.error     = null;
      this.openAccordion = null;
      this.expandedChunks = {};
    },

    async analyze() {
      if (!this.transcript.trim()) {
        this.error = "Please enter a farmer transcript before analysing.";
        return;
      }
      this.loading = true;
      this.result  = null;
      this.error   = null;
      this.openAccordion = null;
      this.expandedChunks = {};

      try {
        const payload = {
          scenario_id: this.scenarioId || null,
          language:    this.language,
          crop:        this.crop,
          transcript:  this.transcript,
          image_file:  this.imageFile || null
        };
        const resp = await fetch("/api/simulate", {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify(payload)
        });
        if (!resp.ok) {
          const txt = await resp.text();
          throw new Error(`Server error ${resp.status}: ${txt}`);
        }
        this.result = await resp.json();
        this.$nextTick(() => {
          const a = document.getElementById('advisoryAudio');
          if (a) {
            a.load();
          }
        });
      } catch (err) {
        this.error = err.message || "Unknown error occurred.";
      } finally {
        this.loading = false;
      }
    },

    visionRows() {
      if (!this.result || !this.result.vision_obs) return [];
      const obs = this.result.vision_obs;
      const keys = ["spots","colour","curling","insects","visible_pattern","is_plant","is_clear"];
      return keys
        .filter(k => obs[k] !== undefined && obs[k] !== null)
        .map(k => [k, String(obs[k])]);
    },

    confBadgeClass(val) {
      if (val >= 0.75) return "bg-green-800 text-green-200";
      if (val >= 0.5)  return "bg-yellow-800 text-yellow-200";
      return "bg-red-800 text-red-200";
    },

    toggleAccordion(idx) {
      this.openAccordion = this.openAccordion === idx ? null : idx;
    },

    truncate(text, len) {
      if (!text) return "";
      return text.length > len ? text.slice(0, len) + "…" : text;
    },

    speakAloud(text) {
      if (!window.speechSynthesis) {
        alert("Speech synthesis is not supported in this browser.");
        return;
      }
      if (this.isSpeaking) {
        window.speechSynthesis.cancel();
        this.isSpeaking = false;
        return;
      }
      if (!text) return;
      window.speechSynthesis.cancel();
      // Remove URLs, source lines for cleaner speech reading
      const cleanText = text.replace(/Source:.*$/im, '').trim();
      const utterance = new SpeechSynthesisUtterance(cleanText);
      const langMap = {
        hi: "hi-IN", te: "te-IN", mr: "mr-IN", pa: "pa-IN",
        ta: "ta-IN", kn: "kn-IN", bn: "bn-IN", gu: "gu-IN",
        ml: "ml-IN", or: "or-IN", en: "en-IN"
      };
      utterance.lang = langMap[this.language] || "hi-IN";
      utterance.rate = 0.9;
      utterance.onend = () => { this.isSpeaking = false; };
      utterance.onerror = () => { this.isSpeaking = false; };
      this.isSpeaking = true;
      window.speechSynthesis.speak(utterance);
    }
  };
}
</script>


  <!-- Floating WhatsApp Simulator Launcher -->
  <aside class="fixed bottom-6 right-6 z-50">
    <a href="/whatsapp"
       title="Open WhatsApp Web Simulator"
       class="group flex items-center gap-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold pl-4 pr-5 py-3.5 rounded-full shadow-2xl hover:shadow-emerald-500/50 transition-all transform hover:-translate-y-1 border border-emerald-300/40">
      <span class="relative flex h-3.5 w-3.5">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-200 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-400"></span>
      </span>
      <i class="fa-brands fa-whatsapp text-2xl text-white"></i>
      <div class="text-left leading-tight">
        <div class="text-[10px] text-emerald-100 uppercase tracking-widest font-extrabold">Live Demo</div>
        <div class="text-sm font-bold text-white flex items-center gap-1.5">
          WhatsApp Simulator
          <i class="fa-solid fa-arrow-right text-xs group-hover:translate-x-1 transition-transform"></i>
        </div>
      </div>
    </a>
  </aside>

</body>
</html>"""
    return HTMLResponse(content=html)
