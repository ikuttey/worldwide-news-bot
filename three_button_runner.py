"""Private browsing + broad climate/environment coverage for the Telegram bot.

Automatic climate/environment news continues to publish to GROUP_CHAT_ID.
User button/command requests are delivered privately whenever Telegram permits.
The public menu stays simple: Maldives, Global, Important and Related Topics.
"""

import asyncio
import html

import climate_intelligence_runner as intelligence

bot = intelligence.bot


# ============================================================
# EXPANDED MALDIVES + GLOBAL DISCOVERY
# ============================================================
# These are additional discovery feeds. Every item still passes the existing
# strict climate/environment relevance filter before it can be published.

bot.MALDIVES_GOOGLE_FEEDS.update(
    {
        "🇲🇻 Maldives Environment EN — Broad": bot.google_news_feed(
            'Maldives (environment OR climate OR ocean OR coral OR reef OR biodiversity OR '
            'conservation OR pollution OR waste OR erosion OR weather OR renewable) when:2d',
            region="MV",
            language="en",
        ),
        "🇲🇻 Maldives Ocean & Reef EN — Broad": bot.google_news_feed(
            'Maldives (ocean OR marine OR coral OR reef OR bleaching OR seagrass OR mangrove '
            'OR coastal OR erosion) when:3d',
            region="MV",
            language="en",
        ),
        "🇲🇻 Maldives Weather & Climate EN": bot.google_news_feed(
            'Maldives (weather OR rainfall OR flood OR swell OR wind OR storm OR heat '
            'OR climate OR monsoon) when:2d',
            region="MV",
            language="en",
        ),
        "🇲🇻 Maldives Policy & Research EN": bot.google_news_feed(
            'Maldives (environment ministry OR climate policy OR climate finance OR protected area '
            'OR environmental study OR marine research OR reef monitoring) when:7d',
            region="MV",
            language="en",
        ),
        "🇲🇻 ރާއްޖޭގެ ތިމާވެށި — ދިވެހި": bot.google_news_feed(
            'ދިވެހިރާއްޖެ (ތިމާވެށި OR ކްލައިމެޓް OR ކަނޑު OR ފަރު OR ކޮރަލް) when:3d',
            region="MV",
            language="dv",
        ),
        "🇲🇻 ރާއްޖޭގެ ކަނޑާއި ފަރު — ދިވެހި": bot.google_news_feed(
            'ރާއްޖެ (ކަނޑު OR ފަރު OR ކޮރަލް OR މޫދު OR ވެލާ OR މަސް) when:3d',
            region="MV",
            language="dv",
        ),
        "🇲🇻 ރާއްޖޭގެ ކުނި އަދި ޕްލާސްޓިކް": bot.google_news_feed(
            'ރާއްޖެ (ކުނި OR ޕްލާސްޓިކް OR ތިމާވެށި) when:3d',
            region="MV",
            language="dv",
        ),
        "🇲🇻 ރާއްޖޭގެ މޫސުން އަދި ކާރިސާ": bot.google_news_feed(
            'ރާއްޖެ (ވާރޭ OR ވައި OR މޫސުން OR ފެންބޮޑުވުން OR ކާރިސާ) when:2d',
            region="MV",
            language="dv",
        ),
    }
)

bot.GLOBAL_GOOGLE_FEEDS.update(
    {
        "🌍 Global Climate Science Plus": bot.google_news_feed(
            '(climate science OR global warming OR greenhouse gases OR sea level rise '
            'OR climate attribution) when:12h',
            region="US",
        ),
        "🌊 Global Coral & Ocean Heat": bot.google_news_feed(
            '(coral bleaching OR marine heatwave OR ocean warming OR ocean acidification '
            'OR coral reef watch) when:12h',
            region="US",
        ),
        "🌍 NOAA Climate & Ocean": bot.google_news_feed(
            '(NOAA climate OR NOAA ocean OR NOAA coral OR NOAA marine heatwave) when:24h',
            region="US",
        ),
        "🌍 UNEP Environment": bot.google_news_feed(
            '(UNEP pollution OR UNEP biodiversity OR UNEP climate OR UNEP environment) when:24h',
            region="US",
        ),
        "🌍 IPCC & Climate Assessment": bot.google_news_feed(
            '(IPCC OR climate assessment) (warming OR emissions OR adaptation OR impacts) when:3d',
            region="US",
        ),
        "🌍 Copernicus Climate & Ocean": bot.google_news_feed(
            '(Copernicus climate OR Copernicus ocean OR Copernicus temperature) when:24h',
            region="US",
        ),
        "🌍 Reuters Environment": bot.google_news_feed(
            'site:reuters.com (climate OR environment OR biodiversity OR ocean OR renewable energy) when:24h',
            region="US",
        ),
        "🌍 AP Climate & Environment": bot.google_news_feed(
            'site:apnews.com (climate OR environment OR wildlife OR ocean OR pollution) when:24h',
            region="US",
        ),
        "🌳 Global Mangroves & Blue Carbon": bot.google_news_feed(
            '(mangrove OR blue carbon OR seagrass) (restoration OR conservation OR climate) when:24h',
            region="US",
        ),
        "🔬 Global Environmental Research": bot.google_news_feed(
            '(new study OR researchers OR scientists) (climate OR coral reef OR biodiversity '
            'OR ocean OR pollution) when:24h',
            region="US",
        ),
    }
)

# Broaden Dhivehi recognition while keeping environmental filtering strict.
_DHIVEHI_GENERAL = {
    "މޫސުން", "ވާރޭ", "ވައި", "ކާރިސާ", "ތިމާވެށީގެ",
    "ރައްކާތެރިކުރުން", "ކަނޑުގެ", "ފަރުގެ", "ކުނިމަދުކުރުން",
}
_DHIVEHI_WEATHER = {"މޫސުން", "ވާރޭ", "ވައި", "ކާރިސާ", "ފެންބޮޑުވުން"}
_DHIVEHI_OCEAN = {"ކަނޑު", "މޫދު", "ފަރު", "ކޮރަލް", "ވެލާ", "މަސް"}

bot.GENERAL_ENVIRONMENT_KEYWORDS |= _DHIVEHI_GENERAL
bot.EXTREME_WEATHER_KEYWORDS |= _DHIVEHI_WEATHER
bot.OCEAN_REEF_KEYWORDS |= _DHIVEHI_OCEAN
bot.ALL_TOPIC_KEYWORDS = (
    bot.CLIMATE_KEYWORDS
    | bot.OCEAN_REEF_KEYWORDS
    | bot.BIODIVERSITY_KEYWORDS
    | bot.POLLUTION_WASTE_KEYWORDS
    | bot.CONSERVATION_KEYWORDS
    | bot.FOREST_KEYWORDS
    | bot.CLEAN_ENERGY_KEYWORDS
    | bot.EXTREME_WEATHER_KEYWORDS
    | bot.SCIENCE_KEYWORDS
    | bot.POLICY_KEYWORDS
    | bot.GENERAL_ENVIRONMENT_KEYWORDS
)


# ============================================================
# SIMPLE MAIN MENU + TOPIC MENU
# ============================================================

def main_keyboard():
    return {
        "keyboard": [
            [
                {"text": "🇲🇻 Maldives"},
                {"text": "🌍 Global"},
                {"text": "🚨 Important"},
            ],
            [{"text": "🧭 Related Topics"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose news or browse related topics...",
    }


def topic_keyboard():
    return {
        "keyboard": [
            [{"text": "🪸 Reefs & Oceans"}, {"text": "🚨 Weather"}],
            [{"text": "🦋 Wildlife"}, {"text": "♻️ Pollution"}],
            [{"text": "🌱 Conservation"}, {"text": "⚡ Clean Energy"}],
            [{"text": "🌡️ Climate"}, {"text": "🏛️ Policy"}],
            [{"text": "🔬 Research"}, {"text": "🏝️ Baa Atoll"}],
            [{"text": "⬅️ Main Menu"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose a related climate/environment topic...",
    }


bot.PUBLIC_COMMANDS = [
    {"command": "maldives", "description": "Maldives climate & environment news"},
    {"command": "global", "description": "Global climate & environment news"},
    {"command": "important", "description": "Highest-priority environment news"},
    {"command": "topics", "description": "Browse related climate/environment topics"},
]


# ============================================================
# STORY LISTS
# ============================================================

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

    if len(priority) < limit:
        selected = {id(story) for story in priority}
        priority.extend(story for story in stories if id(story) not in selected)

    return priority[:limit]


def story_text(story):
    return " ".join(
        [
            str(story.get("headline", "")),
            " ".join(story.get("summary", []) or []),
            str(story.get("category", "")),
            str(story.get("location", "")),
            " ".join(story.get("publishers", []) or []),
            str(story.get("reef_relevance", "")),
        ]
    ).lower()


def topic_news(topic, limit=12, hours=24 * 14):
    stories = list(bot.recent_history(hours))

    def matches(story):
        category = story.get("category", "")
        text = story_text(story)

        if topic == "reefs":
            return category == "Oceans & Reefs" or story.get("reef_relevance") == "Direct" or any(
                term in text for term in {"coral", "reef", "ocean", "marine", "bleaching", "seagrass", "mangrove"}
            )
        if topic == "weather":
            return category == "Extreme Weather" or any(
                term in text for term in {"storm", "flood", "rain", "swell", "wind", "cyclone", "weather", "heatwave"}
            )
        if topic == "wildlife":
            return category == "Biodiversity & Wildlife"
        if topic == "pollution":
            return category == "Pollution & Waste"
        if topic == "conservation":
            return category in {"Conservation & Restoration", "Forests & Mangroves"}
        if topic == "energy":
            return category == "Clean Energy"
        if topic == "climate":
            return category == "Climate Change"
        if topic == "policy":
            return category == "Climate Policy & Finance"
        if topic == "research":
            return category == "Science & Research" or any(term in text for term in {"study", "research", "scientist", "monitoring"})
        if topic == "baa":
            return any(marker in text for marker in intelligence.BAA_MARKERS)
        return False

    matches_list = [story for story in stories if matches(story)]
    matches_list.sort(
        key=lambda item: (
            max(safe_int(item.get("trending_score")), safe_int(item.get("importance_score"))),
            item.get("created_at", ""),
        ),
        reverse=True,
    )
    return matches_list[:limit]


def safe_story_list(title, stories, limit=12):
    """Build Telegram-safe HTML without cutting through a link or HTML tag."""
    title_html = html.escape(str(title))

    if not stories:
        return (
            f"🌿 <b>{title_html}</b>\n\n"
            "No matching climate or environmental stories are stored yet. "
            "The bot is still monitoring English and Dhivehi Maldives sources plus global feeds."
        )

    message = f"🌿 <b>{title_html}</b>\n\n"
    shown = 0

    for index, story in enumerate(stories[:limit], start=1):
        category = story.get("category", "Environment")
        emoji = bot.CATEGORY_EMOJIS.get(category, "🌍")
        headline = html.escape(str(story.get("headline", "Untitled report")))
        link = str(story.get("link", "") or "").strip()
        region = "🇲🇻" if story.get("maldives") else "🌍"
        language = "DV" if story.get("dhivehi") else "EN"
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
            f"   🌐 {language} · 📍 {location} · ⚠️ {severity} · 📊 {score}/100\n\n"
        )

        if len(message) + len(block) > 3650:
            break

        message += block
        shown += 1

    if shown == 0:
        return f"🌿 <b>{title_html}</b>\n\nStories were found, but none could be formatted safely."

    return message.rstrip()


# ============================================================
# BALANCED AUTOMATIC GROUP PUBLISHING
# ============================================================

async def balanced_check_and_publish_news():
    bot.logging.info("Collecting expanded Maldives + global climate/environment news...")

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

        # No chat_id is passed here: automatic news stays in GROUP_CHAT_ID.
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
        "Completed expanded balanced cycle: %s posts, %s AI requests.",
        posted_count,
        ai_used_this_check,
    )


bot.check_and_publish_news = balanced_check_and_publish_news


# ============================================================
# PRIVATE USER RESPONSES
# ============================================================

def request_destination(message):
    chat = message.get("chat", {}) or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type", "private")
    sender_id = (message.get("from", {}) or {}).get("id")

    if chat_type in {"group", "supergroup"} and sender_id:
        return sender_id, chat_id, True
    return chat_id, chat_id, False


def send_user_result(message, text, reply_markup=None):
    destination, origin_chat_id, came_from_group = request_destination(message)
    if destination is None:
        return None

    result = bot.send_message(text, destination, reply_markup=reply_markup or main_keyboard())
    if result:
        return result

    if came_from_group:
        # Telegram does not let bots initiate a private chat with a user who has
        # never opened the bot. Give a small group-side instruction only then.
        bot.send_message(
            "📩 <b>I couldn't message you privately yet.</b>\n\n"
            "Open my bot profile, press <b>Start</b> once, then use the buttons again. "
            "After that, your requested news will be sent privately.",
            origin_chat_id,
            reply_markup=main_keyboard(),
        )
    return None


TOPIC_BUTTONS = {
    "🪸 Reefs & Oceans": ("reefs", "Reefs & Oceans"),
    "🚨 Weather": ("weather", "Extreme Weather & Coastal Hazards"),
    "🦋 Wildlife": ("wildlife", "Biodiversity & Wildlife"),
    "♻️ Pollution": ("pollution", "Pollution & Waste"),
    "🌱 Conservation": ("conservation", "Conservation & Restoration"),
    "⚡ Clean Energy": ("energy", "Clean Energy"),
    "🌡️ Climate": ("climate", "Climate Change"),
    "🏛️ Policy": ("policy", "Climate Policy & Finance"),
    "🔬 Research": ("research", "Environmental Research & Monitoring"),
    "🏝️ Baa Atoll": ("baa", "Baa Atoll Environment & Reef Watch"),
}


_base_handle_command = bot.handle_command


def private_handle_command(message):
    text = message.get("text", "").strip()
    command = (
        text.split(maxsplit=1)[0].split("@")[0].lower()
        if text.startswith("/")
        else ""
    )

    try:
        if command == "/start":
            send_user_result(message, private_welcome(), main_keyboard())
            return

        if text == "🇲🇻 Maldives" or command == "/maldives":
            stories = [story for story in all_recent_news() if story.get("maldives")][:12]
            send_user_result(
                message,
                safe_story_list("Maldives Climate & Environment — English + Dhivehi", stories),
                main_keyboard(),
            )
            return

        if text == "🌍 Global" or command == "/global":
            stories = [story for story in all_recent_news() if not story.get("maldives")][:12]
            send_user_result(
                message,
                safe_story_list("Global Climate & Environment", stories),
                main_keyboard(),
            )
            return

        if text == "🚨 Important" or command in {"/important", "/trending"}:
            send_user_result(
                message,
                safe_story_list("Important Climate & Environment News", important_news(limit=12)),
                main_keyboard(),
            )
            return

        if text == "🧭 Related Topics" or command == "/topics":
            send_user_result(
                message,
                "🧭 <b>Related Topics</b>\n\nChoose a climate or environmental topic below. "
                "Results will stay in your private chat.",
                topic_keyboard(),
            )
            return

        if text == "⬅️ Main Menu":
            send_user_result(message, private_welcome(), main_keyboard())
            return

        if text in TOPIC_BUTTONS:
            topic_key, title = TOPIC_BUTTONS[text]
            send_user_result(
                message,
                safe_story_list(title, topic_news(topic_key)),
                topic_keyboard(),
            )
            return

        # Preserve useful hidden commands such as /search, /status and
        # /checknow. In a private chat they work normally. In a group, the main
        # browsing requests above are kept private while legacy admin/utility
        # commands retain their existing behavior.
        _base_handle_command(message)

    except Exception as error:
        bot.logging.exception("Private command failed for %r: %s", text, error)
        send_user_result(
            message,
            "⚠️ <b>Could not load this request.</b>\n\n"
            "The bot is still monitoring the news. Please try again after the next fetch.",
            main_keyboard(),
        )


bot.public_command_keyboard = main_keyboard
bot.handle_command = private_handle_command


def private_welcome():
    return f"""
🌿 <b>{bot.BOT_NAME}</b>

Automatic climate/environment news continues in the group.
Your button requests are delivered here privately.

🇲🇻 <b>Maldives</b> — English + Dhivehi environmental news
🌍 <b>Global</b> — expanded worldwide climate/environment coverage
🚨 <b>Important</b> — highest-priority stories from both
🧭 <b>Related Topics</b> — reefs, weather, wildlife, pollution, conservation, energy, policy, research, climate and Baa Atoll

Choose a button below.
""".strip()


bot.build_welcome_message = private_welcome


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
