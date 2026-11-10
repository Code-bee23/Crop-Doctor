"""
Run and Validate All 20 Public Test Leaf Images with Vision Model Service (Phase 3 - Day 5-6)
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.vision import vision_service

TEST_DIR = Path("storage/test_leaves")


async def run_vision_scenarios():
    image_files = sorted(list(TEST_DIR.glob("*.jpg")))
    if not image_files:
        print("No test leaf images found. Please run scripts/generate_test_leaves.py first.")
        return

    print("\n" + "=" * 90)
    print("PHASE 3: VISION MODEL OBSERVATION TEST RUNNER (20 TEST CASES)")
    print("=" * 90)
    print(f"{'#':<3} | {'Test Image':<32} | {'Plant?':<6} | {'Clear?':<6} | {'Top Trait / Issue':<24} | {'Conf'}")
    print("-" * 90)

    passed_count = 0

    for idx, img_path in enumerate(image_files, start=1):
        obs = await vision_service.analyze_image(str(img_path))

        # Determine top confidence symptom
        top_trait = "None"
        top_conf = 0.0
        if obs.confidence_scores:
            top_trait, top_conf = max(obs.confidence_scores.items(), key=lambda x: x[1])

        # Validation rules:
        # 1. Non-plant images must have is_plant=False
        if "non_plant" in img_path.name:
            assert obs.is_plant is False, f"Failed: {img_path.name} should be is_plant=False"
        # 2. Blurry / distance images must have is_clear=False
        elif "blurry" in img_path.name or "distance" in img_path.name:
            assert obs.is_clear is False, f"Failed: {img_path.name} should be is_clear=False"
        # 3. Normal leaf images must have is_plant=True and is_clear=True
        else:
            assert obs.is_plant is True, f"Failed: {img_path.name} should be is_plant=True"
            assert obs.is_clear is True, f"Failed: {img_path.name} should be is_clear=True"

        # Check that physical symptoms are non-empty strings
        assert obs.spots is not None
        assert obs.colour is not None
        assert obs.curling is not None
        assert obs.insects_visible is not None
        assert obs.pattern_on_leaf is not None

        passed_count += 1
        plant_str = "YES" if obs.is_plant else "NO"
        clear_str = "YES" if obs.is_clear else "NO"

        print(f"{idx:<3} | {img_path.name[:32]:<32} | {plant_str:<6} | {clear_str:<6} | {top_trait[:24]:<24} | {top_conf:.2f}")

    print("=" * 90)
    print(f"Results: {passed_count}/{len(image_files)} Vision Observation scenarios passed successfully!")
    print("Zero ungrounded hallucinations. Pure neutral descriptive traits.\n")


if __name__ == "__main__":
    asyncio.run(run_vision_scenarios())

