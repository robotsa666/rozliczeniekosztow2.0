# Controlling OPK — Streamlit + Supabase

Aplikacja do agregacji kosztów wg OPK na podstawie plików XLSX. Frontend: Streamlit. Baza: Supabase (PostgreSQL).

## Struktura repo
- `streamlit_app.py` — główna aplikacja Streamlit.
- `requirements.txt` — zależności Pythona.
- `supabase_schema.sql` — skrypt tworzący tabele w Supabase.
- `.streamlit/secrets.toml.template` — szablon sekretów (nie commituj realnych).
- `sample_data/ko_sample.xlsx` — przykładowy plik danych w prawidłowym formacie.
- `.gitignore` — ignoruje wrażliwe/sezonowe pliki.

## Oczekiwany format XLSX
Kolumny (case-insensitive):
- `Data otrzymania` → mapowane do `Data`
- `Nazwa:Towar` → `Nazwa`
- `Cena netto [PLN]` → `Kwota`
- `ID OPK` → `ID_OPK`
- (opcjonalnie) `Numer dokumentu` → `Numer_dokumentu`

## Szybki start lokalnie
```bash
pip install -r requirements.txt
# Uzupełnij sekrety według .streamlit/secrets.toml.template
streamlit run streamlit_app.py
```

## Supabase — schema
Uruchom `supabase_schema.sql` w Supabase → SQL Editor.

## Deploy: GitHub → Streamlit Community Cloud
1. Wgraj to repo na GitHub.
2. W **Streamlit Cloud** podłącz repo. Wybierz `streamlit_app.py` jako Main file.
3. W **Settings → Secrets** wklej:
   ```toml
   [supabase]
   url = "https://YOUR-PROJECT-REF.supabase.co"
   key = "YOUR-ANON-KEY"
   ```
4. Otwórz aplikację, wgraj plik `.xlsx` i korzystaj.

### Dodatkowe usprawnienia (opcjonalnie)
- Tabela `opk_map (ID_OPK, Nazwa_OPK)` i join po `ID_OPK`.
- Idempotentny import (unikalny hash wiersza + `on conflict do nothing`).
- Uwierzytelnianie użytkowników (Supabase Auth).
