import re, time, asyncio, os, json, random, requests as req
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ========== ENVIRONMENT VARIABLES ==========
BOT_TOKEN = "8808046020:AAEjfprJIKHe7y5TZJckjL22b2yXyM4gKfQ"
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "")
SIGHTENGINE_USER = os.environ.get("SIGHTENGINE_API_USER", "")
SIGHTENGINE_SECRET = os.environ.get("SIGHTENGINE_API_SECRET", "")

# Vercel KV (REST API)
KV_REST_API_URL = os.environ.get("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.environ.get("KV_REST_API_TOKEN", "")

# ========== KV HELPERS ==========
def kv_get(key):
    if not KV_REST_API_URL: return None
    url = f"{KV_REST_API_URL}/get/{key}"
    headers = {"Authorization": f"Bearer {KV_REST_API_TOKEN}"}
    try:
        resp = req.get(url, headers=headers, timeout=5)
        data = resp.json()
        return data.get("result")
    except:
        return None

def kv_set(key, value):
    if not KV_REST_API_URL: return
    url = f"{KV_REST_API_URL}/set/{key}"
    headers = {"Authorization": f"Bearer {KV_REST_API_TOKEN}"}
    try:
        req.post(url, headers=headers, json={"value": value}, timeout=5)
    except:
        pass

# ========== WARNING SYSTEM ==========
warnings_db = defaultdict(lambda: defaultdict(int))
spam_tracker = defaultdict(list)
message_map = defaultdict(list)

# ========== REGEX ==========
INVITE_LINK_REGEX = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/|\+)?[\w\-]+", re.IGNORECASE)
BOT_LINK_REGEX    = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/(?!joinchat/|\+)[\w]+", re.IGNORECASE)

# ========== PASSWORD AUTH ==========
DM_PASSWORD = "RISHAVBHAGWANHAI"
authenticated_users = set()

# ========== HELPERS ==========
async def is_admin(chat, user_id):
    member = await chat.get_member(user_id)
    return member.status in ("creator", "administrator")

async def safe_delete(msg):
    try: await msg.delete()
    except: pass

async def ban_user(context, chat_id, user_id, duration=180, reason=""):
    until = datetime.now() + timedelta(days=duration)
    try:
        await context.bot.ban_chat_member(chat_id, user_id, until_date=until)
        await context.bot.send_message(chat_id,
            f"🚫 <b>Banned for {duration} days</b> — {reason}\nUser: {user_id}",
            parse_mode="HTML")
    except: pass

async def send_warning(context, chat_id, user_id, name, count, type_):
    msg = (
        f"⚠️ <b>Warning {count}/2 for @{name}</b>\n"
        f"Reason: {type_}\n"
        f"Next violation = 6‑month ban."
    )
    sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML")
    await asyncio.sleep(10)
    await safe_delete(sent)

# ========== BOT CONFIG (KV) ==========
def get_official_bot_links():
    data = kv_get("official_bots")
    if data:
        bots = json.loads(data)
        return [b['link'] for b in bots]
    return []

def get_random_bot_config():
    data = kv_get("official_bots")
    if data:
        bots = json.loads(data)
        if bots:
            return random.choice(bots)
    return None

def add_bot_to_config(name, username, link, currency):
    bots = []
    data = kv_get("official_bots")
    if data:
        bots = json.loads(data)
    bots.append({"name": name, "username": username, "link": link, "currency": currency})
    kv_set("official_bots", json.dumps(bots))

def delete_bot_by_index(index):
    data = kv_get("official_bots")
    if data:
        bots = json.loads(data)
        if 0 <= index < len(bots):
            del bots[index]
            kv_set("official_bots", json.dumps(bots))
            return True
    return False

def list_bots():
    data = kv_get("official_bots")
    if data:
        return json.loads(data)
    return []

# ========== GROUP HANDLERS ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or chat.type == "private":
        return

    if await is_admin(chat, user.id):
        return

    text = msg.text or msg.caption or ""
    user_id = user.id
    chat_id = chat.id

    # GC link
    if INVITE_LINK_REGEX.search(text):
        official_links = get_official_bot_links()
        if any(link in text for link in official_links):
            return
        await safe_delete(msg)
        warnings_db[chat_id][user_id] += 1
        cnt = warnings_db[chat_id][user_id]
        if cnt >= 2:
            await ban_user(context, chat_id, user_id, duration=180, reason="GC links")
            warnings_db[chat_id][user_id] = 0
        else:
            await send_warning(context, chat_id, user_id, user.first_name, cnt, "GC links")
        return

    # Other bot links
    if BOT_LINK_REGEX.search(text):
        official_links = get_official_bot_links()
        if any(link in text for link in official_links):
            return
        await safe_delete(msg)
        await send_warning(context, chat_id, user_id, user.first_name, 1, "bot links")
        return

    # NSFW image
    if msg.photo and SIGHTENGINE_USER and SIGHTENGINE_SECRET:
        file = await msg.photo[-1].get_file()
        photo_url = file.file_path
        params = {
            'url': photo_url,
            'models': 'nudity-2.1',
            'api_user': SIGHTENGINE_USER,
            'api_secret': SIGHTENGINE_SECRET
        }
        try:
            resp = req.get('https://api.sightengine.com/1.0/check.json', params=params, timeout=10)
            data = resp.json()
            nudity = data.get('nudity', {}).get('raw', 0)
            if nudity > 0.5:
                await msg.delete()
                await context.bot.ban_chat_member(chat_id, user_id, until_date=datetime.now()+timedelta(days=365))
                await context.bot.send_message(chat_id, f"🚫 @{user.username or user.first_name} banned (adult content).")
                return
        except:
            pass

    # Flood detection
    now = time.time()
    spam_tracker[user_id].append(now)
    message_map[user_id].append(msg.message_id)
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if now - t <= 30]
    message_map[user_id] = message_map[user_id][-len(spam_tracker[user_id]):]

    if len(spam_tracker[user_id]) >= 10:
        for mid in message_map[user_id]:
            try: await context.bot.delete_message(chat_id, mid)
            except: pass
        message_map[user_id] = []
        spam_tracker[user_id] = []

        warnings_db[chat_id][user_id] += 1
        cnt = warnings_db[chat_id][user_id]
        if cnt >= 2:
            await ban_user(context, chat_id, user_id, duration=180, reason="spam")
            warnings_db[chat_id][user_id] = 0
        else:
            await send_warning(context, chat_id, user_id, user.first_name, cnt, "spam")

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        official_links = get_official_bot_links()
        link_text = "\n".join(f"👉 {link}" for link in official_links)
        if not link_text:
            link_text = "No official games yet."
        text = (
            f"👋 <b>Welcome, {member.mention_html()}!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎰 <b>Play our official crypto games:</b>\n"
            f"{link_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ No GC links / bot links\n"
            f"🚫 No spamming\n"
            f"🔞 No adult content"
        )
        await update.message.reply_html(text)

# ========== DM HANDLER (Owner Only) ==========
async def dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or update.effective_chat.type != "private":
        return
    if user.id != OWNER_ID:
        await msg.reply_text("You are not authorized.")
        return

    text = msg.text.strip()
    if user.id not in authenticated_users:
        if text == DM_PASSWORD:
            authenticated_users.add(user.id)
            await msg.reply_text(
                "✅ Authenticated.\n"
                "📋 Commands:\n"
                "/add - Add a new bot\n"
                "/list - List all bots\n"
                "/delete <index> - Remove a bot"
            )
        else:
            await msg.reply_text("Incorrect password.")
        return

    if text.startswith("/add"):
        await msg.reply_text("Send bot name:")
        context.user_data["add_step"] = "name"
    elif "add_step" in context.user_data:
        step = context.user_data["add_step"]
        if step == "name":
            context.user_data["new_bot"] = {"name": text}
            context.user_data["add_step"] = "username"
            await msg.reply_text("Send bot username (without @):")
        elif step == "username":
            context.user_data["new_bot"]["username"] = text
            context.user_data["add_step"] = "link"
            await msg.reply_text("Send bot link (e.g., https://t.me/YourBot):")
        elif step == "link":
            context.user_data["new_bot"]["link"] = text
            context.user_data["add_step"] = "currency"
            await msg.reply_text("Send currency (e.g., USDT, INR, BNB):")
        elif step == "currency":
            context.user_data["new_bot"]["currency"] = text
            bot = context.user_data["new_bot"]
            add_bot_to_config(bot["name"], bot["username"], bot["link"], bot["currency"])
            await msg.reply_text("✅ Bot added successfully!")
            context.user_data.pop("add_step", None)
            context.user_data.pop("new_bot", None)
    elif text.startswith("/list"):
        bots = list_bots()
        if not bots:
            await msg.reply_text("No bots added yet.")
        else:
            resp = "📋 <b>Official Bots:</b>\n"
            for i, bot in enumerate(bots):
                resp += f"{i+1}. {bot['name']} (@{bot['username']}) - {bot['currency']}\n"
            await msg.reply_html(resp)
    elif text.startswith("/delete"):
        try:
            idx = int(text.split()[1]) - 1
            if delete_bot_by_index(idx):
                await msg.reply_text("✅ Bot deleted.")
            else:
                await msg.reply_text("Invalid index.")
        except:
            await msg.reply_text("Usage: /delete <index>")
    else:
        await msg.reply_text("Unknown command. Use /add, /list, /delete.")

# ========== FLASK APP ==========
app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUP, handle_message))
application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, dm_handler))

initialized = False

@app.route("/api", methods=["POST"])
def webhook():
    global initialized
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    data = request.get_json()
    if data:
        if not initialized:
            loop.run_until_complete(application.initialize())
            initialized = True
        update = Update.de_json(data, application.bot)
        loop.run_until_complete(application.process_update(update))
    return jsonify({"ok": True})

def handler(request):
    return app(request.environ, start_response)
