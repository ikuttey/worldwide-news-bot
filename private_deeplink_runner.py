"""One-tap private-chat onboarding for the all-news Telegram bot.

A Telegram bot cannot initiate a private conversation with a user who has never
started it. When a group user requests news before starting the bot privately,
this runner shows a clickable deep-link button that opens the bot's private chat.
After the user presses Start once, all interactive news responses remain private.
"""

import asyncio

import all_news_private_runner as app

bot = app.bot

_bot_username_cache = None


def bot_username():
    """Resolve and cache this bot's Telegram username without hard-coding it."""
    global _bot_username_cache

    if _bot_username_cache:
        return _bot_username_cache

    info = bot.telegram_api("getMe")
    if isinstance(info, dict):
        username = str(info.get("username") or "").strip().lstrip("@")
        if username:
            _bot_username_cache = username
            return username

    return None


def private_start_keyboard():
    """Build a one-tap Telegram deep link into this bot's private chat."""
    username = bot_username()
    if not username:
        return None

    return {
        "inline_keyboard": [
            [
                {
                    "text": "📩 Open Private News",
                    "url": f"https://t.me/{username}?start=private_news",
                }
            ]
        ]
    }


def send_private_with_deeplink(message, text, reply_markup=None):
    """Send requested content privately; give new users a private-chat deep link."""
    destination, origin_chat_id, from_group = app.private_destination(message)
    if destination is None:
        return None

    result = bot.send_message(
        text,
        destination,
        reply_markup=reply_markup or app.main_keyboard(),
    )
    if result:
        return result

    if from_group and origin_chat_id is not None:
        markup = private_start_keyboard()
        instruction = (
            "📩 <b>Open your private news chat</b>\n\n"
            "Telegram requires you to start the bot privately once before I can "
            "send your requested news there. Tap <b>Open Private News</b> below, "
            "then press <b>Start</b>. After that, all button results will be sent "
            "only to your private chat."
        )

        if markup:
            bot.send_message(
                instruction,
                origin_chat_id,
                reply_markup=markup,
            )
        else:
            # If Telegram getMe is temporarily unavailable, never leak the news
            # request into the group; fall back to a short setup instruction.
            bot.send_message(
                instruction + "\n\nOpen my profile from this group and press <b>Start</b>.",
                origin_chat_id,
            )

    return None


# The all-news command handler resolves send_private from its module globals at
# runtime, so replacing it here upgrades every current button and command.
app.send_private = send_private_with_deeplink

bot.public_command_keyboard = app.main_keyboard
bot.build_welcome_message = app.welcome_text
bot.handle_command = app.all_news_handle_command
bot.build_digest = app.general_digest
bot.digest_scheduler = app.all_news_digest_scheduler


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
