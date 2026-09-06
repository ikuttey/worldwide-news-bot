"""Final Telegram launcher: private image news plus first-time Start prompt.

Telegram bots cannot initiate a private chat with a user who has never opened the bot
and pressed Start. The image-card UI keeps news results out of the group, so this
wrapper restores only the onboarding prompt: if a private delivery fails for a group
user, the group receives a temporary inline button that opens the bot with the
original request encoded in the deep link. No news content is posted publicly.
"""

import asyncio
import logging
import threading

import private_image_ui as app

bot = app.bot
ui = app.ui

PROMPT_LIFETIME_SECONDS = 120


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

    username = bot.bot_username()
    if not username:
        return None

    payload = str(start_payload or "menu").strip() or "menu"
    markup = {
        "inline_keyboard": [[
            {
                "text": "📩 Open Private News & Start",
                "url": f"https://t.me/{username}?start={payload}",
            }
        ]]
    }
    prompt = ui._base_send_message(
        "📩 <b>Private news setup</b>\n\n"
        "Telegram requires you to open the bot and press <b>Start</b> once before I can send you private news. "
        "Tap below, press Start, and your request will continue privately.",
        origin_chat_id,
        markup,
        True,
    )
    if isinstance(prompt, dict):
        _delete_prompt_later(prompt.get("message_id"))
    logging.info("Asked first-time user %s to start the private bot chat", destination)
    return prompt


# The image-card UI and group UI both resolve bot.send_private dynamically, so this
# final patch covers group buttons, topic buttons, image-card batches and searches.
bot.send_private = send_private_with_start_prompt


async def main():
    await app.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped", bot.BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
