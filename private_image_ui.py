"""Private image-card browsing layered on top of continuous_private_ui.

Private Maldives, Global, Important and topic results are delivered as publisher
image cards when available. The first 10 stories are sent automatically; additional
results are available through a Show more button. Text fallback is used whenever an
outlet does not expose a usable article image.
"""

import asyncio
import html
import logging
import time

import main as bot
import private_group_ui as ui
import continuous_private_ui as base

PRIVATE_BATCH_SIZE = 10
PRIVATE_STORY_DELAY_SECONDS = 0.65


def private_story_caption(row):
    """Build valid HTML for a Telegram photo caption without slicing through tags."""
    summary = bot.story_summary(row["id"])
    emoji = bot.CATEGORY_EMOJIS.get(row["category"], "📰")
    region = "🇲🇻 Maldives" if row["maldives"] else "🌍 Global"
    lang = "Dhivehi" if row["language"] == "dv" else "English"
    header = "🚨 <b>BREAKING NEWS</b>\n\n" if row["breaking"] else (
        "🔥 <b>IMPORTANT NEWS</b>\n\n" if row["importance"] >= 82 else ""
    )
    title = html.escape(bot.shorten_text(row["representative_title"], 220))
    publisher = html.escape(bot.shorten_text(row["primary_publisher"], 80))
    summary_text = html.escape(bot.shorten_text(summary[0] if summary else "", 220))
    return (
        f"{header}{emoji} <b>{html.escape(row['category'])}</b> · {region} · {lang}\n\n"
        f"📰 <b>{title}</b>\n\n"
        f"{summary_text}\n\n"
        f"🏢 <b>Source:</b> {publisher}\n"
        f"📊 <b>Priority:</b> {row['importance']}/100"
    )


def private_story_text(row):
    """Text fallback with a complete, valid HTML link."""
    caption = private_story_caption(row)
    url = html.escape(row["primary_url"], quote=True)
    return f'{caption}\n\n<a href="{url}">🔗 Open original report</a>'


def article_link_markup(row):
    return {
        "inline_keyboard": [[
            {
                "text": "🔗 Open original report",
                "url": str(row["primary_url"]),
            }
        ]]
    }


def send_private_story(destination, row):
    image_url = base.resolve_article_image(row["primary_url"])
    if image_url:
        result = bot.telegram_api(
            "sendPhoto",
            {
                "chat_id": str(destination),
                "photo": image_url,
                "caption": private_story_caption(row),
                "parse_mode": "HTML",
                "reply_markup": article_link_markup(row),
            },
            timeout=45,
        )
        if result:
            logging.info("Sent private story with publisher image: %s", row["primary_publisher"])
            return result
        logging.info("Private publisher image failed; using text fallback for %s", row["primary_publisher"])
    return bot.send_message(private_story_text(row), destination, None, False)


def query_batch(kind, language=None, offset=0, size=PRIVATE_BATCH_SIZE):
    page = max(0, int(offset)) // max(1, int(size))
    rows, total = base._base_query_stories(kind, page, language, page_size=size)
    return list(rows), int(total or 0)


def more_markup(kind, language, next_offset, total):
    buttons = []
    if next_offset < total:
        lang_code = language if language in {"en", "dv"} else "all"
        buttons.append([
            {
                "text": f"➕ Show more ({total - next_offset} left)",
                "callback_data": f"more|{kind}|{lang_code}|{next_offset}",
            }
        ])
    return {"inline_keyboard": buttons} if buttons else bot.main_keyboard()


def send_batch(message, kind, language=None, offset=0, title=None, announce=True):
    destination, _, _ = bot.private_destination(message)
    if destination is None:
        return None

    rows, total = query_batch(kind, language, offset)
    title = title or bot.title_for_kind(kind, language)

    if announce:
        intro = bot.send_private(
            message,
            f"📰 <b>{html.escape(title)}</b>\n\n"
            f"Showing up to <b>{PRIVATE_BATCH_SIZE}</b> stories with publisher images when available. "
            f"Stored results: <b>{total}</b>.",
            None,
            start_payload=f"view_{kind}_{language or 'all'}",
        )
        if not intro:
            return None

    if not rows:
        return bot.send_message(
            f"📰 <b>{html.escape(title)}</b>\n\nNo matching stories are stored yet.",
            destination,
            bot.main_keyboard(),
        )

    last = None
    for row in rows:
        time.sleep(PRIVATE_STORY_DELAY_SECONDS)
        result = send_private_story(destination, row)
        if result:
            last = result

    next_offset = offset + len(rows)
    controls = more_markup(kind, language, next_offset, total)
    status = (
        f"✅ <b>Showing {offset + 1}–{next_offset} of {total}</b>"
        if total else "✅ <b>News loaded</b>"
    )
    return bot.send_message(status, destination, controls)


def send_kind_images(message, kind, page=0, language=None):
    return send_batch(message, kind, language, 0)


def send_maldives_images(message):
    destination, _, _ = bot.private_destination(message)
    if destination is None:
        return None

    en_rows, en_total = query_batch("maldives", "en", 0)
    dv_rows, dv_total = query_batch("maldives", "dv", 0)
    intro = bot.send_private(
        message,
        "🇲🇻 <b>Maldives News</b>\n\n"
        f"🇬🇧 English: <b>{en_total}</b> stored stories\n"
        f"🇲🇻 Dhivehi: <b>{dv_total}</b> stored stories\n\n"
        "The first 10 from each language are shown with publisher images when available.",
        None,
        start_payload="view_maldives_all",
    )
    if not intro:
        return None

    if en_rows:
        bot.send_message("🇬🇧 <b>Maldives News — English</b>", destination)
        for row in en_rows:
            time.sleep(PRIVATE_STORY_DELAY_SECONDS)
            send_private_story(destination, row)
        en_next = len(en_rows)
        bot.send_message(
            f"✅ <b>English: showing 1–{en_next} of {en_total}</b>",
            destination,
            more_markup("maldives", "en", en_next, en_total),
        )

    if dv_rows:
        bot.send_message("🇲🇻 <b>ދިވެހި ނޫސް</b>", destination)
        for row in dv_rows:
            time.sleep(PRIVATE_STORY_DELAY_SECONDS)
            send_private_story(destination, row)
        dv_next = len(dv_rows)
        return bot.send_message(
            f"✅ <b>ދިވެހި: 1–{dv_next} / {dv_total}</b>",
            destination,
            more_markup("maldives", "dv", dv_next, dv_total),
        )

    if not en_rows and not dv_rows:
        return bot.send_message("No Maldives stories are stored yet.", destination, bot.main_keyboard())
    return intro


def send_search_images(message, query):
    rows, total = base.collect_all_search(query)
    rows = rows[:PRIVATE_BATCH_SIZE]
    destination, _, _ = bot.private_destination(message)
    if destination is None:
        return None
    intro = bot.send_private(
        message,
        f"🔎 <b>Search: {html.escape(query)}</b>\n\n"
        f"Showing up to <b>{PRIVATE_BATCH_SIZE}</b> image cards from <b>{total}</b> matches.",
        None,
        start_payload="search",
    )
    if not intro:
        return None
    for row in rows:
        time.sleep(PRIVATE_STORY_DELAY_SECONDS)
        send_private_story(destination, row)
    return bot.send_message(
        f"✅ <b>Showing {len(rows)} of {total} search matches</b>",
        destination,
        bot.main_keyboard(),
    )


def callback_message(callback):
    return {
        "chat": (callback.get("message") or {}).get("chat") or {},
        "from": callback.get("from") or {},
        "text": "",
    }


def handle_callback(callback):
    data = str(callback.get("data") or "")
    if not data.startswith("more|"):
        return base.handle_callback(callback)

    callback_id = callback.get("id")
    bits = data.split("|")
    if len(bits) != 4:
        if callback_id:
            bot.telegram_api(
                "answerCallbackQuery",
                {"callback_query_id": callback_id, "text": "Invalid request."},
            )
        return None

    _, kind, lang_code, offset_text = bits
    try:
        offset = max(0, int(offset_text))
    except ValueError:
        offset = 0
    language = lang_code if lang_code in {"en", "dv"} else None

    # Telegram expects callback queries to be acknowledged quickly. Confirm the tap
    # before fetching images and sending the next batch, which can take several seconds.
    if callback_id:
        bot.telegram_api(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_id,
                "text": "Loading more news…",
                "show_alert": False,
            },
        )

    message = callback_message(callback)
    return send_batch(message, kind, language, offset, announce=False)


def handle_message(message):
    text = str(message.get("text") or "").strip()
    if text.startswith("/search"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            if ui.is_group_message(message):
                ui.delete_group_interaction_message(message)
            return send_search_images(message, parts[1].strip())
    return base.handle_message(message)


# Replace private browsing only. Group image posting, new-member keyboards and first-time
# private-start prompts remain provided by the existing layers.
bot.send_kind_page = send_kind_images
bot.send_maldives_bilingual = send_maldives_images
ui.send_maldives_from_callback = send_maldives_images
bot.handle_message = handle_message
bot.handle_callback = handle_callback


async def main():
    await base.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped", bot.BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
