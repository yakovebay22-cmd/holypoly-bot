import os
import time
import sqlite3
import requests
import datetime
import threading
import json

# ==========================================
# 1. Configuration
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8907723838:AAG5fi0vcbtf9SCdinPR7ilui2E9OPBkqZA")
BUILD_ID = "build-TfctsWXpff2fKS" # Dynamic Build ID from Polymarket site

# ==========================================
# 2. Database Setup
# ==========================================
def setup_db():
    conn = sqlite3.connect('simulator.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS portfolio (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  market TEXT,
                  action TEXT,
                  entry_price REAL,
                  amount REAL,
                  ai_score INTEGER,
                  status TEXT,
                  timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                  chat_id TEXT PRIMARY KEY,
                  joined_at DATETIME,
                  active INTEGER DEFAULT 1)''')
    conn.commit()
    conn.close()

def add_user(chat_id):
    conn = sqlite3.connect('simulator.db', check_same_thread=False)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR IGNORE INTO users (chat_id, joined_at) VALUES (?, ?)", (str(chat_id), now))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('simulator.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM users WHERE active=1")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

# ==========================================
# 3. Polymarket Next.js Scanner (ULTRA STABLE)
# ==========================================
def fetch_live_sports():
    """שליפת משחקי ספורט חיים מה-JSON הפנימי של האתר"""
    url = f"https://polymarket.com/_next/data/{BUILD_ID}/sports/live.json"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Extract markets from the pageProps
            return data.get('pageProps', {}).get('dehydratedState', {}).get('queries', [])
    except Exception as e:
        print(f"Fetch Error: {e}")
    return []

def scan_markets(manual_chat_id=None):
    queries = fetch_live_sports()
    if not queries:
        if manual_chat_id:
            send_telegram(manual_chat_id, "❌ לא הצלחתי למשוך נתונים חיים מהאתר. מנסה דרך ה-API הרגיל...")
            # Fallback to standard API if Next.js fails
            fallback_scan(manual_chat_id)
        return

    found_count = 0
    # נחפש בתוך ה-queries את הנתונים של השווקים
    for q in queries:
        state = q.get('state', {})
        data = state.get('data', {})
        
        # אם זה רשימת אירועים
        if isinstance(data, list):
            for event in data:
                title = event.get('title', '')
                markets = event.get('markets', [])
                
                if markets:
                    m = markets[0]
                    price = float(m.get('outcomePrices', [0, 0])[0])
                    
                    if 0.05 < price < 0.95:
                        found_count += 1
                        msg = (
                            f"🔥 *איתות חי מהאתר!* 🔥\n\n"
                            f"🏟️ *{title}*\n"
                            f"🔑 קניית YES\n"
                            f"💰 מחיר: ${price:.2f}\n"
                            f"📊 ווליום: ${event.get('volume24hr', 0):,.0f}\n"
                            f"🔗 [למסחר](https://polymarket.com/event/{event.get('slug')})"
                        )
                        if manual_chat_id:
                            send_telegram(manual_chat_id, msg)
                        else:
                            for user in get_all_users():
                                send_telegram(user, msg)
                        
                        if found_count >= 5: break
            if found_count >= 5: break

    if found_count == 0 and manual_chat_id:
        send_telegram(manual_chat_id, "⚠️ לא נמצאו משחקים חיים מעניינים כרגע.")

def fallback_scan(chat_id):
    # פונקציית גיבוי למקרה שה-Next.js נכשל
    url = "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=20&order=volume_24hr"
    try:
        r = requests.get(url).json()
        for m in r[:3]:
            send_telegram(chat_id, f"📡 *איתות גיבוי:* {m.get('question')} | ${m.get('outcomePrices',[0])[0]}")
    except: pass

# ==========================================
# 4. Telegram Communication
# ==========================================
def send_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def handle_commands():
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {"timeout": 30, "offset": offset}
            r = requests.get(url, params=params, timeout=35).json()
            if r.get("ok") and r.get("result"):
                for update in r["result"]:
                    offset = update["update_id"] + 1
                    if "message" in update and "text" in update["message"]:
                        chat_id = str(update["message"]["chat"]["id"])
                        text = update["message"]["text"]
                        add_user(chat_id)
                        
                        if text == "/start":
                            send_telegram(chat_id, "🚀 הבוט הופעל ומחובר ישירות לנתוני האתר החיים!")
                        elif text == "/scan":
                            send_telegram(chat_id, "🔄 סורק משחקים חיים מהאתר (Germany vs Curacao וכו')...")
                            scan_markets(manual_chat_id=chat_id)
        except:
            pass
        time.sleep(1)

if __name__ == "__main__":
    setup_db()
    threading.Thread(target=handle_commands, daemon=True).start()
    while True:
        scan_markets()
        time.sleep(300)
