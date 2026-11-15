"""
Tesla Türkiye ikinci el envanterini tarar, yeni araç çıkarsa e-posta gönderir.
GitHub Actions üzerinde zamanlanmış çalışmak için hazırlandı.
"""

import json
import os
import pathlib

import smtplib
import ssl
from email.message import EmailMessage
from playwright.sync_api import sync_playwright

"""
ZIP_KODLARI = ["34000", "06000", "35000"]
URL = "https://www.tesla.com/tr_TR/inventory/used/my?arrangeby=plh&zip={zip}&range=0"
"""

ZIP_KODLARI = ["10115", "80331", "50667"]
URL = "https://www.tesla.com/de_DE/inventory/used/my?arrangeby=plh&zip={zip}&range=0"
GORULENLER = pathlib.Path("gorulenler.json")

GONDEREN = os.environ["MAIL_GONDEREN"]   # Gmail adresiniz
SIFRE = os.environ["MAIL_SIFRE"]         # Gmail "uygulama şifresi"
ALICI = os.environ.get("MAIL_ALICI") or GONDEREN


def mail_gonder(konu, metin):
    msg = EmailMessage()
    msg["From"] = GONDEREN
    msg["To"] = ALICI
    msg["Subject"] = konu
    msg.set_content(metin)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as smtp:
        smtp.login(GONDEREN, SIFRE)
        smtp.send_message(msg)


def sayfayi_cek(page, zip_kodu):
    sonuclar = []

    def yakala(response):
        if "inventory-results" in response.url:
            try:
                sonuclar.extend(response.json().get("results", []))
            except Exception:
                pass

    page.on("response", yakala)
    page.goto(URL.format(zip=zip_kodu), wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)
    page.remove_listener("response", yakala)
    return sonuclar


def ozet(a):
    fiyat = a.get("TotalPrice") or a.get("Price") or a.get("InventoryPrice")
    return {
        "vin": a.get("VIN"),
        "metin": (
            f"🚗 {a.get('Model')} {a.get('TrimName') or ''} | {a.get('Year')}\n"
            f"💰 {fiyat}  | 🛣 {a.get('Odometer')} km\n"
            f"🎨 {a.get('PAINT') or ''} | 📍 {a.get('City') or ''}"
        ),
    }


def main():
    gorulen = set(json.loads(GORULENLER.read_text())) if GORULENLER.exists() else set()
    ilk_calisma = not GORULENLER.exists()
    bulunanlar = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # xvfb ile çalışır
        page = browser.new_context(locale="de-DE").new_page()
        for z in ZIP_KODLARI:
            try:
                for a in sayfayi_cek(page, z):
                    o = ozet(a)
                    if o["vin"]:
                        bulunanlar.setdefault(o["vin"], o)
            except Exception as e:
                print(f"Hata ({z}): {e}")
        browser.close()

    print(f"Bulunan: {len(bulunanlar)}")

    if not bulunanlar:
        # Büyük olasılıkla Tesla engelledi; durumu bildir ama state'i bozma
        print("Hiç sonuç yok, muhtemelen engellendi.")
        return

    yeniler = [o for v, o in bulunanlar.items() if v not in gorulen]

    if ilk_calisma:
        mail_gonder("Tesla Bot çalıştı", f"Şu an {len(bulunanlar)} araç var. Yenileri bildireceğim.")
    elif yeniler:
        govde = "\n\n".join(
            o["metin"] + f"\nhttps://www.tesla.com/tr_TR/m3/order/{o['vin']}"
            for o in yeniler
        )
        mail_gonder(f"🆕 {len(yeniler)} yeni Tesla ilanı", govde)

    GORULENLER.write_text(json.dumps(sorted(gorulen | set(bulunanlar))))


if __name__ == "__main__":
    main()
