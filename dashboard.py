import streamlit as st
import requests
import json
import pandas as pd
import time
import re
from datetime import datetime, timedelta

# --- KONFIGURACJA STRONY (Musi być na samym początku) ---
st.set_page_config(page_title="Raport Pakowaczy FINAL", layout="wide", page_icon="📦")

# ==========================================
# 🔐 KONFIGURACJA BEZPIECZEŃSTWA
# ==========================================

# 1. HASŁO DO STRONY (Możesz zmienić na swoje)
HASLO_DO_STRONY = "flopak323" 

# 2. TOKEN BASELINKER (Pobierany bezpiecznie z Secrets)
try:
    TOKEN = st.secrets["TOKEN"]
except FileNotFoundError:
    st.error("❌ BŁĄD KONFIGURACJI: Nie znaleziono tokenu API!")
    st.info("Jeśli jesteś w Streamlit Cloud: Wejdź w Settings -> Secrets i wklej tam: TOKEN = 'twoj-dlugi-token'")
    st.stop()
except KeyError:
    st.error("❌ BŁĄD KONFIGURACJI: Token nie jest zdefiniowany w Secrets!")
    st.stop()

# ==========================================
# 🛑 SYSTEM LOGOWANIA
# ==========================================

if 'zalogowany' not in st.session_state:
    st.session_state['zalogowany'] = False

if not st.session_state['zalogowany']:
    # Styl dla ekranu logowania
    st.markdown("""
        <style>
        .stApp {background-color: #0e1117;}
        div.stButton > button {width: 100%; background-color: #0078d4; color: white;}
        </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.title("🔒 Dostęp Chroniony")
        podane_haslo = st.text_input("Podaj hasło do raportu:", type="password")
        if st.button("Zaloguj się"):
            if podane_haslo == HASLO_DO_STRONY:
                st.session_state['zalogowany'] = True
                st.rerun()
            else:
                st.error("Błędne hasło!")
    st.stop() # ZATRZYMUJE KOD - DALEJ NIC SIĘ NIE WYKONA BEZ LOGOWANIA

# ==========================================
# 🚀 GŁÓWNA APLIKACJA (Dostępna po zalogowaniu)
# ==========================================

# --- STAŁE I KONFIGURACJA LOGIKI ---
DNI_DO_POBRANIA_API = 90 
FILTR_STATUSOW = [61254, 110811] 
PROG_ODCIECIA_CZASU_MINUT = 10   
MAX_PRZERWA_MINUT = 30           
CZAS_ZA_START = 3                
GODZINA_START = 5                
GODZINA_KONIEC = 18              

# --- CSS (DARK MODE) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    h1, h2, h3, h4, h5, h6, p, div, span, li, label { color: #fafafa !important; }
    header[data-testid="stHeader"] { background-color: #0e1117 !important; }
    header[data-testid="stHeader"] * { color: #fafafa !important; }
    section[data-testid="stSidebar"] { background-color: #262730; border-right: 1px solid #41444e; }
    div[data-testid="metric-container"] {
        background-color: #262730 !important;
        border: 1px solid #41444e;
        border-left: 5px solid #0078d4;
    }
    div[data-testid="metric-container"] label { color: #a0a0a0 !important; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] { color: #ffffff !important; }
    .stDataFrame { background-color: #262730 !important; }
    div.stButton > button {
        background-color: #0078d4; color: white; border: none; width: 100%;
    }
    /* Ukrycie menu Streamlit dla zwykłych userów */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE ---

@st.cache_data(ttl=3600, show_spinner=False)
def pobierz_dane_z_api(dni):
    date_from = int((datetime.now() - timedelta(days=dni)).timestamp())
    wszystkie = []
    
    progress_text = "Pobieranie danych..."
    my_bar = st.progress(0, text=progress_text)
    total_steps = len(FILTR_STATUSOW)
    
    for i, status_id in enumerate(FILTR_STATUSOW):
        id_startowe = 0
        while True:
            my_bar.progress((i / total_steps), text=f"Status {status_id} ({len(wszystkie)} zam.)...")
            method_params = {
                "date_from": date_from, "status_id": status_id,
                "get_unconfirmed_orders": False, "limit": 100
            }
            if id_startowe > 0: method_params["id_from"] = id_startowe

            try:
                resp = requests.post(
                    "https://api.baselinker.com/connector.php", 
                    data={"token": TOKEN, "method": "getOrders", "parameters": json.dumps(method_params)}
                ).json()
                
                if resp['status'] == 'SUCCESS':
                    batch = resp['orders']
                    if not batch: break
                    wszystkie.extend(batch)
                    id_startowe = batch[-1]['order_id']
                    if len(batch) < 100: break
                    time.sleep(0.03) 
                else: break
            except: break
    
    my_bar.empty()
    return list({o['order_id']: o for o in wszystkie}.values())

def znajdz_rodzaj_kartonu(order):
    pole_2 = str(order.get('extra_field_2', '')).strip()
    if pole_2 and len(pole_2) > 1: return pole_2
    for pole in order.get('extra_fields', []):
        val = str(pole.get('value', '')).strip()
        name = str(pole.get('name', '')).lower()
        if "osoba" not in name and "data" not in name and "pakowacz" not in name and ";" not in val and val:
            return f"{val} ({name})"
    return "Nieokreślony"

def przetworz_do_dataframe(orders):
    lista = []
    for order in orders:
        wpis = order.get('extra_field_1', '')
        rodzaj_kartonu = znajdz_rodzaj_kartonu(order)
        
        if wpis and ';' in wpis:
            try:
                czesci = wpis.split(';')
                osoba = czesci[0].strip()
                if "[profile]" in osoba: osoba = "Test/Automat"
                
                data_str = czesci[1].strip()
                try:
                    czas = datetime.strptime(data_str, "%d.%m.%Y %H:%M")
                except ValueError:
                    czas = datetime.strptime(data_str, "%d.%m.%Y %H:%M:%S")
                
                paczki = 1
                if len(czesci) >= 3:
                    txt = czesci[2].strip()
                    found = re.search(r'(\d+)', txt)
                    if found: paczki = int(found.group(1))
                
                lista.append({
                    "Order ID": order['order_id'], "Status ID": order['order_status_id'],
                    "Osoba": osoba, "Data": czas.date(), "Godzina": czas,
                    "Paczki": paczki, "Karton": rodzaj_kartonu
                })
            except: pass
    return pd.DataFrame(lista)

def oblicz_logike_scisla(df_osoby):
    df_osoby = df_osoby.copy()
    df_osoby['Minuta_Str'] = df_osoby['Godzina'].dt.strftime('%Y-%m-%d %H:%M')
    
    # 1. WYKRYWANIE BŁĘDÓW (Duplikaty + Poza godzinami pracy)
    counts = df_osoby['Minuta_Str'].value_counts()
    bledne_minuty = counts[counts > 1].index.tolist()
    maska_duplikaty = df_osoby['Minuta_Str'].isin(bledne_minuty)
    maska_poza_czasem = (df_osoby['Godzina'].dt.hour < GODZINA_START) | (df_osoby['Godzina'].dt.hour >= GODZINA_KONIEC)
    maska_total_bledy = maska_duplikaty | maska_poza_czasem
    
    df_bledy = df_osoby[maska_total_bledy]
    paczki_bledy = df_bledy['Paczki'].sum()
    
    # 2. DANE POPRAWNE (Valid)
    df_valid = df_osoby[~maska_total_bledy].sort_values('Godzina')
    timestamps = df_valid['Godzina'].tolist()
    paczki_lista = df_valid['Paczki'].tolist()
    
    czas_minuty = 0
    paczki_do_sredniej = 0
    paczki_postoj = 0
    liczba_dlugich_przerw = 0 
    
    if not timestamps:
        return 0.0, 0, 0, paczki_bledy, 0
        
    czas_minuty += CZAS_ZA_START
    paczki_do_sredniej += paczki_lista[0]
    
    for i in range(1, len(timestamps)):
        diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 60
        biezace_paczki = paczki_lista[i]
        
        if diff <= PROG_ODCIECIA_CZASU_MINUT:
            # Normalna praca
            czas_minuty += diff
            paczki_do_sredniej += biezace_paczki
        elif diff <= MAX_PRZERWA_MINUT:
            # Postój (10-30m) - Wykluczone
            paczki_postoj += biezace_paczki
        else:
            # Długa przerwa (>30m) - Reset
            czas_minuty += CZAS_ZA_START
            paczki_do_sredniej += biezace_paczki
            liczba_dlugich_przerw += 1 
            
    return round(czas_minuty / 60, 2), paczki_do_sredniej, paczki_postoj, paczki_bledy, liczba_dlugich_przerw

# --- LOGIKA SESJI ---

if 'data_frame' not in st.session_state:
    st.session_state['data_frame'] = pd.DataFrame()
if 'last_update' not in st.session_state:
    st.session_state['last_update'] = None

# --- INTERFEJS ---

c1, c2 = st.columns([3, 1])
with c1: st.title("📦 Raport Pakowaczy (Full)")
with c2: 
    if st.button("Wyloguj"):
        st.session_state['zalogowany'] = False
        st.rerun()

st.sidebar.header("⚙️ Sterowanie")

if st.sidebar.button("🔄 Odśwież dane z API"):
    with st.spinner(f"Pobieram dane ({DNI_DO_POBRANIA_API} dni, 2 statusy)..."):
        raw_data = pobierz_dane_z_api(DNI_DO_POBRANIA_API)
        df_new = przetworz_do_dataframe(raw_data)
        st.session_state['data_frame'] = df_new
        st.session_state['last_update'] = datetime.now().strftime("%H:%M")
        st.rerun()

if st.session_state['data_frame'].empty:
    st.warning("⚠️ Kliknij 'Odśwież dane z API' w menu po lewej, aby pobrać bazę.")
    st.stop()
else:
    df_full = st.session_state['data_frame']
    st.sidebar.success(f"Baza: {st.session_state['last_update']} ({len(df_full)} zam.)")

st.sidebar.markdown("---")
st.sidebar.header("🔍 Filtry")

# FILTRY DATY
opcja_czasu = st.sidebar.radio(
    "📅 Okres:", 
    ["Dzisiaj", "Wczoraj", "Ostatnie 5 dni", "Bieżący miesiąc", "Poprzedni miesiąc", "Zakres niestandardowy"],
    index=0 
)
dzis = datetime.now().date()
start, end = dzis, dzis

if opcja_czasu == "Wczoraj": 
    start = end = dzis - timedelta(days=1)
elif opcja_czasu == "Ostatnie 5 dni": 
    start = dzis - timedelta(days=5)
elif opcja_czasu == "Bieżący miesiąc":
    start = dzis.replace(day=1)
    end = dzis
elif opcja_czasu == "Poprzedni miesiąc":
    first_day_current = dzis.replace(day=1)
    end = first_day_current - timedelta(days=1)
    start = end.replace(day=1)
elif opcja_czasu == "Zakres niestandardowy":
    c1, c2 = st.sidebar.columns(2)
    start = c1.date_input("Od", dzis - timedelta(days=5))
    end = c2.date_input("Do", dzis)

maska = (df_full['Data'] >= start) & (df_full['Data'] <= end)
df = df_full.loc[maska]

lista_osob = sorted(df['Osoba'].unique().tolist())
wybrani = st.sidebar.multiselect("👥 Pracownicy:", lista_osob, default=lista_osob)
if wybrani: df = df[df['Osoba'].isin(wybrani)]

# --- OBLICZENIA I TABELE ---

if not df.empty:
    ranking_data = []
    
    for (osoba, data), group in df.groupby(['Osoba', 'Data']):
        godziny, paczki_srednia, paczki_postoj, paczki_bledy, przerwy = oblicz_logike_scisla(group)
        paczki_razem = group['Paczki'].sum()
        
        ranking_data.append({
            "Osoba": osoba,
            "Data": data,
            "Paczki Razem": paczki_razem,
            "Paczki Średnia": paczki_srednia,
            "Postój (10-30m)": paczki_postoj,
            "Błędy (System/Noc)": paczki_bledy,
            "Długie Przerwy": przerwy,
            "Godziny": godziny
        })
    
    df_stats = pd.DataFrame(ranking_data)
    
    # Agregacja
    final_stats = df_stats.groupby('Osoba').agg({
        'Paczki Razem': 'sum',
        'Paczki Średnia': 'sum',
        'Postój (10-30m)': 'sum',
        'Błędy (System/Noc)': 'sum',
        'Długie Przerwy': 'sum',
        'Godziny': 'sum'
    }).reset_index()
    
    final_stats['Wydajnosc'] = final_stats['Paczki Średnia'] / final_stats['Godziny']
    final_stats['Wydajnosc'] = final_stats['Wydajnosc'].fillna(0)
    final_stats = final_stats.sort_values('Wydajnosc', ascending=False)

    # KPI Globalne
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📦 Paczki Razem", int(final_stats['Paczki Razem'].sum()))
    
    srednia_globalna = final_stats['Paczki Średnia'].sum() / final_stats['Godziny'].sum() if final_stats['Godziny'].sum() > 0 else 0
    c2.metric("⏱️ Średnia (Netto)", f"{srednia_globalna:.1f}")
    c3.metric("⚠️ Błędy / Noc", int(final_stats['Błędy (System/Noc)'].sum()))
    c4.metric("🚫 Postoje", int(final_stats['Postój (10-30m)'].sum()))

    st.markdown("---")

    tab1, tab2 = st.tabs(["📊 Raport Wydajności", "📦 Raport Kartonów"])

    with tab1:
        col1, col2 = st.columns([1, 2])
        col1.bar_chart(df.groupby('Osoba')['Paczki'].sum(), color="#0078d4")
        
        col2.dataframe(
            final_stats,
            column_config={
                "Paczki Razem": st.column_config.ProgressColumn("Paczki", format="%d", max_value=int(final_stats['Paczki Razem'].max()) if not final_stats.empty else 100),
                "Błędy (System/Noc)": st.column_config.NumberColumn("Błędy", format="%d 🛑", help="Duplikaty lub poza godz. 05:00-18:00"),
                "Postój (10-30m)": st.column_config.NumberColumn("Postój", format="%d ⏳", help="Paczki po postoju 10-30m (nie wliczane do średniej)."),
                "Długie Przerwy": st.column_config.NumberColumn("Przerwy >30m", format="%d ☕"),
                "Wydajnosc": st.column_config.NumberColumn("Wydajność/h", format="%.1f"),
                "Godziny": st.column_config.NumberColumn("Czas Netto", format="%.1f h"),
                "Paczki Średnia": st.column_config.NumberColumn("Baza Średniej", format="%d")
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.write("### 🕵️‍♂️ Szczegóły dnia")
        st.dataframe(
            df_stats.sort_values(['Data', 'Osoba'], ascending=False),
            column_config={
                "Data": st.column_config.DateColumn("Data"),
                "Godziny": st.column_config.NumberColumn("Godziny", format="%.2f h"),
                "Błędy (System/Noc)": st.column_config.NumberColumn("Błędy/Noc", format="%d")
            },
            use_container_width=True
        )

    with tab2:
        kartony = df.groupby('Karton')['Paczki'].sum().reset_index().sort_values('Paczki', ascending=False)
        c_k1, c_k2 = st.columns([2, 1])
        c_k1.bar_chart(kartony.set_index('Karton'), color="#0078d4")
        c_k2.dataframe(kartony, hide_index=True, use_container_width=True)

else:
    st.info("Brak danych do wyświetlenia. Odśwież API lub zmień filtry.")
