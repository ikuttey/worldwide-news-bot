# Maldives & World Climate News Bot

This Telegram bot is focused **only on climate and environmental news** from the Maldives and around the world.

## Coverage

- Maldives climate and environmental developments
- Coral reefs, bleaching, restoration and marine ecosystems
- Oceans, coastal erosion, dredging and sea-level rise
- Biodiversity, wildlife and protected species
- Pollution, plastics, sewage and waste management
- Conservation and ecosystem restoration
- Forests and mangroves
- Renewable energy and the energy transition
- Extreme weather and major environmental hazards
- Climate policy, finance and environmental science

General politics, sports, entertainment, technology and business news is filtered out unless the story is directly about climate or the environment.

## How it works

1. Reads Maldivian news RSS feeds.
2. Runs targeted Maldives climate/environment Google News searches in English and Dhivehi.
3. Reads international environment-focused feeds and targeted global searches.
4. Applies a strict local relevance filter before publishing.
5. Groups duplicate reports about the same story.
6. Prioritizes Maldives stories and urgent environmental alerts.
7. Optionally uses Gemini for a small number of high-priority summaries.
8. Publishes morning and evening climate/environment digests in Maldives time.

## Telegram sections

- `/latest`
- `/trending`
- `/maldives`
- `/global`
- `/climate`
- `/oceans`
- `/wildlife`
- `/pollution`
- `/conservation`
- `/energy`
- `/search coral bleaching`

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Set these environment variables before starting the bot:

```text
TELEGRAM_BOT_TOKEN=your_new_bot_token
GROUP_CHAT_ID=your_chat_id
GEMINI_API_KEY=your_new_gemini_key   # optional
```

See `.env.example` for optional tuning values.

Run:

```bash
python main.py
```

## Security note

Do not place Telegram or Gemini credentials directly in `main.py` or commit them to GitHub. If a credential has previously been committed to a public repository, rotate/revoke it and use a newly generated credential through environment variables.
