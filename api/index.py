import os, json, random, requests as req, asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = "8808046020:AAEjfprJIKHe7y5TZJckjL22b2yXyM4gKfQ"
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "")
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "https://welcomed-flounder-86019.upstash.io")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "gQAAAAAAAVADAAIgcDE3ZmI1NTk4N2VmMTM0ZTExOWJiNDk5NTNmNjRkMWM1Yg")

# ---------- KV Helpers ----------
def kv_get(key):
    if not UPSTASH_URL:
        raise Exception("UPSTASH_REDIS_REST_URL not set")
    url = f"{UPSTASH_URL}/get/{key}"
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    resp = req.get(url, headers=headers, timeout=5)
    if resp.status_code != 200:
        raise Exception(f"KV GET failed: {resp.status_code} {resp.text}")
    return resp.json().get("result")

def kv_set(key, value):
    if not UPSTASH_URL:
        raise Exception("UPSTASH_REDIS_REST_URL not set")
    url = f"{UPSTASH_URL}/set/{key}"
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    resp = req.post(url, headers=headers, data=value, timeout=5)
    if resp.status_code != 200:
        raise Exception(f"KV SET failed: {resp.status_code} {resp.text}")

def kv_delete(key):
    if not UPSTASH_URL:
        return
    url = f"{UPSTASH_URL}/del/{key}"
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    req.get(url, headers=headers, timeout=5)

# ---------- Bot Config ----------
def get_official_bots():
    try:
        data = kv_get("official_bots")
        if data:
            return json.loads(data)
    except:
        pass
    return []

async def add_bot_to_config(name, username, link, currency):
    bots = get_official_bots()
    bots.append({"name": name, "username": username, "link": link, "currency": currency})
    kv_set("official_bots", json.dumps(bots))

async def delete_bot_by_index(index):
    bots = get_official_bots()
    if 0 <= index < len(bots):
        del bots[index]
        kv_set("official_bots", json.dumps(bots))
        return True
    return False

# ---------- GROUP HANDLERS ----------
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        bots = get_official_bots()
        if not bots:
            text = (
                "👋 <b>Welcome, {}</b>!\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🎰 <b>PLAY OUR RK OFFICIAL GAMES</b>\n"
                "No official games yet.\n"
                "━━━━━━━━━━━━━━━━━━━━"
            ).format(member.mention_html())
        else:
            lines = []
            for bot in bots:
                line = f"👉 <b>{bot['name']}</b> (@{bot['username']}) — ONLY {bot['currency']} IS SUPPORTED  <a href='{bot['link']}'>Play</a>"
                lines.append(line)
            text = (
                "👋 <b>Welcome, {}</b>!\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🎰 <b>PLAY OUR RK OFFICIAL GAMES</b>\n"
                "{}\n"
                "━━━━━━━━━━━━━━━━━━━━"
            ).format(member.mention_html(), "\n".join(lines))
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

    # ========== SPECIAL COMMANDS (Work even if session active) ==========
    if text == "/debug":
        await msg.reply_text("Testing KV...")
        try:
            kv_set("test_key", "test_value")
            val = kv_get("test_key")
            if val == "test_value":
                await msg.reply_text("✅ KV is working perfectly!")
            else:
                await msg.reply_text(f"⚠️ KV GET returned unexpected: {val}")
        except Exception as e:
            await msg.reply_text(f"❌ KV Error: {str(e)}")
        return

    if text == "/reset":
        authenticated_users.discard(user.id)
        for key in [f"add_state:{user.id}", f"transfer_state:{user.id}", f"knock_state:{user.id}"]:
            kv_delete(key)
        await msg.reply_text("🔒 Authentication reset. Send password to continue.")
        return

    # Password check if not authenticated
    if user.id not in authenticated_users:
        if text == DM_PASSWORD:
            authenticated_users.add(user.id)
            await msg.reply_text(
                "✅ Authenticated.\n"
                "📋 Commands:\n"
                "/add - Add a new bot (multi‑step)\n"
                "/list - List all bots\n"
                "/delete - Delete bots (inline buttons)\n"
                "/transfer - Send a message to the group\n"
                "/memberknock - Remove a member from the group\n"
                "/reset - Clear authentication\n"
                "/debug - Test KV connection\n"
                "/cancel - Cancel current add/transfer/knock session"
            )
        else:
            await msg.reply_text("Incorrect password.")
        return

    # ========== CANCEL SESSION ==========
    if text == "/cancel":
        any_cancelled = False
        for key in [f"add_state:{user.id}", f"transfer_state:{user.id}", f"knock_state:{user.id}"]:
            if kv_get(key):
                kv_delete(key)
                any_cancelled = True
        if any_cancelled:
            await msg.reply_text("🚫 Active session cancelled.")
        else:
            await msg.reply_text("No active session to cancel.")
        return

    # ========== LIST & DELETE COMMANDS ==========
    if text.startswith("/list"):
        bots = get_official_bots()
        if not bots:
            await msg.reply_text("No bots added yet.")
        else:
            resp = "📋 <b>Official Bots:</b>\n"
            for i, bot in enumerate(bots):
                resp += f"{i+1}. {bot['name']} (@{bot['username']}) - {bot['currency']}\n"
            await msg.reply_html(resp)
        return

    if text.startswith("/delete"):
        bots = get_official_bots()
        if not bots:
            await msg.reply_text("No bots to delete.")
            return
        keyboard = []
        for i, bot in enumerate(bots):
            keyboard.append([InlineKeyboardButton(f"{bot['name']} (@{bot['username']})", callback_data=f"del_{i}")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await msg.reply_text("Select a bot to delete:", reply_markup=reply_markup)
        return

    # ========== START NEW SESSION COMMANDS ==========
    if text.startswith("/add"):
        state = {"step": "name", "data": {}}
        kv_set(f"add_state:{user.id}", json.dumps(state))
        await msg.reply_text("Send bot name:")
        return

    if text.startswith("/transfer"):
        kv_set(f"transfer_state:{user.id}", "waiting")
        await msg.reply_text("✉️ Please send the message you want to forward to the group.")
        return

    if text.startswith("/memberknock"):
        kv_set(f"knock_state:{user.id}", "waiting")
        await msg.reply_text("🔨 Send the user ID or @username of the member to remove from the group.")
        return

    # ========== ACTIVE SESSION INPUT HANDLING ==========
    # Knock session
    knock_state = kv_get(f"knock_state:{user.id}")
    if knock_state:
        target = text
        kv_delete(f"knock_state:{user.id}")
        if not GROUP_CHAT_ID:
            await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
            return
        try:
            if target.startswith("@"):
                target_username = target[1:]
                member = await context.bot.get_chat_member(GROUP_CHAT_ID, "@" + target_username)
                target_id = member.user.id
            else:
                target_id = int(target)
            # Kick (ban + unban)
            await context.bot.ban_chat_member(GROUP_CHAT_ID, target_id)
            await context.bot.unban_chat_member(GROUP_CHAT_ID, target_id)
            await msg.reply_text(f"✅ Member {target} has been removed from the group.")
        except Exception as e:
            await msg.reply_text(f"❌ Failed to remove member: {str(e)}")
        return

    # Transfer session
    transfer_state = kv_get(f"transfer_state:{user.id}")
    if transfer_state:
        kv_delete(f"transfer_state:{user.id}")
        if GROUP_CHAT_ID:
            try:
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
                await msg.reply_text("✅ Message sent to the group.")
            except Exception as e:
                await msg.reply_text(f"❌ Failed to send message: {str(e)}")
        else:
            await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
        return

    # Add session (multi‑step)
    add_state_json = kv_get(f"add_state:{user.id}")
    if add_state_json:
        try:
            state = json.loads(add_state_json)
        except:
            await msg.reply_text("❌ Corrupted add session. Use /cancel and start again.")
            kv_delete(f"add_state:{user.id}")
            return
        step = state.get("step")
        data = state.get("data", {})
        if step == "name":
            data["name"] = text
            state["step"] = "username"
            kv_set(f"add_state:{user.id}", json.dumps(state))
            await msg.reply_text("Send bot username (without @):")
        elif step == "username":
            data["username"] = text
            state["step"] = "link"
            kv_set(f"add_state:{user.id}", json.dumps(state))
            await msg.reply_text("Send bot link (e.g., https://t.me/YourBot):")
        elif step == "link":
            data["link"] = text
            state["step"] = "currency"
            kv_set(f"add_state:{user.id}", json.dumps(state))
            await msg.reply_text("Send currency (e.g., USDT, INR, BNB):")
        elif step == "currency":
            data["currency"] = text
            try:
                await add_bot_to_config(data["name"], data["username"], data["link"], data["currency"])
                await msg.reply_text("✅ Bot added successfully!")
            except Exception as e:
                await msg.reply_text(f"❌ Failed to save bot: {str(e)}")
            kv_delete(f"add_state:{user.id}")
        return

    # If no session and no command matched
    await msg.reply_text("Unknown command. Use /add, /list, /delete, /transfer, /memberknock, /reset, /debug, /cancel.")

# ---------- CALLBACK QUERY HANDLER ----------
async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if data == "del_cancel":
        await context.bot.edit_message_text("Delete cancelled.", chat_id=chat_id, message_id=message_id)
        return

    try:
        idx = int(data.split("_")[1])
    except:
        await context.bot.edit_message_text("Invalid selection.", chat_id=chat_id, message_id=message_id)
        return

    try:
        if await delete_bot_by_index(idx):
            await context.bot.edit_message_text("✅ Bot deleted successfully.", chat_id=chat_id, message_id=message_id)
        else:
            await context.bot.edit_message_text("❌ Invalid index.", chat_id=chat_id, message_id=message_id)
    except Exception as e:
        await context.bot.edit_message_text(f"Error: {str(e)}", chat_id=chat_id, message_id=message_id)

# ---------- FLASK ----------
app = Flask(__name__)

@app.route("/api", methods=["POST"])
def webhook():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        data = request.get_json()
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
        application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, dm_handler))
        application.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del_"))
        loop.run_until_complete(application.initialize())
        update = Update.de_json(data, application.bot)
        loop.run_until_complete(application.process_update(update))
        loop.run_until_complete(application.shutdown())
        return jsonify({"ok": True})
    finally:
        loop.close()

def handler(request):
    return app(request.environ, start_response)
