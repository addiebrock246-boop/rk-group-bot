import os, json, random, requests as req
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import asyncio

BOT_TOKEN = "8808046020:AAEjfprJIKHe7y5TZJckjL22b2yXyM4gKfQ"
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "")
KV_REST_API_URL = os.environ.get("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.environ.get("KV_REST_API_TOKEN", "")

# ---------- KV Helpers ----------
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

# ---------- Bot Config ----------
def get_official_bot_links():
    data = kv_get("official_bots")
    if data:
        bots = json.loads(data)
        return [b['link'] for b in bots]
    return []

async def add_bot_to_config(name, username, link, currency):
    bots = []
    data = kv_get("official_bots")
    if data:
        bots = json.loads(data)
    bots.append({"name": name, "username": username, "link": link, "currency": currency})
    kv_set("official_bots", json.dumps(bots))

async def delete_bot_by_index(index):
    data = kv_get("official_bots")
    if data:
        bots = json.loads(data)
        if 0 <= index < len(bots):
            del bots[index]
            kv_set("official_bots", json.dumps(bots))
            return True
    return False

async def list_bots():
    data = kv_get("official_bots")
    if data:
        return json.loads(data)
    return []

# ---------- GROUP HANDLERS ----------
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
            f"ℹ️ Only admins can send messages here."
        )
        await update.message.reply_html(text)

# ---------- DM HANDLER (Owner Only) ----------
DM_PASSWORD = "RISHAVBHAGWANHAI"
authenticated_users = set()

async def dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or update.effective_chat.type != "private":
        return
    if user.id != OWNER_ID:
        await msg.reply_text("You are not authorized.")
        return

    text = msg.text.strip()

    # /reset command – clear auth
    if text == "/reset":
        if user.id in authenticated_users:
            authenticated_users.discard(user.id)
        await msg.reply_text("🔒 Authentication reset. Send password to continue.")
        return

    # Check password if not authenticated
    if user.id not in authenticated_users:
        if text == DM_PASSWORD:
            authenticated_users.add(user.id)
            await msg.reply_text(
                "✅ Authenticated.\n"
                "📋 Commands:\n"
                "/add - Add a new bot\n"
                "/list - List all bots\n"
                "/delete <index> - Remove a bot\n"
                "/reset - Clear authentication"
            )
        else:
            await msg.reply_text("Incorrect password.")
        return

    # Already authenticated
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
            await add_bot_to_config(bot["name"], bot["username"], bot["link"], bot["currency"])
            await msg.reply_text("✅ Bot added successfully!")
            context.user_data.pop("add_step", None)
            context.user_data.pop("new_bot", None)
    elif text.startswith("/list"):
        bots = await list_bots()
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
            if await delete_bot_by_index(idx):
                await msg.reply_text("✅ Bot deleted.")
            else:
                await msg.reply_text("Invalid index.")
        except:
            await msg.reply_text("Usage: /delete <index>")
    else:
        await msg.reply_text("Unknown command. Use /add, /list, /delete, /reset.")

# ---------- FLASK ----------
app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
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
