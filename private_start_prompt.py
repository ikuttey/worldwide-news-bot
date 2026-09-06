"""Final Telegram launcher: clean public group, private controls, bilingual onboarding.

The public group no longer exposes the Maldives/Global/Important/Topics reply keyboard.
New members receive one bilingual temporary onboarding message with a single deep-link
button that opens the private bot. After that member starts the bot privately, the
member-specific onboarding message is deleted from the group.

Private browsing keeps the image-card UI, topic controls and Show more flow.
"""

import asyncio
import logging
import threading

import bilingual_onboarding as app
import continuous_private_ui as continuous

bot = app.bot
ui = app.ui

PROMPT_LIFETIME_SECONDS = 120

# Keep references to the already-layered private behavior before applying the final
# clean-group presentation.
_layer_send_message = bot.send_message
_layer_handle_message = bot.handle_message


def _delete_prompt_later(message_id):
    if not message_id:
        return

    def remove():
        try:
            bot.telegram_api(
                "deleteMessage",
                {"chat_id": str(bot.GROUP_CHAT_ID), "message_id": message_id},
            )
        except Exception as error:
            logging.debug("Could not remove private-start prompt %s: %s", message_id, error)

    timer = threading.Timer(PROMPT_LIFETIME_SECONDS, remove)
    timer.daemon = True
    timer.start()


def private_entry_markup(payload="menu"):
    username = bot.bot_username()
    if not username:
        return None
    safe_payload = str(payload or "menu").strip() or "menu"
    return {
        "inline_keyboard": [[
            {
                "text": "🔴 START PRIVATE NEWS 🔴",
                "url": f"https://t.me/{username}?start={safe_payload}",
            }
        ]]
    }


def clean_group_send_message(text, chat_id=None, reply_markup=None, disable_preview=True):
    """Never attach the private browsing reply keyboard to public group messages."""
    target = str(chat_id or bot.GROUP_CHAT_ID)
    is_main_group = bool(bot.GROUP_CHAT_ID) and target == str(bot.GROUP_CHAT_ID)
    if is_main_group:
        # Inline buttons explicitly supplied for onboarding are allowed. Reply keyboards
        # are stripped so Maldives/Global/Important/Topics stay private-only.
        if isinstance(reply_markup, dict) and "inline_keyboard" not in reply_markup and "remove_keyboard" not in reply_markup:
            reply_markup = None
        return ui._base_send_message(text, chat_id, reply_markup, disable_preview)
    return _layer_send_message(text, chat_id, reply_markup, disable_preview)


def send_private_with_start_prompt(message, text, reply_markup=None, start_payload="menu"):
    """Send privately, or show a temporary Start button when Telegram blocks the DM."""
    destination, origin_chat_id, from_group = bot.private_destination(message)
    if destination is None:
        return None

    if not bot.rate_allowed(destination):
        return bot.send_message(
            "⏳ Too many requests. Please wait a moment and try again.",
            destination,
            bot.main_keyboard(),
        )

    result = bot.send_message(text, destination, reply_markup or bot.main_keyboard())
    if result:
        return result

    if not from_group or origin_chat_id is None:
        return None

    markup = private_entry_markup(start_payload)
    if not markup:
        return None

    prompt = ui._base_send_message(
        "🚨 <b>PRIVATE NEWS SETUP REQUIRED</b> 🚨\n\n"
        "🇬🇧 Tap the button below, open the bot and press <b>Start</b>. All browsing then stays in your private chat.\n\n"
        "🇲🇻 ތިރީގައި ހުންނަ ބަޓަން ފިތާ ބޮޓް ހުޅުވާ <b>Start</b> ފިތާލާ. އެއަށްފަހު ހުރިހާ ނޫސް ބަލާނީ ޕްރައިވެޓް ޗެޓުގައެވެ.",
        origin_chat_id,
        markup,
        True,
    )
    if isinstance(prompt, dict):
        _delete_prompt_later(prompt.get("message_id"))
    logging.info("Asked first-time user %s to start the private bot chat", destination)
    return prompt


def _remove_saved_join_prompt(user_id):
    key = f"join_private_prompt_{user_id}"
    stored = bot.get_setting(key)
    if not stored:
        return
    try:
        bot.telegram_api(
            "deleteMessage",
            {"chat_id": str(bot.GROUP_CHAT_ID), "message_id": int(stored)},
        )
    except (TypeError, ValueError):
        pass
    except Exception as error:
        logging.debug("Could not delete completed onboarding prompt for %s: %s", user_id, error)
    bot.set_setting(key, "")


def handle_message(message):
    """Delete a member's group onboarding message once they start the private bot."""
    text = str(message.get("text") or "").strip()
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")
    sender_id = sender.get("id")
    is_private = chat_id is not None and sender_id is not None and str(chat_id) == str(sender_id)
    if is_private and text.startswith("/start"):
        _remove_saved_join_prompt(sender_id)
    return _layer_handle_message(message)


def activate_private_entry_for_new_members(message):
    """Send each new human member bilingual instructions with one private Start button."""
    members = list(message.get("new_chat_members") or [])
    if not members or not ui.is_main_group_message(message):
        return None

    last = None
    for member in members:
        if member.get("is_bot"):
            continue
        user_id = member.get("id")
        name = str(member.get("first_name") or "").strip() or "there"
        payload = f"join_{user_id}" if user_id is not None else "menu"
        markup = private_entry_markup(payload)
        if not markup:
            continue

        text = (
            f"👋 <b>Welcome, {name}!</b>\n\n"
            "🇬🇧 <b>How to use this group</b>\n"
            "• The group is for public news updates only.\n"
            "• Tap <b>START PRIVATE NEWS</b> below.\n"
            "• Press <b>Start</b> in the bot chat once.\n"
            "• Maldives, Global, Important, Topics and Show more are all available privately.\n"
            "• After you start the bot, this instruction message will disappear from the group.\n\n"
            "🇲🇻 <b>މި ގްރޫޕް ބޭނުންކުރާނެ ގޮތް</b>\n"
            "• ގްރޫޕުގައި ހުންނާނީ ޕަބްލިކް ނޫސް އަޕްޑޭޓްތަކެވެ.\n"
            "• ތިރީގައި ހުންނަ <b>START PRIVATE NEWS</b> ބަޓަން ފިތާލާ.\n"
            "• ބޮޓުގެ ޕްރައިވެޓް ޗެޓުގައި <b>Start</b> އެއްފަހަރު ފިތާލާ.\n"
            "• Maldives، Global، Important، Topics އަދި Show more ހުރިހާ ބަޓަނެއް ޕްރައިވެޓް ޗެޓުގައި ލިބޭނެ.\n"
            "• ބޮޓް Start ކުރުމުން މި މެސެޖް ގްރޫޕުން ފިލާނެ."
        )
        sent = ui._base_send_message(text, bot.GROUP_CHAT_ID, markup, True)
        if isinstance(sent, dict) and sent.get("message_id") and user_id is not None:
            bot.set_setting(f"join_private_prompt_{user_id}", sent["message_id"])
            logging.info("Sent private-only onboarding to new member %s", user_id)
        if sent:
            last = sent
    return last


async def remove_public_reply_keyboard():
    """Clear the old solid group keyboard from existing Telegram clients on startup."""
    old_keeper = bot.get_setting("solid_keyboard_keeper_message_id")
    if old_keeper:
        try:
            await asyncio.to_thread(
                bot.telegram_api,
                "deleteMessage",
                {"chat_id": str(bot.GROUP_CHAT_ID), "message_id": int(old_keeper)},
            )
        except (TypeError, ValueError):
            pass
    bot.set_setting("solid_keyboard_keeper_message_id", "")

    removal = await asyncio.to_thread(
        ui._base_send_message,
        "🔒 News browsing has moved to private chat.",
        bot.GROUP_CHAT_ID,
        {"remove_keyboard": True},
        True,
    )
    await asyncio.sleep(0.8)
    if isinstance(removal, dict) and removal.get("message_id"):
        await asyncio.to_thread(
            bot.telegram_api,
            "deleteMessage",
            {"chat_id": str(bot.GROUP_CHAT_ID), "message_id": removal["message_id"]},
        )
    bot.set_setting("solid_keyboard_version", "private-only-group-v1")
    return removal


def send_group_story_without_controls(row):
    """Keep publisher images in the group, but never attach browsing controls."""
    image_url = continuous.resolve_article_image(row["primary_url"])
    if image_url:
        payload = {
            "chat_id": str(bot.GROUP_CHAT_ID),
            "photo": image_url,
            "caption": continuous.group_photo_caption(row),
            "parse_mode": "HTML",
        }
        result = bot.telegram_api("sendPhoto", payload, timeout=45)
        if result:
            logging.info("Posted clean group story with publisher image: %s", row["primary_publisher"])
            return result
        logging.info("Publisher image could not be sent; using text fallback for %s", row["primary_publisher"])
    return ui._base_send_message(bot.group_post_message(row), bot.GROUP_CHAT_ID, None, False)


# Final production patches.
bot.send_message = clean_group_send_message
bot.send_private = send_private_with_start_prompt
bot.handle_message = handle_message
ui.activate_keyboard_for_new_members = activate_private_entry_for_new_members
ui.restore_solid_group_keyboard = remove_public_reply_keyboard
continuous.send_group_story = send_group_story_without_controls


async def main():
    await app.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped", bot.BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
