import pytest
from app.services.evon import evon_service, TreatmentRecommendation, EvonDecision
from app.schemas import VisionObservation
from app.services.retriever import guide_retriever


@pytest.mark.asyncio
async def test_evon_grounded_answer_chilli_whitefly():
    """Verify grounded answer for Telugu Chilli Leaf Curl with Whitefly."""
    obs = VisionObservation(
        is_plant=True,
        is_clear=True,
        curling="severe upward curling",
        insects_visible="tiny white winged insects on underside",
        confidence_scores={"leaf_curl": 0.89, "whitefly": 0.86}
    )
    chunks = await guide_retriever.search("whitefly leaf curl", crop="chilli", state="Telangana", top_k=2)

    decision = await evon_service.reason(
        vision_obs=obs,
        transcript="Aakulu paiki muduchukupotunnayi tella doma undi",
        crop="chilli",
        crop_age_days=60,
        state="Telangana",
        guide_chunks=chunks,
        language="te"
    )

    assert decision.tool_called == "answer_case"
    assert decision.is_grounded is True
    assert decision.treatment is not None
    assert "Diafenthiuron" in decision.treatment.chemical
    # Verify the quote is verbatim in the retrieved chunk
    assert decision.treatment.quote in chunks[0]["text"]
    assert "15-litre" in decision.treatment.dose_per_15l_tank


@pytest.mark.asyncio
async def test_evon_cotton_pink_bollworm():
    """Verify Marathi Cotton Pink Bollworm advisory with rosette flower removal."""
    obs = VisionObservation(
        is_plant=True,
        is_clear=True,
        spots="bore holes in bolls, rosette flowers",
        insects_visible="pink caterpillar larva",
        confidence_scores={"pink_bollworm": 0.93}
    )
    chunks = await guide_retriever.search("pink bollworm rosette flowers", crop="cotton", state="Maharashtra", top_k=2)

    decision = await evon_service.reason(
        vision_obs=obs,
        transcript="Bondat gulabi aali disat aahe",
        crop="cotton",
        crop_age_days=90,
        state="Maharashtra",
        guide_chunks=chunks,
        language="mr"
    )

    assert decision.tool_called == "answer_case"
    assert decision.is_grounded is True
    assert "Profenophos" in decision.treatment.chemical
    assert "कामगंध" in decision.non_chemical_step or "डोमकळ्या" in decision.non_chemical_step


@pytest.mark.asyncio
async def test_evon_paddy_brown_spot():
    """Verify Punjabi Paddy Brown Spot advisory."""
    obs = VisionObservation(
        is_plant=True,
        is_clear=True,
        spots="oval brown spots with yellow halo",
        confidence_scores={"brown_spot": 0.90}
    )
    chunks = await guide_retriever.search("brown spot", crop="paddy", state="Punjab", top_k=2)

    decision = await evon_service.reason(
        vision_obs=obs,
        transcript="Pattean te bhoore dhabbe aa gaye ne",
        crop="paddy",
        crop_age_days=45,
        state="Punjab",
        guide_chunks=chunks,
        language="pa"
    )

    assert decision.tool_called == "answer_case"
    assert "Propiconazole" in decision.treatment.chemical
    assert decision.treatment.quote in chunks[0]["text"]


@pytest.mark.asyncio
async def test_evon_tomato_nutrient_yellowing_no_pesticide():
    """Verify physiological nitrogen chlorosis suggests foliar nutrition and NO pesticide."""
    obs = VisionObservation(
        is_plant=True,
        is_clear=True,
        spots="none",
        colour="uniform pale yellowing on older leaves",
        confidence_scores={"nitrogen_deficiency": 0.88}
    )
    chunks = await guide_retriever.search("nitrogen deficiency chlorosis yellowing", crop="tomato", state="Andhra Pradesh", top_k=2)

    decision = await evon_service.reason(
        vision_obs=obs,
        transcript="Tomato aakulu pasupu ga maaripotunnayi",
        crop="tomato",
        crop_age_days=40,
        state="Andhra Pradesh",
        guide_chunks=chunks,
        language="te"
    )

    assert decision.tool_called == "answer_case"
    assert "Urea" in decision.treatment.chemical
    assert "10 g per litre" in decision.treatment.dose_per_litre
    assert "పురుగు మందులు వాడవద్దు" in decision.non_chemical_step or "పోషక లోపం" in decision.non_chemical_step


@pytest.mark.asyncio
async def test_evon_banned_chemical_blocking():
    """Guardrail Test: Banned inputs (e.g. Monocrotophos) must be intercepted and blocked."""
    synthetic_decision = EvonDecision(
        tool_called="answer_case",
        treatment=TreatmentRecommendation(
            chemical="Monocrotophos 36% SL",
            dose_per_litre="1.5 ml per litre",
            dose_per_15l_tank="22.5 ml per 15L tank",
            chunk_id=1,
            quote="spray Monocrotophos 36% SL"
        )
    )

    chunks = [{"id": 1, "text": "spray Monocrotophos 36% SL"}]
    validated = await evon_service._verify_guardrails(synthetic_decision, chunks, "")

    # Must be escalated and blocked!
    assert validated.tool_called == "escalate"
    assert validated.treatment is None
    assert validated.is_grounded is False
    assert "Blocked banned chemical" in str(validated.validation_notes)


@pytest.mark.asyncio
async def test_evon_ungrounded_quote_rejection():
    """Guardrail Test: Recommending a chemical quote NOT in the retrieved chunk is blocked."""
    synthetic_decision = EvonDecision(
        tool_called="answer_case",
        treatment=TreatmentRecommendation(
            chemical="Chlorantraniliprole 18.5% SC",
            dose_per_litre="0.3 ml per litre",
            dose_per_15l_tank="4.5 ml per 15L tank",
            chunk_id=1,
            quote="spray Chlorantraniliprole 18.5% SC @ 0.3 ml per litre"
        )
    )

    # The chunk text does NOT contain this quote
    chunks = [{"id": 1, "text": "Only neem oil and yellow sticky traps are recommended."}]
    validated = await evon_service._verify_guardrails(synthetic_decision, chunks, "")

    assert validated.tool_called == "escalate"
    assert validated.treatment is None
    assert validated.is_grounded is False
    assert "Rejected ungrounded chemical quote" in str(validated.validation_notes)


@pytest.mark.asyncio
async def test_evon_blurry_photo_triggers_ask_more():
    """Edge Case: Blurry photo triggers ask_more."""
    obs = VisionObservation(is_plant=True, is_clear=False, confidence_scores={"unclear": 0.95})
    decision = await evon_service.reason(
        vision_obs=obs,
        transcript="paha kay jhalay",
        crop="cotton",
        crop_age_days=50,
        state="Maharashtra",
        guide_chunks=[{"id": 1, "text": "sample"}],
        language="mr"
    )
    assert decision.tool_called == "ask_more"
    assert "फोटो अंधुक आहे" in decision.request or "close-up" in decision.request


@pytest.mark.asyncio
async def test_evon_non_plant_triggers_ask_more():
    """Edge Case: Non-plant image triggers ask_more."""
    obs = VisionObservation(is_plant=False, is_clear=True, confidence_scores={"unclear": 0.99})
    decision = await evon_service.reason(
        vision_obs=obs,
        transcript="idi chudandi",
        crop="chilli",
        crop_age_days=30,
        state="Telangana",
        guide_chunks=[{"id": 1, "text": "sample"}],
        language="te"
    )
    assert decision.tool_called == "ask_more"
    assert "పంట లేదా ఆకు కనిపించడం లేదు" in decision.request


@pytest.mark.asyncio
async def test_evon_unsupported_crop_triggers_escalate():
    """Edge Case: Unrecognized crop with no guide chunks triggers escalation to KVK."""
    obs = VisionObservation(is_plant=True, is_clear=True, confidence_scores={"leaf_curl": 0.85})
    decision = await evon_service.reason(
        vision_obs=obs,
        transcript="dragon fruit meeda machalu vachayi",
        crop="dragon fruit",
        crop_age_days=180,
        state="Telangana",
        guide_chunks=[],
        language="te"
    )
    assert decision.tool_called == "escalate"
    assert "1800-180-1551" in decision.final_text
    assert "KVK" in decision.final_text


@pytest.mark.asyncio
async def test_evon_low_confidence_triggers_ask_more():
    """Edge Case: Top diagnosis confidence below 0.60 triggers ask_more."""
    obs = VisionObservation(
        is_plant=True,
        is_clear=True,
        confidence_scores={"leaf_curl": 0.45, "whitefly": 0.40}
    )
    chunks = [{"id": 1, "section": "Sucking Pests", "publisher": "PJTSAU", "source_title": "Chilli Guide", "page": 18, "text": "spray Diafenthiuron 50% WP @ 1.25 g per litre of water"}]
    decision = await evon_service.reason(
        vision_obs=obs,
        transcript="edho aindi",
        crop="chilli",
        crop_age_days=50,
        state="Telangana",
        guide_chunks=chunks,
        language="te"
    )
    assert decision.tool_called == "ask_more"

