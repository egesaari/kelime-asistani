from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
from datetime import datetime, timedelta
import random
import urllib.request
import urllib.parse
import json

app = Flask(__name__)
app.secret_key = "ege_gizli_anahtar_key_1604"

# UYGULAMA GİRİŞ ŞİFRESİ
GIRIS_SIFRESI = "1604"

def get_db():
    conn = sqlite3.connect("kelimeler.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kelimeler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingilizce TEXT NOT NULL,
            turkce TEXT NOT NULL,
            ornek_cumle TEXT DEFAULT '',
            seviye INTEGER DEFAULT 1,
            sonraki_tekrar DATE DEFAULT CURRENT_DATE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS istatistik (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            son_calisma_tarihi DATE,
            seri_gun INTEGER DEFAULT 0,
            bugun_cozulen INTEGER DEFAULT 0,
            gunluk_hedef INTEGER DEFAULT 10
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM istatistik")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO istatistik (son_calisma_tarihi, seri_gun, bugun_cozulen, gunluk_hedef) VALUES (CURRENT_DATE, 0, 0, 10)")
    conn.commit()
    conn.close()

# Veritabanını otomatik başlat
init_db()

def metin_cevir(metin, kaynak_dil, hedef_dil):
    try:
        encoded_text = urllib.parse.quote(metin)
        url = f"https://api.mymemory.translated.net/get?q={encoded_text}&langpair={kaynak_dil}|{hedef_dil}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            translated = data.get("responseData", {}).get("translatedText", "")
            if translated:
                return translated.strip().lower()
    except Exception:
        pass
    return ""

def seri_guncelle():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM istatistik WHERE id = 1")
    stat = dict(cursor.fetchone())
    
    bugun = datetime.now().date()
    son_tarih = None
    if stat["son_calisma_tarihi"]:
        try:
            son_tarih = datetime.strptime(str(stat["son_calisma_tarihi"]), "%Y-%m-%d").date()
        except ValueError:
            pass

    if son_tarih != bugun:
        if son_tarih and son_tarih < bugun - timedelta(days=1):
            cursor.execute("UPDATE istatistik SET seri_gun = 0 WHERE id = 1")
        cursor.execute("UPDATE istatistik SET bugun_cozulen = 0, son_calisma_tarihi = ? WHERE id = 1", (bugun,))
        conn.commit()
    conn.close()

# --- ŞİFRE VE OTURUM KONTROLLERİ ---
@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    if request.method == "POST":
        girilen_sifre = request.form.get("sifre")
        if girilen_sifre == GIRIS_SIFRESI:
            session["giris_yapildi"] = True
            return redirect(url_for("index"))
        else:
            hata = "Hatalı şifre! Lütfen tekrar deneyin."
    return render_template("login.html", hata=hata)

@app.route("/logout")
def logout():
    session.pop("giris_yapildi", None)
    return redirect(url_for("login"))

@app.route("/")
def index():
    if not session.get("giris_yapildi"):
        return redirect(url_for("login"))
    seri_guncelle()
    return render_template("index.html")

# --- API ENDPOINT'LERİ ---
@app.route("/api/kelimeler", methods=["GET"])
def kelimeleri_getir():
    if not session.get("giris_yapildi"):
        return jsonify({"status": "unauthorized"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kelimeler ORDER BY id DESC")
    kelimeler = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "kelimeler": kelimeler})

@app.route("/api/kelime-ekle", methods=["POST"])
def kelime_ekle():
    if not session.get("giris_yapildi"):
        return jsonify({"status": "unauthorized"}), 401
    data = request.json or {}
    ing = data.get("ingilizce", "").strip().lower()
    turk = data.get("turkce", "").strip().lower()

    if turk and not ing:
        ing = metin_cevir(turk, "tr", "en")
    elif ing and not turk:
        turk = metin_cevir(ing, "en", "tr")

    if not ing and not turk:
        return jsonify({"status": "error", "message": "En az bir kelime girmelisiniz."})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO kelimeler (ingilizce, turkce, seviye, sonraki_tekrar) VALUES (?, ?, 1, CURRENT_DATE)",
        (ing, turk)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"'{ing}' - '{turk}' eklendi!"})

@app.route("/api/kelime-sil/<int:kelime_id>", methods=["DELETE"])
def kelime_sil(kelime_id):
    if not session.get("giris_yapildi"):
        return jsonify({"status": "unauthorized"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM kelimeler WHERE id = ?", (kelime_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Kelime silindi."})

@app.route("/api/kelime-duzenle/<int:kelime_id>", methods=["PUT"])
def kelime_duzenle(kelime_id):
    if not session.get("giris_yapildi"):
        return jsonify({"status": "unauthorized"}), 401
    data = request.json or {}
    ing = data.get("ingilizce", "").strip().lower()
    turk = data.get("turkce", "").strip().lower()

    if not ing or not turk:
        return jsonify({"status": "error", "message": "Alanlar boş bırakılamaz."})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE kelimeler SET ingilizce = ?, turkce = ? WHERE id = ?",
        (ing, turk, kelime_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Kelime güncellendi!"})

@app.route("/api/soru-getir", methods=["GET"])
def soru_getir():
    if not session.get("giris_yapildi"):
        return jsonify({"status": "unauthorized"}), 401
    conn = get_db()
    cursor = conn.cursor()
    bugun = datetime.now().date().strftime("%Y-%m-%d")

    cursor.execute("SELECT * FROM kelimeler WHERE sonraki_tekrar <= ? ORDER BY seviye ASC, RANDOM() LIMIT 1", (bugun,))
    kelime = cursor.fetchone()

    if not kelime:
        cursor.execute("SELECT * FROM kelimeler ORDER BY RANDOM() LIMIT 1")
        kelime = cursor.fetchone()

    if not kelime:
        conn.close()
        return jsonify({"status": "empty"})

    kelime_dict = dict(kelime)
    conn.close()

    soru_tipi = random.choice(["ing_turk", "turk_ing"])
    dogru_cevap = kelime_dict["turkce"] if soru_tipi == "ing_turk" else kelime_dict["ingilizce"]
    
    ilk_harf = dogru_cevap[0].upper() if len(dogru_cevap) > 0 else ""
    kalan_harfler = " _" * (len(dogru_cevap) - 1)
    ipucu = f"İpucu: {ilk_harf}{kalan_harfler}"
    
    return jsonify({
        "status": "success",
        "id": kelime_dict["id"],
        "soru_tipi": soru_tipi,
        "soru": kelime_dict["ingilizce"] if soru_tipi == "ing_turk" else kelime_dict["turkce"],
        "ipucu": ipucu,
        "seviye": kelime_dict["seviye"]
    })

@app.route("/api/cevap-kontrol", methods=["POST"])
def cevap_kontrol():
    if not session.get("giris_yapildi"):
        return jsonify({"status": "unauthorized"}), 401
    data = request.json or {}
    kelime_id = data.get("id")
    kullanici_cevabi = data.get("cevap", "").strip().lower()
    soru_tipi = data.get("soru_tipi")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kelimeler WHERE id = ?", (kelime_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"dogru": False, "dogru_cevap": "", "yeni_seviye": 1})

    kelime = dict(row)
    dogru_cevap = kelime["turkce"] if soru_tipi == "ing_turk" else kelime["ingilizce"]
    is_correct = (kullanici_cevabi == dogru_cevap.strip().lower())

    yeni_seviye = kelime["seviye"]
    if is_correct:
        yeni_seviye = min(5, yeni_seviye + 1)
        gun_ekle = 2 ** (yeni_seviye - 1)
    else:
        yeni_seviye = 1
        gun_ekle = 0

    sonraki_tarih = (datetime.now().date() + timedelta(days=gun_ekle)).strftime("%Y-%m-%d")

    cursor.execute(
        "UPDATE kelimeler SET seviye = ?, sonraki_tekrar = ? WHERE id = ?",
        (yeni_seviye, sonraki_tarih, kelime_id)
    )

    cursor.execute("SELECT * FROM istatistik WHERE id = 1")
    stat = dict(cursor.fetchone())
    yeni_bugun_cozulen = stat["bugun_cozulen"] + 1
    yeni_seri = stat["seri_gun"]

    if yeni_bugun_cozulen >= stat["gunluk_hedef"] and stat["bugun_cozulen"] < stat["gunluk_hedef"]:
        yeni_seri += 1

    cursor.execute(
        "UPDATE istatistik SET bugun_cozulen = ?, seri_gun = ?, son_calisma_tarihi = CURRENT_DATE WHERE id = 1",
        (yeni_bugun_cozulen, yeni_seri)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "dogru": is_correct,
        "dogru_cevap": dogru_cevap,
        "yeni_seviye": yeni_seviye
    })

@app.route("/api/istatistik", methods=["GET"])
def istatistik_getir():
    if not session.get("giris_yapildi"):
        return jsonify({"status": "unauthorized"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM istatistik WHERE id = 1")
    stat = dict(cursor.fetchone())
    
    cursor.execute("SELECT COUNT(*) as toplam FROM kelimeler")
    toplam = cursor.fetchone()["toplam"]
    conn.close()

    return jsonify({
        "seri": stat["seri_gun"],
        "bugun_cozulen": stat["bugun_cozulen"],
        "hedef": stat["gunluk_hedef"],
        "toplam_kelime": toplam
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)