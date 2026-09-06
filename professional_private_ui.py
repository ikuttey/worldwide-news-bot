"""Professional private-news UX layered on top of the existing production launcher.

Core concept is preserved:
- public group = automatic broadcast news + temporary new-member Start onboarding
- private bot = all browsing and personalization

This layer adds five-story batches, a cleaner private home, language preference,
followed topics / My News, saved stories, related coverage, conversational search,
and optional private breaking or scheduled digest notifications.
"""

import asyncio
import html
import json
import logging
from datetime import timedelta

import private_start_prompt as app
import private_image_ui as image_ui

bot = app.bot
ui = app.ui

PRIVATE_BATCH_SIZE = 5
TOPIC_KINDS = [
    ("politics", "🏛️ Politics"),
    ("business", "💰 Business"),
    ("technology", "💻 Technology & AI"),
    ("sports", "⚽ Sports"),
    ("entertainment", "🎬 Entertainment"),
    ("health", "🏥 Health"),
    ("science", "🔬 Science"),
    ("travel", "✈️ Travel & Tourism"),
    ("environment", "🌊 Environment"),
    ("crime", "⚖️ Crime & Courts"),
]
TOPIC_LABELS = dict(TOPIC_KINDS)
NOTIFY_LABELS = {
    "off": "🔕 Off",
    "breaking": "🚨 Breaking only",
    "morning": "🌅 Morning digest",
    "evening": "🌙 Evening digest",
}

_base_handle_message = bot.handle_message
_base_handle_callback = bot.handle_callback
_base_digest_scheduler = bot.digest_scheduler
_base_send_maldives = bot.send_maldives_bilingual

# Reduce private floods from 10 cards to 5 while retaining publisher images and Show more.
image_ui.PRIVATE_BATCH_SIZE = PRIVATE_BATCH_SIZE
_original_query_batch = image_ui.query_batch


def query_batch_five(kind, language=None, offset=0, size=PRIVATE_BATCH_SIZE):
    return _original_query_batch(kind, language, offset, PRIVATE_BATCH_SIZE)


image_ui.query_batch = query_batch_five


def _uid(message_or_callback):
    return str((message_or_callback.get("from") or {}).get("id") or "")


def _setting(prefix, user_id, default=""):
    return bot.get_setting(f"user_{prefix}_{user_id}", default)


def _set_setting(prefix, user_id, value):
    bot.set_setting(f"user_{prefix}_{user_id}", value)


def _json_setting(prefix, user_id, default):
    raw = _setting(prefix, user_id, "")
    if not raw:
        return default
    try:
        value = json.loads(raw)
        return value
    except Exception:
        return default


def _set_json_setting(prefix, user_id, value):
    _set_setting(prefix, user_id, json.dumps(value, ensure_ascii=False))


def language_pref(user_id):
    value = _setting("language", user_id, "both")
    return value if value in {"en", "dv", "both"} else "both"


def subscriptions(user_id):
    values = _json_setting("topics", user_id, [])
    return [item for item in values if item in TOPIC_LABELS]


def saved_story_ids(user_id):
    values = _json_setting("saved", user_id, [])
    result = []
    for item in values:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result[:200]


def notification_pref(user_id):
    value = _setting("notify", user_id, "off")
    return value if value in NOTIFY_LABELS else "off"


def private_home_keyboard():
    return {
        "keyboard": [
            [{"text": "🇲🇻 Maldives"}, {"text": "🌍 Global"}],
            [{"text": "🚨 Important"}, {"text": "🧭 News Topics"}],
            [{"text": "⭐ My News"}, {"text": "🔖 Saved"}],
            [{"text": "🔎 Search"}, {"text": "⚙️ Settings"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Browse or personalize your private news…",
    }


def private_welcome_text():
    return (
        "📰 <b>Maldives & World News</b>\n\n"
        "Your private news center. The public group stays focused on automatic news updates; "
        "all browsing and personalization happen here.\n\n"
        "🇲🇻 <b>Maldives</b> — English + Dhivehi\n"
        "🌍 <b>Global</b> — worldwide coverage\n"
        "🚨 <b>Important</b> — high-priority developments\n"
        "🧭 <b>News Topics</b> — browse by category\n"
        "⭐ <b>My News</b> — stories from topics you follow\n"
        "🔖 <b>Saved</b> — bookmarked reports\n"
        "🔎 <b>Search</b> — find archived stories\n"
        "⚙️ <b>Settings</b> — language, followed topics and notifications\n\n"
        f"News opens in batches of <b>{PRIVATE_BATCH_SIZE}</b> so your chat stays readable."
    )


# Existing /start and Main Menu flows dynamically resolve these functions.
bot.main_keyboard = private_home_keyboard
bot.welcome_text = private_welcome_text


def article_actions(row):
    return {
        "inline_keyboard": [
            [{"text": "🔗 Open original report", "url": str(row["primary_url"])}],
            [
                {"text": "🔖 Save", "callback_data": f"save|{row['id']}"},
                {"text": "📰 Related coverage", "callback_data": f"related|{row['id']}"},
            ],
        ]
    }


# Every private image card now supports Save + Related coverage.
image_ui.article_link_markup = article_actions


def settings_markup(user_id):
    lang = language_pref(user_id)
    notify = notification_pref(user_id)
    lang_name = {"en": "English", "dv": "ދިވެހި", "both": "Both"}[lang]
    return {
        "inline_keyboard": [
            [{"text": f"🌐 Language: {lang_name}", "callback_data": "prefs|language"}],
            [{"text": "⭐ Choose My News topics", "callback_data": "prefs|topics"}],
            [{"text": f"🔔 Notifications: {NOTIFY_LABELS[notify]}", "callback_data": "prefs|notify"}],
            [{"text": "🏠 Private Home", "callback_data": "home"}],
        ]
    }


def send_settings(user_id):
    followed = subscriptions(user_id)
    followed_text = ", ".join(TOPIC_LABELS[item] for item in followed) if followed else "None yet"
    return bot.send_message(
        "⚙️ <b>Private News Settings</b>\n\n"
        f"⭐ <b>My News topics:</b> {html.escape(followed_text)}\n"
        f"🔔 <b>Automatic private updates:</b> {html.escape(NOTIFY_LABELS[notification_pref(user_id)])}\n\n"
        "These settings affect only your private bot chat.",
        user_id,
        settings_markup(user_id),
    )


def language_markup(user_id):
    current = language_pref(user_id)
    choices = [("en", "🇬🇧 English"), ("dv", "🇲🇻 ދިވެހި"), ("both", "🌐 Both")]
    rows = []
    for value, label in choices:
        mark = "✅ " if value == current else ""
        rows.append([{"text": mark + label, "callback_data": f"lang|{value}"}])
    rows.append([{"text": "⬅️ Settings", "callback_data": "prefs|back"}])
    return {"inline_keyboard": rows}


def topics_subscription_markup(user_id):
    selected = set(subscriptions(user_id))
    rows = []
    for index in range(0, len(TOPIC_KINDS), 2):
        row = []
        for kind, label in TOPIC_KINDS[index:index + 2]:
            prefix = "✅ " if kind in selected else "➕ "
            row.append({"text": prefix + label, "callback_data": f"sub|{kind}"})
        rows.append(row)
    rows.append([{"text": "⭐ Open My News", "callback_data": "mynews|0"}])
    rows.append([{"text": "⬅️ Settings", "callback_data": "prefs|back"}])
    return {"inline_keyboard": rows}


def notification_markup(user_id):
    current = notification_pref(user_id)
    rows = []
    for value in ("breaking", "morning", "evening", "off"):
        prefix = "✅ " if value == current else ""
        rows.append([{"text": prefix + NOTIFY_LABELS[value], "callback_data": f"notify|{value}"}])
    rows.append([{"text": "⬅️ Settings", "callback_data": "prefs|back"}])
    return {"inline_keyboard": rows}


def _story_rows_in_order(ids):
    if not ids:
        return []
    rows = bot.story_rows_by_ids(ids)
    by_id = {int(row["id"]): row for row in rows}
    return [by_id[item] for item in ids if item in by_id]


def send_saved_batch(user_id, offset=0):
    ids = saved_story_ids(user_id)
    rows = _story_rows_in_order(ids)
    if not rows:
        return bot.send_message(
            "🔖 <b>Saved News</b>\n\nYou have not saved any stories yet. Tap <b>🔖 Save</b> under a private news card.",
            user_id,
            private_home_keyboard(),
        )
    batch = rows[offset:offset + PRIVATE_BATCH_SIZE]
    bot.send_message(f"🔖 <b>Saved News</b> · {len(rows)} stories", user_id)
    for row in batch:
        image_ui.send_private_story(user_id, row)
    next_offset = offset + len(batch)
    buttons = []
    if next_offset < len(rows):
        buttons.append([{"text": f"➕ Show more ({len(rows) - next_offset} left)", "callback_data": f"savedmore|{next_offset}"}])
    buttons.append([{"text": "🏠 Private Home", "callback_data": "home"}])
    return bot.send_message(
        f"✅ <b>Showing {offset + 1}–{next_offset} of {len(rows)}</b>",
        user_id,
        {"inline_keyboard": buttons},
    )


def collect_my_news(user_id):
    kinds = subscriptions(user_id)
    if not kinds:
        return []
    lang = language_pref(user_id)
    language = None if lang == "both" else lang
    seen = {}
    for kind in kinds:
        rows, _ = bot.query_stories(kind, 0, language, page_size=25)
        for row in rows:
            seen[int(row["id"])] = row
    return sorted(
        seen.values(),
        key=lambda row: (str(row["last_seen"]), int(row["importance"])),
        reverse=True,
    )


def send_my_news_batch(user_id, offset=0):
    rows = collect_my_news(user_id)
    if not subscriptions(user_id):
        return bot.send_message(
            "⭐ <b>My News</b>\n\nChoose the topics you care about first.",
            user_id,
            topics_subscription_markup(user_id),
        )
    if not rows:
        return bot.send_message(
            "⭐ <b>My News</b>\n\nNo matching stories are stored for your selected topics yet.",
            user_id,
            private_home_keyboard(),
        )
    batch = rows[offset:offset + PRIVATE_BATCH_SIZE]
    bot.send_message(f"⭐ <b>My News</b> · personalized from {len(subscriptions(user_id))} followed topics", user_id)
    for row in batch:
        image_ui.send_private_story(user_id, row)
    next_offset = offset + len(batch)
    buttons = []
    if next_offset < len(rows):
        buttons.append([{"text": f"➕ Show more ({len(rows) - next_offset} left)", "callback_data": f"mymore|{next_offset}"}])
    buttons.append([{"text": "⚙️ Edit followed topics", "callback_data": "prefs|topics"}])
    buttons.append([{"text": "🏠 Private Home", "callback_data": "home"}])
    return bot.send_message(
        f"✅ <b>Showing {offset + 1}–{next_offset} of {len(rows)}</b>",
        user_id,
        {"inline_keyboard": buttons},
    )


def send_related(user_id, story_id):
    try:
        story_id = int(story_id)
    except (TypeError, ValueError):
        return None
    with bot.DB_LOCK, bot.db_connect() as db:
        rows = db.execute(
            "SELECT publisher,title,url FROM articles WHERE story_id=? ORDER BY importance DESC,id DESC LIMIT 8",
            (story_id,),
        ).fetchall()
    if not rows:
        return bot.send_message("📰 No additional coverage is stored for this story yet.", user_id)
    lines = [f"📰 <b>Related coverage</b> · {len(rows)} stored report(s)\n"]
    for index, row in enumerate(rows, start=1):
        publisher = html.escape(bot.shorten_text(row["publisher"], 70))
        title = html.escape(bot.shorten_text(row["title"], 160))
        url = html.escape(row["url"], quote=True)
        lines.append(f'{index}. <a href="{url}">{title}</a>\n   {publisher}')
    return bot.send_message("\n\n".join(lines)[:3900], user_id, private_home_keyboard(), False)


def send_maldives_preferred(message):
    user_id = _uid(message)
    pref = language_pref(user_id) if user_id else "both"
    if pref == "en":
        return image_ui.send_batch(message, "maldives", "en", 0, "🇬🇧 Maldives News — English")
    if pref == "dv":
        return image_ui.send_batch(message, "maldives", "dv", 0, "🇲🇻 ދިވެހި ނޫސް")
    return _base_send_maldives(message)


bot.send_maldives_bilingual = send_maldives_preferred
ui.send_maldives_from_callback = send_maldives_preferred


def _is_private(message):
    chat_id = (message.get("chat") or {}).get("id")
    sender_id = (message.get("from") or {}).get("id")
    return chat_id is not None and sender_id is not None and str(chat_id) == str(sender_id)


def handle_message(message):
    text = str(message.get("text") or "").strip()
    user_id = _uid(message)
    if not _is_private(message) or not user_id:
        return _base_handle_message(message)

    # Keep /start, deep links, standard categories and existing group-onboarding cleanup intact.
    if text == "⭐ My News":
        return send_my_news_batch(user_id, 0)
    if text == "🔖 Saved":
        return send_saved_batch(user_id, 0)
    if text == "⚙️ Settings":
        return send_settings(user_id)
    if text == "🔎 Search":
        _set_setting("awaiting_search", user_id, "1")
        return bot.send_message(
            "🔎 <b>Search News</b>\n\nType what you want to find in your next message.\nExample: <code>Maldives tourism</code>",
            user_id,
            {"inline_keyboard": [[{"text": "Cancel", "callback_data": "searchcancel"}]]},
        )

    if _setting("awaiting_search", user_id, "") == "1" and text and not text.startswith("/"):
        _set_setting("awaiting_search", user_id, "")
        return image_ui.send_search_images(message, text)

    return _base_handle_message(message)


def handle_callback(callback):
    data = str(callback.get("data") or "")
    user_id = _uid(callback)
    callback_id = callback.get("id")
    if not user_id:
        return _base_handle_callback(callback)

    ours = (
        data == "home" or data == "searchcancel" or data.startswith("prefs|") or
        data.startswith("lang|") or data.startswith("sub|") or data.startswith("notify|") or
        data.startswith("save|") or data.startswith("related|") or data.startswith("savedmore|") or
        data.startswith("mynews|") or data.startswith("mymore|")
    )
    if not ours:
        return _base_handle_callback(callback)

    if callback_id:
        bot.telegram_api("answerCallbackQuery", {"callback_query_id": callback_id})

    if data == "home":
        return bot.send_message(private_welcome_text(), user_id, private_home_keyboard())
    if data == "searchcancel":
        _set_setting("awaiting_search", user_id, "")
        return bot.send_message("Search cancelled.", user_id, private_home_keyboard())

    if data == "prefs|language":
        return bot.send_message("🌐 <b>Maldives news language</b>\n\nChoose what you want the Maldives button and My News to prioritize.", user_id, language_markup(user_id))
    if data == "prefs|topics":
        return bot.send_message("⭐ <b>Choose My News topics</b>\n\nTap topics to follow or unfollow them.", user_id, topics_subscription_markup(user_id))
    if data == "prefs|notify":
        return bot.send_message("🔔 <b>Automatic private updates</b>\n\nChoose one delivery mode.", user_id, notification_markup(user_id))
    if data == "prefs|back":
        return send_settings(user_id)

    if data.startswith("lang|"):
        value = data.split("|", 1)[1]
        if value in {"en", "dv", "both"}:
            _set_setting("language", user_id, value)
        return bot.send_message("✅ Language preference updated.", user_id, settings_markup(user_id))

    if data.startswith("sub|"):
        kind = data.split("|", 1)[1]
        if kind in TOPIC_LABELS:
            current = subscriptions(user_id)
            if kind in current:
                current.remove(kind)
            else:
                current.append(kind)
            _set_json_setting("topics", user_id, current)
        return bot.send_message("⭐ My News topics updated.", user_id, topics_subscription_markup(user_id))

    if data.startswith("notify|"):
        value = data.split("|", 1)[1]
        if value in NOTIFY_LABELS:
            _set_setting("notify", user_id, value)
        return bot.send_message(f"✅ Notifications set to <b>{html.escape(NOTIFY_LABELS[notification_pref(user_id)])}</b>.", user_id, settings_markup(user_id))

    if data.startswith("save|"):
        try:
            story_id = int(data.split("|", 1)[1])
        except ValueError:
            return None
        current = saved_story_ids(user_id)
        if story_id in current:
            current.remove(story_id)
            notice = "Removed from Saved."
        else:
            current.insert(0, story_id)
            notice = "Saved for later ✅"
        _set_json_setting("saved", user_id, current[:200])
        return bot.send_message(f"🔖 {notice}", user_id, private_home_keyboard())

    if data.startswith("related|"):
        return send_related(user_id, data.split("|", 1)[1])
    if data.startswith("savedmore|"):
        try:
            offset = max(0, int(data.split("|", 1)[1]))
        except ValueError:
            offset = 0
        return send_saved_batch(user_id, offset)
    if data.startswith("mynews|"):
        return send_my_news_batch(user_id, 0)
    if data.startswith("mymore|"):
        try:
            offset = max(0, int(data.split("|", 1)[1]))
        except ValueError:
            offset = 0
        return send_my_news_batch(user_id, offset)
    return None


bot.handle_message = handle_message
bot.handle_callback = handle_callback


def _notification_users():
    with bot.DB_LOCK, bot.db_connect() as db:
        rows = db.execute("SELECT key,value FROM settings WHERE key LIKE 'user_notify_%'").fetchall()
    users = []
    for row in rows:
        user_id = str(row["key"])[len("user_notify_"):]
        mode = str(row["value"] or "off")
        if user_id and mode in NOTIFY_LABELS:
            users.append((user_id, mode))
    return users


def _digest_rows_for_user(user_id, hours=12):
    followed = subscriptions(user_id)
    cutoff = (bot.utc_now() - timedelta(hours=hours)).isoformat()
    if not followed:
        with bot.DB_LOCK, bot.db_connect() as db:
            return db.execute(
                "SELECT * FROM stories WHERE last_seen>=? ORDER BY breaking DESC,importance DESC,last_seen DESC LIMIT 8",
                (cutoff,),
            ).fetchall()
    rows = [row for row in collect_my_news(user_id) if str(row["last_seen"]) >= cutoff]
    return rows[:8]


def _private_digest_text(user_id, title):
    rows = _digest_rows_for_user(user_id, 12)
    if not rows:
        return f"📰 <b>{html.escape(title)}</b>\n\nNo new matching stories were archived in this period."
    lines = [f"📰 <b>{html.escape(title)}</b>\n"]
    for index, row in enumerate(rows, start=1):
        region = "🇲🇻" if row["maldives"] else "🌍"
        emoji = bot.CATEGORY_EMOJIS.get(row["category"], "📰")
        url = html.escape(row["primary_url"], quote=True)
        headline = html.escape(bot.shorten_text(row["representative_title"], 180))
        lines.append(f'{index}. {region} {emoji} <a href="{url}">{headline}</a>')
    return "\n\n".join(lines)[:3900]


async def private_notification_scheduler():
    while True:
        try:
            now = bot.maldives_now()
            today = now.date().isoformat()
            users = await asyncio.to_thread(_notification_users)
            for user_id, mode in users:
                if mode == "morning" and now.hour == bot.MORNING_DIGEST_HOUR and now.minute < 5:
                    key = f"user_digest_sent_{user_id}_morning_{today}"
                    if not bot.get_setting(key):
                        text = await asyncio.to_thread(_private_digest_text, user_id, "Your Morning News Brief")
                        await asyncio.to_thread(bot.send_message, text, user_id, private_home_keyboard(), False)
                        bot.set_setting(key, "1")
                elif mode == "evening" and now.hour == bot.EVENING_DIGEST_HOUR and now.minute < 5:
                    key = f"user_digest_sent_{user_id}_evening_{today}"
                    if not bot.get_setting(key):
                        text = await asyncio.to_thread(_private_digest_text, user_id, "Your Evening News Brief")
                        await asyncio.to_thread(bot.send_message, text, user_id, private_home_keyboard(), False)
                        bot.set_setting(key, "1")
                elif mode == "breaking":
                    cutoff = (bot.utc_now() - timedelta(minutes=10)).isoformat()
                    with bot.DB_LOCK, bot.db_connect() as db:
                        breaking_rows = db.execute(
                            "SELECT * FROM stories WHERE breaking=1 AND last_seen>=? ORDER BY importance DESC,last_seen DESC LIMIT 2",
                            (cutoff,),
                        ).fetchall()
                    for row in breaking_rows:
                        sent_key = f"user_breaking_sent_{user_id}_{row['id']}"
                        if bot.get_setting(sent_key):
                            continue
                        await asyncio.to_thread(image_ui.send_private_story, user_id, row)
                        bot.set_setting(sent_key, "1")
        except Exception as error:
            logging.exception("Private notification scheduler failed: %s", error)
        await asyncio.sleep(60)


async def combined_digest_scheduler():
    await asyncio.gather(_base_digest_scheduler(), private_notification_scheduler())


bot.digest_scheduler = combined_digest_scheduler


async def main():
    await app.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped", bot.BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
