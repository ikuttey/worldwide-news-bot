import unittest

import private_start_prompt as start_ui
import private_image_ui as image_ui
import professional_private_ui as pro


class PrivateFeatureTests(unittest.TestCase):
    def setUp(self):
        self.original_group_chat_id = start_ui.bot.GROUP_CHAT_ID
        self.original_telegram_api = start_ui.bot.telegram_api
        self.original_send_message = pro.bot.send_message
        self.original_get_setting = pro.bot.get_setting
        self.original_set_setting = pro.bot.set_setting
        self.original_send_related = pro.send_related
        self.original_send_saved_batch = pro.send_saved_batch
        self.original_send_my_news_batch = pro.send_my_news_batch
        self.original_image_send_batch = image_ui.send_batch

        self.settings = {}
        self.sent = []
        self.api_calls = []

        start_ui.bot.GROUP_CHAT_ID = "-100123456"

        def fake_api(method, payload=None, timeout=40):
            self.api_calls.append((method, payload or {}))
            return {"message_id": 1}

        def fake_send_message(text, chat_id=None, reply_markup=None, disable_preview=True):
            self.sent.append((text, str(chat_id), reply_markup))
            return {"message_id": 1}

        def fake_get_setting(key, default=None):
            return self.settings.get(key, default)

        def fake_set_setting(key, value):
            self.settings[key] = str(value)

        start_ui.bot.telegram_api = fake_api
        pro.bot.telegram_api = fake_api
        pro.bot.send_message = fake_send_message
        pro.bot.get_setting = fake_get_setting
        pro.bot.set_setting = fake_set_setting

    def tearDown(self):
        start_ui.bot.GROUP_CHAT_ID = self.original_group_chat_id
        start_ui.bot.telegram_api = self.original_telegram_api
        pro.bot.telegram_api = self.original_telegram_api
        pro.bot.send_message = self.original_send_message
        pro.bot.get_setting = self.original_get_setting
        pro.bot.set_setting = self.original_set_setting
        pro.send_related = self.original_send_related
        pro.send_saved_batch = self.original_send_saved_batch
        pro.send_my_news_batch = self.original_send_my_news_batch
        image_ui.send_batch = self.original_image_send_batch

    def test_ephemeral_onboarding_uses_current_api_shape(self):
        result = start_ui.send_ephemeral_group_message(12345, "hello")
        self.assertTrue(result)
        method, payload = self.api_calls[-1]
        self.assertEqual(method, "sendMessage")
        self.assertNotIn("receiver_user_id", payload)
        self.assertEqual(
            payload["ephemeral_message_parameters"]["receiver_user_id"],
            12345,
        )

    def test_private_home_contains_all_primary_buttons(self):
        markup = pro.private_home_keyboard()
        labels = [button["text"] for row in markup["keyboard"] for button in row]
        expected = {
            "🇲🇻 Maldives",
            "🌍 Global",
            "🚨 Important",
            "🧭 News Topics",
            "⭐ My News",
            "🔖 Saved",
            "🔎 Search",
            "⚙️ Settings",
        }
        self.assertEqual(set(labels), expected)

    def test_article_card_actions_exist(self):
        row = {"id": 77, "primary_url": "https://example.com/story"}
        markup = pro.article_actions(row)
        buttons = [button for line in markup["inline_keyboard"] for button in line]
        self.assertTrue(any(button.get("url") == row["primary_url"] for button in buttons))
        callbacks = {button.get("callback_data") for button in buttons if button.get("callback_data")}
        self.assertEqual(callbacks, {"save|77", "related|77"})

    def test_settings_submenus_have_routable_callbacks(self):
        user_id = "12345"
        callback_sets = []
        for markup in (
            pro.settings_markup(user_id),
            pro.language_markup(user_id),
            pro.topics_subscription_markup(user_id),
            pro.notification_markup(user_id),
        ):
            callback_sets.extend(
                button["callback_data"]
                for row in markup["inline_keyboard"]
                for button in row
                if button.get("callback_data")
            )
        self.assertIn("prefs|language", callback_sets)
        self.assertIn("prefs|topics", callback_sets)
        self.assertIn("prefs|notify", callback_sets)
        self.assertIn("lang|en", callback_sets)
        self.assertIn("lang|dv", callback_sets)
        self.assertIn("lang|both", callback_sets)
        self.assertIn("sub|politics", callback_sets)
        self.assertIn("notify|breaking", callback_sets)
        self.assertIn("notify|morning", callback_sets)
        self.assertIn("notify|evening", callback_sets)
        self.assertIn("notify|off", callback_sets)
        self.assertIn("mynews|0", callback_sets)
        self.assertIn("home", callback_sets)

    def test_primary_inline_callbacks_route_without_exception(self):
        pro.send_related = lambda user_id, story_id: {"related": story_id}
        pro.send_saved_batch = lambda user_id, offset=0: {"saved": offset}
        pro.send_my_news_batch = lambda user_id, offset=0: {"mynews": offset}

        callbacks = [
            "home",
            "searchcancel",
            "prefs|language",
            "prefs|topics",
            "prefs|notify",
            "prefs|back",
            "lang|en",
            "lang|dv",
            "lang|both",
            "sub|politics",
            "notify|breaking",
            "notify|morning",
            "notify|evening",
            "notify|off",
            "save|77",
            "related|77",
            "savedmore|5",
            "mynews|0",
            "mymore|5",
        ]
        for index, data in enumerate(callbacks):
            with self.subTest(data=data):
                callback = {
                    "id": f"cb-{index}",
                    "data": data,
                    "from": {"id": 12345},
                    "message": {"chat": {"id": 12345}, "message_id": 10},
                }
                result = pro.handle_callback(callback)
                self.assertIsNotNone(result)

    def test_show_more_callback_is_acknowledged_and_routes(self):
        routed = []

        def fake_send_batch(message, kind, language=None, offset=0, title=None, announce=True):
            routed.append((kind, language, offset, announce))
            return {"message_id": 2}

        image_ui.send_batch = fake_send_batch
        callback = {
            "id": "cb-more",
            "data": "more|global|all|5",
            "from": {"id": 12345},
            "message": {"chat": {"id": 12345}, "message_id": 10},
        }
        result = image_ui.handle_callback(callback)
        self.assertTrue(result)
        self.assertEqual(routed, [("global", None, 5, False)])
        self.assertTrue(any(method == "answerCallbackQuery" for method, _ in self.api_calls))


if __name__ == "__main__":
    unittest.main()
