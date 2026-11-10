import pytest
from pathlib import Path
from app.services.vision import vision_service

TEST_DIR = Path("storage/test_leaves")


@pytest.mark.asyncio
async def test_vision_leaf_curl_whitefly():
    """Verify chilli leaf curl and whiteflies are detected neutrally."""
    img_path = TEST_DIR / "01_chilli_leaf_curl_whitefly.jpg"
    obs = await vision_service.analyze_image(str(img_path))

    assert obs.is_plant is True
    assert obs.is_clear is True
    assert "upward" in obs.curling.lower() or "curl" in obs.curling.lower()
    assert "white" in obs.insects_visible.lower()
    assert obs.confidence_scores.get("leaf_curl", 0) > 0.8


@pytest.mark.asyncio
async def test_vision_pink_bollworm():
    """Verify cotton pink bollworm damage traits."""
    img_path = TEST_DIR / "05_cotton_pink_bollworm.jpg"
    obs = await vision_service.analyze_image(str(img_path))

    assert obs.is_plant is True
    assert obs.is_clear is True
    assert "bore" in obs.spots.lower() or "hole" in obs.spots.lower() or "rosette" in obs.spots.lower()
    assert "pink" in obs.insects_visible.lower() or "larva" in obs.insects_visible.lower()
    assert obs.confidence_scores.get("pink_bollworm", 0) > 0.85


@pytest.mark.asyncio
async def test_vision_paddy_brown_spot():
    """Verify paddy brown spot sesame-seed-like lesions with halo."""
    img_path = TEST_DIR / "08_paddy_brown_spot.jpg"
    obs = await vision_service.analyze_image(str(img_path))

    assert obs.is_plant is True
    assert obs.is_clear is True
    assert "brown" in obs.spots.lower()
    assert "halo" in obs.spots.lower() or "halo" in obs.pattern_on_leaf.lower()
    assert obs.confidence_scores.get("brown_spot", 0) > 0.85


@pytest.mark.asyncio
async def test_vision_nitrogen_yellowing_no_spots():
    """Verify physiological nitrogen chlorosis without lesions."""
    img_path = TEST_DIR / "11_tomato_nitrogen_yellowing.jpg"
    obs = await vision_service.analyze_image(str(img_path))

    assert obs.is_plant is True
    assert obs.is_clear is True
    assert "none" in obs.spots.lower() or "no fungal" in obs.spots.lower()
    assert "yellow" in obs.colour.lower()
    assert obs.confidence_scores.get("nitrogen_deficiency", 0) > 0.8


@pytest.mark.asyncio
async def test_vision_blurry_leaf_rejection():
    """Verify blurry photo triggers is_clear=False for ask_more flow."""
    img_path = TEST_DIR / "16_blurry_leaf_photo.jpg"
    obs = await vision_service.analyze_image(str(img_path))

    assert obs.is_clear is False
    assert obs.confidence_scores.get("unclear", 0) > 0.9


@pytest.mark.asyncio
async def test_vision_distance_field_rejection():
    """Verify distant field photo triggers is_clear=False."""
    img_path = TEST_DIR / "17_distance_field_landscape.jpg"
    obs = await vision_service.analyze_image(str(img_path))

    assert obs.is_clear is False
    assert obs.confidence_scores.get("unclear", 0) > 0.9


@pytest.mark.asyncio
async def test_vision_non_plant_rejection():
    """Verify non-plant object (bottle/shoe) triggers is_plant=False."""
    bottle_path = TEST_DIR / "18_non_plant_pesticide_bottle.jpg"
    obs = await vision_service.analyze_image(str(bottle_path))

    assert obs.is_plant is False


@pytest.mark.asyncio
async def test_vision_healthy_leaf():
    """Verify clean leaf has high healthy confidence and no disease traits."""
    healthy_path = TEST_DIR / "20_healthy_green_leaf.jpg"
    obs = await vision_service.analyze_image(str(healthy_path))

    assert obs.is_plant is True
    assert obs.is_clear is True
    assert "none" in obs.spots.lower()
    assert "none" in obs.curling.lower()
    assert obs.confidence_scores.get("healthy", 0) > 0.9

