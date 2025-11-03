# --------------------------------------------------------------
# scrape_elpriskollen.py
# FULLY WORKING – WITH FAST PRIS 5-YEAR DURATION FIX
# --------------------------------------------------------------
# Runs 1 ZIP → 3 consumptions → 5 contract types (15 total)
# - Special handling: FAST PRIS → clicks "5 years" before continue
# - Headless = OFF by default (for testing)
# - Saves: combined_output.json + combined_output.xlsx
# --------------------------------------------------------------

from playwright.sync_api import sync_playwright
import time
import json
import pandas as pd
import re
import os
import sys
import subprocess

# ==================== CONFIGURATION ====================

COUNTIES = [
    {"county": "Stockholm län", "town": "Stockholm", "zip_code": "11121"},
    {"county": "Uppsala län", "town": "Uppsala", "zip_code": "75310"},
    {"county": "Södermanlands län", "town": "Nyköping", "zip_code": "61131"},
    {"county": "Östergötlands län", "town": "Linköping", "zip_code": "58222"},
    {"county": "Jönköpings län", "town": "Jönköping", "zip_code": "55315"},
    {"county": "Kronobergs län", "town": "Växjö", "zip_code": "35222"},
    {"county": "Kalmar län", "town": "Kalmar", "zip_code": "39231"},
    {"county": "Gotlands län", "town": "Visby", "zip_code": "62157"},
    {"county": "Blekinge län", "town": "Karlskrona", "zip_code": "37131"},
    {"county": "Skåne län", "town": "Malmö", "zip_code": "21122"},
    {"county": "Hallands län", "town": "Halmstad", "zip_code": "30243"},
    {"county": "Västra Götalands län", "town": "Göteborg", "zip_code": "41103"},
    {"county": "Värmlands län", "town": "Karlstad", "zip_code": "65224"},
    {"county": "Örebro län", "town": "Örebro", "zip_code": "70210"},
    {"county": "Västmanlands län", "town": "Västerås", "zip_code": "72211"},
    {"county": "Dalarnas län", "town": "Falun", "zip_code": "79171"},
    {"county": "Gävleborgs län", "town": "Gävle", "zip_code": "80320"},
    {"county": "Västernorrlands län", "town": "Härnösand", "zip_code": "87131"},
    {"county": "Jämtlands län", "town": "Östersund", "zip_code": "83131"},
    {"county": "Västerbottens län", "town": "Umeå", "zip_code": "90327"},
    {"county": "Norrbottens län", "town": "Luleå", "zip_code": "97231"},
]

# HEADLESS = OFF by default (you SEE the browser)
HEADLESS_MODE = os.getenv("HEADLESS", "false").lower() == "true"

# ZIP_INDEX: 0 to 20
ZIP_INDEX = int(os.getenv("ZIP_INDEX", "0"))

if ZIP_INDEX >= len(COUNTIES):
    print(f"Invalid ZIP_INDEX {ZIP_INDEX}. Must be 0–20.")
    sys.exit(0)

SELECTED_ZIP = COUNTIES[ZIP_INDEX]

# --------------------------------------------------------------
def save_combined_output(all_data):
    # JSON
    with open("combined_output.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    # Excel (flatten price_breakdown)
    flat = []
    for item in all_data:
        row = item.copy()
        pb = row.pop("price_breakdown", {})
        for k, v in pb.items():
            col = f"price_{k.replace(' ', '_').replace('/', '_')}"
            row[col] = v
        es = row.pop("energy_sources", [])
        row["energy_sources"] = "; ".join(es) if es else ""
        flat.append(row)

    df = pd.DataFrame(flat)
    df.to_excel("combined_output.xlsx", index=False, engine="openpyxl")
    print(f"Saved {len(all_data)} records → JSON + Excel")

# --------------------------------------------------------------
def scrape_for_zip(page, zip_info):
    zip_code = zip_info["zip_code"]
    county = zip_info["county"]
    town = zip_info["town"]

    CONSUMPTION_LEVELS = ["2000", "5000", "20000"]
    CONTRACT_TYPES = [
        "KVARTSPRIS",
        "TIMPRIS",
        "RÖRLIGT PRIS (MÅNADSBASERAT)",
        "MIXAT PRIS 1 ÅR",
        "FAST PRIS"
    ]

    all_results = []

    for consumption in CONSUMPTION_LEVELS:
        for idx, contract_name in enumerate(CONTRACT_TYPES, start=1):
            print(f"\nScraping: {town} ({zip_code}) | {consumption} kWh | {contract_name}")

            # --- 1. Go to homepage ---
            page.goto("https://elpriskollen.se/", timeout=60000)
            time.sleep(3)

            # --- 2. Cookie banner ---
            try:
                cookie_btn = page.get_by_role("button", name="Godkänn alla kakor")
                cookie_btn.wait_for(state="visible", timeout=10000)
                cookie_btn.click()
                page.wait_for_timeout(1000)
            except Exception:
                pass

            # --- 3. Enter ZIP ---
            page.fill("#pcode", zip_code)
            page.click("#next-page")
            page.wait_for_timeout(2000)

            # --- 4. Enter consumption ---
            page.fill("#annual_consumption", consumption)
            page.click("#next-page")
            page.wait_for_timeout(2000)

            # --- 5. Select contract type ---
            contract_selector = f".contractTypeButtons > a.selectButton:nth-child({idx})"
            try:
                page.wait_for_selector(contract_selector, timeout=10000)
                page.click(contract_selector)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"Failed to click {contract_name}: {e}")
                continue

            # --- 6. FAST PRIS: Select 5-year duration ---
            if contract_name == "FAST PRIS":
                print("  → FAST PRIS: selecting 5-year duration")
                try:
                    duration_btn = page.locator(
                        "#app > div > div.guide__preamble > div.env-form-element > "
                        "div.fastaDesktop > div.contractTypeFastChild > div:nth-child(6) > a"
                    )
                    duration_btn.wait_for(state="visible", timeout=10000)
                    duration_btn.click()
                    page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"  Could not select 5-year duration: {e}")

            page.wait_for_timeout(1000)

            # --- 7. Click "Fortsätt" ---
            try:
                continue_btn = page.locator("#app > div > div.epk-button > a.env-button")
                continue_btn.wait_for(state="visible", timeout=10000)
                continue_btn.click()
                page.wait_for_timeout(3000)
                time.sleep(15)  # Wait for results
            except Exception as e:
                print(f"Failed to click Fortsätt: {e}")
                continue

            # --- 8. "Visa mer" loop ---
            while True:
                try:
                    show_more = page.locator(
                        "button.env-button:has-text('Visa mer'), "
                        "button.env-button:has-text('Show more')"
                    ).first
                    if show_more.is_visible(timeout=3000):
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.9)")
                        page.wait_for_timeout(500)
                        show_more.scroll_into_view_if_needed()
                        show_more.click()
                        page.wait_for_timeout(2000)
                    else:
                        break
                except Exception:
                    break

            # --- 9. Collect profile cards ---
            profile_cards = page.locator("div.pLyFbiEj6YnPeSF9DI94").all()
            urls_and_durations = []

            for card in profile_cards:
                try:
                    text = card.inner_text()
                    duration = re.search(r'(\d+\s*(?:år|månader))', text)
                    duration = duration.group(1) if duration else None

                    link = card.locator("div.aVZNlNTkwbkNs_DcrCqg > a.env-button")
                    href = link.get_attribute("href")
                    if href:
                        full_url = "https://elpriskollen.se" + href.strip()
                        urls_and_durations.append({"url": full_url, "contract_duration": duration})
                except Exception:
                    continue

            print(f"  Found {len(urls_and_durations)} contracts")

            # --- 10. Scrape each detail page ---
            for item in urls_and_durations:
                url = item["url"]
                contract_duration = item["contract_duration"]
                try:
                    page.goto(url, timeout=60000)
                    page.wait_for_timeout(2500)

                    # Header
                    contract_type = electrical_area = None
                    try:
                        headers = page.locator(
                            "div.SvveEH5y1QdtM2MuMz07 div.e3icZ8YXD7PTtS8321U3 "
                            "div.AOqumsb2RS0O78r9kzMX"
                        ).all()
                        contract_type = headers[0].inner_text().strip() if len(headers) > 0 else None
                        electrical_area = headers[1].inner_text().strip() if len(headers) > 1 else None
                    except Exception:
                        pass

                    contract_name = page.locator("div.SvveEH5y1QdtM2MuMz07 h1").inner_text().strip()
                    provider_name = page.locator("div.AWGCPcYaBUXjAUTBLl0c h3").inner_text().strip()
                    jämförpris_block = page.locator("div.gdeuxYpfTrq6O5EdKun6 h2").first.inner_text().strip()
                    consumption_info = page.locator("div.gdeuxYpfTrq6O5EdKun6 p").first.inner_text().strip()

                    # Price table
                    price_breakdown = {}
                    try:
                        rows = page.locator("table.env-table.env-table--zebra tbody tr").all()
                        for r in rows:
                            cells = r.locator("td").all()
                            if len(cells) >= 2:
                                k = cells[0].inner_text().strip()
                                v = cells[1].inner_text().strip()
                                price_breakdown[k] = v
                    except Exception:
                        pass

                    # Contact
                    provider_phone = None
                    try:
                        provider_phone = page.locator(
                            "div.AWGCPcYaBUXjAUTBLl0c h4:has-text('Telefon') + a"
                        ).inner_text().strip()
                    except Exception:
                        pass

                    provider_email = None
                    try:
                        mail_href = page.locator(
                            "div.AWGCPcYaBUXjAUTBLl0c h4:has-text('E-post') + a"
                        ).get_attribute("href")
                        if mail_href and mail_href.startswith("mailto:"):
                            provider_email = mail_href[7:].strip()
                    except Exception:
                        pass

                    # Links
                    change_link = terms_link = website_link = None
                    try:
                        links = page.locator("div.Tgc321GpCPUvHqOKChsl a[target='_blank']").all()
                        change_link = links[0].get_attribute("href") if len(links) > 0 else None
                        terms_link = links[1].get_attribute("href") if len(links) > 1 else None
                        website_link = links[2].get_attribute("href") if len(links) > 2 else None
                    except Exception:
                        pass

                    # Energy sources
                    energy_sources = []
                    try:
                        body_text = page.inner_text("body").lower()
                        for kw in ["förnybar", "vatten", "vind", "solkraft", "kärnkraft", "fossilt", "residualmix"]:
                            if kw in body_text:
                                energy_sources.append(kw.capitalize())
                        energy_sources = list(set(energy_sources))
                    except Exception:
                        pass

                    # Text fields
                    notice_period = billing = payment = expiry = None
                    try:
                        txt = page.inner_text("body").lower()
                        m = re.search(r'uppsägningstid[:\s]*([^\n\.]+)', txt)
                        if m:
                            notice_period = m.group(1).strip()
                        if "fakturering" in txt and "månadsvis" in txt:
                            billing = "Månadsvis i efterskott"
                        if any(w in txt for w in ["betalning", "autogiro", "swish"]):
                            payment = "Autogiro, Swish, Faktura"
                        if "tillsvidare" in txt or "förlängs automatiskt" in txt:
                            expiry = "Övergår till tillsvidare avtal vid utgång"
                    except Exception:
                        pass

                    # Save record
                    record = {
                        "scraped_zip_code": zip_code,
                        "scraped_county": county,
                        "scraped_town": town,
                        "scraped_consumption_kwh": consumption,
                        "selected_contract_type": contract_name,
                        "url": url,
                        "title": page.title(),
                        "contract_duration": contract_duration,
                        "contract_type": contract_type,
                        "electrical_area": electrical_area,
                        "contract_name": contract_name,
                        "provider_name": provider_name,
                        "consumption_info": consumption_info,
                        "jämförpris": jämförpris_block,
                        "energy_sources": energy_sources,
                        "price_breakdown": price_breakdown,
                        "notice_period": notice_period,
                        "billing_options": billing,
                        "payment_options": payment,
                        "expiry_info": expiry,
                        "change_contract_link": change_link,
                        "terms_link": terms_link,
                        "supplier_website": website_link,
                        "provider_phone": provider_phone,
                        "provider_email": provider_email,
                    }
                    all_results.append(record)
                    print(f"  Scraped: {contract_name}")

                except Exception as e:
                    print(f"  Error on detail page {url}: {e}")
                    continue

            print(f"  Finished: {consumption} kWh – {contract_name}")

    return all_results

# --------------------------------------------------------------
def run():
    all_data = []

    with sync_playwright() as p:
        print(f"Launching browser (headless={HEADLESS_MODE})...")
        browser = p.chromium.launch(headless=HEADLESS_MODE)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            results = scrape_for_zip(page, SELECTED_ZIP)
            all_data.extend(results)
        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
        finally:
            browser.close()

    save_combined_output(all_data)
    print(f"\nALL DONE! Total records: {len(all_data)}")

    # Upload to Google Sheets
    try:
        subprocess.run([sys.executable, "upload_to_sheets.py"], check=True)
        print("Google Sheets upload triggered")
    except Exception as e:
        print(f"Upload failed: {e}")

if __name__ == "__main__":
    run()
