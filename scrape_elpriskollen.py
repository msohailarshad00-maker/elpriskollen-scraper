from playwright.sync_api import sync_playwright
import time
import json
import pandas as pd
import re
import os

# ===== SWEDISH COUNTIES & ZIP CODES (21 total) =====
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

# Auto headless: False locally, True in GitHub Actions
HEADLESS_MODE = True

# Split into chunks of 4 ZIPs
# One ZIP per job
GROUP_INDEX = int(os.getenv("ZIP_GROUP", "0"))

if GROUP_INDEX >= len(COUNTIES):
    print(f"⚠️ Invalid ZIP index {GROUP_INDEX}. Exiting.")
    exit(0)

SELECTED_COUNTIES = [COUNTIES[GROUP_INDEX]]
print(f"🚀 Running scraper for ZIP index {GROUP_INDEX} ({SELECTED_COUNTIES[0]['zip_code']})")


def scrape_for_zip(page, zip_info):
    zip_code = zip_info["zip_code"]
    county = zip_info["county"]
    town = zip_info["town"]
    CONSUMPTION_LEVELS = ["2000", "20000", "5000"]  # Fixed: was 20000
    all_results_for_zip = []

    for consumption in CONSUMPTION_LEVELS:
        print(f"\n🔁 Scraping {county} ({town}) - ZIP: {zip_code} - {consumption} kWh")
        page.goto("https://elpriskollen.se/", timeout=60000)
        time.sleep(3)

        # Handle cookie banner
        try:
            # Wait up to 10 seconds for the button to appear in DOM AND be visible
            cookie_btn = page.get_by_role("button", name="Godkänn alla kakor")
            cookie_btn.wait_for(state="visible", timeout=10000)
            cookie_btn.click()
            page.wait_for_timeout(1000)
        except Exception as e:
            print("Cookie button not found or not clickable:", e)
        pass

        page.fill("#pcode", zip_code)
        page.click("#next-page")
        page.wait_for_timeout(2000)
        time.sleep(2)
        page.fill("#annual_consumption", consumption)
        page.click("#next-page")
        page.wait_for_timeout(2000)
        time.sleep(2)
        page.click("#app > div > div.guide__preamble > div.env-form-element > div.contractTypeButtons > a:nth-child(3)")
        page.wait_for_timeout(2000)
        time.sleep(2)
        page.click("#app > div > div.epk-button > a.env-button")
        page.wait_for_timeout(3000)
        time.sleep(15)
        # Scroll + click "Show more"
        while True:
            try:
                show_more = page.locator("button.env-button:has-text('Visa mer'), button.env-button:has-text('Show more')").first
                if show_more.is_visible():
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.9)")
                    page.wait_for_timeout(500)
                    show_more.scroll_into_view_if_needed()
                    show_more.click()
                    page.wait_for_timeout(2000)
                else:
                    break
            except:
                break

        # Collect profile cards
        profile_cards = page.locator("div.pLyFbiEj6YnPeSF9DI94").all()
        urls_and_durations = []
        for card in profile_cards:
            try:
                text = card.inner_text()
                duration = None
                match = re.search(r'(\d+\s*(?:år|månader))', text)
                if match:
                    duration = match.group(1)
                link = card.locator("div.aVZNlNTkwbkNs_DcrCqg > a.env-button")
                href = link.get_attribute("href")
                if href:
                    full_url = "https://elpriskollen.se" + href  # Fixed: no extra spaces
                    urls_and_durations.append({"url": full_url, "contract_duration": duration})
            except:
                continue

        # Scrape each profile
        results = []
        for item in urls_and_durations:
            url = item["url"]
            contract_duration = item["contract_duration"]
            try:
                page.goto(url, timeout=60000)
                page.wait_for_timeout(2000)

                # Header info
                try:
                    header_divs = page.locator("div.SvveEH5y1QdtM2MuMz07 div.e3icZ8YXD7PTtS8321U3 div.AOqumsb2RS0O78r9kzMX").all()
                    contract_type = header_divs[0].inner_text() if len(header_divs) > 0 else None
                    electrical_area = header_divs[1].inner_text() if len(header_divs) > 1 else None
                except:
                    contract_type = electrical_area = None

                try:
                    contract_name = page.locator("div.SvveEH5y1QdtM2MuMz07 h1").inner_text()
                except:
                    contract_name = None

                try:
                    provider_name = page.locator("div.AWGCPcYaBUXjAUTBLl0c h3").inner_text()
                except:
                    provider_name = None

                try:
                    jämförpris_block = page.locator("div.gdeuxYpfTrq6O5EdKun6 h2").first.inner_text()
                except:
                    jämförpris_block = None

                try:
                    consumption_info = page.locator("div.gdeuxYpfTrq6O5EdKun6 p").first.inner_text()
                except:
                    consumption_info = None

                # Price breakdown
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

                # Contact info
                try:
                    provider_phone = page.locator("div.AWGCPcYaBUXjAUTBLl0c h4:has-text('Telefon') + a").inner_text()
                except:
                    provider_phone = None

                try:
                    email_elem = page.locator("div.AWGCPcYaBUXjAUTBLl0c h4:has-text('E-post') + a")
                    provider_email = email_elem.get_attribute("href")
                    if provider_email and provider_email.startswith("mailto:"):
                        provider_email = provider_email.replace("mailto:", "")
                except:
                    provider_email = None

                # Action links
                try:
                    links = page.locator("div.Tgc321GpCPUvHqOKChsl a[target='_blank']").all()
                    change_link = links[0].get_attribute("href") if len(links) > 0 else None
                    terms_link = links[1].get_attribute("href") if len(links) > 1 else None
                    website_link = links[2].get_attribute("href") if len(links) > 2 else None
                except:
                    change_link = terms_link = website_link = None

                # Energy sources
                energy_sources = []
                try:
                    keywords = ["förnybar", "vatten", "vind", "solkraft", "kärnkraft", "fossilt", "residualmix"]
                    text = page.inner_text("body").lower()
                    for kw in keywords:
                        if kw in text:
                            energy_sources.append(kw.capitalize())
                    energy_sources = list(set(energy_sources))
                except:
                    pass

                # Text-based fields
                notice_period = billing = payment = expiry = None
                try:
                    txt = page.inner_text("body")
                    if "uppsägningstid" in txt.lower():
                        m = re.search(r'uppsägningstid[:\s]*([^\n\.]+)', txt, re.IGNORECASE)
                        if m:
                            notice_period = m.group(1).strip()
                    if "fakturering" in txt.lower() and "månadsvis" in txt.lower():
                        billing = "Månadsvis i efterskott"
                    if any(w in txt.lower() for w in ["betalning", "autogiro", "swish"]):
                        payment = "Autogiro, Swish, Faktura"
                    if "tillsvidare" in txt.lower() or "förlängs automatiskt" in txt.lower():
                        expiry = "Övergår till tillsvidare avtal vid utgång"
                except:
                    pass

                data = {
                    "scraped_zip_code": zip_code,
                    "scraped_county": county,
                    "scraped_town": town,
                    "scraped_consumption_kwh": consumption,
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
                    "provider_email": provider_email
                }
                results.append(data)
                print(f"✅ Scraped: {contract_name or 'Unknown'}")
            except Exception as e:
                print(f"❌ Error scraping {url}: {e}")
                continue

        print(f"🎉 Done for {zip_code} @ {consumption} kWh — {len(results)} profiles")
        all_results_for_zip.extend(results)

    return all_results_for_zip

def save_combined_output(all_data):
    with open("combined_output.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    flat = []
    for item in all_data:
        flat_item = item.copy()
        pb = flat_item.pop("price_breakdown", {})
        for k, v in pb.items():
            flat_item[f"price_{k.replace(' ', '_').replace('/', '_')}"] = v
        es = flat_item.pop("energy_sources", [])
        flat_item["energy_sources"] = "; ".join(es) if es else ""
        flat.append(flat_item)
    df = pd.DataFrame(flat)
    df.to_excel("combined_output.xlsx", index=False, engine="openpyxl")

def run():
    all_results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE)
        page = browser.new_page()

        for zip_info in SELECTED_COUNTIES:
            try:
                results = scrape_for_zip(page, zip_info)
                all_results.extend(results)
            except Exception as e:
                print(f"🔥 CRITICAL ERROR on {zip_info['zip_code']}: {e}")
                continue

        browser.close()
        save_combined_output(all_results)
        print(f"\n✅✅✅ ALL DONE! Total records: {len(all_results)}")

        # Trigger upload to Google Sheets
        import subprocess
        import sys
        subprocess.run([sys.executable, "upload_to_sheets.py"])

if __name__ == "__main__":
    run()
