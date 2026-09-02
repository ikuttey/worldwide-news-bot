"""Railway entry point for the Maldives + global climate/environment Telegram bot.

This wrapper keeps the core news logic in main.py, refreshes Telegram's
persistent keyboard, strengthens RSS collection, widens climate relevance for
real-world terms such as El Nino and high sea temperatures, and exposes simple
fetch diagnostics through /status and /checknow.
"""

import asyncio
import threading
import time

import main as bot


# ============================================================
# CLIMATE TOPIC HARDENING
# ============================================================

# Important climate/environment phrases that were missing from the first
# climate-only version. These are common in Maldives MET and reef reporting.
EXTRA_CLIMATE_KEYWORDS = {
    "el nino", "el niño", "la nina", "la niña",
    "sea surface temperature", "sea surface temperatures",
    "sea temperature", "sea temperatures", "ocean temperature",
    "ocean temperatures", "above average temperature",
    "above-average temperature", "high temperature", "high temperatures",
    "record temperature", "record temperatures", "heat stress",
    "thermal stress", "warming seas", "warming sea", "warming waters",
    "climate risk", "climate risks", "climate impact", "climate impacts",
}

EXTRA_WEATHER_KEYWORDS = {
    "heavy rain", "heavy rainfall", "torrential rain", "torrential rainfall",
    "rough sea", "rough seas", "high swell", "high swells", "swell waves",
    "strong wind", "strong winds", "weather warning", "met office",
    "meteorological service", "coastal hazard", "coastal hazards",
}

EXTRA_OCEAN_KEYWORDS = {
    "reef damage", "reef health", "reef monitoring", "coral mortality",
    "coral recovery", "coral cover", "bleaching event", "bleaching events",
    "marine biodiversity", "ocean heat", "ocean heat content",
}

bot.CLIMATE_KEYWORDS |= EXTRA_CLIMATE_KEYWORDS
bot.EXTREME_WEATHER_KEYWORDS |= EXTRA_WEATHER_KEYWORDS
bot.OCEAN_REEF_KEYWORDS |= EXTRA_OCEAN_KEYWORDS
bot.STRONG_ENVIRONMENT_PHRASES |= {
    "el nino", "el niño", "sea surface temperature", "sea temperatures",
    "warming seas", "heat stress", "thermal stress", "coral mortality",
    "reef monitoring", "heavy rainfall", "rough seas", "weather warning",
}

# Rebuild the combined keyword set after extending the individual sets.
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
# RELIABLE NEWS SOURCES
# ============================================================

# Direct feeds are supplemental. Google News searches are the primary Maldives
# discovery layer because several local publishers do not expose a stable RSS
# endpoint. Use a widely-supported Google News locale while keeping "Maldives"
# inside every local query.
bot.MALDIVES_RSS_FEEDS = {
    "🇲🇻 Sun Online": "https://sun.mv/news/rss",
}

bot.MALDIVES_GOOGLE_FEEDS = {
    "🇲🇻 Maldives Climate": bot.google_news_feed(
        'Maldives "climate change" when:7d', region="US", language="en"
    ),
    "🇲🇻 Maldives El Nino": bot.google_news_feed(
        'Maldives ("El Nino" OR "El Niño") when:7d', region="US", language="en"
    ),
    "🇲🇻 Maldives Environment": bot.google_news_feed(
        'Maldives environment conservation biodiversity when:7d', region="US", language="en"
    ),
    "🇲🇻 Maldives Coral & Reefs": bot.google_news_feed(
        'Maldives (coral OR reef OR bleaching) when:7d', region="US", language="en"
    ),
    "🇲🇻 Maldives Ocean & Marine": bot.google_news_feed(
        'Maldives (ocean OR marine OR seagrass OR mangrove) when:7d', region="US", language="en"
    ),
    "🇲🇻 Maldives Weather & Swell": bot.google_news_feed(
        'Maldives ("heavy rain" OR "rough seas" OR swell OR heat OR weather) when:7d',
        region="US",
        language="en",
    ),
    "🇲🇻 Maldives Pollution & Waste": bot.google_news_feed(
        'Maldives (pollution OR plastic OR waste OR sewage) when:7d', region="US", language="en"
    ),
    "🇲🇻 Maldives Clean Energy": bot.google_news_feed(
        'Maldives ("renewable energy" OR solar OR "clean energy") when:7d',
        region="US",
        language="en",
    ),
    "🇲🇻 Edition Environment": bot.google_news_feed(
        'site:edition.mv Maldives (climate OR environment OR coral OR reef OR "El Nino") when:7d',
        region="US",
        language="en",
    ),
    "🇲🇻 Adhadhu Environment": bot.google_news_feed(
        'site:adhadhu.com Maldives (climate OR environment OR coral OR reef OR "El Nino") when:7d',
        region="US",
        language="en",
    ),
    "🇲🇻 PSM Environment": bot.google_news_feed(
        'site:psmnews.mv Maldives (climate OR environment OR coral OR reef OR renewable) when:7d',
        region="US",
        language="en",
    ),
    "🇲🇻 Atoll Times Environment": bot.google_news_feed(
        'site:atolltimes.mv Maldives (climate OR environment OR coral OR reef OR bleaching) when:14d',
        region="US",
        language="en",
    ),
}

bot.GLOBAL_ENVIRONMENT_RSS = {
    "🌍 BBC Science & Environment": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "🌍 The Guardian Environment": "https://www.theguardian.com/environment/rss",
    "🌍 Mongabay": "https://news.mongabay.com/feed/",
    "🌍 Carbon Brief": "https://www.carbonbrief.org/feed/",
    "🌍 Inside Climate News": "https://insideclimatenews.org/feed/",
}

bot.GLOBAL_GOOGLE_FEEDS = {
    "🌍 Global Climate": bot.google_news_feed(
        '"climate change" OR "global warming" OR "climate crisis" when:2d',
        region="US",
        language="en",
    ),
    "🌊 Global Coral & Reefs": bot.google_news_feed(
        '"coral bleaching" OR "coral reef" OR "reef restoration" when:3d',
        region="US",
        language="en",
    ),
    "🌊 Global Oceans": bot.google_news_feed(
        '"ocean warming" OR "marine heatwave" OR "ocean acidification" when:3d',
        region="US",
        language="en",
    ),
    "🦋 Global Biodiversity": bot.google_news_feed(
        'biodiversity wildlife conservation extinction when:2d',
        region="US",
        language="en",
    ),
    "♻️ Global Pollution & Waste": bot.google_news_feed(
        'pollution plastic waste microplastics when:2d',
        region="US",
        language="en",
    ),
    "🌳 Global Forests": bot.google_news_feed(
        'deforestation rainforest mangrove wildfire when:2d',
        region="US",
        language="en",
    ),
    "⚡ Global Clean Energy": bot.google_news_feed(
        '"renewable energy" OR solar OR wind OR "energy transition" when:2d',
        region="US",
        language="en",
    ),
    "🚨 Global Extreme Weather": bot.google_news_feed(
        'heatwave wildfire drought flood cyclone hurricane when:2d',
        region="US",
        language="en",
    ),
    "🏛️ Global Climate Policy": bot.google_news_feed(
        '"climate policy" OR "Paris Agreement" OR "climate finance" OR COP31 when:3d',
        region="US",
        language="en",
    ),
}


# ============================================================
# FETCHING + DIAGNOSTICS
# ============================================================

TARGETED_SOURCE_MARKERS = {
    "climate", "environment", "el nino", "coral", "reef", "ocean",
    "marine", "weather", "swell", "pollution", "waste", "clean energy",
    "biodiversity", "forests", "global", "edition", "adhadhu", "psm",
    "atoll times", "bbc science", "guardian environment", "mongabay",
    "carbon brief", "inside climate",
}


def climate_environment_story(article):
    """More practical relevance gate for targeted environment feeds."""
    text = bot.article_content_text(article)

    if any(phrase in text for phrase in bot.STRONG_ENVIRONMENT_PHRASES):
        return True

    topic_hits = bot.count_keyword_hits(text, bot.ALL_TOPIC_KEYWORDS)
    source = article.get("source", "").lower()
    targeted_source = any(marker in source for marker in TARGETED_SOURCE_MARKERS)

    # Targeted feeds already constrain the subject, so one explicit climate /
    # environment signal is sufficient. Broad local RSS still needs two.
    if targeted_source and topic_hits >= 1:
        return True

    return topic_hits >= 2


bot.is_environment_story = climate_environment_story


def diagnostic_download_rss_feed(source_name, feed_url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/126 Safari/537.36 ClimateEnvironmentNewsBot/2.0"
        ),
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    last_error = None

    for attempt in range(1, 3):
        try:
            response = bot.requests.get(
                feed_url,
                headers=headers,
                timeout=25,
                allow_redirects=True,
            )

            if response.status_code != 200:
                last_error = f"HTTP {response.status_code}"
                if attempt < 2:
                    time.sleep(1)
                    continue
                break

            parsed = bot.feedparser.parse(response.content)
            entries = list(getattr(parsed, "entries", []) or [])

            if entries:
                return parsed, None

            last_error = "feed returned no entries"

        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"

        if attempt < 2:
            time.sleep(1)

    bot.logging.warning("Feed failed — %s: %s", source_name, last_error)
    return None, last_error or "unknown feed error"


def diagnostic_fetch_new_articles():
    seen_ids = set(bot.state.get("seen_ids", []))
    collected_articles = []

    all_feeds = {
        **bot.MALDIVES_RSS_FEEDS,
        **bot.MALDIVES_GOOGLE_FEEDS,
        **bot.GLOBAL_ENVIRONMENT_RSS,
        **bot.GLOBAL_GOOGLE_FEEDS,
    }

    ordered_feeds = sorted(
        all_feeds.items(),
        key=lambda item: (0 if "🇲🇻" in item[0] else 1, item[0]),
    )

    stats = {
        "started_at": bot.utc_now_iso(),
        "feeds_total": len(ordered_feeds),
        "feeds_ok": 0,
        "feeds_failed": 0,
        "entries_seen": 0,
        "duplicates": 0,
        "rejected": 0,
        "new_relevant": 0,
        "source_counts": {},
        "errors": [],
    }

    for source_name, feed_url in ordered_feeds:
        feed, error = diagnostic_download_rss_feed(source_name, feed_url)

        if not feed:
            stats["feeds_failed"] += 1
            if len(stats["errors"]) < 8:
                stats["errors"].append(f"{source_name}: {error}")
            continue

        stats["feeds_ok"] += 1
        entries = list(getattr(feed, "entries", []) or [])
        max_entries = 20 if "🇲🇻" in source_name else 12

        bot.logging.info("Feed OK — %s: %s entries", source_name, len(entries))

        for entry in entries[:max_entries]:
            stats["entries_seen"] += 1
            article = bot.parse_rss_entry(source_name, entry)

            if not article:
                continue

            if article["id"] in seen_ids:
                stats["duplicates"] += 1
                continue

            if not bot.is_environment_story(article):
                stats["rejected"] += 1
                continue

            # Mark relevant articles as seen. This prevents duplicate posting
            # across the 5-minute polling cycle while allowing previously
            # rejected articles to be reconsidered if filtering improves.
            bot.state.setdefault("seen_ids", []).append(article["id"])
            seen_ids.add(article["id"])
            collected_articles.append(article)
            stats["new_relevant"] += 1
            stats["source_counts"][source_name] = (
                stats["source_counts"].get(source_name, 0) + 1
            )

    stats["completed_at"] = bot.utc_now_iso()
    bot.state["last_fetch_stats"] = stats
    bot.save_state()

    bot.logging.info(
        "Fetch summary: %s/%s feeds OK, %s entries inspected, %s relevant, %s rejected, %s duplicates.",
        stats["feeds_ok"],
        stats["feeds_total"],
        stats["entries_seen"],
        stats["new_relevant"],
        stats["rejected"],
        stats["duplicates"],
    )

    return collected_articles


bot.fetch_new_articles = diagnostic_fetch_new_articles


def build_fetch_status():
    stats = bot.state.get("last_fetch_stats") or {}

    if not stats:
        return (
            "📡 <b>Fetch status</b>\n\n"
            "No completed news fetch has been recorded yet. Use /checknow."
        )

    source_counts = stats.get("source_counts", {})
    top_sources = sorted(source_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    source_text = "\n".join(
        f"• {bot.html.escape(name)}: {count}" for name, count in top_sources
    ) or "• No new relevant source items in the latest cycle"

    errors = stats.get("errors", [])[:4]
    error_text = ""
    if errors:
        error_text = "\n\n⚠️ <b>Feed issues:</b>\n" + "\n".join(
            f"• {bot.html.escape(item)}" for item in errors
        )

    return (
        "📡 <b>Climate News Fetch Status</b>\n\n"
        f"✅ Feeds working: {stats.get('feeds_ok', 0)}/{stats.get('feeds_total', 0)}\n"
        f"❌ Feeds failed: {stats.get('feeds_failed', 0)}\n"
        f"📰 Entries inspected: {stats.get('entries_seen', 0)}\n"
        f"🌿 New relevant stories: {stats.get('new_relevant', 0)}\n"
        f"🚫 Rejected as unrelated: {stats.get('rejected', 0)}\n"
        f"♻️ Already seen: {stats.get('duplicates', 0)}\n"
        f"🕐 Last fetch: {bot.html.escape(str(stats.get('completed_at', 'unknown')))}\n\n"
        f"<b>Top sources this cycle:</b>\n{source_text}"
        f"{error_text}"
    )


# ============================================================
# TELEGRAM MENU
# ============================================================

LEGACY_BUTTONS = {
    "📰 Latest News",
    "🌍 World",
    "💻 Technology",
    "💰 Business",
    "⚽ Sports",
    "🌊 Environment",
}


def climate_command_keyboard():
    return {
        "keyboard": [
            [{"text": "📰 Latest"}, {"text": "🔥 Trending"}],
            [{"text": "🇲🇻 Maldives"}, {"text": "🌍 Global"}],
            [{"text": "🌡️ Climate"}, {"text": "🌊 Oceans & Reefs"}],
            [{"text": "🦋 Wildlife"}, {"text": "♻️ Pollution & Waste"}],
            [{"text": "🌱 Conservation"}, {"text": "⚡ Clean Energy"}],
            [{"text": "🔬 Research"}, {"text": "📡 Fetch Status"}],
            [{"text": "🔄 Check News Now"}, {"text": "🔄 Refresh Menu"}],
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
    {"command": "checknow", "description": "Fetch climate news immediately"},
    {"command": "status", "description": "Show feed and fetch status"},
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

This bot is dedicated to climate and environmental news from the Maldives and around the world.

🇲🇻 <b>Maldives</b> — local climate and environmental updates
🌍 <b>Global</b> — international climate and environmental news
🌡️ <b>Climate</b> — climate change, El Niño and extreme weather
🌊 <b>Oceans & Reefs</b> — coral reefs, oceans and marine ecosystems
🦋 <b>Wildlife</b> — biodiversity and wildlife
♻️ <b>Pollution & Waste</b> — plastics, pollution and waste
🌱 <b>Conservation</b> — conservation, restoration, forests and mangroves
⚡ <b>Clean Energy</b> — renewable energy and energy transition
🔬 <b>Research</b> — environmental science and monitoring

📡 <b>Fetch Status</b> shows whether news sources are responding.
🔄 <b>Check News Now</b> runs an immediate news check.

Use <code>/menu</code> to refresh the buttons.
Use <code>/search coral bleaching</code> to search recent stories.
""".strip()


def climate_welcome_message():
    return f"""
🌿 <b>{bot.BOT_NAME}</b>

✅ Climate/environment mode is active.
✅ Improved Maldives and global news fetching is active.
✅ El Niño, reef heat stress, weather warnings and sea-temperature stories are included.

Tap <b>🔄 Check News Now</b> to test fetching immediately, or <b>📡 Fetch Status</b> to see source diagnostics.
""".strip()


_original_handle_command = bot.handle_command
_check_lock = threading.Lock()


def climate_handle_command(message):
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")
    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else ""

    if text in LEGACY_BUTTONS:
        bot.send_message(
            "🌿 <b>The news menu has changed.</b>\n\n"
            "This bot now covers only climate and environmental news.",
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

    if text == "📡 Fetch Status" or command == "/status":
        bot.send_message(
            build_fetch_status(),
            chat_id,
            reply_markup=climate_command_keyboard(),
        )
        return

    if text == "🔄 Check News Now" or command == "/checknow":
        if not _check_lock.acquire(blocking=False):
            bot.send_message(
                "⏳ A manual news check is already running. Please wait a moment.",
                chat_id,
            )
            return

        try:
            bot.send_message(
                "🔎 <b>Checking climate and environmental news now...</b>\n"
                "This can take up to about a minute because several sources are checked.",
                chat_id,
            )
            asyncio.run(bot.check_and_publish_news())
            bot.send_message(
                build_fetch_status(),
                chat_id,
                reply_markup=climate_command_keyboard(),
            )
        except Exception as error:
            bot.logging.exception("Manual news check failed: %s", error)
            bot.send_message(
                "❌ <b>Manual news check failed.</b>\n\n"
                f"Error: <code>{bot.html.escape(str(error))}</code>",
                chat_id,
                reply_markup=climate_command_keyboard(),
            )
        finally:
            _check_lock.release()
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


# Replace menu-facing and fetch functions before main.main() starts.
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
