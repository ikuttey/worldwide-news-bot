"""Bilingual new-member onboarding layered on top of the private image-card UI.

New Telegram group members receive a fresh solid reply keyboard plus concise English
and Dhivehi instructions explaining how to browse news privately. The existing group
privacy behavior, publisher-image cards, Show more controls and first-time Start flow
remain unchanged.
"""

import asyncio
import logging

import private_image_ui as app

bot = app.bot
ui = app.ui

ONBOARDING_VERSION = "all-news-v11-bilingual-new-member-help"


def activate_keyboard_for_new_members(message):
    """Show a bilingual how-to message and fresh solid keyboard when members join."""
    members = list(message.get("new_chat_members") or [])
    if not members or not ui.is_main_group_message(message):
        return None

    ui._clear_keyboard_keeper()

    human_members = [member for member in members if not member.get("is_bot")]
    names = [str(member.get("first_name") or "").strip() for member in human_members]
    names = [name for name in names if name]
    greeting = f"Welcome, {', '.join(names[:3])}!" if names else "Welcome!"

    text = (
        f"👋 <b>{greeting}</b>\n\n"
        "🇬🇧 <b>How to use this news group</b>\n"
        "1. Tap <b>Maldives</b>, <b>Global</b>, <b>Important</b> or <b>News Topics</b> below.\n"
        "2. If this is your first time, tap the red <b>START PRIVATE NEWS</b> button when it appears, then press <b>Start</b> in the bot chat.\n"
        "3. Your requested news is sent to your <b>private chat</b>, not posted publicly in the group.\n"
        "4. Use <b>➕ Show more</b> in private chat to load more stories.\n\n"
        "🇲🇻 <b>މި ގްރޫޕް ބޭނުންކުރާނެ ގޮތް</b>\n"
        "1. ތިރީގައި ހުންނަ <b>Maldives</b>، <b>Global</b>، <b>Important</b> ނުވަތަ <b>News Topics</b> ބަޓަން ފިތާލާ.\n"
        "2. ފުރަތަމަ ފަހަރަށް ބޮޓް ބޭނުންކުރާނަމަ، ރަތް <b>START PRIVATE NEWS</b> ބަޓަން ފިތާ، ބޮޓުގެ ޗެޓުގައި <b>Start</b> ފިތާލާ.\n"
        "3. ތިބާ ހޯދާ ނޫސްތައް ގްރޫޕަށް ނުފޮނުވާ، ތިބާގެ <b>ޕްރައިވެޓް ޗެޓަށް</b> ފޮނުވޭނެ.\n"
        "4. އިތުރު ނޫސް ބަލާނަމަ <b>➕ Show more</b> ފިތާލާ."
    )

    activation = ui._base_send_message(
        text,
        bot.GROUP_CHAT_ID,
        bot.main_keyboard(),
        True,
    )

    if isinstance(activation, dict) and activation.get("message_id"):
        ui._keyboard_keeper_message_id = activation["message_id"]
        bot.set_setting("solid_keyboard_keeper_message_id", ui._keyboard_keeper_message_id)
        bot.set_setting("solid_keyboard_version", ONBOARDING_VERSION)
        logging.info(
            "Sent bilingual onboarding and solid keyboard for %s new group member(s)",
            len(members),
        )
    return activation


# private_group_ui.handle_message resolves this module function dynamically, so replacing
# it here upgrades join onboarding without changing the lower-level message routing.
ui.activate_keyboard_for_new_members = activate_keyboard_for_new_members


async def main():
    await app.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("%s stopped", bot.BOT_NAME)
    except Exception as error:
        logging.exception("The bot could not start: %s", error)
