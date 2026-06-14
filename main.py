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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "USE_SANDBOX_AI")
GAMMA_API = "https://gamma-api.polymarket.com"

# תגיות מפתח (מבוסס על ה-API של Polymarket)
TAGS = {
    "Soccer": "100383",
    "NBA": "100196", # Note: Some IDs might vary, using broad sports tags
    "Tennis": "100319",
    "Weather": "100125"
}

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
# 3. Polymarket Scanner (STABLE)
# ==========================================
def fetch_active_events():
    """שליפת אירועים פעילים מה-Gamma API בצורה היציבה ביותר"""
    url = f"{GAMMA_API}/events"
    params = {
        "active": "true",
        "closed": "false",
        "limit": 50,
        "order": "volume_24hr",
        "ascending": "false"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Fetch Error: {e}")
    return []

def scan_markets(manual_chat_id=None):
    events = fetch_active_events()
    if not events:
        if manual_chat_id:
            send_telegram(manual_chat_id, "❌ לא הצלחתי למשוך נתונים מה-API. מנסה שוב...")
        return

    found_any = False
    report = "🔍 *דוח סריקה גולמי (שווקים פעילים):*\n\n"
    
    for event in events:
        title = event.get('title', 'No Title')
        markets = event.get('markets', [])
        
        # סינון בסיסי לפי מילות מפתח (ספורט ומזג אוויר)
        keywords = ['soccer', 'football', 'nba', 'basketball', 'tennis', 'weather', 'temperature', 'rain']
        is_relevant = any(kw in title.lower() for kw in keywords)
        
        if is_relevant and markets:
            found_any = True
            m = markets[0] # לוקחים את השוק הראשון באירוע
            price = float(m.get('outcomePrices', [0, 0])[0])
            
            # שליחת איתות בסיסי (ללא AI כרגע כדי לוודא זרימה)
            msg = (
                f"🎯 *איתות זוהה!*\n\n"
                f"🏟️ *{title}*\n"
                f"🔑 קניית YES\n"
                f"💰 מחיר: ${price:.2f}\n"
                f"📊 ווליום: ${event.get('volume_24hr', 0):,.0f}"
            )
            
            if manual_chat_id:
                send_telegram(manual_chat_id, msg)
            else:
                for user in get_all_users():
                    send_telegram(user, msg)
            
            # נתעד בתיק
            log_trade(title, "BUY YES", price, 70)

    if not found_any and manual_chat_id:
        send_telegram(manual_chat_id, "⚠️ לא נמצאו שווקי ספורט/מזג אוויר רלוונטיים ברגע זה.")

def log_trade(market, action, entry_price, ai_score):
    conn = sqlite3.connect('simulator.db', check_same_thread=False)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO portfolio (market, action, entry_price, amount, ai_score, status, timestamp) VALUES (?, ?, ?, 10.0, ?, 'OPEN', ?)",
              (market, action, entry_price, ai_score, now))
    conn.commit()
    conn.close()

# ==========================================
# 4. Telegram Communication
# ==========================================
def send_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
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
                            send_telegram(chat_id, "🚀 הבוט הופעל! אני סורק שווקים עכשיו...")
                        elif text == "/scan":
                            send_telegram(chat_id, "🔄 סורק עכשיו את ה-API הרשמי...")
                            scan_markets(manual_chat_id=chat_id)
        except:
            pass
        time.sleep(1)

# ==========================================
# 5. Main Execution
# ==========================================
if __name__ == "__main__":
    setup_db()
    # הפעלת מאזין פקודות בטרד נפרד
    threading.Thread(target=handle_commands, daemon=True).start()
    
    print("Bot is running...")
    while True:
        scan_markets()
        time.sleep(600) # סריקה כל 10 דקות
