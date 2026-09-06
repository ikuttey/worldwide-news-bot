"""Bilingual Maldives-news runner.

Keeps the comprehensive Maldives outlet registry, all-news coverage, private
responses, and one-tap private onboarding. The Maldives button now guarantees
separate English and Dhivehi result sections instead of allowing one language
to dominate a single ranked list. Automatic group publishing also rotates
Maldives English, Maldives Dhivehi, and global stories.
"""

import asyncio

import maldives_sources_runner as sources

app = sources.app
bot = sources.bot

MALDIVES_LANGUAGE_LIMIT = 30
PRIVATE_PAGE_SIZE = 8


# ============================================================
# PRIVATE MALDIVES ENGLISH + DHIVEHI BROWSING
# ============================================================

ENGLISH_LIVE_QUERIES = [
    ('Maldives news when:2d', 'US', 'en'),
    ('Maldives latest news when:2d', 'US', 'en'),
    ('Maldives government economy tourism sports health technology when:3d', 'US', 'en'),
]

DHIVEHI_LIVE_QUERIES = [
    ('ރާއްޖެ ނޫސް when:2d', 'MV', 'dv'),
    ('ދިވެހި ނޫސް when:2d', 'MV', 'dv'),
    ('ރާއްޖޭގެ ފަހުގެ ޚަބަރު when:2d', 'MV', 'dv'),
]


def _story_from_cluster(cluster):
    first = cluster['articles'][0]
    score = max(app.calculate_importance(article) for article in cluster['articles'])
    analysis = app.general_local_analysis(cluster, score)
    trend = bot.calculate_trending_score(cluster, analysis)
    return {
        'created_at': bot.utc_now_iso(),
        'headline': analysis['headline'],
        'summary': analysis['summary'],
        'category': analysis['category'],
        'breaking': analysis['breaking'],
        'importance_score': analysis['importance_score'],
        'trending_score': trend,
        'publishers': sorted(cluster.get('publishers', [])),
        'link': first.get('link', ''),
        'maldives': True,
        'dhivehi': bot.is_dhivehi_story(first),
    }


def _live_language_news(want_dhivehi, limit=MALDIVES_LANGUAGE_LIMIT):
    queries = DHIVEHI_LIVE_QUERIES if want_dhivehi else ENGLISH_LIVE_QUERIES
    articles = []

    for index, (query, region, language) in enumerate(queries, start=1):
        source_name = f"Live Maldives {'DV' if want_dhivehi else 'EN'} {index}"
        feed_url = bot.google_news_feed(query, region=region, language=language)
        feed = bot.download_rss_feed(source_name, feed_url)
        if not feed:
            continue

        for entry in list(getattr(feed, 'entries', []) or [])[:25]:
            article = bot.parse_rss_entry(source_name, entry)
            if not article or not app.all_news_story(article):
                continue
            if not app.is_maldives_story(article):
                continue
            if bool(bot.is_dhivehi_story(article)) != bool(want_dhivehi):
                continue
            articles.append(article)

    if not articles:
        return []

    stories = []
    for cluster in bot.cluster_articles(articles):
        story = _story_from_cluster(cluster)
        if bool(story.get('dhivehi')) == bool(want_dhivehi):
            stories.append(story)

    stories.sort(
        key=lambda story: (
            1 if story.get('breaking') else 0,
            max(app.safe_int(story.get('trending_score')), app.safe_int(story.get('importance_score'))),
            story.get('created_at', ''),
        ),
        reverse=True,
    )
    return stories[:limit]


def _merge_unique(primary, secondary, limit=MALDIVES_LANGUAGE_LIMIT):
    merged = list(primary)
    for candidate in secondary:
        duplicate = False
        for existing in merged:
            if bot.headline_similarity(
                str(candidate.get('headline', '')),
                str(existing.get('headline', '')),
            ) >= 0.72:
                duplicate = True
                break
        if not duplicate:
            merged.append(candidate)
        if len(merged) >= limit:
            break

    merged.sort(
        key=lambda story: (
            story.get('created_at', ''),
            1 if story.get('breaking') else 0,
            max(app.safe_int(story.get('trending_score')), app.safe_int(story.get('importance_score'))),
        ),
        reverse=True,
    )
    return merged[:limit]


def maldives_language_news(want_dhivehi, limit=MALDIVES_LANGUAGE_LIMIT):
    stored = [
        story
        for story in bot.recent_history(24 * 14)
        if story.get('maldives')
        and bool(story.get('dhivehi')) == bool(want_dhivehi)
    ]
    stored.sort(key=lambda story: story.get('created_at', ''), reverse=True)
    stored = stored[:limit]

    # Always perform a small live supplement when the stored side is not full,
    # so a newly deployed bot can immediately show both languages.
    if len(stored) < limit:
        live = _live_language_news(want_dhivehi, limit=limit)
        return _merge_unique(stored, live, limit=limit)

    return stored


def _pages(title, stories):
    if not stories:
        return [app.safe_story_list(title, [])]

    pages = []
    total_pages = (len(stories) + PRIVATE_PAGE_SIZE - 1) // PRIVATE_PAGE_SIZE
    for page_index in range(total_pages):
        start = page_index * PRIVATE_PAGE_SIZE
        page_stories = stories[start : start + PRIVATE_PAGE_SIZE]
        page_title = f"{title} ({page_index + 1}/{total_pages})"
        pages.append(app.safe_story_list(page_title, page_stories, limit=PRIVATE_PAGE_SIZE))
    return pages


def send_maldives_bilingual(message):
    english = maldives_language_news(False)
    dhivehi = maldives_language_news(True)

    messages = [
        (
            "🇲🇻 <b>Maldives News</b>\n\n"
            f"Latest available coverage from the monitored Maldivian outlets: "
            f"<b>{len(english)} English</b> stories and <b>{len(dhivehi)} Dhivehi</b> stories.\n\n"
            "English and Dhivehi are shown separately so one language cannot hide the other."
        )
    ]
    messages.extend(_pages('🇬🇧 Maldives News — English', english))
    messages.extend(_pages('🇲🇻 ދިވެހި ނޫސް', dhivehi))

    # Use the existing private/deep-link sender for the first message. If this
    # is a new group user who has not pressed Start, it shows the one-tap private
    # onboarding button and we stop instead of leaking any news into the group.
    first_result = app.send_private(message, messages[0], app.main_keyboard())
    if not first_result:
        return

    destination, _, _ = app.private_destination(message)
    if destination is None:
        return

    for text in messages[1:]:
        bot.send_message(text, destination, reply_markup=app.main_keyboard())


_base_handler = sources.maldives_sources_handle_command


def bilingual_handle_command(message):
    text = str(message.get('text', '') or '').strip()
    command = text.split(maxsplit=1)[0].split('@')[0].lower() if text.startswith('/') else ''

    if text == '🇲🇻 Maldives' or command == '/maldives':
        try:
            send_maldives_bilingual(message)
        except Exception as error:
            bot.logging.exception('Bilingual Maldives response failed: %s', error)
            app.send_private(
                message,
                '⚠️ <b>Could not load Maldives news right now.</b>\n\nPlease try again shortly.',
                app.main_keyboard(),
            )
        return

    _base_handler(message)


# ============================================================
# AUTOMATIC GROUP FEED: MALDIVES EN + DV + GLOBAL ROTATION
# ============================================================

async def bilingual_all_news_check_and_publish():
    bot.logging.info('Collecting bilingual Maldives + global all-topic news...')
    articles = await asyncio.to_thread(bot.fetch_new_articles)
    if not articles:
        bot.state['last_news_check'] = bot.utc_now_iso()
        bot.save_state()
        return

    clusters = bot.cluster_articles(articles)
    maldives_en = []
    maldives_dv = []
    global_items = []

    for cluster in clusters:
        first = cluster['articles'][0]
        local_score = max(app.calculate_importance(article) for article in cluster['articles'])
        local_score += min((len(cluster.get('publishers', [])) - 1) * 5, 15)
        item = {'cluster': cluster, 'local_score': min(100, local_score)}

        if app.is_maldives_story(first):
            if bot.is_dhivehi_story(first):
                maldives_dv.append(item)
            else:
                maldives_en.append(item)
        else:
            global_items.append(item)

    def rank(item):
        first = item['cluster']['articles'][0]
        return (
            1 if app.is_breaking_story(first) else 0,
            item['local_score'],
            len(item['cluster'].get('publishers', [])),
        )

    for bucket in (maldives_en, maldives_dv, global_items):
        bucket.sort(key=rank, reverse=True)

    # Rotate the three streams. This guarantees Dhivehi gets publishing
    # opportunities instead of being crowded out by higher-volume English feeds.
    ordered = []
    while maldives_en or maldives_dv or global_items:
        if maldives_en:
            ordered.append(maldives_en.pop(0))
        if maldives_dv:
            ordered.append(maldives_dv.pop(0))
        if global_items:
            ordered.append(global_items.pop(0))

    max_posts = min(bot.MAX_POSTS_PER_CHECK, 12)
    posted_count = 0
    ai_used = 0
    category_counts = {}

    for item in ordered:
        cluster = item['cluster']
        first = cluster['articles'][0]
        local_score = item['local_score']

        if not app.all_news_story(first) or local_score < bot.MINIMUM_POST_SCORE:
            continue

        category = app.detect_category(first)
        if app.is_maldives_story(first):
            stream = 'mv-dv' if bot.is_dhivehi_story(first) else 'mv-en'
        else:
            stream = 'global'
        category_key = (stream, category)

        if category_counts.get(category_key, 0) >= 2 and not app.is_breaking_story(first):
            continue

        analysis = None
        if bot.should_use_ai(cluster, local_score, ai_used):
            analysis = await asyncio.to_thread(app.general_ai_analysis, cluster)
            if analysis:
                ai_used += 1
        if not analysis:
            analysis = app.general_local_analysis(cluster, local_score)

        trend_score = bot.calculate_trending_score(cluster, analysis)
        message = app.general_news_message(cluster, analysis, trend_score)
        buttons = bot.build_source_buttons(cluster)

        published = await asyncio.to_thread(
            bot.publish_post,
            message,
            cluster.get('image'),
            buttons,
        )
        if published:
            app.general_save_history(cluster, analysis, trend_score)
            posted_count += 1
            category_counts[category_key] = category_counts.get(category_key, 0) + 1
            await asyncio.sleep(bot.MESSAGE_DELAY_SECONDS)

        if posted_count >= max_posts:
            break

    bot.state['last_news_check'] = bot.utc_now_iso()
    bot.save_state()
    bot.logging.info(
        'Completed bilingual all-news cycle: %s posts, %s AI requests.',
        posted_count,
        ai_used,
    )


bot.handle_command = bilingual_handle_command
bot.check_and_publish_news = bilingual_all_news_check_and_publish


if __name__ == '__main__':
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        bot.logging.info('%s stopped.', bot.BOT_NAME)
    except Exception as error:
        bot.logging.exception('The bot could not start: %s', error)
