"""Cloud-Ollama entry point for the climate intelligence Telegram bot.

This runner keeps Telegram authentication and GROUP_CHAT_ID handling unchanged.
When OLLAMA_BASE_URL is configured, Qwen3/Ollama becomes the primary AI path
for every relevant story, without the Gemini per-check request cap.
"""

import asyncio
import html

import climate_intelligence_runner as intelligence

bot = intelligence.bot

# Runpod's HTTP proxy has a 100-second request ceiling. Keep inference requests
# below that so Railway receives a clean failure and can fall back if needed.
intelligence.OLLAMA_TIMEOUT_SECONDS = min(intelligence.OLLAMA_TIMEOUT_SECONDS, 90)


def cloud_ollama_enabled():
    return bool(intelligence.OLLAMA_BASE_URL)


def cloud_ollama_health():
    if not cloud_ollama_enabled():
        return False, "OLLAMA_BASE_URL is not configured"

    try:
        response = bot.requests.get(
            f"{intelligence.OLLAMA_BASE_URL}/api/tags",
            timeout=15,
        )
        response.raise_for_status()
        models = response.json().get("models", [])
        names = [item.get("name", "") for item in models if item.get("name")]
        configured = intelligence.OLLAMA_MODEL
        if any(name == configured or name.startswith(configured + ":") for name in names):
            return True, f"Connected — {configured} is available"
        if names:
            return False, (
                f"Ollama is reachable, but {configured} is not installed. "
                f"Available: {', '.join(names[:6])}"
            )
        return False, "Ollama is reachable, but no models are installed"
    except Exception as error:
        return False, f"Ollama is unreachable: {error}"


def cloud_should_use_ai(cluster, local_score, ai_used_this_check):
    """Use cloud Ollama on every relevant story; Gemini keeps its old limits."""
    if cloud_ollama_enabled():
        return True
    return intelligence._base_should_use_ai(cluster, local_score, ai_used_this_check)


bot.should_use_ai = cloud_should_use_ai


_base_news_message = bot.build_news_message


def cloud_ai_news_message(cluster, analysis, trend_score):
    message = _base_news_message(cluster, analysis, trend_score)
    engine = analysis.get("ai_engine", "")
    used_ai = bool(analysis.get("used_ai"))

    if engine.startswith("local:"):
        label = f"🤖 <b>AI analysis:</b> Qwen3 via cloud Ollama ({html.escape(intelligence.OLLAMA_MODEL)})"
    elif used_ai:
        label = "🤖 <b>AI analysis:</b> Gemini fallback"
    else:
        label = "⚙️ <b>Analysis:</b> rule-based fallback"

    return bot.shorten_text(f"{message}\n\n{label}", 3980)


bot.build_news_message = cloud_ai_news_message


# Add a lightweight AI health command and button.
if not any(item.get("command") == "aistatus" for item in bot.PUBLIC_COMMANDS):
    bot.PUBLIC_COMMANDS.insert(
        1,
        {"command": "aistatus", "description": "Check cloud Qwen3/Ollama status"},
    )


_base_keyboard = bot.public_command_keyboard


def cloud_keyboard():
    keyboard = _base_keyboard()
    rows = list(keyboard.get("keyboard", []))
    # Insert AI Status before the final Help row, without reintroducing Chat ID.
    insert_at = max(0, len(rows) - 1)
    if not any(button.get("text") == "🤖 AI Status" for row in rows for button in row):
        rows.insert(insert_at, [{"text": "🤖 AI Status"}])
    keyboard["keyboard"] = rows
    return keyboard


bot.public_command_keyboard = cloud_keyboard


_base_handle_command = bot.handle_command


def cloud_handle_command(message):
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")
    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else ""

    if text == "🤖 AI Status" or command == "/aistatus":
        ok, detail = cloud_ollama_health()
        icon = "✅" if ok else "⚠️"
        mode = (
            f"Cloud Ollama / {intelligence.OLLAMA_MODEL}"
            if cloud_ollama_enabled()
            else "Cloud Ollama not configured"
        )
        bot.send_message(
            f"🤖 <b>AI Status</b>\n\n"
            f"<b>Primary:</b> {html.escape(mode)}\n"
            f"<b>Status:</b> {icon} {html.escape(detail)}\n\n"
            "When cloud Ollama is healthy, every relevant climate/environment story is sent to Qwen3 for analysis. "
            "There is no per-request API token billing or artificial two-story AI cap.",
            chat_id,
            reply_markup=cloud_keyboard(),
        )
        return

    _base_handle_command(message)


bot.handle_command = cloud_handle_command


_base_welcome = bot.build_welcome_message


def cloud_welcome_message():
    message = _base_welcome()
    if cloud_ollama_enabled():
        message += (
            f"\n\n🤖 <b>Primary AI:</b> Qwen3 via cloud Ollama "
            f"({html.escape(intelligence.OLLAMA_MODEL)})"
        )
    else:
        message += "\n\n⚠️ <b>Cloud AI:</b> waiting for OLLAMA_BASE_URL"
    return message


bot.build_welcome_message = cloud_welcome_message


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
