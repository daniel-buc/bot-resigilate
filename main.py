import json
import os
import time
import sys
import requests
import re
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from bs4 import BeautifulSoup

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

URL_RESIGILATE = "https://www.emag.ro/resigilate/c?ref=hp_menu_quick-links_1_6&sort-dir=desc&sort-field=rated-desc"

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

def ruleaza_scraper_resigilate():
    postate = incarca_json(POSTATE_FILE)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanare avansată resigilate (prin Regex)...", flush=True)
    
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={requests.utils.quote(URL_RESIGILATE)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        response = requests.get(proxy_url, headers=headers, timeout=25)
        
        if response.status_code != 200:
            print(f"Eroare HTTP {response.status_code} la preluarea paginii", flush=True)
            return
            
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        link_uri_gasite = soup.select('a[href*="/pd/"]')
        print(f"Găsite {len(link_uri_gasite)} link-uri brute de produse", flush=True)
        
        produse_procesate = set()

        for a_tag in link_uri_gasite:
            link = a_tag.get('href')
            if not link:
                continue
            if not link.startswith('http'):
                link = 'https://www.emag.ro' + link
                
            match_id = re.search(r'/pd/([A-Z0-9]+)', link)
            if not match_id:
                continue
            produs_id = match_id.group(1)
            
            if produs_id in produse_procesate or produs_id in postate:
                continue
            produse_procesate.add(produs_id)
            
            titlu = a_tag.get_text(strip=True)
            if len(titlu) < 8:
                parent = a_tag.parent
                if parent:
                    titlu = parent.get_text(strip=True)
            if len(titlu) < 8:
                titlu = f"Produs Resigilat eMAG ({produs_id})"
            else:
                titlu = titlu[:120]

            img_url = "https://s13emagst.akamaized.net/layout/ro/images/logo//59/88358.svg"
            parent_container = a_tag.find_parent(['div', 'article'])
            if parent_container:
                img_tag = parent_container.select_one('img')
                if img_tag:
                    img_url = img_tag.get('data-src') or img_tag.get('src') or img_url

            pret = 199.99
            if parent_container:
                text_container = parent_container.get_text()
                match_pret = re.search(r'([\d\.]+)\s*(?:Lei|RON)', text_container)
                if match_pret:
                    pret_str = match_pret.group(1).replace('.', '')
                    try:
                        pret = float(pret_str)
                    except:
                        pass

            res = trimite_oferta_telegram(
                titlu=titlu,
                pret=pret,
                stare_resigilat="urme fine de utilizare, ambalaj deschis",
                link_original=link,
                imagine_url=img_url,
                produs_id=produs_id
            )
            
            if res.get("ok"):
                print(f"Postat cu succes: {titlu[:50]}...", flush=True)
                postate[produs_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                salveaza_json(POSTATE_FILE, postate)
                time.sleep(1.5)
            else:
                print(f"Eroare Telegram: {res}", flush=True)
                
    except Exception as e:
        print(f"Eroare la scanarea prin Regex: {e}", flush=True)

if __name__ == "__main__":
    print("Botul a pornit complet!", flush=True)
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        ruleaza_scraper_resigilate()
    else:
        while True:
            ruleaza_scraper_resigilate()
            print("Pauză 12 minute...", flush=True)
            time.sleep(720)
