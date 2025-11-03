# upload_to_sheets.py
import json
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os

# === CONFIG ===
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1CpRBgEPTQRE96PnitwTfE8ZzpSOAgUR11-m-9uL43Z4/edit?gid=0#gid=0"
JSON_INPUT = "combined_output.json"

def upload_to_google_sheet():
    print("Loading data...")
    try:
        with open(JSON_INPUT, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"{JSON_INPUT} not found.")
        return

    if not data:
        print("No data.")
        return

    # Flatten
    flat_data = []
    for item in data:
        flat = item.copy()
        pb = flat.pop("price_breakdown", {})
        for k, v in pb.items():
            flat[f"price_{k.replace(' ', '_').replace('/', '_')}"] = v
        es = flat.pop("energy_sources", [])
        flat["energy_sources"] = "; ".join(es) if es else ""
        flat_data.append(flat)

    df = pd.DataFrame(flat_data).fillna("").astype(str).replace("nan", "")

    scrape_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    df.insert(0, "scrape_datetime", scrape_date)
    df.insert(1, "zip_code", data[0].get("scraped_zip_code", ""))

    # Auth
    creds = Credentials.from_service_account_file("credentials.json", scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    sheet = client.open_by_url(GOOGLE_SHEET_URL).sheet1

    # Append
    sheet.append_rows(df.values.tolist(), value_input_option="USER_ENTERED")
    print(f"Appended {len(df)} rows for ZIP {data[0].get('scraped_zip_code')}")

if __name__ == "__main__":
    upload_to_google_sheet()
