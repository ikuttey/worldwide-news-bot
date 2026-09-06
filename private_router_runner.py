"""Strict private-response entry point for the climate/environment Telegram bot.

Automatic news publishing remains in GROUP_CHAT_ID. Interactive button/command
results requested from a group are sent only to the requesting user's Telegram
user ID. This wrapper removes any dependency on chat.type for routing.
"""

import asyncio

import three_button_runner as app

bot = app.bot


def strict_request_destination(message):
    chat = message.get("chat", {}) or {}
    sender = message.get("from", {}) or {}

    chat_id = chat.get("id")
    sender_id = sender.get("id")

    # In a private Telegram chat, chat.id == from.id. In a group/supergroup,
    # chat.id is the group while from.id is the person who pressed the button.
    # Use the ID relationship instead of relying on chat.type.
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

    # The requested news/topic result is sent only to destination. For group
    # requests destination is the user's Telegram ID, never GROUP_CHAT_ID.
    result = bot.send_message(
        text,
        destination,
        reply_markup=reply_markup or app.main_keyboard(),
    )

    if result:
        return result

    if came_from_group and origin_chat_id is not None:
        # Telegram bots cannot initiate a private chat until the user has
        # opened the bot and pressed Start. Do not leak the requested news list
        # into the group; post only this short setup instruction.
        bot.send_message(
            "📩 <b>Private reply is not enabled for you yet.</b>\n\n"
            "Open my bot profile and press <b>Start</b> once. Then return here "
            "and press the news button again. Your requested results will be "
            "sent only to your private chat.",
            origin_chat_id,
            reply_markup=app.main_keyboard(),
        )

    return None


# Replace the routing helpers used by three_button_runner.private_handle_command.
app.request_destination = strict_request_destination
app.send_user_result = strict_send_user_result

# Keep the already-configured private command handler and menus active.
bot.public_command_keyboard = app.main_keyboard
bot.handle_command = app.private_handle_command
bot.build_welcome_message = app.private_welcome


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
