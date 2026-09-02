"""Climate intelligence entry point for the Maldives + global Telegram bot.

Keeps Telegram authentication/configuration in main.py unchanged while adding:
- richer climate/environment analysis and post formatting
- Baa Atoll and reef-focused discovery
- Maldives relevance, severity, evidence and field relevance
- dedicated Baa Atoll, Reef Watch, Extreme Weather and Climate Policy commands
- optional local Ollama AI with no per-request API token billing

The existing Gemini integration remains available as the fallback AI path.
"""

import asyncio
import html as html_module
import json
import os
import re

import bot_runner as runner

bot = runner.bot


# ============================================================
# OPTIONAL LOCAL AI
# ============================================================

# This does not replace or alter the existing Telegram/Gemini variables.
# If OLLAMA_BASE_URL is unset, the bot simply keeps using the existing Gemini
# path when Gemini is configured, otherwise it uses deterministic local logic.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b").strip()
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))


# ============================================================
# EXTRA MALDIVES / BAA ATOLL DISCOVERY
# ============================================================

runner.EXTRA_OCEAN_KEYWORDS |= {
    "coral nursery", "coral nurseries", "coral outplanting", "outplanting",
    "coral husbandry", "reef rehabilitation", "reef resilience",
    "degree heating week", "degree heating weeks", "dhw",
    "sea surface temperature anomaly", "sst anomaly", "bleaching alert",
    "reef survey", "reef surveys", "quadrat", "quadrats",
}

bot.OCEAN_REEF_KEYWORDS |= runner.EXTRA_OCEAN_KEYWORDS
bot.STRONG_ENVIRONMENT_PHRASES |= {
    "coral nursery", "coral outplanting", "reef rehabilitation",
    "degree heating weeks", "bleaching alert", "reef survey",
}

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

bot.MALDIVES_GOOGLE_FEEDS.update(
    {
        "🇲🇻 Baa Atoll Environment": bot.google_news_feed(
            '("Baa Atoll" OR Dharavandhoo OR Hanifaru OR Maalhos OR Kamadhoo) '
            '(climate OR environment OR coral OR reef OR marine OR conservation OR erosion) when:14d',
            region="US",
            language="en",
        ),
        "🇲🇻 Maldives Reef Science": bot.google_news_feed(
            'Maldives ("coral bleaching" OR "reef monitoring" OR "coral restoration" '
            'OR "reef restoration" OR "coral nursery") when:14d',
            region="US",
            language="en",
        ),
        "🇲🇻 Maldives Coastal Change": bot.google_news_feed(
            'Maldives (erosion OR reclamation OR dredging OR shoreline OR "coastal flooding") when:7d',
            region="US",
            language="en",
        ),
        "🇲🇻 Maldives Climate Policy": bot.google_news_feed(
            'Maldives ("climate policy" OR "climate finance" OR adaptation OR resilience '
            'OR emissions OR "renewable energy") when:14d',
            region="US",
            language="en",
        ),
        "🇲🇻 Maldives Environmental Research": bot.google_news_feed(
            'Maldives (study OR research OR monitoring) '
            '(climate OR coral OR reef OR ocean OR biodiversity OR environment) when:30d',
            region="US",
            language="en",
        ),
        "🌊 Coral Reef Watch News": bot.google_news_feed(
            '("Coral Reef Watch" OR "Degree Heating Weeks" OR "bleaching alert") '
            '(Maldives OR Indian Ocean OR coral) when:14d',
            region="US",
            language="en",
        ),
    }
)


# ============================================================
# INTELLIGENCE HELPERS
# ============================================================

BAA_MARKERS = {
    "baa atoll", "dharavandhoo", "hanifaru", "maalhos", "kamadhoo",
    "kihaadhoo", "kendhoo", "kudarikilu", "thulhaadhoo", "eydhafushi",
    "goidhoo", "fulhadhoo", "fehendhoo",
}

OFFICIAL_SCIENCE_MARKERS = {
    "noaa", "nasa", "unep", "unfccc", "ipcc", "meteorological",
    "environment ministry", "ministry", "government", "university",
    "research institute", "coral reef watch", "carbon brief",
}

REEF_TERMS = {
    "coral", "reef", "bleaching", "marine heatwave", "ocean warming",
    "heat stress", "thermal stress", "coral nursery", "outplanting",
    "degree heating", "reef monitoring", "reef restoration",
}

WEATHER_TERMS = {
    "heavy rain", "flood", "flooding", "rough seas", "swell", "storm",
    "cyclone", "weather warning", "strong winds", "coastal flooding",
}

SEASONAL_TERMS = {
    "el nino", "el niño", "la nina", "la niña", "bleaching",
    "marine heatwave", "heat stress", "thermal stress", "monsoon",
}


def cluster_text(cluster):
    parts = []
    for article in cluster.get("articles", [])[:6]:
        parts.extend(
            [
                article.get("title", ""),
                article.get("description", ""),
                article.get("source", ""),
                article.get("publisher", ""),
            ]
        )
    return " ".join(parts).lower()


def detect_location(cluster):
    text = cluster_text(cluster)
    if any(marker in text for marker in BAA_MARKERS):
        return "Baa Atoll, Maldives"
    if cluster.get("articles") and bot.is_maldives_story(cluster["articles"][0]):
        return "Maldives"
    return "Global / international"


def evidence_level(cluster):
    publishers = cluster.get("publishers", set())
    text = cluster_text(cluster)

    if len(publishers) >= 2:
        return "High — multiple reports"
    if any(marker in text for marker in OFFICIAL_SCIENCE_MARKERS):
        return "High — official/specialist source"
    return "Standard — single reported source"


def severity_level(analysis, cluster):
    score = int(analysis.get("importance_score", 0) or 0)
    category = analysis.get("category", "Environment")

    if analysis.get("breaking") and score >= 90:
        return "Critical"
    if analysis.get("breaking") or score >= 82:
        return "High"
    if score >= 65 or category in {"Extreme Weather", "Climate Change"}:
        return "Moderate"
    return "Watch"


def reef_relevance(cluster, analysis):
    text = cluster_text(cluster)
    category = analysis.get("category", "Environment")

    if category == "Oceans & Reefs" or any(term in text for term in REEF_TERMS):
        return "Direct"
    if category in {"Climate Change", "Extreme Weather", "Pollution & Waste", "Biodiversity & Wildlife"}:
        return "Indirect"
    return "Low"


def time_horizon(cluster, analysis):
    text = cluster_text(cluster)
    category = analysis.get("category", "Environment")

    if analysis.get("breaking") or category == "Extreme Weather" or any(term in text for term in WEATHER_TERMS):
        return "Immediate / days"
    if any(term in text for term in SEASONAL_TERMS):
        return "Seasonal / weeks to months"
    if category in {"Climate Change", "Climate Policy & Finance", "Clean Energy"}:
        return "Long-term"
    return "Current development"


def maldives_relevance(cluster, analysis, location):
    category = analysis.get("category", "Environment")

    if location.startswith("Baa Atoll"):
        return (
            "Directly relevant to Baa Atoll's reefs, island communities, tourism, "
            "marine biodiversity and conservation monitoring."
        )
    if location == "Maldives":
        return "Direct national relevance for Maldives environment, communities or climate resilience."
    if category == "Oceans & Reefs":
        return (
            "Relevant to Maldives because coral reefs and ocean health support coastal protection, "
            "biodiversity, fisheries and tourism."
        )
    if category in {"Climate Change", "Extreme Weather"}:
        return (
            "Relevant to low-lying islands through heat, changing ocean conditions, sea-level and "
            "extreme-weather risks."
        )
    if category == "Pollution & Waste":
        return "Relevant to island and marine ecosystems where waste and pollution can reach coastal waters."
    if category == "Biodiversity & Wildlife":
        return "Relevant to Maldives marine biodiversity and protected-species conservation."
    if category == "Clean Energy":
        return "Relevant to Maldives energy transition and dependence on imported fossil fuels."
    if category == "Climate Policy & Finance":
        return "Relevant to Maldives adaptation, resilience planning and access to climate finance."
    return "Useful wider environmental context for Maldives conservation and climate work."


def field_note(cluster, analysis, reef_level):
    text = cluster_text(cluster)
    category = analysis.get("category", "Environment")

    if reef_level == "Direct":
        return (
            "Where locally relevant, compare the report with field observations from shallow reefs, "
            "nurseries, outplants and monitored colonies."
        )
    if category == "Extreme Weather" or any(term in text for term in WEATHER_TERMS):
        return "Check official local weather/sea advisories before field activity and note any post-event reef impacts."
    if category == "Pollution & Waste":
        return "Record unusual debris, runoff or pollution observations during routine coastal and reef monitoring."
    if category == "Biodiversity & Wildlife":
        return "Record unusual wildlife observations with date, location and non-disturbing photographic evidence where possible."
    return "No immediate field action suggested; retain the story for trend and context monitoring."


def enrich_analysis(analysis, cluster):
    enriched = dict(analysis or {})
    location = detect_location(cluster)
    reef_level = reef_relevance(cluster, enriched)

    enriched["topic"] = enriched.get("category", "Environment")
    enriched["location"] = enriched.get("location") or location
    enriched["severity"] = enriched.get("severity") or severity_level(enriched, cluster)
    enriched["evidence"] = enriched.get("evidence") or evidence_level(cluster)
    enriched["reef_relevance"] = enriched.get("reef_relevance") or reef_level
    enriched["time_horizon"] = enriched.get("time_horizon") or time_horizon(cluster, enriched)
    enriched["maldives_relevance"] = enriched.get("maldives_relevance") or maldives_relevance(
        cluster, enriched, location
    )
    enriched["field_note"] = enriched.get("field_note") or field_note(cluster, enriched, reef_level)
    enriched["source_count"] = len(cluster.get("publishers", []))
    return enriched


# ============================================================
# AI ANALYSIS
# ============================================================

_base_ai_analysis = bot.analyze_cluster_with_ai
_base_local_analysis = bot.local_cluster_analysis
_base_should_use_ai = bot.should_use_ai


def ollama_analysis(cluster):
    if not OLLAMA_BASE_URL:
        return None

    reports = []
    for index, article in enumerate(cluster.get("articles", [])[:4], start=1):
        reports.append(
            f"Report {index}\n"
            f"Publisher: {article.get('publisher', '')}\n"
            f"Headline: {article.get('title', '')}\n"
            f"Description: {bot.shorten_text(article.get('description', ''), 1200)}"
        )

    prompt = f"""
You are a factual climate and environment editor for a Maldives-focused intelligence channel.
Use only facts explicitly present in the reports. Do not invent measurements, causes, dates, impacts or locations.
Return one JSON object only with:
{{
  "headline": "clear factual headline",
  "summary": ["sentence one", "sentence two"],
  "why_it_matters": "short evidence-based explanation",
  "category": "one allowed category",
  "breaking": false,
  "importance_score": 0,
  "severity": "Watch|Moderate|High|Critical",
  "location": "location supported by the reports or empty string"
}}
Allowed categories: {", ".join(bot.CATEGORY_EMOJIS.keys())}
Reports:\n{chr(10).join(reports)}
""".strip()

    try:
        response = bot.requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        raw = response.json().get("response", "")
        data = bot.extract_json_object(raw)
        if not data:
            return None

        summaries = data.get("summary", [])
        if not isinstance(summaries, list):
            return None
        summaries = [bot.clean_text(item) for item in summaries if bot.clean_text(item)][:2]
        if len(summaries) != 2:
            return None

        category = bot.clean_text(data.get("category", "Environment"))
        if category not in bot.CATEGORY_EMOJIS:
            category = "Environment"

        try:
            importance = int(data.get("importance_score", 75))
        except Exception:
            importance = 75

        return {
            "headline": bot.clean_text(data.get("headline", cluster["articles"][0]["title"])),
            "summary": summaries,
            "why_it_matters": bot.clean_text(data.get("why_it_matters", "")),
            "category": category,
            "breaking": bool(data.get("breaking", False)),
            "importance_score": max(0, min(100, importance)),
            "severity": bot.clean_text(data.get("severity", "")),
            "location": bot.clean_text(data.get("location", "")),
            "used_ai": True,
            "ai_engine": f"local:{OLLAMA_MODEL}",
        }
    except Exception as error:
        bot.logging.warning("Local AI unavailable; falling back: %s", error)
        return None


def intelligence_should_use_ai(cluster, local_score, ai_used_this_check):
    if OLLAMA_BASE_URL:
        if ai_used_this_check >= bot.MAX_AI_REQUESTS_PER_CHECK:
            return False
        first = cluster["articles"][0]
        return (
            local_score >= 65
            or bot.is_maldives_story(first)
            or bot.is_breaking_story(first)
        )
    return _base_should_use_ai(cluster, local_score, ai_used_this_check)


def intelligence_ai_analysis(cluster):
    analysis = ollama_analysis(cluster)
    if not analysis:
        analysis = _base_ai_analysis(cluster)
    if not analysis:
        return None
    return enrich_analysis(analysis, cluster)


def intelligence_local_analysis(cluster, local_score):
    return enrich_analysis(_base_local_analysis(cluster, local_score), cluster)


bot.should_use_ai = intelligence_should_use_ai
bot.analyze_cluster_with_ai = intelligence_ai_analysis
bot.local_cluster_analysis = intelligence_local_analysis


# ============================================================
# RICH POST FORMAT + HISTORY
# ============================================================


def clean_display(value, fallback="—"):
    value = str(value or "").strip()
    return html_module.escape(value if value else fallback)


def intelligence_news_message(cluster, analysis, trend_score):
    category = analysis.get("category", "Environment")
    emoji = bot.CATEGORY_EMOJIS.get(category, "🌍")
    first_article = cluster["articles"][0]
    region = "🇲🇻 Maldives" if bot.is_maldives_story(first_article) else "🌍 Global"
    language = " · Dhivehi" if bot.is_dhivehi_story(first_article) else ""

    if analysis.get("breaking"):
        header = "🚨 <b>CLIMATE / ENVIRONMENT ALERT</b>\n\n"
    elif analysis.get("severity") in {"High", "Critical"}:
        header = "⚠️ <b>HIGH-PRIORITY ENVIRONMENT UPDATE</b>\n\n"
    elif trend_score >= 84:
        header = "🔥 <b>TRENDING ENVIRONMENT STORY</b>\n\n"
    else:
        header = ""

    message = (
        f"{header}"
        f"{emoji} <b>{clean_display(category)}</b> · {region}{language}\n"
        f"📍 <b>Location:</b> {clean_display(analysis.get('location'))}\n"
        f"⚠️ <b>Severity:</b> {clean_display(analysis.get('severity'))}\n"
        f"🔎 <b>Evidence:</b> {clean_display(analysis.get('evidence'))}\n\n"
        f"📰 <b>{clean_display(analysis.get('headline'))}</b>\n\n"
        f"<b>What happened</b>\n"
        f"• {clean_display(analysis.get('summary', [''])[0])}\n"
        f"• {clean_display(analysis.get('summary', ['', ''])[1])}\n"
    )

    why = analysis.get("why_it_matters")
    if why:
        message += f"\n💡 <b>Why it matters</b>\n{clean_display(why)}\n"

    message += (
        f"\n🇲🇻 <b>Maldives relevance</b>\n{clean_display(analysis.get('maldives_relevance'))}\n"
        f"\n🪸 <b>Reef relevance:</b> {clean_display(analysis.get('reef_relevance'))}\n"
        f"⏳ <b>Time horizon:</b> {clean_display(analysis.get('time_horizon'))}\n"
        f"\n📋 <b>Field note</b>\n{clean_display(analysis.get('field_note'))}\n"
    )

    publishers = ", ".join(sorted(cluster.get("publishers", [])))
    message += (
        f"\n📊 <b>Priority score:</b> {trend_score}/100\n"
        f"🏢 <b>Sources:</b> {clean_display(publishers)}\n"
        "👇 Open the original reporting below."
    )

    if len(cluster.get("articles", [])) > 1:
        message += f"\n🧩 Cross-checked across {len(cluster['articles'])} related reports."

    return bot.shorten_text(message, 3900)


def intelligence_publish_post(message, image_url=None, source_buttons=None):
    # Rich intelligence posts usually exceed Telegram photo-caption limits.
    # Keep the complete analysis instead of truncating it to a photo caption.
    if image_url and len(re.sub(r"<[^>]+>", "", message)) < 850:
        result = bot.send_photo(image_url, message, reply_markup=source_buttons)
        if result:
            return result
    return bot.send_message(message, reply_markup=source_buttons)


def intelligence_save_history(cluster, analysis, trend_score):
    first_article = cluster["articles"][0]
    bot.state.setdefault("history", []).append(
        {
            "created_at": bot.utc_now_iso(),
            "headline": analysis.get("headline", first_article.get("title", "")),
            "summary": analysis.get("summary", []),
            "category": analysis.get("category", "Environment"),
            "breaking": analysis.get("breaking", False),
            "importance_score": analysis.get("importance_score", 0),
            "trending_score": trend_score,
            "publishers": sorted(cluster.get("publishers", [])),
            "link": first_article.get("link", ""),
            "maldives": bot.is_maldives_story(first_article),
            "dhivehi": bot.is_dhivehi_story(first_article),
            "used_ai": analysis.get("used_ai", False),
            "location": analysis.get("location", ""),
            "severity": analysis.get("severity", ""),
            "evidence": analysis.get("evidence", ""),
            "reef_relevance": analysis.get("reef_relevance", ""),
            "time_horizon": analysis.get("time_horizon", ""),
            "maldives_relevance": analysis.get("maldives_relevance", ""),
            "field_note": analysis.get("field_note", ""),
        }
    )


bot.build_news_message = intelligence_news_message
bot.publish_post = intelligence_publish_post
bot.save_to_history = intelligence_save_history


# ============================================================
# RICH STORY LISTS
# ============================================================


def story_search_text(story):
    return " ".join(
        [
            story.get("headline", ""),
            " ".join(story.get("summary", [])),
            story.get("category", ""),
            story.get("location", ""),
            " ".join(story.get("publishers", [])),
        ]
    ).lower()


def rich_story_list(title, stories):
    if not stories:
        return f"🌿 <b>{html_module.escape(title)}</b>\n\nNo matching climate or environmental stories are available yet."

    message = f"🌿 <b>{html_module.escape(title)}</b>\n\n"

    for index, story in enumerate(stories[:10], start=1):
        category = story.get("category", "Environment")
        emoji = bot.CATEGORY_EMOJIS.get(category, "🌍")
        headline = html_module.escape(story.get("headline", "Untitled report"))
        link = html_module.escape(story.get("link", ""), quote=True)
        region = "🇲🇻" if story.get("maldives") else "🌍"
        severity = html_module.escape(story.get("severity") or "Watch")
        location = html_module.escape(story.get("location") or ("Maldives" if story.get("maldives") else "Global"))
        reef = html_module.escape(story.get("reef_relevance") or "—")

        message += (
            f'{index}. {region} {emoji} <a href="{link}">{headline}</a>\n'
            f"   📍 {location} · ⚠️ {severity} · 🪸 {reef}\n"
            f"   📊 Priority {story.get('trending_score', 0)}/100\n\n"
        )

    return bot.shorten_text(message, 3900)


bot.build_story_list = rich_story_list


# ============================================================
# TELEGRAM MENU AND COMMANDS
# ============================================================


def intelligence_keyboard():
    return {
        "keyboard": [
            [{"text": "📰 Latest"}, {"text": "🔥 Trending"}],
            [{"text": "🇲🇻 Maldives"}, {"text": "🏝️ Baa Atoll"}],
            [{"text": "🌍 Global"}, {"text": "🌡️ Climate"}],
            [{"text": "🚨 Extreme Weather"}, {"text": "🌊 Oceans & Reefs"}],
            [{"text": "🪸 Reef Watch"}, {"text": "🦋 Wildlife"}],
            [{"text": "♻️ Pollution & Waste"}, {"text": "🌱 Conservation"}],
            [{"text": "⚡ Clean Energy"}, {"text": "🏛️ Climate Policy"}],
            [{"text": "🔬 Research"}, {"text": "📡 Fetch Status"}],
            [{"text": "🔄 Check News Now"}, {"text": "❓ Help"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose a climate intelligence section...",
    }


bot.PUBLIC_COMMANDS = [
    {"command": "help", "description": "Show the climate intelligence menu"},
    {"command": "latest", "description": "Latest climate & environment news"},
    {"command": "trending", "description": "Highest-priority environmental stories"},
    {"command": "maldives", "description": "Maldives climate & environment news"},
    {"command": "baa", "description": "Baa Atoll environment and reef news"},
    {"command": "global", "description": "Global climate & environment news"},
    {"command": "climate", "description": "Climate change news"},
    {"command": "weather", "description": "Extreme weather and coastal hazards"},
    {"command": "oceans", "description": "Oceans, coral reefs and marine news"},
    {"command": "reefwatch", "description": "Reef heat, bleaching and restoration watch"},
    {"command": "wildlife", "description": "Biodiversity and wildlife news"},
    {"command": "pollution", "description": "Pollution, plastics and waste"},
    {"command": "conservation", "description": "Conservation and restoration"},
    {"command": "energy", "description": "Renewable and clean energy"},
    {"command": "policy", "description": "Climate policy and finance"},
    {"command": "research", "description": "Environmental science and monitoring"},
    {"command": "status", "description": "Show feed and fetch status"},
    {"command": "checknow", "description": "Fetch climate news immediately"},
    {"command": "search", "description": "Search recent environmental stories"},
]


bot.HELP_TEXT = f"""
🌿 <b>{bot.BOT_NAME} — Climate Intelligence</b>

The bot now goes beyond headlines. Each new story can include:
📍 location
⚠️ severity
🔎 evidence strength
🇲🇻 Maldives relevance
🪸 reef relevance
⏳ time horizon
📋 field-monitoring note
🔗 original sources

Dedicated monitoring:
🏝️ Baa Atoll
🪸 reef heat, bleaching, restoration and monitoring
🚨 extreme weather and coastal hazards
🏛️ climate policy and finance
🔬 environmental science and research

General politics, sports, entertainment, technology and business remain excluded unless directly related to climate or the environment.

Use <code>/checknow</code> to run a fetch immediately.
Use <code>/status</code> to inspect source health.
Use <code>/search coral bleaching</code> to search recent stories.
""".strip()


def intelligence_welcome():
    ai_mode = (
        f"Local AI enabled ({OLLAMA_MODEL})"
        if OLLAMA_BASE_URL
        else ("Gemini-assisted analysis when configured" if bot.GEMINI_API_KEY else "Local rule-based analysis")
    )
    return f"""
🌿 <b>{bot.BOT_NAME} — Climate Intelligence</b>

✅ Maldives + global climate/environment monitoring
✅ Dedicated Baa Atoll and reef watch
✅ Severity, evidence, Maldives relevance and field context
✅ {html_module.escape(ai_mode)}

Use the menu below or tap <b>🔄 Check News Now</b> for an immediate fetch.
""".strip()


_base_handle_command = bot.handle_command


def recent_matching(predicate, limit=10, hours=168):
    stories = bot.recent_history(hours)
    matches = [story for story in stories if predicate(story)]
    matches.sort(key=lambda item: item.get("trending_score", 0), reverse=True)
    return matches[:limit]


def intelligence_handle_command(message):
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")
    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else ""

    button_map = {
        "🏝️ Baa Atoll": "/baa",
        "🚨 Extreme Weather": "/weather",
        "🪸 Reef Watch": "/reefwatch",
        "🏛️ Climate Policy": "/policy",
    }
    text = button_map.get(text, text)
    if text.startswith("/"):
        command = text.split(maxsplit=1)[0].split("@")[0].lower()

    if command == "/baa":
        stories = recent_matching(
            lambda story: any(marker in story_search_text(story) for marker in BAA_MARKERS),
            limit=10,
            hours=24 * 14,
        )
        bot.send_message(
            rich_story_list("Baa Atoll Climate & Reef Watch", stories),
            chat_id,
            reply_markup=intelligence_keyboard(),
        )
        return

    if command == "/weather":
        stories = recent_matching(
            lambda story: story.get("category") == "Extreme Weather"
            or any(term in story_search_text(story) for term in WEATHER_TERMS),
            limit=10,
        )
        bot.send_message(
            rich_story_list("Extreme Weather & Coastal Hazards", stories),
            chat_id,
            reply_markup=intelligence_keyboard(),
        )
        return

    if command == "/reefwatch":
        stories = recent_matching(
            lambda story: story.get("reef_relevance") == "Direct"
            or story.get("category") == "Oceans & Reefs"
            or any(term in story_search_text(story) for term in REEF_TERMS),
            limit=10,
            hours=24 * 14,
        )
        bot.send_message(
            rich_story_list("Reef Watch — Heat, Bleaching, Restoration & Monitoring", stories),
            chat_id,
            reply_markup=intelligence_keyboard(),
        )
        return

    if command == "/policy":
        stories = recent_matching(
            lambda story: story.get("category") == "Climate Policy & Finance"
            or "climate finance" in story_search_text(story)
            or "climate policy" in story_search_text(story),
            limit=10,
            hours=24 * 14,
        )
        bot.send_message(
            rich_story_list("Climate Policy & Finance", stories),
            chat_id,
            reply_markup=intelligence_keyboard(),
        )
        return

    # /chatid is intentionally not supported anymore.
    if command == "/chatid":
        bot.send_message(
            "This helper has been removed. Use the climate intelligence menu below.",
            chat_id,
            reply_markup=intelligence_keyboard(),
        )
        return

    _base_handle_command(message)


bot.public_command_keyboard = intelligence_keyboard
bot.build_welcome_message = intelligence_welcome
bot.handle_command = intelligence_handle_command


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
