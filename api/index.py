# Updated dm_handler – Knock section with automatic username→ID conversion

async def dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or update.effective_chat.type != "private":
        return
    if user.id != OWNER_ID:
        await msg.reply_text("You are not authorized.")
        return

    text = msg.text.strip()

    # ── /debug ──
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

    # ── /reset ──
    if text == "/reset":
        authenticated_users.discard(user.id)
        for key in [f"add_state:{user.id}", f"transfer_state:{user.id}", f"knock_state:{user.id}"]:
            kv_delete(key)
        await msg.reply_text("🔒 Authentication reset. Send password to continue.")
        return

    # ── Password check ──
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
                "/memberknock - Remove a member (or any bot) by @username or numeric ID\n"
                "/reset - Clear authentication\n"
                "/debug - Test KV connection\n"
                "/cancel - Cancel current add/transfer/knock session"
            )
        else:
            await msg.reply_text("Incorrect password.")
        return

    # ── /cancel ──
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

    # ── /list ──
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

    # ── /delete ──
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

    # ── /add (start session) ──
    if text.startswith("/add"):
        state = {"step": "name", "data": {}}
        kv_set(f"add_state:{user.id}", json.dumps(state))
        await msg.reply_text("Send bot name:")
        return

    # ── /transfer (start session) ──
    if text.startswith("/transfer"):
        kv_set(f"transfer_state:{user.id}", "waiting")
        await msg.reply_text("✉️ Please send the message you want to forward to the group.")
        return

    # ── /memberknock (start session) ──
    if text.startswith("/memberknock"):
        kv_set(f"knock_state:{user.id}", "waiting")
        await msg.reply_text(
            "🔨 Send the @username or numeric user ID of the member (or bot) to remove.\n"
            "✨ Our bot will automatically convert the @username to a numeric ID."
        )
        return

    # ══════════════════════════════════════
    # ACTIVE SESSION HANDLING
    # ══════════════════════════════════════

    # ── KNOCK SESSION ──
    knock_state = kv_get(f"knock_state:{user.id}")
    if knock_state:
        target = text.strip()
        kv_delete(f"knock_state:{user.id}")

        if not GROUP_CHAT_ID:
            await msg.reply_text("❌ GROUP_CHAT_ID is not set.")
            return

        # 1️⃣ Resolve the target to a numeric user ID
        try:
            if target.lstrip('-').isdigit():
                # Already a numeric ID (e.g., 123456789)
                target_id = int(target)
                target_label = target
            else:
                # Treat as @username (with or without @)
                username = target if target.startswith('@') else '@' + target
                try:
                    # Fetch the member from the group – works for humans and bots
                    member = await context.bot.get_chat_member(GROUP_CHAT_ID, username)
                    target_id = member.user.id
                    target_label = username
                except Exception:
                    await msg.reply_text(
                        f"❌ Could not find '{username}' in the group.\n"
                        "👉 Make sure the user/bot is still in the group and try again.\n"
                        "💡 If the problem persists, use their numeric user ID (you can forward a message "
                        "from that user to @Getmyid_bot to get the ID)."
                    )
                    return

            # 2️⃣ Verify the bot has admin rights
            bot_member = await context.bot.get_chat_member(GROUP_CHAT_ID, context.bot.id)
            if bot_member.status not in ("administrator", "creator"):
                await msg.reply_text("❌ Bot is not an admin of the group.")
                return

            # 3️⃣ Kick the user (ban + unban)
            await context.bot.ban_chat_member(GROUP_CHAT_ID, target_id)
            await context.bot.unban_chat_member(GROUP_CHAT_ID, target_id)
            await msg.reply_text(f"✅ {target_label} has been removed from the group.")

        except Exception as e:
            await msg.reply_text(f"❌ Failed to remove member: {str(e)}")

        return

    # ── TRANSFER SESSION ──
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

    # ── ADD SESSION ──
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

    # ── Unknown command ──
    await msg.reply_text("Unknown command. Use /add, /list, /delete, /transfer, /memberknock, /reset, /debug, /cancel.")
