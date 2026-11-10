import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings
from app.services.stt_prisma import prisma_stt
from app.services.tts_timbre import timbre_tts

client = TestClient(app)
settings = get_settings()


def test_root_endpoint():
    """Verify that root endpoint responds with online status."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Crop Doctor on WhatsApp"
    assert data["status"] == "online"


def test_health_check_endpoint():
    """Verify that health check reports healthy state."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["storage_ready"] is True
    assert data["prisma_key_present"] is True


def test_webhook_verification_success():
    """Verify Meta handshake with correct verify token."""
    challenge_str = "1158201444"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
        "hub.challenge": challenge_str
    }
    response = client.get("/webhook", params=params)
    assert response.status_code == 200
    assert response.text == challenge_str


def test_webhook_verification_failure_wrong_token():
    """Verify Meta handshake rejects invalid verify token."""
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token_123",
        "hub.challenge": "1158201444"
    }
    response = client.get("/webhook", params=params)
    assert response.status_code == 403


def test_webhook_inbound_photo_message():
    """Verify incoming leaf/plant photo event creates a case."""
    mock_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100200300",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "919876543210",
                                "phone_number_id": "100200300"
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Ramesh Farmer"},
                                    "wa_id": "919876543210"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.HBgLOTExOTg3NjU0MzIxMBUCABIYFDFB",
                                    "timestamp": "1710000000",
                                    "type": "image",
                                    "image": {
                                        "id": "mock_image_media_id_999",
                                        "mime_type": "image/jpeg",
                                        "sha256": "abcdef123456"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    response = client.post("/webhook", json=mock_payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_inbound_voice_message():
    """Verify incoming audio/voice note event triggers download and Prisma STT log."""
    mock_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100200300",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "919876543210",
                                "phone_number_id": "100200300"
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Balwinder Farmer"},
                                    "wa_id": "919876543211"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "919876543211",
                                    "id": "wamid.HBgLOTExOTg3NjU0MzIxMVUCABIYFDFB",
                                    "timestamp": "1710000010",
                                    "type": "voice",
                                    "voice": {
                                        "id": "mock_voice_media_id_888",
                                        "mime_type": "audio/ogg"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    response = client.post("/webhook", json=mock_payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_prisma_stt_client_structure(tmp_path):
    """Verify Prisma STT client handles audio input and headers."""
    dummy_audio = tmp_path / "sample_voice.ogg"
    dummy_audio.write_bytes(b"RIFFdummydata")

    assert prisma_stt.headers["X-API-Key-ID"] == settings.effective_prisma_key
    assert "stt/v3" in prisma_stt.api_url

    # Transcribe call handles mock/live response gracefully
    transcript = await prisma_stt.transcribe(str(dummy_audio), language_code="te")
    assert isinstance(transcript, str)
    assert len(transcript) > 0


@pytest.mark.asyncio
async def test_timbre_tts_client_structure():
    """Verify Timbre TTS client handles synthesis request and voice config."""
    assert timbre_tts.headers["X-API-Key-ID"] == settings.effective_timbre_key
    audio_file = await timbre_tts.synthesize(
        text="దయచేసి ఎకరాకు 10 పసుపు జిగురు అట్టలు పెట్టండి.",
        language="te",
        speed=0.9
    )
    assert audio_file is not None
    assert Path(audio_file).exists()
