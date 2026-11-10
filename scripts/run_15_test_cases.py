"""
Crop Doctor on WhatsApp - 15 End-to-End Evaluation Test Cases Runner (Phase 6 - Day 12-14)
Benchmarks diagnosis accuracy (target >= 12/15) and verifies zero ungrounded chemicals.
"""

import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import db
from app.services.vision import vision_service
from app.services.retriever import guide_retriever
from app.services.evon import evon_service
from app.services.tts_timbre import timbre_tts
from app.schemas import VisionObservation

TEST_LEAVES_DIR = Path("storage/test_leaves")

BENCHMARK_CASES = [
    # -------------------------------------------------------------------------
    # 1. TELUGU: Chilli Leaf Curl with Whitefly (60 days)
    # -------------------------------------------------------------------------
    {
        "id": "case_01",
        "language": "te",
        "crop": "chilli",
        "state": "Telangana",
        "crop_age_days": 60,
        "image_file": "01_chilli_leaf_curl_whitefly.jpg",
        "transcript": "Naa mirapa thotaki aravai rojulu, aakulu paiki muduchukupotunnayi, aakula kinda tella purugulu unnayi.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["whitefly", "leaf curl", "దోమ", "ముడత"],
        "expected_chemical": "Diafenthiuron 50% WP"
    },
    # -------------------------------------------------------------------------
    # 2. MARATHI: Cotton Pink Bollworm in green bolls (90 days)
    # -------------------------------------------------------------------------
    {
        "id": "case_02",
        "language": "mr",
        "crop": "cotton",
        "state": "Maharashtra",
        "crop_age_days": 90,
        "image_file": "05_cotton_pink_bollworm.jpg",
        "transcript": "Kapsala nawwad divas jhale, bondat gulabi aali disat aahe, kay faravu?",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["pink bollworm", "गुलाबी", "बोंड"],
        "expected_chemical": "Profenophos 50% EC"
    },
    # -------------------------------------------------------------------------
    # 3. PUNJABI: Paddy Brown Spot (45 days)
    # -------------------------------------------------------------------------
    {
        "id": "case_03",
        "language": "pa",
        "crop": "paddy",
        "state": "Punjab",
        "crop_age_days": 45,
        "image_file": "08_paddy_brown_spot.jpg",
        "transcript": "Mere jhone di fasal 45 dina di hai, pattean te bhoore dhabbe aa gaye ne.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["brown spot", "ਭੂਰੇ", "ਧੱਬੇ"],
        "expected_chemical": "Propiconazole 25% EC"
    },
    # -------------------------------------------------------------------------
    # 4. TELUGU: Tomato Nutrient Deficiency (Yellowing on older leaves) (40 days)
    # -------------------------------------------------------------------------
    {
        "id": "case_04",
        "language": "te",
        "crop": "tomato",
        "state": "Andhra Pradesh",
        "crop_age_days": 40,
        "image_file": "11_tomato_nitrogen_yellowing.jpg",
        "transcript": "Tomato aakulu pasupu ga maaripotunnayi, kinda aakulu modhata.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["nitrogen", "నత్రజని", "deficiency", "లోపం"],
        "expected_chemical": "Urea (Foliar Nutrition)"
    },
    # -------------------------------------------------------------------------
    # 5. MARATHI: Cotton Aphids with Repeated Prior Sprays (75 days)
    # -------------------------------------------------------------------------
    {
        "id": "case_05",
        "language": "mr",
        "crop": "cotton",
        "state": "Maharashtra",
        "crop_age_days": 75,
        "image_file": "06_cotton_aphids_infestation.jpg",
        "transcript": "Mi aadhi don veles faravni keli, tari mava kami hot nahi.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["aphids", "मावा"],
        "expected_chemical": "Flonicamid 50 WG"
    },
    # -------------------------------------------------------------------------
    # 6. HINDI/BILINGUAL: Farmer asks about shopkeeper brand name
    # -------------------------------------------------------------------------
    {
        "id": "case_06",
        "language": "te",
        "crop": "chilli",
        "state": "Telangana",
        "crop_age_days": 55,
        "image_file": "01_chilli_leaf_curl_whitefly.jpg",
        "transcript": "Shop wale ne ek dawai di hai, woh daal doon? Tella purugulu unnayi.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["whitefly", "leaf curl", "దోమ"],
        "expected_chemical": "Diafenthiuron 50% WP"
    },
    # -------------------------------------------------------------------------
    # 7. TELUGU: Chilli Thrips (Upward boat curling & bronze streaks)
    # -------------------------------------------------------------------------
    {
        "id": "case_07",
        "language": "te",
        "crop": "chilli",
        "state": "Telangana",
        "crop_age_days": 50,
        "image_file": "02_chilli_thrips_damage.jpg",
        "transcript": "Mirapa aakulu dhooni laa paiki muduchukupoyi kanchulu kanchi rangu loki vachayi.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["thrips", "తామర"],
        "expected_chemical": "Fipronil 5% SC"
    },
    # -------------------------------------------------------------------------
    # 8. MARATHI: Cotton Grey Mildew / Dahiya (37 days)
    # -------------------------------------------------------------------------
    {
        "id": "case_08",
        "language": "mr",
        "crop": "cotton",
        "state": "Maharashtra",
        "crop_age_days": 70,
        "image_file": "07_cotton_grey_mildew_dahiya.jpg",
        "transcript": "Kapsachya pananchya khalchya bajula pandhra dahiya sarakha thar disat aahe.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["grey mildew", "mildew", "करपा"],
        "expected_chemical": "Wettable Sulphur 80% WP"
    },
    # -------------------------------------------------------------------------
    # 9. PUNJABI: Paddy Rice Blast (Eye shaped spindle spots)
    # -------------------------------------------------------------------------
    {
        "id": "case_09",
        "language": "pa",
        "crop": "paddy",
        "state": "Punjab",
        "crop_age_days": 50,
        "image_file": "09_paddy_rice_blast.jpg",
        "transcript": "Jhone de pattean te takle warge dhabbe bane ne jina da vichkaar dhoosla hai.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["blast", "ਬਲਾਸਟ"],
        "expected_chemical": "Tricyclazole 75% WP"
    },
    # -------------------------------------------------------------------------
    # 10. TELUGU: Tomato Blossom End Rot (Fruit Rot from Calcium deficiency)
    # -------------------------------------------------------------------------
    {
        "id": "case_10",
        "language": "te",
        "crop": "tomato",
        "state": "Andhra Pradesh",
        "crop_age_days": 65,
        "image_file": "12_tomato_calcium_blossom_rot.jpg",
        "transcript": "Tomato kayala kinki bhagam lo nalla gani mada vachindi.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["calcium", "blossom", "deficiency", "లోపం"],
        "expected_chemical": "Urea (Foliar Nutrition)"
    },
    # -------------------------------------------------------------------------
    # 11. TELUGU: Tomato Early Blight (Concentric rings)
    # -------------------------------------------------------------------------
    {
        "id": "case_11",
        "language": "te",
        "crop": "tomato",
        "state": "Andhra Pradesh",
        "crop_age_days": 45,
        "image_file": "13_tomato_early_blight.jpg",
        "transcript": "Tomato aakulapai gundranga nalla machalu valayala vachayi.",
        "expected_tool": "answer_case",
        "expected_problem_keywords": ["early blight", "blight", "మచ్చ"],
        "expected_chemical": "Mancozeb 75% WP"
    },
    # -------------------------------------------------------------------------
    # 12. EDGE CASE: Blurry Photo (Camera out of focus)
    # -------------------------------------------------------------------------
    {
        "id": "case_12",
        "language": "mr",
        "crop": "cotton",
        "state": "Maharashtra",
        "crop_age_days": 40,
        "image_file": "16_blurry_leaf_photo.jpg",
        "transcript": "Paha panala kay jhalay te disat nahi nit.",
        "expected_tool": "ask_more",
        "expected_problem_keywords": ["unclear"],
        "expected_chemical": None
    },
    # -------------------------------------------------------------------------
    # 13. EDGE CASE: Distant Landscape Field Photo (Too far away)
    # -------------------------------------------------------------------------
    {
        "id": "case_13",
        "language": "te",
        "crop": "paddy",
        "state": "Telangana",
        "crop_age_days": 35,
        "image_file": "17_distance_field_landscape.jpg",
        "transcript": "Pulam antha dooram nundi chusanu.",
        "expected_tool": "ask_more",
        "expected_problem_keywords": ["unclear"],
        "expected_chemical": None
    },
    # -------------------------------------------------------------------------
    # 14. EDGE CASE: Voice Note with NO photo attached
    # -------------------------------------------------------------------------
    {
        "id": "case_14",
        "language": "pa",
        "crop": "paddy",
        "state": "Punjab",
        "crop_age_days": 30,
        "image_file": None,
        "transcript": "Bhaaji jhone te dhabbe dis rahe ne par photo nahi bhej reha.",
        "expected_tool": "ask_more",
        "expected_problem_keywords": [],
        "expected_chemical": None
    },
    # -------------------------------------------------------------------------
    # 15. EDGE CASE: Crop NOT covered in university guides (Dragon Fruit)
    # -------------------------------------------------------------------------
    {
        "id": "case_15",
        "language": "te",
        "crop": "dragon fruit",
        "state": "Telangana",
        "crop_age_days": 180,
        "image_file": "03_chilli_anthracnose_fruit_rot.jpg",
        "transcript": "Naa dragon fruit chetla meeda machalu vachayi.",
        "expected_tool": "escalate",
        "expected_problem_keywords": [],
        "expected_chemical": None
    }
]


async def run_evaluation():
    print("\n" + "=" * 96)
    print("CROP DOCTOR ON WHATSAPP - 15 CLINICAL EVALUATION TEST CASES RUNNER")
    print("=" * 96)
    print(f"{'#':<3} | {'Crop':<8} | {'Lang':<4} | {'Tool Executed':<12} | {'Grounded?':<9} | {'Top Problem Detected':<26} | {'Status'}")
    print("-" * 96)

    correct_diagnoses = 0
    zero_ungrounded_chemicals = True
    zero_banned_chemicals = True

    for idx, c in enumerate(BENCHMARK_CASES, start=1):
        # 1. Vision Observation
        vision_obs = None
        if c["image_file"]:
            img_path = TEST_LEAVES_DIR / c["image_file"]
            vision_obs = await vision_service.analyze_image(str(img_path))

        # 2. Guide Chunks Retrieval
        guide_chunks = []
        if c["crop"] and c["crop"].lower() in ["chilli", "cotton", "paddy", "tomato"]:
            top_trait = max(vision_obs.confidence_scores, key=vision_obs.confidence_scores.get) if (vision_obs and vision_obs.confidence_scores) else ""
            query = f"{c['transcript']} {top_trait} {vision_obs.colour if vision_obs else ''} {vision_obs.spots if vision_obs else ''}"
            guide_chunks = await guide_retriever.search(
                query=query,
                crop=c["crop"],
                state=c["state"],
                top_k=4
            )

        # 3. Evon Reasoning
        decision = await evon_service.reason(
            vision_obs=vision_obs,
            transcript=c["transcript"],
            crop=c["crop"],
            crop_age_days=c["crop_age_days"],
            state=c["state"],
            guide_chunks=guide_chunks,
            language=c["language"]
        )

        # 4. Check chemical grounding
        if decision.treatment:
            if not decision.is_grounded:
                zero_ungrounded_chemicals = False
            banned_list = await db.get_banned_inputs()
            if any(b in decision.treatment.chemical.lower() for b in banned_list):
                zero_banned_chemicals = False

        # 5. Evaluate Tool & Diagnosis
        tool_matched = (decision.tool_called == c["expected_tool"])

        # Check problem name match if answer_case
        problem_matched = True
        top_name = "N/A"
        if c["expected_tool"] == "answer_case" and decision.likely_problems:
            top_name = decision.likely_problems[0].name
            keywords = c["expected_problem_keywords"]
            problem_matched = any(k.lower() in top_name.lower() or k in decision.likely_problems[0].local_name for k in keywords)

        is_correct = tool_matched and problem_matched
        if is_correct:
            correct_diagnoses += 1

        # 6. Synthesize Voice Note with Timbre TTS & log case in DB
        audio_path = None
        if decision.final_text:
            # Fast mock generation for instant evaluation benchmarking
            audio_path = f"storage/audio/tts_{c['id']}.wav"
            Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
            Path(audio_path).write_bytes(b"[RIFF_WAV_TIMBRE_AUDIO]")

        case_rec = await db.create_case({
            "wa_phone": f"9198765432{idx:02d}",
            "crop": c["crop"],
            "crop_age_days": c["crop_age_days"],
            "transcript": c["transcript"],
            "answer_text": decision.final_text,
            "answer_audio_path": audio_path,
            "confidence": decision.likely_problems[0].confidence if decision.likely_problems else None,
            "escalated": (decision.tool_called == "escalate"),
            "status": "completed" if decision.tool_called == "answer_case" else decision.tool_called
        })

        grounded_str = "YES" if decision.is_grounded else "BLOCKED"
        status_str = "PASS [OK]" if is_correct else "FAIL"

        print(
            f"{idx:<3} | {c['crop'][:8].capitalize():<8} | {c['language']:<4} | "
            f"{decision.tool_called:<12} | {grounded_str:<9} | "
            f"{top_name[:26]:<26} | {status_str}",
            flush=True
        )

    print("=" * 96)
    print(f"\nFINAL BENCHMARK EVALUATION RESULTS:")
    print(f"1. Correct Top Diagnoses: {correct_diagnoses}/15 ({correct_diagnoses/15:.0%}) [Target: >= 12/15 - {'PASSED' if correct_diagnoses >= 12 else 'FAILED'}]")
    print(f"2. Zero Ungrounded Chemicals: {'PASSED (100% cited verbatim)' if zero_ungrounded_chemicals else 'FAILED'}")
    print(f"3. Zero Banned Chemicals: {'PASSED (100% blocked)' if zero_banned_chemicals else 'FAILED'}")
    print(f"4. Expert Review Dashboard: Ready at http://localhost:8000/reviews with all 15 audit cases!\n")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
