async def dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or update.effective_chat.type != "private":
        return
    if user.id != OWNER_ID:
        await msg.reply_text("You are not authorized.")
        return

    text = msg.text.strip()

    # /debug command
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

    # /reset command
    if text == "/reset":
        authenticated_users.discard(user.id)
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

    # ---------- ACTIVE SESSION HANDLING ----------
    # Check for knock (member remove) session
    knock_key = f"knock_state:{user.id}"
    knock_state = kv_get(knock_key)
    if knock_state:
        # Owner sent the user identifier to kick
        target = text
        kv_delete(knock_key)
        if not GROUP_CHAT_ID:
            await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
            return
        try:
            # Try to resolve user ID (if it's a numeric ID or @username)
            if target.startswith("@"):
                # remove @
                target_username = target[1:]
                # Try to get chat member info (requires admin)
                member = await context.bot.get_chat_member(GROUP_CHAT_ID, "@"+target_username)
                target_id = member.user.id
            else:
                # assume it's a numeric user ID
                target_id = int(target)
            # Kick: ban then unban
            await context.bot.ban_chat_member(GROUP_CHAT_ID, target_id)
            await context.bot.unban_chat_member(GROUP_CHAT_ID, target_id)
            await msg.reply_text(f"✅ Member {target} has been removed from the group.")
        except Exception as e:
            await msg.reply_text(f"❌ Failed to remove member: {str(e)}")
        return

    # Check for active transfer session
    transfer_key = f"transfer_state:{user.id}"
    transfer_state_json = kv_get(transfer_key)
    if transfer_state_json:
        message_to_send = text
        kv_delete(transfer_key)
        if GROUP_CHAT_ID:
            try:
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_to_send)
                await msg.reply_text("✅ Message sent to the group.")
            except Exception as e:
                await msg.reply_text(f"❌ Failed to send message: {str(e)}")
        else:
            await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
        return

    # Check for active add session in KV
    state_key = f"add_state:{user.id}"
    add_state_json = kv_get(state_key)
    if add_state_json:
        try:
            state = json.loads(add_state_json)
        except:
            state = None
    else:
        state = None

    # /cancel during any session
    if text == "/cancel":
        if state:
            kv_delete(state_key)
        if transfer_state_json:
            kv_delete(transfer_key)
        if knock_state:
            kv_delete(knock_key)
        await msg.reply_text("🚫 Any active session cancelled.")
        return

    # If we have an active add session, handle that step
    if state:
        step = state.get("step")
        data = state.get("data", {})
        if step == "name":
            data["name"] = text
            state["step"] = "username"
            kv_set(state_key, json.dumps(state))
            await msg.reply_text("Send bot username (without @):")
        elif step == "username":
            data["username"] = text
            state["step"] = "link"
            kv_set(state_key, json.dumps(state))
            await msg.reply_text("Send bot link (e.g., https://t.me/YourBot):")
        elif step == "link":
            data["link"] = text
            state["step"] = "currency"
            kv_set(state_key, json.dumps(state))
            await msg.reply_text("Send currency (e.g., USDT, INR, BNB):")
        elif step == "currency":
            data["currency"] = text
            try:
                await add_bot_to_config(data["name"], data["username"], data["link"], data["currency"])
                await msg.reply_text("✅ Bot added successfully!")
            except Exception as e:
                await msg.reply_text(f"❌ Failed to save bot: {str(e)}")
            kv_delete(state_key)
        return

    # ---------- NO ACTIVE SESSION – HANDLE COMMANDS ----------
    if text.startswith("/memberknock"):
        kv_set(knock_key, "waiting")
        await msg.reply_text("🔨 Send the user ID or @username of the member to remove from the group.")
        return

    if text.startswith("/transfer"):
        kv_set(transfer_key, "waiting")
        await msg.reply_text("✉️ Please send the message you want to forward to the group.")
        return

    if text.startswith("/add"):
        state = {"step": "name", "data": {}}
        kv_set(state_key, json.dumps(state))
        await msg.reply_text("Send bot name:")
        return

    elif text.startswith("/list"):
        bots = get_official_bots()
        if not bots:
            await msg.reply_text("No bots added yet.")
        else:
            resp = "📋 <b>Official Bots:</b>\n"
            for i, bot in enumerate(bots):
                resp += f"{i+1}. {bot['name']} (@{bot['username']}) - {bot['currency']}\n"
            await msg.reply_html(resp)

    elif text.startswith("/delete"):
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

    else:
        await msg.reply_text("Unknown command. Use /add, /list, /delete, /transfer, /memberknock, /reset, /debug, /cancel.")
