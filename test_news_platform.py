import importlib
import os
import tempfile
import unittest

TEST_DB = tempfile.NamedTemporaryFile(prefix="news-bot-test-", suffix=".sqlite3", delete=False)
TEST_DB.close()
os.environ["NEWS_DB_PATH"] = TEST_DB.name

import main


class NewsPlatformTests(unittest.TestCase):
    def setUp(self):
        main.init_db()

    def test_awards_does_not_match_war(self):
        headline = "Maldives awards contract for Phase 1 of Thilafushi Port to a Chinese company"
        self.assertFalse(main.is_breaking(headline))

    def test_actual_war_matches_as_breaking(self):
        self.assertTrue(main.is_breaking("War declared after overnight missile attack"))

    def test_foreign_story_from_maldivian_publisher_is_not_maldives(self):
        location, is_maldives = main.detect_location(
            "Dozens killed in clashes between Houthis and government forces in Yemen",
            "MV",
        )
        self.assertEqual(location, "Global")
        self.assertFalse(is_maldives)

    def test_maldives_story_from_foreign_publisher_is_maldives(self):
        location, is_maldives = main.detect_location(
            "Maldives parliament approves new tourism measure",
            "OTHER",
        )
        self.assertEqual(location, "Maldives")
        self.assertTrue(is_maldives)

    def test_dhivehi_detection(self):
        self.assertTrue(main.is_dhivehi_text("މިއީ ރާއްޖޭގެ ފަހުގެ ޚަބަރެކެވެ."))
        self.assertFalse(main.is_dhivehi_text("This is an English news headline."))

    def test_duplicate_headline_similarity(self):
        first = "Maldives central bank announces new monetary policy measures"
        second = "Maldives central bank announces new monetary policy measure"
        self.assertGreaterEqual(main.headline_similarity(first, second), 0.78)

    def test_fetched_story_is_archived_before_group_publication(self):
        article = {
            "article_uid": main.hash_value("test", "archive", "https://example.com/archive-test"),
            "source_feed": "Test Feed",
            "publisher": "Test Publisher",
            "publisher_domain": "example.com",
            "publisher_country": "OTHER",
            "title": "Test archive story remains available even when not published",
            "description": "A test story used to verify that fetching and archiving are separate from group publication.",
            "url": "https://example.com/archive-test",
            "canonical_url": "https://example.com/archive-test",
            "language": "en",
            "category": "General",
            "maldives": 0,
            "story_location": "Global",
            "importance": 40,
            "breaking": 0,
            "low_value": 0,
            "published_at": "",
            "fetched_at": main.utc_now_iso(),
            "summary": ["A test summary.", "A second test summary."],
        }
        story_id, created = main.archive_article(article)
        self.assertTrue(created)
        rows = main.story_rows_by_ids({story_id})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["published_to_group"], 0)


if __name__ == "__main__":
    unittest.main()
