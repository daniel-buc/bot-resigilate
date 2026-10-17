import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime

# --- CONFIGURĂRI TELEGRAM ---
TELEGRAM_TOKEN = "8829776172:AAEIU2ezJ7yR-ZOi58-FDFPi9yq2uIer2Jg"
TELEGRAM_CHAT_ID = "@topresigilate"

# --- CONFIGURĂRI PROFITSHARE ---
PROFITSHARE_USER = "gruia_daniellucian_6ad3b14cba4dc"
PROFITSHARE_KEY = "1c78c3895d9a504da4e7fa85f5312f79e6fcaf90"

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
        "links": [
            {
                "url": link_emag,
                "name": nume_oferta
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["ps_url"]
        elif "result" in data and len(data["result"]) > 0:
            return data["result"][0]["ps_url"]
    except Exception as e:
        print("Eroare Profitshare:", e)
        
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
    
    response = requests.post(url, data=payload)
    return response.json()

def ruleaza_scraper_multi_categorie():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    postate = incarca_json(POSTATE_FILE)
    
    for nume_categorie, url_categorie in CATEGORII_EMAG.items():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanare categorie: {nume_categorie}...")
        
        try:
            response = requests.get(url_categorie, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"Eroare la accesare {nume_categorie}: {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            produse = soup.select('.card-v2, .card-item, .product-k-box')
            print(f"Găsite {len(produse)} produse în categoria {nume_categorie}")
            
            for p in produse:
                link_tag = p.select_one('a[href*="/pd/"], a.card-v2-title') or p.select_one('a')
                if not link_tag or 'href' not in link_tag.attrs:
                    continue
                    
                link = link_tag['href']
                if not link.startswith('http'):
                    link = 'https://www.emag.ro' + link
                    
                produs_id = link.split('/')[-2] if '/' in link else link
                
                if produs_id in postate:
                    continue
                    
                titlu_tag = p.select_one('.card-v2-title, .card-title') or link_tag
                titlu = titlu_tag.get_text(strip=True) if titlu_tag else f"Produs Resigilat {nume_categorie}"
                
                img_tag = p.select_one('.card-v2-thumb-inner img, img')
                img_url = None
                if img_tag:
                    img_url = img_tag.get('data-src') or img_tag.get('src')
                
                if not img_url or "imgur" in img_url:
                    img_url = "https://s13emagst.akamaized.net/layout/ro/images/logo//59/88358.svg"

                pret_tag = p.select_one('.product-new-price')
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
                    print(f"Postat cu succes ({nume_categorie}): {titlu}")
                    postate[produs_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    salveaza_json(POSTATE_FILE, postate)
                    time.sleep(5)
                    
        except Exception as e:
            print(f"Eroare la scanarea categoriei {nume_categorie}:", e)

if __name__ == "__main__":
    print("Botul rulează complet automat pentru toate categoriile!")
    while True:
        ruleaza_scraper_multi_categorie()
        print("Aștept 12 minute până la următoarea verificare...")
        time.sleep(720)
