import pytest
from app.services.retriever import guide_retriever
from guides.data import GUIDE_RECORDS


def test_guides_dataset_integrity():
    """Verify all 13 guide records have valid metadata, text, and page numbers."""
    assert len(GUIDE_RECORDS) == 13
    crops = {g["crop"] for g in GUIDE_RECORDS}
    assert crops == {"chilli", "cotton", "paddy", "tomato"}

    for g in GUIDE_RECORDS:
        assert len(g["source_title"]) > 5
        assert len(g["publisher"]) > 3
        assert g["page"] > 0
        assert len(g["text"]) > 50
        # Ensure dosages or units exist
        assert ("litre" in g["text"] or "tank" in g["text"] or "g/kg" in g["text"])


@pytest.mark.asyncio
async def test_retriever_chilli_whitefly():
    """Telugu Chilli leaf curl with whiteflies retrieves PJTSAU whitefly guide."""
    results = await guide_retriever.search(
        query="aakulu paiki muduchukupotunnayi tella purugulu whitefly leaf curl",
        crop="chilli",
        state="Telangana",
        top_k=2
    )
    assert len(results) > 0
    top = results[0]
    assert top["crop"] == "chilli"
    assert "Whitefly" in top["section"] or "Leaf Curl" in top["section"]
    assert "PJTSAU" in top["publisher"]
    assert "Diafenthiuron" in top["text"]
    assert "1.25 g per litre" in top["text"]


@pytest.mark.asyncio
async def test_retriever_cotton_pink_bollworm():
    """Marathi Cotton pink bollworm query retrieves MPKV Rahuri pink bollworm guide."""
    results = await guide_retriever.search(
        query="bondat gulabi aali rosette flowers pink bollworm",
        crop="cotton",
        state="Maharashtra",
        top_k=2
    )
    assert len(results) > 0
    top = results[0]
    assert top["crop"] == "cotton"
    assert "Pink Bollworm" in top["section"]
    assert "MPKV" in top["publisher"]
    assert "Profenophos 50% EC" in top["text"]
    assert "2 ml per litre" in top["text"]


@pytest.mark.asyncio
async def test_retriever_paddy_brown_spot():
    """Punjabi Paddy brown spot query retrieves PAU Ludhiana brown spot guide."""
    results = await guide_retriever.search(
        query="pattean te bhoore dhabbe brown spot oval spots",
        crop="paddy",
        state="Punjab",
        top_k=2
    )
    assert len(results) > 0
    top = results[0]
    assert top["crop"] == "paddy"
    assert "Brown Spot" in top["section"]
    assert "PAU" in top["publisher"]
    assert "Propiconazole" in top["text"]


@pytest.mark.asyncio
async def test_retriever_tomato_nutrient_deficiency():
    """Andhra Pradesh Tomato pale yellowing retrieves Dr. YSRHU nitrogen deficiency guide."""
    results = await guide_retriever.search(
        query="tomato aakulu pasupu ga yellowing older leaves chlorosis nitrogen",
        crop="tomato",
        state="Andhra Pradesh",
        top_k=2
    )
    assert len(results) > 0
    top = results[0]
    assert top["crop"] == "tomato"
    assert "Nitrogen" in top["section"] or "Nutritional" in top["section"]
    assert "Dr. YSRHU" in top["publisher"]
    assert "1% Urea" in top["text"]


@pytest.mark.asyncio
async def test_crop_filter_isolation():
    """Verify crop filter strictly isolates other crops."""
    results = await guide_retriever.search(
        query="curling insects spots pest",
        crop="cotton",
        state=None,
        top_k=6
    )
    assert len(results) > 0
    for r in results:
        assert r["crop"] == "cotton"


@pytest.mark.asyncio
async def test_tank_and_per_litre_doses_present():
    """Verify that chunks specify both per-litre and 15-litre spray tank dosages."""
    results = await guide_retriever.search(
        query="spray management",
        crop="chilli",
        state="Telangana",
        top_k=4
    )
    assert len(results) > 0
    has_tank_dose = any("15-litre" in r["text"] for r in results)
    assert has_tank_dose is True

