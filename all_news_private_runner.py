"""All-news + strict-private Telegram runner.

Automatic news posts continue to go to GROUP_CHAT_ID. Every interactive button
or supported command returns its requested news to the requesting user's private
chat. Coverage includes Maldives English + Dhivehi news and broad global news:
politics, business, technology/AI, sports, entertainment, health, science,
travel/tourism, crime/courts, emergencies, environment and general world news.

Telegram credentials and GROUP_CHAT_ID continue to come from main.py's existing
environment-variable configuration. No credentials are changed here.
"""

import asyncio
import html
import re

import main as bot


# ============================================================
# MODE / CONFIG
# ============================================================

bot.BOT_NAME = "Maldives & World News"
bot.HISTORY_RETENTION_DAYS = 14

# Start a clean all-news history once when switching from climate-only mode.
if bot.state.get("news_mode") != "all_news_v1":
    bot.state["history"] = []
    bot.state["seen_ids"] = []
    bot.state["news_mode"] = "all_news_v1"
    bot.save_state()


# ============================================================
# MALDIVES + GLOBAL SOURCES
# ============================================================

# Direct local feeds are best-effort; Google News discovery gives broader
# English and Dhivehi coverage when publisher RSS endpoints are unavailable.
bot.MALDIVES_RSS_FEEDS = {
    "🇲🇻 Sun Online": "https://sun.mv/news/rss",
    "🇲🇻 PSM News": "https://psmnews.mv/feed",
    "🇲🇻 Adhadhu": "https://adhadhu.com/rss",
    "🇲🇻 Miadhu": "https://miadhu.com/feed",
}

bot.MALDIVES_GOOGLE_FEEDS = {
    # Broad English coverage
    "🇲🇻 Maldives Top News EN": bot.google_news_feed(
        'Maldives news when:2d', region="US", language="en"
    ),
    "🇲🇻 Maldives Latest EN": bot.google_news_feed(
        'Maldives latest when:2d', region="US", language="en"
    ),
    "🇲🇻 Maldives Politics EN": bot.google_news_feed(
        'Maldives (government OR president OR parliament OR election OR minister) when:3d',
        region="US", language="en",
    ),
    "🇲🇻 Maldives Business EN": bot.google_news_feed(
        'Maldives (economy OR business OR bank OR finance OR investment OR trade) when:3d',
        region="US", language="en",
    ),
    "🇲🇻 Maldives Tourism EN": bot.google_news_feed(
        'Maldives (tourism OR resort OR airline OR airport OR travel OR hotel) when:3d',
        region="US", language="en",
    ),
    "🇲🇻 Maldives Sports EN": bot.google_news_feed(
        'Maldives (sports OR football OR futsal OR volleyball OR swimming) when:3d',
        region="US", language="en",
    ),
    "🇲🇻 Maldives Health EN": bot.google_news_feed(
        'Maldives (health OR hospital OR disease OR medical OR doctor) when:3d',
        region="US", language="en",
    ),
    "🇲🇻 Maldives Technology EN": bot.google_news_feed(
        'Maldives (technology OR digital OR internet OR telecom OR AI) when:5d',
        region="US", language="en",
    ),
    "🇲🇻 Maldives Environment EN": bot.google_news_feed(
        'Maldives (environment OR climate OR coral OR reef OR ocean OR wildlife OR pollution) when:5d',
        region="US", language="en",
    ),
    "🇲🇻 Edition Maldives": bot.google_news_feed(
        'site:edition.mv Maldives when:3d', region="US", language="en"
    ),
    "🇲🇻 Adhadhu Maldives": bot.google_news_feed(
        'site:adhadhu.com Maldives when:3d', region="US", language="en"
    ),
    "🇲🇻 PSM Maldives": bot.google_news_feed(
        'site:psmnews.mv Maldives when:3d', region="US", language="en"
    ),
    "🇲🇻 Atoll Times Maldives": bot.google_news_feed(
        'site:atolltimes.mv Maldives when:5d', region="US", language="en"
    ),
    # Broad Dhivehi coverage
    "🇲🇻 ރާއްޖޭގެ ނޫސް": bot.google_news_feed(
        'ރާއްޖެ ނޫސް when:2d', region="MV", language="dv"
    ),
    "🇲🇻 ދިވެހި ނޫސް": bot.google_news_feed(
        'ދިވެހި ނޫސް when:2d', region="MV", language="dv"
    ),
    "🇲🇻 ސަރުކާރު": bot.google_news_feed(
        'ރާއްޖެ ސަރުކާރު when:3d', region="MV", language="dv"
    ),
    "🇲🇻 މަޖިލިސް": bot.google_news_feed(
        'ރާއްޖެ މަޖިލިސް when:3d', region="MV", language="dv"
    ),
    "🇲🇻 އިޤްތިޞާދު": bot.google_news_feed(
        'ރާއްޖެ އިޤްތިޞާދު when:3d', region="MV", language="dv"
    ),
    "🇲🇻 ޓޫރިޒަމް": bot.google_news_feed(
        'ރާއްޖެ ޓޫރިޒަމް when:3d', region="MV", language="dv"
    ),
    "🇲🇻 ސްޕޯޓް": bot.google_news_feed(
        'ރާއްޖެ ސްޕޯޓް when:3d', region="MV", language="dv"
    ),
    "🇲🇻 ޞިއްޙަތު": bot.google_news_feed(
        'ރާއްޖެ ޞިއްޙަތު when:3d', region="MV", language="dv"
    ),
}

# The variable name is inherited from the old climate core, but these are now
# general worldwide news feeds across many topics.
bot.GLOBAL_ENVIRONMENT_RSS = {
    "🌍 BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "🌍 The Guardian World": "https://www.theguardian.com/world/rss",
    "🌍 Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "🌍 NPR World": "https://feeds.npr.org/1004/rss.xml",
    "🌍 NYT World": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "💰 BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "💻 BBC Technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "🏥 BBC Health": "https://feeds.bbci.co.uk/news/health/rss.xml",
    "🎬 BBC Entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "⚽ BBC Sport": "https://feeds.bbci.co.uk/sport/rss.xml",
    "💰 CNBC World": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "💻 TechCrunch": "https://techcrunch.com/feed/",
    "🔬 NASA": "https://www.nasa.gov/news-release/feed/",
}

bot.GLOBAL_GOOGLE_FEEDS = {
    "🌍 World Breaking": bot.google_news_feed(
        'breaking world news when:12h', region="US", language="en"
    ),
    "🌍 World Top News": bot.google_news_feed(
        'world top news when:12h', region="US", language="en"
    ),
    "🌍 Reuters World": bot.google_news_feed(
        'site:reuters.com world news when:24h', region="US", language="en"
    ),
    "🌍 AP World": bot.google_news_feed(
        'site:apnews.com world news when:24h', region="US", language="en"
    ),
    "🏛️ Global Politics": bot.google_news_feed(
        '(government OR election OR parliament OR president OR diplomacy) world when:24h',
        region="US", language="en",
    ),
    "💰 Global Business": bot.google_news_feed(
        '(economy OR business OR markets OR inflation OR banking OR trade) when:24h',
        region="US", language="en",
    ),
    "💻 Global Technology & AI": bot.google_news_feed(
        '(technology OR artificial intelligence OR AI OR cybersecurity OR software) when:24h',
        region="US", language="en",
    ),
    "🏥 Global Health": bot.google_news_feed(
        '(health OR medicine OR disease OR outbreak OR hospital OR vaccine) when:24h',
        region="US", language="en",
    ),
    "🔬 Global Science": bot.google_news_feed(
        '(science OR research OR space OR discovery OR NASA) when:24h',
        region="US", language="en",
    ),
    "⚽ Global Sports": bot.google_news_feed(
        '(football OR soccer OR cricket OR tennis OR basketball OR sports) when:12h',
        region="US", language="en",
    ),
    "🎬 Global Entertainment": bot.google_news_feed(
        '(film OR movie OR music OR television OR entertainment OR celebrity) when:24h',
        region="US", language="en",
    ),
    "✈️ Global Travel": bot.google_news_feed(
        '(travel OR tourism OR airline OR airport OR hotel OR visa) when:24h',
        region="US", language="en",
    ),
    "⚖️ Global Crime & Courts": bot.google_news_feed(
        '(court OR police OR crime OR arrested OR trial OR investigation) world when:24h',
        region="US", language="en",
    ),
    "🌊 Global Environment": bot.google_news_feed(
        '(environment OR climate OR wildlife OR ocean OR pollution OR conservation) when:24h',
        region="US", language="en",
    ),
}


# ============================================================
# ALL-NEWS CLASSIFICATION
# ============================================================

CATEGORY_EMOJIS = {
    "Emergency": "🚨",
    "Politics": "🏛️",
    "Business": "💰",
    "Technology & AI": "💻",
    "Health": "🏥",
    "Science": "🔬",
    "Travel & Tourism": "✈️",
    "Sports": "⚽",
    "Entertainment": "🎬",
    "Crime & Courts": "⚖️",
    "Environment": "🌊",
    "General": "📰",
}

CATEGORY_KEYWORDS = {
    "Emergency": {
        "breaking", "urgent", "emergency", "earthquake", "tsunami", "cyclone",
        "hurricane", "typhoon", "flood", "explosion", "evacuation", "landslide",
        "wildfire", "attack", "missile", "war", "ceasefire", "alert", "warning",
        "ބްރޭކިންގ", "ކާރިސާ", "އެމަޖެންސީ", "ބިންހެލުން", "ސުނާމީ",
    },
    "Politics": {
        "president", "prime minister", "parliament", "election", "government",
        "minister", "senate", "congress", "diplomatic", "sanctions", "constitution",
        "vote", "cabinet", "ރައީސް", "ވުޒީރު", "ވަޒީރު", "މަޖިލިސް",
        "އިންތިޚާބު", "ސަރުކާރު", "ޤާނޫނު", "ސިޔާސީ",
    },
    "Business": {
        "economy", "inflation", "bank", "market", "stocks", "business", "trade",
        "company", "investment", "currency", "finance", "gdp", "profit", "recession",
        "interest rate", "އިޤްތިޞާދު", "ވިޔަފާރި", "ފައިސާ", "ބޭންކު",
        "މާކެޓް", "ފައިނޭންސް",
    },
    "Technology & AI": {
        "technology", "artificial intelligence", "generative ai", "chatgpt", "openai",
        "gemini", "machine learning", "ai model", "software", "cybersecurity", "cyber",
        "smartphone", "computer", "internet", "chip", "semiconductor", "robot",
        "ޓެކްނޮލޮޖީ", "އޭއައި", "އިންޓަރނެޓް", "ސޮފްޓްވެއަރ",
    },
    "Health": {
        "health", "hospital", "disease", "virus", "outbreak", "vaccine", "medical",
        "doctor", "patient", "treatment", "medicine", "ޞިއްޙަތު", "ބަލި",
        "ވައިރަސް", "ހޮސްޕިޓަލް", "ޑޮކްޓަރު",
    },
    "Science": {
        "science", "research", "scientist", "space", "nasa", "discovery", "study",
        "astronomy", "experiment", "satellite", "ސައިންސް", "ދިރާސާ", "ފަލަކީ",
    },
    "Travel & Tourism": {
        "travel", "tourism", "airport", "airline", "flight", "hotel", "resort", "visa",
        "passenger", "cruise", "ޓޫރިޒަމް", "މުސާފިރު", "ރިސޯޓް", "އެއަރޕޯޓް",
        "ފްލައިޓް", "ހޮޓެލް",
    },
    "Sports": {
        "football", "soccer", "cricket", "tennis", "basketball", "futsal", "volleyball",
        "championship", "league", "tournament", "world cup", "olympics", "match", "goal",
        "ފުޓްބޯޅަ", "ކްރިކެޓް", "ސްޕޯޓް", "މެޗު", "ލީގު",
    },
    "Entertainment": {
        "film", "movie", "music", "actor", "actress", "celebrity", "television", "concert",
        "award", "song", "album", "entertainment", "ފިލްމު", "މިއުޒިކް", "ޓީވީ",
        "ކޮންސާޓް", "އެކްޓަރު",
    },
    "Crime & Courts": {
        "police", "court", "crime", "arrested", "charged", "trial", "investigation",
        "prosecutor", "sentence", "murder", "robbery", "fraud", "ފުލުހުން", "ކޯޓު",
        "ހައްޔަރު", "ތަޙްޤީޤު", "ޖިނާއީ",
    },
    "Environment": {
        "environment", "climate", "ocean", "coral", "reef", "wildlife", "pollution",
        "conservation", "biodiversity", "marine", "plastic", "waste", "weather",
        "ތިމާވެށި", "ކަނޑު", "މޫދު", "ފަރު", "ކޮރަލް", "ކުނި",
    },
}

BREAKING_KEYWORDS = {
    "breaking", "urgent", "emergency", "earthquake", "tsunami", "cyclone", "hurricane",
    "typhoon", "flood", "explosion", "attack", "missile", "war", "ceasefire", "evacuation",
    "landslide", "terror", "assassination", "coup", "state of emergency", "killed", "dead",
    "resigns", "arrested", "alert", "warning", "ބްރޭކިންގ", "ކާރިސާ", "އެމަޖެންސީ",
    "ބިންހެލުން", "ސުނާމީ", "އެލާޓް",
}

HIGH_IMPORTANCE_KEYWORDS = {
    "president", "prime minister", "government", "election", "parliament", "war", "ceasefire",
    "sanctions", "economy", "inflation", "interest rate", "recession", "earthquake", "tsunami",
    "cyclone", "hurricane", "emergency", "outbreak", "pandemic", "airport closed", "death",
    "killed", "injury", "central bank", "supreme court", "ރައީސް", "ސަރުކާރު",
    "އިންތިޚާބު", "މަޖިލިސް", "އިޤްތިޞާދު", "ކާރިސާ",
}

LOW_VALUE_KEYWORDS = {
    "horoscope", "recipe", "shopping", "sponsored", "advertisement", "promotion", "discount",
    "photo gallery", "quiz",
}

MALDIVES_MARKERS = {
    "maldives", "maldivian", "malé", "male", "hulhumale", "addu", "baa atoll", "laamu",
    "gaafu", "dhivehi", "ދިވެހިރާއްޖެ", "ރާއްޖެ", "މާލެ", "ހުޅުމާލެ", "އައްޑޫ",
}

bot.CATEGORY_EMOJIS = CATEGORY_EMOJIS


def article_text(article):
    return " ".join(
        [
            str(article.get("source", "")),
            str(article.get("publisher", "")),
            str(article.get("title", "")),
            str(article.get("description", "")),
        ]
    ).lower()


def all_news_story(article):
    title = bot.clean_text(article.get("title", ""))
    link = str(article.get("link", "") or "")
    return len(title) >= 8 and link.startswith(("http://", "https://"))


def is_maldives_story(article):
    source = str(article.get("source", "")).lower()
    if "🇲🇻" in str(article.get("source", "")):
        return True
    if any(marker in source for marker in {"psm", "sun", "adhadhu", "miadhu", "edition", "atoll times"}):
        return True
    text = article_text(article)
    return any(marker in text for marker in MALDIVES_MARKERS)


def is_breaking_story(article):
    text = article_text(article)
    return any(keyword in text for keyword in BREAKING_KEYWORDS)


def detect_category(article):
    text = article_text(article)
    scores = {
        category: sum(1 for keyword in keywords if keyword in text)
        for category, keywords in CATEGORY_KEYWORDS.items()
    }

    # A genuine urgent signal should surface as Emergency before normal topics.
    if scores.get("Emergency", 0) > 0 and is_breaking_story(article):
        return "Emergency"

    non_emergency = {key: value for key, value in scores.items() if key != "Emergency"}
    best = max(non_emergency, key=non_emergency.get)
    return best if non_emergency[best] > 0 else "General"


def calculate_importance(article):
    text = article_text(article)
    score = 38

    if is_maldives_story(article):
        score += 12
    if bot.is_dhivehi_story(article):
        score += 5
    if is_breaking_story(article):
        score += 28

    important_hits = sum(1 for keyword in HIGH_IMPORTANCE_KEYWORDS if keyword in text)
    score += min(important_hits * 5, 25)

    source = str(article.get("source", "")).lower()
    if any(name in source for name in {"bbc", "reuters", "ap", "npr", "nyt", "guardian", "psm", "sun", "adhadhu"}):
        score += 6

    low_hits = sum(1 for keyword in LOW_VALUE_KEYWORDS if keyword in text)
    score -= min(low_hits * 10, 30)

    return max(0, min(100, score))


bot.is_environment_story = all_news_story  # inherited core hook; now accepts all curated news
bot.is_maldives_story = is_maldives_story
bot.is_breaking_story = is_breaking_story
bot.detect_category = detect_category
bot.calculate_importance = calculate_importance


# ============================================================
# GENERAL SUMMARIES / AI / POST FORMAT
# ============================================================

def general_local_analysis(cluster, local_score):
    first = cluster["articles"][0]
    return {
        "headline": first.get("title", "Untitled report"),
        "summary": bot.local_summary(first, cluster.get("articles", [])),
        "why_it_matters": "",
        "category": detect_category(first),
        "breaking": is_breaking_story(first),
        "importance_score": local_score,
        "used_ai": False,
    }


def general_ai_analysis(cluster):
    reports = []
    for index, article in enumerate(cluster.get("articles", [])[:4], start=1):
        reports.append(
            f"Report {index}\n"
            f"Publisher: {article.get('publisher', '')}\n"
            f"Headline: {article.get('title', '')}\n"
            f"Description: {bot.shorten_text(article.get('description', ''), 1200)}"
        )

    prompt = f"""
You edit a factual Maldives + world general-news channel.
Use only facts explicitly contained in the supplied reports. Do not invent details.
Return one JSON object only:
{{
  "headline": "clear factual headline",
  "summary": ["sentence one", "sentence two"],
  "why_it_matters": "short factual context or empty string",
  "category": "one allowed category",
  "breaking": false,
  "importance_score": 0
}}
Allowed categories: {", ".join(CATEGORY_EMOJIS.keys())}
Breaking must be true only for genuinely urgent/new major developments.
Reports:\n{chr(10).join(reports)}
""".strip()

    data = bot.extract_json_object(bot.gemini_generate(prompt))
    if not data:
        return None

    summary = data.get("summary", [])
    if not isinstance(summary, list):
        return None
    summary = [bot.clean_text(item) for item in summary if bot.clean_text(item)][:2]
    if len(summary) != 2:
        return None

    category = bot.clean_text(data.get("category", "General"))
    if category not in CATEGORY_EMOJIS:
        category = "General"

    try:
        importance = int(data.get("importance_score", 70))
    except Exception:
        importance = 70

    return {
        "headline": bot.clean_text(data.get("headline", cluster["articles"][0].get("title", ""))),
        "summary": summary,
        "why_it_matters": bot.clean_text(data.get("why_it_matters", "")),
        "category": category,
        "breaking": bool(data.get("breaking", False)),
        "importance_score": max(0, min(100, importance)),
        "used_ai": True,
    }


def general_news_message(cluster, analysis, trend_score):
    first = cluster["articles"][0]
    category = analysis.get("category", "General")
    emoji = CATEGORY_EMOJIS.get(category, "📰")
    region = "🇲🇻 Maldives" if is_maldives_story(first) else "🌍 Global"
    language = "Dhivehi" if bot.is_dhivehi_story(first) else "English"

    if analysis.get("breaking"):
        header = "🚨 <b>BREAKING NEWS</b>\n\n"
    elif trend_score >= 84:
        header = "🔥 <b>IMPORTANT NEWS</b>\n\n"
    else:
        header = ""

    summary = list(analysis.get("summary", []) or [])
    while len(summary) < 2:
        summary.append("Open the original source below for the complete report.")

    message = (
        f"{header}"
        f"{emoji} <b>{html.escape(category)}</b> · {region} · {language}\n\n"
        f"📰 <b>{html.escape(str(analysis.get('headline', 'Untitled report')))}</b>\n\n"
        f"• {html.escape(str(summary[0]))}\n"
        f"• {html.escape(str(summary[1]))}\n"
    )

    if analysis.get("why_it_matters"):
        message += f"\n💡 <b>Context:</b> {html.escape(str(analysis['why_it_matters']))}\n"

    publishers = html.escape(", ".join(sorted(cluster.get("publishers", []))))
    message += (
        f"\n📊 <b>Priority:</b> {trend_score}/100\n"
        f"🏢 <b>Sources:</b> {publishers}\n\n"
        "👇 Open the original reporting below."
    )
    if len(cluster.get("articles", [])) > 1:
        message += f"\n🧩 Combined from {len(cluster['articles'])} related reports."

    return bot.shorten_text(message, 3600)


def general_save_history(cluster, analysis, trend_score):
    first = cluster["articles"][0]
    bot.state.setdefault("history", []).append(
        {
            "created_at": bot.utc_now_iso(),
            "headline": analysis.get("headline", first.get("title", "")),
            "summary": analysis.get("summary", []),
            "category": analysis.get("category", "General"),
            "breaking": bool(analysis.get("breaking", False)),
            "importance_score": int(analysis.get("importance_score", 0) or 0),
            "trending_score": int(trend_score or 0),
            "publishers": sorted(cluster.get("publishers", [])),
            "link": first.get("link", ""),
            "maldives": is_maldives_story(first),
            "dhivehi": bot.is_dhivehi_story(first),
            "used_ai": bool(analysis.get("used_ai", False)),
        }
    )


bot.local_cluster_analysis = general_local_analysis
bot.analyze_cluster_with_ai = general_ai_analysis
bot.build_news_message = general_news_message
bot.save_to_history = general_save_history


# ============================================================
# BALANCED, DIVERSE AUTOMATIC GROUP PUBLISHING
# ============================================================

async def all_news_check_and_publish():
    bot.logging.info("Collecting Maldives + global all-topic news...")
    articles = await asyncio.to_thread(bot.fetch_new_articles)
    if not articles:
        bot.state["last_news_check"] = bot.utc_now_iso()
        bot.save_state()
        bot.logging.info("No new news items.")
        return

    clusters = bot.cluster_articles(articles)
    maldives_items = []
    global_items = []

    for cluster in clusters:
        local_score = max(calculate_importance(a) for a in cluster["articles"])
        local_score += min((len(cluster.get("publishers", [])) - 1) * 5, 15)
        item = {"cluster": cluster, "local_score": min(100, local_score)}
        if is_maldives_story(cluster["articles"][0]):
            maldives_items.append(item)
        else:
            global_items.append(item)

    def rank(item):
        first = item["cluster"]["articles"][0]
        return (
            1 if is_breaking_story(first) else 0,
            item["local_score"],
            len(item["cluster"].get("publishers", [])),
        )

    maldives_items.sort(key=rank, reverse=True)
    global_items.sort(key=rank, reverse=True)

    ordered = []
    while maldives_items or global_items:
        if maldives_items:
            ordered.append(maldives_items.pop(0))
        if global_items:
            ordered.append(global_items.pop(0))

    max_posts = min(bot.MAX_POSTS_PER_CHECK, 12)
    posted_count = 0
    ai_used = 0
    category_counts = {}

    for item in ordered:
        cluster = item["cluster"]
        first = cluster["articles"][0]
        local_score = item["local_score"]
        if not all_news_story(first) or local_score < bot.MINIMUM_POST_SCORE:
            continue

        category = detect_category(first)
        # Keep the automatic group feed broad instead of allowing one subject
        # to consume every slot. Breaking news bypasses this diversity cap.
        if category_counts.get(category, 0) >= 2 and not is_breaking_story(first):
            continue

        analysis = None
        if bot.should_use_ai(cluster, local_score, ai_used):
            analysis = await asyncio.to_thread(general_ai_analysis, cluster)
            if analysis:
                ai_used += 1
        if not analysis:
            analysis = general_local_analysis(cluster, local_score)

        trend_score = bot.calculate_trending_score(cluster, analysis)
        message = general_news_message(cluster, analysis, trend_score)
        buttons = bot.build_source_buttons(cluster)

        published = await asyncio.to_thread(
            bot.publish_post,
            message,
            cluster.get("image"),
            buttons,
        )
        if published:
            general_save_history(cluster, analysis, trend_score)
            posted_count += 1
            category_counts[category] = category_counts.get(category, 0) + 1
            await asyncio.sleep(bot.MESSAGE_DELAY_SECONDS)

        if posted_count >= max_posts:
            break

    bot.state["last_news_check"] = bot.utc_now_iso()
    bot.save_state()
    bot.logging.info("Completed all-news cycle: %s posts, %s AI requests.", posted_count, ai_used)


bot.check_and_publish_news = all_news_check_and_publish


# ============================================================
# PRIVATE LIVE BROWSING
# ============================================================

MAIN_BUTTONS = {
    "🇲🇻 Maldives",
    "🌍 Global",
    "🚨 Important",
    "🧭 News Topics",
    "🧭 Related Topics",  # previous keyboard label
}

TOPIC_BUTTONS = {
    "🚨 Breaking": ("breaking", "Breaking & Urgent News"),
    "🏛️ Politics": ("politics", "Politics"),
    "💰 Business": ("business", "Business & Economy"),
    "💻 Technology & AI": ("technology", "Technology & AI"),
    "⚽ Sports": ("sports", "Sports"),
    "🎬 Entertainment": ("entertainment", "Entertainment"),
    "🏥 Health": ("health", "Health"),
    "🔬 Science": ("science", "Science & Research"),
    "✈️ Travel & Tourism": ("travel", "Travel & Tourism"),
    "🌊 Environment": ("environment", "Environment & Climate"),
    "⚖️ Crime & Courts": ("crime", "Crime & Courts"),
    "📰 Latest": ("latest", "Latest News"),
}

# Map old climate-menu buttons to sensible general-news topics so stale reply
# keyboards still get a private result instead of falling back to old logic.
STALE_TOPIC_BUTTONS = {
    "🪸 Reefs & Oceans": ("environment", "Environment & Oceans"),
    "🚨 Weather": ("environment", "Weather & Environment"),
    "🦋 Wildlife": ("environment", "Wildlife & Environment"),
    "♻️ Pollution": ("environment", "Pollution & Environment"),
    "🌱 Conservation": ("environment", "Conservation & Environment"),
    "⚡ Clean Energy": ("business", "Energy & Business"),
    "🌡️ Climate": ("environment", "Climate & Environment"),
    "🏛️ Policy": ("politics", "Politics & Policy"),
    "🔬 Research": ("science", "Science & Research"),
    "🏝️ Baa Atoll": ("maldives", "Baa Atoll & Maldives News"),
    "🔥 Trending": ("important", "Important News"),
    "🌊 Oceans & Reefs": ("environment", "Environment & Oceans"),
    "🚨 Extreme Weather": ("environment", "Weather & Environment"),
    "🪸 Reef Watch": ("environment", "Environment & Oceans"),
    "♻️ Pollution & Waste": ("environment", "Pollution & Environment"),
    "🏛️ Climate Policy": ("politics", "Politics & Policy"),
    "📰 Latest News": ("latest", "Latest News"),
    "🌍 World": ("global", "Global News"),
    "💻 Technology": ("technology", "Technology & AI"),
    "💰 Business": ("business", "Business & Economy"),
    "⚽ Sports": ("sports", "Sports"),
}


def main_keyboard():
    return {
        "keyboard": [
            [
                {"text": "🇲🇻 Maldives"},
                {"text": "🌍 Global"},
                {"text": "🚨 Important"},
            ],
            [{"text": "🧭 News Topics"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose Maldives, Global, Important or News Topics...",
    }


def topics_keyboard():
    return {
        "keyboard": [
            [{"text": "🚨 Breaking"}, {"text": "🏛️ Politics"}],
            [{"text": "💰 Business"}, {"text": "💻 Technology & AI"}],
            [{"text": "⚽ Sports"}, {"text": "🎬 Entertainment"}],
            [{"text": "🏥 Health"}, {"text": "🔬 Science"}],
            [{"text": "✈️ Travel & Tourism"}, {"text": "🌊 Environment"}],
            [{"text": "⚖️ Crime & Courts"}, {"text": "📰 Latest"}],
            [{"text": "⬅️ Main Menu"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose a news topic...",
    }


def safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def story_text(story):
    return " ".join(
        [
            str(story.get("headline", "")),
            " ".join(story.get("summary", []) or []),
            str(story.get("category", "")),
            " ".join(story.get("publishers", []) or []),
        ]
    ).lower()


def history_news(kind, limit=12, hours=24 * 14):
    stories = list(bot.recent_history(hours))

    if kind == "maldives":
        stories = [s for s in stories if s.get("maldives")]
    elif kind == "global":
        stories = [s for s in stories if not s.get("maldives")]
    elif kind == "important":
        stories = [
            s for s in stories
            if s.get("breaking")
            or max(safe_int(s.get("trending_score")), safe_int(s.get("importance_score"))) >= 75
        ]
    elif kind == "breaking":
        stories = [s for s in stories if s.get("breaking") or s.get("category") == "Emergency"]
    elif kind == "latest":
        pass
    else:
        category_map = {
            "politics": {"Politics"},
            "business": {"Business"},
            "technology": {"Technology & AI"},
            "sports": {"Sports"},
            "entertainment": {"Entertainment"},
            "health": {"Health"},
            "science": {"Science"},
            "travel": {"Travel & Tourism"},
            "environment": {"Environment"},
            "crime": {"Crime & Courts"},
        }
        accepted = category_map.get(kind, set())
        stories = [s for s in stories if s.get("category") in accepted]

    if kind in {"important", "breaking"}:
        stories.sort(
            key=lambda s: (
                1 if s.get("breaking") else 0,
                max(safe_int(s.get("trending_score")), safe_int(s.get("importance_score"))),
                s.get("created_at", ""),
            ),
            reverse=True,
        )
    else:
        stories.sort(key=lambda s: s.get("created_at", ""), reverse=True)

    return stories[:limit]


LIVE_QUERIES = {
    "maldives": [
        ('Maldives news when:1d', "US", "en"),
        ('ރާއްޖެ ނޫސް when:1d', "MV", "dv"),
    ],
    "global": [('world top news when:12h', "US", "en")],
    "important": [
        ('breaking world news when:12h', "US", "en"),
        ('Maldives breaking news when:1d', "US", "en"),
    ],
    "breaking": [('breaking news world when:12h', "US", "en")],
    "politics": [('world politics government election when:24h', "US", "en")],
    "business": [('business economy markets finance when:24h', "US", "en")],
    "technology": [('technology AI cybersecurity software when:24h', "US", "en")],
    "sports": [('sports football cricket tennis when:12h', "US", "en")],
    "entertainment": [('entertainment film music television when:24h', "US", "en")],
    "health": [('health medicine disease research when:24h', "US", "en")],
    "science": [('science research space discovery when:24h', "US", "en")],
    "travel": [('travel tourism airline airport when:24h', "US", "en")],
    "environment": [('environment climate wildlife ocean when:24h', "US", "en")],
    "crime": [('crime court police investigation world when:24h', "US", "en")],
    "latest": [('world latest news when:12h', "US", "en")],
}


def live_private_news(kind, limit=12):
    articles = []
    for index, (query, region, language) in enumerate(LIVE_QUERIES.get(kind, []), start=1):
        source_name = f"Private live {kind} {index}"
        feed_url = bot.google_news_feed(query, region=region, language=language)
        feed = bot.download_rss_feed(source_name, feed_url)
        if not feed:
            continue
        for entry in list(getattr(feed, "entries", []) or [])[:12]:
            article = bot.parse_rss_entry(source_name, entry)
            if article and all_news_story(article):
                articles.append(article)

    if not articles:
        return []

    stories = []
    for cluster in bot.cluster_articles(articles):
        first = cluster["articles"][0]
        score = max(calculate_importance(a) for a in cluster["articles"])
        analysis = general_local_analysis(cluster, score)
        trend = bot.calculate_trending_score(cluster, analysis)
        stories.append(
            {
                "created_at": bot.utc_now_iso(),
                "headline": analysis["headline"],
                "summary": analysis["summary"],
                "category": analysis["category"],
                "breaking": analysis["breaking"],
                "importance_score": analysis["importance_score"],
                "trending_score": trend,
                "publishers": sorted(cluster.get("publishers", [])),
                "link": first.get("link", ""),
                "maldives": is_maldives_story(first),
                "dhivehi": bot.is_dhivehi_story(first),
            }
        )

    stories.sort(
        key=lambda s: (
            1 if s.get("breaking") else 0,
            max(safe_int(s.get("trending_score")), safe_int(s.get("importance_score"))),
        ),
        reverse=True,
    )
    return stories[:limit]


def private_news(kind, limit=12):
    stored = history_news(kind, limit=limit)
    if len(stored) >= min(5, limit):
        return stored[:limit]

    live = live_private_news(kind, limit=limit)
    combined = list(stored)
    for candidate in live:
        duplicate = False
        for existing in combined:
            if bot.headline_similarity(
                str(candidate.get("headline", "")),
                str(existing.get("headline", "")),
            ) >= 0.72:
                duplicate = True
                break
        if not duplicate:
            combined.append(candidate)
        if len(combined) >= limit:
            break
    return combined[:limit]


def safe_story_list(title, stories, limit=12):
    title_html = html.escape(str(title))
    if not stories:
        return (
            f"📰 <b>{title_html}</b>\n\n"
            "No matching stories were available from the recent history or live news search. "
            "Please try again shortly."
        )

    message = f"📰 <b>{title_html}</b>\n\n"
    shown = 0
    for index, story in enumerate(stories[:limit], start=1):
        category = str(story.get("category", "General"))
        emoji = CATEGORY_EMOJIS.get(category, "📰")
        headline = html.escape(str(story.get("headline", "Untitled report")))
        link = str(story.get("link", "") or "").strip()
        region = "🇲🇻" if story.get("maldives") else "🌍"
        language = "DV" if story.get("dhivehi") else "EN"
        score = max(safe_int(story.get("trending_score")), safe_int(story.get("importance_score")))

        if link.startswith(("https://", "http://")):
            headline_part = f'<a href="{html.escape(link, quote=True)}">{headline}</a>'
        else:
            headline_part = headline

        block = (
            f"{index}. {region} {emoji} {headline_part}\n"
            f"   {html.escape(category)} · 🌐 {language} · 📊 {score}/100\n\n"
        )
        if len(message) + len(block) > 3650:
            break
        message += block
        shown += 1

    return message.rstrip() if shown else f"📰 <b>{title_html}</b>\n\nNo stories could be formatted."


# ============================================================
# STRICT PRIVATE ROUTING
# ============================================================

def private_destination(message):
    chat = message.get("chat", {}) or {}
    sender = message.get("from", {}) or {}
    chat_id = chat.get("id")
    sender_id = sender.get("id")
    from_group = (
        sender_id is not None
        and chat_id is not None
        and str(sender_id) != str(chat_id)
    )
    return (sender_id if from_group else chat_id), chat_id, from_group


def send_private(message, text, reply_markup=None):
    destination, origin_chat_id, from_group = private_destination(message)
    if destination is None:
        return None

    result = bot.send_message(
        text,
        destination,
        reply_markup=reply_markup or main_keyboard(),
    )
    if result:
        return result

    if from_group and origin_chat_id is not None:
        # Never place requested news in the group as a fallback.
        bot.send_message(
            "📩 <b>I need permission to message you privately.</b>\n\n"
            "Open my bot profile and press <b>Start</b> once, then return to the group "
            "and press the button again. The requested news will be sent only to you.",
            origin_chat_id,
        )
    return None


def welcome_text():
    return f"""
📰 <b>{bot.BOT_NAME}</b>

The bot now covers <b>all major news topics</b>, not only climate/environment.

🇲🇻 Maldives — English + Dhivehi news
🌍 Global — broad worldwide news
🚨 Important — high-priority and breaking developments
🧭 News Topics — politics, business, technology/AI, sports, entertainment, health, science, travel, crime/courts and environment

Automatic news stays in the group. Your button requests are returned privately.
""".strip()


COMMAND_TO_KIND = {
    "/maldives": ("maldives", "Maldives News — English + Dhivehi"),
    "/global": ("global", "Global News"),
    "/world": ("global", "Global News"),
    "/important": ("important", "Important News"),
    "/trending": ("important", "Important News"),
    "/latest": ("latest", "Latest News"),
    "/breaking": ("breaking", "Breaking & Urgent News"),
    "/politics": ("politics", "Politics"),
    "/business": ("business", "Business & Economy"),
    "/technology": ("technology", "Technology & AI"),
    "/tech": ("technology", "Technology & AI"),
    "/sports": ("sports", "Sports"),
    "/entertainment": ("entertainment", "Entertainment"),
    "/health": ("health", "Health"),
    "/science": ("science", "Science & Research"),
    "/travel": ("travel", "Travel & Tourism"),
    "/environment": ("environment", "Environment & Climate"),
    "/crime": ("crime", "Crime & Courts"),
}


def all_news_handle_command(message):
    text = str(message.get("text", "") or "").strip()
    if not text:
        return

    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else ""
    argument = text.split(maxsplit=1)[1].strip() if command == "/search" and len(text.split(maxsplit=1)) > 1 else ""

    try:
        if command in {"/start", "/help", "/menu"} or text == "⬅️ Main Menu":
            send_private(message, welcome_text(), main_keyboard())
            return

        if text in {"🧭 News Topics", "🧭 Related Topics"} or command == "/topics":
            send_private(
                message,
                "🧭 <b>News Topics</b>\n\nChoose a topic below. Your news results will be sent privately.",
                topics_keyboard(),
            )
            return

        if text == "🇲🇻 Maldives":
            send_private(message, safe_story_list("Maldives News — English + Dhivehi", private_news("maldives")), main_keyboard())
            return
        if text == "🌍 Global":
            send_private(message, safe_story_list("Global News", private_news("global")), main_keyboard())
            return
        if text == "🚨 Important":
            send_private(message, safe_story_list("Important News", private_news("important")), main_keyboard())
            return

        topic = TOPIC_BUTTONS.get(text) or STALE_TOPIC_BUTTONS.get(text)
        if topic:
            kind, title = topic
            send_private(message, safe_story_list(title, private_news(kind)), topics_keyboard())
            return

        if command in COMMAND_TO_KIND:
            kind, title = COMMAND_TO_KIND[command]
            send_private(message, safe_story_list(title, private_news(kind)), main_keyboard())
            return

        if command == "/search":
            if not argument:
                send_private(
                    message,
                    "🔎 <b>Search news</b>\n\nExample: <code>/search Maldives tourism</code>",
                    main_keyboard(),
                )
                return

            terms = [term.lower() for term in argument.split() if term]
            matches = [
                story for story in bot.recent_history(24 * 14)
                if all(term in story_text(story) for term in terms)
            ]
            matches.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            if not matches:
                # Live search for arbitrary queries when history has no match.
                LIVE_QUERIES["_search"] = [(f'{argument} news when:2d', "US", "en")]
                matches = live_private_news("_search", limit=12)
            send_private(message, safe_story_list(f"Search: {argument}", matches[:12]), main_keyboard())
            return

        # Stale utility buttons are still handled privately and never invoke
        # group-facing climate handlers.
        if text in {"📡 Fetch Status", "🔄 Check News Now", "🔄 Refresh Menu", "❓ Help"}:
            send_private(message, welcome_text(), main_keyboard())
            return

    except Exception as error:
        bot.logging.exception("All-news private command failed for %r: %s", text, error)
        send_private(
            message,
            "⚠️ <b>Could not load this news request.</b>\n\nPlease try again shortly.",
            main_keyboard(),
        )


# ============================================================
# GENERAL DIGESTS / STARTUP MENU
# ============================================================

def general_digest(title, hours):
    stories = list(bot.recent_history(hours))
    if not stories:
        return f"📰 <b>{html.escape(title)}</b>\n\nNo new stories were published in this period."
    stories.sort(
        key=lambda s: (
            1 if s.get("breaking") else 0,
            max(safe_int(s.get("trending_score")), safe_int(s.get("importance_score"))),
        ),
        reverse=True,
    )
    return safe_story_list(title, stories[:12])


async def all_news_digest_scheduler():
    while True:
        now = bot.maldives_now()
        today = now.date().isoformat()

        if now.hour == bot.MORNING_DIGEST_HOUR and now.minute < 5 and bot.state.get("last_morning_digest") != today:
            await asyncio.to_thread(bot.send_message, general_digest("Morning News Brief", 12))
            bot.state["last_morning_digest"] = today
            bot.save_state()

        if now.hour == bot.EVENING_DIGEST_HOUR and now.minute < 5 and bot.state.get("last_evening_digest") != today:
            await asyncio.to_thread(bot.send_message, general_digest("Evening News Brief", 12))
            bot.state["last_evening_digest"] = today
            bot.save_state()

        await asyncio.sleep(60)


bot.PUBLIC_COMMANDS = [
    {"command": "maldives", "description": "Maldives news in English + Dhivehi"},
    {"command": "global", "description": "Global news"},
    {"command": "important", "description": "Important and breaking news"},
    {"command": "topics", "description": "Browse all news topics"},
    {"command": "latest", "description": "Latest news"},
    {"command": "politics", "description": "Politics"},
    {"command": "business", "description": "Business and economy"},
    {"command": "technology", "description": "Technology and AI"},
    {"command": "sports", "description": "Sports"},
    {"command": "entertainment", "description": "Entertainment"},
    {"command": "health", "description": "Health"},
    {"command": "science", "description": "Science"},
    {"command": "travel", "description": "Travel and tourism"},
    {"command": "environment", "description": "Environment and climate"},
    {"command": "crime", "description": "Crime and courts"},
    {"command": "search", "description": "Search recent news"},
]

bot.public_command_keyboard = main_keyboard
bot.build_welcome_message = welcome_text
bot.handle_command = all_news_handle_command
bot.build_digest = general_digest
bot.digest_scheduler = all_news_digest_scheduler


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
