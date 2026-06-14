import os
import time
import sqlite3
import requests
import datetime
import threading
from py_clob_client.client import ClobClient

# ==========================================
# 1. Configuration
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8907723838:AAG5fi0vcbtf9SCdinPR7ilui2E9OPBkqZA")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 300))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "USE_SANDBOX_AI")

# ==========================================
# 2. Database
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

def remove_user(chat_id):
    conn = sqlite3.connect('simulator.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("UPDATE users SET active=0 WHERE chat_id=?", (str(chat_id),))
    conn.commit()
    conn.close()

def get_history(limit=5):
    conn = sqlite3.connect('simulator.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT market, action, entry_price, ai_score, timestamp FROM portfolio ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def log_trade(market, action, entry_price, ai_score, amount=10.0):
    conn = sqlite3.connect('simulator.db', check_same_thread=False)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO portfolio (market, action, entry_price, amount, ai_score, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (market, action, entry_price, amount, ai_score, 'OPEN', now))
    conn.commit()
    conn.close()

def get_portfolio_stats():
    conn = sqlite3.connect('simulator.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM portfolio")
    total = c.fetchone()[0]
    conn.close()
    return total

# ==========================================
# 3. Niche Analyzers & Whale Tracker
# ==========================================
def identify_niche(market_name):
    name_lower = market_name.lower()
    
    # --- שלב 1: סינון מיידי של כל מה שלא רלוונטי ---
    # ספורט שאנחנו לא עוקבים אחריו
    skip_sports = ['nhl', 'hockey', 'stanley cup', 'mlb', 'nfl', 'mls', 'formula 1', 'f1', 
                   'boxing', 'ufc', 'mma', 'golf', 'pga', 'rugby', 'cricket', 'esports', 
                   'lol', 'dota', 'cs:', 'valorant', 'nascar', 'cycling']
    if any(word in name_lower for word in skip_sports):
        return "🌍 כללי"
    
    # שאלות ספקולטיביות ארוכות טווח שלא ניתן לנתח
    skip_speculative = ['world cup', 'championship', 'super bowl', 'win the', 'win their']
    if any(word in name_lower for word in skip_speculative):
        return "🌍 כללי"

    # --- שלב 2: זיהוי נישה ספציפית ---
    # כדורגל — משחקים ספציפיים בלבד (לא אליפויות)
    if any(word in name_lower for word in ['premier league', 'champions league', 'la liga', 'serie a', 
                                            'bundesliga', 'ligue 1', 'eredivisie', 'mls cup',
                                            'will score', 'match winner', 'over/under', 'o/u',
                                            'fifwc', 'will win on']):
        return "⚽ כדורגל"
    
    # כדורסל NBA — משחקים ספציפיים
    if any(word in name_lower for word in ['nba', 'basketball']) and \
       any(word in name_lower for word in ['game', 'series', 'match', 'cover', 'points', 'win on']):
        return "🏀 כדורסל"
    
    # טניס — משחקים ספציפיים
    if any(word in name_lower for word in ['tennis', 'atp', 'wta', 'wimbledon', 'us open', 
                                            'french open', 'australian open', 'roland garros']):
        return "🎾 טניס"
    
    # מזג אוויר — מילות מפתח ספציפיות בלבד (לא שמות קבוצות!)
    weather_keywords = ['temperature', 'rainfall', 'precipitation', 'degrees fahrenheit', 
                        'degrees celsius', 'hurricane warning', 'tropical storm', 
                        'tornado warning', 'blizzard', 'snowfall', 'heat wave',
                        'will it rain', 'will it snow', 'weather forecast']
    if any(word in name_lower for word in weather_keywords):
        return "🌡️ מזג אוויר"
    
    return "🌍 כללי"

def analyze_with_ai(market_name, price, is_yes, niche):
    """
    ניתוח AI עמוק — שולח את הנתונים ל-GPT-4 לניתוח אמיתי.
    ה-AI מקבל את שם השוק, המחיר, והנישה — וצריך להחליט אם יש אדג' אמיתי.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    
    if not api_key or api_key == "USE_SANDBOX_AI":
        return 65, f"⚠️ מנוע ה-AI כבוי. הניתוח מבוסס על תמחור בלבד בנישת {niche}."
    
    prompt = f"""You are a professional sports/weather bettor analyzing Polymarket.
Today's date: {datetime.datetime.now().strftime('%Y-%m-%d')}.

Market: "{market_name}"
Niche: {niche}
Proposed action: Buy {"YES" if is_yes else "NO"}
Current price: ${price:.2f}

IMPORTANT RULES:
- Only give score above 80 if you have STRONG evidence this is mispriced
- Consider: Is this team/player actually likely to win TODAY based on recent form?
- Consider: Is the market price already fair? If yes, score should be below 60
- Be SKEPTICAL. Most markets are correctly priced.
- A score of 50 means "no edge, skip this"
- A score of 90+ means "very high confidence the market is wrong"

Return ONLY valid JSON:
{{"score": <int 1-100>, "reason": "<1-2 sentences in Hebrew explaining your analysis. MUST include specific reasons like 'יש פציעה לשחקן מפתח', 'רצף ניצחונות אחרון', or 'תחזית מזג אוויר מעודכנת'>"}}
"""
    try:
        # Use an available model in the sandbox environment, fallback to gpt-4.1-mini
        model_name = "gpt-4.1-mini" if "manus.im" in api_base else "gpt-4o"
        
        response = requests.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_name, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=15
        )
        data = response.json()
        content = data['choices'][0]['message']['content'].strip()
        # ניקוי JSON
        if content.startswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0]
        import json as _j
        result = _j.loads(content)
        score = int(result.get("score", 50))
        reason = result.get("reason", "ניתוח הושלם")
        return score, reason
    except Exception as e:
        print(f"AI Error: {e}")
        return 55, "שגיאה בניתוח AI. מדלג."

def check_whale_activity(token_id):
    whale_alert = False
    whale_volume = 0
    try:
        url = f"https://data-api.polymarket.com/trades?asset={token_id}&limit=5&filterType=CASH&filterAmount=5000"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            trades = r.json()
            if trades and len(trades) > 0:
                whale_alert = True
                whale_volume = sum(t.get('size', 0) for t in trades)
    except:
        pass
    return whale_alert, whale_volume

# ==========================================
# 4. Telegram Broadcaster
# ==========================================
def send_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def broadcast_signal(signal_msg):
    users = get_all_users()
    for user in users:
        send_telegram(user, signal_msg)

def format_advanced_signal(market_name, signal, total_trades, niche):
    icon = "🟢" if "YES" in signal['action'] else "🔴"
    score = signal['ai_score']
    score_icon = "🔥" if score >= 80 else ("⭐" if score >= 60 else "⚠️")
    whale_text = f"\n🐋 *התראת לוויתנים:* זוהו עסקאות חכמות בנפח ${signal['whale_vol']:,.0f}!" if signal['whale_alert'] else ""

    return (
        f"{niche} *איתות ממוקד* {niche}\n\n"
        f"*{market_name}*\n\n"
        f"🔑 {signal['action']} {icon}\n"
        f"🎯 מחיר כניסה: ${signal['entry']:.2f}\n"
        f"📊 *ציון מערכת:* {score}/100 {score_icon}\n"
        f"{whale_text}\n\n"
        f"📝 *ניתוח:* {signal['reason']}\n\n"
        f"💼 הימור סימולטור: $10.00\n"
        f"📈 סה\"כ המלצות: {total_trades + 1}"
    )

# ==========================================
# 5. Telegram Commands Listener
# ==========================================
def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    try:
        r = requests.get(url, params=params, timeout=35)
        return r.json()
    except:
        return {"ok": False}

def handle_commands():
    print("Command listener started.")
    offset = None
    while True:
        updates = get_updates(offset)
        if updates.get("ok") and updates.get("result"):
            for update in updates["result"]:
                offset = update["update_id"] + 1
                if "message" in update and "text" in update["message"]:
                    chat_id = str(update["message"]["chat"]["id"])
                    text = update["message"]["text"]
                    
                    add_user(chat_id)
                    
                    if text == "/start":
                        msg = (
                            "👋 *ברוך הבא ל-HolyPoly Bot!*\n\n"
                            "הבוט סורק את שווקי Polymarket ומתמקד בנישות: ⚽ כדורגל, 🏀 כדורסל, 🎾 טניס ו-🌡️ מזג אוויר.\n\n"
                            "פקודות זמינות:\n"
                            "🔹 `/status` - מצב הבוט והתיק\n"
                            "🔹 `/scan` - הפעלת סריקה יזומה עכשיו\n"
                            "🔹 `/help` - עזרה"
                        )
                        send_telegram(chat_id, msg)
                    
                    elif text == "/status":
                        stats = get_portfolio_stats()
                        msg = (
                            "📊 *סטטוס הבוט*\n\n"
                            "✅ הבוט רץ וסורק שווקים (כדורגל, כדורסל, טניס, מזג אוויר).\n"
                            f"📈 סה\"כ איתותים שנשלחו: {stats}\n"
                            f"👥 משתמשים מנויים: {len(get_all_users())}"
                        )
                        send_telegram(chat_id, msg)
                        
                    elif text == "/scan":
                        send_telegram(chat_id, "🔄 מתחיל סריקה יזומה של השוק (מסנן נישות)... זה ייקח כמה שניות.")
                        scan_markets(ClobClient("https://clob.polymarket.com"), manual_chat_id=chat_id)
                        
                    elif text == "/stop":
                        remove_user(chat_id)
                        send_telegram(chat_id, "⏹ *האיתותים נעצרו.*\n\nלא תקבל יותר הודעות אוטומטיות.\nלהפעלה מחדש שלח /start")
                    
                    elif text == "/history":
                        rows = get_history(5)
                        if not rows:
                            send_telegram(chat_id, "💭 אין עדיין היסטוריה. הבוט עדיין לא שלח איתותים.")
                        else:
                            msg = "📜 *5 איתותים אחרונים:*\n\n"
                            for i, (market, action, price, score, ts) in enumerate(rows, 1):
                                icon = "🟢" if "YES" in action else "🔴"
                                msg += f"{i}. {icon} {action} | ${price:.2f} | ציון:{score}\n   _{market[:45]}_\n   {ts}\n\n"
                            send_telegram(chat_id, msg)
                    
                    elif text == "/help":
                        send_telegram(chat_id, "📚 *פקודות:*\n\n/start — הפעלה + רישום\n/scan — סריקה יזומה\n/status — מצב הבוט\n/history — 5 איתותים אחרונים\n/stop — עצירת איתותים\n\nהבוט סורק כל 5 דקות אוטומטית.")
                        
        time.sleep(1)

# ==========================================
# 6. Main Scanner
# ==========================================
def scan_markets(client, manual_chat_id=None):
    try:
        import json as _json
        headers = {'User-Agent': 'Mozilla/5.0'}
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        tomorrow = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        
        # --- שליפת אירועים של היום ומחר דרך Events API ---
        all_markets = []
        
        # 1. שליפת events עם slug מדויק לכל תאריך (היום ומחר)
        # שימוש ב-slug_contains + סינון לפי שנת 2026
        for date_str in [today, tomorrow]:
            try:
                r = requests.get(
                    f'https://gamma-api.polymarket.com/events?slug_contains={date_str}&limit=50',
                    headers=headers, timeout=10
                )
                if r.status_code == 200:
                    events = r.json()
                    for event in events:
                        slug = event.get('slug', '')
                        # סינון: רק אירועים שה-slug מכיל את התאריך המדויק שלנו
                        if date_str not in slug:
                            continue
                        for mk in event.get('markets', []):
                            mk['_event_title'] = event.get('title', '')
                            all_markets.append(mk)
            except:
                pass
        
        # 1b. חיפוש נוסף עם slug מדויק למשחקי מונדיאל (שיש להם more-markets)
        for date_str in [today, tomorrow]:
            try:
                r = requests.get(
                    f'https://gamma-api.polymarket.com/events?slug_contains={date_str}-more-markets&limit=50',
                    headers=headers, timeout=10
                )
                if r.status_code == 200:
                    events = r.json()
                    for event in events:
                        slug = event.get('slug', '')
                        if date_str not in slug:
                            continue
                        for mk in event.get('markets', []):
                            mk['_event_title'] = event.get('title', '')
                            all_markets.append(mk)
            except:
                pass
        
        # 2. גם שליפה רגילה של markets פעילים (למזג אוויר ודברים שלא ב-events)
        try:
            r2 = requests.get('https://gamma-api.polymarket.com/markets?limit=100&active=true', headers=headers, timeout=10)
            if r2.status_code == 200:
                all_markets.extend(r2.json())
        except:
            pass
        
        if not all_markets:
            if manual_chat_id: send_telegram(manual_chat_id, "❌ לא נמצאו שווקים כרגע.")
            return
        
        if manual_chat_id:
            send_telegram(manual_chat_id, f"🔍 נמצאו {len(all_markets)} שווקים. מסנן...")

        signals_found = 0
        for market in all_markets:
            name = market.get("question", "")
            
            # זיהוי נישה - אם זה לא באחת מ-4 הנישות, מדלגים
            niche = identify_niche(name)
            if niche == "🌍 כללי":
                continue

            # סינון שווקים מתים (נפח נמוך מ-$5000)
            volume = market.get('volume', 0)
            if volume and float(volume) < 5000:
                continue
            
            # פילטר תאריך: שווקים מה-events API כבר מסוננים להיום/מחר.
            # רק שווקים מהשליפה הרגילה צריכים סינון תאריך
            if not market.get('_event_title'):  # זה מהשליפה הרגילה, נסנן תאריך
                end_date = market.get('endDate', '')
                if end_date:
                    try:
                        market_date = datetime.datetime.fromisoformat(end_date.replace('Z', '+00:00')).date()
                        today_date = datetime.datetime.utcnow().date()
                        if market_date > today_date + datetime.timedelta(days=7):
                            continue
                    except:
                        pass

            # מחיר ישירות מה-API — ללא קריאה נוספת!
            prices = market.get('outcomePrices')
            if not prices:
                continue
            try:
                if isinstance(prices, str):
                    prices = _json.loads(prices)
                price = float(prices[0])
            except:
                continue

            yes_token = None
            clobtokens = market.get('clobTokenIds')
            if clobtokens:
                try:
                    if isinstance(clobtokens, str):
                        clobtokens = _json.loads(clobtokens)
                    yes_token = clobtokens[0]
                except:
                    pass
            
            try:

                # סינון בסיסי - תמחור קיצוני
                signal_type, entry_price, is_yes = None, 0, True
                # שינוי הלוגיקה: 
                # לא קונים YES רק בגלל שהמחיר נמוך (כי רוב הקבוצות לא יזכו במונדיאל)
                # קונים YES רק כשיש הסתברות חזקה (מעל 60%) אבל לא גבוהה מדי (עד 85%)
                # קונים NO כשיש תמחור יתר קיצוני (מעל 85%)
                
                if 0.60 <= price <= 0.85:
                    signal_type, entry_price, is_yes = "קנה YES", price, True
                elif price > 0.85:
                    signal_type, entry_price, is_yes = "קנה NO", round(1.0 - price, 2), False

                if signal_type:
                    whale_alert, whale_vol = check_whale_activity(yes_token)
                    ai_score, ai_reason = analyze_with_ai(name, entry_price, is_yes, niche)
                    
                    if whale_alert: ai_score = min(100, ai_score + 15)

                    # סף מינימלי של 80 כדי לסנן ספאם
                    if ai_score >= 80:
                        signal = {
                            "action": signal_type, "entry": entry_price, "ai_score": ai_score,
                            "reason": ai_reason, "whale_alert": whale_alert, "whale_vol": whale_vol
                        }
                        log_trade(name, signal_type, entry_price, ai_score)
                        stats = get_portfolio_stats()
                        msg = format_advanced_signal(name, signal, stats, niche)
                        
                        if manual_chat_id:
                            send_telegram(manual_chat_id, msg)
                        else:
                            broadcast_signal(msg)
                            
                        signals_found += 1
                        time.sleep(2)

            except: continue

        if manual_chat_id and signals_found == 0:
            send_telegram(manual_chat_id, "🤷‍♂️ סריקה הסתיימה. לא נמצאו הזדמנויות חזקות בנישות הנבחרות כרגע.")

    except Exception as e:
        print(f"Error scanning: {e}")

def auto_scanner():
    client = ClobClient("https://clob.polymarket.com")
    while True:
        scan_markets(client)
        time.sleep(CHECK_INTERVAL)

def main():
    setup_db()
    if os.getenv("TELEGRAM_CHAT_ID"):
        add_user(os.getenv("TELEGRAM_CHAT_ID"))
        
    print("Starting HolyPoly Bot...")
    
    scanner_thread = threading.Thread(target=auto_scanner, daemon=True)
    scanner_thread.start()
    
    handle_commands()

if __name__ == "__main__":
    main()
