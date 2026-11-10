"""
Comprehensive Agricultural University Crop Guides Dataset.
Sources:
1. PJTSAU (Prof. Jayashankar Telangana State Agricultural University) - Chilli
2. MPKV Rahuri (Mahatma Phule Krishi Vidyapeeth) - Cotton
3. PAU Ludhiana (Punjab Agricultural University) - Paddy (Rice)
4. Dr. YSRHU (Dr. Y.S.R. Horticultural University) / ICAR-IIHR - Tomato
"""

GUIDE_RECORDS = [
    # -------------------------------------------------------------------------
    # 1. CHILLI (PJTSAU Hyderabad - Telangana / Andhra Pradesh)
    # -------------------------------------------------------------------------
    {
        "source_title": "Chilli Production Technology and Plant Protection",
        "publisher": "PJTSAU Hyderabad",
        "state": "Telangana",
        "crop": "chilli",
        "section": "Sucking Pests - Whitefly (Bemisia tabaci) and Leaf Curl",
        "page": 18,
        "text": (
            "Whitefly nymphs and adults suck sap from the undersides of leaves, secreting honeydew which attracts "
            "sooty mould. More critically, whitefly acts as the insect vector transmitting the Chilli Leaf Curl Virus, "
            "causing severe upward leaf curling, puckering, stunted bush growth, and total yield loss if unmanaged. "
            "Non-chemical management: Erect yellow sticky traps @ 10-15 traps per acre at canopy level to monitor and trap whitefly adults. "
            "Spray 5% Neem Seed Kernel Extract (NSKE) or Neem oil 1500 ppm @ 5 ml per litre of water at early infestation. "
            "Chemical intervention: When pest intensity crosses ETL (5-8 whiteflies per leaf), spray Diafenthiuron 50% WP @ 1.25 g per litre of water "
            "(18.75 g to 19 g per 15-litre knapsack pump) or Acetamiprid 20% SP @ 0.2 g per litre of water (3 g per 15-litre pump). "
            "Safety: Spray during morning or evening hours with calm air. Wear protective gloves and face mask; never spray against wind. "
            "Waiting period (PHI): 15 days before harvesting green chillies."
        )
    },
    {
        "source_title": "Chilli Production Technology and Plant Protection",
        "publisher": "PJTSAU Hyderabad",
        "state": "Telangana",
        "crop": "chilli",
        "section": "Sucking Pests - Thrips (Scirtothrips dorsalis)",
        "page": 19,
        "text": (
            "Thrips lacerate the tender leaf surface and suck oozing sap, causing upward curling of leaf margins, "
            "boat-shaped leaf deformity, crinkling, and bronze or silvery discoloration on the ventral surface. "
            "Non-chemical management: Install blue sticky traps @ 10-15 per acre. Avoid excessive nitrogenous fertilizers. "
            "Chemical management: Spray Fipronil 5% SC @ 2 ml per litre of water (30 ml per 15-litre spray tank) or "
            "Spinosad 45% SC @ 0.3 ml per litre of water (4.5 ml per 15-litre spray tank). "
            "Safety: Alternate chemical groups to prevent rapid resistance buildup. Pre-harvest waiting period is 12 days."
        )
    },
    {
        "source_title": "Chilli Production Technology and Plant Protection",
        "publisher": "PJTSAU Hyderabad",
        "state": "Telangana",
        "crop": "chilli",
        "section": "Fungal Diseases - Anthracnose, Dieback and Fruit Rot (Colletotrichum capsici)",
        "page": 22,
        "text": (
            "Symptoms include dark brown sunken circular spots with concentric rings on ripe fruits, followed by dry rot. "
            "Twigs die back from the tip downward, with withered branches turning white with black dot-like acervuli. "
            "Non-chemical management: Use disease-free seeds; treat seed with Trichoderma viride @ 4 g/kg seed before nursery sowing. "
            "Destroy diseased crop debris and remove infected ripe pods promptly. "
            "Chemical management: Spray Azoxystrobin 23% SC @ 1 ml per litre of water (15 ml per 15-litre tank) or "
            "Difenoconazole 25% EC @ 0.5 ml per litre of water (7.5 ml per 15-litre tank) at 10-14 days intervals upon symptom onset. "
            "Safety: Wear full-body overalls and protective goggles during spraying. Waiting period: 10 days."
        )
    },
    {
        "source_title": "Chilli Production Technology and Plant Protection",
        "publisher": "PJTSAU Hyderabad",
        "state": "Telangana",
        "crop": "chilli",
        "section": "Soil-borne Diseases - Damping-off and Collar Rot (Pythium / Phytophthora)",
        "page": 25,
        "text": (
            "Water-soaked lesions develop at the collar region of young seedlings, leading to rotting, softening of tissues, "
            "and toppling over of seedlings in nurseries or freshly transplanted fields. "
            "Non-chemical management: Prepare raised nursery beds 15 cm high with proper drainage. Avoid stagnant water and overwatering. "
            "Chemical management: Drench the nursery bed and root zone with Copper Oxychloride 50% WP @ 3 g per litre of water "
            "(45 g per 15-litre can/pump) or Metalaxyl 8% + Mancozeb 64% WP @ 2 g per litre of water (30 g per 15-litre pump). "
            "Safety: Do not apply in direct midday sunshine. Keep livestock away from treated areas."
        )
    },

    # -------------------------------------------------------------------------
    # 2. COTTON (MPKV Rahuri / ICAR-CICR - Maharashtra)
    # -------------------------------------------------------------------------
    {
        "source_title": "Cotton Integrated Pest Management Advisory",
        "publisher": "MPKV Rahuri",
        "state": "Maharashtra",
        "crop": "cotton",
        "section": "Bollworms - Pink Bollworm (Pectinophora gossypiella)",
        "page": 24,
        "text": (
            "Pink bollworm larvae enter tender flower buds and squares, webbing the petals together to form characteristic 'rosette flowers' (Domkalya). "
            "Larvae bore into developing green bolls, feeding on developing seeds and staining the lint brown or yellow. "
            "Non-chemical management: Regularly collect and destroy rosette flowers and dropped squares. Install 5 pheromone traps per acre "
            "with Gossyplure lures for monitoring, and 8-10 traps per acre for mass trapping. "
            "Chemical intervention at ETL (8 moths/trap/night for 3 consecutive days or 10% damaged green bolls): "
            "Spray Profenophos 50% EC @ 2 ml per litre of water (30 ml per 15-litre knapsack pump) or "
            "Emamectin Benzoate 5% SG @ 0.4 g per litre of water (6 g per 15-litre pump). "
            "Safety: Do not spray synthetic pyrethroids repeatedly as they induce resurgence of sucking pests. PHI: 30 days."
        )
    },
    {
        "source_title": "Cotton Integrated Pest Management Advisory",
        "publisher": "MPKV Rahuri",
        "state": "Maharashtra",
        "crop": "cotton",
        "section": "Sucking Pests - Aphids (Aphis gossypii) and Resistance Management",
        "page": 31,
        "text": (
            "Aphids (Mava) colonize the lower surface of tender leaves and shoots, sucking sap and causing downward leaf cupping. "
            "They excrete sweet honeydew leading to black sooty mold fungus on lower foliage. "
            "Resistance warning: Repeated sprays of organophosphates or synthetic pyrethroids trigger rapid pesticide resistance. "
            "Non-chemical management: Stop indiscriminate chemical spraying immediately. Spray 5% Neem Seed Kernel Extract (NSKE) @ 50 g/L "
            "or conserve natural predators like ladybird beetles and chrysoperla. "
            "Chemical management: If aphid population exceeds 15-20% affected plants, spray Flonicamid 50 WG @ 0.3 g per litre of water "
            "(4.5 g per 15-litre spray tank) or Dinotefuran 20% SG @ 0.3 g per litre of water (4.5 g per 15-litre tank). "
            "Safety: Ensure thorough coverage of lower leaf surface using hollow cone nozzle. PHI: 25 days."
        )
    },
    {
        "source_title": "Cotton Integrated Pest Management Advisory",
        "publisher": "MPKV Rahuri",
        "state": "Maharashtra",
        "crop": "cotton",
        "section": "Fungal Diseases - Grey Mildew / Dahiya Disease (Ramularia areola)",
        "page": 37,
        "text": (
            "Characterized by irregular angular pale green or yellowish spots on upper leaf surfaces, with frosty white, powdery "
            "fungal sporulation on the lower surface resembling a drenching of curd (Dahiya). Leaves turn prematurely brown and shed. "
            "Non-chemical management: Ensure wider plant spacing to allow sun penetration and air circulation. Remove lower old infected leaves. "
            "Chemical management: Spray Wettable Sulphur 80% WP @ 3 g per litre of water (45 g per 15-litre pump) or "
            "Kresoxim-methyl 44.3% SC @ 1 ml per litre of water (15 ml per 15-litre pump). "
            "Safety: Do not spray wettable sulphur when ambient temperature exceeds 35 degrees Celsius to prevent phytotoxicity."
        )
    },

    # -------------------------------------------------------------------------
    # 3. PADDY / RICE (PAU Ludhiana - Punjab)
    # -------------------------------------------------------------------------
    {
        "source_title": "Package of Practices for Kharif Crops - Rice",
        "publisher": "PAU Ludhiana",
        "state": "Punjab",
        "crop": "paddy",
        "section": "Fungal Diseases - Brown Spot (Bipolaris oryzae / Helminthosporium)",
        "page": 42,
        "text": (
            "Brown spot produces numerous circular to oval brown spots with a yellow halo resembling sesame seeds on leaf blades and glumes. "
            "Severely diseased leaves turn yellow, dry up, and seedlings/tillers become severely blighted, especially under potash deficiency. "
            "Non-chemical management: Ensure balanced fertilizer application; avoid excessive nitrogen and rectify potassium deficiency in sandy loam soils. "
            "Drain stagnant water and provide fresh irrigation. "
            "Chemical management: Spray Propiconazole 25% EC @ 1 ml per litre of water (15 ml per 15-litre spray pump) or "
            "Tebuconazole 50% + Trifloxystrobin 25% WG (Nativo) @ 0.4 g per litre of water (6 g per 15-litre pump). "
            "Safety: Always wear protective rubber gloves and mask. Avoid skin and eye contact. Waiting period: 30 days before harvest."
        )
    },
    {
        "source_title": "Package of Practices for Kharif Crops - Rice",
        "publisher": "PAU Ludhiana",
        "state": "Punjab",
        "crop": "paddy",
        "section": "Fungal Diseases - Rice Blast (Magnaporthe grisea)",
        "page": 45,
        "text": (
            "Blast produces spindle-shaped lesions on leaves with pointed ends, greyish centres, and dark brown margins. "
            "At heading stage, neck blast rots the panicle base turning it black, causing chaffy panicles that snap and break. "
            "Non-chemical management: Refrain from applying nitrogen in split doses during cloudy and humid weather. "
            "Chemical management: At early symptom detection, spray Tricyclazole 75% WP @ 0.6 g per litre of water "
            "(9 g per 15-litre spray tank) or Isoprothiolane 40% EC @ 1.5 ml per litre of water (22.5 ml per 15-litre spray pump). "
            "Safety: Spray during morning hours before strong winds develop. Waiting period (PHI): 30 days."
        )
    },
    {
        "source_title": "Package of Practices for Kharif Crops - Rice",
        "publisher": "PAU Ludhiana",
        "state": "Punjab",
        "crop": "paddy",
        "section": "Insect Pests - Planthoppers and Sucking Pests (BPH / WBPH / Tela)",
        "page": 49,
        "text": (
            "Brown planthopper and white-backed planthopper (Tela) congregate in colonies at the basal stem region just above water level. "
            "They suck sap causing tillers to turn yellow and dry up rapidly into circular scorched patches known as 'hopper burn'. "
            "Non-chemical management: Create alley pathways (30 cm paths every 2-3 meters) to let sunlight and air into the canopy. "
            "Drain flood water from the field for 2-3 days to disturb nymphal colonies. "
            "Chemical management: When population exceeds 5-10 hoppers per hill, direct the spray nozzle toward the base of plants. "
            "Spray Pymetrozine 50% WDG @ 0.6 g per litre of water (9 g per 15-litre pump) or Triflumezopyrim 10% SC @ 0.5 ml per litre of water "
            "(7.5 ml per 15-litre pump). Avoid spraying upper leaf tips as hoppers dwell at plant base. PHI: 21 days."
        )
    },

    # -------------------------------------------------------------------------
    # 4. TOMATO (Dr. YSRHU Andhra Pradesh / ICAR-IIHR)
    # -------------------------------------------------------------------------
    {
        "source_title": "Package of Practices for Commercial Vegetable Crops - Tomato",
        "publisher": "Dr. YSRHU",
        "state": "Andhra Pradesh",
        "crop": "tomato",
        "section": "Nutritional Disorders - Nitrogen and Calcium Deficiencies",
        "page": 12,
        "text": (
            "Nitrogen deficiency causes uniform pale yellowing (chlorosis) beginning on older lower leaves, while upper young leaves remain smaller and pale green. "
            "Stems become thin, fibrous, and growth slows down significantly without any fungal spots or necrotic rings. "
            "Calcium deficiency produces 'Blossom End Rot' where the distal blossom end of green fruits develops water-soaked dark sunken leathery rot. "
            "Non-chemical management: Do NOT apply chemical pesticides or fungicides for physiological disorders. "
            "Incorporate well-rotted farmyard manure (FYM) or vermicompost into the root zone and maintain uniform soil moisture without water stress. "
            "Foliar correction: For nitrogen chlorosis, apply foliar spray of 1% Urea (10 g per litre of water, or 150 g per 15-litre spray tank). "
            "For calcium deficiency, spray Calcium Nitrate @ 5 g per litre of water (75 g per 15-litre spray tank). "
            "Safety: Spray during morning or evening when temperatures are below 30 deg C to avoid leaf scorch. No waiting period required."
        )
    },
    {
        "source_title": "Package of Practices for Commercial Vegetable Crops - Tomato",
        "publisher": "Dr. YSRHU",
        "state": "Andhra Pradesh",
        "crop": "tomato",
        "section": "Fungal Diseases - Early Blight and Late Blight (Alternaria / Phytophthora)",
        "page": 16,
        "text": (
            "Early blight causes brown to dark brown circular spots with distinctive concentric target boards on leaves, stems, and fruits. "
            "Late blight produces rapid water-soaked greenish-black lesions that rot leaves and green fruits quickly in cool humid conditions with white mold on leaf underside. "
            "Non-chemical management: Stake tomato plants to keep foliage off wet soil. Avoid overhead sprinkler irrigation. Remove infected lower leaves promptly. "
            "Chemical management: For early blight, spray Mancozeb 75% WP @ 2.5 g per litre of water (37.5 g per 15-litre pump) or "
            "Difenoconazole 25% EC @ 0.5 ml per litre of water (7.5 ml per 15-litre pump). "
            "For late blight, spray Cymoxanil 8% + Mancozeb 64% WP @ 2 g per litre of water (30 g per 15-litre tank). "
            "Safety: Wear protective mask and gloves; wash equipment thoroughly. Waiting period (PHI): 7 days."
        )
    },
    {
        "source_title": "Package of Practices for Commercial Vegetable Crops - Tomato",
        "publisher": "Dr. YSRHU",
        "state": "Andhra Pradesh",
        "crop": "tomato",
        "section": "Viral Diseases - Tomato Leaf Curl Virus (ToLCV transmitted by Whitefly)",
        "page": 20,
        "text": (
            "Infected plants show severe downward and upward curling of leaflets, thick puckering, yellowing of interveinal areas, and severe stunting. "
            "Plants infected early produce no marketable fruit. Transmitted solely by the whitefly vector (Bemisia tabaci). "
            "Non-chemical management: Raise tomato seedlings under 40-mesh nylon insect-proof net in nursery. Install 15 yellow sticky traps per acre. "
            "Rogue out and bury virus-infected plants immediately to eliminate field inoculum. "
            "Chemical management: Control whitefly vectors by spraying Acetamiprid 20% SP @ 0.25 g per litre of water (3.75 g per 15-litre tank) or "
            "Spiromesifen 22.9% SC @ 1 ml per litre of water (15 ml per 15-litre tank). "
            "Safety: Do not apply insecticides during heavy flowering to safeguard honeybee pollinators. Waiting period: 10 days."
        )
    }
]

