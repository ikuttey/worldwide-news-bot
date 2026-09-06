"""Comprehensive Maldives outlet discovery for the all-news Telegram bot.

This wrapper keeps the all-news/private-response/deep-link behavior intact and
adds a broad registry of Maldivian publishers. Rather than making one request
per outlet every few minutes, verified publisher domains are grouped into a
small number of Google News site-search feeds. This gives much wider Maldives
coverage without making Railway unnecessarily slow.
"""

import asyncio

import private_deeplink_runner as onboarding

app = onboarding.app
bot = onboarding.bot


# 61 active publisher domains listed by the Maldives news aggregator Adafi in
# September 2026. Keep these as data so the list can be audited and expanded.
VERIFIED_ACTIVE_MALDIVES_DOMAINS = [
    "adhadhu.com",
    "adhives.mv",
    "aslu.com.mv",
    "asuruonline.com",
    "cnm.mv",
    "dhelionline.mv",
    "dhidaily.mv",
    "dhuvas.mv",
    "dhuvelionline.mv",
    "eki.mv",
    "fainuonline.com",
    "faragu.mv",
    "farudhun.com",
    "fiyaonline.com",
    "fiyes.mv",
    "furathama.mv",
    "gaafu.mv",
    "gohkolhu.com",
    "halha.mv",
    "halinews.com",
    "hathaavees.com",
    "havaasa.com",
    "heerasnews.com",
    "hiraas.com.mv",
    "hirinews.com",
    "hoara.mv",
    "hurihaa.mv",
    "huvadhoomedia.com",
    "iruvanews.com",
    "iruvaru.com",
    "jeeluonline.com",
    "kaafu.mv",
    "keyolha.com",
    "khabaruonline.com",
    "maletimes.mv",
    "masverin.mv",
    "miadhu.mv",
    "mikalnews.com",
    "milauthuru.com",
    "mulhiraajje.com",
    "muniavas.com",
    "muraasilu.mv",
    "naares.com",
    "oivaru.com",
    "oneonline.mv",
    "raajje24.com",
    "ras.mv",
    "sababu.mv",
    "sandhaanu.today",
    "sarukaaru.gov.mv",
    "sauvees.com",
    "sun.mv",
    "suruhee.mv",
    "themirror.mv",
    "thepress.mv",
    "thiladhun.com",
    "viraasee.com",
    "viyafaari.com.mv",
    "viyas.mv",
    "voice.mv",
    "xeetimes.com",
]

# Major Maldives newsrooms/media sites that are widely used or monitored but
# are not all present in the 61-domain Adafi snapshot above.
MAJOR_MALDIVES_DOMAINS = [
    "mihaaru.com",
    "dhauru.com",
    "avas.mv",
    "raajje.mv",
    "vnews.mv",
    "dhen.mv",
    "mmtv.mv",
    "edition.mv",
    "maldivesindependent.com",
    "mvrepublic.com",
    "psm.mv",
    "vaguthu.mv",
    "sangu.mv",
    "javiyani.mv",
]

ALL_MALDIVES_OUTLET_DOMAINS = sorted(
    set(VERIFIED_ACTIVE_MALDIVES_DOMAINS + MAJOR_MALDIVES_DOMAINS)
)


def _chunks(items, size=8):
    for index in range(0, len(items), size):
        yield items[index : index + size]


# Add grouped site searches. Grouping avoids 75 independent HTTP calls on every
# scheduled check while still explicitly covering every registered domain.
for group_number, domains in enumerate(_chunks(VERIFIED_ACTIVE_MALDIVES_DOMAINS), start=1):
    query = "(" + " OR ".join(f"site:{domain}" for domain in domains) + ") when:3d"
    bot.MALDIVES_GOOGLE_FEEDS[
        f"🇲🇻 Verified Maldives Outlets {group_number:02d}"
    ] = bot.google_news_feed(query, region="MV", language="dv")

# Major national outlets get their own smaller English/Dhivehi discovery group
# because several publish bilingual content and are frequently indexed globally.
for group_number, domains in enumerate(_chunks(MAJOR_MALDIVES_DOMAINS, 7), start=1):
    query = "(" + " OR ".join(f"site:{domain}" for domain in domains) + ") when:3d"
    bot.MALDIVES_GOOGLE_FEEDS[
        f"🇲🇻 Major Maldives Media {group_number:02d}"
    ] = bot.google_news_feed(query, region="US", language="en")

# Extra broad searches catch publisher posts that Google does not return from a
# site-restricted query, especially newly indexed Dhivehi pages.
bot.MALDIVES_GOOGLE_FEEDS.update(
    {
        "🇲🇻 Maldives All News Broad EN": bot.google_news_feed(
            'Maldives (news OR latest OR breaking) when:2d', region="US", language="en"
        ),
        "🇲🇻 Maldives All News Broad DV": bot.google_news_feed(
            'ރާއްޖެ (ނޫސް OR ޚަބަރު OR ފަހުގެ) when:2d', region="MV", language="dv"
        ),
        "🇲🇻 Major Newsrooms by Name": bot.google_news_feed(
            '(Mihaaru OR Dhauru OR Avas OR Raajje OR VNews OR PSM OR Adhadhu OR Sun OR MMTV OR Dhen) Maldives when:2d',
            region="US",
            language="en",
        ),
    }
)


def sources_text():
    lines = [
        "🗞️ <b>Maldives News Sources</b>",
        "",
        f"Monitoring <b>{len(ALL_MALDIVES_OUTLET_DOMAINS)}</b> Maldivian publisher domains, plus broad English and Dhivehi Maldives searches.",
        "",
    ]
    for index, domain in enumerate(ALL_MALDIVES_OUTLET_DOMAINS, start=1):
        lines.append(f"{index}. {domain}")
    return "\n".join(lines)


_base_handler = app.all_news_handle_command


def maldives_sources_handle_command(message):
    text = str(message.get("text", "") or "").strip()
    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else ""

    if command == "/sources" or text == "🗞️ Maldives Sources":
        app.send_private(message, sources_text(), app.main_keyboard())
        return

    _base_handler(message)


# Register a private /sources command without changing the existing public menu.
if not any(item.get("command") == "sources" for item in bot.PUBLIC_COMMANDS):
    bot.PUBLIC_COMMANDS.append(
        {"command": "sources", "description": "Show Maldives news outlets monitored"}
    )

bot.handle_command = maldives_sources_handle_command


if __name__ == "__main__":
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info("%s stopped.", bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception("The bot could not start: %s", error)
