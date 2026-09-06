"""Telegram UI launcher with solid group buttons and private results.

The public group uses Telegram's persistent reply keyboard for the familiar solid
Maldives / Global / Important / News Topics buttons at the bottom of the chat.
Telegram necessarily creates a normal group message when a reply-keyboard button is
pressed, so the bot immediately deletes that interaction message on a best-effort
basis and routes the requested result only to the requesting user's private chat.

To keep the solid keyboard reliably visible, every normal bot post sent to the main
group also carries the same reply keyboard. A small startup activation message keeps
the keyboard visible before the first news post arrives, then disappears automatically
as soon as the first normal group post successfully replaces it.

For a completely clean group this requires the bot to have Telegram's Delete Messages
administrator permission. Slash-command menus remain private-chat only, and manually
typed group commands are also deleted before their result is routed privately.

Inline callback handling is retained for old control-panel messages that may still
exist in the chat history.

The unified news/archive engine continues to live in main.py.
"""

import asyncio
import logging

import main as bot

UI_VERSION = "all-news-v9-solid-keyboard-kept-alive"

_base_handle_message = bot.handle_message
_base_handle_callback = bot.handle_callback
_base_send_message = bot.send_message
_keyboard_keeper_message_id = None


def group_inline_keyboard():
    """Compatibility keyboard for older inline control-panel messages."""
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


def group_keyboard_send_message(text, chat_id=None, reply_markup=None, disable_preview=True):
    """Attach the solid keyboard to every normal main-group bot post.

    The short startup activation message remains only until a regular group post has
    successfully taken over as the message carrying Telegram's persistent keyboard.
    """
    global _keyboard_keeper_message_id

    target = str(chat_id or bot.GROUP_CHAT_ID)
    is_main_group = bool(bot.GROUP_CHAT_ID) and target == str(bot.GROUP_CHAT_ID)
    injected_keyboard = is_main_group and reply_markup is None
    if injected_keyboard:
        reply_markup = bot.main_keyboard()

    result = _base_send_message(text, chat_id, reply_markup, disable_preview)

    if injected_keyboard and result and _keyboard_keeper_message_id:
        new_message_id = result.get("message_id") if isinstance(result, dict) else None
        if new_message_id != _keyboard_keeper_message_id:
            bot.telegram_api(
                "deleteMessage",
                {
                    "chat_id": str(bot.GROUP_CHAT_ID),
                    "message_id": _keyboard_keeper_message_id,
                },
            )
            _keyboard_keeper_message_id = None
            bot.set_setting("solid_keyboard_keeper_message_id", "")

    return result


def silent_send_private(message, text, reply_markup=None, start_payload="menu"):
    """Send only to the requester. Never fall back to a group news response."""
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
    """Keep old inline control-panel buttons working privately."""
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
                    "text": "Open the bot privately and press Start once, then try again.",
                    "show_alert": True,
                },
            )
    return result


GROUP_BUTTONS = {
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
    """Immediately remove a reply-keyboard press or group slash command."""
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    if chat_id is None or message_id is None:
        return None
    return bot.telegram_api(
        "deleteMessage",
        {"chat_id": str(chat_id), "message_id": message_id},
    )


def handle_message(message):
    """Delete visible group interactions, then let the core send results privately."""
    text = str(message.get("text") or "").strip()
    from_group = is_group_message(message)

    if from_group and (text in GROUP_BUTTONS or text.startswith("/")):
        deleted = delete_group_interaction_message(message)
        if not deleted:
            logging.warning(
                "Could not delete group interaction %r. Ensure the bot has Delete Messages permission.",
                text,
            )

    return _base_handle_message(message)


async def configure_command_scopes():
    """Show Telegram slash commands only in private chats, never in groups."""
    await asyncio.to_thread(
        bot.telegram_api,
        "setMyCommands",
        {"commands": [], "scope": {"type": "default"}},
    )
    await asyncio.to_thread(
        bot.telegram_api,
        "setMyCommands",
        {"commands": [], "scope": {"type": "all_group_chats"}},
    )
    await asyncio.to_thread(
        bot.telegram_api,
        "setMyCommands",
        {"commands": bot.PUBLIC_COMMANDS, "scope": {"type": "all_private_chats"}},
    )


async def remove_old_inline_control_panel():
    """Remove the previous pinned inline panel if the bot still knows its message id."""
    old_message_id = bot.get_setting("group_control_panel_message_id")
    if not old_message_id:
        return
    try:
        await asyncio.to_thread(
            bot.telegram_api,
            "deleteMessage",
            {"chat_id": str(bot.GROUP_CHAT_ID), "message_id": int(old_message_id)},
        )
    except (TypeError, ValueError):
        pass
    bot.set_setting("group_control_panel_message_id", "")


async def restore_solid_group_keyboard():
    """Show the solid keyboard immediately and keep it until a normal news post replaces it."""
    global _keyboard_keeper_message_id

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

    activation = await asyncio.to_thread(
        bot.send_message,
        "📰 <b>News buttons ready</b>\n\n"
        "Tap Maldives, Global, Important or News Topics below. "
        "Your button message disappears and the result is sent privately.",
        bot.GROUP_CHAT_ID,
        bot.main_keyboard(),
        True,
    )

    if isinstance(activation, dict) and activation.get("message_id"):
        _keyboard_keeper_message_id = activation["message_id"]
        bot.set_setting("solid_keyboard_keeper_message_id", _keyboard_keeper_message_id)

    bot.set_setting("solid_keyboard_version", UI_VERSION)
    return activation


async def main():
    bot.validate_configuration()
    bot.init_db()

    info = await asyncio.to_thread(bot.telegram_api, "getMe")
    if not info:
        raise RuntimeError("Telegram connection failed")
    bot.BOT_USERNAME = str(info.get("username") or "").strip().lstrip("@")

    await configure_command_scopes()
    await remove_old_inline_control_panel()
    await restore_solid_group_keyboard()
    bot.set_setting("startup_announcement_version", UI_VERSION)

    await asyncio.gather(
        bot.automatic_news_loop(),
        bot.command_listener(),
        bot.digest_scheduler(),
    )


# Patch the shared engine at runtime. Private messages stay unchanged; only normal
# main-group posts receive the solid reply keyboard automatically.
bot.send_message = group_keyboard_send_message
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
