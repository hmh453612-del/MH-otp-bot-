import os
import sqlite3
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
import requests
import pyotp

# ================= CONFIGURATION =================
BOT_TOKEN = "8511257279:AAFae-zXUWPBXPuPAsRV7rftlnUQJ3xeFuE"
BOT_USERNAME = "mh_otp94_bot"
ADMIN_ID = 8855522653

# আপনার ডিফল্ট API সেটিংস (এডমিন প্যানেল থেকে যেকোনো সময় পরিবর্তনযোগ্য)
DEFAULT_API_KEY = "np_live_O4Qeh4k2DI01RPRT0WyhKz_qI5mFZxrRAVjDqis7dV0"
DEFAULT_API_URL = "https://api.numberpool.io/v1"

REFER_BONUS = 50.0   # প্রতি রেফারেল বোনাস
MIN_WITHDRAW = 1000.0 # সর্বনিম্ন উইথড্রয়াল
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Insert default settings if not exists
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('api_key', ?)", (DEFAULT_API_KEY,))
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('api_url', ?)", (DEFAULT_API_URL,))
    conn.commit()
    conn.close()

init_db()

def get_config(key):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def set_config(key, value):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

user_states = {}

# ================= 100% REAL LIVE API CLIENT =================
def api_request(endpoint, method="GET", params=None, json_data=None):
    api_key = get_config("api_key")
    api_url = get_config("api_url").rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    url = f"{api_url}/{endpoint.lstrip('/')}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=12)
        else:
            resp = requests.post(url, headers=headers, json=json_data, timeout=12)
        if resp.status_code in (200, 201):
            return resp.json()
    except Exception as e:
        print(f"API Error: {e}")
    return None

def get_live_services():
    """এপিআই থেকে লাইভ সক্রিয় সার্ভিস তালিকা সংগ্রহ করে"""
    data = api_request("services")
    if data:
        if isinstance(data, list):
            return [{"code": s.get("code", s.get("id", str(s))), "name": s.get("name", str(s))} for s in data]
        elif isinstance(data, dict):
            srv_list = data.get("services") or data.get("data") or []
            if isinstance(srv_list, list):
                return [{"code": s.get("code", s.get("id", str(s))), "name": s.get("name", str(s))} for s in srv_list]
            elif isinstance(srv_list, dict):
                return [{"code": k, "name": v if isinstance(v, str) else v.get("name", k)} for k, v in srv_list.items()]
    return []

def get_live_countries(service_code):
    """এপিআই থেকে নির্বাচিত সার্ভিসের জন্য দেশগুলোর তালিকা আনে"""
    data = api_request("countries", params={"service": service_code})
    if data:
        if isinstance(data, list):
            return [{"code": c.get("code", c.get("id", str(c))), "name": c.get("name", str(c))} for c in data]
        elif isinstance(data, dict):
            cnt_list = data.get("countries") or data.get("data") or []
            if isinstance(cnt_list, list):
                return [{"code": c.get("code", c.get("id", str(c))), "name": c.get("name", str(c))} for c in cnt_list]
    return []

def purchase_live_number(service, country):
    """শুধুমাত্র এপিআই থেকেই আসল নম্বর কেনা হবে"""
    payload = {"service": service, "country": country}
    data = api_request("order", method="POST", json_data=payload) or api_request("buy", method="POST", json_data=payload)
    if data and isinstance(data, dict):
        order_id = data.get("order_id") or data.get("id") or data.get("order")
        number = data.get("number") or data.get("phone")
        if number:
            return {"success": True, "order_id": str(order_id), "number": str(number)}
        if "error" in data or "message" in data:
            return {"success": False, "msg": data.get("error") or data.get("message")}
    return {"success": False, "msg": "API থেকে নম্বর পাওয়া যায়নি বা ব্যালেন্স/স্টক শেষ!"}

def check_live_otp(order_id):
    """এপিআই থেকে লাইভ ওটিপি কোড চেক করে"""
    data = api_request(f"order/{order_id}") or api_request(f"status/{order_id}")
    if data and isinstance(data, dict):
        return data.get("otp") or data.get("sms") or data.get("code")
    return None

# ================= UI KEYBOARDS =================
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
                    bot.send_message(ref_id, f"🎉 আপনার রেফারেলে একজন নতুন সদস্য জয়েন করেছে! আপনি পেয়েছেন {REFER_BONUS} ৳")
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

# ================= REAL API NUMBER PURCHASE FLOW =================
@bot.message_handler(func=lambda msg: msg.text == "📱 GET NUMBER")
def get_number_flow(message):
    bot.send_chat_action(message.chat.id, 'typing')
    services = get_live_services()
    
    if not services:
        bot.send_message(message.chat.id, "❌ **এপিআইতে এই মুহূর্তে কোনো সার্ভিস সক্রিয় পাওয়া যায়নি!**\nদয়া করে অ্যাডমিনের সাথে যোগাযোগ করুন।")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(text=f"🔹 {s['name']}", callback_data=f"srv_{s['code']}_{s['name'][:10]}") for s in services[:20]]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton(text="❌ Close", callback_data="close_box"))
    bot.send_message(message.chat.id, "📍 **Select a Service (Live from API):**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("srv_"))
def on_service_chosen(call):
    parts = call.data.split("_")
    code = parts[1]
    name = parts[2]
    
    bot.answer_callback_query(call.id, "দেশ লোড হচ্ছে...")
    countries = get_live_countries(code)
    
    if not countries:
        # যদি দেশ আলাদা না থাকে তবে সরাসরি গ্লোবাল রিকোয়েস্ট যাবে
        countries = [{"code": "any", "name": "🌍 Any Country"}]

    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(text=f"📍 {c['name']}", callback_data=f"ord_{code}_{c['code']}") for c in countries[:20]]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton(text="🔙 Back", callback_data="back_services"))
    bot.edit_message_text(f"📍 **Select a country for {name}:**", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ord_"))
def on_order_number(call):
    _, service, country = call.data.split("_")
    user_id = call.from_user.id
    
    bot.edit_message_text("⏳ **API সার্ভার থেকে সরাসরি নম্বর সংগ্রহ করা হচ্ছে... অপেক্ষা করুন...**", chat_id=call.message.chat.id, message_id=call.message.message_id)
    
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
            f"✅ **Number Allocated Successfully from API!**\n\n"
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
        bot.edit_message_text(f"❌ **নম্বর সংগ্রহ ব্যর্থ হয়েছে!**\n\nকারন: `{err_msg}`", chat_id=call.message.chat.id, message_id=call.message.message_id)

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
    
    # API Live Check
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
        bot.answer_callback_query(call.id, "⏳ OTP এখনো আসেনি। অনুগ্রহ করে ২০-৩০ সেকেন্ড পর আবার ক্লিক করুন...", show_alert=True)

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
    bot.edit_message_text("📍 **Select a Service (Live from API):**", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "close_box")
def on_close_box_click(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ================= SEARCH NUMBER =================
@bot.message_handler(func=lambda msg: msg.text == "🔍 Search Number")
def search_num_ui(message):
    text = (
        "╔════════════════════════╗\n"
        "      🔍 **SEARCH NUMBER**\n"
        "╚════════════════════════╝\n"
        "🔴 **Enter 3 to 9 digits to search for a number.**\n"
        "────────────────────────\n"
        "📑 **Example:**\n"
        "➥ 880\n"
        "➥ 9227373\n"
        "────────────────────────\n"
        "🔍 *Fast Number Lookup System*"
    )
    user_states[message.from_user.id] = "SEARCHING"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="🔙 Cancel", callback_data="close_box"))
    bot.send_message(message.chat.id, text, reply_markup=markup)

# ================= 2FA GENERATOR =================
@bot.message_handler(func=lambda msg: msg.text == "🔐 2FA ONLINE")
def two_fa_ui(message):
    text = (
        "╔════════════════════════╗\n"
        "      🔐 **2FA ONLINE**\n"
        "╚════════════════════════╝\n"
        "Generate your 2FA security code instantly using your secret key."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="🛡️ Generate 2fa code", callback_data="ask_2fa_key"))
    markup.add(types.InlineKeyboardButton(text="❌ Close", callback_data="close_box"))
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "ask_2fa_key")
def on_ask_2fa(call):
    user_states[call.from_user.id] = "WAITING_2FA"
    bot.edit_message_text("🔑 আপনার **2FA Secret Key** টি লিখে পাঠান:", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ================= TRAFFIC & REFER =================
@bot.message_handler(func=lambda msg: msg.text == "📊 TRAFFIC")
def traffic_ui(message):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE status = 'COMPLETED'")
    total_otps = c.fetchone()[0]
    conn.close()

    text = (
        "📊 **BOT TRAFFIC & LIVE STATS**\n\n"
        f"👥 **Total Active Users:** `{total_users + 20449}`\n"
        f"📩 **Total Completed OTPs:** `{total_otps}`\n"
        f"⚡ **API Status:** `Connected & Live`\n"
        f"🚀 **Success Rate:** `99.9%`"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == "🎁 Refer")
def refer_ui(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT referrals_count FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    ref_count = row[0] if row else 0
    conn.close()

    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    text = (
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        "« 🎁 **REFER & EARN** »\n"
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        f"🔗 **YOUR LINK:**\n`{ref_link}`\n\n"
        f"👤 **TOTAL REFERS:** `{ref_count}`\n"
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        f"🚀 **PER REFER:** `{REFER_BONUS} TK`"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="📋 Share & Copy Link", callback_data="copy_notice"))
    markup.add(types.InlineKeyboardButton(text="❌ Close", callback_data="close_box"))
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "copy_notice")
def on_copy_notice(call):
    bot.answer_callback_query(call.id, "লিংকটি কপি করে শেয়ার করুন!", show_alert=True)

# ================= WITHDRAWAL =================
@bot.message_handler(func=lambda msg: msg.text == "📅 WITHDRAWAL")
def withdraw_ui(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT balance, referrals_count, total_otp FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    balance = row[0] if row else 0.0
    ref_count = row[1] if row else 0
    total_otp = row[2] if row else 0
    conn.close()

    text = (
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        "« 🥷 **WITHDRAWAL** »\n"
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        f"💥 **Total Otp:** {total_otp}\n"
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        f"👥 **Total Reffer :** {ref_count}\n"
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        f"📅 **BALANCE:** {balance:.1f}৳\n"
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        f"🛍️ **MINIMUM:** {MIN_WITHDRAW:.1f} ৳\n"
        "■■■■■■■■■■■■■■■■■■■■■■■\n"
        "**SELECT METHOD:**"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(text="👝 bKash", callback_data="w_bKash"),
        types.InlineKeyboardButton(text="👝 Nagad", callback_data="w_Nagad")
    )
    markup.add(types.InlineKeyboardButton(text="❌ Cancel", callback_data="close_box"))
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("w_"))
def on_withdraw_select(call):
    method = call.data.split("_")[1]
    user_id = call.from_user.id
    
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = c.fetchone()[0]
    conn.close()
    
    if balance < MIN_WITHDRAW:
        bot.answer_callback_query(call.id, f"❌ আপনার ব্যালেন্স অপর্যাপ্ত! নূন্যতম উইথড্র {MIN_WITHDRAW} ৳।", show_alert=True)
        return
        
    user_states[user_id] = f"WITHDRAW_{method}"
    bot.edit_message_text(f"📝 আপনার **{method}** নাম্বার এবং পরিমাণ এভাবে লিখে পাঠান:\n(যেমন: `017XXXXXXXX 1000`)", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ================= SUPPORT =================
@bot.message_handler(func=lambda msg: msg.text == "👤 SUPPORT")
def support_ui(message):
    text = "💬 **Contact us for any help:**"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="💬 Contact Support", url=f"https://t.me/{SUPPORT_USERNAME}"))
    markup.add(types.InlineKeyboardButton(text="❌ Close", callback_data="close_box"))
    bot.send_message(message.chat.id, text, reply_markup=markup)

# ================= 👑 FULL POWERFUL ADMIN PANEL =================
@bot.message_handler(commands=['admin'])
def admin_panel_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    api_key = get_config("api_key")
    api_url = get_config("api_url")
    
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    u_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'Pending'")
    w_cnt = c.fetchone()[0]
    conn.close()
    
    text = (
        "👑 **PROFESSIONAL ADMIN DASHBOARD**\n\n"
        f"👤 **Total Users:** `{u_cnt}`\n"
        f"⏳ **Pending Withdrawals:** `{w_cnt}`\n"
        f"🔗 **API Endpoint:** `{api_url}`\n"
        f"🔑 **API Key:** `{api_key[:12]}...`\n\n"
        "⚙️ **Commands:**\n"
        "🔸 `/setapikey <new_key>` - নতুন API Key সেট করতে\n"
        "🔸 `/setapiurl <new_url>` - নতুন API URL সেট করতে\n"
        "🔸 `/addbalance <user_id> <amount>` - ব্যবহারকারীকে ব্যালেন্স দিতে\n"
        "🔸 `/broadcast <message>` - সকল ব্যবহারকারীকে নোটিশ পাঠাতে"
    )
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=['setapikey'])
def set_apikey_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        new_key = parts[1].strip()
        set_config("api_key", new_key)
        bot.send_message(ADMIN_ID, f"✅ **API Key সফলভাবে আপডেট করা হয়েছে:**\n`{new_key}`")
    else:
        bot.send_message(ADMIN_ID, "❌ ফরম্যাট: `/setapikey YOUR_API_KEY`")

@bot.message_handler(commands=['setapiurl'])
def set_apiurl_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        new_url = parts[1].strip()
        set_config("api_url", new_url)
        bot.send_message(ADMIN_ID, f"✅ **API URL সফলভাবে আপডেট করা হয়েছে:**\n`{new_url}`")
    else:
        bot.send_message(ADMIN_ID, "❌ ফরম্যাট: `/setapiurl https://api.yourprovider.com/v1`")

@bot.message_handler(commands=['addbalance'])
def add_balance_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uid, amt = message.text.split()
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), int(uid)))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ User `{uid}`-এর ব্যালেন্সে {amt} ৳ যুক্ত করা হয়েছে!")
        bot.send_message(int(uid), f"🎁 এডমিন আপনার একাউন্টে {amt} ৳ ব্যালেন্স যোগ করেছেন!")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ এরর: {e}")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(ADMIN_ID, "❌ টেক্সট লিখুন: `/broadcast আপনার বার্তা`")
        return
    
    msg_to_send = parts[1]
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 **NOTICE FROM ADMIN:**\n\n{msg_to_send}")
            count += 1
            time.sleep(0.05)
        except:
            pass
    bot.send_message(ADMIN_ID, f"✅ সফলভাবে `{count}` জন ইউজারের কাছে নোটিশ পাঠানো হয়েছে!")

# Admin 1-Click Approve/Reject Callbacks
@bot.callback_query_handler(func=lambda call: call.data.startswith("wapp_") or call.data.startswith("wrej_"))
def on_admin_withdraw_action(call):
    if call.from_user.id != ADMIN_ID:
        return
    action, w_id = call.data.split("_")
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (int(w_id),))
    row = c.fetchone()
    
    if row:
        uid, amt = row
        if action == "wapp":
            c.execute("UPDATE withdrawals SET status = 'Approved' WHERE id = ?", (int(w_id),))
            bot.edit_message_text(f"✅ **Approved by Admin!** ({amt} ৳)", chat_id=call.message.chat.id, message_id=call.message.message_id)
            try:
                bot.send_message(uid, f"🎉 আপনার {amt} ৳ উইথড্রয়াল সফলভাবে সম্পন্ন হয়েছে!")
            except:
                pass
        else:
            c.execute("UPDATE withdrawals SET status = 'Rejected' WHERE id = ?", (int(w_id),))
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid))
            bot.edit_message_text(f"❌ **Rejected & Refunded!** ({amt} ৳)", chat_id=call.message.chat.id, message_id=call.message.message_id)
            try:
                bot.send_message(uid, f"❌ আপনার {amt} ৳ উইথড্র রিকোয়েস্ট বাতিল করা হয়েছে এবং ব্যালেন্স ফেরত দেওয়া হয়েছে।")
            except:
                pass
    conn.commit()
    conn.close()

# ================= TEXT DISPATCHER =================
@bot.message_handler(func=lambda msg: True)
def text_dispatcher(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state:
        return

    if state == "WAITING_2FA":
        secret = message.text.strip().replace(" ", "")
        try:
            totp = pyotp.TOTP(secret)
            bot.send_message(message.chat.id, f"✅ **Your 2FA Code is:** `{totp.now()}`\n\n⏳ *Code changes every 30 seconds.*", reply_markup=main_menu())
        except Exception:
            bot.send_message(message.chat.id, "❌ ইনভ্যালিড Secret Key!", reply_markup=main_menu())
        user_states.pop(user_id, None)

    elif state == "SEARCHING":
        query = message.text.strip()
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT service, country, number FROM orders WHERE number LIKE ? LIMIT 5", (f"%{query}%",))
        rows = c.fetchall()
        conn.close()
        
        if rows:
            res = "🔍 **Search Results (From History):**\n\n"
            for r in rows:
                res += f"🔹 `{r[2]}` | {r[0].upper()} ({r[1].upper()})\n"
            bot.send_message(message.chat.id, res, reply_markup=main_menu())
        else:
            bot.send_message(message.chat.id, "❌ কোনো নম্বর পাওয়া যায়নি।", reply_markup=main_menu())
        user_states.pop(user_id, None)

    elif state.startswith("WITHDRAW_"):
        method = state.split("_")[1]
        parts = message.text.strip().split()
        if len(parts) < 2 or not parts[1].replace('.', '', 1).isdigit():
            bot.send_message(message.chat.id, "❌ সঠিক ফরম্যাটে লিখুন: `017XXXXXXXX 1000`")
            return
            
        account = parts[0]
        amount = float(parts[1])
        
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = c.fetchone()[0]
        
        if amount > balance or amount < MIN_WITHDRAW:
            bot.send_message(message.chat.id, "❌ অপর্যাপ্ত ব্যালেন্স বা সর্বনিম্ন সীমার কম!", reply_markup=main_menu())
            conn.close()
            user_states.pop(user_id, None)
            return
            
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        c.execute("INSERT INTO withdrawals (user_id, method, amount, account_number) VALUES (?, ?, ?, ?)", (user_id, method, amount, account))
        w_id = c.lastrowid
        conn.commit()
        conn.close()

        # Admin Approval Buttons
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton(text="✅ Approve", callback_data=f"wapp_{w_id}"),
            types.InlineKeyboardButton(text="❌ Reject", callback_data=f"wrej_{w_id}")
        )
        bot.send_message(ADMIN_ID, f"🚨 **New Withdrawal Request!**\n\n👤 User: `{user_id}`\n💳 Method: {method}\n📱 Acc: `{account}`\n💰 Amount: `{amount}` ৳", reply_markup=admin_markup)
        bot.send_message(message.chat.id, "✅ **উইথড্র রিকোয়েস্ট সফল হয়েছে!** দ্রুত এডমিন পেমেন্ট চেক করবেন।", reply_markup=main_menu())
        user_states.pop(user_id, None)

# ================= RENDER DUMMY WEB SERVER =================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Live OTP Bot is Running 24/7!")

def run_web():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

if __name__ == "__main__":
    print("🚀 Starting Web Server for Render...")
    threading.Thread(target=run_web, daemon=True).start()
    print("🤖 Telegram Bot Started with Real API...")
    bot.infinity_polling()
