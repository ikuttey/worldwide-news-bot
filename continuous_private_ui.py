"""Private Telegram news browsing without user-facing pagination.

This presentation layer keeps the existing solid group keyboard and disappearing
button messages from private_group_ui.py. It changes only private browsing: every
matching story is sent automatically as one continuous result stream. Telegram's
message-size limit may require several consecutive messages, but users never need to
press Next or Previous.
"""

import asyncio
import html
import logging
import time

import main as bot
import private_group_ui as ui

STREAM_MESSAGE_LIMIT = 3650
STREAM_DELAY_SECONDS = 0.8

_base_query_stories = bot.query_stories
_base_search_stories = bot.search_stories
_base_handle_message = bot.handle_message
_base_handle_callback = bot.handle_callback


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


# Global lookups inside main.handle_message resolve these replacements at runtime.
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
