"""Railway entry point for the climate/environment Telegram bot.

This wrapper keeps the core news logic in main.py while forcing Telegram to
replace any persistent keyboard left behind by the previous general-news bot.
"""

import asyncio

import main as bot


LEGACY_BUTTONS = {
    "📰 Latest News",
    "🌍 World",
    "💻 Technology",
    "💰 Business",
    "⚽ Sports",
    "🌊 Environment",
}


def climate_command_keyboard():
    """Return the current climate/environment-only Telegram keyboard."""
    return {
        "keyboard": [
            [{"text": "📰 Latest"}, {"text": "🔥 Trending"}],
            [{"text": "🇲🇻 Maldives"}, {"text": "🌍 Global"}],
            [{"text": "🌡️ Climate"}, {"text": "🌊 Oceans & Reefs"}],
            [{"text": "🦋 Wildlife"}, {"text": "♻️ Pollution & Waste"}],
            [{"text": "🌱 Conservation"}, {"text": "⚡ Clean Energy"}],
            [{"text": "🔬 Research"}, {"text": "🔄 Refresh Menu"}],
            [{"text": "❓ Help"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose a climate/environment section...",
    }


bot.PUBLIC_COMMANDS = [
    {"command": "help", "description": "Show the climate & environment menu"},
    {"command": "menu", "description": "Refresh the climate news menu"},
    {"command": "latest", "description": "Latest climate & environment news"},
    {"command": "trending", "description": "Most reported environmental stories"},
    {"command": "maldives", "description": "Maldives climate & environment news"},
    {"command": "global", "description": "Global climate & environment news"},
    {"command": "climate", "description": "Climate change and extreme weather"},
    {"command": "oceans", "description": "Ocean, coral reef and marine news"},
    {"command": "wildlife", "description": "Biodiversity and wildlife news"},
    {"command": "pollution", "description": "Pollution, plastics and waste"},
    {"command": "conservation", "description": "Conservation and restoration"},
    {"command": "energy", "description": "Renewable and clean energy"},
    {"command": "research", "description": "Environmental science and research"},
    {"command": "search", "description": "Search recent environmental stories"},
]


bot.HELP_TEXT = f"""
🌿 <b>Welcome to {bot.BOT_NAME}</b>

This bot is now dedicated to climate and environmental news from the Maldives and around the world.

🇲🇻 <b>Maldives</b> — local climate and environmental updates
🌍 <b>Global</b> — international climate and environmental news
🌡️ <b>Climate</b> — climate change, adaptation and extreme weather
🌊 <b>Oceans & Reefs</b> — coral reefs, oceans and marine ecosystems
🦋 <b>Wildlife</b> — biodiversity and wildlife
♻️ <b>Pollution & Waste</b> — plastics, pollution and waste
🌱 <b>Conservation</b> — conservation, restoration, forests and mangroves
⚡ <b>Clean Energy</b> — renewable energy and energy transition
🔬 <b>Research</b> — environmental science and monitoring

General politics, sports, entertainment, technology and business news are excluded unless directly related to climate or the environment.

Use <code>/menu</code> at any time to refresh the buttons.
Use <code>/search coral bleaching</code> to search recent stories.
""".strip()


def climate_welcome_message():
    return f"""
🌿 <b>{bot.BOT_NAME}</b>

✅ Climate/environment mode is active.
✅ The old general-news menu has been replaced.

Choose a section below:

🇲🇻 Maldives climate & environment
🌍 Global climate & environment
🌡️ Climate & extreme weather
🌊 Oceans, coral reefs & marine ecosystems
🦋 Biodiversity & wildlife
♻️ Pollution, plastics & waste
🌱 Conservation & restoration
⚡ Clean energy
🔬 Environmental research
""".strip()


_original_handle_command = bot.handle_command


def climate_handle_command(message):
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")
    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else ""

    # Telegram reply keyboards are persistent. If a user taps one of the old
    # buttons, immediately replace it with the climate/environment keyboard.
    if text in LEGACY_BUTTONS:
        bot.send_message(
            "🌿 <b>The news menu has changed.</b>\n\n"
            "This bot now covers only climate and environmental news. "
            "The updated menu is shown below.",
            chat_id,
            reply_markup=climate_command_keyboard(),
        )
        return

    if text == "🔄 Refresh Menu" or command == "/menu":
        bot.send_message(
            "🔄 <b>Climate & environment menu refreshed.</b>",
            chat_id,
            reply_markup=climate_command_keyboard(),
        )
        return

    if text == "🔬 Research" or command == "/research":
        stories = bot.filter_history(
            category_names={"Science & Research"},
            limit=8,
        )
        bot.send_message(
            bot.build_story_list("Environmental Science & Research", stories),
            chat_id,
            reply_markup=climate_command_keyboard(),
        )
        return

    _original_handle_command(message)


# Replace menu-facing functions before main.main() starts.
bot.public_command_keyboard = climate_command_keyboard
bot.build_welcome_message = climate_welcome_message
bot.handle_command = climate_handle_command


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
