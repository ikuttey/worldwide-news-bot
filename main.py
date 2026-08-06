import asyncio
import hashlib
import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus, urljoin

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
# BASIC CONFIGURATION
# ============================================================

BOT_NAME = "Worldwide News"

TELEGRAM_BOT_TOKEN = "8798817185:AAFHH3NorVx6X0_pTbUjcoksAT0s444w1IQ"

# Your Telegram group ID
GROUP_CHAT_ID = "-5388255576"

# Gemini is optional.
# Leave this empty to use only free local summaries.
GEMINI_API_KEY = "AQ.Ab8RN6IqJFSmL4pLqFac3rGW3BJ8zs9Eq4q6hs_xtE1Gay1syQ"

GEMINI_MODEL = "gemini-2.5-flash"

# Check news every 2 minutes for breaking news
NEWS_CHECK_INTERVAL_SECONDS = 120  # 2 minutes

# Maximum posts published during each check.
MAX_POSTS_PER_CHECK = 50

# Delay between Telegram posts.
MESSAGE_DELAY_SECONDS = 2

# Stories below this score will normally not be posted.
MINIMUM_POST_SCORE = 5  # Very low to catch all news

# AI is used only for highly important stories.
MINIMUM_AI_SCORE = 80

# Maximum AI requests in a single news check.
MAX_AI_REQUESTS_PER_CHECK = 2

# Maximum AI requests in one hour.
MAX_AI_REQUESTS_PER_HOUR = 10

# Stop using AI temporarily after a quota error.
AI_QUOTA_COOLDOWN_MINUTES = 30

# Similarity required to merge duplicate stories.
DUPLICATE_SIMILARITY_THRESHOLD = 0.66

# Keep published history for seven days.
HISTORY_RETENTION_DAYS = 7

# Maldives time: UTC+5
MALDIVES_TIMEZONE = timezone(timedelta(hours=5))

# Scheduled daily digests.
MORNING_DIGEST_HOUR = 7
EVENING_DIGEST_HOUR = 19

STATE_FILE = Path("worldwide_news_state.json")


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


# ============================================================
# REAL-TIME MALDIVES NEWS SOURCES (ENGLISH + DHIVEHI)
# ============================================================

# Direct RSS feeds from Maldivian news sites
RSS_FEEDS = {
    # English Maldives News
    "🇲🇻 PSM News (English)": "https://psmnews.mv/feed",
    "🇲🇻 Sun Online (English)": "https://sun.mv/rss",
    "🇲🇻 Dhiyares (English)": "https://dhiyares.com/rss",
    "🇲🇻 Adhadhu (English)": "https://adhadhu.com/rss",
    "🇲🇻 VNews (English)": "https://vnews.mv/rss",
    
    # Dhivehi Maldives News (ދިވެހި ނޫސް)
    "🇲🇻 Miadhu (Dhivehi)": "https://miadhu.com/feed",
    "🇲🇻 Dhivehi Observer (Dhivehi)": "https://dhivehiobserver.com/feed",
    "🇲🇻 Times of Addu (Dhivehi)": "https://timesofaddu.com/feed",
    
    # Google News - ENGLISH queries for Maldives
    "🇲🇻 Google English Top": google_news_feed("Maldives when:1h", region="MV", language="en"),
    "🇲🇻 Google English Breaking": google_news_feed("Maldives breaking when:1h", region="MV", language="en"),
    "🇲🇻 Google English Latest": google_news_feed("Maldives latest when:1h", region="MV", language="en"),
    "🇲🇻 Google English News": google_news_feed("Maldives news when:1h", region="MV", language="en"),
    "🇲🇻 Google English President": google_news_feed("Maldives president when:1h", region="MV", language="en"),
    "🇲🇻 Google English Government": google_news_feed("Maldives government when:1h", region="MV", language="en"),
    "🇲🇻 Google English Economy": google_news_feed("Maldives economy when:1h", region="MV", language="en"),
    "🇲🇻 Google English Tourism": google_news_feed("Maldives tourism when:1h", region="MV", language="en"),
    "🇲🇻 Google English Sports": google_news_feed("Maldives sports when:1h", region="MV", language="en"),
    "🇲🇻 Google English Environment": google_news_feed("Maldives environment when:1h", region="MV", language="en"),
    
    # Google News - DHIVEHI queries for Maldives (ދިވެހި)
    "🇲🇻 Google Dhivehi Top": google_news_feed("ދިވެހި ނޫސް when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi Breaking": google_news_feed("ދިވެހި ބްރޭކިންގ when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi Latest": google_news_feed("ދިވެހި އެންމެ ފަހު when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi News": google_news_feed("ދިވެހި ނޫސް ޚަބަރު when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi President": google_news_feed("ރައީސް when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi Government": google_news_feed("ސަރުކާރު when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi Parliament": google_news_feed("މަޖިލިސް when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi Economy": google_news_feed("އިޤްތިޞާދު when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi Tourism": google_news_feed("ޓޫރިޒަމް when:1h", region="MV", language="dv"),
    "🇲🇻 Google Dhivehi Sports": google_news_feed("ސްޕޯޓް when:1h", region="MV", language="dv"),
}

# International RSS feeds
INTERNATIONAL_RSS = {
    "🌍 BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "🌍 The Guardian": "https://www.theguardian.com/world/rss",
    "🌍 Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "🌍 NPR World": "https://feeds.npr.org/1004/rss.xml",
    "🇬🇧 BBC UK": "https://feeds.bbci.co.uk/news/uk/rss.xml",
    "🇺🇸 NYT World": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "🇮🇳 NDTV": "https://feeds.feedburner.com/ndtvnews-top-stories",
    "🇮🇳 The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "💰 CNBC World": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "💻 TechCrunch": "https://techcrunch.com/feed/",
    "🌊 NASA": "https://www.nasa.gov/news-release/feed/",
    "⚽ BBC Sport": "https://feeds.bbci.co.uk/sport/rss.xml",
}

# Google News international
GOOGLE_INTERNATIONAL = {
    "🌍 Global Breaking": google_news_feed("breaking world news when:1h", region="US"),
    "🌍 Reuters AP": google_news_feed("Reuters OR AP world when:1h", region="US"),
    "🇺🇸 US News": google_news_feed("United States top news when:1h", region="US"),
    "🇬🇧 UK News": google_news_feed("United Kingdom top news when:1h", region="GB"),
    "🇪🇺 Europe": google_news_feed("Europe top news when:1h", region="GB"),
}


# ============================================================
# CATEGORIES - WITH DHIVEHI KEYWORDS
# ============================================================

CATEGORY_EMOJIS = {
    "Maldives": "🇲🇻",
    "World": "🌍",
    "Politics": "🏛️",
    "Business": "💰",
    "Technology": "💻",
    "AI": "🤖",
    "Environment": "🌊",
    "Climate": "🌡️",
    "Health": "🏥",
    "Science": "🔬",
    "Travel": "✈️",
    "Sports": "⚽",
    "Entertainment": "🎬",
    "Emergency": "🚨",
    "Other": "📰",
}

# Keywords in BOTH English and Dhivehi for better detection
CATEGORY_KEYWORDS = {
    "Emergency": {
        # English
        "earthquake", "tsunami", "cyclone", "hurricane", "flood",
        "explosion", "evacuation", "emergency", "landslide",
        "plane crash", "shipwreck", "wildfire", "breaking",
        "urgent", "alert", "warning",
        # Dhivehi
        "ބިންހެލުން", "ކާރިސާ", "ގޮންޖެހުން", "އެމަޖެންސީ",
        "ފެންބޮޑުވުން", "ވައިގަދަ", "ސުނާމީ",
    },
    "Maldives": {
        # English
        "maldives", "maldivian", "malé", "male", "hulhumale",
        "addu", "dhivehi", "baa atoll", "laamu", "gaafu",
        # Dhivehi
        "ދިވެހިރާއްޖެ", "ރާއްޖެ", "މާލެ", "ހުޅުމާލެ",
        "އައްޑު", "ދިވެހި", "ބ. އަތޮޅު", "ލ. އަތޮޅު",
        "ގއ. އަތޮޅު", "މާލެ ސިޓީ",
    },
    "Politics": {
        # English
        "president", "prime minister", "parliament", "election",
        "government", "minister", "senate", "congress",
        "diplomatic", "sanctions", "constitution", "vote",
        # Dhivehi
        "ރައީސް", "ވުޒީރު", "މަޖިލިސް", "އިންތިޚާބު",
        "ސަރުކާރު", "ވަޒީރު", "ޤާނޫނު", "ސިޔާސީ",
    },
    "Business": {
        # English
        "economy", "inflation", "bank", "market", "stocks",
        "business", "trade", "company", "investment",
        "currency", "finance", "gdp", "profit", "loss",
        # Dhivehi
        "އިޤްތިޞާދު", "ވިޔަފާރި", "ފައިސާ", "ފައިނޭންސް",
        "ބޭންކު", "މާކެޓް", "ސްޓޮކް",
    },
    "AI": {
        "artificial intelligence", "generative ai", "chatgpt",
        "openai", "gemini", "machine learning", "ai model",
        "އޭއައި", "އާޓިފިޝަލް އިންޓެލިޖެންސް",
    },
    "Technology": {
        "technology", "software", "cyber", "smartphone",
        "computer", "internet", "chip", "semiconductor",
        "apple", "google", "microsoft", "robot",
        "ޓެކްނޮލޮޖީ", "ސޮފްޓްވެއަރ", "އިންޓަރނެޓް",
    },
    "Environment": {
        "environment", "ocean", "coral", "reef", "wildlife",
        "pollution", "conservation", "biodiversity", "marine",
        "plastic", "waste",
        "ތިމާވެށި", "ކަނޑު", "މޫދު", "ފަރު", "ކޮރަލް",
        "ދިރިއުޅުން", "ކަނޑު ދިރިއުޅުން",
    },
    "Climate": {
        "climate change", "global warming", "heatwave",
        "weather", "carbon", "emissions", "temperature",
        "storm", "rain", "flood",
        "ކްލައިމެޓް", "ހޫނުވުން", "ވައިގެ ޙާލަތު",
    },
    "Health": {
        "health", "hospital", "disease", "virus", "outbreak",
        "vaccine", "medical", "doctor", "patient", "covid",
        "flu", "treatment",
        "ޞިއްޙަތު", "ބަލި", "ވައިރަސް", "ހޮސްޕިޓަލް",
        "ޑޮކްޓަރު", "ޓްރީޓްމެންޓް",
    },
    "Science": {
        "science", "research", "scientist", "space", "nasa",
        "discovery", "study", "astronomy", "experiment",
        "ސައިންސް", "ދިރާސާ", "ފަލަކީ",
    },
    "Travel": {
        "travel", "tourism", "airport", "airline", "flight",
        "hotel", "resort", "visa", "passenger", "cruise",
        "ޓޫރިޒަމް", "މުސާފިރު", "ރިސޯޓް", "އެއަރޕޯޓް",
        "ފްލައިޓް", "ހޮޓެލް",
    },
    "Sports": {
        "football", "soccer", "cricket", "tennis", "basketball",
        "championship", "league", "tournament", "world cup",
        "olympics", "match", "goal", "win", "victory",
        "ފުޓްބޯޅަ", "ކްރިކެޓް", "ސްޕޯޓް", "މެޗު",
        "ޗެމްޕިއަންޝިޕް", "ލީގު",
    },
    "Entertainment": {
        "film", "movie", "music", "actor", "actress",
        "celebrity", "television", "concert", "award",
        "song", "album",
        "ފިލްމު", "މިއުޒިކް", "ޓީވީ", "ކޮންސާޓް",
        "އެކްޓަރު", "ސެލެބްރިޓީ",
    },
}

BREAKING_KEYWORDS = {
    # English
    "breaking", "urgent", "emergency", "earthquake", "tsunami",
    "cyclone", "hurricane", "flood", "explosion", "attack",
    "missile", "war", "ceasefire", "evacuation", "landslide",
    "terror", "assassination", "coup", "state of emergency",
    "killed", "dead", "resigns", "arrested", "charged",
    "alert", "warning", "immediate",
    # Dhivehi
    "ބްރޭކިންގ", "ކާރިސާ", "އެމަޖެންސީ", "ބިންހެލުން",
    "ސުނާމީ", "ގޮންޖެހުން", "އެލާޓް", "ވާރނިންގ",
}

HIGH_IMPORTANCE_KEYWORDS = {
    # English
    "president", "prime minister", "government", "election",
    "parliament", "war", "ceasefire", "sanctions", "economy",
    "inflation", "interest rate", "recession", "earthquake",
    "tsunami", "cyclone", "hurricane", "emergency", "outbreak",
    "pandemic", "airport closed", "climate", "coral bleaching",
    "death", "killed", "injury",
    # Dhivehi
    "ރައީސް", "ވުޒީރު", "ސަރުކާރު", "އިންތިޚާބު",
    "މަޖިލިސް", "އިޤްތިޞާދު", "ކާރިސާ", "އެމަޖެންސީ",
}

LOW_IMPORTANCE_KEYWORDS = {
    "opinion", "recipe", "horoscope", "fashion", "shopping",
    "celebrity style", "photo gallery", "quiz", "sponsored",
    "promotion", "discount", "advertisement",
    "އޮޕިނިއަން", "ފެޝަން", "ޝޮޕިންގ",
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

    state["seen_ids"] = state.get("seen_ids", [])[-10000:]
    state["history"] = state.get("history", [])[-1500:]
    state["ai_request_times"] = state.get("ai_request_times", [])[-100:]

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
    except Exception as error:
        logging.error("Could not save state: %s", error)


# ============================================================
# GENERAL TEXT HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    text = str(value)

    text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


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


# ============================================================
# RSS DOWNLOAD FUNCTION
# ============================================================

def download_rss_feed(source_name, feed_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(feed_url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()

        parsed_feed = feedparser.parse(response.content)

        return parsed_feed

    except Exception as error:
        logging.debug(f"RSS feed unavailable — {source_name}: {error}")
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

    article_id = (
        entry.get("id")
        or entry.get("guid")
        or article_hash(source_name, title, link)
    )

    publisher = source_name

    # Try to get image
    image = None
    media_content = entry.get("media_content", [])
    if media_content and isinstance(media_content, list):
        for item in media_content:
            if isinstance(item, dict) and item.get("url"):
                image = item["url"]
                break

    if not image:
        enclosures = entry.get("enclosures", [])
        if enclosures and isinstance(enclosures, list):
            for enclosure in enclosures:
                if isinstance(enclosure, dict) and enclosure.get("url"):
                    if "image" in enclosure.get("type", ""):
                        image = enclosure["url"]
                        break

    return {
        "id": str(article_id),
        "source": source_name,
        "publisher": publisher,
        "title": title,
        "description": description,
        "link": str(link),
        "image": image,
        "timestamp": entry.get("published", utc_now_iso()),
    }


# ============================================================
# FETCH ALL NEWS - ENGLISH + DHIVEHI
# ============================================================

def fetch_new_articles():
    seen_ids = set(state.get("seen_ids", []))
    collected_articles = []

    # Combine all RSS feeds
    all_rss = {**RSS_FEEDS, **INTERNATIONAL_RSS, **GOOGLE_INTERNATIONAL}
    
    # Process Maldives feeds first (priority) - English + Dhivehi
    maldives_feeds = {
        name: url for name, url in all_rss.items() if "🇲🇻" in name
    }
    
    # Process international feeds
    international_feeds = {
        name: url for name, url in all_rss.items() if "🇲🇻" not in name
    }
    
    ordered_feeds = list(maldives_feeds.items()) + list(international_feeds.items())

    for source_name, feed_url in ordered_feeds:
        # Log all Maldives feeds
        if "🇲🇻" in source_name:
            logging.info(f"Checking: {source_name}")
        
        feed = download_rss_feed(source_name, feed_url)
        if not feed:
            continue
            
        entries = getattr(feed, "entries", [])
        
        # Get more entries for Maldives feeds
        max_entries = 10 if "🇲🇻" in source_name else 5
        
        for entry in entries[:max_entries]:
            article = parse_rss_entry(source_name, entry)
            
            if not article:
                continue
                
            if article["id"] in seen_ids:
                continue
                
            # Mark as seen immediately to avoid duplicates in same check
            state["seen_ids"].append(article["id"])
            collected_articles.append(article)

    logging.info(f"Total new articles collected: {len(collected_articles)}")
    return collected_articles


# ============================================================
# LOCAL NEWS ANALYSIS - DHIVEHI AWARE
# ============================================================

def combined_article_text(article):
    return (
        article.get("source", "")
        + " "
        + article.get("publisher", "")
        + " "
        + article.get("title", "")
        + " "
        + article.get("description", "")
    ).lower()


def detect_category(article):
    text = combined_article_text(article)

    category_scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        category_scores[category] = sum(1 for keyword in keywords if keyword in text)

    best_category = max(category_scores, key=category_scores.get)

    if category_scores[best_category] == 0:
        return "World"

    return best_category


def is_maldives_story(article):
    # Check if it's from a Maldives source
    source = article.get("source", "").lower()
    if any(marker in source for marker in ["maldives", "psm", "sun", "raajje", "mihaaru", 
                                           "adhadhu", "miadhu", "dhiyares", "vnews",
                                           "dhivehi", "ދިވެހި"]):
        return True
    
    # Check content for Maldives indicators
    text = combined_article_text(article)
    maldives_indicators = [
        "maldives", "maldivian", "malé", "male", "hulhumale", "addu",
        "ދިވެހިރާއްޖެ", "ރާއްޖެ", "މާލެ", "ހުޅުމާލެ", "އައްޑު",
        "baa atoll", "laamu", "gaafu"
    ]
    
    return any(indicator in text for indicator in maldives_indicators)


def is_breaking_story(article):
    text = combined_article_text(article)

    return any(keyword in text for keyword in BREAKING_KEYWORDS)


def is_dhivehi_story(article):
    """Detect if the article is in Dhivehi language"""
    text = combined_article_text(article)
    # Look for Dhivehi script (ހ-ި range)
    dhivehi_pattern = re.compile(r'[\u0780-\u07BF]')
    matches = dhivehi_pattern.findall(text)
    # If more than 10% of characters are Dhivehi, it's a Dhivehi story
    if len(text) > 0 and len(matches) > 0:
        dhivehi_ratio = len(matches) / len(text)
        return dhivehi_ratio > 0.05  # 5% Dhivehi characters
    return False


def calculate_local_importance(article):
    text = combined_article_text(article)

    # Base score
    score = 25
    
    # MALDIVES BONUS - High priority
    if is_maldives_story(article):
        score += 40  # Big boost for Maldives stories
    
    # DHIVEHI BONUS - Give extra priority to Dhivehi news
    if is_dhivehi_story(article):
        score += 15  # Boost for Dhivehi language news
    
    # BREAKING NEWS - High priority
    if is_breaking_story(article):
        score += 35  # Big boost for breaking news
    
    # Source reputation bonus
    source = article.get("source", "").lower()
    if any(s in source for s in ["psm", "sun", "raajje", "mihaaru", "adhadhu", 
                                  "miadhu", "dhiyares", "vnews", "dhivehi", "google"]):
        score += 10
    
    # Google News Dhivehi sources get extra boost
    if "dhivehi" in source:
        score += 8
    
    # Keywords boost
    important_hits = sum(1 for keyword in HIGH_IMPORTANCE_KEYWORDS if keyword in text)
    score += min(important_hits * 5, 25)
    
    # Penalize low-value content
    low_value_hits = sum(1 for keyword in LOW_IMPORTANCE_KEYWORDS if keyword in text)
    score -= min(low_value_hits * 8, 24)

    return max(0, min(100, score))


# ============================================================
# DUPLICATE STORY MERGING
# ============================================================

def normalize_title(title):
    normalized = clean_text(title).lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    ignored_words = {"breaking", "latest", "live", "update", "updates", "news", "report", "reports", "says"}

    words = [word for word in normalized.split() if word not in ignored_words]

    return " ".join(words)


def headline_similarity(first, second):
    first = normalize_title(first)
    second = normalize_title(second)

    if not first or not second:
        return 0.0

    sequence_score = SequenceMatcher(None, first, second).ratio()

    first_words = set(first.split())
    second_words = set(second.split())

    if first_words and second_words:
        word_score = len(first_words & second_words) / len(first_words | second_words)
    else:
        word_score = 0.0

    return max(sequence_score, word_score)


def cluster_articles(articles):
    clusters = []

    # Sort by importance (Breaking + Maldives + Dhivehi first)
    articles.sort(
        key=lambda article: (
            0 if is_breaking_story(article) else 1,
            0 if is_maldives_story(article) else 1,
            0 if is_dhivehi_story(article) else 1,
            -calculate_local_importance(article),
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
# AI FOR IMPORTANT STORIES ONLY
# ============================================================

def should_use_ai(cluster, local_score, ai_used_this_check):
    if not GEMINI_API_KEY or "PASTE_YOUR" in GEMINI_API_KEY:
        return False

    if ai_used_this_check >= MAX_AI_REQUESTS_PER_CHECK:
        return False

    if ai_is_in_cooldown():
        return False

    first_article = cluster["articles"][0]

    # Always use AI for breaking Maldives news
    if is_breaking_story(first_article) and is_maldives_story(first_article):
        return local_score >= 60
    
    # Use AI for important Maldives stories
    if is_maldives_story(first_article) and local_score >= 70:
        return True

    return local_score >= MINIMUM_AI_SCORE


def analyze_important_cluster_with_ai(cluster):
    article_blocks = []

    for index, article in enumerate(cluster["articles"][:4], start=1):
        article_blocks.append(
            f"""
Report {index}
Publisher: {article['publisher']}
Headline: {article['title']}
Description: {shorten_text(article['description'], 1300)}
""".strip()
        )

    combined_reports = "\n\n".join(article_blocks)

    prompt = f"""
You are editing a friendly and reliable public news channel called Worldwide News.

Several reports below may describe the same event.

Return only one valid JSON object:

{{
  "headline": "Clear factual headline",
  "summary": [
    "First short factual sentence",
    "Second short factual sentence"
  ],
  "why_it_matters": "One short factual sentence",
  "category": "World",
  "breaking": false,
  "importance_score": 80
}}

Rules:

1. Use only information provided in the reports.
2. Never invent facts.
3. Keep the language simple and customer-friendly.
4. The summary must contain exactly two concise sentences.
5. Select one category from:
   Maldives, World, Politics, Business, Technology, AI,
   Environment, Climate, Health, Science, Travel,
   Sports, Entertainment, Emergency, Other.
6. Use Maldives when the story mainly concerns Maldives.
7. Breaking should be true only for urgent major developments.
8. Importance score must be between 0 and 100.

Reports:

{combined_reports}
""".strip()

    response_text = gemini_generate(prompt, max_tokens=600)

    data = extract_json_object(response_text)

    if not data:
        return None

    summary = data.get("summary", [])

    if not isinstance(summary, list):
        return None

    summary = [clean_text(item) for item in summary if clean_text(item)][:2]

    if len(summary) < 2:
        return None

    category = clean_text(data.get("category", "World"))

    if category not in CATEGORY_EMOJIS:
        category = "World"

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
        "category": detect_category(first_article),
        "breaking": is_breaking_story(first_article),
        "importance_score": local_score,
        "used_ai": False,
    }


# ============================================================
# LOCAL SUMMARY
# ============================================================

def local_summary(article, cluster_articles=None):
    descriptions = [article.get("description", "")]

    if cluster_articles:
        descriptions.extend(
            item.get("description", "")
            for item in cluster_articles[1:3]
        )

    combined_text = " ".join(descriptions)
    sentences = split_sentences(combined_text)

    selected_sentences = []

    for sentence in sentences:
        normalized_sentence = sentence.lower()

        already_selected = any(
            normalized_sentence == existing.lower()
            for existing in selected_sentences
        )

        if already_selected:
            continue

        selected_sentences.append(shorten_text(sentence, 260))

        if len(selected_sentences) == 2:
            break

    if not selected_sentences:
        selected_sentences.append(
            shorten_text(
                article.get("title", "Open the source for further information."),
                240,
            )
        )

    if len(selected_sentences) < 2:
        selected_sentences.append(
            "Open the original source using the button below for full details."
        )

    return selected_sentences[:2]


# ============================================================
# TELEGRAM API
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
            logging.error("Telegram %s error: %s", method, result.get("description", response.text[:500]))
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


# ============================================================
# SOURCE BUTTONS
# ============================================================

def build_source_buttons(cluster):
    buttons = []
    added_links = set()

    for article in cluster.get("articles", [])[:5]:
        link = article.get("link")
        publisher = article.get("publisher", "Original source")

        if not link or link in added_links:
            continue

        if not link.startswith(("http://", "https://")):
            continue

        added_links.add(link)

        button_text = shorten_text(f"🔗 Read on {publisher}", 45)

        buttons.append({"text": button_text, "url": link})

    if not buttons:
        return None

    return {"inline_keyboard": [[button] for button in buttons]}


# ============================================================
# PUBLIC COMMAND BUTTONS
# ============================================================

def public_command_keyboard():
    return {
        "keyboard": [
            [{"text": "📰 Latest News"}, {"text": "🔥 Trending"}],
            [{"text": "🇲🇻 Maldives"}, {"text": "🌍 World"}],
            [{"text": "💻 Technology"}, {"text": "💰 Business"}],
            [{"text": "⚽ Sports"}, {"text": "🌊 Environment"}],
            [{"text": "❓ Help"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Choose a news section or type a search...",
    }


def publish_post(message, image_url=None, source_buttons=None):
    if image_url:
        result = send_photo(photo_url=image_url, caption=message, reply_markup=source_buttons)

        if result:
            return result

        logging.warning("Image could not be sent. Sending a text post.")

    return send_message(text=message, reply_markup=source_buttons)


# ============================================================
# TELEGRAM COMMAND MENU
# ============================================================

PUBLIC_COMMANDS = [
    {"command": "help", "description": "Show the news menu"},
    {"command": "latest", "description": "View the latest important news"},
    {"command": "trending", "description": "View the most reported stories"},
    {"command": "maldives", "description": "View the latest Maldives news"},
    {"command": "world", "description": "View international news"},
    {"command": "technology", "description": "View technology and AI news"},
    {"command": "business", "description": "View business and economy news"},
    {"command": "sports", "description": "View the latest sports news"},
    {"command": "environment", "description": "View environment and climate news"},
    {"command": "search", "description": "Search recently published news"},
]


def register_public_commands():
    return telegram_api("setMyCommands", {"commands": PUBLIC_COMMANDS})


# ============================================================
# AI SYSTEM
# ============================================================

def ai_is_in_cooldown():
    disabled_until = state.get("ai_disabled_until")

    if not disabled_until:
        return False

    try:
        cooldown_end = datetime.fromisoformat(disabled_until)
        if utc_now() < cooldown_end:
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
    cooldown_end = utc_now() + timedelta(minutes=AI_QUOTA_COOLDOWN_MINUTES)
    state["ai_disabled_until"] = cooldown_end.isoformat()
    save_state()
    logging.warning("AI temporarily disabled until %s.", cooldown_end)


def gemini_generate(prompt, max_tokens=600):
    if not GEMINI_API_KEY or "PASTE_YOUR" in GEMINI_API_KEY:
        return None

    if ai_is_in_cooldown():
        logging.info("AI is currently in quota cooldown.")
        return None

    if ai_hourly_limit_reached():
        logging.info("AI hourly safety limit reached.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.15,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }

    record_ai_request()

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=75)

        if response.status_code == 429:
            logging.error("Gemini quota reached: %s", response.text[:500])
            activate_ai_cooldown()
            return None

        if response.status_code != 200:
            logging.error("Gemini error %s: %s", response.status_code, response.text[:700])
            return None

        result = response.json()
        candidates = result.get("candidates", [])

        if not candidates:
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        generated_text = "".join(part.get("text", "") for part in parts).strip()

        return generated_text or None

    except requests.RequestException as error:
        logging.error("Gemini connection error: %s", error)
        return None


def extract_json_object(text):
    if not text:
        return None

    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```$", "", text).strip()

    object_start = text.find("{")
    object_end = text.rfind("}")

    if object_start == -1 or object_end == -1:
        return None

    try:
        return json.loads(text[object_start:object_end + 1])
    except json.JSONDecodeError:
        return None


# ============================================================
# TRENDING SCORE
# ============================================================

def calculate_trending_score(cluster, analysis):
    score = analysis["importance_score"] * 0.55

    source_bonus = min(len(cluster["publishers"]) * 12, 35)
    score += source_bonus

    if analysis["breaking"]:
        score += 12

    if analysis["category"] == "Maldives":
        score += 10

    return min(100, round(score))


# ============================================================
# NEWS POST FORMAT
# ============================================================

def build_news_message(cluster, analysis, trend_score):
    category = analysis["category"]

    category_emoji = CATEGORY_EMOJIS.get(category, "📰")

    safe_category = html.escape(category)
    safe_headline = html.escape(analysis["headline"])
    safe_summary_one = html.escape(analysis["summary"][0])
    safe_summary_two = html.escape(analysis["summary"][1])
    safe_publishers = html.escape(", ".join(sorted(cluster["publishers"])))

    # Add language indicator
    first_article = cluster["articles"][0]
    lang_indicator = ""
    if is_dhivehi_story(first_article):
        lang_indicator = " (Dhivehi)"

    if analysis["breaking"]:
        heading = "🚨 <b>BREAKING NEWS</b>\n\n"
    elif trend_score >= 82:
        heading = "🔥 <b>TRENDING STORY</b>\n\n"
    else:
        heading = ""

    message = (
        f"{heading}"
        f"{category_emoji} "
        f"<b>{safe_category}</b>{lang_indicator}\n\n"
        f"📰 <b>{safe_headline}</b>\n\n"
        f"• {safe_summary_one}\n"
        f"• {safe_summary_two}\n"
    )

    why_it_matters = analysis.get("why_it_matters")

    if why_it_matters:
        message += f"\n💡 <b>Why this matters:</b>\n{html.escape(why_it_matters)}\n"

    message += (
        f"\n📊 <b>Trending score:</b> "
        f"{trend_score}/100\n"
        f"🏢 <b>Reporting sources:</b> "
        f"{safe_publishers}\n\n"
        "👇 Tap a source button below to read the complete report."
    )

    if len(cluster["articles"]) > 1:
        message += f"\n\n🧩 Combined from {len(cluster['articles'])} related reports."

    return message


# ============================================================
# SAVING PUBLISHED STORIES
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
            "link": cluster["articles"][0]["link"],
            "maldives": analysis["category"] == "Maldives",
            "dhivehi": is_dhivehi_story(first_article),
            "used_ai": analysis["used_ai"],
        }
    )


def recent_history(hours=48):
    cutoff = utc_now() - timedelta(hours=hours)

    results = []

    for item in state.get("history", []):
        try:
            created_at = datetime.fromisoformat(item["created_at"])
            if created_at >= cutoff:
                results.append(item)
        except Exception:
            continue

    return results


# ============================================================
# MAIN NEWS CHECK
# ============================================================

async def check_and_publish_news():
    logging.info("Collecting worldwide news...")

    articles = await asyncio.to_thread(fetch_new_articles)

    if not articles:
        logging.info("No new articles found.")
        state["last_news_check"] = utc_now_iso()
        save_state()
        return

    logging.info("Collected %s unseen articles.", len(articles))

    clusters = cluster_articles(articles)

    ranked_clusters = []

    for cluster in clusters:
        highest_score = max(
            calculate_local_importance(article)
            for article in cluster["articles"]
        )

        highest_score += min((len(cluster["publishers"]) - 1) * 7, 21)
        highest_score = min(100, highest_score)

        ranked_clusters.append({"cluster": cluster, "local_score": highest_score})

    ranked_clusters.sort(
        key=lambda item: (
            0 if is_breaking_story(item["cluster"]["articles"][0]) else 1,
            0 if is_maldives_story(item["cluster"]["articles"][0]) else 1,
            0 if is_dhivehi_story(item["cluster"]["articles"][0]) else 1,
            -item["local_score"],
            -len(item["cluster"]["publishers"]),
        )
    )

    posted_count = 0
    ai_used_this_check = 0

    for item in ranked_clusters:
        cluster = item["cluster"]
        local_score = item["local_score"]

        for article in cluster["articles"]:
            if article["id"] not in state["seen_ids"]:
                state["seen_ids"].append(article["id"])

        first_article = cluster["articles"][0]

        should_publish = (
            local_score >= MINIMUM_POST_SCORE
            or is_maldives_story(first_article)
            or is_breaking_story(first_article)
            or is_dhivehi_story(first_article)  # Always publish Dhivehi stories
            or len(cluster["publishers"]) >= 3
        )

        if not should_publish:
            logging.info("Filtered out: %s", first_article["title"])
            continue

        if posted_count >= MAX_POSTS_PER_CHECK:
            break

        analysis = None

        if should_use_ai(cluster, local_score, ai_used_this_check):
            logging.info("Using AI for important story: %s", first_article["title"])

            analysis = await asyncio.to_thread(
                analyze_important_cluster_with_ai,
                cluster,
            )

            if analysis:
                ai_used_this_check += 1

        if not analysis:
            analysis = local_cluster_analysis(cluster, local_score)

        trend_score = calculate_trending_score(cluster, analysis)

        message = build_news_message(cluster, analysis, trend_score)

        source_buttons = build_source_buttons(cluster)

        published = await asyncio.to_thread(
            publish_post,
            message,
            cluster.get("image"),
            source_buttons,
        )

        if published:
            save_to_history(cluster, analysis, trend_score)
            posted_count += 1
            await asyncio.sleep(MESSAGE_DELAY_SECONDS)

    state["last_news_check"] = utc_now_iso()
    save_state()

    logging.info("Completed: %s posts and %s AI requests.", posted_count, ai_used_this_check)


# ============================================================
# DAILY DIGESTS
# ============================================================

def build_digest(title, hours):
    stories = recent_history(hours)

    if not stories:
        return (
            f"🗞️ <b>{html.escape(title)}</b>\n\n"
            "There are no new important stories available for this period."
        )

    stories.sort(
        key=lambda story: (
            0 if story.get("maldives") else 1,
            0 if story.get("breaking") else 1,
            -story.get("trending_score", 0),
        )
    )

    maldives_count = sum(1 for story in stories if story.get("maldives"))
    breaking_count = sum(1 for story in stories if story.get("breaking"))
    dhivehi_count = sum(1 for story in stories if story.get("dhivehi"))

    message = (
        f"🗞️ <b>{html.escape(title)}</b>\n\n"
        "Here is your quick news roundup from "
        f"<b>{BOT_NAME}</b>.\n\n"
        f"📰 Important stories: {len(stories)}\n"
        f"🇲🇻 Maldives stories: {maldives_count}\n"
        f"📝 Dhivehi stories: {dhivehi_count}\n"
        f"🚨 Breaking stories: {breaking_count}\n\n"
    )

    for index, story in enumerate(stories[:12], start=1):
        category = story.get("category", "World")
        emoji = CATEGORY_EMOJIS.get(category, "📰")

        headline = html.escape(story.get("headline", "Untitled report"))
        link = html.escape(story.get("link", ""), quote=True)
        
        lang_marker = "📝 " if story.get("dhivehi") else ""

        message += (
            f'{index}. {emoji} {lang_marker}'
            f'<a href="{link}">{headline}</a>\n'
            f"   📊 Trending: "
            f"{story.get('trending_score', 0)}/100\n\n"
        )

    return shorten_text(message, 3900)


async def digest_scheduler():
    while True:
        now = maldives_now()
        today = now.date().isoformat()

        if now.hour == MORNING_DIGEST_HOUR and now.minute < 5 and state.get("last_morning_digest") != today:
            morning_message = build_digest("Good Morning — Your Worldwide News Brief", 12)

            await asyncio.to_thread(send_message, morning_message)

            state["last_morning_digest"] = today
            save_state()

        if now.hour == EVENING_DIGEST_HOUR and now.minute < 5 and state.get("last_evening_digest") != today:
            evening_message = build_digest("Good Evening — Today's Top Stories", 12)

            await asyncio.to_thread(send_message, evening_message)

            state["last_evening_digest"] = today
            save_state()

        await asyncio.sleep(60)


# ============================================================
# PUBLIC COMMAND RESPONSES
# ============================================================

HELP_TEXT = f"""
🌐 <b>Welcome to {BOT_NAME}</b>

Stay informed with important stories from the Maldives and around the world.

Use the buttons below or choose a command:

📰 <b>Latest News</b> — Recent important stories
🔥 <b>Trending</b> — Most reported stories
🇲🇻 <b>Maldives</b> — Latest Maldives news (English + Dhivehi)
🌍 <b>World</b> — International headlines
💻 <b>Technology</b> — Technology, science and AI
💰 <b>Business</b> — Business and economy
⚽ <b>Sports</b> — Latest sports reports
🌊 <b>Environment</b> — Climate and environmental news

You can also search our recent stories:

<code>/search Maldives tourism</code>

Tap the source button under any news post to read the complete original report.
""".strip()


def filter_history(category_names=None, maldives_only=False, world_only=False, query=None, limit=8):
    stories = list(reversed(state.get("history", [])))

    results = []

    for story in stories:
        if maldives_only and not story.get("maldives"):
            continue

        if world_only and story.get("maldives"):
            continue

        if category_names:
            category = story.get("category", "").lower()
            accepted_categories = {name.lower() for name in category_names}

            if category not in accepted_categories:
                continue

        if query:
            searchable_text = (
                story.get("headline", "")
                + " "
                + " ".join(story.get("summary", []))
                + " "
                + " ".join(story.get("publishers", []))
            ).lower()

            search_terms = [term for term in query.lower().split() if term]

            if not all(term in searchable_text for term in search_terms):
                continue

        results.append(story)

        if len(results) >= limit:
            break

    return results


def build_story_list(title, stories):
    if not stories:
        return (
            f"📰 <b>{html.escape(title)}</b>\n\n"
            "There are no matching stories available yet. "
            "Please check again shortly."
        )

    message = f"📰 <b>{html.escape(title)}</b>\n\n"

    for index, story in enumerate(stories, start=1):
        category = story.get("category", "World")
        emoji = CATEGORY_EMOJIS.get(category, "📰")

        headline = html.escape(story.get("headline", "Untitled report"))
        link = html.escape(story.get("link", ""), quote=True)
        
        lang_marker = "📝 " if story.get("dhivehi") else ""

        message += (
            f'{index}. {emoji} {lang_marker}'
            f'<a href="{link}">{headline}</a>\n'
            f"   📊 Trending: "
            f"{story.get('trending_score', 0)}/100\n\n"
        )

    return shorten_text(message, 3900)


def handle_command(message):
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")

    button_commands = {
        "📰 Latest News": "/latest",
        "🔥 Trending": "/trending",
        "🇲🇻 Maldives": "/maldives",
        "🌍 World": "/world",
        "💻 Technology": "/technology",
        "💰 Business": "/business",
        "⚽ Sports": "/sports",
        "🌊 Environment": "/environment",
        "❓ Help": "/help",
    }

    text = button_commands.get(text, text)

    if not text.startswith("/"):
        return

    sections = text.split(maxsplit=1)

    command = sections[0].split("@")[0].lower()
    argument = sections[1].strip() if len(sections) > 1 else ""

    if command in {"/start", "/help"}:
        send_message(
            HELP_TEXT,
            chat_id,
            reply_markup=public_command_keyboard(),
        )
        return

    if command == "/latest":
        stories = filter_history(limit=8)

        send_message(
            build_story_list("Latest Important News", stories),
            chat_id,
        )
        return

    if command == "/trending":
        stories = recent_history(48)

        stories.sort(key=lambda story: story.get("trending_score", 0), reverse=True)

        send_message(
            build_story_list("Trending Stories", stories[:8]),
            chat_id,
        )
        return

    if command == "/maldives":
        stories = filter_history(maldives_only=True, limit=8)

        send_message(
            build_story_list("Latest Maldives News", stories),
            chat_id,
        )
        return

    if command == "/world":
        stories = filter_history(world_only=True, limit=8)

        send_message(
            build_story_list("World News", stories),
            chat_id,
        )
        return

    if command == "/technology":
        stories = filter_history(category_names={"Technology", "AI", "Science"}, limit=8)

        send_message(
            build_story_list("Technology, Science and AI", stories),
            chat_id,
        )
        return

    if command == "/business":
        stories = filter_history(category_names={"Business"}, limit=8)

        send_message(
            build_story_list("Business and Economy", stories),
            chat_id,
        )
        return

    if command == "/sports":
        stories = filter_history(category_names={"Sports"}, limit=8)

        send_message(
            build_story_list("Latest Sports News", stories),
            chat_id,
        )
        return

    if command == "/environment":
        stories = filter_history(category_names={"Environment", "Climate"}, limit=8)

        send_message(
            build_story_list("Environment and Climate", stories),
            chat_id,
        )
        return

    if command == "/search":
        if not argument:
            send_message(
                "🔎 <b>Search Worldwide News</b>\n\n"
                "Please enter your search after the command.\n\n"
                "Example:\n"
                "<code>/search Maldives tourism</code>",
                chat_id,
            )
            return

        stories = filter_history(query=argument, limit=10)

        send_message(
            build_story_list(f"Search results: {argument}", stories),
            chat_id,
        )
        return

    send_message(
        "Please choose one of the news buttons below, "
        "or use /help to view the available options.",
        chat_id,
        reply_markup=public_command_keyboard(),
    )


# ============================================================
# TELEGRAM LONG POLLING
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
            update_id = update.get("update_id", 0)

            state["telegram_offset"] = update_id + 1

            message = update.get("message")

            if message:
                try:
                    await asyncio.to_thread(handle_command, message)
                except Exception as error:
                    logging.exception("Command error: %s", error)

            save_state()


# ============================================================
# AUTOMATIC NEWS LOOP
# ============================================================

async def automatic_news_loop():
    while True:
        try:
            await check_and_publish_news()
        except Exception as error:
            logging.exception("News check failed: %s", error)

        logging.info("Waiting %s minutes before the next check.", NEWS_CHECK_INTERVAL_SECONDS // 60)

        await asyncio.sleep(NEWS_CHECK_INTERVAL_SECONDS)


# ============================================================
# STARTUP
# ============================================================

def validate_configuration():
    missing_values = []

    if not TELEGRAM_BOT_TOKEN or "PASTE_YOUR" in TELEGRAM_BOT_TOKEN:
        missing_values.append("TELEGRAM_BOT_TOKEN")

    if not GROUP_CHAT_ID:
        missing_values.append("GROUP_CHAT_ID")

    if not GEMINI_API_KEY:
        logging.warning("No Gemini key configured. The bot will use free local summaries.")

    if missing_values:
        raise ValueError("Please configure: " + ", ".join(missing_values))


def test_telegram_connection():
    bot_information = telegram_api("getMe")

    if not bot_information:
        return False

    logging.info("Connected to Telegram as @%s", bot_information.get("username", "unknown_bot"))

    return True


def build_welcome_message():
    return f"""
🌐 <b>Welcome to {BOT_NAME}</b>

Your easy way to stay informed with important news from the Maldives and around the world.

We bring you:

🇲🇻 Priority Maldives updates (English + Dhivehi)
🌍 Major international headlines
🚨 Breaking-news alerts (within minutes)
🔥 Trending stories from multiple sources
💻 Technology and AI updates
💰 Business and economic news
⚽ Sports headlines
🌊 Environment and climate reports

Every story includes a direct source button, so you can open and read the complete original report.

Choose a section using the buttons below and stay connected with what matters.
""".strip()


async def main():
    validate_configuration()

    logging.info("Starting %s...", BOT_NAME)

    telegram_working = await asyncio.to_thread(test_telegram_connection)

    if not telegram_working:
        logging.error("Telegram connection failed. Please check the bot token and internet connection.")
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