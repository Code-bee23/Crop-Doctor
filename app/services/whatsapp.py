import logging
from pathlib import Path
from typing import Optional, Dict, Any
import httpx
from app.config import get_settings

logger = logging.getLogger("crop_doctor.whatsapp")


class WhatsAppService:
    """
    Client for Meta WhatsApp Business Cloud API.
    Handles media download (photos and voice notes) and outbound responses.
    """
    def __init__(self):
        self.settings = get_settings()
        self.api_version = self.settings.WHATSAPP_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        self.phone_number_id = self.settings.WHATSAPP_PHONE_NUMBER_ID
        self.access_token = self.settings.WHATSAPP_ACCESS_TOKEN

    @property
    def auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    async def get_media_url(self, media_id: str) -> Optional[str]:
        """
        Step 1 of WhatsApp media retrieval: Query Meta Graph API to obtain
        the direct CDN download URL for a given media_id.
        """
        if not self.access_token or self.access_token.startswith("mock"):
            logger.warning("WhatsApp access token is mocked or missing; returning mock media URL.")
            return f"https://mock.whatsapp.local/media/{media_id}"

        url = f"{self.base_url}/{media_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers={"Authorization": f"Bearer {self.access_token}"})
                response.raise_for_status()
                data = response.json()
                return data.get("url")
            except Exception as e:
                logger.error(f"Failed to fetch media metadata for ID {media_id}: {e}")
                return None

    async def download_media(self, media_id: str, media_type: str = "image", extension: Optional[str] = None) -> Optional[str]:
        """
        Step 2 of WhatsApp media retrieval: Download the binary file using the CDN URL
        with Bearer authentication, and save it to the local storage directory.
        """
        download_url = await self.get_media_url(media_id)
        if not download_url:
            return None

        # Determine target file path
        if not extension:
            extension = ".jpg" if media_type == "image" else ".ogg"
        if not extension.startswith("."):
            extension = f".{extension}"

        target_dir = self.settings.storage_path / ("images" if media_type == "image" else "audio")
        target_path = target_dir / f"{media_id}{extension}"

        # If mocked token, write a placeholder mock file for offline testing
        if not self.access_token or self.access_token.startswith("mock"):
            target_path.write_bytes(b"[MOCK_MEDIA_DATA]")
            logger.info(f"Mock media file saved at: {target_path}")
            return str(target_path)

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # Meta requires the Authorization header when requesting the media download URL as well
                response = await client.get(download_url, headers={"Authorization": f"Bearer {self.access_token}"})
                response.raise_for_status()
                target_path.write_bytes(response.content)
                logger.info(f"Downloaded WhatsApp {media_type} to: {target_path} ({len(response.content)} bytes)")
                return str(target_path)
            except Exception as e:
                logger.error(f"Failed to download media binary from {download_url}: {e}")
                return None

    async def send_text_message(self, to_phone: str, message_text: str) -> bool:
        """
        Send a WhatsApp text message reply to a farmer.
        """
        if not self.access_token or self.access_token.startswith("mock"):
            logger.info(f"[MOCK WHATSAPP OUTBOUND TEXT to {to_phone}]: {message_text}")
            return True

        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self.auth_headers)
                response.raise_for_status()
                logger.info(f"Successfully sent text message to {to_phone}")
                return True
            except Exception as e:
                logger.error(f"Failed to send text message to {to_phone}: {e}")
                return False

    async def send_audio_message(self, to_phone: str, audio_url: str) -> bool:
        """
        Send a WhatsApp voice/audio message reply to a farmer.
        """
        if not self.access_token or self.access_token.startswith("mock"):
            logger.info(f"[MOCK WHATSAPP OUTBOUND AUDIO to {to_phone}]: URL={audio_url}")
            return True

        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "audio",
            "audio": {
                "link": audio_url
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self.auth_headers)
                response.raise_for_status()
                logger.info(f"Successfully sent audio message to {to_phone}")
                return True
            except Exception as e:
                logger.error(f"Failed to send audio message to {to_phone}: {e}")
                return False


whatsapp_service = WhatsAppService()

