# 🌾 Crop Doctor on WhatsApp - 60-Second Video Demo Script

This script is designed for a punchy, professional 60-second video presentation or pitch demonstration.

---

### **0:00 - 0:10 | The Problem (Pesticide Shop Counter)**
* **Visual:** Close-up of a pesticide dealer counter crowded with unbranded plastic bottles and chemical cans. A smallholder farmer looks uncertain, holding a withered leaf.
* **Voiceover (Mentor / Presenter):**
  > *"When a farmer spots curled leaves on chilli or brown spots on paddy, their only option is often the local pesticide shop—where dealers push whatever high-margin chemical is on the shelf, often at dangerous doses. Agriculture universities publish peer-reviewed packages of practices, but they sit buried in 200-page PDFs. Farmers don't need a PDF; they need an instant, trustworthy answer in their language on WhatsApp."*

---

### **0:10 - 0:30 | The Farmer Interaction (WhatsApp Web Simulator or Live WhatsApp)**
* **Visual:** Browser showing the **WhatsApp Web Simulator** at `http://localhost:8000/whatsapp` (or phone screen recording). The user selects a leaf photo showing upward curling and tiny whiteflies (`01_chilli_leaf_curl_whitefly.jpg`) along with a voice query in Telugu (or any of the 11 supported languages).
* **Audio (Telugu Voice Note plays):**
  > *`"Naa mirapa thotaki aravai rojulu, aakulu paiki muduchukupotunnayi, aakula kinda tella purugulu unnayi."`*
  *(Translation: "My chilli crop is 60 days old, leaves are curling upwards, and there are tiny white insects underneath.")*
* **Voiceover:**
  > *"The farmer sends a photo and speaks naturally in Telugu. Gnani Prisma STT transcribes the noisy farm audio, a neutral vision model identifies the upward curling and whitefly clusters, and our pgvector search retrieves the university guide from PJTSAU."*

---

### **0:30 - 0:45 | The Response (Timbre Voice Reply + Grounded Text)**
* **Visual:** In WhatsApp, *Crop Doctor* replies in less than 3 seconds with an audio voice note and a structured text card. The user taps play on the voice note.
* **Audio (Timbre Telugu Voice plays at 0.9x speed):**
  > *`"1. ప్రధాన సమస్య: తెల్ల దోమ మరియు ఆకు ముడత (Tella doma)..."`*
* **Visual on Text Card:**
  > **1. సమస్య:** తెల్ల దోమ మరియు ఆకు ముడత (Tella doma)  
  > **2. రసాయనం లేని రక్షణ:** ఎకరాకు 10-15 పసుపు రంగు జిగురు అట్టలు (Yellow sticky traps)  
  > **3. సిఫార్సు మందు:** Diafenthiuron 50% WP — మోతాదు: 1.25 గ్రాములు లీటరుకు (19 గ్రాములు 15 లీటర్ల స్ప్రే ట్యాంకుకు)  
  > **4. రక్షణ:** ముక్కుకు మాస్క్ మరియు చేతులకు గ్లౌజులు ధరించండి. గాలికి ఎదురుగా పిచికారీ చేయకండి.  
  > **ఆధారం:** PJTSAU మిరప సాగు మార్గదర్శిని, పేజీ 18
* **Voiceover:**
  > *"Gnani Timbre speaks the answer slowly, reading exact dosages per 15-litre knapsack pump. Notice: zero brand names—only official chemical formulations verbatim from the university."*

---

### **0:45 - 0:55 | Clinical Review & Safety Audit Dashboard**
* **Visual:** Screen switches to laptop browser showing `http://localhost:8000/reviews`.
* **Action:** Cursor clicks on *Case #case_01*. The split-screen shows the leaf photo, the transcribed audio, and the exact PJTSAU Page 18 passage highlighted in green side-by-side with the bot's response. A KVK scientist selects *“Correct”* and submits the audit.
* **Voiceover:**
  > *"Every case is audited on our web dashboard. Agriculture students and KVK scientists verify the exact cited passage and audit accuracy. If a chemical isn't quoted word-for-word in the guide, our guardrail blocks it instantly."*

---

### **0:55 - 1:00 | Safety & Guardrails (The Blurry Photo Test)**
* **Visual:** Quick cut back to WhatsApp. The user sends a blurry, out-of-focus photo (`16_blurry_leaf_photo.jpg`).
* **Visual on Bot Reply:**
  > *`"ఫోటో అస్పష్టంగా ఉంది. దయచేసి దెబ్బతిన్న ఒకే ఆకు పైభాగం మరియు వెనుక భాగం దగ్గరగా (close-up) స్పష్టంగా ఫోటో తీసి పంపండి."`*
* **Voiceover:**
  > *"If a photo is blurry, Crop Doctor never guesses—it asks for a closer shot or refers the farmer directly to their nearest KVK. Crop Doctor on WhatsApp: science-backed advice in the palm of every farmer's hand."*

---

### Key Presentation Talking Points (For Q&A)
1. **Safety First**: Zero hallucinated chemicals. If a quote does not match the university guide character-for-character, the system automatically escalates.
2. **Banned Inputs Shield**: Endosulfan, Monocrotophos, Paraquat, and Phorate are hardcoded into an interceptor gate.
3. **Pesticide Resistance Awareness**: Detects repeated sprays and stops farmers from spraying ineffective organophosphates repeatedly.
4. **Local Dialects**: Full native script support in Telugu, Marathi, and Punjabi with regional pest terminology (*Tella doma*, *Mava*, *Gulabi bond aali*, *Bhoore dhabbe*).

