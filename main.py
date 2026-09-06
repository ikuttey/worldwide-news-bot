import asyncio
import hashlib
import html
import json
import logging
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import feedparser
import requests


logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_NAME = "Maldives & World News"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
NEWS_CHECK_INTERVAL_SECONDS = int(os.getenv("NEWS_CHECK_INTERVAL_SECONDS", "300"))
MAX_POSTS_PER_CHECK = int(os.getenv("MAX_POSTS_PER_CHECK", "12"))
MESSAGE_DELAY_SECONDS = float(os.getenv("MESSAGE_DELAY_SECONDS", "2"))
MINIMUM_POST_SCORE = int(os.getenv("MINIMUM_POST_SCORE", "58"))
FETCH_WORKERS = max(2, min(16, int(os.getenv("FETCH_WORKERS", "8"))))
PRIVATE_PAGE_SIZE = max(5, min(12, int(os.getenv("PRIVATE_PAGE_SIZE", "8"))))
USER_REQUEST_LIMIT = max(5, int(os.getenv("USER_REQUEST_LIMIT", "30")))
USER_REQUEST_WINDOW_SECONDS = max(60, int(os.getenv("USER_REQUEST_WINDOW_SECONDS", "300")))
ADMIN_USER_IDS = {item.strip() for item in os.getenv("ADMIN_USER_IDS", "").split(",") if item.strip()}
MALDIVES_TIMEZONE = timezone(timedelta(hours=5))
MORNING_DIGEST_HOUR = 7
EVENING_DIGEST_HOUR = 19
ARCHIVE_RETENTION_DAYS = int(os.getenv("ARCHIVE_RETENTION_DAYS", "90"))
APP_VERSION = "all-news-v4"

_default_db = "/data/news_bot.sqlite3" if Path("/data").exists() else "news_bot.sqlite3"
DB_PATH = Path(os.getenv("NEWS_DB_PATH", _default_db))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_LOCK = threading.RLock()
BOT_USERNAME = None
RATE_MEMORY = {}


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_iso():
    return utc_now().isoformat()


def maldives_now():
    return datetime.now(MALDIVES_TIMEZONE)


def clean_text(value):
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def shorten_text(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: max(0, limit - 3)].rstrip() + "..."


def is_dhivehi_text(text):
    text = clean_text(text)
    if not text:
        return False
    thaana = len(re.findall(r"[\u0780-\u07BF]", text))
    letters = len(re.findall(r"[A-Za-z\u0780-\u07BF]", text))
    return thaana >= 3 and thaana / max(letters, 1) >= 0.18


def split_sentences(text, language="en"):
    text = clean_text(text)
    if not text:
        return []
    if language == "dv":
        parts = re.split(r"(?<=[.!?؟])\s+|\n+", text)
    else:
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
    return [part.strip() for part in parts if len(part.strip()) >= 18]


def contains_phrase(text, phrase):
    text = text.lower()
    phrase = phrase.lower().strip()
    if not phrase:
        return False
    if re.search(r"[\u0780-\u07BF]", phrase):
        return phrase in text
    pattern = r"(?<![A-Za-z0-9])" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.I) is not None


def phrase_hits(text, phrases):
    return sum(1 for phrase in phrases if contains_phrase(text, phrase))


def normalize_title(title):
    title = clean_text(title).lower()
    title = re.sub(r"[^\w\u0780-\u07BF\s]", " ", title, flags=re.UNICODE)
    title = re.sub(r"\s+", " ", title).strip()
    ignored = {"breaking", "latest", "live", "update", "updates", "news", "report", "reports", "says"}
    return " ".join(word for word in title.split() if word not in ignored)


def headline_similarity(first, second):
    first = normalize_title(first)
    second = normalize_title(second)
    if not first or not second:
        return 0.0
    sequence_score = SequenceMatcher(None, first, second).ratio()
    a, b = set(first.split()), set(second.split())
    jaccard = len(a & b) / len(a | b) if a and b else 0.0
    return max(sequence_score, jaccard)


def canonicalize_url(url):
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return url
    try:
        parts = urlsplit(url)
        kept = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.lower().startswith("utm_") or key.lower() in {"fbclid", "gclid", "mc_cid", "mc_eid"}:
                continue
            kept.append((key, value))
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(kept), ""))
    except Exception:
        return url


def hash_value(*parts):
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def google_news_feed(query, region="US", language="en"):
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={language}&gl={region}&ceid={region}:{language}"
    )


MALDIVES_DOMAINS = [
    "adhadhu.com", "adhives.mv", "aslu.com.mv", "asuruonline.com", "avas.mv", "cnm.mv",
    "dhelionline.mv", "dhen.mv", "dhauru.com", "dhidaily.mv", "dhuvas.mv", "dhuvelionline.mv",
    "edition.mv", "eki.mv", "fainuonline.com", "faragu.mv", "farudhun.com", "fiyaonline.com",
    "fiyes.mv", "furathama.mv", "gaafu.mv", "gohkolhu.com", "halha.mv", "halinews.com",
    "hathaavees.com", "havaasa.com", "heerasnews.com", "hiraas.com.mv", "hirinews.com", "hoara.mv",
    "hurihaa.mv", "huvadhoomedia.com", "iruvanews.com", "iruvaru.com", "javiyani.mv", "jeeluonline.com",
    "kaafu.mv", "keyolha.com", "khabaruonline.com", "maldivesindependent.com", "maletimes.mv",
    "masverin.mv", "miadhu.mv", "mihaaru.com", "mikalnews.com", "milauthuru.com", "mmtv.mv",
    "mulhiraajje.com", "muniavas.com", "muraasilu.mv", "mvrepublic.com", "naares.com", "oivaru.com",
    "oneonline.mv", "psm.mv", "raajje.mv", "raajje24.com", "ras.mv", "sababu.mv", "sandhaanu.today",
    "sangu.mv", "sarukaaru.gov.mv", "sauvees.com", "sun.mv", "suruhee.mv", "themirror.mv", "thepress.mv",
    "thiladhun.com", "vaguthu.mv", "viraasee.com", "viyafaari.com.mv", "viyas.mv", "vnews.mv", "voice.mv",
    "xeetimes.com",
]
MALDIVES_DOMAIN_SET = set(MALDIVES_DOMAINS)

MAJOR_PUBLISHER_NAMES = {
    "mihaaru.com": "Mihaaru", "dhauru.com": "Dhauru", "avas.mv": "Avas", "raajje.mv": "Raajje TV",
    "vnews.mv": "VNews", "dhen.mv": "Dhen", "mmtv.mv": "MMTV", "edition.mv": "The Edition",
    "maldivesindependent.com": "Maldives Independent", "mvrepublic.com": "MV Republic", "psm.mv": "PSM News",
    "sun.mv": "Sun Online", "adhadhu.com": "Adhadhu", "miadhu.mv": "Miadhu", "vaguthu.mv": "Vaguthu",
}

DIRECT_MALDIVES_FEEDS = {
    "Sun Online": "https://sun.mv/news/rss",
    "PSM News": "https://psmnews.mv/feed",
    "Adhadhu": "https://adhadhu.com/rss",
    "Miadhu": "https://miadhu.com/feed",
    "Dhiyares": "https://dhiyares.com/rss",
    "VNews": "https://vnews.mv/rss",
    "Times of Addu": "https://timesofaddu.com/feed",
}

GLOBAL_RSS_FEEDS = {
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "The Guardian World": "https://www.theguardian.com/world/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "NPR World": "https://feeds.npr.org/1004/rss.xml",
    "NYT World": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "BBC Technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "BBC Health": "https://feeds.bbci.co.uk/news/health/rss.xml",
    "BBC Entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "BBC Sport": "https://feeds.bbci.co.uk/sport/rss.xml",
    "CNBC World": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "TechCrunch": "https://techcrunch.com/feed/",
    "NASA": "https://www.nasa.gov/news-release/feed/",
}

CATEGORY_EMOJIS = {
    "Emergency": "🚨", "Politics": "🏛️", "Business": "💰", "Technology & AI": "💻",
    "Health": "🏥", "Science": "🔬", "Travel & Tourism": "✈️", "Sports": "⚽",
    "Entertainment": "🎬", "Crime & Courts": "⚖️", "Environment": "🌊", "General": "📰",
}

CATEGORY_KEYWORDS = {
    "Politics": {"president", "prime minister", "parliament", "election", "government", "minister", "cabinet", "vote", "diplomatic", "constitution", "ރައީސް", "ވަޒީރު", "މަޖިލިސް", "އިންތިޚާބު", "ސަރުކާރު"},
    "Business": {"economy", "inflation", "bank", "market", "stocks", "business", "trade", "investment", "finance", "gdp", "interest rate", "އިޤްތިޞާދު", "ވިޔަފާރި", "ފައިސާ", "ބޭންކު"},
    "Technology & AI": {"technology", "artificial intelligence", "generative ai", "chatgpt", "openai", "gemini", "software", "cybersecurity", "internet", "semiconductor", "robot", "ޓެކްނޮލޮޖީ", "އޭއައި", "އިންޓަރނެޓް"},
    "Health": {"health", "hospital", "disease", "virus", "outbreak", "vaccine", "medical", "doctor", "patient", "treatment", "medicine", "ޞިއްޙަތު", "ބަލި", "ހޮސްޕިޓަލް"},
    "Science": {"science", "research", "scientist", "space", "nasa", "discovery", "study", "satellite", "ސައިންސް", "ދިރާސާ"},
    "Travel & Tourism": {"travel", "tourism", "airport", "airline", "flight", "hotel", "resort", "visa", "passenger", "cruise", "ޓޫރިޒަމް", "މުސާފިރު", "ރިސޯޓް", "އެއަރޕޯޓް"},
    "Sports": {"football", "soccer", "cricket", "tennis", "basketball", "futsal", "volleyball", "championship", "league", "tournament", "world cup", "olympics", "match", "goal", "ފުޓްބޯޅަ", "ކްރިކެޓް", "ސްޕޯޓް", "މެޗު", "ލީގު"},
    "Entertainment": {"film", "movie", "music", "actor", "actress", "celebrity", "television", "concert", "award", "song", "album", "entertainment", "ފިލްމު", "މިއުޒިކް", "ޓީވީ"},
    "Crime & Courts": {"police", "court", "crime", "arrested", "charged", "trial", "investigation", "prosecutor", "sentence", "murder", "robbery", "fraud", "ފުލުހުން", "ކޯޓު", "ހައްޔަރު", "ތަޙްޤީޤު"},
    "Environment": {"environment", "climate", "ocean", "coral", "reef", "wildlife", "pollution", "conservation", "biodiversity", "marine", "plastic", "waste", "weather", "ތިމާވެށި", "ކަނޑު", "މޫދު", "ފަރު", "ކުނި"},
}

BREAKING_STRONG = {
    "breaking", "urgent", "state of emergency", "earthquake", "tsunami", "cyclone", "hurricane", "typhoon",
    "major flood", "flash flood", "explosion", "evacuation", "landslide", "terror attack", "missile attack",
    "coup", "assassination", "ceasefire", "war", "airport closed", "mass casualty", "ބްރޭކިންގ", "ކާރިސާ", "ސުނާމީ", "ބިންހެލުން",
}
BREAKING_SUPPORT = {"killed", "dead", "injured", "warning", "alert", "emergency", "attack", "flood", "fire", "outbreak"}
HIGH_IMPORTANCE = {"president", "prime minister", "government", "election", "parliament", "economy", "inflation", "interest rate", "supreme court", "central bank", "earthquake", "tsunami", "cyclone", "outbreak", "ރައީސް", "ސަރުކާރު", "އިންތިޚާބު", "މަޖިލިސް", "އިޤްތިޞާދު"}
LOW_VALUE = {"horoscope", "recipe", "shopping", "sponsored", "advertisement", "promotion", "discount", "photo gallery", "quiz"}

MALDIVES_LOCAL_MARKERS = {
    "maldives", "maldivian", "malé", "male city", "hulhumale", "hulhumalé", "villimale", "addu", "fuvahmulah",
    "kulhudhuffushi", "thinadhoo", "eydhafushi", "dharavandhoo", "hanifaru", "maafushi", "thulusdhoo", "dhigurah",
    "hithadhoo", "naifaru", "fonadhoo", "kudahuvadhoo", "manadhoo", "ungoofaaru", "villingili", "baa atoll", "laamu atoll",
    "gaafu", "kaafu atoll", "raa atoll", "noonu atoll", "shaviyani atoll", "lhaviyani atoll", "ari atoll", "meen atoll",
    "ދިވެހިރާއްޖެ", "ރާއްޖެ", "މާލެ", "ހުޅުމާލެ", "އައްޑޫ", "ފުވައްމުލައް", "އޭދަފުށި", "ދަރަވަންދޫ",
}
MALDIVES_INSTITUTIONS = {
    "people's majlis", "peoples majlis", "maldives police service", "mndf", "bank of maldives", "maldives monetary authority",
    "maldives inland revenue", "mira", "macl", "mtcc", "stelco", "fenaka", "rufiyaa", "mvr", "president muizzu",
    "ރުފިޔާ", "މަޖިލިސް", "އެމްއެންޑީއެފް", "ފުލުހުން",
}
FOREIGN_MARKERS = {
    "yemen", "india", "sri lanka", "united kingdom", " uk ", "united states", "gaza", "israel", "ukraine", "russia",
    "china", "pakistan", "bangladesh", "saudi arabia", "uae", "iran", "iraq", "nepal", "australia", "new zealand",
    "france", "germany", "italy", "spain", "japan", "korea", "afghanistan", "myanmar", "sudan", "somalia",
}

SOURCE_QUALITY = {
    "Reuters": 10, "Associated Press": 10, "AP News": 10, "BBC": 9, "BBC World": 9, "NPR": 9,
    "New York Times": 9, "The Guardian": 8, "Al Jazeera": 8, "PSM News": 7, "Sun Online": 6,
    "Mihaaru": 7, "Dhauru": 7, "Adhadhu": 7, "The Edition": 7, "Maldives Independent": 7,
}


def db_connect():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def init_db():
    with DB_LOCK, db_connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                representative_title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                category TEXT NOT NULL,
                language TEXT NOT NULL,
                maldives INTEGER NOT NULL DEFAULT 0,
                story_location TEXT NOT NULL,
                importance INTEGER NOT NULL DEFAULT 0,
                breaking INTEGER NOT NULL DEFAULT 0,
                low_value INTEGER NOT NULL DEFAULT 0,
                primary_url TEXT NOT NULL,
                primary_publisher TEXT NOT NULL,
                publishers_json TEXT NOT NULL DEFAULT '[]',
                article_count INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                published_to_group INTEGER NOT NULL DEFAULT 0,
                published_importance INTEGER NOT NULL DEFAULT 0,
                published_breaking INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_stories_last_seen ON stories(last_seen DESC);
            CREATE INDEX IF NOT EXISTS idx_stories_maldives_lang ON stories(maldives, language, last_seen DESC);
            CREATE INDEX IF NOT EXISTS idx_stories_category ON stories(category, last_seen DESC);
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_uid TEXT UNIQUE NOT NULL,
                story_id INTEGER NOT NULL,
                source_feed TEXT NOT NULL,
                publisher TEXT NOT NULL,
                publisher_domain TEXT,
                publisher_country TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                url TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                language TEXT NOT NULL,
                category TEXT NOT NULL,
                maldives INTEGER NOT NULL,
                story_location TEXT NOT NULL,
                importance INTEGER NOT NULL,
                breaking INTEGER NOT NULL,
                low_value INTEGER NOT NULL,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                FOREIGN KEY(story_id) REFERENCES stories(id)
            );
            CREATE INDEX IF NOT EXISTS idx_articles_story ON articles(story_id);
            CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at DESC);
            CREATE TABLE IF NOT EXISTS source_health (
                source_name TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                last_attempt TEXT,
                last_success TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                article_count INTEGER NOT NULL DEFAULT 0,
                response_ms INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        db.commit()


def get_setting(key, default=None):
    with DB_LOCK, db_connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with DB_LOCK, db_connect() as db:
        db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        db.commit()


def cleanup_db():
    cutoff = (utc_now() - timedelta(days=ARCHIVE_RETENTION_DAYS)).isoformat()
    with DB_LOCK, db_connect() as db:
        db.execute("DELETE FROM articles WHERE fetched_at < ?", (cutoff,))
        db.execute("DELETE FROM stories WHERE last_seen < ?", (cutoff,))
        db.commit()


def domain_from_url(url):
    try:
        return urlsplit(str(url or "")).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def publisher_country_from_domain(domain):
    domain = domain.lower().removeprefix("www.")
    return "MV" if domain in MALDIVES_DOMAIN_SET or domain.endswith(".mv") else "OTHER"


def publisher_from_entry(entry, source_name, direct_publisher=None):
    source_obj = entry.get("source")
    publisher = ""
    publisher_url = ""
    if isinstance(source_obj, dict):
        publisher = clean_text(source_obj.get("title", ""))
        publisher_url = str(source_obj.get("href") or source_obj.get("url") or "")
    if direct_publisher:
        publisher = direct_publisher
    title = clean_text(entry.get("title", ""))
    if not publisher and " - " in title:
        left, right = title.rsplit(" - ", 1)
        if 2 <= len(right) <= 80:
            publisher = clean_text(right)
            title = clean_text(left)
    publisher = publisher or source_name
    domain = domain_from_url(publisher_url)
    return publisher, domain, title


def detect_location(text, publisher_country):
    lowered = f" {clean_text(text).lower()} "
    local_hits = phrase_hits(lowered, MALDIVES_LOCAL_MARKERS) + phrase_hits(lowered, MALDIVES_INSTITUTIONS)
    foreign_hits = phrase_hits(lowered, FOREIGN_MARKERS)
    if local_hits > 0:
        return "Maldives", True
    if foreign_hits > 0:
        return "Global", False
    if publisher_country == "MV" and is_dhivehi_text(lowered):
        return "Maldives", True
    if publisher_country == "MV":
        return "Maldives", True
    return "Global", False


def detect_category(text):
    scores = {category: phrase_hits(text, words) for category, words in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "General"


def is_breaking(text):
    strong = phrase_hits(text, BREAKING_STRONG)
    support = phrase_hits(text, BREAKING_SUPPORT)
    if strong >= 1:
        return True
    return support >= 2 and contains_phrase(text, "emergency")


def is_low_value(text):
    return phrase_hits(text, LOW_VALUE) > 0


def source_quality(publisher):
    publisher_lower = publisher.lower()
    best = 4
    for name, score in SOURCE_QUALITY.items():
        if name.lower() in publisher_lower:
            best = max(best, score)
    return best


def calculate_importance(text, maldives, breaking, category, publisher):
    score = 38
    if maldives:
        score += 10
    if breaking:
        score += 30
    score += min(phrase_hits(text, HIGH_IMPORTANCE) * 5, 20)
    score += max(0, source_quality(publisher) - 4)
    if category in {"Politics", "Business", "Health", "Emergency"}:
        score += 3
    if is_low_value(text):
        score -= 25
    return max(0, min(100, score))


def local_summary(title, description, language):
    sentences = split_sentences(description, language)
    if sentences:
        result = [shorten_text(sentence, 260) for sentence in sentences[:2]]
    else:
        result = [shorten_text(description or title, 260)] if (description or title) else []
    if len(result) < 2:
        fallback = "ތަފްޞީލު ކިޔުމަށް އަސްލު ޚަބަރު ހުޅުވާ." if language == "dv" else "Open the original source for the full report."
        result.append(fallback)
    return result[:2]


def parse_entry(source, entry):
    publisher, publisher_domain, cleaned_title = publisher_from_entry(
        entry, source["name"], source.get("publisher")
    )
    title = cleaned_title or clean_text(entry.get("title", ""))
    link = str(entry.get("link") or entry.get("id") or "").strip()
    if len(title) < 8 or not link.startswith(("http://", "https://")):
        return None
    description = clean_text(entry.get("summary") or entry.get("description") or entry.get("subtitle") or title)
    canonical = canonicalize_url(link)
    language = "dv" if is_dhivehi_text(f"{title} {description}") else "en"
    domain = publisher_domain or domain_from_url(link)
    publisher_country = source.get("publisher_country") or publisher_country_from_domain(domain)
    location, maldives = detect_location(f"{title} {description}", publisher_country)
    category = detect_category(f"{title} {description}")
    breaking = is_breaking(f"{title} {description}")
    low_value = is_low_value(f"{title} {description}")
    importance = calculate_importance(f"{title} {description}", maldives, breaking, category, publisher)
    article_uid = hash_value(publisher, normalize_title(title), canonical)
    return {
        "article_uid": article_uid,
        "source_feed": source["name"],
        "publisher": publisher,
        "publisher_domain": domain,
        "publisher_country": publisher_country,
        "title": title,
        "description": description,
        "url": link,
        "canonical_url": canonical,
        "language": language,
        "category": category,
        "maldives": 1 if maldives else 0,
        "story_location": location,
        "importance": importance,
        "breaking": 1 if breaking else 0,
        "low_value": 1 if low_value else 0,
        "published_at": clean_text(entry.get("published") or entry.get("updated") or ""),
        "fetched_at": utc_now_iso(),
        "summary": local_summary(title, description, language),
    }


def build_sources():
    sources = []
    for name, url in DIRECT_MALDIVES_FEEDS.items():
        sources.append({"name": f"MV Direct · {name}", "url": url, "publisher": name, "publisher_country": "MV", "max_entries": 18})
    for index in range(0, len(MALDIVES_DOMAINS), 6):
        group = MALDIVES_DOMAINS[index : index + 6]
        site_query = "(" + " OR ".join(f"site:{domain}" for domain in group) + ") when:3d"
        number = index // 6 + 1
        sources.append({"name": f"MV Outlets EN {number:02d}", "url": google_news_feed(site_query, "US", "en"), "max_entries": 20})
        sources.append({"name": f"MV Outlets DV {number:02d}", "url": google_news_feed(site_query, "MV", "dv"), "max_entries": 20})
    broad_local = {
        "MV Broad EN": google_news_feed("Maldives latest news when:2d", "US", "en"),
        "MV Broad DV": google_news_feed("ރާއްޖެ ނޫސް when:2d", "MV", "dv"),
        "MV Politics EN": google_news_feed("Maldives government parliament election when:3d", "US", "en"),
        "MV Business EN": google_news_feed("Maldives economy business tourism finance when:3d", "US", "en"),
        "MV Sports EN": google_news_feed("Maldives sports football futsal when:3d", "US", "en"),
        "MV Health EN": google_news_feed("Maldives health hospital medical when:3d", "US", "en"),
    }
    for name, url in broad_local.items():
        sources.append({"name": name, "url": url, "max_entries": 20})
    for name, url in GLOBAL_RSS_FEEDS.items():
        sources.append({"name": f"Global · {name}", "url": url, "publisher": name, "publisher_country": "OTHER", "max_entries": 12})
    global_searches = {
        "Global Breaking": "breaking world news when:12h",
        "Global Reuters": "site:reuters.com world news when:24h",
        "Global AP": "site:apnews.com world news when:24h",
        "Global Politics": "world politics government election diplomacy when:24h",
        "Global Business": "business economy markets finance when:24h",
        "Global Technology": "technology AI cybersecurity software when:24h",
        "Global Sports": "sports football cricket tennis when:12h",
        "Global Entertainment": "entertainment film music television when:24h",
        "Global Health": "health medicine disease outbreak when:24h",
        "Global Science": "science research space discovery when:24h",
        "Global Travel": "travel tourism airline airport when:24h",
        "Global Environment": "environment climate wildlife ocean when:24h",
        "Global Crime": "crime court police investigation world when:24h",
    }
    for name, query in global_searches.items():
        sources.append({"name": name, "url": google_news_feed(query, "US", "en"), "max_entries": 12})
    return sources


SOURCES = build_sources()


def record_health(source, success, count, elapsed_ms, error=""):
    now = utc_now_iso()
    with DB_LOCK, db_connect() as db:
        existing = db.execute("SELECT consecutive_failures FROM source_health WHERE source_name=?", (source["name"],)).fetchone()
        failures = 0 if success else ((existing["consecutive_failures"] if existing else 0) + 1)
        db.execute(
            """
            INSERT INTO source_health(source_name,url,last_attempt,last_success,consecutive_failures,last_error,article_count,response_ms)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(source_name) DO UPDATE SET
                url=excluded.url,last_attempt=excluded.last_attempt,
                last_success=CASE WHEN ? THEN excluded.last_success ELSE source_health.last_success END,
                consecutive_failures=excluded.consecutive_failures,last_error=excluded.last_error,
                article_count=excluded.article_count,response_ms=excluded.response_ms
            """,
            (source["name"], source["url"], now, now if success else None, failures, error[:300], count, elapsed_ms, 1 if success else 0),
        )
        db.commit()


def fetch_source(source):
    start = time.monotonic()
    try:
        response = requests.get(
            source["url"],
            headers={"User-Agent": "Mozilla/5.0 NewsBot/4.0"},
            timeout=(5, 15),
            allow_redirects=True,
        )
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        articles = []
        for entry in list(getattr(feed, "entries", []) or [])[: source.get("max_entries", 12)]:
            article = parse_entry(source, entry)
            if article:
                articles.append(article)
        elapsed = int((time.monotonic() - start) * 1000)
        record_health(source, True, len(articles), elapsed)
        return articles
    except Exception as error:
        elapsed = int((time.monotonic() - start) * 1000)
        record_health(source, False, 0, elapsed, str(error))
        logging.debug("Source failed %s: %s", source["name"], error)
        return []


def fetch_all_articles():
    articles = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = [executor.submit(fetch_source, source) for source in SOURCES]
        for future in as_completed(futures):
            try:
                articles.extend(future.result())
            except Exception as error:
                logging.warning("Fetch worker failed: %s", error)
    logging.info("Fetched %s valid articles from %s sources", len(articles), len(SOURCES))
    return articles


def find_matching_story(db, article):
    exact = db.execute("SELECT story_id FROM articles WHERE canonical_url=? LIMIT 1", (article["canonical_url"],)).fetchone()
    if exact:
        return exact["story_id"]
    cutoff = (utc_now() - timedelta(days=7)).isoformat()
    rows = db.execute(
        "SELECT id,representative_title,language,maldives,story_location FROM stories WHERE last_seen>=? ORDER BY last_seen DESC LIMIT 350",
        (cutoff,),
    ).fetchall()
    for row in rows:
        if row["language"] != article["language"]:
            continue
        if int(row["maldives"]) != int(article["maldives"]):
            continue
        if row["story_location"] != article["story_location"]:
            continue
        if headline_similarity(article["title"], row["representative_title"]) >= 0.78:
            return row["id"]
    return None


def archive_article(article):
    with DB_LOCK, db_connect() as db:
        exists = db.execute("SELECT id,story_id FROM articles WHERE article_uid=?", (article["article_uid"],)).fetchone()
        if exists:
            return exists["story_id"], False
        story_id = find_matching_story(db, article)
        now = article["fetched_at"]
        if story_id is None:
            publishers = json.dumps([article["publisher"]], ensure_ascii=False)
            cursor = db.execute(
                """
                INSERT INTO stories(representative_title,normalized_title,category,language,maldives,story_location,
                    importance,breaking,low_value,primary_url,primary_publisher,publishers_json,article_count,first_seen,last_seen)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    article["title"], normalize_title(article["title"]), article["category"], article["language"], article["maldives"],
                    article["story_location"], article["importance"], article["breaking"], article["low_value"], article["url"],
                    article["publisher"], publishers, 1, now, now,
                ),
            )
            story_id = cursor.lastrowid
        else:
            row = db.execute("SELECT publishers_json,importance,breaking,low_value FROM stories WHERE id=?", (story_id,)).fetchone()
            publishers = set(json.loads(row["publishers_json"] or "[]"))
            publishers.add(article["publisher"])
            db.execute(
                """
                UPDATE stories SET last_seen=?, article_count=article_count+1,
                    importance=MAX(importance,?), breaking=MAX(breaking,?), low_value=MIN(low_value,?),
                    publishers_json=? WHERE id=?
                """,
                (now, article["importance"], article["breaking"], article["low_value"], json.dumps(sorted(publishers), ensure_ascii=False), story_id),
            )
        db.execute(
            """
            INSERT INTO articles(article_uid,story_id,source_feed,publisher,publisher_domain,publisher_country,title,description,url,
                canonical_url,language,category,maldives,story_location,importance,breaking,low_value,published_at,fetched_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                article["article_uid"], story_id, article["source_feed"], article["publisher"], article["publisher_domain"],
                article["publisher_country"], article["title"], article["description"], article["url"], article["canonical_url"],
                article["language"], article["category"], article["maldives"], article["story_location"], article["importance"],
                article["breaking"], article["low_value"], article["published_at"], article["fetched_at"],
            ),
        )
        db.commit()
        return story_id, True


def archive_articles(articles):
    changed_story_ids = set()
    new_articles = 0
    for article in articles:
        story_id, created = archive_article(article)
        if created:
            changed_story_ids.add(story_id)
            new_articles += 1
    logging.info("Archived %s new articles into %s changed stories", new_articles, len(changed_story_ids))
    return changed_story_ids


def story_rows_by_ids(ids):
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    with DB_LOCK, db_connect() as db:
        return db.execute(f"SELECT * FROM stories WHERE id IN ({marks})", tuple(ids)).fetchall()


def story_summary(story_id):
    with DB_LOCK, db_connect() as db:
        row = db.execute(
            "SELECT title,description,language FROM articles WHERE story_id=? ORDER BY importance DESC,id ASC LIMIT 1",
            (story_id,),
        ).fetchone()
    if not row:
        return ["Open the original source for the full report.", ""]
    return local_summary(row["title"], row["description"], row["language"])


def publishers_for_story(row):
    try:
        return list(json.loads(row["publishers_json"] or "[]"))
    except Exception:
        return [row["primary_publisher"]]


def telegram_api(method, payload=None, timeout=40):
    if not TELEGRAM_BOT_TOKEN:
        return None
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}", json=payload or {}, timeout=timeout
        )
        data = response.json()
        if response.status_code != 200 or not data.get("ok"):
            logging.error("Telegram %s error: %s", method, data.get("description", response.text[:300]))
            return None
        return data.get("result")
    except Exception as error:
        logging.error("Telegram connection error: %s", error)
        return None


def send_message(text, chat_id=None, reply_markup=None, disable_preview=True):
    payload = {
        "chat_id": str(chat_id or GROUP_CHAT_ID),
        "text": str(text)[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return telegram_api("sendMessage", payload)


def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": str(chat_id), "message_id": message_id, "text": str(text)[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return telegram_api("editMessageText", payload)


def bot_username():
    global BOT_USERNAME
    if BOT_USERNAME:
        return BOT_USERNAME
    info = telegram_api("getMe")
    if isinstance(info, dict):
        BOT_USERNAME = str(info.get("username") or "").strip().lstrip("@")
    return BOT_USERNAME


def main_keyboard():
    return {
        "keyboard": [
            [{"text": "🇲🇻 Maldives"}, {"text": "🌍 Global"}, {"text": "🚨 Important"}],
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


def private_destination(message):
    chat_id = (message.get("chat") or {}).get("id")
    sender_id = (message.get("from") or {}).get("id")
    from_group = sender_id is not None and chat_id is not None and str(sender_id) != str(chat_id)
    return (sender_id if from_group else chat_id), chat_id, from_group


def rate_allowed(user_id):
    if user_id is None:
        return True
    key = str(user_id)
    now = time.time()
    bucket = [stamp for stamp in RATE_MEMORY.get(key, []) if now - stamp <= USER_REQUEST_WINDOW_SECONDS]
    if len(bucket) >= USER_REQUEST_LIMIT:
        RATE_MEMORY[key] = bucket
        return False
    bucket.append(now)
    RATE_MEMORY[key] = bucket
    return True


def deep_link_markup(payload):
    username = bot_username()
    if not username:
        return None
    return {"inline_keyboard": [[{"text": "📩 Open Private News", "url": f"https://t.me/{username}?start={payload}"}]]}


def send_private(message, text, reply_markup=None, start_payload="menu"):
    destination, origin_chat_id, from_group = private_destination(message)
    if destination is None:
        return None
    if not rate_allowed(destination):
        return send_message("⏳ Too many requests. Please wait a moment and try again.", destination, main_keyboard())
    result = send_message(text, destination, reply_markup or main_keyboard())
    if result:
        return result
    if from_group and origin_chat_id is not None:
        markup = deep_link_markup(start_payload)
        instruction = (
            "📩 <b>Open your private news chat</b>\n\n"
            "Telegram requires you to press <b>Start</b> once before I can send private news. "
            "Tap the button below. Your original request will open automatically after Start."
        )
        return send_message(instruction, origin_chat_id, markup)
    return None


def query_stories(kind, page=0, language=None, page_size=PRIVATE_PAGE_SIZE):
    where = []
    params = []
    if kind == "maldives":
        where.append("maldives=1")
    elif kind == "global":
        where.append("maldives=0")
    elif kind == "important":
        where.append("(breaking=1 OR importance>=75)")
    elif kind == "breaking":
        where.append("breaking=1")
    elif kind in {"politics", "business", "technology", "sports", "entertainment", "health", "science", "travel", "environment", "crime"}:
        mapping = {
            "politics": "Politics", "business": "Business", "technology": "Technology & AI", "sports": "Sports",
            "entertainment": "Entertainment", "health": "Health", "science": "Science", "travel": "Travel & Tourism",
            "environment": "Environment", "crime": "Crime & Courts",
        }
        where.append("category=?")
        params.append(mapping[kind])
    if language in {"en", "dv"}:
        where.append("language=?")
        params.append(language)
    cutoff = (utc_now() - timedelta(days=ARCHIVE_RETENTION_DAYS)).isoformat()
    where.append("last_seen>=?")
    params.append(cutoff)
    clause = " AND ".join(where) if where else "1=1"
    order = "breaking DESC, importance DESC, last_seen DESC" if kind in {"important", "breaking"} else "last_seen DESC, importance DESC"
    offset = max(0, page) * page_size
    with DB_LOCK, db_connect() as db:
        total = db.execute(f"SELECT COUNT(*) AS c FROM stories WHERE {clause}", tuple(params)).fetchone()["c"]
        rows = db.execute(
            f"SELECT * FROM stories WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
            tuple(params + [page_size, offset]),
        ).fetchall()
    return rows, total


def format_story_page(title, kind, rows, total, page, language=None):
    total_pages = max(1, (total + PRIVATE_PAGE_SIZE - 1) // PRIVATE_PAGE_SIZE)
    page = min(max(page, 0), total_pages - 1)
    message = f"📰 <b>{html.escape(title)}</b> · Page {page + 1}/{total_pages}\n\n"
    if not rows:
        message += "No matching stories are stored yet. The archive refreshes automatically every few minutes."
        return message, None
    start = page * PRIVATE_PAGE_SIZE + 1
    for index, row in enumerate(rows, start=start):
        emoji = CATEGORY_EMOJIS.get(row["category"], "📰")
        headline = html.escape(row["representative_title"])
        url = html.escape(row["primary_url"], quote=True)
        publisher = html.escape(row["primary_publisher"])
        region = "🇲🇻" if row["maldives"] else "🌍"
        lang = "DV" if row["language"] == "dv" else "EN"
        block = (
            f'{index}. {region} {emoji} <a href="{url}">{headline}</a>\n'
            f"   {publisher} · {html.escape(row['category'])} · 🌐 {lang} · 📊 {row['importance']}/100\n\n"
        )
        if len(message) + len(block) > 3600:
            break
        message += block
    buttons = []
    nav = []
    lang_code = language or "all"
    if page > 0:
        nav.append({"text": "⬅️ Previous", "callback_data": f"page|{kind}|{lang_code}|{page-1}"})
    if page + 1 < total_pages:
        nav.append({"text": "Next ➡️", "callback_data": f"page|{kind}|{lang_code}|{page+1}"})
    if nav:
        buttons.append(nav)
    if kind == "maldives":
        buttons.append([
            {"text": "🇬🇧 English", "callback_data": "page|maldives|en|0"},
            {"text": "🇲🇻 Dhivehi", "callback_data": "page|maldives|dv|0"},
        ])
    return message.rstrip(), ({"inline_keyboard": buttons} if buttons else None)


def title_for_kind(kind, language=None):
    titles = {
        "maldives": "Maldives News", "global": "Global News", "important": "Important News", "breaking": "Breaking & Urgent News",
        "politics": "Politics", "business": "Business & Economy", "technology": "Technology & AI", "sports": "Sports",
        "entertainment": "Entertainment", "health": "Health", "science": "Science & Research", "travel": "Travel & Tourism",
        "environment": "Environment & Climate", "crime": "Crime & Courts", "latest": "Latest News",
    }
    title = titles.get(kind, "News")
    if kind == "maldives" and language == "en":
        title = "🇬🇧 Maldives News — English"
    elif kind == "maldives" and language == "dv":
        title = "🇲🇻 ދިވެހި ނޫސް"
    return title


def send_kind_page(message, kind, page=0, language=None):
    rows, total = query_stories(kind, page, language)
    text, markup = format_story_page(title_for_kind(kind, language), kind, rows, total, page, language)
    return send_private(message, text, markup or main_keyboard(), start_payload=f"view_{kind}_{language or 'all'}")


def send_maldives_bilingual(message):
    intro = send_private(
        message,
        "🇲🇻 <b>Maldives News Archive</b>\n\nEnglish and Dhivehi are kept separately so one language cannot hide the other. Use Next/Previous to browse all stored Maldives stories.",
        main_keyboard(),
        start_payload="view_maldives_all",
    )
    if not intro:
        return
    destination, _, _ = private_destination(message)
    for language in ("en", "dv"):
        rows, total = query_stories("maldives", 0, language)
        text, markup = format_story_page(title_for_kind("maldives", language), "maldives", rows, total, 0, language)
        send_message(text, destination, markup)


def search_stories(query, page=0):
    terms = [term.lower() for term in clean_text(query).split() if term]
    if not terms:
        return [], 0
    cutoff = (utc_now() - timedelta(days=ARCHIVE_RETENTION_DAYS)).isoformat()
    with DB_LOCK, db_connect() as db:
        rows = db.execute(
            "SELECT * FROM stories WHERE last_seen>=? ORDER BY last_seen DESC LIMIT 1000", (cutoff,)
        ).fetchall()
    matches = []
    for row in rows:
        searchable = " ".join([row["representative_title"], row["category"], row["primary_publisher"], row["story_location"]]).lower()
        if all(term in searchable for term in terms):
            matches.append(row)
    total = len(matches)
    start = page * PRIVATE_PAGE_SIZE
    return matches[start : start + PRIVATE_PAGE_SIZE], total


def health_text():
    with DB_LOCK, db_connect() as db:
        rows = db.execute("SELECT * FROM source_health ORDER BY consecutive_failures DESC, source_name").fetchall()
    healthy = sum(1 for row in rows if row["consecutive_failures"] == 0)
    lines = [f"📡 <b>Source Health</b>\n\nHealthy: <b>{healthy}/{len(rows)}</b>\n"]
    for row in rows[:20]:
        icon = "✅" if row["consecutive_failures"] == 0 else "⚠️"
        lines.append(f"{icon} {html.escape(row['source_name'])} · {row['article_count']} items · {row['response_ms']} ms")
    return "\n".join(lines)[:3900]


def sources_text():
    lines = [f"🗞️ <b>Maldives News Sources</b>\n\nMonitoring <b>{len(MALDIVES_DOMAINS)}</b> Maldivian publisher domains in both English and Dhivehi discovery feeds, plus direct RSS where available.\n"]
    for index, domain in enumerate(MALDIVES_DOMAINS, start=1):
        lines.append(f"{index}. {domain}")
    return "\n".join(lines)[:3900]


def welcome_text():
    return (
        f"📰 <b>{BOT_NAME}</b>\n\n"
        "🇲🇻 Maldives — English + Dhivehi archive\n"
        "🌍 Global — worldwide news\n"
        "🚨 Important — high-priority and breaking developments\n"
        "🧭 News Topics — politics, business, technology/AI, sports, entertainment, health, science, travel, crime/courts and environment\n\n"
        "Automatic selected news stays in the group. Interactive results are private."
    )


BUTTON_KIND = {
    "🌍 Global": "global", "🚨 Important": "important", "🚨 Breaking": "breaking", "🏛️ Politics": "politics",
    "💰 Business": "business", "💻 Technology & AI": "technology", "⚽ Sports": "sports", "🎬 Entertainment": "entertainment",
    "🏥 Health": "health", "🔬 Science": "science", "✈️ Travel & Tourism": "travel", "🌊 Environment": "environment",
    "⚖️ Crime & Courts": "crime", "📰 Latest": "latest",
}
COMMAND_KIND = {
    "/global": "global", "/world": "global", "/important": "important", "/trending": "important", "/breaking": "breaking",
    "/politics": "politics", "/business": "business", "/technology": "technology", "/tech": "technology", "/sports": "sports",
    "/entertainment": "entertainment", "/health": "health", "/science": "science", "/travel": "travel", "/environment": "environment",
    "/crime": "crime", "/latest": "latest",
}


def handle_message(message):
    text = str(message.get("text", "") or "").strip()
    if not text:
        return
    parts = text.split(maxsplit=1)
    command = parts[0].split("@")[0].lower() if text.startswith("/") else ""
    argument = parts[1].strip() if len(parts) > 1 else ""
    if command == "/start":
        send_private(message, welcome_text(), main_keyboard())
        if argument.startswith("view_"):
            payload = argument[5:]
            bits = payload.rsplit("_", 1)
            kind = bits[0]
            language = bits[1] if len(bits) == 2 and bits[1] in {"en", "dv"} else None
            if kind == "maldives" and not language:
                send_maldives_bilingual(message)
            elif kind in {"maldives", "global", "important", "breaking", "politics", "business", "technology", "sports", "entertainment", "health", "science", "travel", "environment", "crime", "latest"}:
                send_kind_page(message, kind, 0, language)
        return
    if command in {"/help", "/menu"} or text == "⬅️ Main Menu":
        send_private(message, welcome_text(), main_keyboard())
        return
    if text in {"🧭 News Topics", "🧭 Related Topics"} or command == "/topics":
        send_private(message, "🧭 <b>News Topics</b>\n\nChoose a topic below. Results are sent privately.", topics_keyboard(), "topics")
        return
    if text == "🇲🇻 Maldives" or command == "/maldives":
        send_maldives_bilingual(message)
        return
    kind = BUTTON_KIND.get(text) or COMMAND_KIND.get(command)
    if kind:
        send_kind_page(message, kind)
        return
    if command == "/sources":
        send_private(message, sources_text(), main_keyboard(), "sources")
        return
    if command == "/health":
        sender = str((message.get("from") or {}).get("id") or "")
        if ADMIN_USER_IDS and sender not in ADMIN_USER_IDS:
            send_private(message, "🔒 This command is restricted to bot administrators.", main_keyboard())
        else:
            send_private(message, health_text(), main_keyboard())
        return
    if command == "/search":
        if not argument:
            send_private(message, "🔎 <b>Search news</b>\n\nExample: <code>/search Maldives tourism</code>", main_keyboard())
            return
        rows, total = search_stories(argument, 0)
        text_out, markup = format_story_page(f"Search: {argument}", "latest", rows, total, 0)
        send_private(message, text_out, markup or main_keyboard())
        return


def handle_callback(callback):
    callback_id = callback.get("id")
    data = str(callback.get("data") or "")
    message = callback.get("message") or {}
    sender = callback.get("from") or {}
    telegram_api("answerCallbackQuery", {"callback_query_id": callback_id})
    if not data.startswith("page|"):
        return
    bits = data.split("|")
    if len(bits) != 4:
        return
    _, kind, lang_code, page_text = bits
    try:
        page = max(0, int(page_text))
    except ValueError:
        page = 0
    language = lang_code if lang_code in {"en", "dv"} else None
    rows, total = query_stories(kind, page, language)
    text, markup = format_story_page(title_for_kind(kind, language), kind, rows, total, page, language)
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    if chat_id and message_id and str(chat_id) == str(sender.get("id")):
        edit_message(chat_id, message_id, text, markup)


def group_post_message(row):
    summary = story_summary(row["id"])
    emoji = CATEGORY_EMOJIS.get(row["category"], "📰")
    header = "🚨 <b>BREAKING NEWS</b>\n\n" if row["breaking"] else ("🔥 <b>IMPORTANT NEWS</b>\n\n" if row["importance"] >= 82 else "")
    lang = "Dhivehi" if row["language"] == "dv" else "English"
    region = "🇲🇻 Maldives" if row["maldives"] else "🌍 Global"
    publishers = html.escape(", ".join(publishers_for_story(row)[:4]))
    return (
        f"{header}{emoji} <b>{html.escape(row['category'])}</b> · {region} · {lang}\n\n"
        f"📰 <b>{html.escape(row['representative_title'])}</b>\n\n"
        f"• {html.escape(summary[0])}\n"
        f"• {html.escape(summary[1])}\n\n"
        f"📊 <b>Priority:</b> {row['importance']}/100\n"
        f"🏢 <b>Sources:</b> {publishers}\n\n"
        f'<a href="{html.escape(row["primary_url"], quote=True)}">🔗 Open original report</a>'
    )


def select_group_candidates(changed_ids):
    rows = story_rows_by_ids(changed_ids)
    eligible = [
        row for row in rows
        if not row["low_value"] and row["importance"] >= MINIMUM_POST_SCORE
        and (
            not row["published_to_group"]
            or row["breaking"] > row["published_breaking"]
            or row["importance"] >= row["published_importance"] + 15
        )
    ]
    buckets = {"mv_en": [], "mv_dv": [], "global": []}
    for row in eligible:
        if row["maldives"]:
            buckets["mv_dv" if row["language"] == "dv" else "mv_en"].append(row)
        else:
            buckets["global"].append(row)
    for bucket in buckets.values():
        bucket.sort(key=lambda row: (row["breaking"], row["importance"], row["last_seen"]), reverse=True)
    ordered = []
    while any(buckets.values()):
        for name in ("mv_en", "mv_dv", "global"):
            if buckets[name]:
                ordered.append(buckets[name].pop(0))
    selected = []
    category_counts = {}
    for row in ordered:
        key = ("mv" if row["maldives"] else "global", row["category"])
        if category_counts.get(key, 0) >= 2 and not row["breaking"]:
            continue
        selected.append(row)
        category_counts[key] = category_counts.get(key, 0) + 1
        if len(selected) >= MAX_POSTS_PER_CHECK:
            break
    return selected


def mark_group_published(row):
    with DB_LOCK, db_connect() as db:
        db.execute(
            "UPDATE stories SET published_to_group=1,published_importance=?,published_breaking=? WHERE id=?",
            (row["importance"], row["breaking"], row["id"]),
        )
        db.commit()


async def check_and_publish_news():
    logging.info("Starting unified all-news collection...")
    articles = await asyncio.to_thread(fetch_all_articles)
    changed_ids = await asyncio.to_thread(archive_articles, articles)
    set_setting("last_news_check", utc_now_iso())
    candidates = select_group_candidates(changed_ids)
    posted = 0
    for row in candidates:
        message = group_post_message(row)
        result = await asyncio.to_thread(send_message, message, GROUP_CHAT_ID, None, False)
        if result:
            mark_group_published(row)
            posted += 1
            await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    cleanup_db()
    logging.info("News cycle complete: %s group posts; %s changed stories archived", posted, len(changed_ids))


def digest_message(title, hours):
    cutoff = (utc_now() - timedelta(hours=hours)).isoformat()
    with DB_LOCK, db_connect() as db:
        rows = db.execute(
            "SELECT * FROM stories WHERE last_seen>=? ORDER BY breaking DESC,importance DESC,last_seen DESC LIMIT 12",
            (cutoff,),
        ).fetchall()
    if not rows:
        return f"📰 <b>{html.escape(title)}</b>\n\nNo new stories were archived in this period."
    message = f"📰 <b>{html.escape(title)}</b>\n\n"
    for index, row in enumerate(rows, start=1):
        region = "🇲🇻" if row["maldives"] else "🌍"
        emoji = CATEGORY_EMOJIS.get(row["category"], "📰")
        line = f'{index}. {region} {emoji} <a href="{html.escape(row["primary_url"], quote=True)}">{html.escape(row["representative_title"])}</a>\n'
        if len(message) + len(line) > 3800:
            break
        message += line
    return message


async def digest_scheduler():
    while True:
        now = maldives_now()
        today = now.date().isoformat()
        if now.hour == MORNING_DIGEST_HOUR and now.minute < 5 and get_setting("last_morning_digest") != today:
            await asyncio.to_thread(send_message, digest_message("Morning News Brief", 12), GROUP_CHAT_ID)
            set_setting("last_morning_digest", today)
        if now.hour == EVENING_DIGEST_HOUR and now.minute < 5 and get_setting("last_evening_digest") != today:
            await asyncio.to_thread(send_message, digest_message("Evening News Brief", 12), GROUP_CHAT_ID)
            set_setting("last_evening_digest", today)
        await asyncio.sleep(60)


def get_updates():
    try:
        offset = int(get_setting("telegram_offset", "0") or 0)
    except ValueError:
        offset = 0
    return telegram_api(
        "getUpdates",
        {"offset": offset, "timeout": 25, "allowed_updates": ["message", "callback_query"]},
        timeout=35,
    )


async def command_listener():
    while True:
        updates = await asyncio.to_thread(get_updates)
        if not updates:
            await asyncio.sleep(1)
            continue
        for update in updates:
            set_setting("telegram_offset", update.get("update_id", 0) + 1)
            try:
                if update.get("message"):
                    await asyncio.to_thread(handle_message, update["message"])
                elif update.get("callback_query"):
                    await asyncio.to_thread(handle_callback, update["callback_query"])
            except Exception as error:
                logging.exception("Telegram interaction failed: %s", error)


async def automatic_news_loop():
    while True:
        try:
            await check_and_publish_news()
        except Exception as error:
            logging.exception("News check failed: %s", error)
        await asyncio.sleep(NEWS_CHECK_INTERVAL_SECONDS)


PUBLIC_COMMANDS = [
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
    {"command": "search", "description": "Search archived news"},
    {"command": "sources", "description": "Show Maldives news outlets monitored"},
]


def validate_configuration():
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not GROUP_CHAT_ID:
        missing.append("GROUP_CHAT_ID")
    if missing:
        raise ValueError("Missing required environment variable(s): " + ", ".join(missing))


async def main():
    validate_configuration()
    init_db()
    info = await asyncio.to_thread(telegram_api, "getMe")
    if not info:
        raise RuntimeError("Telegram connection failed")
    global BOT_USERNAME
    BOT_USERNAME = str(info.get("username") or "").strip().lstrip("@")
    await asyncio.to_thread(telegram_api, "setMyCommands", {"commands": PUBLIC_COMMANDS})
    if get_setting("startup_announcement_version") != APP_VERSION:
        await asyncio.to_thread(send_message, welcome_text(), GROUP_CHAT_ID, main_keyboard(), True)
        set_setting("startup_announcement_version", APP_VERSION)
    await asyncio.gather(automatic_news_loop(), command_listener(), digest_scheduler())


init_db()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped", BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
