"""Strict private-response entry point for the climate/environment Telegram bot.

Automatic scheduled news publishing remains in GROUP_CHAT_ID. Every interactive
Telegram keyboard-button response is forced to the requesting user's private
chat, including current buttons and stale buttons from older deployed menus.
"""

import asyncio

import three_button_runner as app

bot = app.bot


# Current buttons plus buttons that may remain visible on older Telegram
# keyboards after previous bot deployments. Keeping them here prevents an old
# button from falling through to a group-facing legacy handler.
ALL_KEYBOARD_BUTTONS = {
    # Current main menu
    "🇲🇻 Maldives",
    "🌍 Global",
    "🚨 Important",
    "🧭 Related Topics",
    # Current topic menu
    "🪸 Reefs & Oceans",
    "🚨 Weather",
    "🦋 Wildlife",
    "♻️ Pollution",
    "🌱 Conservation",
    "⚡ Clean Energy",
    "🌡️ Climate",
    "🏛️ Policy",
    "🔬 Research",
    "🏝️ Baa Atoll",
    "⬅️ Main Menu",
    # Older climate menus that may still be cached by Telegram clients
    "📰 Latest",
    "🔥 Trending",
    "🚨 Extreme Weather",
    "🌊 Oceans & Reefs",
    "🪸 Reef Watch",
    "♻️ Pollution & Waste",
    "🏛️ Climate Policy",
    "📡 Fetch Status",
    "🔄 Check News Now",
    "🔄 Refresh Menu",
    "❓ Help",
    # Very old menu buttons
    "📰 Latest News",
    "🌍 World",
    "💻 Technology",
    "💰 Business",
    "⚽ Sports",
    "🌊 Environment",
}


def strict_request_destination(message):
    chat = message.get("chat", {}) or {}
    sender = message.get("from", {}) or {}

    chat_id = chat.get("id")
    sender_id = sender.get("id")

    # Telegram private chat: chat.id == from.id.
    # Telegram group/supergroup: chat.id != from.id.
    if sender_id is not None and chat_id is not None and str(sender_id) != str(chat_id):
        return sender_id, chat_id, True

    return chat_id, chat_id, False


def strict_send_user_result(message, text, reply_markup=None):
    destination, origin_chat_id, came_from_group = strict_request_destination(message)

    if destination is None:
        bot.logging.warning("Private response skipped: no destination for message")
        return None

    sender_id = (message.get("from", {}) or {}).get("id")
    bot.logging.info(
        "Routing interactive response: origin=%s sender=%s destination=%s private_from_group=%s",
        origin_chat_id,
        sender_id,
        destination,
        came_from_group,
    )

    # Requested content goes only to the individual user.
    result = bot.send_message(
        text,
        destination,
        reply_markup=reply_markup or app.main_keyboard(),
    )

    if result:
        return result

    if came_from_group and origin_chat_id is not None:
        # Telegram does not allow a bot to initiate a private conversation with
        # someone who has never opened the bot. This is the only group-side
        # response allowed for an interactive request, and it contains no news.
        bot.send_message(
            "📩 <b>Private reply is not enabled for you yet.</b>\n\n"
            "Open my bot profile and press <b>Start</b> once. Then return here "
            "and press the button again. Your requested results will be sent "
            "only to your private chat.",
            origin_chat_id,
        )

    return None


# Install strict destination helpers used by the current app handler.
app.request_destination = strict_request_destination
app.send_user_result = strict_send_user_result


_base_private_handler = app.private_handle_command


def force_private_button_handler(message):
    """Force every known keyboard button through a private chat context.

    Some users can retain old reply-keyboard buttons after a deployment. Those
    older button labels may be handled several layers down by legacy handlers.
    Rewriting only the interactive message's chat destination guarantees those
    legacy handlers also reply to the individual user rather than the group.
    """
    text = (message.get("text") or "").strip()
    chat = message.get("chat", {}) or {}
    sender = message.get("from", {}) or {}
    chat_id = chat.get("id")
    sender_id = sender.get("id")
    came_from_group = (
        sender_id is not None
        and chat_id is not None
        and str(sender_id) != str(chat_id)
    )

    if text in ALL_KEYBOARD_BUTTONS and came_from_group:
        # Do not let the old manual-fetch button trigger a burst of automatic
        # group posts. The scheduled news loop already checks sources itself.
        if text == "🔄 Check News Now":
            result = bot.send_message(
                "🔎 <b>News monitoring is active.</b>\n\n"
                "The bot checks sources automatically. Manual group-triggered "
                "publishing is disabled so button activity stays private.",
                sender_id,
                reply_markup=app.main_keyboard(),
            )
            if not result:
                strict_send_user_result(message, "Open the bot privately and press Start once.")
            return

        private_message = dict(message)
        private_chat = dict(chat)
        private_chat["id"] = sender_id
        private_chat["type"] = "private"
        private_message["chat"] = private_chat

        bot.logging.info(
            "Forcing keyboard button private: text=%r group=%s user=%s",
            text,
            chat_id,
            sender_id,
        )
        _base_private_handler(private_message)
        return

    # Private-chat buttons already have the correct destination. Slash commands
    # and non-button text keep their existing behavior.
    _base_private_handler(message)


bot.public_command_keyboard = app.main_keyboard
bot.handle_command = force_private_button_handler
bot.build_welcome_message = app.private_welcome


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
