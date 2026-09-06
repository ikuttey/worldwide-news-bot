"""Telegram UI launcher that keeps group browsing silent.

The public group uses inline callback buttons, so tapping Maldives/Global/Important/
News Topics does not create a user message in the group. Results are sent only to
the requesting user's private chat. Slash-command menus are exposed only in private
chats. Any manually typed group command is deleted on a best-effort basis before its
result is routed privately.

The existing unified news/archive engine continues to live in main.py.
"""

import asyncio
import logging

import main as bot

UI_VERSION = "all-news-v6-private-inline-no-group-commands"

_base_handle_message = bot.handle_message
_base_handle_callback = bot.handle_callback


def group_inline_keyboard():
    rows = [
        [
            {"text": "🇲🇻 Maldives", "callback_data": "private|maldives"},
            {"text": "🌍 Global", "callback_data": "private|global"},
            {"text": "🚨 Important", "callback_data": "private|important"},
        ],
        [{"text": "🧭 News Topics", "callback_data": "private|topics"}],
    ]
    username = bot.bot_username()
    if username:
        rows.append([
            {"text": "📩 Open Private News", "url": f"https://t.me/{username}?start=menu"}
        ])
    return {"inline_keyboard": rows}


def silent_send_private(message, text, reply_markup=None, start_payload="menu"):
    """Send only to the requester. Never fall back to a group message."""
    destination, _, _ = bot.private_destination(message)
    if destination is None:
        return None
    if not bot.rate_allowed(destination):
        return bot.send_message(
            "⏳ Too many requests. Please wait a moment and try again.",
            destination,
            bot.main_keyboard(),
        )
    return bot.send_message(text, destination, reply_markup or bot.main_keyboard())


def callback_message(callback):
    return {
        "chat": (callback.get("message") or {}).get("chat") or {},
        "from": callback.get("from") or {},
        "text": "",
    }


def send_maldives_from_callback(message):
    intro = bot.send_private(
        message,
        "🇲🇻 <b>Maldives News Archive</b>\n\n"
        "English and Dhivehi are kept separately so one language cannot hide the other. "
        "Use Next/Previous to browse all stored Maldives stories.",
        bot.main_keyboard(),
        start_payload="view_maldives_all",
    )
    if not intro:
        return None

    destination, _, _ = bot.private_destination(message)
    for language in ("en", "dv"):
        rows, total = bot.query_stories("maldives", 0, language)
        text, markup = bot.format_story_page(
            bot.title_for_kind("maldives", language),
            "maldives",
            rows,
            total,
            0,
            language,
        )
        bot.send_message(text, destination, markup)
    return intro


def handle_callback(callback):
    data = str(callback.get("data") or "")
    callback_id = callback.get("id")

    if not data.startswith("private|"):
        return _base_handle_callback(callback)

    kind = data.split("|", 1)[1]
    message = callback_message(callback)
    result = None

    try:
        if kind == "maldives":
            result = send_maldives_from_callback(message)
        elif kind == "topics":
            result = bot.send_private(
                message,
                "🧭 <b>News Topics</b>\n\nChoose a topic below. Results stay in your private chat.",
                bot.topics_keyboard(),
                "topics",
            )
        elif kind in {
            "global", "important", "breaking", "politics", "business",
            "technology", "sports", "entertainment", "health", "science",
            "travel", "environment", "crime", "latest",
        }:
            result = bot.send_kind_page(message, kind)
    except Exception as error:
        logging.exception("Private group callback failed for %s: %s", kind, error)

    if callback_id:
        if result:
            bot.telegram_api(
                "answerCallbackQuery",
                {"callback_query_id": callback_id, "text": "Sent privately ✅"},
            )
        else:
            bot.telegram_api(
                "answerCallbackQuery",
                {
                    "callback_query_id": callback_id,
                    "text": "Open Private News below and press Start once, then try again.",
                    "show_alert": True,
                },
            )
    return result


STALE_GROUP_BUTTONS = {
    "🇲🇻 Maldives", "🌍 Global", "🚨 Important", "🧭 News Topics",
    "🧭 Related Topics", "🚨 Breaking", "🏛️ Politics", "💰 Business",
    "💻 Technology & AI", "⚽ Sports", "🎬 Entertainment", "🏥 Health",
    "🔬 Science", "✈️ Travel & Tourism", "🌊 Environment",
    "⚖️ Crime & Courts", "📰 Latest", "⬅️ Main Menu",
}


def is_group_message(message):
    chat_id = (message.get("chat") or {}).get("id")
    sender_id = (message.get("from") or {}).get("id")
    return chat_id is not None and sender_id is not None and str(chat_id) != str(sender_id)


def delete_group_interaction_message(message):
    """Best-effort cleanup for old keyboard presses or manually typed commands."""
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    if chat_id is None or message_id is None:
        return None
    return bot.telegram_api(
        "deleteMessage",
        {"chat_id": str(chat_id), "message_id": message_id},
    )


def handle_message(message):
    """Keep button/command interactions out of the group timeline."""
    text = str(message.get("text") or "").strip()
    from_group = is_group_message(message)

    if from_group and (text in STALE_GROUP_BUTTONS or text.startswith("/")):
        # Inline callbacks never create group messages. This path exists only for
        # cached reply keyboards and users who manually type slash commands.
        # Deleting another user's group message requires Telegram's Delete Messages
        # permission for the bot, so this is intentionally best effort.
        delete_group_interaction_message(message)

    # The unified core routes supported commands/buttons to the sender's private ID.
    return _base_handle_message(message)


async def configure_command_scopes():
    """Show Telegram slash commands only in private chats, never in groups."""
    # Clear the old default/global command list left by previous deployments.
    await asyncio.to_thread(
        bot.telegram_api,
        "setMyCommands",
        {"commands": [], "scope": {"type": "default"}},
    )
    # Explicitly keep group chats command-free even if Telegram has cached defaults.
    await asyncio.to_thread(
        bot.telegram_api,
        "setMyCommands",
        {"commands": [], "scope": {"type": "all_group_chats"}},
    )
    # Preserve the convenient command menu inside each user's private bot chat.
    await asyncio.to_thread(
        bot.telegram_api,
        "setMyCommands",
        {"commands": bot.PUBLIC_COMMANDS, "scope": {"type": "all_private_chats"}},
    )


async def main():
    bot.validate_configuration()
    bot.init_db()

    info = await asyncio.to_thread(bot.telegram_api, "getMe")
    if not info:
        raise RuntimeError("Telegram connection failed")
    bot.BOT_USERNAME = str(info.get("username") or "").strip().lstrip("@")

    await configure_command_scopes()

    if bot.get_setting("startup_announcement_version") != UI_VERSION:
        # Remove the old persistent reply keyboard. This temporary message is
        # deleted after Telegram clients receive the keyboard-removal update.
        removal = await asyncio.to_thread(
            bot.send_message,
            "🔒 Switching group browsing to silent private mode…",
            bot.GROUP_CHAT_ID,
            {"remove_keyboard": True},
            True,
        )

        await asyncio.to_thread(
            bot.send_message,
            bot.welcome_text() +
            "\n\n<b>Tap the buttons below.</b> Your selection is not posted in the group; results are sent privately. "
            "Slash commands are available only in your private bot chat.",
            bot.GROUP_CHAT_ID,
            group_inline_keyboard(),
            True,
        )

        if isinstance(removal, dict) and removal.get("message_id"):
            await asyncio.sleep(1)
            await asyncio.to_thread(
                bot.telegram_api,
                "deleteMessage",
                {"chat_id": str(bot.GROUP_CHAT_ID), "message_id": removal["message_id"]},
            )

        bot.set_setting("startup_announcement_version", UI_VERSION)

    await asyncio.gather(
        bot.automatic_news_loop(),
        bot.command_listener(),
        bot.digest_scheduler(),
    )


# Replace only the interaction routing. The news engine remains in main.py.
bot.send_private = silent_send_private
bot.handle_callback = handle_callback
bot.handle_message = handle_message


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped", bot.BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
