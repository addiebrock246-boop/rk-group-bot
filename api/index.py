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

# ---------- KV Helpers ----------
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

# ---------- GROUP ----------
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

# ---------- Sent Messages Storage ----------
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

# ---------- DM ----------
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
        # 🔥 COMMANDS FIRST (so /cancel, /reset always work)
        # ─────────────────────────────────────────────────
        if is_text:
            if text == "/debug":
                await msg.reply_text("Testing KV...")
                try:
                    kv_set("test_key", "test_value")
                    val = kv_get("test_key")
                    if val == "test_value":
                        await msg.reply_text("✅ KV is working perfectly!")
                    else:
                        await msg.reply_text(f"⚠️ KV GET unexpected: {val}")
                except Exception as e:
                    await msg.reply_text(f"❌ KV Error: {str(e)}")
                return

            if text == "/reset":
                authenticated_users.discard(user.id)
                session_keys = [
                    f"add_state:{user.id}", f"transfer_state:{user.id}",
                    f"knock_state:{user.id}", f"grow_state:{user.id}",
                    f"image_state:{user.id}", f"video_state:{user.id}",
                    f"dltmvp_state:{user.id}"
                ]
                for key in session_keys:
                    kv_delete(key)
                await msg.reply_text("🔒 Authentication reset. All active sessions cancelled.\nSend password to continue.")
                return

            if text == "/cancel":
                any_cancelled = False
                session_keys = [
                    f"add_state:{user.id}", f"transfer_state:{user.id}",
                    f"knock_state:{user.id}", f"grow_state:{user.id}",
                    f"image_state:{user.id}", f"video_state:{user.id}",
                    f"dltmvp_state:{user.id}"
                ]
                for key in session_keys:
                    if kv_get(key):
                        kv_delete(key)
                        any_cancelled = True
                if any_cancelled:
                    await msg.reply_text("🚫 Active session cancelled.")
                else:
                    await msg.reply_text("No active session to cancel.")
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
                await msg.reply_text("Select a bot to delete:", reply_markup=InlineKeyboardMarkup(keyboard))
                return

            if text.startswith("/add"):
                kv_set(f"add_state:{user.id}", json.dumps({"step":"name","data":{}}))
                await msg.reply_text("Send bot name:")
                return

            if text.startswith("/transfer"):
                kv_set(f"transfer_state:{user.id}", "waiting")
                await msg.reply_text("✉️ Please send the message you want to forward to the group.")
                return

            if text.startswith("/memberknock"):
                kv_set(f"knock_state:{user.id}", "waiting")
                await msg.reply_text(
                    "🔨 Send the @username, numeric ID, or <b>forward any message</b> from the user/bot you want to remove.\n"
                    "✨ If you send a @username, I'll show you the numeric ID and a <b>Remove</b> button.\n"
                    "💡 If I can't find the username, simply <b>forward a message</b> from that person – it always works!",
                    parse_mode="HTML"
                )
                return

            if text.startswith("/membergrow"):
                kv_set(f"grow_state:{user.id}", "waiting")
                await msg.reply_text(
                    "🌱 Send the @username or numeric ID of the user/bot you want to <b>add</b> to the group.\n"
                    "⚠️ The user must have a public username (or you know their numeric ID).\n"
                    "✨ If I can't add directly (e.g., privacy settings), I'll send you an invite link automatically.",
                    parse_mode="HTML"
                )
                return

            if text.startswith("/image"):
                kv_set(f"image_state:{user.id}", "waiting")
                await msg.reply_text("🖼️ Send me the photo you want to post in the group.")
                return

            if text.startswith("/video"):
                kv_set(f"video_state:{user.id}", "waiting")
                await msg.reply_text("🎥 Send me the video you want to post in the group.")
                return

            if text.startswith("/dltmvp"):
                kv_set(f"dltmvp_state:{user.id}", json.dumps({"step":"choose_type"}))
                await msg.reply_text("🗑️ <b>What do you want to delete?</b>\nReply with <b>photo</b>, <b>video</b> or <b>text</b>.", parse_mode="HTML")
                return

        # ─────────────────────────────────────────────────
        # SESSION INPUT HANDLING (only if no command matched)
        # ─────────────────────────────────────────────────

        # ── IMAGE SESSION ──
        image_state = kv_get(f"image_state:{user.id}")
        if image_state:
            if is_photo:
                kv_delete(f"image_state:{user.id}")
                if not GROUP_CHAT_ID:
                    await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
                    return
                file_id = msg.photo[-1].file_id
                try:
                    sent_msg = await context.bot.send_photo(chat_id=GROUP_CHAT_ID, photo=file_id)
                    add_sent_record("photo", sent_msg.message_id, msg.caption or "Photo")
                    await msg.reply_text("✅ Photo sent to the group.")
                except Exception as e:
                    await msg.reply_text(f"❌ Failed to send photo: {str(e)}")
            else:
                await msg.reply_text("📷 Please send a photo now (not text/video). Send /cancel to abort.")
            return

        # ── VIDEO SESSION ──
        video_state = kv_get(f"video_state:{user.id}")
        if video_state:
            if is_video:
                kv_delete(f"video_state:{user.id}")
                if not GROUP_CHAT_ID:
                    await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
                    return
                file_id = msg.video.file_id
                try:
                    sent_msg = await context.bot.send_video(chat_id=GROUP_CHAT_ID, video=file_id)
                    add_sent_record("video", sent_msg.message_id, msg.caption or "Video")
                    await msg.reply_text("✅ Video sent to the group.")
                except Exception as e:
                    await msg.reply_text(f"❌ Failed to send video: {str(e)}")
            else:
                await msg.reply_text("🎥 Please send a video now (not photo/text). Send /cancel to abort.")
            return

        # ── DLTMVP SESSION ──
        dlt_state = kv_get(f"dltmvp_state:{user.id}")
        if dlt_state:
            try:
                state_data = json.loads(dlt_state)
            except:
                state_data = {"step": "choose_type"}

            if state_data["step"] == "choose_type":
                choice = text.lower().strip()
                if choice in ("photo", "video", "text"):
                    records = get_sent_records(msg_type=choice)
                    if not records:
                        await msg.reply_text(f"❌ No {choice} messages found.")
                        kv_delete(f"dltmvp_state:{user.id}")
                        return
                    lines = [f"📋 <b>{choice.capitalize()} messages:</b>\n"]
                    for i, rec in enumerate(records, 1):
                        tstamp = rec["timestamp"][:19]
                        snippet = rec["snippet"] or ""
                        lines.append(f"{i}. 🆔 {rec['msg_id']} | {tstamp} | {snippet[:50]}")
                    lines.append("\n✏️ <b>Reply with the line number (or message ID)</b> to delete, or /cancel.")
                    await msg.reply_html("\n".join(lines))
                    state_data["step"] = "confirm_delete"
                    state_data["type"] = choice
                    state_data["records"] = records
                    kv_set(f"dltmvp_state:{user.id}", json.dumps(state_data))
                else:
                    await msg.reply_text("❌ Invalid choice. Please reply with <b>photo</b>, <b>video</b> or <b>text</b>.", parse_mode="HTML")
                return

            elif state_data["step"] == "confirm_delete":
                user_input = text.strip()
                records = state_data["records"]
                target_rec = None

                # Try to interpret as line number first
                try:
                    idx = int(user_input) - 1
                    if 0 <= idx < len(records):
                        target_rec = records[idx]
                except ValueError:
                    pass

                # If not a valid index, try as message ID
                if not target_rec:
                    try:
                        mid = int(user_input)
                        for rec in records:
                            if rec["msg_id"] == mid:
                                target_rec = rec
                                break
                    except ValueError:
                        pass

                if target_rec:
                    try:
                        await context.bot.delete_message(chat_id=GROUP_CHAT_ID, message_id=target_rec["msg_id"])
                        remove_sent_record(target_rec["msg_id"])
                        await msg.reply_text(f"✅ Message (ID: {target_rec['msg_id']}) deleted from group.")
                        kv_delete(f"dltmvp_state:{user.id}")
                    except Exception as e:
                        await msg.reply_text(f"❌ Failed to delete message: {str(e)}")
                else:
                    await msg.reply_text("❌ Invalid input. Please reply with a valid line number or message ID, or /cancel.")
                return

        # ── KNOCK / GROW / TRANSFER / ADD sessions ──
        knock_state = kv_get(f"knock_state:{user.id}")
        if knock_state and is_text:
            kv_delete(f"knock_state:{user.id}")
            if not GROUP_CHAT_ID:
                await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
                return
            forward_from = getattr(msg, 'forward_from', None)
            forward_from_chat = getattr(msg, 'forward_from_chat', None)
            target_id = None
            target_label = ""

            if forward_from:
                target_id = forward_from.id
                target_label = f"@{forward_from.username}" if forward_from.username else forward_from.full_name
            elif forward_from_chat:
                target_id = forward_from_chat.id
                target_label = f"@{forward_from_chat.username}" if forward_from_chat.username else forward_from_chat.title
            else:
                text_input = text.strip()
                if not text_input:
                    kv_set(f"knock_state:{user.id}", "waiting")
                    await msg.reply_text("❌ No input. Send @username, numeric ID, or forward a message.")
                    return
                if text_input.lstrip('-').isdigit():
                    try:
                        target_id = int(text_input)
                        target_label = text_input
                    except:
                        await msg.reply_text("❌ Invalid numeric ID.")
                        return
                else:
                    username = text_input if text_input.startswith('@') else '@' + text_input
                    try:
                        chat = await context.bot.get_chat(username)
                        target_id = chat.id
                        target_label = username
                    except Exception:
                        kv_set(f"knock_state:{user.id}", "waiting")
                        await msg.reply_text(
                            f"❌ I couldn't find the user '{username}'.\n"
                            "👉 Please <b>forward any message</b> from that user to me – I'll extract the ID automatically.",
                            parse_mode="HTML"
                        )
                        return

                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🗑️ Remove from group", callback_data=f"knock_confirm_{target_id}")]
                    ])
                    await msg.reply_text(
                        f"✅ Username <b>{username}</b> → Numeric ID: <code>{target_id}</code>\n\n"
                        "Click the button below to <b>remove</b> this user from the group.",
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    return

            if target_id:
                try:
                    bot_member = await context.bot.get_chat_member(GROUP_CHAT_ID, context.bot.id)
                    if bot_member.status not in ("administrator", "creator"):
                        await msg.reply_text("❌ Bot is not an admin of the group.")
                        return
                    await context.bot.ban_chat_member(GROUP_CHAT_ID, target_id)
                    await context.bot.unban_chat_member(GROUP_CHAT_ID, target_id)
                    await msg.reply_text(f"✅ {target_label} (ID: {target_id}) has been removed from the group.")
                except Exception as e:
                    await msg.reply_text(f"❌ Failed to remove member: {str(e)}")
            return

        grow_state = kv_get(f"grow_state:{user.id}")
        if grow_state and is_text:
            kv_delete(f"grow_state:{user.id}")
            if not GROUP_CHAT_ID:
                await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
                return
            forward_from = getattr(msg, 'forward_from', None)
            forward_from_chat = getattr(msg, 'forward_from_chat', None)
            target_id = None
            target_label = ""

            if forward_from:
                target_id = forward_from.id
                target_label = f"@{forward_from.username}" if forward_from.username else forward_from.full_name
            elif forward_from_chat:
                target_id = forward_from_chat.id
                target_label = f"@{forward_from_chat.username}" if forward_from_chat.username else forward_from_chat.title
            else:
                text_input = text.strip()
                if not text_input:
                    kv_set(f"grow_state:{user.id}", "waiting")
                    await msg.reply_text("❌ No input. Send @username or numeric ID.")
                    return
                if text_input.lstrip('-').isdigit():
                    try:
                        target_id = int(text_input)
                        target_label = text_input
                    except:
                        await msg.reply_text("❌ Invalid numeric ID.")
                        return
                else:
                    username = text_input if text_input.startswith('@') else '@' + text_input
                    try:
                        chat = await context.bot.get_chat(username)
                        target_id = chat.id
                        target_label = username
                    except Exception:
                        try:
                            invite_link = await context.bot.create_chat_invite_link(
                                GROUP_CHAT_ID,
                                member_limit=1,
                                creates_join_request=False
                            )
                            link = invite_link.invite_link
                            await msg.reply_text(
                                f"🔗 <b>{username}</b> ko direct add nahi kar paya.\n"
                                f"👇 Send them this invite link:\n{link}\n\n"
                                "⚠️ Link is single‑use.",
                                parse_mode="HTML"
                            )
                        except Exception as e2:
                            await msg.reply_text(f"❌ Failed to create invite link: {str(e2)}")
                        return

                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("➕ Add to group", callback_data=f"grow_confirm_{target_id}")]
                    ])
                    await msg.reply_text(
                        f"✅ Username <b>{username}</b> → Numeric ID: <code>{target_id}</code>\n\n"
                        "Click the button below to <b>add</b> this user to the group.",
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    return

            if target_id:
                try:
                    bot_member = await context.bot.get_chat_member(GROUP_CHAT_ID, context.bot.id)
                    if bot_member.status not in ("administrator", "creator"):
                        await msg.reply_text("❌ Bot is not an admin of the group.")
                        return
                    if not bot_member.can_invite_users:
                        await msg.reply_text("❌ Bot does not have 'Add users' permission.")
                        return

                    resp = req.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/addChatMember",
                        json={"chat_id": int(GROUP_CHAT_ID), "user_id": target_id},
                        timeout=10
                    )
                    data = resp.json()
                    if resp.status_code == 200 and data.get("ok"):
                        await msg.reply_text(f"✅ {target_label} (ID: {target_id}) has been <b>added</b> to the group.", parse_mode="HTML")
                    else:
                        error_msg = data.get("description", resp.text)
                        if "Not Found" in error_msg or "USER_PRIVACY_RESTRICTED" in error_msg:
                            try:
                                invite_link = await context.bot.create_chat_invite_link(
                                    GROUP_CHAT_ID,
                                    member_limit=1,
                                    creates_join_request=False
                                )
                                link = invite_link.invite_link
                                await msg.reply_text(
                                    f"⚠️ Could not add user directly.\n"
                                    f"👉 Send them this invite link:\n{link}\n"
                                    f"The link expires after first use."
                                )
                            except Exception as e2:
                                await msg.reply_text(f"❌ Could not add user and also failed to create invite link: {str(e2)}")
                        else:
                            await msg.reply_text(f"❌ Failed to add member: {error_msg}")
                except Exception as e:
                    await msg.reply_text(f"❌ Failed to add member: {str(e)}")
            return

        transfer_state = kv_get(f"transfer_state:{user.id}")
        if transfer_state and is_text:
            kv_delete(f"transfer_state:{user.id}")
            if GROUP_CHAT_ID:
                try:
                    sent_msg = await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
                    add_sent_record("text", sent_msg.message_id, text[:100])
                    await msg.reply_text("✅ Message sent to the group.")
                except Exception as e:
                    await msg.reply_text(f"❌ Failed to send message: {str(e)}")
            else:
                await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
            return

        add_state_json = kv_get(f"add_state:{user.id}")
        if add_state_json and is_text:
            try:
                state = json.loads(add_state_json)
            except:
                await msg.reply_text("❌ Corrupted session. /cancel and start again.")
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

        if is_text:
            await msg.reply_text("Unknown command. Use /add, /list, /delete, /transfer, /memberknock, /membergrow, /image, /video, /dltmvp, /reset, /debug, /cancel.")
    except Exception as e:
        traceback.print_exc()
        try:
            await update.effective_message.reply_text(f"❌ Internal error: {str(e)}")
        except:
            pass

# ---------- CALLBACKS ----------
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

async def knock_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    parts = data.split("_")
    if len(parts) >= 3:
        try:
            target_id = int(parts[2])
        except ValueError:
            await context.bot.edit_message_text("❌ Invalid user ID.", chat_id=chat_id, message_id=message_id)
            return
    else:
        await context.bot.edit_message_text("❌ Invalid callback.", chat_id=chat_id, message_id=message_id)
        return
    if not GROUP_CHAT_ID:
        await context.bot.edit_message_text("❌ GROUP_CHAT_ID is not set.", chat_id=chat_id, message_id=message_id)
        return
    try:
        bot_member = await context.bot.get_chat_member(GROUP_CHAT_ID, context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            await context.bot.edit_message_text("❌ Bot is not an admin of the group.", chat_id=chat_id, message_id=message_id)
            return
        await context.bot.ban_chat_member(GROUP_CHAT_ID, target_id)
        await context.bot.unban_chat_member(GROUP_CHAT_ID, target_id)
        await context.bot.edit_message_text(
            f"✅ User (ID: <code>{target_id}</code>) has been <b>removed</b> from the group.",
            chat_id=chat_id, message_id=message_id, parse_mode="HTML"
        )
    except Exception as e:
        await context.bot.edit_message_text(
            f"❌ Failed to remove member: {str(e)}",
            chat_id=chat_id, message_id=message_id
        )

async def grow_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    parts = data.split("_")
    if len(parts) >= 3:
        try:
            target_id = int(parts[2])
        except ValueError:
            await context.bot.edit_message_text("❌ Invalid user ID.", chat_id=chat_id, message_id=message_id)
            return
    else:
        await context.bot.edit_message_text("❌ Invalid callback.", chat_id=chat_id, message_id=message_id)
        return
    if not GROUP_CHAT_ID:
        await context.bot.edit_message_text("❌ GROUP_CHAT_ID is not set.", chat_id=chat_id, message_id=message_id)
        return
    try:
        bot_member = await context.bot.get_chat_member(GROUP_CHAT_ID, context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            await context.bot.edit_message_text("❌ Bot is not an admin of the group.", chat_id=chat_id, message_id=message_id)
            return
        if not bot_member.can_invite_users:
            await context.bot.edit_message_text("❌ Bot does not have 'Add users' permission.", chat_id=chat_id, message_id=message_id)
            return
        resp = req.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/addChatMember",
            json={"chat_id": int(GROUP_CHAT_ID), "user_id": target_id},
            timeout=10
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            await context.bot.edit_message_text(
                f"✅ User (ID: <code>{target_id}</code>) has been <b>added</b> to the group.",
                chat_id=chat_id, message_id=message_id, parse_mode="HTML"
            )
        else:
            error_msg = data.get("description", resp.text)
            if "Not Found" in error_msg or "USER_PRIVACY_RESTRICTED" in error_msg:
                try:
                    invite_link = await context.bot.create_chat_invite_link(
                        GROUP_CHAT_ID,
                        member_limit=1,
                        creates_join_request=False
                    )
                    link = invite_link.invite_link
                    await context.bot.edit_message_text(
                        f"⚠️ Could not add user directly.\n"
                        f"👉 Send them this invite link:\n{link}\n"
                        f"The link expires after first use.",
                        chat_id=chat_id, message_id=message_id
                    )
                except Exception as e2:
                    await context.bot.edit_message_text(
                        f"❌ Could not add user and also failed to create invite link: {str(e2)}",
                        chat_id=chat_id, message_id=message_id
                    )
            else:
                await context.bot.edit_message_text(
                    f"❌ Failed to add member: {error_msg}",
                    chat_id=chat_id, message_id=message_id
                )
    except Exception as e:
        await context.bot.edit_message_text(
            f"❌ Failed to add member: {str(e)}",
            chat_id=chat_id, message_id=message_id
        )

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

def handler(request):
    return app(request.environ, start_response)
