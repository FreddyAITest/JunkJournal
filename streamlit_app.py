import streamlit as st
import os
import json
import time
import requests
from google import genai
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv
import re
import zipfile

# --- KONFIGURATION ---

# --- KONFIGURATION ---
OUTPUT_FOLDER = "NanoBilder_Batch"
BATCH_INFO_FOLDER = "NanoBilder_Batch" # Wo die JSONs liegen
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

# --- SETUP ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

st.set_page_config(page_title="Etsy Junk Journal Generator", page_icon="🎨", layout="wide")

# --- SICHERHEIT: PASSWORTSCHUTZ ---
def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Bitte Passwort eingeben:", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input again.
        st.text_input(
            "Bitte Passwort eingeben:", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Passwort falsch")
        return False
    else:
        # Password correct.
        return True

if not check_password():
    st.stop()

# --- SIDEBAR ---
st.sidebar.title("🎨 Konfiguration")
if not API_KEY:
    st.sidebar.error("Kein API Key gefunden! Bitte .env prüfen.")
    st.stop()

client = genai.Client(api_key=API_KEY)

# --- FUNKTIONEN (Portiert) ---

def generate_theme(user_input=None):
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
    return response.text.strip()

def generate_prompts(theme, count):
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

Generate exactly {count} prompts now."""

    response = client.models.generate_content(
        model='gemini-2.0-flash-exp',
        contents=generation_prompt
    )
    
    lines = response.text.strip().split('\n')
    prompts = []
    for line in lines:
        cleaned = line.strip()
        cleaned = re.sub(r'^[\d\.\-\*\s]+', '', cleaned)
        if cleaned:
            prompts.append(cleaned)
            
    # Auffüllen falls nötig
    if len(prompts) < count:
        while len(prompts) < count:
            prompts.append(prompts[len(prompts)%len(prompts)])
            
    return prompts[:count]

def save_job_info(job_id, theme, prompts):
    clean_job_id = job_id.split('/')[-1]
    info = {
        "job_id": job_id,
        "theme": theme,
        "timestamp": time.time(),
        "status": "SUBMITTED",
        "prompts": prompts
    }
    filename = f"{BATCH_INFO_FOLDER}/batch_job_{clean_job_id}.json"
    with open(filename, "w") as f:
        json.dump(info, f, indent=4)
    return filename

def get_all_jobs():
    jobs = []
    if not os.path.exists(BATCH_INFO_FOLDER):
        return []
        
    files = [f for f in os.listdir(BATCH_INFO_FOLDER) if f.startswith("batch_job_") and f.endswith(".json")]
    for f in files:
        try:
            with open(os.path.join(BATCH_INFO_FOLDER, f), "r") as file:
                data = json.load(file)
                data['filename'] = f
                jobs.append(data)
        except:
            pass
    # Sortieren nach Timestamp (neueste zuerst)
    jobs.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    return jobs

def process_downloaded_content(text_content, job_id):
    results = text_content.strip().split('\n')
    images = []
    
    # Erstelle Unterordner für diesen Job
    clean_job_id = job_id.split('/')[-1]
    job_folder = os.path.join(OUTPUT_FOLDER, clean_job_id)
    if not os.path.exists(job_folder):
        os.makedirs(job_folder)
        
    count = 0
    for line in results:
        try:
            result_json = json.loads(line)
            # Check for valid response
            if "response" in result_json and "candidates" in result_json["response"]:
                candidates = result_json["response"]["candidates"]
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"]["parts"]
                    for part in parts:
                        if "inlineData" in part:
                            img_data_b64 = part["inlineData"]["data"]
                            import base64
                            img_bytes = base64.b64decode(img_data_b64)
                            
                            # Speichern
                            filename = f"{job_folder}/img_{count}.png"
                            with open(filename, "wb") as f:
                                f.write(img_bytes)
                            
                            images.append(filename)
                            count += 1
        except Exception:
            pass
    return images

def create_zip_of_folder(folder_path):
    """Erstellt ein ZIP-Archiv im Speicher aus einem Ordner."""
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.endswith(".png"):
                    file_path = os.path.join(root, file)
                    zf.write(file_path, os.path.basename(file_path))
    memory_file.seek(0)
    return memory_file

def convert_to_a4(image):
    """Konvertiert ein Bild zu DIN A4 (300 DPI) mittels Lanczos-Filter."""
    # A4 bei 300 DPI
    A4_WIDTH = 2480
    A4_HEIGHT = 3508
    
    target_ratio = A4_WIDTH / A4_HEIGHT
    img_ratio = image.width / image.height
    
    # 1. Skalieren (Aspect Ratio beibehalten, so dass es A4 füllt)
    if img_ratio > target_ratio:
        # Bild ist breiter als A4 -> Höhe anpassen
        new_height = A4_HEIGHT
        new_width = int(new_height * img_ratio)
    else:
        # Bild ist schmaler als A4 -> Breite anpassen
        new_width = A4_WIDTH
        new_height = int(new_width / img_ratio)
        
    resized_img = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # 2. Center Crop auf exakt A4
    left = (new_width - A4_WIDTH) / 2
    top = (new_height - A4_HEIGHT) / 2
    right = (new_width + A4_WIDTH) / 2
    bottom = (new_height + A4_HEIGHT) / 2
    
    return resized_img.crop((left, top, right, bottom))

# --- UI ---

st.title("🎨 Etsy Junk Journal Generator")

tab1, tab2, tab3 = st.tabs(["🚀 Neuen Batch starten", "📂 Meine Batches & Bilder", "🖨️ Druck-Vorbereitung (A4)"])

with tab1:
    st.header("Neues Set erstellen")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        user_idea = st.text_input("Deine Idee (Optional)", placeholder="z.B. Christmas Steampunk, Mushroom Fairy...")
        num_images = st.slider("Anzahl Bilder", min_value=10, max_value=100, value=20, step=10)
    
    if st.button("✨ Thema & Prompts generieren", type="primary"):
        with st.status("Arbeite...", expanded=True) as status:
            st.write("🧠 Entwickle Thema...")
            theme = generate_theme(user_idea)
            st.info(f"Thema: **{theme}**")
            
            st.write(f"📝 Schreibe {num_images} Prompts...")
            prompts = generate_prompts(theme, num_images)
            st.success(f"{len(prompts)} Prompts erstellt!")
            
            # Batch Job starten
            st.write("☁️ Sende an Google Batch API...")
            
            # Temp File erstellen
            batch_filename = "temp_streamlit_batch.jsonl"
            with open(batch_filename, "w") as f:
                for p in prompts:
                    req = {
                        "request": {
                            "contents": [{"parts": [{"text": p}]}],
                            "generation_config": {"response_modalities": ["IMAGE"]}
                        }
                    }
                    f.write(json.dumps(req) + "\n")
            
            # Upload & Start
            try:
                batch_file = client.files.upload(file=batch_filename, config={'mime_type': 'application/json'})
                batch_job = client.batches.create(
                    model="gemini-3-pro-image-preview",
                    src=batch_file.name
                )
                
                save_job_info(batch_job.name, theme, prompts)
                st.balloons()
                st.success(f"Batch Job gestartet! ID: {batch_job.name}")
                os.remove(batch_filename)
                
            except Exception as e:
                st.error(f"Fehler beim Starten: {e}")
            
            status.update(label="Fertig!", state="complete", expanded=False)

with tab2:
    st.header("Verlauf")
    
    jobs = get_all_jobs()
    if not jobs:
        st.info("Noch keine Jobs gefunden.")
    else:
        for job in jobs:
            with st.expander(f"{job.get('theme', 'Unbekannt')} ({job.get('status')}) - {job.get('job_id')}"):
                st.write(f"**Job ID:** {job['job_id']}")
                st.write(f"**Erstellt:** {time.ctime(job.get('timestamp', 0))}")
                
                col_check, col_del = st.columns([1, 4])
                
                if col_check.button("Status prüfen & Laden", key=f"btn_{job['job_id']}"):
                    try:
                        api_job = client.batches.get(name=job['job_id'])
                        st.write(f"Status: **{api_job.state}**")
                        
                        if api_job.state == "JOB_STATE_SUCCEEDED":
                            st.success("Job fertig! Lade Bilder...")
                            
                            # Download Logic
                            file_name = api_job.dest.file_name
                            content = ""
                            
                            try:
                                content_bytes = client.files.download(file=file_name)
                                content = content_bytes.decode('utf-8')
                            except:
                                # Fallback Search
                                for f in client.files.list():
                                    if f.name == file_name:
                                        headers = {"x-goog-api-key": API_KEY}
                                        resp = requests.get(f.uri, headers=headers, params={'alt': 'media'})
                                        if resp.status_code == 200:
                                            content = resp.text
                                        break
                            
                            if content:
                                images = process_downloaded_content(content, job['job_id'])
                                st.success(f"{len(images)} Bilder gespeichert!")
                                
                                # Update JSON status
                                job['status'] = "COMPLETED"
                                job['image_count'] = len(images)
                                with open(os.path.join(BATCH_INFO_FOLDER, job['filename']), "w") as f:
                                    json.dump(job, f, indent=4)
                                    
                                st.rerun() # Refresh UI
                            else:
                                st.error("Konnte Datei nicht herunterladen.")
                                
                    except Exception as e:
                        st.error(f"Fehler beim Prüfen: {e}")

                # Bilder anzeigen wenn vorhanden
                clean_id = job['job_id'].split('/')[-1]
                job_dir = os.path.join(OUTPUT_FOLDER, clean_id)
                
                if os.path.exists(job_dir):
                    images = [os.path.join(job_dir, f) for f in os.listdir(job_dir) if f.endswith(".png")]
                    if images:
                        st.write(f"📸 {len(images)} Bilder verfügbar:")
                        
                        # 1. Download Button für alle
                        zip_data = create_zip_of_folder(job_dir)
                        st.download_button(
                            label="📦 Alle Bilder als ZIP herunterladen",
                            data=zip_data,
                            file_name=f"images_{clean_id}.zip",
                            mime="application/zip",
                            type="primary",
                            key=f"zip_btn_{clean_id}"
                        )
                        
                        # 2. Galerie (Grid Layout)
                        cols = st.columns(3) # 3 Bilder pro Reihe
                        for idx, img_path in enumerate(images):
                            with cols[idx % 3]:
                                st.image(img_path, use_container_width=True)

with tab3:
    st.header("🖨️ Bilder für Druck vorbereiten (DIN A4)")
    st.write("Lade deine Favoriten hoch. Sie werden automatisch auf **DIN A4 (300 DPI)** hochskaliert und zugeschnitten.")
    
    uploaded_files = st.file_uploader("Bilder auswählen", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    
    if uploaded_files:
        if st.button(f"✨ {len(uploaded_files)} Bilder konvertieren"):
            progress_bar = st.progress(0)
            processed_images = []
            
            # Temp Ordner für ZIP
            timestamp = int(time.time())
            upscale_folder = f"Upscaled_A4_{timestamp}"
            os.makedirs(upscale_folder, exist_ok=True)
            
            for i, uploaded_file in enumerate(uploaded_files):
                # Laden
                image = Image.open(uploaded_file)
                
                # Konvertieren
                a4_image = convert_to_a4(image)
                
                # Speichern
                save_path = os.path.join(upscale_folder, f"A4_{uploaded_file.name}")
                a4_image.save(save_path, quality=95)
                processed_images.append(save_path)
                
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            st.success("Fertig!")
            
            # ZIP erstellen
            zip_data = create_zip_of_folder(upscale_folder)
            st.download_button(
                label="📦 Alle A4-Bilder herunterladen (ZIP)",
                data=zip_data,
                file_name=f"A4_Print_Ready_{timestamp}.zip",
                mime="application/zip",
                type="primary"
            )
            
            # Aufräumen (Ordner löschen)
            import shutil
            shutil.rmtree(upscale_folder)
                                # Optional: Einzeldownload
                                # with open(img_path, "rb") as file:
                                #     st.download_button("⬇️", file, file_name=os.path.basename(img_path), key=f"dl_{clean_id}_{idx}")
