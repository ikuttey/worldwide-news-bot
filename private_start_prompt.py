"""Final Telegram launcher: clean public group, private controls, private onboarding.

The public group contains only automatic broadcast news. New members receive a
Telegram ephemeral onboarding message that is visible only to that member and the
bot, with one deep-link button that opens the private bot. All browsing and
personalization stay in private chat.
"""

import asyncio
import logging

import bilingual_onboarding as app
import continuous_private_ui as continuous

bot = app.bot
ui = app.ui

# Keep references to the already-layered private behavior before applying the final
# clean-group presentation.
_layer_send_message = bot.send_message
_layer_handle_message = bot.handle_message


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
    """Never attach private browsing reply keyboards to public group messages."""
    target = str(chat_id or bot.GROUP_CHAT_ID)
    is_main_group = bool(bot.GROUP_CHAT_ID) and target == str(bot.GROUP_CHAT_ID)
    if is_main_group:
        if isinstance(reply_markup, dict) and "inline_keyboard" not in reply_markup and "remove_keyboard" not in reply_markup:
            reply_markup = None
        return ui._base_send_message(text, chat_id, reply_markup, disable_preview)
    return _layer_send_message(text, chat_id, reply_markup, disable_preview)


def send_ephemeral_group_message(user_id, text, reply_markup=None):
    """Send a group-timeline message visible only to one specific user."""
    if user_id is None or not bot.GROUP_CHAT_ID:
        return None
    payload = {
        "chat_id": str(bot.GROUP_CHAT_ID),
        "receiver_user_id": int(user_id),
        "text": str(text)[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return bot.telegram_api("sendMessage", payload)


def send_private_with_start_prompt(message, text, reply_markup=None, start_payload="menu"):
    """Send privately, or show a user-only ephemeral Start prompt in the group."""
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

    prompt_text = (
        "🚨 <b>PRIVATE NEWS SETUP REQUIRED</b> 🚨\n\n"
        "🇬🇧 Tap the button below, open the bot and press <b>Start</b>. All browsing then stays in your private chat.\n\n"
        "🇲🇻 ތިރީގައި ހުންނަ ބަޓަން ފިތާ ބޮޓް ހުޅުވާ <b>Start</b> ފިތާލާ. އެއަށްފަހު ހުރިހާ ނޫސް ބަލާނީ ޕްރައިވެޓް ޗެޓުގައެވެ."
    )
    prompt = send_ephemeral_group_message(destination, prompt_text, markup)
    if prompt:
        logging.info("Sent user-only private-start prompt to %s", destination)
    else:
        logging.warning("Could not deliver ephemeral private-start prompt to %s", destination)
    return prompt


def handle_message(message):
    """Preserve the existing private and group message routing."""
    return _layer_handle_message(message)


def activate_private_entry_for_new_members(message):
    """Show each new human member a bilingual welcome visible only to that member."""
    members = list(message.get("new_chat_members") or [])
    if not members or not ui.is_main_group_message(message):
        return None

    last = None
    for member in members:
        if member.get("is_bot"):
            continue
        user_id = member.get("id")
        if user_id is None:
            continue
        name = str(member.get("first_name") or "").strip() or "there"
        markup = private_entry_markup(f"join_{user_id}")
        if not markup:
            continue

        text = (
            f"👋 <b>Welcome, {name}!</b>\n\n"
            "🇬🇧 <b>How to use this group</b>\n"
            "• The group is for public news updates only.\n"
            "• Tap <b>START PRIVATE NEWS</b> below.\n"
            "• Press <b>Start</b> in the bot chat once.\n"
            "• Maldives, Global, Important, Topics, My News, Saved and Search are available privately.\n"
            "• This welcome is visible only to you.\n\n"
            "🇲🇻 <b>މި ގްރޫޕް ބޭނުންކުރާނެ ގޮތް</b>\n"
            "• ގްރޫޕުގައި ހުންނާނީ ޕަބްލިކް ނޫސް އަޕްޑޭޓްތަކެވެ.\n"
            "• ތިރީގައި ހުންނަ <b>START PRIVATE NEWS</b> ބަޓަން ފިތާލާ.\n"
            "• ބޮޓުގެ ޕްރައިވެޓް ޗެޓުގައި <b>Start</b> އެއްފަހަރު ފިތާލާ.\n"
            "• Maldives، Global، Important، Topics، My News، Saved އަދި Search ޕްރައިވެޓް ޗެޓުގައި ލިބޭނެ.\n"
            "• މި ވެލްކަމް މެސެޖް ފެންނާނީ ތިބާއަށް އެކަނި."
        )
        sent = send_ephemeral_group_message(user_id, text, markup)
        if sent:
            logging.info("Sent ephemeral onboarding to new member %s", user_id)
            last = sent
        else:
            # Never fall back to a normal public welcome message; privacy is more important.
            logging.warning("Ephemeral onboarding could not be delivered to new member %s", user_id)
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
    bot.set_setting("solid_keyboard_version", "private-only-group-v2-ephemeral")
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
