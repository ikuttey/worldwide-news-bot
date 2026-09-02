"""Railway entry point that adds a /chatid helper to the climate news bot."""

import asyncio

import bot_runner as runner

bot = runner.bot
_original_handle_command = bot.handle_command

# Add the command to Telegram's slash-command menu.
if not any(item.get("command") == "chatid" for item in bot.PUBLIC_COMMANDS):
    bot.PUBLIC_COMMANDS.insert(
        2,
        {"command": "chatid", "description": "Show this Telegram chat/group ID"},
    )


def handle_command_with_chat_id(message):
    text = message.get("text", "").strip()
    chat = message.get("chat", {}) or {}
    chat_id = chat.get("id")
    command = (
        text.split(maxsplit=1)[0].split("@")[0].lower()
        if text.startswith("/")
        else ""
    )

    if command == "/chatid":
        chat_type = chat.get("type", "unknown")
        title = chat.get("title") or chat.get("username") or "This chat"
        bot.send_message(
            "🆔 <b>Telegram Chat ID</b>\n\n"
            f"<b>Chat:</b> {bot.html.escape(str(title))}\n"
            f"<b>Type:</b> {bot.html.escape(str(chat_type))}\n"
            f"<b>ID:</b> <code>{bot.html.escape(str(chat_id))}</code>\n\n"
            "Copy the number shown as <b>ID</b> and use it as "
            "<code>GROUP_CHAT_ID</code> in Railway.",
            chat_id,
            reply_markup=runner.climate_command_keyboard(),
        )
        return

    _original_handle_command(message)


bot.handle_command = handle_command_with_chat_id


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
