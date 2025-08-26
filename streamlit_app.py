# streamlit_app.py
# -------------------------------------------------------------
# Controlling: agregacja kosztów wg OPK
# Backend danych: Supabase (PostgreSQL przez Supabase)
# UI/hosting: Streamlit (np. Streamlit Community Cloud po podpięciu repo GitHub)
# -------------------------------------------------------------

from __future__ import annotations
import io
from typing import Optional, List
import pandas as pd
import streamlit as st
from datetime import date, datetime

from supabase import create_client, Client

# -------------------------
# Konfiguracja & połączenie
# -------------------------
# Sekrety ustaw w .streamlit/secrets.toml (lokalnie) lub w Streamlit Cloud → Settings → Secrets
# [supabase]
# url = "https://YOUR-PROJECT-REF.supabase.co"
# key = "YOUR-ANON-KEY"

st.set_page_config(page_title="Controlling OPK", layout="wide")
st.title("📊 Controlling OPK — Streamlit + Supabase")

try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error("Brak konfiguracji Supabase. Ustaw [supabase].url i [supabase].key w Secrets.")
    st.stop()

# -------------------------
# Pomocnicze funkcje
# -------------------------
NORMALIZE_MAP = {
    "data otrzymania": "Data",
    "nazwa:towar": "Nazwa",
    "cena netto [pln]": "Kwota",
    "id opk": "ID_OPK",
    # Dodatkowe warianty (opcjonalnie)
    "data": "Data",
    "nazwa": "Nazwa",
    "kwota": "Kwota",
    "id_opk": "ID_OPK",
    "idopk": "ID_OPK",
}

REQUIRED = ["Data", "Nazwa", "Kwota", "ID_OPK"]

def normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    cols = []
    for c in df.columns:
        key = str(c).strip().lower()
        cols.append(NORMALIZE_MAP.get(key, c))
    df.columns = cols
    return df

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_headers(df)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Brak kolumn: {missing}. Oczekiwane: {REQUIRED}")

    df = df.copy()
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.date
    df["Kwota"] = pd.to_numeric(df["Kwota"], errors="coerce")
    df["ID_OPK"] = df["ID_OPK"].astype(str).str.strip()
    df["Nazwa"] = df["Nazwa"].astype(str)
    df = df.dropna(subset=["Data", "Kwota", "ID_OPK"]).reset_index(drop=True)
    return df

# -------------------------
# Warstwa DB: Supabase
# -------------------------
@st.cache_data(ttl=300)
def db_fetch_date_range(min_only: bool = False, max_only: bool = False):
    res = sb.table("costs").select("Data").execute()
    if not res.data:
        return None if (min_only or max_only) else (None, None)
    s = pd.DataFrame(res.data)
    s["Data"] = pd.to_datetime(s["Data"]).dt.date
    if min_only:
        return s["Data"].min()
    if max_only:
        return s["Data"].max()
    return s["Data"].min(), s["Data"].max()

def db_insert_costs(df: pd.DataFrame):
    payload = df.copy()
    payload["Data"] = payload["Data"].astype(str)  # ISO
    if "Numer dokumentu" in payload.columns:
        payload.rename(columns={"Numer dokumentu": "Numer_dokumentu"}, inplace=True)
    keep_cols = [c for c in ["Numer_dokumentu", "Data", "Nazwa", "Kwota", "ID_OPK"] if c in payload.columns]
    payload = payload[keep_cols]

    CHUNK = 1000
    for i in range(0, len(payload), CHUNK):
        chunk = payload.iloc[i:i+CHUNK].to_dict(orient="records")
        sb.table("costs").insert(chunk).execute()

@st.cache_data(ttl=300)
def db_fetch_distinct_opk() -> List[str]:
    res = sb.table("costs").select("ID_OPK").execute()
    ids = sorted(pd.DataFrame(res.data)["ID_OPK"].astype(str).unique().tolist()) if res.data else []
    return ids

@st.cache_data(ttl=300)
def db_fetch_filtered(date_from: Optional[date], date_to: Optional[date], selected_opk: Optional[List[str]]):
    res = sb.table("costs").select("*").execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=["Data","Nazwa","Kwota","ID_OPK"])
    if df.empty:
        return df
    df["Data"] = pd.to_datetime(df["Data"]).dt.date
    df["Kwota"] = pd.to_numeric(df["Kwota"], errors="coerce")
    df["ID_OPK"] = df["ID_OPK"].astype(str)
    if date_from:
        df = df[df["Data"] >= date_from]
    if date_to:
        df = df[df["Data"] <= date_to]
    if selected_opk:
        df = df[df["ID_OPK"].isin(selected_opk)]
    return df.reset_index(drop=True)

# -------------------------
# UI: wgrywanie, filtry, agregacje
# -------------------------
with st.sidebar:
    st.header("Dane wejściowe")
    upl = st.file_uploader("Wgraj plik XLSX", type=["xlsx"])
    st.caption("Oczekiwane kolumny: Data otrzymania, Nazwa:Towar, Cena netto [PLN], ID OPK (+ ew. Numer dokumentu)")

    if upl is not None:
        try:
            raw = pd.read_excel(io.BytesIO(upl.read()))
            df = normalize_headers(raw)
            if "Numer dokumentu" in raw.columns and "Numer dokumentu" not in df.columns:
                df["Numer dokumentu"] = raw["Numer dokumentu"]
            df = ensure_schema(df)
            with st.spinner("Zapis do bazy Supabase…"):
                db_insert_costs(df)
            st.success(f"Zaimportowano {len(df)} wierszy do bazy.")
            db_fetch_distinct_opk.clear()
            db_fetch_date_range.clear()
            db_fetch_filtered.clear()
        except Exception as e:
            st.error(f"Błąd importu: {e}")

min_d, max_d = db_fetch_date_range() or (None, None)
col1, col2, col3 = st.columns([1,1,2])
with col1:
    d_from = st.date_input("Od", value=min_d or date(2025,1,1))
with col2:
    d_to = st.date_input("Do", value=max_d or date.today())
with col3:
    opk_all = db_fetch_distinct_opk()
    selected = st.multiselect("Wybierz OPK (opcjonalnie)", options=opk_all)

base = db_fetch_filtered(d_from, d_to, selected)

st.subheader("Szczegóły (dane źródłowe)")
st.dataframe(base, use_container_width=True)

summary = (
    base.groupby(["ID_OPK"], as_index=False)["Kwota"]
    .sum()
    .rename(columns={"Kwota": "Suma_Kwota"})
    .sort_values("Suma_Kwota", ascending=False)
)

st.subheader("Suma kosztów wg OPK")
st.dataframe(summary, use_container_width=True)

st.subheader("TOP 10 OPK wg sumy kosztów")
if not summary.empty:
    st.bar_chart(summary.head(10).set_index("ID_OPK")["Suma_Kwota"])

if not base.empty:
    tmp = base.copy()
    tmp["Period"] = pd.to_datetime(tmp["Data"]).astype("datetime64[ns]")
    tmp["Period"] = tmp["Period"].dt.to_period("M").dt.to_timestamp()
    monthly = (
        tmp.pivot_table(index=["ID_OPK"], columns="Period", values="Kwota", aggfunc="sum", fill_value=0)
        .sort_index(axis=1)
        .reset_index()
    )
else:
    monthly = pd.DataFrame()

st.subheader("Trend miesięczny wg OPK")
st.dataframe(monthly, use_container_width=True)

st.download_button(
    label="📥 Pobierz podsumowanie (CSV)",
    data=summary.to_csv(index=False).encode("utf-8"),
    file_name="podsumowanie_opk.csv",
    mime="text/csv",
)

st.download_button(
    label="📥 Pobierz trend miesięczny (CSV)",
    data=monthly.to_csv(index=False).encode("utf-8"),
    file_name="trend_miesieczny_opk.csv",
    mime="text/csv",
)

st.caption("Wskazówka: aby dodać przyjazne nazwy OPK, utwórz tabelę opk_map (ID_OPK, Nazwa_OPK) i dołączaj w widoku po ID_OPK.")
