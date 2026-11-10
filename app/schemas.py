from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# WhatsApp Cloud API Webhook Schemas
# ============================================================================

class WhatsAppMediaItem(BaseModel):
    id: str
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    caption: Optional[str] = None


class WhatsAppTextItem(BaseModel):
    body: str


class WhatsAppMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    timestamp: str
    type: str
    image: Optional[WhatsAppMediaItem] = None
    audio: Optional[WhatsAppMediaItem] = None
    voice: Optional[WhatsAppMediaItem] = None
    text: Optional[WhatsAppTextItem] = None


class WhatsAppContactProfile(BaseModel):
    name: Optional[str] = None


class WhatsAppContact(BaseModel):
    wa_id: str
    profile: Optional[WhatsAppContactProfile] = None


class WhatsAppMetadata(BaseModel):
    display_phone_number: Optional[str] = None
    phone_number_id: Optional[str] = None


class WhatsAppChangeValue(BaseModel):
    messaging_product: Optional[str] = None
    metadata: Optional[WhatsAppMetadata] = None
    contacts: Optional[List[WhatsAppContact]] = None
    messages: Optional[List[WhatsAppMessage]] = None
    statuses: Optional[List[Dict[str, Any]]] = None


class WhatsAppChange(BaseModel):
    field: str
    value: WhatsAppChangeValue


class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    object: Optional[str] = None
    entry: List[WhatsAppEntry] = []


# ============================================================================
# Internal Domain & Case Schemas
# ============================================================================

class FarmerProfile(BaseModel):
    id: Optional[str] = None
    wa_phone: str
    language: str = "te"  # 'te' (Telugu), 'mr' (Marathi), 'pa' (Punjabi)
    state: Optional[str] = None
    district: Optional[str] = None


class VisionObservation(BaseModel):
    spots: Optional[str] = None
    colour: Optional[str] = None
    curling: Optional[str] = None
    insects_visible: Optional[str] = None
    pattern_on_leaf: Optional[str] = None
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    is_plant: bool = True
    is_clear: bool = True


class LikelyProblem(BaseModel):
    name: str
    local_name: Optional[str] = None
    confidence: float
    description: Optional[str] = None


class CaseSession(BaseModel):
    id: Optional[str] = None
    farmer_id: Optional[str] = None
    wa_phone: str
    wa_message_id: str
    crop: Optional[str] = None
    crop_age_days: Optional[int] = None
    photo_path: Optional[str] = None
    voice_path: Optional[str] = None
    transcript: Optional[str] = None
    vision_obs: Optional[VisionObservation] = None
    retrieved_chunk_ids: List[int] = Field(default_factory=list)
    likely_problems: List[LikelyProblem] = Field(default_factory=list)
    answer_text: Optional[str] = None
    answer_audio_path: Optional[str] = None
    confidence: Optional[float] = None
    escalated: bool = False
    escalation_reason: Optional[str] = None
    status: str = "received"
