import os
import time
import json
from google import genai
from dotenv import load_dotenv

# 1. API Key laden
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    print("❌ FEHLER: Kein API Key gefunden! Prüfe deine .env Datei.")
    exit()

# --- KONFIGURATION ---
OUTPUT_FOLDER = "NanoBilder_Batch"
NUMBER_OF_IMAGES = 100
MODEL_ID = "gemini-3-pro-image-preview"

# --- HILFSFUNKTIONEN ---
def generate_theme(client, user_input=None):
    """Lässt Gemini ein kreatives Thema entwickeln."""
    print("🧠 Gemini überlegt sich ein Thema für die Kollektion...")
    
    base_instruction = "You are a creative director for a digital art shop on Etsy selling 'Junk Journal' background papers."
    
    if user_input and user_input.strip():
        prompt = f"""{base_instruction}
The user has suggested: "{user_input}".
Based on this, define a specific, catchy, and commercially viable 'Collection Theme' name and a brief description.
Output ONLY the Theme Name and Description in one line.
Example: 'Vintage Beekeeper: A nostalgic collection of honeycomb patterns, vintage bee illustrations, and aged paper textures.'"""
    else:
        prompt = f"""{base_instruction}
Brainstorm a unique, high-potential, and specific 'Collection Theme' for a new set of background papers.
It should be distinct from generic themes. Think about niches like 'Steampunk Alice in Wonderland', 'Dark Academia Botany', 'Celestial Navigation', 'Victorian Gothic', 'Cottagecore Herbarium'.
Output ONLY the Theme Name and Description in one line."""

    response = client.models.generate_content(
        model='gemini-2.0-flash-exp',
        contents=prompt
    )
    theme = response.text.strip()
    print(f"✨ Gewähltes Thema: {theme}")
    return theme

def generate_prompts_with_gemini(client, theme, count):
    """Nutzt Gemini, um kreative Prompt-Variationen für das Thema zu generieren."""
    print(f"🤖 Generiere {count} Prompts für das Thema...")
    
    generation_prompt = f"""Act as an expert AI art prompter.
Target Audience: Etsy customers looking for "Junk Journal Background Pages".
Collection Theme: "{theme}"

Task: Generate {count} HIGHLY DETAILED and UNIQUE image generation prompts for this collection.

Requirements:
1. **Variety**: Ensure a mix of:
   - Full page patterns (seamless or distressed)
   - Collage-style compositions (ephemera, torn paper, stamps)
   - Focal point artistic illustrations with textured backgrounds
   - Macro textures (aged paper, fabric, lace)
2. **Aesthetics**: All images must look "Vintage", "Textured", "Distressed", and "High Quality".
3. **Format**: Output ONLY the prompts, one per line. No numbering, no bullet points.
4. **Content**: Each prompt must be a full, descriptive sentence.

Example Prompt Style:
"Aged parchment paper background featuring faded botanical illustrations of ferns and mushrooms, overlaid with vintage handwriting and coffee stains, high resolution, junk journal style."

Generate exactly {count} prompts now."""

    response = client.models.generate_content(
        model='gemini-2.0-flash-exp',
        contents=generation_prompt
    )
    
    # Parse die generierten Prompts
    generated_text = response.text
    lines = generated_text.strip().split('\n')
    prompts = []
    
    import re
    for line in lines:
        cleaned = line.strip()
        # Entferne Nummerierung (1. , 1), Bullets (*, -)
        cleaned = re.sub(r'^[\d\.\-\*\s]+', '', cleaned)
        
        if cleaned:
            prompts.append(cleaned)
    
    print(f"✅ {len(prompts)} Prompts generiert!")
    
    # Fallback falls zu wenige
    if len(prompts) < count:
        print(f"⚠️ Nur {len(prompts)} erhalten, fülle auf...")
        while len(prompts) < count:
            prompts.append(prompts[len(prompts)%len(prompts)]) # Wiederhole einfach
            
    return prompts[:count]

def save_batch_info(job_id, prompt_list):
    """Speichert Job-Infos."""
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    
    clean_job_id = job_id.split('/')[-1]
    info = {
        "job_id": job_id,
        "base_prompt": prompt_list[0], 
        "prompts": prompt_list
    }
    filename = f"{OUTPUT_FOLDER}/batch_job_{clean_job_id}.json"
    with open(filename, "w") as f:
        json.dump(info, f, indent=4)
    print(f"📄 Job-Infos gespeichert in: {filename}")

# --- HAUPTPROGRAMM ---
if __name__ == "__main__":
    client = genai.Client(api_key=API_KEY)

    print("\n--- ETSY JUNK JOURNAL BATCH GENERATOR ---")
    print("Lasse leer für ein zufälliges Thema oder gib eine Richtung vor.")
    user_input = input("🎨 Deine Idee (Optional): ")
    
    # 1. Thema finden
    theme = generate_theme(client, user_input)
    
    # 2. Prompts erstellen
    print(f"\n🤖 Erstelle {NUMBER_OF_IMAGES} Variationen für '{theme}'...")
    prompt_list = generate_prompts_with_gemini(client, theme, NUMBER_OF_IMAGES)

    # 1. Anfragen in temporäre Datei schreiben
    batch_filename = "temp_batch_requests.jsonl"
    print(f"📝 Schreibe Anfragen in temporäre Datei: {batch_filename}")
    
    with open(batch_filename, "w") as f:
        for prompt_text in prompt_list:
            request_entry = {
                "request": {
                    "contents": [
                        {"parts": [{"text": prompt_text}]}
                    ],
                    "generation_config": {
                        "response_modalities": ["IMAGE"]
                    }
                }
            }
            f.write(json.dumps(request_entry) + "\n")

    try:
        # 2. Datei zu Google hochladen
        print("☁️  Lade Batch-Datei hoch...")
        
        # HIER WAR DER FEHLER: Wir geben jetzt explizit den Typ an!
        batch_file = client.files.upload(
            file=batch_filename,
            config={'mime_type': 'application/json'}
        )
        
        # 3. Batch Job starten
        print("🚀 Starte Batch-Job...")
        batch_job = client.batches.create(
            model=MODEL_ID,
            src=batch_file.name
        )
        
        job_id = batch_job.name
        print(f"\n✅ ERFOLG! Batch-Job wurde angenommen.")
        print(f"🆔 Job ID: {job_id}")
        print("="*40)
        print("⚠️  Bilder werden generiert. Nutze 'python3 check_batch.py' zum Prüfen.")
        print("="*40)
        
        save_batch_info(job_id, prompt_list)
        
        # Aufräumen
        os.remove(batch_filename)

    except Exception as e:
        print(f"\n❌ Fehler: {e}")