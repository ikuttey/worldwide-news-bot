"""Private Telegram news browsing without user-facing pagination.

This presentation layer keeps the existing solid group keyboard and disappearing
button messages from private_group_ui.py. Private browsing sends every matching story
automatically without Next/Previous controls.

Automatic group posts also try to use each publisher article's own preview image.
The image is read from standard article metadata such as og:image or twitter:image.
If the publisher does not expose a usable image, Telegram falls back to the existing
text-only group post so news delivery is never blocked by image extraction.
"""

import asyncio
import html
import logging
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import main as bot
import private_group_ui as ui

STREAM_MESSAGE_LIMIT = 3650
STREAM_DELAY_SECONDS = 0.8
ARTICLE_IMAGE_HTML_LIMIT = 750000

_base_query_stories = bot.query_stories
_base_search_stories = bot.search_stories
_base_handle_message = bot.handle_message
_base_handle_callback = bot.handle_callback


class ArticleImageParser(HTMLParser):
    """Extract the publisher's preferred article image from HTML metadata."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates = []

    def handle_starttag(self, tag, attrs):
        values = {str(key).lower(): value for key, value in attrs if key and value}
        if tag.lower() == "meta":
            key = str(values.get("property") or values.get("name") or "").lower().strip()
            if key in {
                "og:image",
                "og:image:url",
                "og:image:secure_url",
                "twitter:image",
                "twitter:image:src",
            }:
                content = str(values.get("content") or "").strip()
                if content:
                    self.candidates.append(content)
        elif tag.lower() == "link":
            rel = str(values.get("rel") or "").lower()
            href = str(values.get("href") or "").strip()
            if href and "image_src" in rel:
                self.candidates.append(href)


def usable_image_url(url):
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return False
    try:
        host = urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return False
    if not host:
        return False
    # Avoid generic Google News branding being mistaken for the publisher's article image.
    blocked = {"news.google.com", "google.com", "www.google.com", "gstatic.com"}
    return not any(host == item or host.endswith("." + item) for item in blocked)


def resolve_article_image(article_url):
    """Return an article preview image URL, or None when the outlet exposes none."""
    article_url = str(article_url or "").strip()
    if not article_url.startswith(("http://", "https://")):
        return None
    try:
        response = bot.requests.get(
            article_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
                    "Chrome/126.0 Mobile Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=(5, 12),
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = str(response.headers.get("content-type") or "").lower()
        if "html" not in content_type and not response.text.lstrip().startswith("<"):
            return None
        parser = ArticleImageParser()
        parser.feed(response.text[:ARTICLE_IMAGE_HTML_LIMIT])
        base_url = response.url or article_url
        for candidate in parser.candidates:
            resolved = urljoin(base_url, html.unescape(candidate).strip())
            if usable_image_url(resolved):
                return resolved
    except Exception as error:
        logging.debug("Article image lookup failed for %s: %s", article_url, error)
    return None


def group_photo_caption(row):
    """Build a compact Telegram photo caption while keeping source attribution."""
    summary = bot.story_summary(row["id"])
    emoji = bot.CATEGORY_EMOJIS.get(row["category"], "📰")
    header = "🚨 <b>BREAKING NEWS</b>\n\n" if row["breaking"] else (
        "🔥 <b>IMPORTANT NEWS</b>\n\n" if row["importance"] >= 82 else ""
    )
    region = "🇲🇻 Maldives" if row["maldives"] else "🌍 Global"
    lang = "Dhivehi" if row["language"] == "dv" else "English"
    title = html.escape(bot.shorten_text(row["representative_title"], 250))
    publisher = html.escape(bot.shorten_text(row["primary_publisher"], 90))
    summary_text = html.escape(bot.shorten_text(summary[0] if summary else "", 260))
    url = html.escape(row["primary_url"], quote=True)
    caption = (
        f"{header}{emoji} <b>{html.escape(row['category'])}</b> · {region} · {lang}\n\n"
        f"📰 <b>{title}</b>\n\n"
        f"{summary_text}\n\n"
        f"🏢 <b>Source:</b> {publisher}\n"
        f"📊 <b>Priority:</b> {row['importance']}/100\n\n"
        f'<a href="{url}">🔗 Open original report</a>'
    )
    # Telegram photo captions are shorter than normal text messages.
    return caption[:1000]


def clear_keyboard_keeper_after_photo(result):
    """Remove the short startup keyboard message after the first successful photo post."""
    keeper = getattr(ui, "_keyboard_keeper_message_id", None)
    if not keeper or not result:
        return
    new_message_id = result.get("message_id") if isinstance(result, dict) else None
    if new_message_id == keeper:
        return
    bot.telegram_api(
        "deleteMessage",
        {"chat_id": str(bot.GROUP_CHAT_ID), "message_id": keeper},
    )
    ui._keyboard_keeper_message_id = None
    bot.set_setting("solid_keyboard_keeper_message_id", "")


def send_group_story(row):
    """Send a group story with the publisher image when possible, otherwise text."""
    image_url = resolve_article_image(row["primary_url"])
    if image_url:
        payload = {
            "chat_id": str(bot.GROUP_CHAT_ID),
            "photo": image_url,
            "caption": group_photo_caption(row),
            "parse_mode": "HTML",
            "reply_markup": bot.main_keyboard(),
        }
        result = bot.telegram_api("sendPhoto", payload, timeout=45)
        if result:
            clear_keyboard_keeper_after_photo(result)
            logging.info("Posted group story with publisher image: %s", row["primary_publisher"])
            return result
        logging.info("Publisher image could not be sent; using text fallback for %s", row["primary_publisher"])

    return bot.send_message(bot.group_post_message(row), bot.GROUP_CHAT_ID, None, False)


async def check_and_publish_news_with_images():
    """Run the normal archive pipeline, adding publisher images only at group delivery."""
    logging.info("Starting unified all-news collection...")
    articles = await asyncio.to_thread(bot.fetch_all_articles)
    changed_ids = await asyncio.to_thread(bot.archive_articles, articles)
    bot.set_setting("last_news_check", bot.utc_now_iso())
    candidates = bot.select_group_candidates(changed_ids)
    posted = 0
    for row in candidates:
        result = await asyncio.to_thread(send_group_story, row)
        if result:
            bot.mark_group_published(row)
            posted += 1
            await asyncio.sleep(bot.MESSAGE_DELAY_SECONDS)
    bot.cleanup_db()
    logging.info(
        "News cycle complete: %s group posts; %s changed stories archived",
        posted,
        len(changed_ids),
    )


def collect_all_rows(kind, language=None):
    first, total = _base_query_stories(kind, 0, language)
    total = int(total or 0)
    if total <= len(first):
        return list(first), total
    rows, _ = _base_query_stories(kind, 0, language, page_size=total)
    return list(rows), total


def collect_all_search(query):
    rows = []
    page = 0
    total = None
    while True:
        batch, current_total = _base_search_stories(query, page)
        if total is None:
            total = int(current_total or 0)
        if not batch:
            break
        rows.extend(batch)
        if len(rows) >= current_total:
            break
        page += 1
    return rows, int(total or 0)


def story_block(row, index):
    emoji = bot.CATEGORY_EMOJIS.get(row["category"], "📰")
    region = "🇲🇻" if row["maldives"] else "🌍"
    lang = "DV" if row["language"] == "dv" else "EN"
    return (
        f'{index}. {region} {emoji} <a href="{html.escape(row["primary_url"], quote=True)}">'
        f'{html.escape(row["representative_title"])}</a>\n'
        f'   {html.escape(row["primary_publisher"])} · '
        f'{html.escape(row["category"])} · 🌐 {lang}\n\n'
    )


def build_chunks(title, rows, total):
    safe_title = html.escape(title)
    if not rows:
        return [
            f"📰 <b>{safe_title}</b>\n\n"
            "No matching stories are stored yet. The archive refreshes automatically every few minutes."
        ]

    header = f"📰 <b>{safe_title}</b> · {total} stories\n\n"
    continued = f"📰 <b>{safe_title}</b> · continued\n\n"
    chunks = []
    current = header

    for index, row in enumerate(rows, start=1):
        block = story_block(row, index)
        if len(current) + len(block) > STREAM_MESSAGE_LIMIT and current != header:
            chunks.append(current.rstrip())
            current = continued
        if len(current) + len(block) > STREAM_MESSAGE_LIMIT:
            block = block[: max(0, STREAM_MESSAGE_LIMIT - len(current) - 20)] + "…\n"
        current += block

    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def send_chunks(message, chunks, start_payload="menu"):
    if not chunks:
        return None

    first = bot.send_private(
        message,
        chunks[0],
        bot.main_keyboard() if len(chunks) == 1 else None,
        start_payload=start_payload,
    )
    if not first:
        return None

    destination, _, _ = bot.private_destination(message)
    last = first
    for index, chunk in enumerate(chunks[1:], start=1):
        time.sleep(STREAM_DELAY_SECONDS)
        markup = bot.main_keyboard() if index == len(chunks) - 1 else None
        result = bot.send_message(chunk, destination, markup)
        if not result:
            logging.warning("Private news stream stopped after %s/%s messages", index, len(chunks))
            break
        last = result
    return last


def send_kind_all(message, kind, page=0, language=None):
    rows, total = collect_all_rows(kind, language)
    return send_chunks(
        message,
        build_chunks(bot.title_for_kind(kind, language), rows, total),
        start_payload=f"view_{kind}_{language or 'all'}",
    )


def send_maldives_all(message):
    en_rows, en_total = collect_all_rows("maldives", "en")
    dv_rows, dv_total = collect_all_rows("maldives", "dv")
    chunks = [
        "🇲🇻 <b>Maldives News</b>\n\n"
        f"🇬🇧 English: <b>{en_total}</b> stories\n"
        f"🇲🇻 Dhivehi: <b>{dv_total}</b> stories\n\n"
        "All stored results follow automatically. No Next/Previous buttons are needed."
    ]
    chunks.extend(build_chunks(bot.title_for_kind("maldives", "en"), en_rows, en_total))
    chunks.extend(build_chunks(bot.title_for_kind("maldives", "dv"), dv_rows, dv_total))
    return send_chunks(message, chunks, start_payload="view_maldives_all")


def send_search_all(message, query):
    rows, total = collect_all_search(query)
    return send_chunks(message, build_chunks(f"Search: {query}", rows, total))


def callback_message(callback):
    return {
        "chat": (callback.get("message") or {}).get("chat") or {},
        "from": callback.get("from") or {},
        "text": "",
    }


def handle_callback(callback):
    data = str(callback.get("data") or "")
    if not data.startswith("page|"):
        return _base_handle_callback(callback)

    # Old private messages may still have pagination buttons. Tapping one now sends
    # the complete result stream instead of moving to another page.
    bits = data.split("|")
    if len(bits) != 4:
        return None
    _, kind, lang_code, _ = bits
    language = lang_code if lang_code in {"en", "dv"} else None
    message = callback_message(callback)
    result = send_kind_all(message, kind, language=language)
    callback_id = callback.get("id")
    if callback_id:
        bot.telegram_api(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_id,
                "text": "All matching news sent privately ✅" if result else "Could not send the private result.",
                "show_alert": False if result else True,
            },
        )
    return result


def handle_message(message):
    text = str(message.get("text") or "").strip()
    if text.startswith("/search"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            # Preserve the disappearing group-command behavior before sending search privately.
            if ui.is_group_message(message):
                ui.delete_group_interaction_message(message)
            return send_search_all(message, parts[1].strip())
    return _base_handle_message(message)


# Global lookups inside main.py resolve these replacements at runtime.
bot.check_and_publish_news = check_and_publish_news_with_images
bot.send_kind_page = send_kind_all
bot.send_maldives_bilingual = send_maldives_all
ui.send_maldives_from_callback = send_maldives_all
bot.handle_message = handle_message
bot.handle_callback = handle_callback


async def main():
    await ui.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped", bot.BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
