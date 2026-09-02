"""Three-button Telegram interface for the climate intelligence bot.

Keeps all existing climate/environment feeds, analysis, automatic publishing,
Telegram authentication and GROUP_CHAT_ID handling unchanged. Only the visible
Telegram menu and its three primary browsing actions are simplified.
"""

import asyncio

import climate_intelligence_runner as intelligence

bot = intelligence.bot


def three_button_keyboard():
    return {
        "keyboard": [
            [
                {"text": "🇲🇻 Maldives"},
                {"text": "🌍 Global"},
                {"text": "🚨 Important"},
            ]
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose Maldives, Global or Important...",
    }


# Keep Telegram's slash-command list equally simple.
bot.PUBLIC_COMMANDS = [
    {"command": "maldives", "description": "All Maldives climate & environment news"},
    {"command": "global", "description": "All global climate & environment news"},
    {"command": "important", "description": "Most important climate & environment news"},
]


def recent_news(limit=12, hours=24 * 14):
    stories = bot.recent_history(hours)
    stories.sort(
        key=lambda item: (
            item.get("created_at", ""),
            item.get("trending_score", 0),
        ),
        reverse=True,
    )
    return stories[:limit]


def important_news(limit=12, hours=24 * 14):
    stories = bot.recent_history(hours)

    severity_rank = {
        "Critical": 4,
        "High": 3,
        "Moderate": 2,
        "Watch": 1,
    }

    # Important means genuinely high-priority material first: breaking stories,
    # Critical/High severity and high trend/importance scores. If there are too
    # few hard alerts, the highest-ranked remaining stories fill the list.
    stories.sort(
        key=lambda item: (
            1 if item.get("breaking") else 0,
            severity_rank.get(item.get("severity", ""), 0),
            max(
                int(item.get("trending_score", 0) or 0),
                int(item.get("importance_score", 0) or 0),
            ),
            item.get("created_at", ""),
        ),
        reverse=True,
    )

    priority = [
        story
        for story in stories
        if story.get("breaking")
        or story.get("severity") in {"Critical", "High"}
        or max(
            int(story.get("trending_score", 0) or 0),
            int(story.get("importance_score", 0) or 0),
        ) >= 75
    ]

    if len(priority) < limit:
        selected_ids = {id(story) for story in priority}
        priority.extend(story for story in stories if id(story) not in selected_ids)

    return priority[:limit]


_base_handle_command = bot.handle_command


def three_button_handle_command(message):
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")
    command = (
        text.split(maxsplit=1)[0].split("@")[0].lower()
        if text.startswith("/")
        else ""
    )

    if text == "🇲🇻 Maldives" or command == "/maldives":
        stories = [story for story in recent_news(limit=40) if story.get("maldives")][:12]
        bot.send_message(
            intelligence.rich_story_list("Maldives Climate & Environment", stories),
            chat_id,
            reply_markup=three_button_keyboard(),
        )
        return

    if text == "🌍 Global" or command == "/global":
        stories = [story for story in recent_news(limit=50) if not story.get("maldives")][:12]
        bot.send_message(
            intelligence.rich_story_list("Global Climate & Environment", stories),
            chat_id,
            reply_markup=three_button_keyboard(),
        )
        return

    if text == "🚨 Important" or command in {"/important", "/trending"}:
        stories = important_news(limit=12)
        bot.send_message(
            intelligence.rich_story_list("Important Climate & Environment News", stories),
            chat_id,
            reply_markup=three_button_keyboard(),
        )
        return

    # Existing hidden commands continue to work if manually typed, but every
    # response returns users to the simplified three-button keyboard.
    _base_handle_command(message)


bot.public_command_keyboard = three_button_keyboard
bot.handle_command = three_button_handle_command


def simple_welcome():
    return f"""
🌿 <b>{bot.BOT_NAME}</b>

Climate and environmental news is still monitored in full detail.

🇲🇻 <b>Maldives</b> — all Maldives climate & environment news
🌍 <b>Global</b> — worldwide climate & environment news
🚨 <b>Important</b> — highest-priority stories from both

Choose one of the three buttons below.
""".strip()


bot.build_welcome_message = simple_welcome


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
