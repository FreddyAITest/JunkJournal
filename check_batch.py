import os
import json
import time
import requests
from google import genai
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv

# 1. API Key laden
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    print("❌ FEHLER: Kein API Key gefunden! Prüfe deine .env Datei.")
    exit()

OUTPUT_FOLDER = "NanoBilder_Batch"

def process_file_content(text_content):
    """Hilfsfunktion: Verarbeitet den Textinhalt der Datei zu Bildern"""
    results = text_content.strip().split('\n')
    count = 0
    saved_files = []
    
    print(f"📦 Verarbeite {len(results)} Ergebnisse...")
    
    for line in results:
        try:
            result_json = json.loads(line)
            generation_response = result_json.get("response")
            
            if generation_response and "candidates" in generation_response:
                candidates = generation_response["candidates"]
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"]["parts"]
                    for part in parts:
                        if "inlineData" in part:
                            img_data_b64 = part["inlineData"]["data"]
                            
                            import base64
                            img_bytes = base64.b64decode(img_data_b64)
                            image = Image.open(BytesIO(img_bytes))
                            
                            timestamp = int(time.time())
                            filename = f"{OUTPUT_FOLDER}/batch_img_{timestamp}_{count}.png"
                            image.save(filename)
                            print(f"   ✅ Bild gespeichert: {filename}")
                            saved_files.append(filename)
                            count += 1
        except Exception as parse_error:
            # Ignoriere leere Zeilen oder Fehler
            pass
            
    if count > 0:
        print(f"\n🎉 FERTIG! {count} Bilder gespeichert.")
        os.system(f"open {OUTPUT_FOLDER}")
    else:
        print("⚠️ Keine Bilder im Inhalt gefunden.")

def download_images(client, job_id):
    print(f"\n🔍 Prüfe Status für Job: {job_id}...")
    
    try:
        # Status abfragen
        job = client.batches.get(name=job_id)
        state = job.state
        print(f"📊 STATUS: {state}")

        if state == "JOB_STATE_SUCCEEDED":
            print("\n🚀 Job fertig! Starte Download...")
            
            file_name = job.dest.file_name
            print(f"📄 Dateiname: {file_name}")

            # --- VERSUCH 1: Der offizielle Weg (Dein Snippet) ---
            try:
                print("1️⃣  Versuche offiziellen Download (client.files.download)...")
                # Versuche mit 'file' Parameter statt 'name'
                file_content_bytes = client.files.download(file=file_name)
                
                # Bytes zu String decodieren
                text_content = file_content_bytes.decode('utf-8')
                process_file_content(text_content)
                return # Wenn das klappt, sind wir fertig!

            except Exception as e:
                print(f"⚠️  Offizieller Weg gescheitert: {e}")
                print("➡️  Wechsele zu Plan B (Listen-Suche)...")

            # --- VERSUCH 2: Der Listen-Trick (Falls Fehler 400 kommt) ---
            # Wenn der direkte Download wegen der Länge scheitert, suchen wir die URL manuell
            download_url = None
            for f in client.files.list():
                if f.name == file_name:
                    print("✅ Datei in der Liste gefunden!")
                    download_url = f.uri
                    break
            
            if download_url:
                print(f"🔗 Lade herunter von: {download_url}")
                headers = {"x-goog-api-key": API_KEY}
                response = requests.get(download_url, headers=headers, params={'alt': 'media'})
                if response.status_code == 200:
                    process_file_content(response.text)
                else:
                    print(f"❌ Auch Plan B gescheitert: {response.status_code}")
            else:
                print("❌ Datei auch in der Liste nicht gefunden. Google blockiert sie komplett.")

        elif state in ["JOB_STATE_ACTIVE", "JOB_STATE_RUNNING"]:
            print("\n⏳ Der Job läuft noch.")
        
        elif state == "JOB_STATE_FAILED":
            print(f"\n❌ Job fehlgeschlagen: {job.error}")

    except Exception as e:
        print(f"❌ Kritischer Fehler: {e}")
        import traceback
        traceback.print_exc()

# --- HAUPTPROGRAMM ---
if __name__ == "__main__":
    if not os.path.exists(OUTPUT_FOLDER):
        print(f"❌ Ordner '{OUTPUT_FOLDER}' fehlt.")
        exit()

    json_files = [f for f in os.listdir(OUTPUT_FOLDER) if f.startswith("batch_job_") and f.endswith(".json")]
    
    if not json_files:
        print(f"❌ Keine Jobs gefunden.")
        exit()

    latest_file = max([os.path.join(OUTPUT_FOLDER, f) for f in json_files], key=os.path.getctime)
    
    print(f"📂 Lade Infos: {latest_file}")
    with open(latest_file, "r") as f:
        job_info = json.load(f)
        job_id = job_info["job_id"]
    
    client = genai.Client(api_key=API_KEY)
    download_images(client, job_id)