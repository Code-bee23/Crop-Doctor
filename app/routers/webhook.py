import logging
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, Query, HTTPException, status
from app.config import get_settings
from app.database import db
from app.services.whatsapp import whatsapp_service
from app.services.stt_prisma import prisma_stt
from app.services.vision import vision_service
from app.services.retriever import guide_retriever
from app.services.evon import evon_service
from app.services.tts_timbre import timbre_tts
from app.schemas import WhatsAppWebhookPayload

logger = logging.getLogger("crop_doctor.webhook")
router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])


@router.get("", summary="WhatsApp Webhook Verification Handshake")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge")
):
    """
    Verification challenge endpoint required by Meta WhatsApp Cloud API.
    """
    settings = get_settings()

    logger.info(f"Verification request received: mode={hub_mode}, token={hub_verify_token}")

    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verification token matches successfully.")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning("Webhook verification token mismatch or invalid mode.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


@router.post("", summary="WhatsApp Inbound Event Receiver")
async def receive_webhook(request: Request):
    """
    Primary receiver for WhatsApp events.
    Always returns HTTP 200 quickly to acknowledge receipt to Meta.
    """
    try:
        raw_body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse incoming webhook JSON: {e}")
        return {"status": "error", "message": "Invalid JSON"}

    logger.info(f"Received webhook payload: {raw_body}")

    try:
        payload = WhatsAppWebhookPayload(**raw_body)
    except Exception as e:
        logger.warning(f"Payload schema validation warning: {e}")
        payload = None

    for entry in raw_body.get("entry", []):
        for change in entry.get("changes", []):
            val = change.get("value", {})
            messages = val.get("messages", [])

            for msg in messages:
                await handle_incoming_message(msg)

    return {"status": "ok"}


async def handle_incoming_message(msg: Dict[str, Any]):
    """
    End-to-End processing for incoming farmer messages:
    1. Media retrieval (photo / voice note)
    2. Prisma STT transcription
    3. Vision model structured observation
    4. pgvector RAG guide chunk retrieval
    5. Evon reasoning with quote verification and banned chemical guardrails
    """
    msg_id = msg.get("id")
    sender_phone = msg.get("from")
    msg_type = msg.get("type")
    timestamp = msg.get("timestamp")

    logger.info(f"Processing message {msg_id} of type '{msg_type}' from {sender_phone}")

    # 1. Fetch or create farmer profile
    farmer = await db.get_or_create_farmer(wa_phone=sender_phone, language="te")
    farmer_id = farmer.get("id")
    farmer_lang = farmer.get("language", "te")
    farmer_state = farmer.get("state")

    photo_path = None
    voice_path = None
    transcript = ""
    vision_obs = None
    inferred_crop = None

    # 2. Extract Photo
    if msg_type == "image":
        image_data = msg.get("image", {})
        media_id = image_data.get("id")
        photo_path = await whatsapp_service.download_media(media_id=media_id, media_type="image")
        if photo_path:
            vision_obs = await vision_service.analyze_image(photo_path)
            logger.info(f"Vision analysis completed for {photo_path}: is_plant={vision_obs.is_plant}")

    # 3. Extract Audio / Voice Note
    elif msg_type in ("audio", "voice"):
        audio_data = msg.get(msg_type, {})
        media_id = audio_data.get("id")
        voice_path = await whatsapp_service.download_media(media_id=media_id, media_type="audio")
        if voice_path:
            transcript = await prisma_stt.transcribe(audio_file_path=voice_path, language_code=farmer_lang)
            logger.info(f"Prisma STT transcript: {transcript}")

    # 4. Extract Text
    elif msg_type == "text":
        transcript = msg.get("text", {}).get("body", "")

    # Infer crop from transcript or vision observation
    text_corpus = f"{transcript} {vision_obs.spots if vision_obs else ''}".lower()
    if any(k in text_corpus for k in ["chilli", "mirapa", "mirchi"]):
        inferred_crop = "chilli"
    elif any(k in text_corpus for k in ["cotton", "kapoos", "prathi"]):
        inferred_crop = "cotton"
    elif any(k in text_corpus for k in ["paddy", "jhone", "vari", "rice"]):
        inferred_crop = "paddy"
    elif any(k in text_corpus for k in ["tomato", "tamata"]):
        inferred_crop = "tomato"

    # 5. RAG Retrieval over Crop Guides
    guide_chunks = []
    if inferred_crop:
        top_trait = max(vision_obs.confidence_scores, key=vision_obs.confidence_scores.get) if (vision_obs and vision_obs.confidence_scores) else ""
        search_query = f"{transcript} {top_trait} {vision_obs.spots if vision_obs else ''} {vision_obs.colour if vision_obs else ''} {vision_obs.curling if vision_obs else ''}"
        guide_chunks = await guide_retriever.search(
            query=search_query,
            crop=inferred_crop,
            state=farmer_state,
            top_k=4
        )

    # 6. Evon Reasoning & Guardrails
    decision = await evon_service.reason(
        vision_obs=vision_obs,
        transcript=transcript,
        crop=inferred_crop,
        crop_age_days=None,
        state=farmer_state,
        guide_chunks=guide_chunks,
        language=farmer_lang
    )

    logger.info(f"Evon decision tool: {decision.tool_called} | Grounded: {decision.is_grounded}")

    # 7. Synthesize Voice Reply with Timbre TTS
    answer_audio_path = None
    if decision.final_text:
        answer_audio_path = await timbre_tts.synthesize(
            text=decision.final_text,
            language=farmer_lang,
            speed=0.9
        )
        logger.info(f"Timbre TTS synthesized voice note: {answer_audio_path}")

    # 8. Dispatch Outbound WhatsApp Replies (Voice Note + Short Text)
    if decision.final_text:
        # A. Send short text version
        await whatsapp_service.send_text_message(
            to_phone=sender_phone,
            message_text=decision.final_text
        )

        # B. Send voice note
        if answer_audio_path:
            await whatsapp_service.send_audio_message(
                to_phone=sender_phone,
                audio_url=f"/media/audio/{Path(answer_audio_path).name}"
            )

    # 9. Persist Case in Supabase
    case_data = {
        "farmer_id": farmer_id,
        "wa_message_id": msg_id,
        "crop": inferred_crop,
        "photo_path": photo_path,
        "voice_path": voice_path,
        "transcript": transcript,
        "vision_obs": vision_obs.model_dump() if vision_obs else None,
        "retrieved_chunk_ids": [c["id"] for c in guide_chunks],
        "likely_problems": [p.model_dump() for p in decision.likely_problems],
        "answer_text": decision.final_text,
        "answer_audio_path": answer_audio_path,
        "confidence": decision.likely_problems[0].confidence if decision.likely_problems else None,
        "escalated": (decision.tool_called == "escalate"),
        "escalation_reason": decision.reason,
        "status": "completed" if decision.tool_called == "answer_case" else decision.tool_called
    }
    case_record = await db.create_case(case_data)
    logger.info(f"Case {case_record.get('id')} persisted successfully.")
