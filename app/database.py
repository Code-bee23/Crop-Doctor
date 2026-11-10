import logging
from typing import Optional, Dict, Any, List
from app.config import get_settings

logger = logging.getLogger("crop_doctor.database")

# In-memory storage fallback for local student testing before Supabase credentials are configured
_in_memory_farmers: Dict[str, Dict[str, Any]] = {}
_in_memory_cases: Dict[str, Dict[str, Any]] = {}
_in_memory_banned_inputs: List[Dict[str, str]] = [
    {"name": "Endosulfan", "note": "Banned nationwide"},
    {"name": "Monocrotophos", "note": "Banned on vegetables"},
    {"name": "Paraquat dichloride", "note": "Restricted highly toxic herbicide"},
    {"name": "Phorate", "note": "Banned/severely restricted Class Ia organophosphate"},
    {"name": "Methyl Parathion", "note": "Banned in India"},
    {"name": "Phosphamidon", "note": "Banned in India"}
]


class DatabaseService:
    """
    Database Service abstracting Supabase & Postgres interactions.
    Gracefully falls back to local memory if Supabase URL/Key is not yet set up.
    """
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self._init_client()

    def _init_client(self):
        if self.settings.SUPABASE_URL and "your-project-id" not in self.settings.SUPABASE_URL and self.settings.SUPABASE_KEY:
            try:
                from supabase import create_client, Client
                self.client: Optional[Client] = create_client(
                    self.settings.SUPABASE_URL,
                    self.settings.SUPABASE_KEY
                )
                logger.info("Connected to Supabase client successfully.")
            except Exception as e:
                logger.warning(f"Could not initialize Supabase client: {e}. Running in local mock mode.")
                self.client = None
        else:
            logger.info("Supabase credentials not configured. Running database service in local memory mode.")

    async def get_or_create_farmer(self, wa_phone: str, language: str = "te") -> Dict[str, Any]:
        """
        Fetch existing farmer profile by WhatsApp phone number or create a new record.
        """
        if self.client:
            try:
                res = self.client.table("farmers").select("*").eq("wa_phone", wa_phone).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]
                # Create farmer
                new_farmer = {"wa_phone": wa_phone, "language": language}
                insert_res = self.client.table("farmers").insert(new_farmer).execute()
                return insert_res.data[0] if insert_res.data else new_farmer
            except Exception as e:
                logger.error(f"Supabase error in get_or_create_farmer: {e}")

        # Local fallback
        if wa_phone not in _in_memory_farmers:
            import uuid
            _in_memory_farmers[wa_phone] = {
                "id": str(uuid.uuid4()),
                "wa_phone": wa_phone,
                "language": language,
                "state": None,
                "district": None
            }
        return _in_memory_farmers[wa_phone]

    async def create_case(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new case record for an incoming farmer consultation.
        """
        if self.client:
            try:
                res = self.client.table("cases").insert(case_data).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error(f"Supabase error in create_case: {e}")

        import uuid
        case_id = str(uuid.uuid4())
        record = {"id": case_id, **case_data}
        _in_memory_cases[case_id] = record
        logger.info(f"Created case in local memory: ID={case_id}")
        return record

    async def update_case(self, case_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update case with transcription, vision observation, retrieved chunks, or answer.
        """
        if self.client:
            try:
                res = self.client.table("cases").update(updates).eq("id", case_id).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error(f"Supabase error in update_case: {e}")

        if case_id in _in_memory_cases:
            _in_memory_cases[case_id].update(updates)
            return _in_memory_cases[case_id]
        return None

    async def get_banned_inputs(self) -> List[str]:
        """
        Retrieve list of banned chemical names to guarantee they are never suggested.
        """
        if self.client:
            try:
                res = self.client.table("banned_inputs").select("name").execute()
                if res.data:
                    return [row["name"].strip().lower() for row in res.data]
            except Exception as e:
                logger.error(f"Supabase error in get_banned_inputs: {e}")

        return [item["name"].strip().lower() for item in _in_memory_banned_inputs]


# Global singleton instance
db = DatabaseService()

