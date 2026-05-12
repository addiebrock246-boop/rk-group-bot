import re, time, asyncio, os, json
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, request, jsonify
from telegram import Update, ChatPermissions
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ========== TERA BOT TOKEN (READY) ==========
BOT_TOKEN = "8808046020:AAEjfprJIKHe7y5TZJckjL22b2yXyM4gKfQ"

# In‑memory warnings (reset on redeploy, but bans stay on Telegram)
warnings_db = defaultdict(lambda: defaultdict(int))
spam_tracker = defaultdict(list)
message_map = defaultdict(list)

# GC invite link regex
INVITE_LINK_REGEX = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/|\+)?[\w\-]+",
    re.IGNORECASE
)

# ========== HANDLERS ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or chat.type == "private":
        return

    user_id = user.id
    chat_id = chat.id
    text = msg.text or msg.caption or ""

    # ---------- GC LINK DETECTION ----------
    if INVITE_LINK_REGEX.search(text):
        try: await msg.delete()
        except: pass
        warnings_db[chat_id][user_id] += 1
        cnt = warnings_db[chat_id][user_id]

        if cnt >= 2:
            until = datetime.now() + timedelta(days=180)
            try:
                await context.bot.ban_chat_member(chat_id, user_id, until_date=until)
                await context.bot.send_message(chat_id, f"🚫 @{user.username or user.first_name} banned 6 months (GC links).")
            except Exception as e:
                print(f"Ban error: {e}")
            warnings_db[chat_id][user_id] = 0
        else:
            try:
                sent = await context.bot.send_message(
                    chat_id, f"⚠️ @{user.username or user.first_name} GC links not allowed! Warning {cnt}/2. Next = 6‑month ban."
                )
                await asyncio.sleep(10)
                await sent.delete()
            except: pass
        return

    # ---------- SPAM DETECTION ----------
    now = time.time()
    spam_tracker[user_id].append(now)
    message_map[user_id].append(msg.message_id)

    # keep last 30 seconds
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if now - t <= 30]
    message_map[user_id] = message_map[user_id][-len(spam_tracker[user_id]):]

    if len(spam_tracker[user_id]) >= 10:
        # delete all spam
        for mid in message_map[user_id]:
            try: await context.bot.delete_message(chat_id, mid)
            except: pass
        message_map[user_id] = []
        spam_tracker[user_id] = []

        warnings_db[chat_id][user_id] += 1
        cnt = warnings_db[chat_id][user_id]

        if cnt >= 2:
            until = datetime.now() + timedelta(days=180)
            try:
                await context.bot.ban_chat_member(chat_id, user_id, until_date=until)
                await context.bot.send_message(chat_id, f"🚫 @{user.username or user.first_name} banned 6 months (spam).")
            except: pass
            warnings_db[chat_id][user_id] = 0
        else:
            try:
                sent = await context.bot.send_message(
                    chat_id, f"⚠️ @{user.username or user.first_name} stop spamming! Warning {cnt}/2."
                )
                await asyncio.sleep(10)
                await sent.delete()
            except: pass

# ---------- WELCOME ----------
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        text = (
            f"👋 Welcome, {member.mention_html()}!\n"
            "Please follow rules:\n"
            "❌ No group invite links\n"
            "🚫 No spamming (10+ msgs in 30s)\n"
            "Violators get 2 warnings then 6‑month ban."
        )
        await update.message.reply_html(text)

# ========== FLASK + APPLICATION ==========
app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUP, handle_message))

initialized = False

@app.route("/api", methods=["POST"])
async def webhook():
    global initialized
    if not initialized:
        await application.initialize()
        initialized = True
    data = request.get_json()
    if data:
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    return jsonify({"ok": True})

# Vercel handler
def handler(request):
    return app(request.environ, start_response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
