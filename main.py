from bs4 import BeautifulSoup
import json
import os
import time
import sys
import requests
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from playwright.sync_api import sync_playwright

# --- SERVER WEB PENTRU RENDER (HEALTH CHECK) ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHandler)
    httpd.serve_forever()

server_thread = threading.Thread(target=run_web_server, daemon=True)
server_thread.start()
# -----------------------------------------------

# --- CONFIGURĂRI TELEGRAM ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8829776172:AAEIU2ezJ7yR-ZOi58-FDFPi9yq2uIer2Jg")
TELEGRAM_CHAT_ID = "@topresigilate"

# --- CONFIGURĂRI PROFITSHARE ---
PROFITSHARE_USER = os.environ.get("PROFITSHARE_USER", "gruia_daniellucian_6ad3b14cba4dc")
PROFITSHARE_KEY = os.environ.get("PROFITSHARE_KEY", "1c78c3895d9a504da4e7fa85f5312f79e6fcaf90")

DB_FILE = "istoric_preturi.json"
POSTATE_FILE = "produse_postate.json"

CATEGORII_EMAG = {
    "Televizoare": "https://www.emag.ro/televizoare/c?filter-resigilat-f-v=da",
    "Telefoane": "https://www.emag.ro/telefoane-mobile/c?filter-resigilat-f-v=da",
    "IT & Laptopuri": "https://www.emag.ro/laptopuri/c?filter-resigilat-f-v=da",
    "Electronice": "https://www.emag.ro/sisteme-audio/c?filter-resigilat-f-v=da",
    "Mobilă": "https://www.emag.ro/scaune-birou/c?filter-resigilat-f-v=da"
}

def incarca_json(cale_fisier):
    if os.path.exists(cale_fisier):
        with open(cale_fisier, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def salveaza_json(cale_fisier, date):
    with open(cale_fisier, "w", encoding="utf-8") as f:
        json.dump(date, f, ensure_ascii=False, indent=4)

def verifica_si_actualizeaza_pret(produs_id, pret_curent):
    istoric = incarca_json(DB_FILE)
    data_azi = datetime.now().strftime("%d.%m.%Y")
    
    if produs_id in istoric:
        date_produs = istoric[produs_id]
        pret_min_vechi = date_produs["min_price"]
        
        if pret_curent < pret_min_vechi:
            istoric[produs_id] = {"min_price": pret_curent, "date": data_azi}
            salveaza_json(DB_FILE, istoric)
            return pret_curent, data_azi
        else:
            return pret_min_vechi, date_produs["date"]
    else:
        istoric[produs_id] = {"min_price": pret_curent, "date": data_azi}
        salveaza_json(DB_FILE, istoric)
        return pret_curent, data_azi

def genereaza_link_afiliat(link_emag, nume_oferta):
    url = "https://api.profitshare.ro/affiliate-links"
    headers = {
        "X-Postmaster-User": PROFITSHARE_USER,
        "X-Postmaster-Key": PROFITSHARE_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "links": [{"url": link_emag, "name": nume_oferta}]
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["ps_url"]
        elif "result" in data and len(data["result"]) > 0:
            return data["result"][0]["ps_url"]
    except Exception as e:
        print("Eroare Profitshare:", e, flush=True)
    return link_emag

def trimite_oferta_telegram(titlu, pret, stare_resigilat, link_original, imagine_url, produs_id, cod_voucher=None):
    pret_minim, data_minima = verifica_si_actualizeaza_pret(produs_id, pret)
    link_afiliat = genereaza_link_afiliat(link_original, titlu)
    
    linie_voucher = f"🎟️ Voucher extra: `{cod_voucher}`\n" if cod_voucher else ""
    mesaj = (
        f"💵 **{pret} lei**\n"
        f"📦 **{titlu}**\n"
        f"📝 Produs cu {stare_resigilat}\n"
        f"{linie_voucher}"
        f"📉 Preț minim înregistrat: {pret_minim} lei ({data_minima})\n"
        f"🔗 [Vezi Oferta Aici]({link_afiliat})"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": mesaj,
        "parse_mode": "Markdown",
        "photo": imagine_url
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Eroare trimitere Telegram: {e}", flush=True)
        return {}

def ruleaza_scraper_multi_categorie():
    postate = incarca_json(POSTATE_FILE)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        for nume_categorie, url_categorie in CATEGORII_EMAG.items():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanare categorie: {nume_categorie}...", flush=True)
            
            try:
                # Încărcare rapidă fără timeout-uri inutile de rețea
                page.goto(url_categorie, timeout=30000, wait_until="domcontentloaded")
                time.sleep(3) # Timp scurt pentru randarea elementelor vizuale
                
                content = page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                produse = soup.select('.card-item, .card-v2, div[data-id]')
                print(f"Găsite {len(produse)} produse în categoria {nume_categorie}", flush=True)
                
                for p_elem in produse:
                    link_tag = p_elem.select_one('a.card-v2-title, a[href*="/pd/"]') or p_elem.select_one('a')
                    if not link_tag or 'href' not in link_tag.attrs:
                        continue
                        
                    link = link_tag['href']
                    if not link.startswith('http'):
                        link = 'https://www.emag.ro' + link
                        
                    produs_id = link.split('/')[-2] if '/' in link else link
                    
                    if produs_id in postate:
                        continue
                        
                    titlu_tag = p_elem.select_one('.card-v2-title, .card-title, h2') or link_tag
                    titlu = titlu_tag.get_text(strip=True) if titlu_tag else f"Produs Resigilat {nume_categorie}"
                    
                    img_tag = p_elem.select_one('.card-v2-thumb img, img')
                    img_url = None
                    if img_tag:
                        img_url = img_tag.get('data-src') or img_tag.get('src')
                    
                    if not img_url or "imgur" in img_url:
                        img_url = "https://s13emagst.akamaized.net/layout/ro/images/logo//59/88358.svg"

                    pret_tag = p_elem.select_one('.product-new-price, p.product-new-price')
                    if pret_tag:
                        pret_text = pret_tag.get_text(strip=True).replace('.', '').replace(' Lei', '').replace(',', '.')
                        pret = float(''.join(c for c in pret_text if c.isdigit() or c == '.'))
                    else:
                        pret = 199.99

                    res = trimite_oferta_telegram(
                        titlu=titlu,
                        pret=pret,
                        stare_resigilat="urme fine de utilizare, ambalaj deschis",
                        link_original=link,
                        imagine_url=img_url,
                        produs_id=produs_id
                    )
                    
                    if res.get("ok"):
                        print(f"Postat cu succes ({nume_categorie}): {titlu}", flush=True)
                        postate[produs_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        salveaza_json(POSTATE_FILE, postate)
                        time.sleep(2)
                    else:
                        print(f"Eroare Telegram: {res}", flush=True)
                        
            except Exception as e:
                print(f"Eroare la scanarea categoriei {nume_categorie}: {e}", flush=True)

        browser.close()

if __name__ == "__main__":
    print("Botul a pornit complet!", flush=True)
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        ruleaza_scraper_multi_categorie()
    else:
        while True:
            ruleaza_scraper_multi_categorie()
            print("Pauză 12 minute...", flush=True)
            time.sleep(720)
