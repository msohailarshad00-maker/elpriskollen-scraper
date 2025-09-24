# upload_to_sheets.py
import json
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG ===
CREDENTIALS_FILE = "credentials.json"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1CpRBgEPTQRE96PnitwTfE8ZzpSOAgUR11-m-9uL43Z4/edit?gid=0#gid=0"  # ← REPLACE WITH YOUR SHEET URL
JSON_INPUT = "combined_output.json"

def upload_to_google_sheet():
    print("📤 Loading scraped data...")
    try:
        with open(JSON_INPUT, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ {JSON_INPUT} not found. Run scraper first!")
        return

    if not data:
        print("⚠️ No data to upload.")
        return

    # Flatten price_breakdown
    flat_data = []
    for item in data:
        flat = item.copy()
        price_bd = flat.pop("price_breakdown", {})
        for k, v in price_bd.items():
            flat[f"price_{k.replace(' ', '_').replace('/', '_')}"] = v
        energy_sources = flat.pop("energy_sources", [])
        flat["energy_sources"] = "; ".join(energy_sources) if energy_sources else None
        flat_data.append(flat)

    df = pd.DataFrame(flat_data)

    # Replace NaN, None, NaT with empty string to avoid JSON serialization error
    df = df.fillna("").astype(str)

    # But convert "nan" string back to "" (because .astype(str) turns NaN -> "nan")
    df = df.replace("nan", "")

    scrape_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    df.insert(0, "scrape_datetime", scrape_date)
    # Authenticate
    print("🔑 Authenticating with Google Sheets...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)

    # Open sheet
    sheet = client.open_by_url(GOOGLE_SHEET_URL).sheet1

    # Get existing headers
    existing_headers = sheet.row_values(1) if sheet.row_count > 0 else []

    # Ensure all columns exist
    new_headers = df.columns.tolist()
    missing_headers = [h for h in new_headers if h not in existing_headers]

    if missing_headers:
        print(f"🆕 Adding new columns: {missing_headers}")
        # Append missing headers to row 1
        start_col = len(existing_headers) + 1
        sheet.update(
            f"{gspread.utils.rowcol_to_a1(1, start_col)}:{gspread.utils.rowcol_to_a1(1, start_col + len(missing_headers) - 1)}",
            [missing_headers]
        )
        existing_headers.extend(missing_headers)

    # Reorder df columns to match sheet
    df = df.reindex(columns=existing_headers, fill_value="")

    # Convert to list of lists
    values = [df.columns.tolist()] + df.values.tolist()
    # But we only want to append DATA rows (not header again)
    data_rows = df.values.tolist()

    if data_rows:
        print(f"📈 Appending {len(data_rows)} rows to Google Sheet...")
        sheet.append_rows(data_rows, value_input_option="USER_ENTERED")
        print("✅ Upload successful!")
    else:
        print("⚠️ No rows to append.")

if __name__ == "__main__":
    upload_to_google_sheet()