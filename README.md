# Maldives & World News Bot

A Telegram news bot that collects, archives, deduplicates, ranks and publishes news from the Maldives and around the world.

## Current behavior

- Automatic selected news is posted to the configured Telegram group.
- User button and command results are sent privately.
- New users get a one-tap private-chat deep link and press **Start** once before private replies are allowed by Telegram.
- Maldives browsing is split into **English** and **Dhivehi** sections so one language cannot crowd out the other.
- Private news lists are paginated with **Next / Previous** controls.
- The bot archives every fetched article before deciding what to publish to the group.
- Duplicate reports are merged across fetch cycles instead of only inside one RSS check.

## Coverage

### Maldives

The bot monitors 75 Maldivian publisher domains through grouped English and Dhivehi Google News discovery feeds, plus direct RSS feeds where available. Coverage includes politics, business, technology, health, sports, entertainment, travel and tourism, crime and courts, science, environment, emergencies and general news.

Use `/sources` to see the current Maldives publisher list.

### Global

Global discovery includes broad world news plus politics, business, technology/AI, sports, entertainment, health, science, travel, crime/courts and environment feeds and searches.

## Reliability improvements

The current version uses one active `main.py` instead of a chain of runner wrappers.

- **SQLite archive:** stories, individual articles, Telegram offset and source health are stored in SQLite.
- **Persistent-volume ready:** if Railway mounts a persistent volume at `/data`, the bot automatically stores its database at `/data/news_bot.sqlite3`. Otherwise it falls back to `news_bot.sqlite3` in the working directory.
- **Concurrent fetching:** sources are fetched in parallel with a controlled worker pool.
- **Source health:** response time, article counts and consecutive failures are tracked per source.
- **Correct geography:** a Maldivian publisher does not automatically make an international story a Maldives story. Story location and publisher country are treated separately.
- **Safer breaking detection:** phrase matching uses word boundaries, so words such as `awards` do not accidentally match `war`.
- **Publisher extraction:** Google News publisher metadata is used when available instead of generic feed-group labels.
- **Retry-safe publishing:** stories are archived before group publishing and are marked published only after Telegram confirms the post.
- **Update handling:** a published story can become eligible again only when it becomes breaking or its importance rises substantially.
- **Dhivehi-aware summaries:** Thaana detection and sentence splitting are handled separately from English.

## Telegram commands

- `/maldives` — Maldives news in English + Dhivehi
- `/global` — global news
- `/important` — important and breaking stories
- `/topics` — topic menu
- `/latest`
- `/politics`
- `/business`
- `/technology`
- `/sports`
- `/entertainment`
- `/health`
- `/science`
- `/travel`
- `/environment`
- `/crime`
- `/search <terms>` — search the archive
- `/sources` — monitored Maldives publishers
- `/health` — source-health view; restrict with `ADMIN_USER_IDS`

## Environment variables

Required:

```text
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROUP_CHAT_ID=your_group_chat_id
```

Recommended optional settings:

```text
NEWS_DB_PATH=/data/news_bot.sqlite3
NEWS_CHECK_INTERVAL_SECONDS=300
MAX_POSTS_PER_CHECK=12
MINIMUM_POST_SCORE=58
FETCH_WORKERS=8
PRIVATE_PAGE_SIZE=8
ARCHIVE_RETENTION_DAYS=90
ADMIN_USER_IDS=123456789
```

`GEMINI_API_KEY` and `GEMINI_MODEL` remain supported environment variables for future AI enrichment, but the core news collection, classification and private browsing do not depend on AI.

## Railway persistence

For reliable long-term history across redeployments, attach a Railway persistent volume mounted at:

```text
/data
```

The bot will then automatically use:

```text
/data/news_bot.sqlite3
```

Without a persistent volume, SQLite still works correctly during a running deployment, but the database may be lost when Railway replaces the container filesystem.

## Tests

```bash
pip install -r requirements.txt
python -m py_compile main.py
python -m unittest -v test_news_platform.py
```

The repository also runs these checks in GitHub Actions on every push.

## Security

Do not commit Telegram tokens, Gemini keys or other credentials to GitHub. Keep credentials in Railway environment variables. If a credential was ever committed publicly, rotate it before use.
