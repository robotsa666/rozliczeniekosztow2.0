# streamlit_app.py (patched: Supabase column names lowercase)
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
from datetime import date

from supabase import create_client, Client

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
    "data otrzymania": "data",
    "nazwa:towar": "nazwa",
    "cena netto [pln]": "kwota",
    "id opk": "id_opk",
    "data": "data",
    "nazwa": "nazwa",
    "kwota": "kwota",
    "id_opk": "id_opk",
    "idopk": "id_opk",
}

REQUIRED = ["data", "nazwa", "kwota", "id_opk"]

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
    df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    df["kwota"] = pd.to_numeric(df["kwota"], errors="coerce")
    df["id_opk"] = df["id_opk"].astype(str).str.strip()
    df["nazwa"] = df["nazwa"].astype(str)
    df = df.dropna(subset=["data", "kwota", "id_opk"]).reset_index(drop=True)
    return df

# -------------------------
# Warstwa DB: Supabase
# -------------------------
@st.cache_data(ttl=300)
def db_fetch_date_range(min_only: bool = False, max_only: bool = False):
    res = sb.table("costs").select("data").execute()
    if not res.data:
        return None if (min_only or max_only) else (None, None)
    s = pd.DataFrame(res.data)
    s["data"] = pd.to_datetime(s["data"]).dt.date
    if min_only:
        return s["data"].min()
    if max_only:
        return s["data"].max()
    return s["data"].min(), s["data"].max()

def db_insert_costs(df: pd.DataFrame):
    payload = df.copy()
    payload["data"] = payload["data"].astype(str)
    rename_map = {
        "Numer dokumentu": "numer_dokumentu",
        "data": "data",
        "nazwa": "nazwa",
        "kwota": "kwota",
        "id_opk": "id_opk",
    }
    for k, v in rename_map.items():
        if k in payload.columns:
            payload.rename(columns={k: v}, inplace=True)
    keep = [c for c in ["numer_dokumentu","data","nazwa","kwota","id_opk"] if c in payload.columns]
    payload = payload[keep]

    CHUNK = 1000
    for i in range(0, len(payload), CHUNK):
        chunk = payload.iloc[i:i+CHUNK].to_dict(orient="records")
        sb.table("costs").insert(chunk).execute()

@st.cache_data(ttl=300)
def db_fetch_distinct_opk() -> List[str]:
    res = sb.table("costs").select("id_opk").execute()
    ids = sorted(pd.DataFrame(res.data)["id_opk"].astype(str).unique().tolist()) if res.data else []
    return ids

@st.cache_data(ttl=300)
def db_fetch_filtered(date_from: Optional[date], date_to: Optional[date], selected_opk: Optional[List[str]]):
    res = sb.table("costs").select("*").execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=["data","nazwa","kwota","id_opk"])
    if df.empty:
        return df
    df.columns = [c.lower() for c in df.columns]
    df["data"] = pd.to_datetime(df["data"]).dt.date
    df["kwota"] = pd.to_numeric(df["kwota"], errors="coerce")
    df["id_opk"] = df["id_opk"].astype(str)
    if date_from:
        df = df[df["data"] >= date_from]
    if date_to:
        df = df[df["data"] <= date_to]
    if selected_opk:
        df = df[df["id_opk"].isin(selected_opk)]
    return df.reset_index(drop=True)

# -------------------------
# UI
# -------------------------
with st.sidebar:
    st.header("Dane wejściowe")
    upl = st.file_uploader("Wgraj plik XLSX", type=["xlsx"])
    if upl is not None:
        try:
            raw = pd.read_excel(io.BytesIO(upl.read()))
            df = normalize_headers(raw)
            if "Numer dokumentu" in raw.columns and "numer_dokumentu" not in df.columns:
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
    base.groupby(["id_opk"], as_index=False)["kwota"]
        .sum()
        .rename(columns={"kwota": "Suma_Kwota"})
        .sort_values("Suma_Kwota", ascending=False)
)

st.subheader("Suma kosztów wg OPK")
st.dataframe(summary, use_container_width=True)

st.subheader("TOP 10 OPK wg sumy kosztów")
if not summary.empty:
    st.bar_chart(summary.head(10).set_index("id_opk")["Suma_Kwota"])

if not base.empty:
    tmp = base.copy()
    tmp["Period"] = pd.to_datetime(tmp["data"]).astype("datetime64[ns]").dt.to_period("M").dt.to_timestamp()
    monthly = (
        tmp.pivot_table(index=["id_opk"], columns="Period", values="kwota", aggfunc="sum", fill_value=0)
           .sort_index(axis=1).reset_index()
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
