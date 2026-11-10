"""
Generate 20 Realistic Public Test Leaf Images & Metadata Sidecars (Phase 3 - Day 5-6)
Uses Pillow to create valid JPEG images with corresponding sidecar JSON files.
"""

import json
from pathlib import Path
from PIL import Image, ImageDraw

OUTPUT_DIR = Path("storage/test_leaves")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCENARIOS = [
    {
        "filename": "01_chilli_leaf_curl_whitefly.jpg",
        "bg_color": (160, 200, 130),
        "label": "Chilli Leaf Curl & Whitefly",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "none",
            "colour": "pale greenish yellow margin",
            "curling": "severe upward curling of leaf margins with puckering",
            "insects_visible": "tiny white winged insects (whiteflies) clustered on leaf underside",
            "pattern_on_leaf": "interveinal puckering and upward cup shape",
            "confidence_scores": {"leaf_curl": 0.89, "whitefly": 0.86}
        }
    },
    {
        "filename": "02_chilli_thrips_damage.jpg",
        "bg_color": (180, 190, 120),
        "label": "Chilli Thrips Damage",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "bronze and silvery streaks on lower surface",
            "colour": "bronze discolored underside",
            "curling": "boat-shaped upward curling of leaf margins",
            "insects_visible": "minute slender yellowish insects",
            "pattern_on_leaf": "lacerated rasped surface along veins",
            "confidence_scores": {"thrips": 0.87, "leaf_curl": 0.72}
        }
    },
    {
        "filename": "03_chilli_anthracnose_fruit_rot.jpg",
        "bg_color": (150, 75, 40),
        "label": "Chilli Anthracnose Fruit Rot",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "dark brown sunken circular lesions with concentric rings and black dots",
            "colour": "straw-coloured bleached necrotic fruit tissue",
            "curling": "dieback on adjacent twigs",
            "insects_visible": "none",
            "pattern_on_leaf": "circular necrotic targets on pods and foliage",
            "confidence_scores": {"anthracnose": 0.91}
        }
    },
    {
        "filename": "04_chilli_damping_off.jpg",
        "bg_color": (90, 120, 80),
        "label": "Chilli Damping Off",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "water-soaked soft brown lesion at collar region near soil line",
            "colour": "pale dull green wilting foliage",
            "curling": "toppled stem base",
            "insects_visible": "none",
            "pattern_on_leaf": "flaccid collapsed seedling",
            "confidence_scores": {"damping_off": 0.89}
        }
    },
    {
        "filename": "05_cotton_pink_bollworm.jpg",
        "bg_color": (140, 170, 110),
        "label": "Cotton Pink Bollworm",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "small bore entry holes plugged with excreta on green boll, rosette flower petals",
            "colour": "brownish staining inside boll",
            "curling": "webbed rosette flower buds",
            "insects_visible": "pinkish caterpillar larva inside locule feeding on seeds",
            "pattern_on_leaf": "damage localized on fruiting bolls and squares",
            "confidence_scores": {"pink_bollworm": 0.93}
        }
    },
    {
        "filename": "06_cotton_aphids_infestation.jpg",
        "bg_color": (110, 150, 90),
        "label": "Cotton Aphids (Mava)",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "black sooty mould patches over sticky sheen",
            "colour": "yellowish chlorotic leaf margin",
            "curling": "severe downward cupping and crinkling of leaves",
            "insects_visible": "dense colonies of tiny greenish-black soft-bodied aphids on leaf underside",
            "pattern_on_leaf": "honeydew accumulation coated with black mould",
            "confidence_scores": {"aphids": 0.92}
        }
    },
    {
        "filename": "07_cotton_grey_mildew_dahiya.jpg",
        "bg_color": (130, 160, 120),
        "label": "Cotton Grey Mildew (Dahiya)",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "angular pale translucent spots bounded by veinlets",
            "colour": "frosty white powdery sporulation on lower leaf surface",
            "curling": "premature curling and crisp drying of leaf",
            "insects_visible": "none",
            "pattern_on_leaf": "checkerboard angular patches resembling curd splash",
            "confidence_scores": {"grey_mildew": 0.88}
        }
    },
    {
        "filename": "08_paddy_brown_spot.jpg",
        "bg_color": (120, 170, 90),
        "label": "Paddy Brown Spot",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "numerous circular to oval dark brown spots with prominent yellow halo",
            "colour": "yellowing leaf blade surrounding spots",
            "curling": "none",
            "insects_visible": "none",
            "pattern_on_leaf": "sesame-seed-like lesions scattered uniformly across leaf blade",
            "confidence_scores": {"brown_spot": 0.90}
        }
    },
    {
        "filename": "09_paddy_rice_blast.jpg",
        "bg_color": (100, 160, 80),
        "label": "Paddy Rice Blast",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "spindle-shaped lesions with pointed ends, grey centres, and dark brown margins",
            "colour": "pale grey centre surrounded by reddish brown border",
            "curling": "none",
            "insects_visible": "none",
            "pattern_on_leaf": "eye-shaped blast lesions coalescing into large irregular patches",
            "confidence_scores": {"blast": 0.91}
        }
    },
    {
        "filename": "10_paddy_planthopper_burn.jpg",
        "bg_color": (160, 150, 70),
        "label": "Paddy Planthopper Burn",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "scorched brown dried patches",
            "colour": "drying yellow-brown straw appearance (hopper burn)",
            "curling": "tillers drying and lodging",
            "insects_visible": "brown/white-backed planthoppers congregated at base of hill",
            "pattern_on_leaf": "circular drying patches spreading outwards",
            "confidence_scores": {"planthoppers": 0.88, "hopper_burn": 0.86}
        }
    },
    {
        "filename": "11_tomato_nitrogen_yellowing.jpg",
        "bg_color": (175, 195, 110),
        "label": "Tomato Nitrogen Yellowing",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "none (no fungal or bacterial lesions)",
            "colour": "uniform pale yellowing chlorosis on older lower leaves",
            "curling": "none",
            "insects_visible": "none",
            "pattern_on_leaf": "generalized leaf blade chlorosis with pale veins and thin petioles",
            "confidence_scores": {"nitrogen_deficiency": 0.89}
        }
    },
    {
        "filename": "12_tomato_calcium_blossom_rot.jpg",
        "bg_color": (190, 80, 50),
        "label": "Tomato Blossom End Rot",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "water-soaked sunken dark leathery black spot at the blossom end of green fruit",
            "colour": "black sunken leathery depression on distal fruit end",
            "curling": "none on leaves",
            "insects_visible": "none",
            "pattern_on_leaf": "confined to blossom end of developing fruit",
            "confidence_scores": {"calcium_deficiency": 0.92, "blossom_end_rot": 0.94}
        }
    },
    {
        "filename": "13_tomato_early_blight.jpg",
        "bg_color": (130, 160, 90),
        "label": "Tomato Early Blight",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "brown to dark brown concentric rings forming target-board pattern on leaves",
            "colour": "chlorotic yellow halo around dark circular spots",
            "curling": "senescing leaf tips",
            "insects_visible": "none",
            "pattern_on_leaf": "concentric ring targets on lower canopy leaves",
            "confidence_scores": {"early_blight": 0.89}
        }
    },
    {
        "filename": "14_tomato_late_blight.jpg",
        "bg_color": (95, 130, 85),
        "label": "Tomato Late Blight",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "large irregular water-soaked dark greenish-black oily lesions on foliage and stems",
            "colour": "purplish-black rapid blighting with delicate white fungal down on lower surface",
            "curling": "rapid rotting and wilting of affected shoots",
            "insects_visible": "none",
            "pattern_on_leaf": "water-soaked rapidly expanding blotches",
            "confidence_scores": {"late_blight": 0.91}
        }
    },
    {
        "filename": "15_tomato_leaf_curl_tolcv.jpg",
        "bg_color": (155, 190, 105),
        "label": "Tomato Leaf Curl (ToLCV)",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "none",
            "colour": "interveinal chlorosis with pale yellowish borders",
            "curling": "severe upward and downward curling, thick puckering, stunted bushy foliage",
            "insects_visible": "whitefly adults fluttering near growing tips",
            "pattern_on_leaf": "thickened leathery crinkled leaves with shortened internodes",
            "confidence_scores": {"leaf_curl": 0.92, "whitefly": 0.85}
        }
    },
    {
        "filename": "16_blurry_leaf_photo.jpg",
        "bg_color": (110, 130, 90),
        "label": "Blurry Out of Focus Leaf",
        "observation": {
            "is_plant": True,
            "is_clear": False,
            "spots": "blurred indistinct smudge",
            "colour": "greenish blur",
            "curling": "cannot determine due to motion blur",
            "insects_visible": "none visible",
            "pattern_on_leaf": "camera focus failed; leaf venation and margins blurred",
            "confidence_scores": {"unclear": 0.95}
        }
    },
    {
        "filename": "17_distance_field_landscape.jpg",
        "bg_color": (80, 140, 70),
        "label": "Distant Field Landscape",
        "observation": {
            "is_plant": True,
            "is_clear": False,
            "spots": "cannot resolve leaf surface from distance",
            "colour": "panoramic view of field canopy",
            "curling": "cannot resolve individual leaves",
            "insects_visible": "none visible from distance",
            "pattern_on_leaf": "wide landscape shot; individual plant symptoms cannot be diagnosed",
            "confidence_scores": {"unclear": 0.96}
        }
    },
    {
        "filename": "18_non_plant_pesticide_bottle.jpg",
        "bg_color": (220, 220, 220),
        "label": "Non Plant - Pesticide Bottle",
        "observation": {
            "is_plant": False,
            "is_clear": True,
            "spots": "none (plastic container)",
            "colour": "commercial bottle label and cap",
            "curling": "none",
            "insects_visible": "none",
            "pattern_on_leaf": "not a plant specimen; image shows an input container",
            "confidence_scores": {"unclear": 0.99}
        }
    },
    {
        "filename": "19_non_plant_tractor_wheel.jpg",
        "bg_color": (90, 75, 60),
        "label": "Non Plant - Tractor Wheel in Mud",
        "observation": {
            "is_plant": False,
            "is_clear": True,
            "spots": "none (rubber tread pattern and wet soil)",
            "colour": "black rubber and dark brown mud",
            "curling": "none",
            "insects_visible": "none",
            "pattern_on_leaf": "not a crop leaf; photo shows farm equipment",
            "confidence_scores": {"unclear": 0.99}
        }
    },
    {
        "filename": "20_healthy_green_leaf.jpg",
        "bg_color": (50, 160, 50),
        "label": "Healthy Green Leaf",
        "observation": {
            "is_plant": True,
            "is_clear": True,
            "spots": "none (no fungal, bacterial, or necrotic lesions)",
            "colour": "deep uniform dark green",
            "curling": "none (smooth natural flat blade)",
            "insects_visible": "none",
            "pattern_on_leaf": "clean healthy tissue with normal venation and turgidity",
            "confidence_scores": {"healthy": 0.95}
        }
    }
]


def generate_images():
    print(f"Generating {len(SCENARIOS)} test leaf images in {OUTPUT_DIR.resolve()}...")

    for item in SCENARIOS:
        img_path = OUTPUT_DIR / item["filename"]
        json_path = OUTPUT_DIR / item["filename"].replace(".jpg", ".json")

        # 1. Create 600x600 image with distinct visual representation
        img = Image.new("RGB", (600, 600), color=item["bg_color"])
        draw = ImageDraw.Draw(img)

        # Draw decorative leaf/object representation
        if "blurry" in item["filename"]:
            # Draw fuzzy lines
            for i in range(10, 590, 15):
                draw.line([(i, 0), (i, 600)], fill=(120, 140, 100), width=4)
        elif "non_plant" in item["filename"]:
            # Draw box/circle
            draw.rectangle([150, 150, 450, 450], outline=(40, 40, 40), width=6)
        else:
            # Draw leaf outline shape
            draw.polygon([(300, 80), (450, 280), (380, 500), (300, 540), (220, 500), (150, 280)], outline=(30, 90, 30), width=5)
            # Draw main vein
            draw.line([(300, 80), (300, 540)], fill=(30, 90, 30), width=4)

        # Draw banner text
        draw.rectangle([20, 20, 580, 70], fill=(20, 20, 20))
        draw.text((35, 35), f"[TEST LEAF] {item['label']}", fill=(255, 255, 255))

        # Save JPEG
        img.save(img_path, format="JPEG", quality=90)

        # Save sidecar JSON observation
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(item["observation"], f, indent=2)

    print(f"Successfully generated all {len(SCENARIOS)} images and sidecars!")


if __name__ == "__main__":
    generate_images()

