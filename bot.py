import os
import sqlite3
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
import requests
import pyotp

# ================= SECURE CONFIGURATION =================
BOT_TOKEN = "8511257279:AAFae-zXUWPBXPuPAsRV7rftlnUQJ3xeFuE"
BOT_USERNAME = "mh_otp94_bot"
ADMIN_ID = 8855522653

# আপনার পার্মানেন্ট লকড এপিআই কী
LOCKED_API_KEY = "np_live_O4Qeh4k2DI01RPRT0WyhKz_qI5mFZxrRAVjDqis7dV0"
LOCKED_API_URL = "https://api.numberpool.io/v1"

REFER_BONUS = 50.0   
MIN_WITHDRAW = 1000.0 
SUPPORT_USERNAME = "mh_admin"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ================= DATABASE SETUP =================
def init_db():
    conn = sqlite3.connect("database.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            referrals_count INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT 0,
            total_otp INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_id TEXT,
            service TEXT,
            country TEXT,
            number TEXT,
            otp TEXT DEFAULT 'Waiting for OTP...',
            status TEXT DEFAULT 'ACTIVE',
            created_at INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            method TEXT,
            amount REAL,
            account_number TEXT,
            status TEXT DEFAULT 'Pending'
        )
    """)
    conn.commit()
    conn.close()

init_db()
user_states = {}

# ================= ADVANCED UNIVERSAL API HANDLER =================
def get_live_services():
    """এপিআই থেকে লাইভ সার্ভিস লিস্ট ফেচ করবে (একাধিক মেথড সাপোর্টসহ)"""
    headers = {"Authorization": f"Bearer {LOCKED_API_KEY}", "x-api-key": LOCKED_API_KEY}
    
    # ট্রায়াল ১: স্ট্যান্ডার্ড REST JSON
    try:
        resp = requests.get(f"{LOCKED_API_URL}/services", headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return [{"code": s.get("code", s.get("id", str(s))), "name": s.get("name", str(s))} for s in data]
            elif isinstance(data, dict):
                srv = data.get("services") or data.get("data") or []
                if isinstance(srv, list) and len(srv) > 0:
                    return [{"code": s.get("code", s.get("id", str(s))), "name": s.get("name", str(s))} for s in srv]
                elif isinstance(srv, dict):
                    return [{"code": k, "name": v if isinstance(v, str) else v.get("name", k)} for k, v in srv.items()]
    except:
        pass

    # ট্রায়াল ২: SMS-Activate / Stub Handler প্রোটোকল
    try:
        url = f"https://api.sms-activate.org/stubs/handler_api.php?api_key={LOCKED_API_KEY}&action=getServicesList"
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return [{"code": k, "name": v.get("name", k) if isinstance(v, dict) else k} for k, v in data.items()]
    except:
        pass

    # ডিফল্ট লিস্ট (যদি এপিআই সাময়িকভাবে রুট পরিবর্তন করে)
    return [
        {"code": "whatsapp", "name": "WhatsApp"},
        {"code": "telegram", "name": "Telegram"},
        {"code": "facebook", "name": "Facebook"},
        {"code": "instagram", "name": "Instagram"},
        {"code": "tiktok", "name": "TikTok"},
        {"code": "google", "name": "Google/YouTube"},
        {"code": "imo", "name": "IMO"}
    ]

def get_live_countries(service_code):
    headers = {"Authorization": f"Bearer {LOCKED_API_KEY}", "x-api-key": LOCKED_API_KEY}
    try:
        resp = requests.get(f"{LOCKED_API_URL}/countries?service={service_code}", headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return [{"code": c.get("code", c.get("id", str(c))), "name": c.get("name", str(c))} for c in data]
            elif isinstance(data, dict):
                cnt = data.get("countries") or data.get("data") or []
                if isinstance(cnt, list):
                    return [{"code": c.get("code", c.get("id", str(c))), "name": c.get("name", str(c))} for c in cnt]
    except:
        pass
    
    return [
        {"code": "benin", "name": "🇧🇯 Benin"},
        {"code": "iraq", "name": "🇮🇶 Iraq"},
        {"code": "ivory_coast", "name": "🇨🇮 Ivory Coast"},
        {"code": "madagascar", "name": "🇲🇬 Madagascar"},
        {"code": "mali", "name": "🇲🇱 Mali"},
        {"code": "saudi_arabia", "name": "🇸🇦 Saudi Arabia"},
        {"code": "tajikistan", "name": "🇹🇯 Tajikistan"},
        {"code": "togo", "name": "🇹🇬 Togo"},
        {"code": "ukraine", "name": "🇺🇦 Ukraine"}
    ]

def purchase_live_number(service, country):
    headers = {"Authorization": f"Bearer {LOCKED_API_KEY}", "x-api-key": LOCKED_API_KEY, "Content-Type": "application/json"}
    
    # ট্রায়াল ১: JSON POST /order অথবা /buy
    for endpoint in ["order", "buy", "getNumber"]:
        try:
            payload = {"service": service, "country": country}
            resp = requests.post(f"{LOCKED_API_URL}/{endpoint}", headers=headers, json=payload, timeout=8)
            if resp.status_code in (200, 201):
                data = resp.json()
                order_id = data.get("order_id") or data.get("id") or data.get("order")
                number = data.get("number") or data.get("phone")
                if number:
                    return {"success": True, "order_id": str(order_id), "number": str(number)}
                if "error" in data or "message" in data:
                    return {"success": False, "msg": data.get("error") or data.get("message")}
        except:
            pass

    # ট্রায়াল ২: GET মেথড প্যারামিটার রিকোয়েস্ট
    try:
        resp = requests.get(f"{LOCKED_API_URL}/order?service={service}&country={country}", headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            order_id = data.get("order_id") or data.get("id")
            number = data.get("number") or data.get("phone")
            if number:
                return {"success": True, "order_id": str(order_id), "number": str(number)}
    except:
        pass

    return {"success": False, "msg": "API সার্ভারে এই সার্ভিসের স্টক এই মুহূর্তে খালি আছে বা এপিআই ব্যালেন্স শেষ!"}

def check_live_otp(order_id):
    headers = {"Authorization": f"Bearer {LOCKED_API_KEY}", "x-api-key": LOCKED_API_KEY}
    try:
        resp = requests.get(f"{LOCKED_API_URL}/order/{order_id}", headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("otp") or data.get("sms") or data.get("code")
    except:
        pass
    return None

# ================= KEYBOARDS =================
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📱 GET NUMBER"),
        types.KeyboardButton("🔍 Search Number"),
        types.KeyboardButton("📊 TRAFFIC"),
        types.KeyboardButton("🔐 2FA ONLINE"),
        types.KeyboardButton("🎁 Refer"),
        types.KeyboardButton("📅 WITHDRAWAL"),
        types.KeyboardButton("👤 SUPPORT")
    )
    return markup

# ================= START COMMAND =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username or "User"
    args = message.text.split()

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()

    if not user:
        referred_by = 0
        if len(args) > 1 and args[1].isdigit():
            ref_id = int(args[1])
            if ref_id != user_id:
                referred_by = ref_id
                c.execute("UPDATE users SET balance = balance + ?, referrals_count = referrals_count + 1 WHERE user_id = ?", (REFER_BONUS, ref_id))
                try:
                    bot.send_message(ref_id, f"🎉 আপনার রেফারেলে নতুন মেম্বার যুক্ত হয়েছে! বোনাস পেয়েছেন {REFER_BONUS} ৳")
                except:
                    pass
        c.execute("INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)", (user_id, username, referred_by))
        conn.commit()
    conn.close()

    welcome_text = (
        "╔════════════════════════╗\n"
        "      👑 **NUMBER BOT**\n"
        "╚════════════════════════╝\n"
        "🚀 **Welcome to Number & OTP Service**\n"
        "────────────────────────\n"
        "✅ **Choose an option below to continue using the bot.**\n"
        "────────────────────────\n"
        "💎 *Premium OTP Service*"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu())

# ================= GET NUMBER FLOW =================
@bot.message_handler(func=lambda msg: msg.text == "📱 GET NUMBER")
def get_number_flow(message):
    bot.send_chat_action(message.chat.id, 'typing')
    services = get_live_services()
    
    if not services:
        bot.send_message(message.chat.id, "❌ **এপিআই থেকে কোনো সার্ভিস লোড করা যায়নি!**")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(text=f"🔹 {s['name']}", callback_data=f"srv_{s['code']}_{s['name'][:10]}") for s in services[:20]]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton(text="❌ Close", callback_data="close_box"))
    bot.send_message(message.chat.id, "📍 **Select a Service:**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("srv_"))
def on_service_chosen(call):
    parts = call.data.split("_")
    code = parts[1]
    name = parts[2]
    
    bot.answer_callback_query(call.id, "দেশ লোড হচ্ছে...")
    countries = get_live_countries(code)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(text=f"{c['name']}", callback_data=f"ord_{code}_{c['code']}") for c in countries[:20]]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton(text="🔙 Back", callback_data="back_services"))
    bot.edit_message_text(f"📍 **Select a country for {name}:**", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ord_"))
def on_order_number(call):
    _, service, country = call.data.split("_")
    user_id = call.from_user.id
    
    bot.edit_message_text("⏳ **সরাসরি এপিআই থেকে নম্বর জেনারেট করা হচ্ছে...**", chat_id=call.message.chat.id, message_id=call.message.message_id)
    
    res = purchase_live_number(service, country)
    if res.get("success"):
        order_id = res["order_id"]
        number = res["number"]
        
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("INSERT INTO orders (user_id, order_id, service, country, number, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, order_id, service, country, number, int(time.time())))
        db_id = c.lastrowid
        conn.commit()
        conn.close()

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(text="🔄 Get OTP", callback_data=f"chkotp_{db_id}"),
            types.InlineKeyboardButton(text="❌ Cancel Number", callback_data=f"cnlord_{db_id}")
        )
        
        bot.edit_message_text(
            f"✅ **Number Allocated Successfully!**\n\n"
            f"📱 **Service:** `{service.upper()}`\n"
            f"🌍 **Country:** `{country.upper()}`\n"
            f"📞 **Number:** `{number}`\n\n"
            f"⏳ *Use this number to receive your OTP code.*",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    else:
        err_msg = res.get("msg", "API Error")
        bot.edit_message_text(f"❌ **নম্বর সংগ্রহ ব্যর্থ হয়েছে!**\n\nকারণ: `{err_msg}`", chat_id=call.message.chat.id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chkotp_"))
def on_check_otp_click(call):
    db_id = int(call.data.split("_")[1])
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT order_id, number, otp, user_id FROM orders WHERE id = ?", (db_id,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        bot.answer_callback_query(call.id, "অর্ডার পাওয়া যায়নি!")
        return
        
    order_id, number, local_otp, user_id = row
    
    live_otp = check_live_otp(order_id)
    if live_otp:
        c.execute("UPDATE orders SET otp = ?, status = 'COMPLETED' WHERE id = ?", (live_otp, db_id))
        c.execute("UPDATE users SET total_otp = total_otp + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text(
            f"🎉 **OTP Received Successfully!**\n\n"
            f"📞 **Number:** `{number}`\n"
            f"🔑 **OTP Code:** `{live_otp}`\n\n"
            f"✅ Service Completed.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
    elif local_otp != "Waiting for OTP...":
        conn.close()
        bot.edit_message_text(f"🎉 **OTP Received!**\n\n📞 Number: `{number}`\n🔑 OTP: `{local_otp}`", chat_id=call.message.chat.id, message_id=call.message.message_id)
    else:
        conn.close()
        bot.answer_callback_query(call.id, "⏳ OTP এখনো আসেনি। কিছুক্ষণ পর আবার ক্লিক করুন...", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cnlord_"))
def on_cancel_order_click(call):
    db_id = int(call.data.split("_")[1])
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = ?", (db_id,))
    conn.commit()
    conn.close()
    bot.edit_message_text("❌ **Number Cancelled successfully.**", chat_id=call.message.chat.id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "back_services")
def on_back_to_services(call):
    services = get_live_services()
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(text=f"🔹 {s['name']}", callback_data=f"srv_{s['code']}_{s['name'][:10]}") for s in services[:20]]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton(text="❌ Close", callback_data="close_box"))
    bot.edit_message_text("📍 **Select a Service:**", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "close_box")
def on_close_box_click(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ================= OTHER MODULES (Search, 2FA, Refer, Withdrawal, Admin) =================
@bot.message_handler(func=lambda msg: msg.text == "🔍 Search Number")
def search_num_ui(message):
    user_states[message.from_user.id] = "SEARCHING"
    bot.send_message(message.chat.id, "🔍 **Enter 3 to 9 digits to search for a number:**", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(text="🔙 Cancel", callback_data="close_box")))

@bot.message_handler(func=lambda msg: msg.text == "🔐 2FA ONLINE")
def two_fa_ui(message):
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(text="🛡️ Generate 2fa code", callback_data="ask_2fa_key"))
    bot.send_message(message.chat.id, "🔐 **Generate 2FA Code:**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "ask_2fa_key")
def on_ask_2fa(call):
    user_states[call.from_user.id] = "WAITING_2FA"
    bot.edit_message_text("🔑 আপনার **2FA Secret Key** টি লিখে পাঠান:", chat_id=call.message.chat.id, message_id=call.message.message_id)

@bot.message_handler(func=lambda msg: msg.text == "📊 TRAFFIC")
def traffic_ui(message):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    u = c.fetchone()[0]
    conn.close()
    bot.send_message(message.chat.id, f"📊 **Live Stats:**\nUsers: `{u + 20449}`\nAPI Status: `Online`")

@bot.message_handler(func=lambda msg: msg.text == "🎁 Refer")
def refer_ui(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT referrals_count FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(message.chat.id, f"🎁 **Refer & Earn**\n\nLink:\n`{ref_link}`\nRefers: {row[0] if row else 0}")

@bot.message_handler(func=lambda msg: msg.text == "📅 WITHDRAWAL")
def withdraw_ui(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    bal = c.fetchone()[0]
    conn.close()
    markup = types.InlineKeyboardMarkup(row_width=2).add(
        types.InlineKeyboardButton(text="👝 bKash", callback_data="w_bKash"),
        types.InlineKeyboardButton(text="👝 Nagad", callback_data="w_Nagad")
    )
    bot.send_message(message.chat.id, f"🥷 **Withdrawal**\nBalance: {bal}৳\nMinimum: {MIN_WITHDRAW}৳\n\nSelect Method:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("w_"))
def on_withdraw_select(call):
    method = call.data.split("_")[1]
    user_states[call.from_user.id] = f"WITHDRAW_{method}"
    bot.edit_message_text(f"📝 আপনার **{method}** নাম্বার এবং পরিমাণ লিখুন:\n(যেমন: `017XXXXXXXX 1000`)", chat_id=call.message.chat.id, message_id=call.message.message_id)

@bot.message_handler(func=lambda msg: msg.text == "👤 SUPPORT")
def support_ui(message):
    bot.send_message(message.chat.id, f"💬 **Support:** @{SUPPORT_USERNAME}")

# ================= ADMIN PANEL =================
@bot.message_handler(commands=['admin'])
def admin_panel_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(ADMIN_ID, "👑 **Admin Panel Active**\n\nCommands:\n`/addbalance <id> <amount>`\n`/broadcast <text>`")

@bot.message_handler(commands=['addbalance'])
def add_bal(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uid, amt = message.text.split()
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), int(uid)))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ Added {amt}৳ to {uid}")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"Error: {e}")

@bot.message_handler(commands=['broadcast'])
def bdcst(message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.split(maxsplit=1)[1]
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    for u in users:
        try: bot.send_message(u[0], f"📢 **Notice:**\n\n{text}")
        except: pass
    bot.send_message(ADMIN_ID, "✅ Broadcast completed!")

@bot.message_handler(func=lambda msg: True)
def text_dispatcher(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state:
        return

    if state == "WAITING_2FA":
        try:
            totp = pyotp.TOTP(message.text.strip().replace(" ", ""))
            bot.send_message(message.chat.id, f"✅ **2FA Code:** `{totp.now()}`", reply_markup=main_menu())
        except:
            bot.send_message(message.chat.id, "❌ Invalid Key!", reply_markup=main_menu())
        user_states.pop(user_id, None)

    elif state.startswith("WITHDRAW_"):
        parts = message.text.strip().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ সঠিক ফরম্যাটে লিখুন: `017XXXXXXXX 1000`")
            return
        acc, amt = parts[0], float(parts[1])
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        bal = c.fetchone()[0]
        if amt > bal or amt < MIN_WITHDRAW:
            bot.send_message(message.chat.id, "❌ অপর্যাপ্ত ব্যালেন্স!", reply_markup=main_menu())
            conn.close()
            user_states.pop(user_id, None)
            return
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amt, user_id))
        c.execute("INSERT INTO withdrawals (user_id, method, amount, account_number) VALUES (?, ?, ?, ?)", (user_id, state.split("_")[1], amt, acc))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"🚨 **New Withdrawal!**\nUser: `{user_id}`\nAmount: `{amt}৳`\nAcc: `{acc}`")
        bot.send_message(message.chat.id, "✅ উইথড্র রিকোয়েস্ট সফল হয়েছে!", reply_markup=main_menu())
        user_states.pop(user_id, None)

# ================= KEEP ALIVE SERVER =================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running 24/7!")

if __name__ == "__main__":
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), SimpleHandler).serve_forever(), daemon=True).start()
    print("🤖 Bot started successfully with universal API handlers...")
    bot.infinity_polling()
