import streamlit as st
import pandas as pd
import time
from supabase import create_client
import io
from datetime import datetime, date
import json
import re

# --- 1. CONFIGURATIE ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    st.error("Geen secrets gevonden. Voeg ze toe in Streamlit Cloud instellingen.")
    st.stop()

# Verbinden met database
@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase = init_connection()
except:
    st.error("Kan geen verbinding maken met Supabase. Check je URL en KEY.")
    st.stop()

st.set_page_config(layout="centered", page_title="Vapi Pro Dashboard", page_icon="📞")

# --- 2. DESIGN & CSS ---
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .status-active { 
        background-color: #d4edda; color: #155724; padding: 20px; border-radius: 10px; 
        border: 1px solid #c3e6cb; text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 20px;
    }
    .status-stopped { 
        background-color: #f8d7da; color: #721c24; padding: 20px; border-radius: 10px; 
        border: 1px solid #f5c6cb; text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 20px;
    }
    div[data-testid="metric-container"] {
        background-color: white; border: 1px solid #e0e0e0; padding: 15px; border-radius: 8px;
    }
    .stButton>button { width: 100%; border-radius: 6px; font-weight: 600; height: 50px; }
</style>
""", unsafe_allow_html=True)

# --- 3. HELPER FUNCTIES ---
def normalize_number(raw_num):
    s = str(raw_num)
    digits = "".join(filter(str.isdigit, s))
    if digits.startswith("0031"): digits = digits[4:]
    if digits.startswith("31"):   digits = digits[2:]
    if digits.startswith("0"):    digits = digits[1:]
    return f"+31{digits}" if len(digits) == 9 else None

def fetch_all(table, columns, page_size=1000):
    # Supabase geeft default max 1000 rows terug — paginate om alles op te halen
    rows = []
    offset = 0
    while True:
        res = supabase.table(table).select(columns).range(offset, offset + page_size - 1).execute()
        page = res.data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows

# --- 4. STATUS CONTROLEREN ---
try:
    status_res = supabase.table('config').select("value").eq("key", "status").execute()
    current_status = status_res.data[0]['value'] if status_res.data else "UIT"
except: current_status = "UIT"

if current_status == "AAN":
    st.markdown('<div class="status-active">🟢 SYSTEEM ACTIEF</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="status-stopped">🔴 SYSTEEM GESTOPT</div>', unsafe_allow_html=True)

# --- 5. KPI TELLERS (VANDAAG) ---
vandaag = date.today().isoformat()
try:
    count_succes = supabase.table('leads').select("*", count='exact', head=True) \
        .eq('result', 'SUCCES') \
        .gte('ended_at', f"{vandaag} 00:00:00").lte('ended_at', f"{vandaag} 23:59:59").execute().count
        
    count_fail = supabase.table('leads').select("*", count='exact', head=True) \
        .eq('result', 'MISLUKT') \
        .gte('ended_at', f"{vandaag} 00:00:00").lte('ended_at', f"{vandaag} 23:59:59").execute().count
        
    count_todo = supabase.table('leads').select("*", count='exact', head=True).eq('status', 'new').execute().count
except:
    count_succes, count_fail, count_todo = 0, 0, 0

c1, c2, c3 = st.columns(3)
c1.metric("✅ Succes Vandaag", count_succes)
c2.metric("❌ Mislukt Vandaag", count_fail)
c3.metric("⏳ Wachtrij Totaal", count_todo)

# --- 6. BESTURING ---
st.divider()
st.subheader("⚙️ Besturing")

col_btn1, col_btn2, col_btn3 = st.columns(3)

if col_btn1.button("▶ START DIALER", type="primary"):
    supabase.table('config').upsert({"key": "status", "value": "AAN"}).execute()
    st.rerun()

if col_btn2.button("⏹ STOP DIALER"):
    supabase.table('config').upsert({"key": "status", "value": "UIT"}).execute()
    st.rerun()

if col_btn3.button("🔄 VERVERS"):
    st.rerun()

# --- SNELHEID ---
try:
    speed_res = supabase.table('config').select("value").eq("key", "speed").execute()
    current_speed = int(speed_res.data[0]['value']) if speed_res.data else 20
except:
    current_speed = 20

st.write("")
st.write(f"**Huidige snelheid:** {current_speed} calls per minuut")
new_speed = st.slider("", min_value=10, max_value=100, value=current_speed, step=5, label_visibility="collapsed")

if new_speed != current_speed:
    supabase.table('config').upsert({"key": "speed", "value": str(new_speed)}).execute()
    st.success(f"Snelheid aangepast naar {new_speed} calls/minuut!")
    time.sleep(1)
    st.rerun()

# --- 7. TELEFOONNUMMERS (4 VAKJES) ---
st.write("")
st.subheader("📞 Uitbel Nummers (Vapi Phone ID's)")

# Haal huidige nummers op
try:
    phone_res = supabase.table('config').select("value").eq("key", "phone_ids").execute()
    saved_list = json.loads(phone_res.data[0]['value']) if phone_res.data else ["", "", "", ""]
except:
    saved_list = ["", "", "", ""]

# Zorg dat de lijst altijd 4 lang is
while len(saved_list) < 4: saved_list.append("")

col_p1, col_p2 = st.columns(2)
col_p3, col_p4 = st.columns(2)

# De 4 vakjes
p1 = col_p1.text_input("Nummer 1 ID:", value=saved_list[0])
p2 = col_p2.text_input("Nummer 2 ID:", value=saved_list[1])
p3 = col_p3.text_input("Nummer 3 ID:", value=saved_list[2])
p4 = col_p4.text_input("Nummer 4 ID:", value=saved_list[3])

if st.button("💾 Opslaan Nummers"):
    new_list = [x.strip() for x in [p1, p2, p3, p4] if x.strip()]
    json_str = json.dumps(new_list)
    supabase.table('config').upsert({"key": "phone_ids", "value": json_str}).execute()
    st.success(f"Opgeslagen! De motor gebruikt nu {len(new_list)} nummers.")
    time.sleep(1); st.rerun()

st.divider()

# --- 8. BEHEER & ONDERHOUD ---
with st.expander("🛠️ Beheer & Opschonen", expanded=False):
    b1, b2 = st.columns(2)
    
    if b1.button("♻️ Reset 'Geen Gehoor'"):
        # We doen ze stuk voor stuk, dat is veiliger
        try:
            # 1. Reset 'customer-did-not-answer'
            supabase.table('leads').update({"status": "new", "result": None}).eq("ended_reason", "customer-did-not-answer").execute()
            
            # 2. Reset 'no-answer-transfer'
            supabase.table('leads').update({"status": "new", "result": None}).eq("ended_reason", "no-answer-transfer").execute()
            
            # 3. Reset 'voicemail'
            supabase.table('leads').update({"status": "new", "result": None}).eq("ended_reason", "voicemail").execute()
            
            # 4. Optioneel: Reset 'silence-timed-out' (vaak ook voicemail)
            supabase.table('leads').update({"status": "new", "result": None}).eq("ended_reason", "silence-timed-out").execute()

            st.success("✅ Leads (Geen Gehoor) zijn gereset!")
            time.sleep(2)
            st.rerun()
            
        except Exception as e:
            st.error(f"Fout bij resetten: {e}")
        
    if b2.button("🗑️ Verwijder ALLES (Hard Reset)"):
        if st.checkbox("Ik weet zeker dat ik de hele database wil wissen"):
            supabase.table('leads').delete().neq("id", 0).execute()
            st.warning("Database is volledig gewist.")
            time.sleep(2)
            st.rerun()
        else:
            st.info("Vink het vakje aan om te bevestigen.")

st.divider()

# --- BATCHES OVERZICHT ---
st.subheader("📊 Batches Overzicht")

try:
    df_batches = pd.DataFrame(fetch_all('leads', 'batch_id,status,result,ended_reason'))
except Exception as e:
    st.error(f"Kan batches niet ophalen: {e}")
    df_batches = pd.DataFrame()

if df_batches.empty:
    st.info("Nog geen leads in de database.")
else:
    df_batches['batch_id'] = df_batches['batch_id'].fillna('onbekend')

    # Nieuwste batches bovenaan, 'oude_import' altijd onderaan
    alle_batches = df_batches['batch_id'].unique().tolist()
    overige = sorted([b for b in alle_batches if b != 'oude_import'], reverse=True)
    if 'oude_import' in alle_batches:
        overige.append('oude_import')

    GEEN_GEHOOR_REDENEN = ["customer-did-not-answer", "no-answer-transfer", "voicemail", "silence-timed-out"]

    for batch in overige:
        sub = df_batches[df_batches['batch_id'] == batch]
        totaal = len(sub)
        wachtrij = int((sub['status'] == 'new').sum())
        succes = int((sub['result'] == 'SUCCES').sum())
        mislukt = int((sub['result'] == 'MISLUKT').sum())
        bezig = int((sub['status'] == 'in-progress').sum())

        titel = f"📦 **{batch}** — {totaal} leads · ⏳ {wachtrij} te bellen · ✅ {succes} succes"
        with st.expander(titel, expanded=False):
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("📞 Totaal", totaal)
            m2.metric("⏳ Te bellen", wachtrij)
            m3.metric("✅ Succes", succes)
            m4.metric("❌ Mislukt", mislukt)
            m5.metric("🔄 Bezig", bezig)

            col_r, col_d = st.columns(2)

            # Reset 'Geen Gehoor' alleen voor deze batch
            if col_r.button("♻️ Reset Geen Gehoor", key=f"reset_{batch}"):
                try:
                    aantal = 0
                    for reden in GEEN_GEHOOR_REDENEN:
                        res = supabase.table('leads').update({"status": "new", "result": None}) \
                            .eq("batch_id", batch).eq("ended_reason", reden).execute()
                        aantal += len(res.data) if res.data else 0
                    st.success(f"✅ {aantal} leads in '{batch}' staan weer in de wachtrij.")
                    time.sleep(1.5); st.rerun()
                except Exception as e:
                    st.error(f"Fout bij reset: {e}")

            # Verwijder hele batch — checkbox eerst, dan knop (correct pattern)
            bevestig = col_d.checkbox(f"Bevestig verwijderen", key=f"conf_{batch}")
            if col_d.button("🗑️ Verwijder Batch", key=f"del_{batch}"):
                if bevestig:
                    try:
                        supabase.table('leads').delete().eq("batch_id", batch).execute()
                        st.warning(f"🗑️ Batch '{batch}' is volledig verwijderd.")
                        time.sleep(1.5); st.rerun()
                    except Exception as e:
                        st.error(f"Fout bij verwijderen: {e}")
                else:
                    st.info("Vink eerst 'Bevestig verwijderen' aan.")

st.divider()

# --- 9. IMPORT MODULE ---
st.subheader("📂 Leads & Blacklist Importeren")

import_doel = st.radio("Waar wil je dit bestand importeren?", ["📞 Leads voor Dialer", "⛔ Nummers voor Blacklist"])
uploaded_file = st.file_uploader(f"Upload Excel/CSV voor {import_doel}", type=['xlsx', 'csv'])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'): 
            try: df = pd.read_csv(uploaded_file, dtype=str, sep=None, engine='python')
            except: df = pd.read_csv(uploaded_file, dtype=str, sep=';')
        else: 
            df = pd.read_excel(uploaded_file, dtype=str)
        
        df = df.fillna("")
        
        cols = df.columns.tolist()
        phone_col = st.selectbox("Welke kolom is het telefoonnummer?", ["Kies..."] + cols)
        
        name_col = None
        if import_doel == "📞 Leads voor Dialer":
            name_col = st.selectbox("Welke kolom is de naam?", ["Kies..."] + cols)

        if st.button(f"🚀 Start Import naar {import_doel}") and phone_col != "Kies...":
            progress = st.progress(0)
            status_text = st.empty()
            
            if import_doel == "📞 Leads voor Dialer":
                # Batch-naam: bestandsnaam (zonder extensie, opgeschoond) + datum/tijd
                bestandsnaam = re.sub(r'\.[^.]+$', '', uploaded_file.name)
                bestandsnaam = re.sub(r'[^\w\-]', '_', bestandsnaam).strip('_').lower() or "import"
                batch_id = f"{bestandsnaam}_{datetime.now().strftime('%Y-%m-%d_%H%M')}"

                existing_numbers = {row['phone'] for row in fetch_all('leads', 'phone')}
                blacklist_numbers = {row['phone'] for row in fetch_all('blacklist', 'phone')}

                to_upload = []
                c_new, c_dup, c_black, c_inv = 0, 0, 0, 0

                for i, (index, row) in enumerate(df.iterrows()):
                    clean = normalize_number(row[phone_col])
                    if not clean:
                        c_inv += 1
                    elif clean in blacklist_numbers:
                        c_black += 1
                    elif clean in existing_numbers:
                        c_dup += 1
                    else:
                        clean_naam = str(row[name_col]) if name_col and name_col != "Kies..." else "Klant"
                        to_upload.append({
                            "phone": clean,
                            "name": clean_naam,
                            "status": "new",
                            "batch_id": batch_id,
                            "original_data": row.to_dict()
                        })
                        existing_numbers.add(clean)
                        c_new += 1
                    
                    if i % 100 == 0: progress.progress(min(i / len(df), 1.0))
                
                if to_upload:
                    # Upload in chunks van 1000
                    for i in range(0, len(to_upload), 1000):
                        try:
                            supabase.table('leads').upsert(to_upload[i:i+1000], on_conflict='phone', ignore_duplicates=True).execute()
                        except Exception as e:
                            print(f"Batch warning: {e}")
                
                st.success(f"✅ Import voltooid! Batch: **{batch_id}**")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🆕 Toegevoegd", c_new)
                c2.metric("🔄 Dubbel", c_dup)
                c3.metric("⛔ Blacklist", c_black)
                c4.metric("⚠️ Ongeldig", c_inv)

            else:
                existing_black = {row['phone'] for row in fetch_all('blacklist', 'phone')}
                
                to_blacklist = []
                c_new, c_dup, c_inv = 0, 0, 0
                
                for i, (index, row) in enumerate(df.iterrows()):
                    clean = normalize_number(row[phone_col])
                    if not clean:
                        c_inv += 1
                    elif clean in existing_black:
                        c_dup += 1
                    else:
                        to_blacklist.append({"phone": clean})
                        existing_black.add(clean)
                        c_new += 1
                    if i % 100 == 0: progress.progress(min(i / len(df), 1.0))
                
                if to_blacklist:
                    for i in range(0, len(to_blacklist), 1000):
                        try:
                            supabase.table('blacklist').upsert(to_blacklist, on_conflict='phone', ignore_duplicates=True).execute()
                        except: pass
                
                st.success("✅ Blacklist bijgewerkt!")
                c1, c2, c3 = st.columns(3)
                c1.metric("⛔ Nieuw op Blacklist", c_new)
                c2.metric("🔄 Stond er al op", c_dup)
                c3.metric("⚠️ Ongeldig", c_inv)
                
            progress.progress(1.0)
            time.sleep(2)
            st.rerun()

    except Exception as e:
        st.error(f"Fout bij lezen bestand: {e}")

st.divider()

# --- 10. EXPORT ---
st.subheader("📥 Export Succesvolle Leads")

col_d1, col_d2 = st.columns(2)
start_d = col_d1.date_input("Van", value=date.today())
end_d = col_d2.date_input("Tot", value=date.today())

if st.button("Download Excel"):
    try:
        res = supabase.table('leads').select("*").eq("result", "SUCCES") \
            .gte("ended_at", str(start_d)).lte("ended_at", str(end_d) + " 23:59:59").execute()
        
        df_exp = pd.DataFrame(res.data)
        
        if not df_exp.empty:
            if 'original_data' in df_exp.columns:
                json_data = pd.json_normalize(df_exp['original_data'])
                df_final = pd.concat([df_exp[['phone', 'result', 'duration', 'recording', 'ended_at']], json_data], axis=1)
            else: df_final = df_exp
            
            df_final.insert(0, "enquete", "telefonische enquete vrije tijd en ontspanning")
            
            if 'ended_at' in df_final.columns:
                # LET OP: Deze regel moet ingesprongen zijn (met 4 spaties)
                df_final['enquete_datum'] = pd.to_datetime(df_final['ended_at'], errors='coerce').dt.strftime('%d-%m-%Y')
                
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False)
                
            st.download_button("⬇️ Download Excel", buffer, f"leads_{start_d}.xlsx", "application/vnd.ms-excel")
        else:
            st.warning("Geen succesvolle leads gevonden.")
            
    except Exception as e:
        st.error(f"Fout: {e}")
