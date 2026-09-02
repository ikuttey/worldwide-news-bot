import asyncio
import hashlib
import html
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


# ============================================================
# CONFIGURATION
# ============================================================

BOT_NAME = "Maldives & World Climate News"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

NEWS_CHECK_INTERVAL_SECONDS = int(os.getenv("NEWS_CHECK_INTERVAL_SECONDS", "300"))
MAX_POSTS_PER_CHECK = int(os.getenv("MAX_POSTS_PER_CHECK", "12"))
MESSAGE_DELAY_SECONDS = float(os.getenv("MESSAGE_DELAY_SECONDS", "2"))
MINIMUM_POST_SCORE = int(os.getenv("MINIMUM_POST_SCORE", "8"))
MINIMUM_AI_SCORE = int(os.getenv("MINIMUM_AI_SCORE", "78"))
MAX_AI_REQUESTS_PER_CHECK = int(os.getenv("MAX_AI_REQUESTS_PER_CHECK", "2"))
MAX_AI_REQUESTS_PER_HOUR = int(os.getenv("MAX_AI_REQUESTS_PER_HOUR", "10"))
AI_QUOTA_COOLDOWN_MINUTES = 30
DUPLICATE_SIMILARITY_THRESHOLD = 0.68
HISTORY_RETENTION_DAYS = 7

MALDIVES_TIMEZONE = timezone(timedelta(hours=5))
MORNING_DIGEST_HOUR = 7
EVENING_DIGEST_HOUR = 19

STATE_FILE = Path(os.getenv("STATE_FILE", "climate_environment_news_state.json"))


# ============================================================
# RSS FEED HELPERS
# ============================================================

def google_news_feed(query, region="MV", language="en"):
    encoded_query = quote_plus(query)
    return (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}"
        f"&hl={language}"
        f"&gl={region}"
        f"&ceid={region}:{language}"
    )


# Broad Maldivian publishers are intentionally included, but every article
# passes a strict climate/environment relevance filter before publication.
MALDIVES_RSS_FEEDS = {
    "🇲🇻 PSM News": "https://psmnews.mv/feed",
    "🇲🇻 Sun Online": "https://sun.mv/rss",
    "🇲🇻 Dhiyares": "https://dhiyares.com/rss",
    "🇲🇻 Adhadhu": "https://adhadhu.com/rss",
    "🇲🇻 VNews": "https://vnews.mv/rss",
    "🇲🇻 Miadhu": "https://miadhu.com/feed",
    "🇲🇻 Times of Addu": "https://timesofaddu.com/feed",
}

MALDIVES_GOOGLE_FEEDS = {
    "🇲🇻 Maldives Climate": google_news_feed(
        '"Maldives" ("climate change" OR warming OR emissions OR "sea level") when:1d'
    ),
    "🇲🇻 Maldives Environment": google_news_feed(
        '"Maldives" (environment OR conservation OR biodiversity OR pollution) when:1d'
    ),
    "🇲🇻 Maldives Reefs & Ocean": google_news_feed(
        '"Maldives" (coral OR reef OR ocean OR marine OR bleaching) when:1d'
    ),
    "🇲🇻 Maldives Waste & Erosion": google_news_feed(
        '"Maldives" (waste OR plastic OR erosion OR shoreline OR dredging) when:1d'
    ),
    "🇲🇻 Maldives Wildlife": google_news_feed(
        '"Maldives" (wildlife OR turtle OR shark OR manta OR dolphin OR whale) when:1d'
    ),
    "🇲🇻 Maldives Clean Energy": google_news_feed(
        '"Maldives" ("renewable energy" OR solar OR decarbonization OR "clean energy") when:1d'
    ),
    "🇲🇻 Maldives Extreme Weather": google_news_feed(
        '"Maldives" (flood OR storm OR swell OR cyclone OR heatwave OR "heavy rain") when:1d'
    ),
    "🇲🇻 ތިމާވެށި": google_news_feed(
        "ދިވެހިރާއްޖެ ތިމާވެށި when:1d", region="MV", language="dv"
    ),
    "🇲🇻 ކްލައިމެޓް": google_news_feed(
        "ދިވެހިރާއްޖެ ކްލައިމެޓް when:1d", region="MV", language="dv"
    ),
    "🇲🇻 ފަރު އަދި ކޮރަލް": google_news_feed(
        "ރާއްޖެ ފަރު ކޮރަލް when:1d", region="MV", language="dv"
    ),
    "🇲🇻 ކުނި އަދި ޕްލާސްޓިކް": google_news_feed(
        "ރާއްޖެ ކުނި ޕްލާސްޓިކް when:1d", region="MV", language="dv"
    ),
}

GLOBAL_ENVIRONMENT_RSS = {
    "🌍 BBC Science & Environment": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "🌍 The Guardian Environment": "https://www.theguardian.com/environment/rss",
    "🌍 Mongabay": "https://news.mongabay.com/feed/",
    "🌍 Carbon Brief": "https://www.carbonbrief.org/feed/",
    "🌍 Inside Climate News": "https://insideclimatenews.org/feed/",
    "🌍 NASA": "https://www.nasa.gov/news-release/feed/",
}

GLOBAL_GOOGLE_FEEDS = {
    "🌍 Global Climate": google_news_feed(
        '"climate change" OR "global warming" OR decarbonization when:12h',
        region="US",
    ),
    "🌊 Global Ocean & Reefs": google_news_feed(
        'ocean OR coral OR reef OR "marine conservation" when:12h',
        region="US",
    ),
    "🦋 Global Biodiversity": google_news_feed(
        'biodiversity OR wildlife OR conservation OR extinction when:12h',
        region="US",
    ),
    "♻️ Global Pollution & Waste": google_news_feed(
        'pollution OR plastic OR waste OR microplastics when:12h',
        region="US",
    ),
    "🌳 Global Forests": google_news_feed(
        'deforestation OR forest OR mangrove OR peatland when:12h',
        region="US",
    ),
    "⚡ Global Clean Energy": google_news_feed(
        '"renewable energy" OR solar OR wind OR "energy transition" when:12h',
        region="US",
    ),
    "🚨 Global Extreme Weather": google_news_feed(
        'heatwave OR wildfire OR drought OR flood OR cyclone OR hurricane OR "storm surge" when:12h',
        region="US",
    ),
    "🏛️ Global Climate Policy": google_news_feed(
        '"climate policy" OR COP OR "Paris Agreement" OR "climate finance" when:12h',
        region="US",
    ),
}


# ============================================================
# TOPICS, KEYWORDS AND FILTERING
# ============================================================

CATEGORY_EMOJIS = {
    "Maldives Environment": "🇲🇻",
    "Climate Change": "🌡️",
    "Extreme Weather": "🚨",
    "Oceans & Reefs": "🌊",
    "Biodiversity & Wildlife": "🦋",
    "Pollution & Waste": "♻️",
    "Conservation & Restoration": "🌱",
    "Forests & Mangroves": "🌳",
    "Clean Energy": "⚡",
    "Climate Policy & Finance": "🏛️",
    "Science & Research": "🔬",
    "Environment": "🌍",
}

MALDIVES_MARKERS = {
    "maldives", "maldivian", "malé", "male", "hulhumale", "addu",
    "baa atoll", "dharavandhoo", "hanifaru", "laamu", "gaafu",
    "ދިވެހިރާއްޖެ", "ރާއްޖެ", "މާލެ", "ހުޅުމާލެ", "އައްޑޫ",
}

CLIMATE_KEYWORDS = {
    "climate change", "global warming", "climate crisis", "climate action",
    "greenhouse gas", "greenhouse gases", "emissions", "carbon emissions",
    "methane", "decarbonization", "decarbonisation", "net zero",
    "sea level rise", "sea-level rise", "climate adaptation",
    "climate resilience", "climate mitigation", "warming ocean",
    "ocean warming", "climate finance", "paris agreement",
    "loss and damage", "ipcc", "cop30", "cop31", "climate policy",
    "ކްލައިމެޓް", "ހޫނުވުން", "މޫސުމާ ގުޅޭ ބަދަލު",
}

OCEAN_REEF_KEYWORDS = {
    "coral", "corals", "coral reef", "coral reefs", "coral bleaching",
    "reef restoration", "ocean", "marine", "marine ecosystem",
    "seagrass", "sea grass", "mangrove", "blue carbon",
    "ocean acidification", "marine heatwave", "coastal erosion",
    "shoreline erosion", "dredging", "reclamation", "lagoon",
    "ފަރު", "ކޮރަލް", "ކަނޑު", "މޫދު", "ކަނޑު ދިރިއުޅުން",
}

BIODIVERSITY_KEYWORDS = {
    "biodiversity", "wildlife", "endangered", "extinction", "species",
    "habitat", "ecosystem", "turtle", "sea turtle", "shark", "whale",
    "dolphin", "manta", "manta ray", "ray", "bird", "protected species",
    "ދިރިއުޅުން", "މަސް", "ވެލާ", "ކަހަނބު",
}

POLLUTION_WASTE_KEYWORDS = {
    "pollution", "plastic pollution", "plastic waste", "microplastic",
    "microplastics", "waste management", "solid waste", "sewage",
    "oil spill", "chemical spill", "marine debris", "trash", "landfill",
    "recycling", "single-use plastic", "ކުނި", "ޕްލާސްޓިކް",
}

CONSERVATION_KEYWORDS = {
    "conservation", "restoration", "ecosystem restoration", "reef restoration",
    "coral restoration", "protected area", "marine protected area",
    "nature reserve", "reforestation", "habitat restoration",
    "environmental protection", "environment protection",
    "ރައްކާތެރި", "ތިމާވެށި",
}

FOREST_KEYWORDS = {
    "forest", "forests", "deforestation", "reforestation", "rainforest",
    "mangrove", "mangroves", "peatland", "wildfire", "forest fire",
}

CLEAN_ENERGY_KEYWORDS = {
    "renewable energy", "clean energy", "solar power", "solar energy",
    "wind power", "wind energy", "energy transition", "battery storage",
    "green hydrogen", "fossil fuel", "coal phaseout", "coal phase-out",
    "electric grid", "clean electricity",
}

EXTREME_WEATHER_KEYWORDS = {
    "heatwave", "heat wave", "wildfire", "drought", "flood", "flooding",
    "cyclone", "hurricane", "typhoon", "storm surge", "extreme rainfall",
    "extreme weather", "record heat", "marine heatwave", "severe storm",
    "coastal flooding", "high swell", "tidal flooding",
    "ފެންބޮޑުވުން", "ވައިގަދަ", "ސުނާމީ", "ކާރިސާ",
}

SCIENCE_KEYWORDS = {
    "climate study", "environmental study", "researchers found",
    "scientists found", "new study", "peer-reviewed", "research",
    "scientist", "scientists", "monitoring", "satellite data",
}

POLICY_KEYWORDS = {
    "climate policy", "environmental law", "environment law",
    "climate finance", "green finance", "carbon market", "carbon tax",
    "cop30", "cop31", "paris agreement", "loss and damage",
    "environment ministry", "environment minister", "unep", "unfccc",
}

GENERAL_ENVIRONMENT_KEYWORDS = {
    "environment", "environmental", "ecology", "ecological", "nature",
    "sustainability", "sustainable", "conservation", "biodiversity",
    "ecosystem", "pollution", "climate", "ocean", "marine", "coral",
    "reef", "wildlife", "renewable", "emissions", "deforestation",
    "mangrove", "waste", "plastic", "restoration",
    "ތިމާވެށި", "ކަނޑު", "ފަރު", "ކޮރަލް", "ކުނި",
}

ALL_TOPIC_KEYWORDS = (
    CLIMATE_KEYWORDS
    | OCEAN_REEF_KEYWORDS
    | BIODIVERSITY_KEYWORDS
    | POLLUTION_WASTE_KEYWORDS
    | CONSERVATION_KEYWORDS
    | FOREST_KEYWORDS
    | CLEAN_ENERGY_KEYWORDS
    | EXTREME_WEATHER_KEYWORDS
    | SCIENCE_KEYWORDS
    | POLICY_KEYWORDS
    | GENERAL_ENVIRONMENT_KEYWORDS
)

STRONG_ENVIRONMENT_PHRASES = {
    "climate change", "global warming", "coral bleaching", "coral reef",
    "reef restoration", "marine conservation", "ocean acidification",
    "biodiversity loss", "plastic pollution", "renewable energy",
    "energy transition", "sea level rise", "sea-level rise",
    "coastal erosion", "climate finance", "environmental protection",
    "marine protected area", "mangrove restoration", "extreme weather",
    "marine heatwave", "ތިމާވެށި", "ކްލައިމެޓް",
}

IRRELEVANT_SIGNALS = {
    "football", "cricket", "basketball", "tennis", "championship",
    "celebrity", "movie", "film", "music", "fashion", "horoscope",
    "recipe", "gaming", "smartphone launch", "stock market",
    "cryptocurrency", "crypto price", "election campaign",
}

ENVIRONMENT_SOURCE_MARKERS = {
    "environment", "climate", "mongabay", "carbon brief", "inside climate",
}

BREAKING_ENVIRONMENT_KEYWORDS = {
    "tsunami", "cyclone", "hurricane", "typhoon", "wildfire",
    "flash flood", "flooding", "storm surge", "marine heatwave",
    "record heat", "mass bleaching", "oil spill", "chemical spill",
    "evacuation", "environmental emergency", "ސުނާމީ", "ކާރިސާ",
}


# ============================================================
# SAVED STATE
# ============================================================

DEFAULT_STATE = {
    "seen_ids": [],
    "history": [],
    "telegram_offset": 0,
    "last_news_check": None,
    "last_morning_digest": None,
    "last_evening_digest": None,
    "ai_request_times": [],
    "ai_disabled_until": None,
}


def load_state():
    if not STATE_FILE.exists():
        return DEFAULT_STATE.copy()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            saved_state = json.load(file)
        result = DEFAULT_STATE.copy()
        result.update(saved_state)
        return result
    except Exception as error:
        logging.error("Could not load state: %s", error)
        return DEFAULT_STATE.copy()


state = load_state()


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_iso():
    return utc_now().isoformat()


def maldives_now():
    return datetime.now(MALDIVES_TIMEZONE)


def cleanup_state():
    history_cutoff = utc_now() - timedelta(days=HISTORY_RETENTION_DAYS)
    cleaned_history = []

    for item in state.get("history", []):
        try:
            created_at = datetime.fromisoformat(item["created_at"])
            if created_at >= history_cutoff:
                cleaned_history.append(item)
        except Exception:
            continue

    state["history"] = cleaned_history

    hour_cutoff = utc_now() - timedelta(hours=1)
    valid_ai_requests = []

    for request_time in state.get("ai_request_times", []):
        try:
            parsed_time = datetime.fromisoformat(request_time)
            if parsed_time >= hour_cutoff:
                valid_ai_requests.append(request_time)
        except Exception:
            continue

    state["ai_request_times"] = valid_ai_requests


def save_state():
    cleanup_state()
    state["seen_ids"] = state.get("seen_ids", [])[-12000:]
    state["history"] = state.get("history", [])[-2000:]
    state["ai_request_times"] = state.get("ai_request_times", [])[-100:]

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
    except Exception as error:
        logging.error("Could not save state: %s", error)


# ============================================================
# TEXT AND ARTICLE HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    text = str(value)
    text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def shorten_text(text, maximum_length):
    text = str(text)
    if len(text) <= maximum_length:
        return text
    return text[:maximum_length].rstrip() + "..."


def split_sentences(text):
    text = clean_text(text)
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [sentence.strip() for sentence in sentences if len(sentence.strip()) >= 25]


def article_hash(source, title, link):
    value = f"{source}|{title}|{link}"
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def combined_article_text(article):
    return " ".join(
        [
            article.get("source", ""),
            article.get("publisher", ""),
            article.get("title", ""),
            article.get("description", ""),
        ]
    ).lower()


def article_content_text(article):
    """Title + description only, so feed labels cannot make a story relevant."""
    return " ".join(
        [
            article.get("title", ""),
            article.get("description", ""),
        ]
    ).lower()


def count_keyword_hits(text, keywords):
    return sum(1 for keyword in keywords if keyword in text)


def is_maldives_story(article):
    text = combined_article_text(article)
    return any(marker in text for marker in MALDIVES_MARKERS) or "🇲🇻" in article.get("source", "")


def is_dhivehi_story(article):
    text = combined_article_text(article)
    matches = re.findall(r"[\u0780-\u07BF]", text)
    return bool(text) and len(matches) / max(len(text), 1) > 0.05


def environmental_relevance_score(article):
    text = article_content_text(article)

    strong_hits = count_keyword_hits(text, STRONG_ENVIRONMENT_PHRASES)
    topic_hits = count_keyword_hits(text, ALL_TOPIC_KEYWORDS)
    irrelevant_hits = count_keyword_hits(text, IRRELEVANT_SIGNALS)

    source = article.get("source", "").lower()
    source_bonus = 2 if any(marker in source for marker in ENVIRONMENT_SOURCE_MARKERS) else 0
    maldives_bonus = 1 if is_maldives_story(article) else 0

    score = strong_hits * 4 + min(topic_hits, 6) * 2 + source_bonus + maldives_bonus
    score -= min(irrelevant_hits * 4, 12)

    return max(0, score)


def is_environment_story(article):
    text = article_content_text(article)

    # One strong phrase is enough. Otherwise require multiple topic signals.
    if any(phrase in text for phrase in STRONG_ENVIRONMENT_PHRASES):
        return True

    topic_hits = count_keyword_hits(text, ALL_TOPIC_KEYWORDS)
    if topic_hits >= 2:
        return True

    source = article.get("source", "").lower()
    if any(marker in source for marker in ENVIRONMENT_SOURCE_MARKERS) and topic_hits >= 1:
        return True

    return False


def detect_category(article):
    text = article_content_text(article)

    scores = {
        "Climate Change": count_keyword_hits(text, CLIMATE_KEYWORDS),
        "Extreme Weather": count_keyword_hits(text, EXTREME_WEATHER_KEYWORDS),
        "Oceans & Reefs": count_keyword_hits(text, OCEAN_REEF_KEYWORDS),
        "Biodiversity & Wildlife": count_keyword_hits(text, BIODIVERSITY_KEYWORDS),
        "Pollution & Waste": count_keyword_hits(text, POLLUTION_WASTE_KEYWORDS),
        "Conservation & Restoration": count_keyword_hits(text, CONSERVATION_KEYWORDS),
        "Forests & Mangroves": count_keyword_hits(text, FOREST_KEYWORDS),
        "Clean Energy": count_keyword_hits(text, CLEAN_ENERGY_KEYWORDS),
        "Climate Policy & Finance": count_keyword_hits(text, POLICY_KEYWORDS),
        "Science & Research": count_keyword_hits(text, SCIENCE_KEYWORDS),
    }

    category = max(scores, key=scores.get)
    if scores[category] == 0:
        category = "Environment"

    if is_maldives_story(article):
        # Keep topic-specific labels for strong topic stories, but clearly
        # distinguish general Maldives environmental news.
        if scores.get(category, 0) == 0:
            return "Maldives Environment"

    return category


def is_breaking_story(article):
    text = article_content_text(article)
    return any(keyword in text for keyword in BREAKING_ENVIRONMENT_KEYWORDS)


def calculate_importance(article):
    if not is_environment_story(article):
        return 0

    text = article_content_text(article)
    score = 35

    score += min(environmental_relevance_score(article) * 3, 30)

    if is_maldives_story(article):
        score += 18

    if is_breaking_story(article):
        score += 18

    if count_keyword_hits(text, {"coral bleaching", "sea level rise", "marine heatwave", "climate finance"}):
        score += 7

    return max(0, min(100, score))


# ============================================================
# RSS DOWNLOAD AND PARSING
# ============================================================

def download_rss_feed(source_name, feed_url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )
    }

    try:
        response = requests.get(feed_url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status()
        return feedparser.parse(response.content)
    except Exception as error:
        logging.debug("RSS feed unavailable — %s: %s", source_name, error)
        return None


def parse_rss_entry(source_name, entry):
    title = clean_text(entry.get("title", "Untitled report"))
    link = entry.get("link") or entry.get("id")

    if not link or len(title) < 8:
        return None

    description = clean_text(
        entry.get("summary")
        or entry.get("description")
        or entry.get("subtitle")
        or title
    )

    article_id = entry.get("id") or entry.get("guid") or article_hash(source_name, title, link)

    image = None
    for item in entry.get("media_content", []) or []:
        if isinstance(item, dict) and item.get("url"):
            image = item["url"]
            break

    if not image:
        for enclosure in entry.get("enclosures", []) or []:
            if (
                isinstance(enclosure, dict)
                and enclosure.get("url")
                and "image" in enclosure.get("type", "")
            ):
                image = enclosure["url"]
                break

    return {
        "id": str(article_id),
        "source": source_name,
        "publisher": source_name,
        "title": title,
        "description": description,
        "link": str(link),
        "image": image,
        "timestamp": entry.get("published", utc_now_iso()),
    }


def fetch_new_articles():
    seen_ids = set(state.get("seen_ids", []))
    collected_articles = []

    all_feeds = {
        **MALDIVES_RSS_FEEDS,
        **MALDIVES_GOOGLE_FEEDS,
        **GLOBAL_ENVIRONMENT_RSS,
        **GLOBAL_GOOGLE_FEEDS,
    }

    ordered_feeds = sorted(
        all_feeds.items(),
        key=lambda item: (0 if "🇲🇻" in item[0] else 1, item[0]),
    )

    for source_name, feed_url in ordered_feeds:
        feed = download_rss_feed(source_name, feed_url)
        if not feed:
            continue

        max_entries = 12 if "🇲🇻" in source_name else 8

        for entry in getattr(feed, "entries", [])[:max_entries]:
            article = parse_rss_entry(source_name, entry)

            if not article or article["id"] in seen_ids:
                continue

            # Mark every inspected article as seen so irrelevant general-news
            # items from broad Maldivian feeds are not re-processed endlessly.
            state.setdefault("seen_ids", []).append(article["id"])
            seen_ids.add(article["id"])

            if not is_environment_story(article):
                logging.debug("Environment filter rejected: %s", article["title"])
                continue

            collected_articles.append(article)

    logging.info("Collected %s new climate/environment articles.", len(collected_articles))
    return collected_articles


# ============================================================
# DUPLICATE STORY MERGING
# ============================================================

def normalize_title(title):
    normalized = clean_text(title).lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    ignored_words = {
        "breaking", "latest", "live", "update", "updates", "news",
        "report", "reports", "says", "climate", "environment",
    }
    return " ".join(word for word in normalized.split() if word not in ignored_words)


def headline_similarity(first, second):
    first = normalize_title(first)
    second = normalize_title(second)

    if not first or not second:
        return 0.0

    sequence_score = SequenceMatcher(None, first, second).ratio()
    first_words = set(first.split())
    second_words = set(second.split())
    word_score = (
        len(first_words & second_words) / len(first_words | second_words)
        if first_words and second_words
        else 0.0
    )
    return max(sequence_score, word_score)


def cluster_articles(articles):
    clusters = []

    articles.sort(
        key=lambda article: (
            0 if is_maldives_story(article) else 1,
            0 if is_breaking_story(article) else 1,
            -calculate_importance(article),
        )
    )

    for article in articles:
        matching_cluster = None
        highest_similarity = 0.0

        for cluster in clusters:
            representative = cluster["articles"][0]
            similarity = headline_similarity(article["title"], representative["title"])

            if similarity >= DUPLICATE_SIMILARITY_THRESHOLD and similarity > highest_similarity:
                matching_cluster = cluster
                highest_similarity = similarity

        if matching_cluster:
            matching_cluster["articles"].append(article)
            matching_cluster["publishers"].add(article["publisher"])
            if not matching_cluster.get("image") and article.get("image"):
                matching_cluster["image"] = article["image"]
        else:
            clusters.append(
                {
                    "articles": [article],
                    "publishers": {article["publisher"]},
                    "image": article.get("image"),
                }
            )

    return clusters


# ============================================================
# SUMMARIES AND OPTIONAL GEMINI ANALYSIS
# ============================================================

def local_summary(article, cluster_articles=None):
    descriptions = [article.get("description", "")]
    if cluster_articles:
        descriptions.extend(item.get("description", "") for item in cluster_articles[1:3])

    sentences = split_sentences(" ".join(descriptions))
    selected = []

    for sentence in sentences:
        if sentence.lower() in {item.lower() for item in selected}:
            continue
        selected.append(shorten_text(sentence, 260))
        if len(selected) == 2:
            break

    if not selected:
        selected.append(shorten_text(article.get("title", ""), 240))

    if len(selected) < 2:
        selected.append("Open the original source below for the complete report.")

    return selected[:2]


def ai_is_in_cooldown():
    disabled_until = state.get("ai_disabled_until")
    if not disabled_until:
        return False

    try:
        if utc_now() < datetime.fromisoformat(disabled_until):
            return True
    except Exception:
        pass

    state["ai_disabled_until"] = None
    return False


def ai_hourly_limit_reached():
    cleanup_state()
    return len(state.get("ai_request_times", [])) >= MAX_AI_REQUESTS_PER_HOUR


def record_ai_request():
    state.setdefault("ai_request_times", []).append(utc_now_iso())
    save_state()


def activate_ai_cooldown():
    state["ai_disabled_until"] = (
        utc_now() + timedelta(minutes=AI_QUOTA_COOLDOWN_MINUTES)
    ).isoformat()
    save_state()


def gemini_generate(prompt, max_tokens=600):
    if not GEMINI_API_KEY or ai_is_in_cooldown() or ai_hourly_limit_reached():
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }

    record_ai_request()

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=75)
        if response.status_code == 429:
            activate_ai_cooldown()
            return None
        if response.status_code != 200:
            logging.error("Gemini error %s: %s", response.status_code, response.text[:500])
            return None

        candidates = response.json().get("candidates", [])
        if not candidates:
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts).strip() or None
    except requests.RequestException as error:
        logging.error("Gemini connection error: %s", error)
        return None


def extract_json_object(text):
    if not text:
        return None

    text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        return None

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def should_use_ai(cluster, local_score, ai_used_this_check):
    if not GEMINI_API_KEY:
        return False
    if ai_used_this_check >= MAX_AI_REQUESTS_PER_CHECK:
        return False
    if ai_is_in_cooldown():
        return False

    first_article = cluster["articles"][0]
    return (
        local_score >= MINIMUM_AI_SCORE
        or (is_maldives_story(first_article) and local_score >= 70)
        or is_breaking_story(first_article)
    )


def analyze_cluster_with_ai(cluster):
    reports = []

    for index, article in enumerate(cluster["articles"][:4], start=1):
        reports.append(
            f"""Report {index}
Publisher: {article['publisher']}
Headline: {article['title']}
Description: {shorten_text(article['description'], 1300)}"""
        )

    prompt = f"""
You edit a climate and environmental news channel focused on the Maldives and the world.

Return only one JSON object:
{{
  "headline": "Clear factual headline",
  "summary": ["Sentence one", "Sentence two"],
  "why_it_matters": "One short factual sentence",
  "category": "Environment",
  "breaking": false,
  "importance_score": 80
}}

Rules:
1. Use only facts contained in the supplied reports.
2. Do not add facts, causes, numbers, locations, or conclusions that are not stated.
3. The story must be about climate change, environment, oceans, coral reefs,
   biodiversity, wildlife, conservation, pollution, waste, forests, mangroves,
   clean energy, environmental science, climate policy, or a major environmental hazard.
4. Allowed categories: {", ".join(CATEGORY_EMOJIS.keys())}.
5. Use exactly two concise summary sentences.
6. "breaking" is true only for an urgent environmental or climate development.
7. importance_score must be 0-100.

Reports:

{chr(10).join(reports)}
""".strip()

    data = extract_json_object(gemini_generate(prompt))
    if not data:
        return None

    summary = data.get("summary", [])
    if not isinstance(summary, list):
        return None

    summary = [clean_text(item) for item in summary if clean_text(item)][:2]
    if len(summary) != 2:
        return None

    category = clean_text(data.get("category", "Environment"))
    if category not in CATEGORY_EMOJIS:
        category = "Environment"

    try:
        importance_score = int(data.get("importance_score", 75))
    except Exception:
        importance_score = 75

    return {
        "headline": clean_text(data.get("headline", cluster["articles"][0]["title"])),
        "summary": summary,
        "why_it_matters": clean_text(data.get("why_it_matters", "")),
        "category": category,
        "breaking": bool(data.get("breaking", False)),
        "importance_score": max(0, min(100, importance_score)),
        "used_ai": True,
    }


def local_cluster_analysis(cluster, local_score):
    first_article = cluster["articles"][0]
    return {
        "headline": first_article["title"],
        "summary": local_summary(first_article, cluster["articles"]),
        "why_it_matters": "",
        "category": (
            "Maldives Environment"
            if is_maldives_story(first_article) and detect_category(first_article) == "Environment"
            else detect_category(first_article)
        ),
        "breaking": is_breaking_story(first_article),
        "importance_score": local_score,
        "used_ai": False,
    }


# ============================================================
# TELEGRAM API AND POST FORMAT
# ============================================================

def telegram_api(method, payload=None, timeout=40):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"

    try:
        response = requests.post(url, json=payload or {}, timeout=timeout)
        try:
            result = response.json()
        except Exception:
            logging.error("Telegram returned invalid JSON: %s", response.text[:500])
            return None

        if response.status_code != 200 or not result.get("ok"):
            logging.error(
                "Telegram %s error: %s",
                method,
                result.get("description", response.text[:500]),
            )
            return None

        return result.get("result")
    except requests.RequestException as error:
        logging.error("Telegram connection error: %s", error)
        return None


def send_message(text, chat_id=GROUP_CHAT_ID, disable_preview=False, reply_markup=None):
    payload = {
        "chat_id": str(chat_id),
        "text": shorten_text(text, 4000),
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return telegram_api("sendMessage", payload)


def send_photo(photo_url, caption, chat_id=GROUP_CHAT_ID, reply_markup=None):
    payload = {
        "chat_id": str(chat_id),
        "photo": photo_url,
        "caption": shorten_text(caption, 1000),
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return telegram_api("sendPhoto", payload)


def build_source_buttons(cluster):
    buttons = []
    added_links = set()

    for article in cluster.get("articles", [])[:5]:
        link = article.get("link")
        publisher = article.get("publisher", "Original source")

        if (
            not link
            or link in added_links
            or not link.startswith(("http://", "https://"))
        ):
            continue

        added_links.add(link)
        buttons.append(
            {
                "text": shorten_text(f"🔗 Read on {publisher}", 45),
                "url": link,
            }
        )

    return {"inline_keyboard": [[button] for button in buttons]} if buttons else None


def public_command_keyboard():
    return {
        "keyboard": [
            [{"text": "📰 Latest"}, {"text": "🔥 Trending"}],
            [{"text": "🇲🇻 Maldives"}, {"text": "🌍 Global"}],
            [{"text": "🌡️ Climate"}, {"text": "🌊 Oceans & Reefs"}],
            [{"text": "🦋 Wildlife"}, {"text": "♻️ Pollution & Waste"}],
            [{"text": "🌱 Conservation"}, {"text": "⚡ Clean Energy"}],
            [{"text": "❓ Help"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose a climate/environment section...",
    }


PUBLIC_COMMANDS = [
    {"command": "help", "description": "Show the climate & environment menu"},
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
    {"command": "search", "description": "Search recent environmental stories"},
]


def register_public_commands():
    return telegram_api("setMyCommands", {"commands": PUBLIC_COMMANDS})


def calculate_trending_score(cluster, analysis):
    score = analysis["importance_score"] * 0.62
    score += min(len(cluster["publishers"]) * 11, 30)

    if analysis["breaking"]:
        score += 10
    if is_maldives_story(cluster["articles"][0]):
        score += 8

    return min(100, round(score))


def build_news_message(cluster, analysis, trend_score):
    category = analysis["category"]
    emoji = CATEGORY_EMOJIS.get(category, "🌍")
    first_article = cluster["articles"][0]

    heading = ""
    if analysis["breaking"]:
        heading = "🚨 <b>ENVIRONMENT ALERT</b>\n\n"
    elif trend_score >= 84:
        heading = "🔥 <b>TRENDING ENVIRONMENT STORY</b>\n\n"

    region = "🇲🇻 Maldives" if is_maldives_story(first_article) else "🌍 Global"
    language = " · Dhivehi" if is_dhivehi_story(first_article) else ""

    message = (
        f"{heading}"
        f"{emoji} <b>{html.escape(category)}</b> · {region}{language}\n\n"
        f"📰 <b>{html.escape(analysis['headline'])}</b>\n\n"
        f"• {html.escape(analysis['summary'][0])}\n"
        f"• {html.escape(analysis['summary'][1])}\n"
    )

    if analysis.get("why_it_matters"):
        message += (
            "\n💡 <b>Why it matters:</b>\n"
            f"{html.escape(analysis['why_it_matters'])}\n"
        )

    publishers = html.escape(", ".join(sorted(cluster["publishers"])))
    message += (
        f"\n📊 <b>Trending score:</b> {trend_score}/100\n"
        f"🏢 <b>Sources:</b> {publishers}\n\n"
        "👇 Open the original reporting below."
    )

    if len(cluster["articles"]) > 1:
        message += f"\n\n🧩 Combined from {len(cluster['articles'])} related reports."

    return message


def publish_post(message, image_url=None, source_buttons=None):
    if image_url:
        result = send_photo(image_url, message, reply_markup=source_buttons)
        if result:
            return result
        logging.warning("Image failed; falling back to text post.")

    return send_message(message, reply_markup=source_buttons)


# ============================================================
# HISTORY
# ============================================================

def save_to_history(cluster, analysis, trend_score):
    first_article = cluster["articles"][0]
    state.setdefault("history", []).append(
        {
            "created_at": utc_now_iso(),
            "headline": analysis["headline"],
            "summary": analysis["summary"],
            "category": analysis["category"],
            "breaking": analysis["breaking"],
            "importance_score": analysis["importance_score"],
            "trending_score": trend_score,
            "publishers": sorted(cluster["publishers"]),
            "link": first_article["link"],
            "maldives": is_maldives_story(first_article),
            "dhivehi": is_dhivehi_story(first_article),
            "used_ai": analysis["used_ai"],
        }
    )


def recent_history(hours=48):
    cutoff = utc_now() - timedelta(hours=hours)
    results = []

    for item in state.get("history", []):
        try:
            if datetime.fromisoformat(item["created_at"]) >= cutoff:
                results.append(item)
        except Exception:
            continue

    return results


# ============================================================
# MAIN NEWS CHECK
# ============================================================

async def check_and_publish_news():
    logging.info("Collecting climate and environment news...")

    articles = await asyncio.to_thread(fetch_new_articles)
    if not articles:
        state["last_news_check"] = utc_now_iso()
        save_state()
        logging.info("No new relevant stories.")
        return

    clusters = cluster_articles(articles)
    ranked = []

    for cluster in clusters:
        highest_score = max(calculate_importance(article) for article in cluster["articles"])
        highest_score += min((len(cluster["publishers"]) - 1) * 6, 18)
        ranked.append({"cluster": cluster, "local_score": min(100, highest_score)})

    ranked.sort(
        key=lambda item: (
            0 if is_maldives_story(item["cluster"]["articles"][0]) else 1,
            0 if is_breaking_story(item["cluster"]["articles"][0]) else 1,
            -item["local_score"],
            -len(item["cluster"]["publishers"]),
        )
    )

    posted_count = 0
    ai_used_this_check = 0

    for item in ranked:
        if posted_count >= MAX_POSTS_PER_CHECK:
            break

        cluster = item["cluster"]
        local_score = item["local_score"]
        first_article = cluster["articles"][0]

        if not is_environment_story(first_article) or local_score < MINIMUM_POST_SCORE:
            continue

        analysis = None

        if should_use_ai(cluster, local_score, ai_used_this_check):
            analysis = await asyncio.to_thread(analyze_cluster_with_ai, cluster)
            if analysis:
                ai_used_this_check += 1

        if not analysis:
            analysis = local_cluster_analysis(cluster, local_score)

        trend_score = calculate_trending_score(cluster, analysis)
        message = build_news_message(cluster, analysis, trend_score)
        buttons = build_source_buttons(cluster)

        published = await asyncio.to_thread(
            publish_post,
            message,
            cluster.get("image"),
            buttons,
        )

        if published:
            save_to_history(cluster, analysis, trend_score)
            posted_count += 1
            await asyncio.sleep(MESSAGE_DELAY_SECONDS)

    state["last_news_check"] = utc_now_iso()
    save_state()
    logging.info("Completed: %s posts, %s AI requests.", posted_count, ai_used_this_check)


# ============================================================
# DIGESTS AND COMMANDS
# ============================================================

def build_digest(title, hours):
    stories = recent_history(hours)

    if not stories:
        return (
            f"🌿 <b>{html.escape(title)}</b>\n\n"
            "No new climate or environmental stories were published in this period."
        )

    stories.sort(
        key=lambda story: (
            0 if story.get("maldives") else 1,
            0 if story.get("breaking") else 1,
            -story.get("trending_score", 0),
        )
    )

    message = (
        f"🌿 <b>{html.escape(title)}</b>\n\n"
        f"From <b>{BOT_NAME}</b>\n\n"
    )

    for index, story in enumerate(stories[:12], start=1):
        category = story.get("category", "Environment")
        emoji = CATEGORY_EMOJIS.get(category, "🌍")
        headline = html.escape(story.get("headline", "Untitled report"))
        link = html.escape(story.get("link", ""), quote=True)
        region = "🇲🇻" if story.get("maldives") else "🌍"

        message += (
            f'{index}. {region} {emoji} <a href="{link}">{headline}</a>\n'
            f"   📊 {story.get('trending_score', 0)}/100\n\n"
        )

    return shorten_text(message, 3900)


async def digest_scheduler():
    while True:
        now = maldives_now()
        today = now.date().isoformat()

        if (
            now.hour == MORNING_DIGEST_HOUR
            and now.minute < 5
            and state.get("last_morning_digest") != today
        ):
            await asyncio.to_thread(
                send_message,
                build_digest("Morning Climate & Environment Brief", 12),
            )
            state["last_morning_digest"] = today
            save_state()

        if (
            now.hour == EVENING_DIGEST_HOUR
            and now.minute < 5
            and state.get("last_evening_digest") != today
        ):
            await asyncio.to_thread(
                send_message,
                build_digest("Evening Climate & Environment Brief", 12),
            )
            state["last_evening_digest"] = today
            save_state()

        await asyncio.sleep(60)


HELP_TEXT = f"""
🌿 <b>Welcome to {BOT_NAME}</b>

This bot publishes only climate and environmental news from the Maldives and around the world.

Covered topics:
🇲🇻 Maldives environment and climate
🌡️ Climate change and extreme weather
🌊 Oceans, coral reefs and marine ecosystems
🦋 Biodiversity and wildlife
♻️ Pollution, plastics and waste
🌱 Conservation and ecosystem restoration
🌳 Forests and mangroves
⚡ Renewable and clean energy
🏛️ Climate policy and finance
🔬 Environmental science and research

General politics, sports, entertainment, technology and business stories are excluded unless they are directly about climate or the environment.

Search recent stories with:
<code>/search coral bleaching</code>
""".strip()


def filter_history(category_names=None, maldives_only=False, global_only=False, query=None, limit=8):
    stories = list(reversed(state.get("history", [])))
    results = []
    accepted = {name.lower() for name in category_names} if category_names else set()

    for story in stories:
        if maldives_only and not story.get("maldives"):
            continue
        if global_only and story.get("maldives"):
            continue
        if accepted and story.get("category", "").lower() not in accepted:
            continue

        if query:
            searchable = " ".join(
                [
                    story.get("headline", ""),
                    " ".join(story.get("summary", [])),
                    " ".join(story.get("publishers", [])),
                    story.get("category", ""),
                ]
            ).lower()
            terms = [term for term in query.lower().split() if term]
            if not all(term in searchable for term in terms):
                continue

        results.append(story)
        if len(results) >= limit:
            break

    return results


def build_story_list(title, stories):
    if not stories:
        return (
            f"🌿 <b>{html.escape(title)}</b>\n\n"
            "No matching climate or environmental stories are available yet."
        )

    message = f"🌿 <b>{html.escape(title)}</b>\n\n"

    for index, story in enumerate(stories, start=1):
        category = story.get("category", "Environment")
        emoji = CATEGORY_EMOJIS.get(category, "🌍")
        headline = html.escape(story.get("headline", "Untitled report"))
        link = html.escape(story.get("link", ""), quote=True)
        region = "🇲🇻" if story.get("maldives") else "🌍"

        message += (
            f'{index}. {region} {emoji} <a href="{link}">{headline}</a>\n'
            f"   📊 Trending: {story.get('trending_score', 0)}/100\n\n"
        )

    return shorten_text(message, 3900)


def handle_command(message):
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")

    button_commands = {
        "📰 Latest": "/latest",
        "🔥 Trending": "/trending",
        "🇲🇻 Maldives": "/maldives",
        "🌍 Global": "/global",
        "🌡️ Climate": "/climate",
        "🌊 Oceans & Reefs": "/oceans",
        "🦋 Wildlife": "/wildlife",
        "♻️ Pollution & Waste": "/pollution",
        "🌱 Conservation": "/conservation",
        "⚡ Clean Energy": "/energy",
        "❓ Help": "/help",
    }

    text = button_commands.get(text, text)
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    command = parts[0].split("@")[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command in {"/start", "/help"}:
        send_message(HELP_TEXT, chat_id, reply_markup=public_command_keyboard())
    elif command == "/latest":
        send_message(build_story_list("Latest Climate & Environment News", filter_history(limit=8)), chat_id)
    elif command == "/trending":
        stories = recent_history(48)
        stories.sort(key=lambda story: story.get("trending_score", 0), reverse=True)
        send_message(build_story_list("Trending Climate & Environment Stories", stories[:8]), chat_id)
    elif command == "/maldives":
        send_message(build_story_list("Maldives Climate & Environment", filter_history(maldives_only=True, limit=8)), chat_id)
    elif command in {"/global", "/world"}:
        send_message(build_story_list("Global Climate & Environment", filter_history(global_only=True, limit=8)), chat_id)
    elif command == "/climate":
        send_message(
            build_story_list(
                "Climate Change & Extreme Weather",
                filter_history(category_names={"Climate Change", "Extreme Weather", "Climate Policy & Finance"}, limit=8),
            ),
            chat_id,
        )
    elif command == "/oceans":
        send_message(build_story_list("Oceans & Reefs", filter_history(category_names={"Oceans & Reefs"}, limit=8)), chat_id)
    elif command == "/wildlife":
        send_message(build_story_list("Biodiversity & Wildlife", filter_history(category_names={"Biodiversity & Wildlife"}, limit=8)), chat_id)
    elif command == "/pollution":
        send_message(build_story_list("Pollution & Waste", filter_history(category_names={"Pollution & Waste"}, limit=8)), chat_id)
    elif command == "/conservation":
        send_message(
            build_story_list(
                "Conservation & Restoration",
                filter_history(category_names={"Conservation & Restoration", "Forests & Mangroves"}, limit=8),
            ),
            chat_id,
        )
    elif command == "/energy":
        send_message(build_story_list("Clean Energy", filter_history(category_names={"Clean Energy"}, limit=8)), chat_id)
    elif command == "/search":
        if not argument:
            send_message(
                "🔎 <b>Search climate & environment news</b>\n\n"
                "Example:\n<code>/search coral bleaching</code>",
                chat_id,
            )
        else:
            send_message(build_story_list(f"Search results: {argument}", filter_history(query=argument, limit=10)), chat_id)
    else:
        send_message(
            "Use /help to view the climate and environment menu.",
            chat_id,
            reply_markup=public_command_keyboard(),
        )


# ============================================================
# TELEGRAM LONG POLLING AND STARTUP
# ============================================================

def get_updates():
    return telegram_api(
        "getUpdates",
        {
            "offset": state.get("telegram_offset", 0),
            "timeout": 25,
            "allowed_updates": ["message"],
        },
        timeout=35,
    )


async def command_listener():
    while True:
        updates = await asyncio.to_thread(get_updates)

        if not updates:
            await asyncio.sleep(2)
            continue

        for update in updates:
            state["telegram_offset"] = update.get("update_id", 0) + 1
            message = update.get("message")

            if message:
                try:
                    await asyncio.to_thread(handle_command, message)
                except Exception as error:
                    logging.exception("Command error: %s", error)

            save_state()


async def automatic_news_loop():
    while True:
        try:
            await check_and_publish_news()
        except Exception as error:
            logging.exception("News check failed: %s", error)

        logging.info(
            "Waiting %.1f minutes before the next check.",
            NEWS_CHECK_INTERVAL_SECONDS / 60,
        )
        await asyncio.sleep(NEWS_CHECK_INTERVAL_SECONDS)


def validate_configuration():
    missing = []

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not GROUP_CHAT_ID:
        missing.append("GROUP_CHAT_ID")

    if missing:
        raise ValueError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )

    if not GEMINI_API_KEY:
        logging.warning("GEMINI_API_KEY is not set; local summaries will be used.")


def test_telegram_connection():
    bot_information = telegram_api("getMe")
    if not bot_information:
        return False

    logging.info(
        "Connected to Telegram as @%s",
        bot_information.get("username", "unknown_bot"),
    )
    return True


def build_welcome_message():
    return f"""
🌿 <b>{BOT_NAME}</b>

The bot is now focused only on climate and environmental news.

🇲🇻 Maldives climate & environment
🌍 Global climate & environment
🌊 Coral reefs, oceans and marine ecosystems
🦋 Biodiversity and wildlife
♻️ Pollution, plastics and waste
🌱 Conservation and restoration
🌳 Forests and mangroves
⚡ Clean energy
🚨 Major environmental hazards

General news is filtered out unless it directly relates to climate or the environment.
""".strip()


async def main():
    validate_configuration()
    logging.info("Starting %s...", BOT_NAME)

    if not await asyncio.to_thread(test_telegram_connection):
        logging.error("Telegram connection failed.")
        return

    await asyncio.to_thread(register_public_commands)
    await asyncio.to_thread(
        send_message,
        build_welcome_message(),
        GROUP_CHAT_ID,
        False,
        public_command_keyboard(),
    )

    await asyncio.gather(
        automatic_news_loop(),
        command_listener(),
        digest_scheduler(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped.", BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
