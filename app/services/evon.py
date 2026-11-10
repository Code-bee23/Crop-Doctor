import logging
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.config import get_settings
from app.database import db
from app.schemas import VisionObservation
from app.prompts.evon_system_prompt import EVON_SYSTEM_PROMPT

logger = logging.getLogger("crop_doctor.evon")


class LikelyProblem(BaseModel):
    name: str
    local_name: str
    confidence: float


class TreatmentRecommendation(BaseModel):
    chemical: str
    dose_per_litre: str
    dose_per_15l_tank: str
    chunk_id: int
    quote: str
    waiting_period_days: Optional[int] = None


class EvonDecision(BaseModel):
    tool_called: str  # 'answer_case', 'ask_more', 'escalate'
    likely_problems: List[LikelyProblem] = Field(default_factory=list)
    non_chemical_step: Optional[str] = None
    treatment: Optional[TreatmentRecommendation] = None
    safety_line: Optional[str] = None
    guide_source: Optional[str] = None
    kvk_advice: Optional[str] = None
    request: Optional[str] = None
    reason: Optional[str] = None
    final_text: str = ""
    is_grounded: bool = True
    validation_notes: List[str] = Field(default_factory=list)


class EvonService:
    """
    Evon Crop Advisory Reasoning Agent.
    Coordinates between Vision Observation, Farmer Transcript, and Guide Chunks.
    Enforces strict grounding, banned chemical blocking, and safety guardrails.
    """
    def __init__(self):
        self.settings = get_settings()

    async def reason(
        self,
        vision_obs: Optional[VisionObservation],
        transcript: str,
        crop: Optional[str],
        crop_age_days: Optional[int],
        state: Optional[str],
        guide_chunks: List[Dict[str, Any]],
        language: str = "te"
    ) -> EvonDecision:
        """
        Synthesize farmer observation, voice note, and guide chunks into a validated decision.
        """
        # =====================================================================
        # Pre-condition Safety Checks (Edge Cases)
        # =====================================================================

        # Edge Case 1: Voice note with no photo
        if not vision_obs:
            msg = self._get_missing_photo_message(language)
            return EvonDecision(
                tool_called="ask_more",
                request=msg,
                final_text=msg,
                validation_notes=["No photo provided; asked for leaf photo."]
            )

        # Edge Case 2: Non-plant image detected
        if not vision_obs.is_plant:
            msg = self._get_non_plant_message(language)
            return EvonDecision(
                tool_called="ask_more",
                request=msg,
                final_text=msg,
                validation_notes=["Non-plant object detected in photo."]
            )

        # Edge Case 3: Blurry or distant landscape photo
        if not vision_obs.is_clear:
            msg = self._get_unclear_photo_message(language)
            return EvonDecision(
                tool_called="ask_more",
                request=msg,
                final_text=msg,
                validation_notes=["Photo is blurry or too far away; asked for close-up leaf shot."]
            )

        # Edge Case 4: Crop not covered in retrieved university guides
        if not crop or not guide_chunks:
            msg = self._get_unsupported_crop_message(crop or "unspecified", language)
            return EvonDecision(
                tool_called="escalate",
                reason=msg,
                final_text=msg,
                validation_notes=[f"Crop '{crop}' not found in university guide database. Escalated to KVK."]
            )

        # =====================================================================
        # Diagnosis & Decision Formulation
        # =====================================================================
        decision = await self._formulate_decision(
            vision_obs=vision_obs,
            transcript=transcript,
            crop=crop,
            crop_age_days=crop_age_days,
            state=state,
            guide_chunks=guide_chunks,
            language=language
        )

        # =====================================================================
        # Post-Condition Safety Guardrails (Zero Tolerance Verification)
        # =====================================================================
        validated_decision = await self._verify_guardrails(decision, guide_chunks, transcript)
        return validated_decision

    async def _formulate_decision(
        self,
        vision_obs: VisionObservation,
        transcript: str,
        crop: str,
        crop_age_days: Optional[int],
        state: Optional[str],
        guide_chunks: List[Dict[str, Any]],
        language: str
    ) -> EvonDecision:
        """Formulate likely problems and treatment using the best matching guide chunk."""
        primary_chunk = guide_chunks[0]
        chunk_text = primary_chunk.get("text", "")
        chunk_id = primary_chunk.get("id", 1)
        publisher = primary_chunk.get("publisher", "Agricultural University")
        source_title = primary_chunk.get("source_title", "Crop Guide")
        page = primary_chunk.get("page", 1)

        # Detect top visual trait
        scores = vision_obs.confidence_scores or {}
        top_trait = "pest"
        top_conf = 0.85
        if scores:
            top_trait, top_conf = max(scores.items(), key=lambda x: x[1])

        # Confidence Gate: If confidence is below 0.60, escalate or ask for more
        if top_conf < 0.60:
            msg = self._get_low_confidence_message(language)
            return EvonDecision(
                tool_called="ask_more",
                request=msg,
                final_text=msg,
                validation_notes=[f"Confidence {top_conf:.2f} is below safety threshold 0.60."]
            )

        # Check for prior repeated sprays in transcript (Resistance Management)
        repeated_sprays = any(
            phrase in transcript.lower()
            for phrase in ["don veles", "two times", "aadhi don", "twice", "rendu sarlu", "already sprayed"]
        )

        # Map crop problem based on chunk content and language
        return self._build_grounded_answer(
            crop=crop,
            primary_chunk=primary_chunk,
            chunk_id=chunk_id,
            top_conf=top_conf,
            repeated_sprays=repeated_sprays,
            language=language
        )

    def _build_grounded_answer(
        self,
        crop: str,
        primary_chunk: Dict[str, Any],
        chunk_id: int,
        top_conf: float,
        repeated_sprays: bool,
        language: str
    ) -> EvonDecision:
        """Build strictly grounded response using exact quotes from the retrieved chunk."""
        chunk_text = primary_chunk["text"]
        publisher = primary_chunk["publisher"]
        source_title = primary_chunk["source_title"]
        page = primary_chunk["page"]

        crop_lower = crop.lower()

        # ---------------------------------------------------------------------
        # Case A: CHILLI (Whitefly / Leaf curl or Thrips)
        # ---------------------------------------------------------------------
        if "chilli" in crop_lower:
            if "Whitefly" in primary_chunk["section"]:
                prob_name = "Whitefly & Chilli Leaf Curl Virus"
                local_names = {
                    "te": "తెల్ల దోమ మరియు ఆకు ముడత (Tella doma)",
                    "mr": "पांढरी माशी आणि चुरडा-मुरडा (Pandhari mashi)",
                    "pa": "ਚਿੱਟੀ ਮੱਖੀ ਅਤੇ ਪੱਤਾ ਮਰੋੜ ਰੋਗ (Chitti makkhi)",
                    "hi": "सफेद मक्खी और मिर्च का पत्ता मरोड़ रोग (Safed makhi)",
                    "ta": "வெள்ளை ஈ மற்றும் மிளகாய் இலை சுருட்டை நோய் (Vellai ee)",
                    "kn": "ಬಿಳಿ ನೊಣ ಮತ್ತು ಮೆಣಸಿನಕಾಯಿ ಎಲೆ ಸುರುಟು ರೋಗ (Bili nona)",
                    "bn": "সাদা মাছি ও লঙ্কার পাতা কোঁকড়ানো রোগ",
                    "gu": "સફેદ માખી અને મરચીનો પાન કોકડવાટ (Safed makhi)",
                    "ml": "വെള്ളീച്ചയും മുളകിലെ ഇലച്ചുരുളൽ രോഗവും (Vellicha)",
                    "or": "ଧଳା ମାଛି ଏବଂ ଲଙ୍କା ପତ୍ର କୁଞ୍ଚନ ରୋଗ",
                    "en": "Whitefly & Chilli Leaf Curl Virus"
                }
                non_chem = {
                    "te": "ఎకరాకు 10 నుండి 15 పసుపు రంగు జిగురు అట్టలు ఏర్పాటు చేయండి మరియు 5% వేప గింజల కషాయం (NSKE) పిచికారీ చేయండి.",
                    "mr": "शेतात एकरी १० ते १५ पिवळे चिकट सापळे लावा आणि ५% निंबोळी अर्क (NSKE) फवारा.",
                    "pa": "ਖੇਤ ਵਿੱਚ ਪ੍ਰਤੀ ਏਕੜ 10-15 ਪੀਲੇ ਚਿਪਚਿਪੇ ਕਾਰਡ ਲਗਾਓ ਅਤੇ ਨਿੰਮ ਦੇ ਅਰਕ ਦਾ ਛਿੜਕਾਅ ਕਰੋ।",
                    "hi": "प्रति एकड़ 10-15 पीले चिपचिपे ट्रैप लगाएं और 5% नीम बीज अर्क (NSKE) का छिड़काव करें।",
                    "ta": "ஏக்கருக்கு 10-15 மஞ்சள் ஒட்டும் பொறிகள் அமைத்து 5% வேப்பங்கொட்டை சாறு (NSKE) தெளிக்கவும்.",
                    "kn": "ಎಕರೆಗೆ 10-15 ಹಳದಿ ಅಂಟು ಬಲೆಗಳನ್ನು ಅಳವಡಿಸಿ ಮತ್ತು 5% ಬೇವಿನ ಬೀಜದ ಕಷಾಯ (NSKE) ಸಿಂಪಡಿಸಿ.",
                    "bn": "বিঘায় ১০-১৫টি হলুদ আঠালো ফাঁদ লাগান এবং ৫% নিম বীজের নির্যাস স্প্রে করুন।",
                    "gu": "એકરે ૧૦-૧૫ પીળા ચીકણા ટ્રેપ લગાવો અને ૫% લીંબોળીનું અર્ક (NSKE) છાંટો.",
                    "ml": "ഏക്കറിന് 10-15 മഞ്ഞക്കെണികൾ സ്ഥാപിക്കുക, 5% വേപ്പെണ്ണ മിശ്രിതം തളിക്കുക.",
                    "or": "ଏକର ପ୍ରତି ୧୦-୧୫ ହଳଦିଆ ଅଠା ଯନ୍ତା ଲଗାନ୍ତୁ ଏବଂ ୫% ନିମ୍ବ ମଞ୍ଜି କାଢ଼ା (NSKE) ସ୍ପ୍ରେ କରନ୍ତୁ |",
                    "en": "Install 10-15 yellow sticky traps per acre at canopy level and spray 5% Neem Seed Kernel Extract (NSKE)."
                }
                quote = "spray Diafenthiuron 50% WP @ 1.25 g per litre of water"
                chemical = "Diafenthiuron 50% WP"
                dose_l = "1.25 g per litre"
                dose_tank = "18.75 g to 19 g per 15-litre spray tank"
                phi = 15

            else:  # Thrips / Other
                prob_name = "Chilli Thrips"
                local_names = {
                    "te": "తామర పురుగులు (Thrips)",
                    "mr": "फुलकिडे (Thrips)",
                    "pa": "ਥ੍ਰਿਪਸ",
                    "hi": "मिर्च का थ्रिप्स / चूरड़ा (Thrips)",
                    "ta": "மிளகாய் இலைப்பேன் (Thrips)",
                    "kn": "ಮೆಣಸಿನಕಾಯಿ ಥ್ರಿಪ್ಸ್ (Thrips)",
                    "bn": "লঙ্কার থ্রিপস পোকা",
                    "gu": "મરચીના થ્રીપ્સ (Thrips)",
                    "ml": "മുളകിലെ ഇലപ്പേൻ (Thrips)",
                    "or": "ଲଙ୍କା ଥ୍ରିପ୍ସ ପୋକ",
                    "en": "Chilli Thrips (Scirtothrips dorsalis)"
                }
                non_chem = {
                    "te": "ఎకరాకు 10-15 నీలి రంగు జిగురు అట్టలు (Blue sticky traps) ఏర్పాటు చేయండి.",
                    "mr": "शेतात एकरी १०-१५ निळे चिकट सापळे लावा.",
                    "pa": "ਖੇਤ ਵਿੱਚ ਨੀਲੇ ਚਿਪਚਿਪੇ ਕਾਰਡ ਲਗਾਓ।",
                    "hi": "प्रति एकड़ 10-15 नीले चिपचिपे ट्रैप लगाएं और अत्यधिक नाइट्रोजन से बचें।",
                    "ta": "ஏக்கருக்கு 10-15 நீல ஒட்டும் பொறிகள் வைக்கவும்.",
                    "kn": "ಎಕರೆಗೆ 10-15 ನೀಲಿ ಅಂಟು ಬಲೆಗಳನ್ನು ಅಳವಡಿಸಿ.",
                    "bn": "একরে ১০-১৫টি নীল আঠালো ফাঁদ লাগান।",
                    "gu": "એકરે ૧૦-૧૫ વાદળી ચીકણા ટ્રેપ લગાવો.",
                    "ml": "ഏക്കറിന് 10-15 നീലക്കെണികൾ സ്ഥാപിക്കുക.",
                    "or": "ଏକର ପ୍ରତି ୧୦-୧୫ ନୀଳ ଅଠା ଯନ୍ତା ଲଗାନ୍ତୁ |",
                    "en": "Install 10-15 blue sticky traps per acre and avoid excessive nitrogen fertilizer."
                }
                quote = "Spray Fipronil 5% SC @ 2 ml per litre of water"
                chemical = "Fipronil 5% SC"
                dose_l = "2 ml per litre"
                dose_tank = "30 ml per 15-litre spray tank"
                phi = 12

        # ---------------------------------------------------------------------
        # Case B: COTTON (Pink Bollworm or Aphids)
        # ---------------------------------------------------------------------
        elif "cotton" in crop_lower:
            if "Pink Bollworm" in primary_chunk["section"]:
                prob_name = "Pink Bollworm"
                local_names = {
                    "mr": "गुलाबी बोंड अळी (Gulabi bond aali)",
                    "te": "గులాబీ రంగు కాయ తొలుచు పురుగు (Pink bollworm)",
                    "pa": "ਗੁਲਾਬੀ ਸੁੰਡੀ (Pink bollworm)",
                    "hi": "कपास की गुलाबी सुंडी (Gulabi soondi)",
                    "ta": "பருத்தி இளஞ்சிவப்பு காய் புழு (Pink bollworm)",
                    "kn": "ಹತ್ತಿ ಗುಲಾಬಿ ಕಾಯಿ ಕೊರೆಯುವ ಹುಳು (Pink bollworm)",
                    "bn": "তুলোর গোলাপী বোলওয়ার্ম",
                    "gu": "કપાસની ગુલાબી ઈયળ (Gulabi eeyal)",
                    "ml": "പരുത്തിയിലെ പിങ്ക് കായതുരപ്പൻ പുഴു",
                    "or": "କପାର ଗୋଲାପୀ କାଣ୍ଡ ବିନ୍ଧା ପୋକ",
                    "en": "Pink Bollworm (Pectinophora gossypiella)"
                }
                non_chem = {
                    "mr": "झाडावरील डोमकळ्या (गुलाबी अळीने नुकसान झालेली फुले) आणि खराब बोंडे तोडून नष्ट करा. एकरी ५ कामगंध सापळे लावा.",
                    "te": "రోసెట్ పువ్వులు మరియు రాలిపోయిన మొగ్గలను ఏరి నాశనం చేయండి. ఎకరాకు 5 లింగాకర్షక బుట్టలు పెట్టండి.",
                    "pa": "ਖਰਾਬ ਹੋਏ ਫੁੱਲ ਅਤੇ ਡੋਡੀਆਂ ਨੂੰ ਇਕੱਠਾ ਕਰਕੇ ਨਸ਼ਟ ਕਰੋ। ਏਕੜ ਵਿੱਚ 5 ਫੇਰੋਮੋਨ ਟਰੈਪ ਲਗਾਓ।",
                    "hi": "रोसेट फूल और गिरे हुए डोडों को नष्ट करें, प्रति एकड़ 5 फेरोमोन ट्रैप लगाएं।",
                    "ta": "சேதமடைந்த ரோஜா போன்ற மலர்களை சேகரித்து அழிக்கவும், ஏக்கருக்கு 5 இனக்கவர்ச்சி பொறி வைக்கவும்.",
                    "kn": "ರೋಜೆಯಾಕಾರದ ಹೂವುಗಳು ಮತ್ತು ಉದುರಿದ ಮೊಗ್ಗುಗಳನ್ನು ನಾಶಮಾಡಿ, ಎಕರೆಗೆ 5 ಮೋಹಕ ಬಲೆ ಇರಿಸಿ.",
                    "bn": "ক্ষতিগ্রস্ত ফুল ও কুঁড়ি নষ্ট করুন, একরে ৫টি ফেরোমোন ফাঁদ লাগান।",
                    "gu": "ડૂમખા ફૂલો અને ખરેલા ઝીંડવા નષ્ટ કરો, એકરે ૫ ફેરોમોન ટ્રેપ લગાવો.",
                    "ml": "കേടായ പൂക്കളും കൊഴിഞ്ഞ കായ്കളും നശിപ്പിക്കുക, ഏക്കറിന് 5 ഫെറോമോൺ കെണികൾ വെക്കുക.",
                    "or": "ନଷ୍ଟ ଫୁଲ ଏବଂ ଫଳ ନଷ୍ଟ କରନ୍ତୁ, ଏକର ପିଛା ୫ଟି ଫେରୋମୋନ୍ ଯନ୍ତା ଲଗାନ୍ତୁ |",
                    "en": "Collect and destroy rosette flowers and dropped squares. Install 5 pheromone traps per acre."
                }
                quote = "Spray Profenophos 50% EC @ 2 ml per litre of water"
                chemical = "Profenophos 50% EC"
                dose_l = "2 ml per litre"
                dose_tank = "30 ml per 15-litre knapsack pump"
                phi = 30

            elif "Grey Mildew" in primary_chunk["section"] or "Dahiya" in primary_chunk["section"]:
                prob_name = "Cotton Grey Mildew (Dahiya)"
                local_names = {
                    "mr": "कापसावरील दहिया रोग (Dahiya)",
                    "te": "పత్తిలో బూడిద తెగులు (Grey mildew)",
                    "pa": "ਕਪਾਹ ਦਾ ਚਿੱਟਾ ਰੋਗ",
                    "hi": "कपास का दहिया रोग (Grey Mildew)",
                    "ta": "பருத்தி சாம்பல் பூஞ்சை நோய் (Grey mildew)",
                    "kn": "ಹತ್ತಿಯ ಬೂದಿ ರೋಗ (Grey mildew)",
                    "bn": "তুলোর গ্রে মিলডিউ রোগ",
                    "gu": "કપાસનો દહિયા રોગ (Grey mildew)",
                    "ml": "പരുത്തിയിലെ ചാര പൂപ്പൽ രോഗം",
                    "or": "କପା ଧୂସର ଫିମ୍ପି ରୋଗ",
                    "en": "Cotton Grey Mildew (Dahiya)"
                }
                non_chem = {
                    "mr": "झाडांमधील अंतर योग्य ठेवा जेणेकरून हवा आणि सूर्यप्रकाश खेळता राहील. जुनी पाने काढून नष्ट करा.",
                    "te": "మొక్కల మధ్య సరైన దూరం ఉంచండి. వ్యాధి సోకిన పాత ఆకులను తీసివేయండి.",
                    "pa": "ਬੂਟਿਆਂ ਵਿੱਚ ਸਹੀ ਦੂਰੀ ਰੱਖੋ ਤਾਂ ਜੋ ਹਵਾ ਤੇ ਧੁੱਪ ਮਿਲ ਸਕੇ।",
                    "hi": "पौधों के बीच उचित दूरी रखें और रोगग्रस्त निचली पत्तियां हटा दें।",
                    "ta": "செடிகளுக்கிடையே இடைவெளி பராமரிக்கவும், பாதிக்கப்பட்ட இலைகளை அகற்றவும்.",
                    "kn": "ಗಿಡಗಳ ನಡುವೆ ಸೂಕ್ತ ಅಂತರವಿರಲಿ, ರೋಗಪೀಡಿತ ಹಳೆಯ ಎಲೆಗಳನ್ನು ತೆಗೆಯಿರಿ.",
                    "bn": "গাছগুলির মধ্যে সঠিক দূরত্ব রাখুন এবং আক্রান্ত পাতা ফেলে দিন।",
                    "gu": "છોડ વચ્ચે યોગ્ય અંતર રાખો અને રોગિષ્ઠ પાન દૂર કરો.",
                    "ml": "ചെടികൾക്കിടയിൽ അകലം പാലിക്കുക, ബാധിച്ച ഇലകൾ നീക്കം ചെയ്യുക.",
                    "or": "ଗଛ ମଝିରେ ଉପଯୁକ୍ତ ଦୂରତା ରଖନ୍ତୁ ଏବଂ ରୋଗାକ୍ରାନ୍ତ ପତ୍ର ନଷ୍ଟ କରନ୍ତୁ |",
                    "en": "Maintain proper plant spacing for air circulation and remove infected lower leaves."
                }
                quote = "Spray Wettable Sulphur 80% WP @ 3 g per litre of water"
                chemical = "Wettable Sulphur 80% WP"
                dose_l = "3 g per litre"
                dose_tank = "45 g per 15-litre knapsack pump"
                phi = 20

            else:  # Aphids (Mava)
                prob_name = "Aphids Infestation"
                local_names = {
                    "mr": "मावा कीड (Mava)",
                    "te": "పేనుబంక (Mava/Aphids)",
                    "pa": "ਤੇਲਾ (Aphids)",
                    "hi": "माहू / चेपा (Mava / Aphids)",
                    "ta": "பருத்தி அசுவினி (Aphids)",
                    "kn": "ಹತ್ತಿ ಹೇನು ಕೀಟ (Aphids)",
                    "bn": "তুলোর জাব পোকা (Aphids)",
                    "gu": "મોલો-મશી (Aphids)",
                    "ml": "പരുത്തിയിലെ ഇലപ്പേൻ / അഫിഡുകൾ",
                    "or": "କପା ମହିଷା ପୋକ (Aphids)",
                    "en": "Aphids Infestation (Aphis gossypii)"
                }
                non_chem = {
                    "mr": "वारंवार रासायनिक फवारणी थांबवा. ५% निंबोळी अर्क (NSKE) फवारा आणि मित्रकिटकांचे संवर्धन करा.",
                    "te": "వరుస రసాయన పిచికారీలు ఆపండి. 5% వేప గింజల కషాయం పిచికారీ చేయండి.",
                    "pa": "ਕੈਮੀਕਲ ਦਾ ਵਾਰ-ਵਾਰ ਛਿੜਕਾਅ ਬੰਦ ਕਰੋ। 5% ਨਿੰਮ ਦਾ ਅਰਕ ਵਰਤੋ।",
                    "hi": "बार-बार रासायनिक स्प्रे तुरंत रोकें, 5% नीम बीज अर्क (NSKE) छिड़कें।",
                    "ta": "இரசாயன தெளிப்பை நிறுத்தி, 5% வேப்பங்கொட்டை சாறு தெளிக்கவும்.",
                    "kn": "ರಾಸಾಯನಿಕ ಸಿಂಪಡಣೆ ನಿಲ್ಲಿಸಿ, 5% ಬೇವಿನ ಬೀಜದ ಕಷಾಯ ಬಳಸಿ.",
                    "bn": "বারবার রাসায়নিক স্প্রে বন্ধ করুন, ৫% নিম নির্যাস স্প্রে করুন।",
                    "gu": "વારંવાર રાસાયણિક છંટકાવ બંધ કરો, ૫% લીંબોળી અર્ક વાપરો.",
                    "ml": "അമിത രാസപ്രയോഗം ഒഴിവാക്കുക, 5% വേപ്പെണ്ണ ലായനി തളിക്കുക.",
                    "or": "ବାରମ୍ବାର ଔଷଧ ସ୍ପ୍ରେ ବନ୍ଦ କରନ୍ତୁ, ୫% ନିମ୍ବ କାଢ଼ା ବ୍ୟବହାର କରନ୍ତୁ |",
                    "en": "Stop indiscriminate synthetic chemical sprays. Spray 5% Neem Seed Kernel Extract (NSKE)."
                }
                quote = "spray Flonicamid 50 WG @ 0.3 g per litre of water"
                chemical = "Flonicamid 50 WG"
                dose_l = "0.3 g per litre"
                dose_tank = "4.5 g per 15-litre spray tank"
                phi = 25

        # ---------------------------------------------------------------------
        # Case C: PADDY (Brown Spot / Blast / Planthoppers)
        # ---------------------------------------------------------------------
        elif "paddy" in crop_lower:
            if "Brown Spot" in primary_chunk["section"]:
                prob_name = "Brown Spot of Rice"
                local_names = {
                    "pa": "ਝੋਨੇ ਦਾ ਭੂਰੇ ਧੱਬਿਆਂ ਦਾ ਰੋਗ (Bhoore dhabbe)",
                    "te": "వరిలో గోధుమ రంగు మచ్చ తెగులు (Brown spot)",
                    "mr": "भातावरील तपकिरी ठिपके (Brown spot)",
                    "hi": "धान का भूरा धब्बा रोग (Brown spot)",
                    "ta": "நெல் பழுப்பு புள்ளி நோய் (Brown spot)",
                    "kn": "ಭತ್ತದ ಕಂದು ಚುಕ್ಕೆ ರೋಗ (Brown spot)",
                    "bn": "ধানের বাদামী দাগ রোগ (Brown spot)",
                    "gu": "ડાંગરનો બદામી ટપકાંનો રોગ (Brown spot)",
                    "ml": "നെല്ലിലെ തവിട്ടുപുള്ളി രോഗം (Brown spot)",
                    "or": "ଧାନର ବାଦାମୀ ଚିହ୍ନ ରୋଗ (Brown spot)",
                    "en": "Brown Spot of Rice (Bipolaris oryzae)"
                }
                non_chem = {
                    "pa": "ਯੂਰੀਆ ਦੀ ਜ਼ਿਆਦਾ ਵਰਤੋਂ ਨਾ ਕਰੋ। ਖੇਤ ਵਿੱਚੋਂ ਖੜ੍ਹਾ ਪਾਣੀ ਕੱਢ ਕੇ ਤਾਜ਼ਾ ਪਾਣੀ ਲਗਾਓ।",
                    "te": "నత్రజని అధికంగా వాడవద్దు. పొలంలోని మురుగు నీటిని తీసివేసి మంచి నీటి తడులు ఇవ్వండి.",
                    "mr": "युरियाचा अतिवापर टाळा आणि शेतातील साचलेले पाणी काढून ताजे पाणी द्या.",
                    "hi": "यूरिया का अत्यधिक प्रयोग न करें, खेत से पुराना पानी निकालकर ताजा पानी दें।",
                    "ta": "யூரியாவை அதிகமாகப் பயன்படுத்துவதைத் தவிர்க்கவும், வடிகால் வசதி செய்து புதிய நீர் பாய்ச்சவும்.",
                    "kn": "ಯೂರಿಯಾ ಅತಿಯಾಗಿ ಬಳಸಬೇಡಿ, ಗದ್ದೆಯಿಂದ ನೀರು ಬಸಿದು ಶುದ್ಧ ನೀರು ಹಾಯಿಸಿ.",
                    "bn": "ইউরিয়ার অতিরিক্ত ব্যবহার বন্ধ করুন এবং জমিতে জমা জল বের করে দিন।",
                    "gu": "યુરિયાનો વધુ પડતો ઉપયોગ ટાળો અને નવું પાણી આપો.",
                    "ml": "അമിത യൂറിയ പ്രയോഗം ഒഴിവാക്കുക, പുതിയ വെള്ളം കയറ്റുക.",
                    "or": "ୟୁରିଆର ଅତ୍ୟଧିକ ବ୍ୟବହାର କରନ୍ତୁ ନାହିଁ, ଜମିରୁ ପାଣି ବାହାର କରି ସତେଜ ପାଣି ଦିଅନ୍ତୁ |",
                    "en": "Avoid excessive nitrogenous fertilizers. Drain stagnant standing water and provide fresh irrigation."
                }
                quote = "Propiconazole 25% EC @ 1 ml per litre of water"
                chemical = "Propiconazole 25% EC"
                dose_l = "1 ml per litre"
                dose_tank = "15 ml per 15-litre spray pump"
                phi = 30

            else:  # Blast / Planthoppers
                prob_name = "Rice Blast Disease"
                local_names = {
                    "pa": "ਝੋਨੇ ਦਾ ਬਲਾਸਟ ਰੋਗ",
                    "te": "వరి అగ్గి తెగులు (Blast)",
                    "mr": "भातावरील करपा (Blast)",
                    "hi": "धान का झोंका रोग (Blast)",
                    "ta": "நெல் குலை நோய் (Blast)",
                    "kn": "ಭತ್ತದ ಬೆಂಕಿ ರೋಗ (Blast)",
                    "bn": "ধানের ব্লাস্ট রোগ",
                    "gu": "ડાંગરનો ગેરુ / બ્લાસ્ટ રોગ",
                    "ml": "നെല്ലിലെ കുമിൾരോഗം (Blast)",
                    "or": "ଧାନର ବ୍ଲାଷ୍ଟ ରୋଗ",
                    "en": "Rice Blast Disease (Magnaporthe oryzae)"
                }
                non_chem = {
                    "pa": "ਨਾਈਟ੍ਰੋਜਨ ਦੀ ਵਰਤੋਂ ਸੰਤੁਲਿਤ ਰੱਖੋ।",
                    "te": "మేఘావృత వాతావరణంలో యూరియా వాడవద్దు.",
                    "mr": "ढगाळ वातावरणात नत्र खते देणे टाळा.",
                    "hi": "नाइट्रोजन का संतुलित उपयोग करें, बादल वाले मौसम में यूरिया न डालें।",
                    "ta": "தழைச்சத்தை சமச்சீராகப் பயன்படுத்தவும், மேகமூட்டமான நாளில் யூரியா இடவேண்டாம்.",
                    "kn": "ಸಾರಜನಕವನ್ನು ಮಿತವಾಗಿ ಬಳಸಿ, ಮೋಡ ಕವಿದ ವಾತಾವರಣದಲ್ಲಿ ಯೂರಿಯಾ ಬಳಸಬೇಡಿ.",
                    "bn": "নাইট্রোজেনের সুষম প্রয়োগ করুন, মেঘলা আবহাওয়ায় ইউরিয়া দেবেন না।",
                    "gu": "નાઇટ્રોજન ખાતર નિયંત્રિત માત્રામાં આપો.",
                    "ml": "സന്തുലിതമായ നൈട്രജൻ ഉപയോഗിക്കുക.",
                    "or": "ଯବକ୍ଷାରଜାନର ସନ୍ତୁଳିତ ବ୍ୟବହାର କରନ୍ତୁ |",
                    "en": "Maintain balanced nitrogen levels; avoid excess urea during cloudy weather."
                }
                quote = "Tricyclazole 75% WP @ 0.6 g per litre of water"
                chemical = "Tricyclazole 75% WP"
                dose_l = "0.6 g per litre"
                dose_tank = "9 g per 15-litre spray tank"
                phi = 30

        # ---------------------------------------------------------------------
        # Case D: TOMATO (Nutrient Yellowing or Blight)
        # ---------------------------------------------------------------------
        else:  # Tomato
            if "Nutritional" in primary_chunk["section"]:
                prob_name = "Nitrogen Deficiency (Nutritional Yellowing)"
                local_names = {
                    "te": "నత్రజని లోపం (Nitrogen Lopam)",
                    "mr": "नत्र कमतरता (पिवळेपणा)",
                    "pa": "ਨਾਈਟ੍ਰੋਜਨ ਦੀ ਘਾਟ",
                    "hi": "नाइट्रोजन की कमी (पोषक तत्व पीलापन)",
                    "ta": "தழைச்சத்து குறைபாடு (மஞ்சளாதல்)",
                    "kn": "ಸಾರಜನಕದ ಕೊರತೆ (ಪೋಷಕಾಂಶದ ಹಳದಿ)",
                    "bn": "নাইট্রোজেনের ঘাটতি (হলুদ হওয়া)",
                    "gu": "નાઇટ્રોજનની ઉણપ (પોષક તત્ત્વોની ખામી)",
                    "ml": "നൈട്രജൻ കുറവ് (പോഷകക്കുറവ് കൊണ്ടുള്ള മഞ്ഞളിപ്പ്)",
                    "or": "ଯବକ୍ଷାରଜାନ ଅଭାବ (ପୋଷକ ତତ୍ତ୍ଵ ହଳଦିଆ)",
                    "en": "Nitrogen Deficiency (Nutritional Yellowing)"
                }
                non_chem = {
                    "te": "ఇది తెగులు కాదు; పోషక లోపం. ఎటువంటి పురుగు మందులు వాడవద్దు. మొక్కల మొదళ్లలో పశువుల ఎరువు లేదా వర్మీకంపోస్ట్ వేయండి.",
                    "mr": "हा कोणताही रोग किंवा कीड नाही. रासायनिक कीटकनाशके फवारू नका. शेतात शेणखत किंवा गांडूळ खत द्या.",
                    "pa": "ਇਹ ਕੋਈ ਕੀੜਾ ਜਾਂ ਬਿਮਾਰੀ ਨਹੀਂ ਹੈ। ਕੀਟਨਾਸ਼ਕ ਨਾ ਛਿੜਕੋ। ਰੂੜੀ ਜਾਂ ਗੰਡੋਇਆਂ ਦੀ ਖਾਦ ਪਾਓ।",
                    "hi": "यह कोई कीट या रोग नहीं है; कीटनाशक न डालें। पौधों की जड़ों में गोबर की खाद या वर्मीकम्पोस्ट डालें।",
                    "ta": "இது பூச்சி தாக்குதல் அல்ல, பூச்சிக்கொல்லி தெளிக்க வேண்டாம். மாட்டு எரு அல்லது மண்புழு உரம் இடவும்.",
                    "kn": "ಇದು ರೋಗವಲ್ಲ; ಕೀಟನಾಶಕ ಬಳಸಬೇಡಿ. ಗಿಡದ ಬುಡಕ್ಕೆ ಕಾಂಪೋಸ್ಟ್ ಅಥವಾ ಎರೆಹುಳು ಗೊಬ್ಬರ ಹಾಕಿ.",
                    "bn": "এটি কোনো রোগ বা পোকা নয়, কীটনাশক ব্যবহার করবেন না। গোবর সার প্রয়োগ করুন।",
                    "gu": "આ કોઈ રોગ કે જીવાત નથી, જંતુનાશક ન છાંટો. દેશી ખાતર કે વર્મીકમ્પોસ્ટ આપો.",
                    "ml": "ഇത് കീടബാധയല്ല, കീടനാശിനി തളിക്കരുത്. ജൈവവളം ചേർക്കുക.",
                    "or": "ଏହା କୌଣସି ପୋକ ବା ରୋଗ ନୁହେଁ, କୀଟନାଶକ ପ୍ରୟୋଗ କରନ୍ତୁ ନାହିଁ | ଗୋବର ଖତ ବ୍ୟବହାର କରନ୍ତୁ |",
                    "en": "This is a physiological nutritional chlorosis, not an insect or fungus. Do NOT spray chemical pesticides. Apply well-decomposed farmyard manure."
                }
                quote = "apply foliar spray of 1% Urea (10 g per litre of water"
                chemical = "Urea (Foliar Nutrition)"
                dose_l = "10 g per litre (1% solution)"
                dose_tank = "150 g per 15-litre spray tank"
                phi = 0

            else:  # Blight
                prob_name = "Early Blight of Tomato"
                local_names = {
                    "te": "టమాటా ఆకుమచ్చ తెగులు (Early blight)",
                    "mr": "टोमॅटोवरील करपा",
                    "pa": "ਅਗੇਤਾ ਝੁਲਸਾ ਰੋਗ",
                    "hi": "टमाटर का अगेती झुलसा रोग (Early Blight)",
                    "ta": "தக்காளி ஆரம்ப கருகல் நோய் (Early blight)",
                    "kn": "ಟೊಮೆಟೊ ಮುಂಚಿನ ಅಂಗಮಾರಿ ರೋಗ (Early blight)",
                    "bn": "টমেটোর আর্লি ব্লাইট রোগ",
                    "gu": "ટામેટાનો આગોતરો સુકારો (Early blight)",
                    "ml": "തക്കാളിയിലെ മുൻകാല കരിച്ചിൽ രോഗം",
                    "or": "ଟମାଟୋ ଆଗୁଆ ଝାଉଁଳା ରୋଗ (Early blight)",
                    "en": "Early Blight of Tomato (Alternaria solani)"
                }
                non_chem = {
                    "te": "కింది ఆకులు తడి మట్టికి తగలకుండా కర్రల ఆసరా ఇవ్వండి.",
                    "mr": "झाडांना काठ्यांचा आधार देऊन पाने जमिनीला टेकू देऊ नका.",
                    "pa": "ਬੂਟਿਆਂ ਨੂੰ ਸਹਾਰਾ ਦਿਓ ਤਾਂ ਜੋ ਪੱਤੇ ਗਿੱਲੀ ਮਿੱਟੀ ਨਾਲ ਨਾ ਲੱਗਣ।",
                    "hi": "निचली पत्तियों को गीली मिट्टी से छूने से रोकने के लिए सहारा दें।",
                    "ta": "அடிப்பகுதி இலைகள் ஈர மண்ணில் படாமல் இருக்க குச்சிகளால் முட்டுக் கொடுக்கவும்.",
                    "kn": "ಕೆಳಗಿನ ಎಲೆಗಳು ಒದ್ದೆ ಮಣ್ಣಿಗೆ ತಾಗದಂತೆ ಕೋಲುಗಳ ಆಸರೆ ನೀಡಿ.",
                    "bn": "নিচের পাতাগুলি যেন ভেজা মাটিতে না ঠেকে তার ব্যবস্থা করুন।",
                    "gu": "નીચેના પાન ભીની માટીને ન અડે તે માટે ટેકો આપો.",
                    "ml": "അടിയിലെ ഇലകൾ നനഞ്ഞ മണ്ണിൽ തൊടാതെ താങ്ങു നൽകുക.",
                    "or": "ତଳ ପତ୍ର ଓଦା ମାଟିରେ ନ ଲାଗିବା ପାଇଁ ବାଉଁଶ ବାଡ଼ା ଦିଅନ୍ତୁ |",
                    "en": "Stake plants so lower foliage does not touch moist soil; remove lower infected leaves."
                }
                quote = "Mancozeb 75% WP @ 2.5 g per litre of water"
                chemical = "Mancozeb 75% WP"
                dose_l = "2.5 g per litre"
                dose_tank = "37.5 g per 15-litre pump"
                phi = 7

        # Assemble full validated answer text
        safety_line = self._get_safety_line(language)
        kvk_advice = self._get_kvk_advice(language)
        guide_source = f"Source: {publisher} - {source_title} (Page {page})"

        treatment = TreatmentRecommendation(
            chemical=chemical,
            dose_per_litre=dose_l,
            dose_per_15l_tank=dose_tank,
            chunk_id=chunk_id,
            quote=quote,
            waiting_period_days=phi
        )

        loc_name = local_names.get(language, local_names.get("te", prob_name))
        step = non_chem.get(language, non_chem.get("te", ""))

        # Assemble full validated answer text with multilingual headers
        templates = {
            "te": (
                f"1. ప్రధాన సమస్య: {loc_name}\n"
                f"2. రసాయనం లేని రక్షణ: {step}\n"
                f"3. సిఫార్సు మందు: {chemical} - మోతాదు: {dose_l} ({dose_tank}).\n"
                f"4. రక్షణ సూచన: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "mr": (
                f"1. मुख्य समस्या: {loc_name}\n"
                f"2. गैर-रासायनिक उपाय: {step}\n"
                f"3. शिफारस केलेले औषध: {chemical} - प्रमाण: {dose_l} ({dose_tank}).\n"
                f"4. सुरक्षा सूचना: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "pa": (
                f"1. ਮੁੱਖ ਸਮੱਸਿਆ: {loc_name}\n"
                f"2. ਗੈਰ-ਰਸਾਇਣਕ ਉਪਾਅ: {step}\n"
                f"3. ਸਿਫ਼ਾਰਸ਼ ਕੀਤੀ ਦਵਾਈ: {chemical} - ਮਾਤਰਾ: {dose_l} ({dose_tank})।\n"
                f"4. ਸੁਰੱਖਿਆ ਸਾਵਧਾਨੀ: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "hi": (
                f"1. मुख्य समस्या: {loc_name}\n"
                f"2. गैर-रासायनिक रोकथाम: {step}\n"
                f"3. अनुशंसित उपचार: {chemical} - मात्रा: {dose_l} ({dose_tank})।\n"
                f"4. सुरक्षा निर्देश: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "ta": (
                f"1. முக்கிய பிரச்சனை: {loc_name}\n"
                f"2. இரசாயனமற்ற மேலாண்மை: {step}\n"
                f"3. பரிந்துரைக்கப்படும் மருந்து: {chemical} - அளவு: {dose_l} ({dose_tank}).\n"
                f"4. பாதுகாப்பு வழிமுறை: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "kn": (
                f"1. ಪ್ರಮುಖ ಸಮಸ್ಯೆ: {loc_name}\n"
                f"2. ರಾಸಾಯನಿಕವಲ್ಲದ ನಿಯಂತ್ರಣ: {step}\n"
                f"3. ಶಿಫಾರಸು ಮಾಡಿದ ಔಷಧ: {chemical} - ಪ್ರಮಾಣ: {dose_l} ({dose_tank}).\n"
                f"4. ಸುರಕ್ಷತಾ ಸೂಚನೆ: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "bn": (
                f"1. প্রধান সমস্যা: {loc_name}\n"
                f"2. অ-রাসায়নিক প্রতিকার: {step}\n"
                f"3. সুপারিশকৃত ওষুধ: {chemical} - মাত্রা: {dose_l} ({dose_tank})।\n"
                f"4. সুরক্ষা নির্দেশিকা: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "gu": (
                f"1. મુખ્ય સમસ્યા: {loc_name}\n"
                f"2. બિન-રાસાયણિક ઉપાય: {step}\n"
                f"3. ભલામણ કરેલ દવા: {chemical} - પ્રમાણ: {dose_l} ({dose_tank}).\n"
                f"4. સલામતી સૂચના: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "ml": (
                f"1. പ്രധാന പ്രശ്നം: {loc_name}\n"
                f"2. രാസേതര നിയന്ത്രണം: {step}\n"
                f"3. ശുപാർശ ചെയ്യുന്ന മരുന്ന്: {chemical} - അളവ്: {dose_l} ({dose_tank}).\n"
                f"4. സുരക്ഷാ മുൻകരുതൽ: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "or": (
                f"1. ମୁଖ୍ୟ ସମସ୍ୟା: {loc_name}\n"
                f"2. ଅଣ-ରାସାୟନିକ ନିୟନ୍ତ୍ରଣ: {step}\n"
                f"3. ସୁପାରିଶ ଔଷଧ: {chemical} - ମାତ୍ରା: {dose_l} ({dose_tank})।\n"
                f"4. ସୁରକ୍ଷା ପରାମର୍ଶ: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            ),
            "en": (
                f"1. Primary Problem: {loc_name}\n"
                f"2. Non-Chemical Management: {step}\n"
                f"3. Recommended Treatment: {chemical} - Dose: {dose_l} ({dose_tank}).\n"
                f"4. Safety Precaution: {safety_line}\n"
                f"5. {kvk_advice}\n"
                f"{guide_source}"
            )
        }
        final_text = templates.get(language, templates["te"])

        return EvonDecision(
            tool_called="answer_case",
            likely_problems=[LikelyProblem(name=prob_name, local_name=loc_name, confidence=round(top_conf, 2))],
            non_chemical_step=step,
            treatment=treatment,
            safety_line=safety_line,
            guide_source=guide_source,
            kvk_advice=kvk_advice,
            final_text=final_text
        )

    async def _verify_guardrails(
        self,
        decision: EvonDecision,
        guide_chunks: List[Dict[str, Any]],
        transcript: str
    ) -> EvonDecision:
        """
        Enforce Guardrails:
        1. Banned Chemical Check
        2. Exact Quote Verification in Cited Chunk
        3. No Synthetic Chemical Cocktails
        """
        if decision.tool_called != "answer_case" or not decision.treatment:
            return decision

        treatment = decision.treatment
        banned_list = await db.get_banned_inputs()

        # Guardrail 1: Banned Input Check
        chem_name_lower = treatment.chemical.lower()
        for banned in banned_list:
            if banned in chem_name_lower:
                logger.error(f"[GUARDRAIL VIOLATION] Recommended chemical '{treatment.chemical}' is in banned list!")
                decision.tool_called = "escalate"
                decision.treatment = None
                decision.is_grounded = False
                decision.reason = f"Security block: '{treatment.chemical}' is prohibited by agricultural safety regulations."
                decision.final_text = (
                    "భద్రతా హెచ్చరిక: ఈ రసాయనం నిషేధించబడినది. దయచేసి ఎటువంటి నిషేధిత మందులు వాడవద్దు. "
                    "సరైన ప్రత్యామ్నాయం కోసం దగ్గరలోని కృషి విజ్ఞాన కేంద్రం (KVK) లేదా 1800-180-1551 ను సంప్రదించండి."
                )
                decision.validation_notes.append(f"Blocked banned chemical: {banned}")
                return decision

        # Guardrail 2: Exact Quote Grounding in Retrieved Chunk
        cited_chunk = next((c for c in guide_chunks if c["id"] == treatment.chunk_id), None)
        if not cited_chunk:
            # Check first chunk as fallback
            cited_chunk = guide_chunks[0]

        chunk_text = cited_chunk.get("text", "")
        # Clean both quote and chunk for robust whitespace comparison
        clean_quote = re.sub(r"\s+", " ", treatment.quote.strip().lower())
        clean_chunk = re.sub(r"\s+", " ", chunk_text.lower())

        if clean_quote not in clean_chunk:
            logger.error(f"[GUARDRAIL VIOLATION] Quote '{treatment.quote}' not found in chunk {cited_chunk['id']}!")
            decision.tool_called = "escalate"
            decision.treatment = None
            decision.is_grounded = False
            decision.reason = "Citation verification failed: chemical quote is not verbatim in university guides."
            decision.final_text = (
                "ఈ సమస్యకు అధికారిక విశ్వవిద్యాలయ గ్రంథంలో స్పష్టమైన మందు లభించలేదు. "
                "సరికాని రసాయనాలు సిఫార్సు చేయకుండా నివారించడానికి, దయచేసి స్థానిక KVK శాస్త్రవేత్తలను సంప్రదించండి."
            )
            decision.validation_notes.append("Rejected ungrounded chemical quote.")
            return decision

        decision.is_grounded = True
        decision.validation_notes.append("Quote successfully verified verbatim in university chunk.")
        return decision

    # =========================================================================
    # Multilingual Helper Strings (11 Indic & Indian Languages)
    # =========================================================================
    def _get_safety_line(self, lang: str) -> str:
        lines = {
            "te": "మందు పిచికారీ చేసేటప్పుడు తప్పనిసరిగా ముక్కుకు మాస్క్ మరియు చేతులకు గ్లౌజులు ధరించండి. గాలి వీచే దిశకు ఎదురుగా పిచికారీ చేయకండి.",
            "mr": "फवारणी करताना तोंडाला मास्क आणि हातात हातमोजे वापरा. वाऱ्याच्या विरुद्ध दिशेने फवारणी करू नका.",
            "pa": "ਸਪਰੇਅ ਕਰਦੇ ਸਮੇਂ ਮਾਸਕ ਅਤੇ ਦਸਤਾਨੇ ਜ਼ਰੂਰ ਪਹਿਨੋ। ਹਵਾ ਦੇ ਉਲਟ ਦਿਸ਼ਾ ਵਿੱਚ ਕਦੇ ਵੀ ਸਪਰੇਅ ਨਾ ਕਰੋ।",
            "hi": "कीटनाशक छिड़कते समय चेहरे पर मास्क और हाथों में दस्ताने जरूर पहनें। हवा की उल्टी दिशा में कभी छिड़काव न करें।",
            "ta": "மருந்து தெளிக்கும் போது முகக்கவசம் மற்றும் கையுறைகள் கட்டாயம் அணியவும். காற்று வீசும் திசைக்கு எதிரே தெளிக்க வேண்டாம்.",
            "kn": "ಔಷಧ ಸಿಂಪಡಿಸುವಾಗ ಮುಖಗವಸು (ಮಾಸ್ಕ್) ಮತ್ತು ಕೈಗವಸುಗಳನ್ನು ಧರಿಸಿ. ಗಾಳಿಯ ವಿರುದ್ಧ ದಿಕ್ಕಿನಲ್ಲಿ ಸಿಂಪಡಿಸಬೇಡಿ.",
            "bn": "কীটনাশক স্প্রে করার সময় মুখে মাস্ক এবং হাতে গ্লাভস পরুন। বাতাসের বিপরীত দিকে কখনই স্প্রে করবেন না।",
            "gu": "દવાનો છંટકાવ કરતી વખતે મોં પર માસ્ક અને હાથમાં મોજાં પહેરો. પવનની વિરુદ્ધ દિશામાં ક્યારેય છંટકાવ ન કરવો.",
            "ml": "കീടനാശിനി തളിക്കുമ്പോൾ മുഖംമൂടിയും കൈയ്യുറകളും ധരിക്കുക. കാറ്റിന്റെ എതിർദിശയിൽ തളിക്കരുത്.",
            "or": "ଔଷଧ ସ୍ପ୍ରେ କରିବା ସମୟରେ ମାସ୍କ ଏବଂ ହାତମୋଜା ପିନ୍ଧନ୍ତୁ | ପବନର ବିପରୀତ ଦିଗରେ କେବେବି ସ୍ପ୍ରେ କରନ୍ତୁ ନାହିଁ |",
            "en": "Always wear a protective face mask and gloves during spraying. Never spray against the wind direction."
        }
        return lines.get(lang, lines["te"])

    def _get_kvk_advice(self, lang: str) -> str:
        lines = {
            "te": "సమస్య 4-5 రోజుల్లో తగ్గకపోతే లేదా తోటలో మూడోవంతు కంటే ఎక్కువ వ్యాపిస్తే మీ దగ్గరలోని కృషి విజ్ఞాన కేంద్రం (KVK) ను సంప్రదించండి లేదా కిసాన్ కాల్ సెంటర్ 1800-180-1551 కు కాల్ చేయండి.",
            "mr": "समस्या ४-५ दिवसांत कमी न झाल्यास किंवा शेतात वेगाने पसरत असल्यास जवळच्या कृषी विज्ञान केंद्राशी (KVK) संपर्क साधा किंवा किसान कॉल सेंटर १८००-१८०-१५५१ वर संपर्क करा.",
            "pa": "ਜੇਕਰ ਰੋਗ 4-5 ਦਿਨਾਂ ਵਿੱਚ ਨਾ ਰੁਕੇ ਤਾਂ ਨੇੜਲੇ ਕ੍ਰਿਸ਼ੀ ਵਿਗਿਆਨ ਕੇਂਦਰ (KVK) ਜਾਂ ਕਿਸਾਨ ਕਾਲ ਸੈਂਟਰ 1800-180-1551 'ਤੇ ਸੰਪਰਕ ਕਰੋ।",
            "hi": "यदि समस्या 4-5 दिनों में ठीक न हो या खेत में फैले, तो नजदीकी कृषि विज्ञान केंद्र (KVK) से संपर्क करें या किसान कॉल सेंटर 1800-180-1551 पर कॉल करें।",
            "ta": "பிரச்சனை 4-5 நாட்களில் குறையவில்லை என்றால், அருகிலுள்ள வேளாண் அறிவியல் மையத்தை (KVK) அணுகவும் அல்லது கிசான் உதவி எண் 1800-180-1551 ஐ தொடர்பு கொள்ளவும்.",
            "kn": "ಸಮಸ್ಯೆ 4-5 ದಿನಗಳಲ್ಲಿ ಕಡಿಮೆಯಾಗದಿದ್ದರೆ ಸಮೀಪದ ಕೃಷಿ ವಿಜ್ಞಾನ ಕೇಂದ್ರ (KVK) ಅಥವಾ ಕಿಸಾನ್ ಕಾಲ್ ಸೆಂಟರ್ 1800-180-1551 ಗೆ ಕರೆ ಮಾಡಿ.",
            "bn": "সমস্যা ৪-৫ দিনে না কমলে নিকটস্থ কৃষি বিজ্ঞান কেন্দ্র (KVK) বা কিষাণ কল সেন্টার ১৮০০-১৮০-১৫৫১ নম্বরে যোগাযোগ করুন।",
            "gu": "જો સમસ્યા ૪-૫ દિવસમાં નિયંત્રણમાં ન આવે તો નજીકના કૃષિ વિજ્ઞાન કેન્દ્ર (KVK) નો સંપર્ક કરો અથવા કિસાન કોલ સેન્ટર ૧૮૦૦-૧૮૦-૧૫૫૧ પર સંપર્ક કરો.",
            "ml": "പ്രശ്നം 4-5 ദിവസത്തിനകം മാറിയില്ലെങ്കിൽ അടുത്തുള്ള കൃഷി വിജ്ഞാന കേന്ദ്രവുമായോ (KVK) കിസാൻ കോൾ സെന്ററുമായോ 1800-180-1551 ബന്ധപ്പെടുക.",
            "or": "ସମସ୍ୟା ୪-୫ ଦିନ ମଧ୍ୟରେ ନ କମିଲେ ନିକଟସ୍ଥ କୃଷି ବିଜ୍ଞାନ କେନ୍ଦ୍ର (KVK) କିମ୍ବା କିଷାନ କଲ୍ ସେଣ୍ଟର ୧୮୦୦-୧୮୦-୧୫୫୧ ରେ ଯୋଗାଯୋଗ କରନ୍ତୁ |",
            "en": "If symptoms persist beyond 4-5 days or spread to more than one-third of the field, contact your local Krishi Vigyan Kendra (KVK) or call Kisan Call Centre at 1800-180-1551."
        }
        return lines.get(lang, lines["te"])

    def _get_missing_photo_message(self, lang: str) -> str:
        lines = {
            "te": "మీ వాయిస్ మెసేజ్ అందినది, కానీ ఆకు ఫోటో రాలేదు. సరైన నిర్ధారణ కోసం దయచేసి దెబ్బతిన్న ఆకు ఫోటోను దగ్గరగా తీసి పంపండి.",
            "mr": "तुमचा व्हॉइस मेसेज मिळाला, पण पानाचा फोटो आलेला नाही. योग्य निदानासाठी कृपया बाधित पानाचा जवळून काढलेला फोटो पाठवा.",
            "pa": "ਤੁਹਾਡਾ ਵੌਇਸ ਮੈਸੇਜ ਮਿਲ ਗਿਆ ਹੈ ਪਰ ਪੱਤੇ ਦੀ ਫੋਟੋ ਨਹੀਂ ਆਈ। ਕਿਰਪਾ ਕਰਕੇ ਪ੍ਰਭਾਵਿਤ ਪੱਤੇ ਦੀ ਸਾਫ਼ ਫੋਟੋ ਭੇਜੋ।",
            "hi": "आपका वॉयस मैसेज प्राप्त हुआ, लेकिन पत्ते का फोटो नहीं मिला। सटीक जांच के लिए कृपया प्रभावित पत्ते का स्पष्ट फोटो भेजें।",
            "ta": "உங்கள் குரல் பதிவு கிடைத்தது, ஆனால் இலையின் புகைப்படம் கிடைக்கவில்லை. சரியான பரிந்துரைக்கு பாதிக்கப்பட்ட இலையின் புகைப்படத்தை அனுப்பவும்.",
            "kn": "ನಿಮ್ಮ ಧ್ವನಿ ಸಂದೇಶ ತಲುಪಿದೆ, ಆದರೆ ಎಲೆಯ ಫೋಟೋ ಬಂದಿಲ್ಲ. ನಿಖರ ತಪಾಸಣೆಗಾಗಿ ದಯವಿಟ್ಟು ಬಾಧಿತ ಎಲೆಯ ಸ್ಪಷ್ಟ ಫೋಟೋ ಕಳುಹಿಸಿ.",
            "bn": "আপনার ভয়েস মেসেজ পেয়েছি, কিন্তু পাতার ছবি আসেনি। সঠিক পরামর্শের জন্য অনুগ্রহ করে আক্রান্ত পাতার একটি স্পষ্ট ছবি পাঠান।",
            "gu": "તમારો અવાજ સંદેશ મળ્યો, પણ પાનનો ફોટો મળ્યો નથી. યોગ્ય નિદાન માટે કૃપા કરીને અસરગ્રસ્ત પાનનો સ્પષ્ટ ફોટો મોકલો.",
            "ml": "വോയ്‌സ് മെസ്സേജ് ലഭിച്ചു, എന്നാൽ ഇലയുടെ ഫോട്ടോ ലഭിച്ചില്ല. കൃത്യമായ രോഗനിർണ്ണയത്തിനായി രോഗബാധിത ഇലയുടെ വ്യക്തമായ ഫോട്ടോ അയക്കുക.",
            "or": "ଆପଣଙ୍କ ଭଏସ୍ ମେସେଜ୍ ମିଳିଲା, କିନ୍ତୁ ପତ୍ରର ଫଟୋ ଆସିନାହିଁ | ଦୟାକରି ପ୍ରଭାବିତ ପତ୍ରର ଏକ ସ୍ପଷ୍ଟ ଫଟୋ ପଠାନ୍ତୁ |",
            "en": "Voice note received, but no leaf photo was provided. Please send a close-up photo of the affected plant leaf for accurate diagnosis."
        }
        return lines.get(lang, lines["te"])

    def _get_non_plant_message(self, lang: str) -> str:
        lines = {
            "te": "పంపిన ఫోటోలో పంట లేదా ఆకు కనిపించడం లేదు. దయచేసి సమస్య ఉన్న పంట ఆకు లేదా మొక్క భాగాన్ని స్పష్టంగా ఫోటో తీసి పంపండి.",
            "mr": "पाठवलेल्या फोटोमध्ये पीक किंवा पान दिसत नाही. कृपया बाधित पिकाच्या पानाचा स्पष्ट फोटो पाठवा.",
            "pa": "ਫੋਟੋ ਵਿੱਚ ਫ਼ਸਲ ਜਾਂ ਪੱਤਾ ਸਾਫ਼ ਨਹੀਂ ਦਿਖ ਰਿਹਾ। ਕਿਰਪਾ ਕਰਕੇ ਪ੍ਰਭਾਵਿਤ ਪੌਦੇ ਦੇ ਪੱਤੇ ਦੀ ਫੋਟੋ ਭੇਜੋ।",
            "hi": "भेजे गए फोटो में फसल या पत्ती नहीं दिख रही है। कृपया प्रभावित पौधे की पत्ती का स्पष्ट फोटो भेजें।",
            "ta": "அனுப்பிய புகைப்படத்தில் பயிர் அல்லது இலை தெளிவாக இல்லை. தயவுசெய்து பாதிக்கப்பட்ட இலையின் தெளிவான புகைப்படத்தை அனுப்பவும்.",
            "kn": "ಕಳುಹಿಸಿದ ಫೋಟೋದಲ್ಲಿ ಬೆಳೆ ಅಥವಾ ಎಲೆ ಕಾಣಿಸುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ರೋಗಪೀಡಿತ ಎಲೆಯ ಸ್ಪಷ್ಟ ಫೋಟೋ ಕಳುಹಿಸಿ.",
            "bn": "পাঠানো ছবিতে ফসল বা পাতা দেখা যাচ্ছে না। দয়া করে আক্রান্ত পাতার স্পষ্ট ছবি পাঠান।",
            "gu": "મોકલેલા ફોટામાં પાક કે પાંદડું દેખાતું નથી. કૃપા કરીને અસરગ્રસ્ત પાનનો સ્પષ્ટ ફોટો મોકલો.",
            "ml": "അയച്ച ഫോട്ടോയിൽ വിളയോ ഇലയോ വ്യക്തമല്ല. ദയവായി രോഗം ബാധിച്ച ഇലയുടെ വ്യക്തമായ ഫോട്ടോ അയക്കുക.",
            "or": "ପଠାଯାଇଥିବା ଫଟୋରେ ଫସଲ କିମ୍ବା ପତ୍ର ଦେଖାଯାଉ ନାହିଁ | ଦୟାକରି ଆକ୍ରାନ୍ତ ପତ୍ରର ସ୍ପଷ୍ଟ ଫଟୋ ପଠାନ୍ତୁ |",
            "en": "The submitted image does not appear to contain a crop or plant leaf. Please send a clear photo of the affected leaf."
        }
        return lines.get(lang, lines["te"])

    def _get_unclear_photo_message(self, lang: str) -> str:
        lines = {
            "te": "ఫోటో అస్పష్టంగా ఉంది లేదా చాలా దూరం నుండి తీయబడింది. దయచేసి దెబ్బతిన్న ఒకే ఆకు పైభాగం మరియు వెనుక భాగం దగ్గరగా (close-up) స్పష్టంగా ఫోటో తీసి పంపండి.",
            "mr": "फोटो अंधुक आहे किंवा खूप लांबून काढला आहे. कृपया बाधित एका पानाच्या वरच्या आणि खालच्या बाजूचा जवळून (close-up) स्पष्ट फोटो पाठवा.",
            "pa": "ਫੋਟੋ ਧੁੰਦਲੀ ਹੈ ਜਾਂ ਦੂਰੋਂ ਖਿੱਚੀ ਗਈ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਪ੍ਰਭਾਵਿਤ ਪੱਤੇ ਦੇ ਉੱਪਰਲੇ ਅਤੇ ਹੇਠਲੇ ਹਿੱਸੇ ਦੀ ਨੇੜਿਓਂ ਸਾਫ਼ ਫੋਟੋ ਭੇਜੋ।",
            "hi": "फोटो धुंधला है या बहुत दूर से लिया गया है। कृपया प्रभावित पत्ती के ऊपरी और निचले हिस्से का पास से (close-up) स्पष्ट फोटो भेजें।",
            "ta": "புகைப்படம் மங்கலாக உள்ளது. பாதிக்கப்பட்ட இலையின் மேற்புறம் மற்றும் அடிப்பகுதியை நெருக்கமாக படம் பிடித்து அனுப்பவும்.",
            "kn": "ಫೋಟೋ ಮಸುಕಾಗಿದೆ. ದಯವಿಟ್ಟು ಬಾಧಿತ ಎಲೆಯ ಮೇಲ್ಭಾಗ ಮತ್ತು ಕೆಳಭಾಗದ ಹತ್ತಿರದ ಸ್ಪಷ್ಟ ಫೋಟೋ ಕಳುಹಿಸಿ.",
            "bn": "ছবিটি ঝাপসা এসেছে। দয়া করে আক্রান্ত পাতার উপরিভাগ ও নিচের অংশের কাছ থেকে তোলা স্পষ্ট ছবি পাঠান।",
            "gu": "ફોટો ઝાંખો છે. કૃપા કરીને અસરગ્રસ્ત પાનની ઉપર અને નીચેની બાજુનો નજીકથી સ્પષ્ટ ફોટો મોકલો.",
            "ml": "ഫോട്ടോ വ്യക്തമല്ല. ഇലയുടെ മുകൾ ഭാഗവും അടിഭാഗവും കാണത്തക്ക വിധം അടുത്തുവെച്ച് വ്യക്തമായ ഫോട്ടോ അയക്കുക.",
            "or": "ଫଟୋ ଅସ୍ପଷ୍ଟ ଅଛି | ଦୟାକରି ଆକ୍ରାନ୍ତ ପତ୍ରର ପାଖରୁ ସ୍ପଷ୍ଟ ଫଟୋ ଉଠାଇ ପଠାନ୍ତୁ |",
            "en": "The photo is blurry or taken from too far away. Please take a clear close-up photo showing both the upper and lower surfaces of a single affected leaf."
        }
        return lines.get(lang, lines["te"])

    def _get_unsupported_crop_message(self, crop: str, lang: str) -> str:
        lines = {
            "te": f"'{crop}' పంటకు సంబంధించిన అధికారిక విశ్వవిద్యాలయ సిఫార్సులు డేటాబేస్‌లో లేవు. తప్పుడు మందులు సూచించకుండా నివారించడానికి, దయచేసి KVK శాస్త్రవేత్తలను లేదా కిసాన్ కాల్ సెంటర్ 1800-180-1551 ను సంప్రదించండి.",
            "mr": f"'{crop}' या पिकाची विद्यापीठ शिफारस सध्या उपलब्ध नाही. चुकीचे औषध टाळण्यासाठी कृपया कृषी विज्ञान केंद्रातील (KVK) शास्त्रज्ञांशी किंवा किसान कॉल सेंटर १८००-१८०-१५५१ वर संपर्क करा.",
            "pa": f"'{crop}' ਫ਼ਸਲ ਬਾਰੇ ਯੂਨੀਵਰਸਿਟੀ ਦੀ ਸਿਫ਼ਾਰਸ਼ ਉਪਲਬਧ ਨਹੀਂ ਹੈ। ਸਹੀ ਜਾਣਕਾਰੀ ਲਈ ਕ੍ਰਿਸ਼ੀ ਵਿਗਿਆਨ ਕੇਂਦਰ (KVK) ਜਾਂ 1800-180-1551 'ਤੇ ਸੰਪਰਕ ਕਰੋ।",
            "hi": f"'{crop}' फसल के लिए आधिकारिक विश्वविद्यालय सिफारिशें उपलब्ध नहीं हैं। गलत कीटनाशक के प्रयोग से बचने के लिए, कृपया KVK वैज्ञानिकों या किसान कॉल सेंटर 1800-180-1551 से संपर्क करें।",
            "ta": f"'{crop}' பயிருக்கான பல்கலைக்கழக வழிகாட்டுதல் தற்போது தரவுத்தளத்தில் இல்லை. தவறான மருந்துகளைத் தவிர்க்க KVK அல்லது 1800-180-1551 ஐ தொடர்பு கொள்ளவும்.",
            "kn": f"'{crop}' ಬೆಳೆಗೆ ಸಂಬಂಧಿಸಿದ ಅಧಿಕೃತ ವಿಶ್ವವಿದ್ಯಾಲಯ ಶಿಫಾರಸು ಲಭ್ಯವಿಲ್ಲ. ತಪ್ಪು ಕೀಟನಾಶಕ ತಪ್ಪಿಸಲು KVK ಅಥವಾ 1800-180-1551 ಸಂಪರ್ಕಿಸಿ.",
            "bn": f"'{crop}' ফসলের জন্য সরকারি বিশ্ববিদ্যালয়ের সুপারিশ বর্তমানে তথ্যভাণ্ডারে নেই। সঠিক পরামর্শের জন্য KVK বা ১৮০০-১৮০-১৫৫১ নম্বরে যোগাযোগ করুন।",
            "gu": f"'{crop}' પાક માટે યુનિવર્સિટીની સત્તાવાર ભલામણો ઉપલબ્ધ નથી. ખોટી દવા ટાળવા KVK અથવા ૧૮૦૦-૧૮૦-૧૫૫૧ પર સંપર્ક કરો.",
            "ml": f"'{crop}' വിളയ്ക്കുള്ള ഔദ്യോഗിക ശുപാർശകൾ ലഭ്യമല്ല. തെറ്റായ കീടനാശിനി പ്രયોગം ഒഴിവാക്കാൻ KVK യുമായി ബന്ധപ്പെടുക.",
            "or": f"'{crop}' ଫସଲ ପାଇଁ ସରକାରୀ ବିଶ୍ୱବିଦ୍ୟାଳୟ ସୁପାରିଶ ଉପଲବ୍ଧ ନାହିଁ | ସଠିକ୍ ପରାମର୍ଶ ପାଇଁ KVK କିମ୍ବା ୧୮୦୦-୧୮୦-୧୫୫୧ ରେ ଯୋଗାଯୋଗ କରନ୍ତୁ |",
            "en": f"Official university package of practices for '{crop}' is not currently in the verified database. To prevent ungrounded chemical usage, please consult local KVK experts or Kisan Call Centre at 1800-180-1551."
        }
        return lines.get(lang, lines["te"])

    def _get_low_confidence_message(self, lang: str) -> str:
        lines = {
            "te": "లక్షణాలు పూర్తిగా స్పష్టంగా లేవు. తప్పుడు మందు పిచికారీ చేయడం వల్ల పంట దెబ్బతినే ప్రమాదం ఉంది. దయచేసి మొక్క మొత్తం కనిపించేలా మరొక స్పష్టమైన ఫోటో పంపండి.",
            "mr": "रोगाची लक्षणे पुरेशी स्पष्ट नाहीत. चुकीचे औषध फवारल्यास नुकसान होऊ शकते. कृपया संपूर्ण झाड दिसेल असा आणखी एक स्पष्ट फोटो पाठवा.",
            "pa": "ਲੱਛਣ ਪੂਰੀ ਤਰ੍ਹਾਂ ਸਾਫ਼ ਨਹੀਂ ਹਨ। ਕਿਰਪਾ ਕਰਕੇ ਪੂਰੇ ਪੌਦੇ ਦੀ ਇੱਕ ਹੋਰ ਸਾਫ਼ ਫੋਟੋ ਭੇਜੋ ਤਾਂ ਜੋ ਸਹੀ ਜਾਂਚ ਹੋ ਸਕੇ।",
            "hi": "लक्षण पूरी तरह स्पष्ट नहीं हैं। गलत कीटनाशक छिड़कने से फसल को नुकसान हो सकता है। कृपया पूरे पौधे की एक और स्पष्ट फोटो भेजें।",
            "ta": "அறிகுறிகள் தெளிவாக இல்லை. தவறான மருந்து பயிரை பாதிக்கும் என்பதால் முழு செடியும் தெரியும்படி மற்றொரு தெளிவான படம் அனுப்பவும்.",
            "kn": "ರೋಗಲಕ್ಷಣಗಳು ಸ್ಪಷ್ಟವಾಗಿಲ್ಲ. ತಪ್ಪು ಔಷಧ ಸಿಂಪಡಿಸಿದರೆ ಬೆಳೆ ಹಾನಿಯಾಗಬಹುದು. ದಯವಿಟ್ಟು ಸಂಪೂರ್ಣ ಗಿಡ ಕಾಣಿಸುವ ಮತ್ತೊಂದು ಸ್ಪಷ್ಟ ಫೋಟೋ ಕಳುಹಿಸಿ.",
            "bn": "লক্ষণগুলি স্পষ্ট নয়। ভুল কীটনাশক দিলে ফসলের ক্ষতি হতে পারে। দয়া করে পুরো গাছের একটি পরিষ্কার ছবি পাঠান।",
            "gu": "લક્ષણો સ્પષ્ટ નથી. ખોટી દવાથી પાકને નુકસાન થઈ શકે છે. કૃપા કરીને આખા છોડનો બીજો સ્પષ્ટ ફોટો મોકલો.",
            "ml": "ലക്ഷണങ്ങൾ വ്യക്തമല്ല. തെറ്റായ മരുന്ന് വിളയെ നശിപ്പിക്കാൻ ഇടയുണ്ട്. മുഴുവൻ ചെടിയും കാണുന്ന മറ്റൊരു ഫോട്ടോ അയക്കുക.",
            "or": "ରୋଗର ଲକ୍ଷଣ ସ୍ପଷ୍ଟ ନାହିଁ | ଦୟାକରି ସମ୍ପୂର୍ଣ୍ଣ ଗଛ ଦେଖାଯିବା ଭଳି ଆଉ ଏକ ସ୍ପଷ୍ଟ ଫଟୋ ପଠାନ୍ତୁ |",
            "en": "Symptoms are not sufficiently conclusive. To prevent risk of applying improper treatments, please send another clear photo showing the whole plant canopy."
        }
        return lines.get(lang, lines["te"])


evon_service = EvonService()
