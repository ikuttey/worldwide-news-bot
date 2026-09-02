"""Reliable three-button Telegram interface for the climate intelligence bot.

Keeps all climate/environment feeds, intelligence analysis, Telegram auth and
GROUP_CHAT_ID handling unchanged. The visible UI stays limited to Maldives,
Global and Important while adding safe list formatting and balanced history.
"""

import asyncio
import html

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


bot.PUBLIC_COMMANDS = [
    {"command": "maldives", "description": "All Maldives climate & environment news"},
    {"command": "global", "description": "All global climate & environment news"},
    {"command": "important", "description": "Most important climate & environment news"},
]


def safe_int(value, default=0):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def all_recent_news(hours=24 * 7):
    stories = list(bot.recent_history(hours))
    stories.sort(
        key=lambda item: (
            item.get("created_at", ""),
            safe_int(item.get("trending_score", 0)),
        ),
        reverse=True,
    )
    return stories


def important_news(limit=12, hours=24 * 7):
    stories = list(bot.recent_history(hours))
    severity_rank = {"Critical": 4, "High": 3, "Moderate": 2, "Watch": 1}

    stories.sort(
        key=lambda item: (
            1 if item.get("breaking") else 0,
            severity_rank.get(str(item.get("severity", "")), 0),
            max(
                safe_int(item.get("trending_score", 0)),
                safe_int(item.get("importance_score", 0)),
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
            safe_int(story.get("trending_score", 0)),
            safe_int(story.get("importance_score", 0)),
        ) >= 75
    ]

    # Important should always respond. If there are fewer hard-priority items,
    # fill the rest with the best-ranked recent environmental stories.
    if len(priority) < limit:
        selected = {id(story) for story in priority}
        priority.extend(story for story in stories if id(story) not in selected)

    return priority[:limit]


def safe_story_list(title, stories, limit=12):
    """Build Telegram-safe HTML without cutting through an HTML link/tag."""
    title_html = html.escape(str(title))

    if not stories:
        return (
            f"🌿 <b>{title_html}</b>\n\n"
            "No matching climate or environmental stories are stored yet. "
            "The bot is still monitoring the feeds and will add new stories automatically."
        )

    message = f"🌿 <b>{title_html}</b>\n\n"
    shown = 0

    for index, story in enumerate(stories[:limit], start=1):
        category = story.get("category", "Environment")
        emoji = bot.CATEGORY_EMOJIS.get(category, "🌍")
        headline = html.escape(str(story.get("headline", "Untitled report")))
        link = str(story.get("link", "") or "").strip()
        region = "🇲🇻" if story.get("maldives") else "🌍"
        severity = html.escape(str(story.get("severity") or "Watch"))
        location = html.escape(
            str(story.get("location") or ("Maldives" if story.get("maldives") else "Global"))
        )
        score = max(
            safe_int(story.get("trending_score", 0)),
            safe_int(story.get("importance_score", 0)),
        )

        if link.startswith(("https://", "http://")):
            headline_part = f'<a href="{html.escape(link, quote=True)}">{headline}</a>'
        else:
            headline_part = headline

        block = (
            f"{index}. {region} {emoji} {headline_part}\n"
            f"   📍 {location} · ⚠️ {severity} · 📊 {score}/100\n\n"
        )

        # Never use a raw string slice on HTML. Stop before Telegram's limit.
        if len(message) + len(block) > 3650:
            break

        message += block
        shown += 1

    if shown == 0:
        return f"🌿 <b>{title_html}</b>\n\nStories were found, but none could be formatted safely."

    return message.rstrip()


# ---------------------------------------------------------------------------
# BALANCED AUTOMATIC PUBLISHING
# ---------------------------------------------------------------------------
# The original ranking puts every Maldives cluster before every global cluster.
# With MAX_POSTS_PER_CHECK, a busy Maldives cycle can consume every slot and
# leave no global stories in history. Interleave both groups so both buttons
# have recent material whenever both kinds of news are available.


async def balanced_check_and_publish_news():
    bot.logging.info("Collecting climate and environment news with balanced regional publishing...")

    articles = await asyncio.to_thread(bot.fetch_new_articles)
    if not articles:
        bot.state["last_news_check"] = bot.utc_now_iso()
        bot.save_state()
        bot.logging.info("No new relevant stories.")
        return

    clusters = bot.cluster_articles(articles)
    maldives_items = []
    global_items = []

    for cluster in clusters:
        highest_score = max(bot.calculate_importance(article) for article in cluster["articles"])
        highest_score += min((len(cluster["publishers"]) - 1) * 6, 18)
        item = {"cluster": cluster, "local_score": min(100, highest_score)}

        if bot.is_maldives_story(cluster["articles"][0]):
            maldives_items.append(item)
        else:
            global_items.append(item)

    def ranking_key(item):
        cluster = item["cluster"]
        first = cluster["articles"][0]
        return (
            1 if bot.is_breaking_story(first) else 0,
            item["local_score"],
            len(cluster["publishers"]),
        )

    maldives_items.sort(key=ranking_key, reverse=True)
    global_items.sort(key=ranking_key, reverse=True)

    ordered = []
    while maldives_items or global_items:
        if maldives_items:
            ordered.append(maldives_items.pop(0))
        if global_items:
            ordered.append(global_items.pop(0))

    posted_count = 0
    ai_used_this_check = 0

    for item in ordered:
        if posted_count >= bot.MAX_POSTS_PER_CHECK:
            break

        cluster = item["cluster"]
        local_score = item["local_score"]
        first_article = cluster["articles"][0]

        if not bot.is_environment_story(first_article) or local_score < bot.MINIMUM_POST_SCORE:
            continue

        analysis = None
        if bot.should_use_ai(cluster, local_score, ai_used_this_check):
            analysis = await asyncio.to_thread(bot.analyze_cluster_with_ai, cluster)
            if analysis:
                ai_used_this_check += 1

        if not analysis:
            analysis = bot.local_cluster_analysis(cluster, local_score)

        trend_score = bot.calculate_trending_score(cluster, analysis)
        message = bot.build_news_message(cluster, analysis, trend_score)
        buttons = bot.build_source_buttons(cluster)

        published = await asyncio.to_thread(
            bot.publish_post,
            message,
            cluster.get("image"),
            buttons,
        )

        if published:
            bot.save_to_history(cluster, analysis, trend_score)
            posted_count += 1
            await asyncio.sleep(bot.MESSAGE_DELAY_SECONDS)

    bot.state["last_news_check"] = bot.utc_now_iso()
    bot.save_state()
    bot.logging.info(
        "Completed balanced cycle: %s posts, %s AI requests.",
        posted_count,
        ai_used_this_check,
    )


bot.check_and_publish_news = balanced_check_and_publish_news


_base_handle_command = bot.handle_command


def three_button_handle_command(message):
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")
    command = (
        text.split(maxsplit=1)[0].split("@")[0].lower()
        if text.startswith("/")
        else ""
    )

    try:
        if text == "🇲🇻 Maldives" or command == "/maldives":
            stories = [story for story in all_recent_news() if story.get("maldives")][:12]
            bot.send_message(
                safe_story_list("Maldives Climate & Environment", stories),
                chat_id,
                reply_markup=three_button_keyboard(),
            )
            return

        if text == "🌍 Global" or command == "/global":
            stories = [story for story in all_recent_news() if not story.get("maldives")][:12]
            bot.send_message(
                safe_story_list("Global Climate & Environment", stories),
                chat_id,
                reply_markup=three_button_keyboard(),
            )
            return

        if text == "🚨 Important" or command in {"/important", "/trending"}:
            stories = important_news(limit=12)
            bot.send_message(
                safe_story_list("Important Climate & Environment News", stories),
                chat_id,
                reply_markup=three_button_keyboard(),
            )
            return

        _base_handle_command(message)

    except Exception as error:
        bot.logging.exception("Three-button command failed for %r: %s", text, error)
        bot.send_message(
            "⚠️ <b>Could not load this news list.</b>\n\n"
            "The bot is still running. Please try the button again after the next news check.",
            chat_id,
            reply_markup=three_button_keyboard(),
        )


bot.public_command_keyboard = three_button_keyboard
bot.handle_command = three_button_handle_command


def simple_welcome():
    return f"""
🌿 <b>{bot.BOT_NAME}</b>

Climate and environmental news is monitored in full detail.

🇲🇻 <b>Maldives</b> — Maldives climate & environment news
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
