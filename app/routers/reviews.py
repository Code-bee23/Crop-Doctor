import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.database import db, _in_memory_cases
from app.services.retriever import guide_retriever

logger = logging.getLogger("crop_doctor.reviews")
router = APIRouter(prefix="", tags=["Review Dashboard"])


class ReviewSubmission(BaseModel):
    case_id: str
    reviewer: str
    verdict: str  # 'correct', 'partly', 'wrong'
    note: Optional[str] = None


@router.get("/api/cases", summary="Get all cases for review audit")
async def get_all_cases() -> List[Dict[str, Any]]:
    """
    Fetch all consultation cases with their vision observations,
    retrieved passages, and answers for expert auditing.
    """
    if db.client:
        try:
            res = db.client.table("cases").select("*, reviews(*)").order("created_at", desc=True).execute()
            if res.data:
                return res.data
        except Exception as e:
            logger.warning(f"Failed to fetch cases from Supabase: {e}")

    # Fallback to local memory cases. If empty, load benchmark seed cases for instant demonstration.
    if not _in_memory_cases:
        seed_benchmark_cases()

    cases_list = list(_in_memory_cases.values())
    cases_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return cases_list


def seed_benchmark_cases():
    """Seed sample clinical cases for review dashboard demonstration."""
    sample_items = [
        {
            "id": "case_chilli_whitefly_01",
            "wa_phone": "919876543201",
            "crop": "chilli",
            "photo_path": "storage/test_leaves/01_chilli_leaf_curl_whitefly.jpg",
            "voice_path": "storage/audio/sample_voice.ogg",
            "answer_audio_path": "storage/audio/tts_case_01.wav",
            "transcript": "Naa mirapa thotaki aravai rojulu, aakulu paiki muduchukupotunnayi, aakula kinda tella purugulu unnayi.",
            "answer_text": (
                "1. ప్రధాన సమస్య: తెల్ల దోమ మరియు ఆకు ముడత (Tella doma)\n"
                "2. రసాయనం లేని రక్షణ: ఎకరాకు 10 నుండి 15 పసుపు రంగు జిగురు అట్టలు ఏర్పాటు చేయండి.\n"
                "3. సిఫార్సు మందు: Diafenthiuron 50% WP - మోతాదు: 1.25 g per litre (18.75 g to 19 g per 15-litre spray tank).\n"
                "4. రక్షణ సూచన: మందు పిచికారీ చేసేటప్పుడు తప్పనిసరిగా ముక్కుకు మాస్క్ మరియు చేతులకు గ్లౌజులు ధరించండి.\n"
                "5. సమస్య 4-5 రోజుల్లో తగ్గకపోతే KVK ని సంప్రదించండి.\n"
                "Source: PJTSAU Hyderabad - Chilli Production Technology (Page 18)"
            ),
            "confidence": 0.89,
            "escalated": False,
            "status": "completed",
            "reviews": [
                {"reviewer": "Dr. Ramesh (KVK Warangal)", "verdict": "correct", "note": "Accurate dose per PJTSAU guide"}
            ]
        },
        {
            "id": "case_cotton_pink_bollworm_02",
            "wa_phone": "919876543202",
            "crop": "cotton",
            "photo_path": "storage/test_leaves/05_cotton_pink_bollworm.jpg",
            "voice_path": "storage/audio/sample_voice.ogg",
            "answer_audio_path": "storage/audio/tts_case_02.wav",
            "transcript": "Kapsala nawwad divas jhale, bondat gulabi aali disat aahe, kay faravu?",
            "answer_text": (
                "1. मुख्य समस्या: गुलाबी बोंड अळी (Gulabi bond aali)\n"
                "2. बिगर रासायनिक उपाय: झाडावरील डोमकळ्या तोडून नष्ट करा. एकरी ५ कामगंध सापळे लावा.\n"
                "3. शिफारस केलेले औषध: Profenophos 50% EC - प्रमाण: 2 ml per litre (30 ml per 15-litre knapsack pump).\n"
                "4. सुरक्षा सूचना: तोंडाला मास्क आणि हातात हातमोजे वापरा. वाऱ्याच्या विरुद्ध दिशेने फवारणी करू नका.\n"
                "5. ४-५ दिवसांत फरक न पडल्यास जवळच्या KVK शी संपर्क साधा.\n"
                "Source: MPKV Rahuri - Cotton Advisory (Page 24)"
            ),
            "confidence": 0.93,
            "escalated": False,
            "status": "completed",
            "reviews": []
        },
        {
            "id": "case_paddy_brown_spot_03",
            "wa_phone": "919876543203",
            "crop": "paddy",
            "photo_path": "storage/test_leaves/08_paddy_brown_spot.jpg",
            "voice_path": "storage/audio/sample_voice.ogg",
            "answer_audio_path": "storage/audio/tts_case_03.wav",
            "transcript": "Mere jhone di fasal 45 dina di hai, pattean te bhoore dhabbe aa gaye ne.",
            "answer_text": (
                "1. ਮੁੱਖ ਸਮੱਸਿਆ: ਝੋਨੇ ਦਾ ਭੂਰੇ ਧੱਬਿਆਂ ਦਾ ਰੋਗ (Bhoore dhabbe)\n"
                "2. ਗ਼ੈਰ-ਰਸਾਇਣਕ ਉਪਾਅ: ਯੂਰੀਆ ਦੀ ਜ਼ਿਆਦਾ ਵਰਤੋਂ ਨਾ ਕਰੋ। ਖੇਤ ਵਿੱਚੋਂ ਖੜ੍ਹਾ ਪਾਣੀ ਕੱਢ ਕੇ ਤਾਜ਼ਾ ਪਾਣੀ ਲਗਾਓ।\n"
                "3. ਸਿਫ਼ਾਰਸ਼ ਕੀਤੀ ਦਵਾਈ: Propiconazole 25% EC - ਮਾਤਰਾ: 1 ml per litre (15 ml per 15-litre spray pump).\n"
                "4. ਸੁਰੱਖਿਆ: ਸਪਰੇਅ ਕਰਦੇ ਸਮੇਂ ਮਾਸਕ ਅਤੇ ਦਸਤਾਨੇ ਜ਼ਰੂਰ ਪਹਿਨੋ।\n"
                "5. ਰੋਗ ਨਾ ਰੁਕੇ ਤਾਂ ਕ੍ਰਿਸ਼ੀ ਵਿਗਿਆਨ ਕੇਂਦਰ (KVK) ਨਾਲ ਸੰਪਰਕ ਕਰੋ।\n"
                "Source: PAU Ludhiana - Kharif Crops Guide (Page 42)"
            ),
            "confidence": 0.90,
            "escalated": False,
            "status": "completed",
            "reviews": []
        },
        {
            "id": "case_tomato_yellowing_04",
            "wa_phone": "919876543204",
            "crop": "tomato",
            "photo_path": "storage/test_leaves/11_tomato_nitrogen_yellowing.jpg",
            "voice_path": "storage/audio/sample_voice.ogg",
            "answer_audio_path": "storage/audio/tts_case_04.wav",
            "transcript": "Tomato aakulu pasupu ga maaripotunnayi, kinda aakulu modhata.",
            "answer_text": (
                "1. ప్రధాన సమస్య: నత్రజని లోపం (Nitrogen Deficiency - Nutritional Chlorosis)\n"
                "2. రక్షణ చర్య: ఇది తెగులు కాదు; పోషక లోపం. ఎటువంటి పురుగు మందులు వాడవద్దు. మొక్కల మొదళ్లలో పశువుల ఎరువు లేదా వర్మీకంపోస్ట్ వేయండి.\n"
                "3. సిఫార్సు: Urea (Foliar Nutrition) - మోతాదు: 10 g per litre (1% solution) (150 g per 15-litre spray tank).\n"
                "4. రక్షణ సూచన: ఉదయం లేదా సాయంత్రం వేళల్లో పిచికారీ చేయండి.\n"
                "Source: Dr. YSRHU - Commercial Vegetable Guide (Page 12)"
            ),
            "confidence": 0.89,
            "escalated": False,
            "status": "completed",
            "reviews": []
        },
        {
            "id": "case_blurry_rejection_05",
            "wa_phone": "919876543205",
            "crop": "cotton",
            "photo_path": "storage/test_leaves/16_blurry_leaf_photo.jpg",
            "voice_path": "storage/audio/sample_voice.ogg",
            "answer_audio_path": "storage/audio/tts_case_05.wav",
            "transcript": "Paha panala kay jhalay te disat nahi nit.",
            "answer_text": "फोटो अंधुक आहे किंवा खूप लांबून काढला आहे. कृपया बाधित एका पानाच्या वरच्या आणि खालच्या बाजूचा जवळून (close-up) स्पष्ट फोटो पाठवा.",
            "confidence": 0.95,
            "escalated": False,
            "status": "ask_more",
            "reviews": []
        }
    ]
    for item in sample_items:
        _in_memory_cases[item["id"]] = item


@router.post("/reviews/audit", summary="Submit expert agricultural review verdict")
async def submit_review(
    case_id: str = Form(...),
    reviewer: str = Form(...),
    verdict: str = Form(...),
    note: Optional[str] = Form("")
):
    """
    Records an expert or agricultural student verdict (correct, partly, wrong)
    for a diagnosed case.
    """
    if verdict not in ("correct", "partly", "wrong"):
        raise HTTPException(status_code=400, detail="Verdict must be 'correct', 'partly', or 'wrong'")

    review_data = {
        "case_id": case_id,
        "reviewer": reviewer.strip(),
        "verdict": verdict,
        "note": note.strip()
    }

    if db.client:
        try:
            db.client.table("reviews").insert(review_data).execute()
            logger.info(f"Persisted review in Supabase for Case {case_id}")
        except Exception as e:
            logger.error(f"Error persisting review to Supabase: {e}")

    # Also store in local memory for offline testing
    if case_id in _in_memory_cases:
        if "reviews" not in _in_memory_cases[case_id]:
            _in_memory_cases[case_id]["reviews"] = []
        _in_memory_cases[case_id]["reviews"].append(review_data)

    logger.info(f"Review recorded: Case={case_id}, Reviewer={reviewer}, Verdict={verdict}")
    return RedirectResponse(url="/reviews", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/reviews", response_class=HTMLResponse, summary="Agricultural Review Web Dashboard")
async def review_dashboard_html():
    """
    Full web dashboard for agricultural students and KVK officers
    to audit diagnoses, verify citations, and evaluate accuracy.
    """
    cases = await get_all_cases()

    # Pre-render case rows
    cards_html = ""
    for c in cases:
        case_id = c.get("id", "N/A")
        phone = c.get("wa_phone", "Anonymous")
        # Mask phone number for privacy
        masked_phone = f"+91 {phone[-10:-6]}****{phone[-2:]}" if len(phone) >= 10 else phone
        crop = (c.get("crop") or "Unspecified").capitalize()
        status_tag = c.get("status", "received").upper()
        confidence = c.get("confidence")
        conf_str = f"{float(confidence):.0%}" if confidence else "N/A"
        answer = c.get("answer_text", "No answer formulated yet.")
        transcript = c.get("transcript", "No transcript available.")
        escalated = c.get("escalated", False)

        # Existing reviews
        reviews = c.get("reviews", [])
        reviews_badge = ""
        for r in reviews:
            v = r.get("verdict", "review")
            color = "#15803d" if v == "correct" else ("#b45309" if v == "partly" else "#b91c1c")
            reviews_badge += f"<span style='background: {color}; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-right: 4px;'>{r.get('reviewer')}: {v.upper()}</span>"

        photo_elem = "<div style='color: #64748b; font-style: italic;'>No photo attached</div>"
        if c.get("photo_path"):
            photo_elem = f"<a href='/{c.get('photo_path')}' target='_blank'><img src='/{c.get('photo_path')}' style='max-width: 160px; max-height: 160px; border-radius: 6px; border: 1px solid #cbd5e1;' alt='Leaf photo' /></a>"

        audio_elem = ""
        if c.get("voice_path"):
            audio_elem += f"<div style='margin-top: 6px;'><b>Farmer Voice:</b><br><audio controls src='/{c.get('voice_path')}' style='width: 100%; height: 32px;'></audio></div>"
        if c.get("answer_audio_path"):
            audio_elem += f"<div style='margin-top: 6px;'><b>Timbre Reply:</b><br><audio controls src='/{c.get('answer_audio_path')}' style='width: 100%; height: 32px;'></audio></div>"

        cards_html += f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #f1f5f9; padding-bottom: 10px; margin-bottom: 12px;">
                <div>
                    <span style="font-size: 16px; font-weight: 700; color: #0f172a;">Case #{str(case_id)[:8]}</span>
                    <span style="margin-left: 8px; background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">{crop}</span>
                    <span style="margin-left: 6px; background: {'#fee2e2' if escalated else '#dcfce7'}; color: {'#991b1b' if escalated else '#166534'}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">{'ESCALATED' if escalated else status_tag}</span>
                </div>
                <div style="font-size: 12px; color: #64748b;">
                    Farmer: <b>{masked_phone}</b> | Confidence: <b>{conf_str}</b>
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 180px 1fr 1fr; gap: 16px;">
                <!-- Column 1: Media -->
                <div>
                    {photo_elem}
                    {audio_elem}
                </div>

                <!-- Column 2: Farmer Input & Diagnosis -->
                <div>
                    <div style="font-size: 12px; color: #475569; margin-bottom: 8px;">
                        <b>Transcript:</b><br>
                        <span style="background: #f8fafc; padding: 6px; display: block; border-radius: 4px; border: 1px solid #e2e8f0;">{transcript}</span>
                    </div>
                    <div style="font-size: 12px; color: #1e293b;">
                        <b>Evon Validated Advisory:</b><br>
                        <pre style="background: #f1f5f9; padding: 8px; border-radius: 4px; white-space: pre-wrap; font-family: inherit; font-size: 12px; line-height: 1.4; border-left: 3px solid #22c55e;">{answer}</pre>
                    </div>
                </div>

                <!-- Column 3: Expert Review Form -->
                <div style="background: #fafafa; padding: 12px; border-radius: 6px; border: 1px solid #e5e7eb;">
                    <div style="font-size: 12px; font-weight: 700; margin-bottom: 6px; color: #334155;">Expert Audit Review</div>
                    <div style="margin-bottom: 8px;">{reviews_badge or '<span style=\"font-size: 11px; color: #94a3b8;\">Pending review</span>'}</div>
                    <form action="/reviews/audit" method="POST">
                        <input type="hidden" name="case_id" value="{case_id}" />
                        <div style="margin-bottom: 6px;">
                            <label style="font-size: 11px; color: #64748b;">Reviewer Name / KVK:</label><br>
                            <input type="text" name="reviewer" required style="width: 100%; padding: 4px 6px; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px;" placeholder="Dr. Sharma, PAU" />
                        </div>
                        <div style="margin-bottom: 6px;">
                            <label style="font-size: 11px; color: #64748b;">Verdict:</label><br>
                            <select name="verdict" style="width: 100%; padding: 4px 6px; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px;">
                                <option value="correct">Correct (Diagnosis & Citation Accurate)</option>
                                <option value="partly">Partly Correct (Dose/Product Minor Mismatch)</option>
                                <option value="wrong">Wrong (Misdiagnosis / Dangerous Advice)</option>
                            </select>
                        </div>
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #64748b;">Notes / Observations:</label><br>
                            <textarea name="note" rows="2" style="width: 100%; padding: 4px 6px; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px;" placeholder="Verified against ICAR Package of Practices..."></textarea>
                        </div>
                        <button type="submit" style="background: #2563eb; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; font-weight: 600;">Submit Audit</button>
                    </form>
                </div>
            </div>
        </div>
        """

    total_cases = len(cases)
    reviewed_cases = sum(1 for c in cases if c.get("reviews"))

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Crop Doctor on WhatsApp - Expert Case Review Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 24px; color: #0f172a; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
            .stats-card {{ background: #fff; padding: 12px 20px; border-radius: 8px; border: 1px solid #e2e8f0; display: inline-block; font-size: 13px; font-weight: 600; color: #334155; }}
        </style>
    </head>
    <body>
        <div class="container">

    <nav style="background: #14532d; padding: 12px 24px; color: #fff; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #16a34a; margin-bottom: 24px; border-radius: 8px;">
        <a href="/" style="color: #fff; font-weight: 700; text-decoration: none; font-size: 18px; display: flex; align-items: center; gap: 8px;">
            🌾 Crop Doctor
        </a>
        <div style="display: flex; gap: 18px; font-size: 14px; font-weight: 500;">
            <a href="/" style="color: #bbf7d0; text-decoration: none;">Home</a>
            <a href="/whatsapp" style="color: #4ade80; text-decoration: none; font-weight: 700;">💬 WhatsApp Web Simulator</a>
            <a href="/demo" style="color: #bbf7d0; text-decoration: none;">Clinical Demo</a>
            <a href="/guides" style="color: #bbf7d0; text-decoration: none;">Guides</a>
            <a href="/stats" style="color: #bbf7d0; text-decoration: none;">Analytics</a>
            <a href="/reviews" style="color: #ffffff; text-decoration: none; border-bottom: 2px solid #4ade80; padding-bottom: 2px;">Review Dashboard</a>
            <a href="/docs" style="color: #bbf7d0; text-decoration: none;">API Docs</a>
        </div>
    </nav>

            <div class="header">
                <div>
                    <h1 style="margin: 0; font-size: 24px; color: #166534;">🌾 Crop Doctor on WhatsApp - Expert Review Dashboard</h1>
                    <p style="margin: 4px 0 0; color: #64748b; font-size: 13px;">Clinical case audits by Agriculture University students and Krishi Vigyan Kendra (KVK) scientists.</p>
                </div>
                <div>
                    <div class="stats-card">
                        Total Cases: <span style="color: #2563eb;">{total_cases}</span> | Audited: <span style="color: #16a34a;">{reviewed_cases}</span>
                    </div>
                </div>
            </div>

            {cards_html if cards_html else '<div style="background: #fff; padding: 40px; text-align: center; border-radius: 8px; border: 1px solid #e2e8f0; color: #64748b;">No farmer consultation cases logged yet. Send a test message or run the test suite!</div>'}
        </div>
    
    <div style="position: fixed; bottom: 24px; right: 24px; z-index: 1000;">
        <a href="/whatsapp" style="display: flex; align-items: center; gap: 10px; background: #059669; color: #ffffff; text-decoration: none; padding: 12px 20px; border-radius: 9999px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); font-weight: 700; font-size: 14px; border: 1px solid rgba(255,255,255,0.3);">
            <span style="font-size: 20px;">💬</span> Open WhatsApp Web Simulator →
        </a>
    </div>
    
</body>
    </html>
    """
    return HTMLResponse(content=html)

