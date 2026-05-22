import os, json, random, requests as req, asyncio, traceback
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "")
UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"]
UPSTASH_TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]

# ---------- KV Helpers (unchanged) ----------
def kv_get(key):
    url = f"{UPSTASH_URL}/get/{key}"
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    resp = req.get(url, headers=headers, timeout=5)
    if resp.status_code != 200:
        raise Exception(f"KV GET failed: {resp.status_code} {resp.text}")
    return resp.json().get("result")

def kv_set(key, value):
    url = f"{UPSTASH_URL}/set/{key}"
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    resp = req.post(url, headers=headers, data=value, timeout=5)
    if resp.status_code != 200:
        raise Exception(f"KV SET failed: {resp.status_code} {resp.text}")

def kv_delete(key):
    url = f"{UPSTASH_URL}/del/{key}"
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    req.get(url, headers=headers, timeout=5)

# ---------- Bot Config (unchanged) ----------
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

# ---------- GROUP (unchanged) ----------
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        bots = get_official_bots()
        if not bots:
            text = ("👋 <b>Welcome, {}</b>!\n━━━━━━━━━━━━━━━━━━━━\n🎰 <b>PLAY OUR RK OFFICIAL GAMES</b>\nNo official games yet.\n━━━━━━━━━━━━━━━━━━━━").format(member.mention_html())
        else:
            lines = []
            for bot in bots:
                lines.append(f"👉 <b>{bot['name']}</b> (@{bot['username']}) — ONLY {bot['currency']} IS SUPPORTED  <a href='{bot['link']}'>Play</a>")
            text = ("👋 <b>Welcome, {}</b>!\n━━━━━━━━━━━━━━━━━━━━\n🎰 <b>PLAY OUR RK OFFICIAL GAMES</b>\n{}\n━━━━━━━━━━━━━━━━━━━━").format(member.mention_html(), "\n".join(lines))
        await update.message.reply_html(text)

# ---------- Sent Messages Storage (unchanged) ----------
SENT_MSGS_KEY = f"sent_msgs:{GROUP_CHAT_ID}" if GROUP_CHAT_ID else "sent_msgs:default"

def add_sent_record(msg_type, msg_id, snippet=""):
    try:
        data = kv_get(SENT_MSGS_KEY)
        records = json.loads(data) if data else []
    except:
        records = []
    records.append({
        "msg_id": msg_id,
        "type": msg_type,
        "timestamp": datetime.utcnow().isoformat(),
        "snippet": snippet[:100]
    })
    kv_set(SENT_MSGS_KEY, json.dumps(records))

def get_sent_records(msg_type=None):
    try:
        data = kv_get(SENT_MSGS_KEY)
        records = json.loads(data) if data else []
    except:
        records = []
    if msg_type:
        records = [r for r in records if r["type"] == msg_type]
    return records

def remove_sent_record(msg_id):
    records = get_sent_records()
    records = [r for r in records if r["msg_id"] != msg_id]
    kv_set(SENT_MSGS_KEY, json.dumps(records))

# ---------- DM (modified transfer handling) ----------
DM_PASSWORD = "RISHAVBHAGWANHAI"
authenticated_users = set()

async def dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.effective_message
        user = update.effective_user
        if not msg or not user or update.effective_chat.type != "private":
            return
        if user.id != OWNER_ID:
            await msg.reply_text("You are not authorized.")
            return

        # ── Determine message type ──
        is_text = bool(msg.text) or bool(msg.caption)
        is_photo = len(msg.photo) > 0 if msg.photo else False
        is_video = bool(msg.video)
        is_any_media = msg.photo or msg.video or msg.animation or msg.document or msg.sticker or msg.voice or msg.audio

        # Extract text (caption if media with caption, else normal text)
        if is_video and msg.caption:
            text = msg.caption.strip()
        elif is_photo and msg.caption:
            text = msg.caption.strip()
        elif is_text:
            text = msg.text.strip() if msg.text else ""
        else:
            text = ""

        # ─────────────────────────────────────────────────
        # 🔥 COMMANDS FIRST
        # ─────────────────────────────────────────────────
        if is_text:
            if text == "/debug":
                # ... (unchanged) ...
                return
            if text == "/reset":
                # ... (unchanged) ...
                return
            if text == "/cancel":
                # ... (unchanged) ...
                return

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
                        "/memberknock - Remove a member (or any bot)\n"
                        "/membergrow - Add a member (or any bot) to the group\n"
                        "/image - Send a photo to the group\n"
                        "/video - Send a video to the group\n"
                        "/dltmvp - Delete a message/photo/video sent by bot\n"
                        "/reset - Clear authentication\n"
                        "/debug - Test KV connection\n"
                        "/cancel - Cancel any session"
                    )
                else:
                    await msg.reply_text("Incorrect password.")
                return

            # ========== Other commands ==========
            if text.startswith("/list"):
                # ... (unchanged) ...
                return
            if text.startswith("/delete"):
                # ... (unchanged) ...
                return
            if text.startswith("/add"):
                # ... (unchanged) ...
                return
            if text.startswith("/transfer"):
                kv_set(f"transfer_state:{user.id}", "waiting")
                await msg.reply_text("✉️ Please send the message (any type) you want to forward to the group.")
                return
            if text.startswith("/memberknock"):
                # ... (unchanged) ...
                return
            if text.startswith("/membergrow"):
                # ... (unchanged) ...
                return
            if text.startswith("/image"):
                # ... (unchanged) ...
                return
            if text.startswith("/video"):
                # ... (unchanged) ...
                return
            if text.startswith("/dltmvp"):
                # ... (unchanged) ...
                return

        # ─────────────────────────────────────────────────
        # SESSION INPUT HANDLING (transfer improved)
        # ─────────────────────────────────────────────────

        # ── TRANSFER SESSION (handles ALL message types) ──
        transfer_state = kv_get(f"transfer_state:{user.id}")
        if transfer_state:
            kv_delete(f"transfer_state:{user.id}")
            if not GROUP_CHAT_ID:
                await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
                return
            try:
                # Copy the exact message to the group (works for text, photo, video, etc.)
                sent_msg = await context.bot.copy_message(
                    chat_id=GROUP_CHAT_ID,
                    from_chat_id=msg.chat_id,
                    message_id=msg.message_id
                )
                # Determine type for sent record
                if msg.text and not msg.caption:
                    msg_type = "text"
                elif msg.photo:
                    msg_type = "photo"
                elif msg.video:
                    msg_type = "video"
                elif msg.animation:
                    msg_type = "animation"
                elif msg.document:
                    msg_type = "document"
                elif msg.sticker:
                    msg_type = "sticker"
                else:
                    msg_type = "other"
                add_sent_record(msg_type, sent_msg.message_id, text[:100] if text else str(msg_type))
                await msg.reply_text("✅ Message sent to the group.")
            except Exception as e:
                await msg.reply_text(f"❌ Failed to send message: {str(e)}")
            return

        # ── IMAGE SESSION (unchanged) ──
        image_state = kv_get(f"image_state:{user.id}")
        if image_state:
            # ... (unchanged) ...
            return

        # ── VIDEO SESSION (unchanged) ──
        video_state = kv_get(f"video_state:{user.id}")
        if video_state:
            # ... (unchanged) ...
            return

        # ── DLTMVP SESSION (unchanged) ──
        dlt_state = kv_get(f"dltmvp_state:{user.id}")
        if dlt_state:
            # ... (unchanged) ...
            return

        # ── KNOCK / GROW / ADD sessions (unchanged) ──
        knock_state = kv_get(f"knock_state:{user.id}")
        if knock_state and is_text:
            # ... (unchanged) ...
            return

        grow_state = kv_get(f"grow_state:{user.id}")
        if grow_state and is_text:
            # ... (unchanged) ...
            return

        add_state_json = kv_get(f"add_state:{user.id}")
        if add_state_json and is_text:
            # ... (unchanged) ...
            return

        if is_text:
            await msg.reply_text("Unknown command. Use /add, /list, /delete, /transfer, /memberknock, /membergrow, /image, /video, /dltmvp, /reset, /debug, /cancel.")
    except Exception as e:
        traceback.print_exc()
        try:
            await update.effective_message.reply_text(f"❌ Internal error: {str(e)}")
        except:
            pass

# ---------- CALLBACKS (unchanged) ----------
async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (unchanged) ...

async def knock_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (unchanged) ...

async def grow_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (unchanged) ...

# ---------- FLASK ----------
app = Flask(__name__)

@app.route("/api", methods=["POST"])
def webhook():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        data = request.get_json()
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO) & filters.ChatType.PRIVATE,
            dm_handler
        ))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
        application.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del_"))
        application.add_handler(CallbackQueryHandler(knock_confirm_callback, pattern=r"^knock_confirm_"))
        application.add_handler(CallbackQueryHandler(grow_confirm_callback, pattern=r"^grow_confirm_"))
        loop.run_until_complete(application.initialize())
        update = Update.de_json(data, application.bot)
        loop.run_until_complete(application.process_update(update))
        loop.run_until_complete(application.shutdown())
        return jsonify({"ok": True})
    finally:
        loop.close()

# Vercel entry point (fixed)
from werkzeug.wsgi import DispatcherMiddleware
from werkzeug.serving import run_simple  # just for local testing if needed

def handler(request, context):
    """Vercel serverless function entry point."""
    return app(request.environ, start_response)
