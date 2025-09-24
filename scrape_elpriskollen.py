from playwright.sync_api import sync_playwright
import time
import json
import pandas as pd
import re
import os

# ===== SWEDISH COUNTIES & ZIP CODES =====
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


# ===== CONFIG =====
CONSUMPTION_KWH = "2000"  # You can change this
HEADLESS_MODE = True     # Set to True for faster background runs
DELAY_BETWEEN_ZIPS = 5    # Seconds to pause between ZIPs (be kind to server)

def scrape_for_zip(page, zip_info):
    """
    Scrapes all data for one ZIP code across multiple consumption levels.
    Returns list of scraped records.
    """
    zip_code = zip_info["zip_code"]
    county = zip_info["county"]
    town = zip_info["town"]

    # ✅ THREE CONSUMPTION LEVELS
    CONSUMPTION_LEVELS = ["2000", "3000", "5000"]
    all_results_for_zip = []

    for consumption in CONSUMPTION_LEVELS:
        print(f"\n🔁 Scraping {county} ({town}) - ZIP: {zip_code} - Consumption: {consumption} kWh")

        # Step 1: Go to homepage
        page.goto("https://elpriskollen.se/", timeout=60000)
        try:
            cookie_button = page.locator('button.env-button:has-text("Godkänn alla kakor")')
            if cookie_button.is_visible(timeout=3000):
                cookie_button.click()
                print("🍪 Accepted cookies")
                page.wait_for_timeout(1000)
        except Exception as e:
            print("ℹ️ No cookie banner found or failed to click:", str(e))        
        # Step 2: Enter ZIP code
        page.fill("#pcode", zip_code)
        page.click("#next-page")
        page.wait_for_timeout(2000)
        time.sleep(5)

        # Step 3: Enter consumption
        page.fill("#annual_consumption", consumption)
        page.click("#next-page")
        page.wait_for_timeout(2000)
        time.sleep(5)
        # Step 4: Click 3rd contract type button (Mixavtal)
        page.click("#app > div > div.guide__preamble > div.env-form-element > div.contractTypeButtons > a:nth-child(3)")
        page.wait_for_timeout(2000)
        time.sleep(5)
        # Step 5: Click final "Nästa" button
        page.click("#app > div > div.epk-button > a.env-button")
        page.wait_for_timeout(3000)
        time.sleep(30)
        # Step 6: Scroll and click "Show more" until no more available
        while True:
            try:
                show_more = page.locator("button.env-button:has-text('Visa mer'), button.env-button:has-text('Show more')").first

                if show_more.is_visible():
                    # Scroll to 90% of page height
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.9)")
                    page.wait_for_timeout(500)
                    show_more.scroll_into_view_if_needed()
                    show_more.click()
                    print("✅ Clicked 'Show more' — loading more contracts...")
                    page.wait_for_timeout(2000)
                else:
                    print("⏹️ No more 'Show more' buttons found.")
                    break

            except Exception as e:
                print(f"⏹️ Stopping 'Show more' loop — {e}")
                break

        # Step 7: Collect all profile URLs + CONTRACT DURATION from main page
        profile_cards = page.locator("div.pLyFbiEj6YnPeSF9DI94").all()
        urls_and_durations = []

        for card in profile_cards:
            try:
                # Extract contract duration (e.g., "1 år", "3 månader")
                duration = None
                try:
                    text_content = card.inner_text()
                    match = re.search(r'(\d+\s*(?:år|månader))', text_content)
                    if match:
                        duration = match.group(1)
                except:
                    pass

                # Extract URL
                link = card.locator("div.aVZNlNTkwbkNs_DcrCqg > a.env-button")
                href = link.get_attribute("href")
                if href:
                    full_url = "https://elpriskollen.se" + href
                    urls_and_durations.append({
                        "url": full_url,
                        "contract_duration": duration
                    })
            except Exception as e:
                print(f"⚠️ Error extracting card: {e}")
                continue

        # Step 8: Visit each profile and scrape detailed data
        results = []
        for item in urls_and_durations:
            url = item["url"]
            contract_duration = item["contract_duration"]

            try:
                page.goto(url, timeout=60000)
                page.wait_for_timeout(2000)

                # --- SCRAPE PROFILE DATA ---

                # Contract Type, Electrical Area, Contract Name
                try:
                    header_divs = page.locator("div.SvveEH5y1QdtM2MuMz07 div.e3icZ8YXD7PTtS8321U3 div.AOqumsb2RS0O78r9kzMX").all()
                    contract_type = header_divs[0].inner_text() if len(header_divs) > 0 else None
                    electrical_area = header_divs[1].inner_text() if len(header_divs) > 1 else None
                except:
                    contract_type = None
                    electrical_area = None

                try:
                    contract_name = page.locator("div.SvveEH5y1QdtM2MuMz07 h1").inner_text()
                except:
                    contract_name = None

                # Provider
                try:
                    provider_name = page.locator("div.AWGCPcYaBUXjAUTBLl0c h3").inner_text()
                except:
                    provider_name = None

                # Jämförpris & Consumption
                try:
                    jämförpris_block = page.locator("div.gdeuxYpfTrq6O5EdKun6 h2").first.inner_text()
                except:
                    jämförpris_block = None

                try:
                    consumption_info = page.locator("div.gdeuxYpfTrq6O5EdKun6 p").first.inner_text()
                except:
                    consumption_info = None

                # Price Breakdown Table
                price_breakdown = {}
                try:
                    rows = page.locator("table.env-table.env-table--zebra tbody tr").all()
                    for row in rows:
                        try:
                            key = row.locator("td").nth(0).inner_text().strip()
                            val = row.locator("td").nth(1).inner_text().strip()
                            price_breakdown[key] = val
                        except:
                            pass
                except:
                    pass

                # Contact Info
                try:
                    provider_phone = page.locator("div.AWGCPcYaBUXjAUTBLl0c h4:has-text('Telefon') + a").inner_text()
                except:
                    provider_phone = None

                try:
                    provider_email_elem = page.locator("div.AWGCPcYaBUXjAUTBLl0c h4:has-text('E-post') + a")
                    provider_email = provider_email_elem.get_attribute("href")
                    if provider_email and provider_email.startswith("mailto:"):
                        provider_email = provider_email.replace("mailto:", "")
                except:
                    provider_email = None

                # Action Links (Change, Terms, Website)
                try:
                    action_links = page.locator("div.Tgc321GpCPUvHqOKChsl a[target='_blank']").all()
                    change_contract_link = action_links[0].get_attribute("href") if len(action_links) > 0 else None
                    terms_link = action_links[1].get_attribute("href") if len(action_links) > 1 else None
                    supplier_website = action_links[2].get_attribute("href") if len(action_links) > 2 else None
                except:
                    change_contract_link = None
                    terms_link = None
                    supplier_website = None

                # Energy Sources
                energy_sources = []
                try:
                    energy_keywords = ["förnybar", "vatten", "vind", "solkraft", "kärnkraft", "fossilt", "residualmix"]
                    page_text = page.inner_text("body").lower()
                    for keyword in energy_keywords:
                        if keyword in page_text:
                            energy_sources.append(keyword.capitalize())
                    energy_sources = list(set(energy_sources))
                except:
                    pass

                # Extract Notice Period, Billing, Payment, Expiry from text
                notice_period = None
                billing_options = None
                payment_options = None
                expiry_info = None

                try:
                    page_text = page.inner_text("body")

                    if "uppsägningstid" in page_text.lower():
                        match = re.search(r'uppsägningstid[:\s]*([^\n\.]+)', page_text, re.IGNORECASE)
                        if match:
                            notice_period = match.group(1).strip()

                    if "fakturering" in page_text.lower():
                        if "månadsvis" in page_text.lower():
                            billing_options = "Månadsvis i efterskott"

                    if any(word in page_text.lower() for word in ["betalning", "autogiro", "swish", "faktura"]):
                        payment_options = "Autogiro, Swish, Faktura (se villkor)"

                    if "tillsvidare" in page_text.lower() or "förlängs automatiskt" in page_text.lower():
                        expiry_info = "Övergår till tillsvidare avtal vid utgång"

                except Exception as e:
                    print(f"⚠️ Error extracting text info: {e}")

                # ✅ ADD GEOGRAPHIC CONTEXT + CONSUMPTION
                data = {
                    "scraped_zip_code": zip_code,
                    "scraped_county": county,
                    "scraped_town": town,
                    "scraped_consumption_kwh": consumption,  # <-- NEW: Track consumption level
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
                    "billing_options": billing_options,
                    "payment_options": payment_options,
                    "expiry_info": expiry_info,
                    "change_contract_link": change_contract_link,
                    "terms_link": terms_link,
                    "supplier_website": supplier_website,
                    "provider_phone": provider_phone,
                    "provider_email": provider_email
                }

                results.append(data)
                print(f"✅ Scraped: {contract_name or 'Unknown'}")

            except Exception as e:
                print(f"❌ Error scraping {url}: {e}")
                continue

        print(f"🎉 Done for {zip_code} @ {consumption} kWh — Scraped {len(results)} profiles.")
        all_results_for_zip.extend(results)

        # Optional: Pause between consumption levels
        if CONSUMPTION_LEVELS.index(consumption) < len(CONSUMPTION_LEVELS) - 1:
            print(f"⏳ Waiting 3 seconds before next consumption level...")
            time.sleep(3)

    return all_results_for_zip
def save_individual_output(data, zip_code):
    """Save individual JSON and Excel files per ZIP"""
    # JSON
    json_filename = f"output_{zip_code}.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Excel
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
    excel_filename = f"output_{zip_code}.xlsx"
    df.to_excel(excel_filename, index=False, engine="openpyxl")

    return json_filename, excel_filename

def save_combined_output(all_data):
    """Save one master JSON and Excel with all ZIPs combined"""
    # JSON
    with open("combined_output.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    # Excel
    flat_data = []
    for item in all_data:
        flat = item.copy()
        price_bd = flat.pop("price_breakdown", {})
        for k, v in price_bd.items():
            flat[f"price_{k.replace(' ', '_').replace('/', '_')}"] = v
        energy_sources = flat.pop("energy_sources", [])
        flat["energy_sources"] = "; ".join(energy_sources) if energy_sources else None
        flat_data.append(flat)

    df = pd.DataFrame(flat_data)
    df.to_excel("combined_output.xlsx", index=False, engine="openpyxl")

    print("\n📊 Combined files saved: combined_output.json, combined_output.xlsx")

def run():
    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE)
        page = browser.new_page()

        for zip_info in COUNTIES:
            try:
                # Scrape for current ZIP
                results = scrape_for_zip(page, zip_info)
                all_results.extend(results)

                # Save individual files
                save_individual_output(results, zip_info["zip_code"])

                # Pause before next ZIP (be respectful)
                if COUNTIES.index(zip_info) < len(COUNTIES) - 1:
                    print(f"\n⏳ Waiting {DELAY_BETWEEN_ZIPS} seconds before next ZIP...")
                    time.sleep(DELAY_BETWEEN_ZIPS)

            except Exception as e:
                print(f"🔥 CRITICAL ERROR on {zip_info['zip_code']}: {e}")
                continue

        browser.close()

    # Save combined files
    save_combined_output(all_results)

    print(f"\n✅✅✅ ALL DONE! Total records scraped: {len(all_results)}")
    print("📁 Individual files: output_XXXXX.json/.xlsx")
    print("📁 Combined files: combined_output.json/.xlsx")


if __name__ == "__main__":
    run()
