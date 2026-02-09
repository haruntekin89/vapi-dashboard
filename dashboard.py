import streamlit as st
import pandas as pd
import time
from supabase import create_client
import io
from datetime import datetime, date

# --- 1. CONFIGURATIE (INVULLEN!) ---
SUPABASE_URL = "st.secrets["SUPABASE_URL"
SUPABASE_KEY = "st.secrets["SUPABASE_KEY"]"

# Verbinden met database
@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase = init_connection()
except:
    st.error("Kan geen verbinding maken met Supabase. Check je URL en KEY in het script.")
    st.stop()

st.set_page_config(layout="centered", page_title="Vapi Pro Dashboard", page_icon="📞")

# --- 2. DESIGN & CSS (Google Sheets Stijl) ---
st.markdown("""
<style>
    /* Algemene Stijl */
    .main { background-color: #f8f9fa; }
    
    /* Status Balken */
    .status-active { 
        background-color: #d4edda; color: #155724; 
        padding: 20px; border-radius: 10px; border: 1px solid #c3e6cb;
        text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 20px;
    }
    .status-stopped { 
        background-color: #f8d7da; color: #721c24; 
        padding: 20px; border-radius: 10px; border: 1px solid #f5c6cb;
        text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 20px;
    }
    
    /* KPI Kaarten */
    div[data-testid="metric-container"] {
        background-color: white;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Knoppen */
    .stButton>button { width: 100%; border-radius: 6px; font-weight: 600; }
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

# --- 4. STATUS CONTROLEREN ---
try:
    status_res = supabase.table('config').select("value").eq("key", "status").execute()
    current_status = status_res.data[0]['value'] if status_res.data else "UIT"
except:
    current_status = "UIT"

# Toon de statusbalk
if current_status == "AAN":
    st.markdown('<div class="status-active">🟢 SYSTEEM ACTIEF</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="status-stopped">🔴 SYSTEEM GESTOPT</div>', unsafe_allow_html=True)

# --- 5. KPI TELLERS ---
c1, c2, c3 = st.columns(3)

# Slimme queries (count only) voor snelheid
try:
    count_succes = supabase.table('leads').select("*", count='exact', head=True).eq('result', 'SUCCES').execute().count
    count_fail = supabase.table('leads').select("*", count='exact', head=True).eq('result', 'MISLUKT').execute().count
    count_todo = supabase.table('leads').select("*", count='exact', head=True).eq('status', 'new').execute().count
except:
    count_succes, count_fail, count_todo = 0, 0, 0

c1.metric("✅ SUCCES", count_succes)
c2.metric("❌ MISLUKT", count_fail)
c3.metric("⏳ WACHTRIJ", count_todo)

# --- 6. BESTURINGSKNOPPEN ---
col_btn1, col_btn2, col_btn3 = st.columns(3)

if col_btn1.button("▶ START DIALER", type="primary"):
    supabase.table('config').upsert({"key": "status", "value": "AAN"}).execute()
    st.rerun()

if col_btn2.button("⏹ STOP DIALER"):
    supabase.table('config').upsert({"key": "status", "value": "UIT"}).execute()
    st.rerun()

if col_btn3.button("🔄 VERVERS"):
    st.rerun()

st.divider()

# --- 7. BEHEER & ONDERHOUD ---
with st.expander("🛠️ Beheer & Opschonen", expanded=False):
    b1, b2 = st.columns(2)
    
    if b1.button("♻️ Reset 'Geen Gehoor'"):
        # Zet failed/busy terug naar new
        supabase.table('leads').update({"status": "new", "result": None}).in_("result", ["No Answer", "Busy", "Failed", "MISLUKT"]).execute()
        st.success("Leads zijn gereset en staan weer in de wachtrij.")
        time.sleep(2)
        st.rerun()
        
    if b2.button("🗑️ Verwijder ALLES (Hard Reset)"):
        if st.checkbox("Ik weet zeker dat ik de hele database wil wissen"):
            supabase.table('leads').delete().neq("id", 0).execute()
            st.warning("Database is volledig gewist.")
            time.sleep(2)
            st.rerun()
        else:
            st.info("Vink het vakje aan om te bevestigen.")

st.divider()

# --- IMPORT MODULE (MET KEUZE: DIALER OF BLACKLIST) ---
st.subheader("📂 Leads & Blacklist Importeren")

# Stap 1: Kies het doel
import_doel = st.radio("Waar wil je dit bestand importeren?", ["📞 Leads voor Dialer", "⛔ Nummers voor Blacklist"])

uploaded_file = st.file_uploader(f"Upload Excel/CSV voor {import_doel}", type=['xlsx', 'csv'])

if uploaded_file:
    # Inlezen
    if uploaded_file.name.endswith('.csv'): df = pd.read_csv(uploaded_file, dtype=str)
    else: df = pd.read_excel(uploaded_file, dtype=str)
    
    # Kolom kiezen
    cols = df.columns.tolist()
    phone_col = st.selectbox("Welke kolom is het telefoonnummer?", ["Kies..."] + cols)
    
    # Alleen als het voor de Dialer is, vragen we om de naam
    name_col = None
    if import_doel == "📞 Leads voor Dialer":
        name_col = st.selectbox("Welke kolom is de naam?", ["Kies..."] + cols)

    # Start Knop
    if st.button(f"🚀 Start Import naar {import_doel}") and phone_col != "Kies...":
        progress = st.progress(0)
        status_text = st.empty()
        
        # --- LOGICA VOOR DIALER IMPORT ---
        if import_doel == "📞 Leads voor Dialer":
            # Haal bestaande nummers en blacklist op
            db_leads = supabase.table('leads').select("phone").execute()
            existing_numbers = {row['phone'] for row in db_leads.data}
            
            db_black = supabase.table('blacklist').select("phone").execute()
            blacklist_numbers = {row['phone'] for row in db_black.data}
            
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
                        "original_data": row.fillna("").to_dict()
                    })
                    existing_numbers.add(clean)
                    c_new += 1
                
                if i % 100 == 0: progress.progress(min(i / len(df), 1.0))
            
            # Uploaden naar LEADS tabel
            if to_upload:
                for i in range(0, len(to_upload), 1000):
                    supabase.table('leads').insert(to_upload[i:i+1000]).execute()
            
            st.success("✅ Import naar Dialer voltooid!")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🆕 Toegevoegd", c_new)
            c2.metric("🔄 Dubbel", c_dup)
            c3.metric("⛔ Blacklist", c_black)
            c4.metric("⚠️ Ongeldig", c_inv)

        # --- LOGICA VOOR BLACKLIST IMPORT ---
        else:
            # We importeren naar de BLACKLIST tabel
            # Eerst even ophalen wat er al in staat om dubbelen te voorkomen in de tellers
            db_black = supabase.table('blacklist').select("phone").execute()
            existing_black = {row['phone'] for row in db_black.data}
            
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
            
            # Uploaden naar BLACKLIST tabel
            if to_blacklist:
                for i in range(0, len(to_blacklist), 1000):
                    # ignore_duplicates=True voor de zekerheid
                    supabase.table('blacklist').upsert(to_blacklist, on_conflict='phone', ignore_duplicates=True).execute()
            
            st.success("✅ Import naar Blacklist voltooid!")
            c1, c2, c3 = st.columns(3)
            c1.metric("⛔ Nieuw op Blacklist", c_new)
            c2.metric("🔄 Stond er al op", c_dup)
            c3.metric("⚠️ Ongeldig nummer", c_inv)
            
        progress.progress(1.0)

# --- 9. EXPORT ---
# --- 9. EXPORT ---
st.subheader("📥 Export Succesvolle Leads")

col_d1, col_d2 = st.columns(2)
start_d = col_d1.date_input("Van", value=date.today())
end_d = col_d2.date_input("Tot", value=date.today())

if st.button("Download Excel"):
    # 1. Haal EERST de data op
    try:
        # We filteren op 'ended_at' zoals afgesproken (of created_at als je dat liever hebt)
        res = supabase.table('leads').select("*").eq("result", "SUCCES").gte("created_at", str(start_d)).lte("created_at", str(end_d) + " 23:59:59").execute()
        df_exp = pd.DataFrame(res.data)
        
        # 2. Check NU pas of hij leeg is (binnen de knop-actie)
        if not df_exp.empty:
            # JSON uitpakken (zodat je adressen e.d. terugkrijgt)
            if 'original_data' in df_exp.columns:
                # Normaliseer de JSON data
                json_data = pd.json_normalize(df_exp['original_data'])
                # Plak alles aan elkaar
                df_final = pd.concat([df_exp[['phone', 'result', 'duration', 'recording']], json_data], axis=1)
            else:
                df_final = df_exp
                
            # Excel maken in het geheugen
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False)
                
            # Download knop tonen
            st.download_button(
                label="⬇️ Klik hier om de Excel te downloaden",
                data=buffer,
                file_name=f"leads_{start_d}_tot_{end_d}.xlsx",
                mime="application/vnd.ms-excel"
            )
        else:
            st.warning("Geen succesvolle leads gevonden in deze periode.")
            
    except Exception as e:
        st.error(f"Er ging iets mis bij de export: {e}")
