import unittest

import private_group_ui as ui


class PrivateGroupUITests(unittest.TestCase):
    def setUp(self):
        self.original_username = ui.bot.BOT_USERNAME
        self.original_send_message = ui.bot.send_message
        self.original_send_kind_page = ui.bot.send_kind_page
        self.original_telegram_api = ui.bot.telegram_api
        self.original_rate_memory = dict(ui.bot.RATE_MEMORY)
        ui.bot.RATE_MEMORY.clear()

    def tearDown(self):
        ui.bot.BOT_USERNAME = self.original_username
        ui.bot.send_message = self.original_send_message
        ui.bot.send_kind_page = self.original_send_kind_page
        ui.bot.telegram_api = self.original_telegram_api
        ui.bot.RATE_MEMORY.clear()
        ui.bot.RATE_MEMORY.update(self.original_rate_memory)

    def test_group_menu_uses_inline_callbacks_not_reply_keyboard(self):
        ui.bot.BOT_USERNAME = "example_news_bot"
        markup = ui.group_inline_keyboard()
        self.assertIn("inline_keyboard", markup)
        self.assertNotIn("keyboard", markup)
        callback_values = [
            button.get("callback_data")
            for row in markup["inline_keyboard"]
            for button in row
            if button.get("callback_data")
        ]
        self.assertIn("private|maldives", callback_values)
        self.assertIn("private|global", callback_values)
        self.assertIn("private|important", callback_values)
        self.assertIn("private|topics", callback_values)

    def test_private_send_never_falls_back_to_group(self):
        calls = []

        def fake_send_message(text, chat_id=None, reply_markup=None, disable_preview=True):
            calls.append(str(chat_id))
            return None

        ui.bot.send_message = fake_send_message
        message = {
            "chat": {"id": -100999},
            "from": {"id": 12345},
        }
        result = ui.silent_send_private(message, "private result")
        self.assertIsNone(result)
        self.assertEqual(calls, ["12345"])
        self.assertNotIn("-100999", calls)

    def test_group_callback_routes_to_requesting_user_flow(self):
        routed = []
        answers = []

        def fake_send_kind_page(message, kind, page=0, language=None):
            routed.append((message["from"]["id"], message["chat"]["id"], kind))
            return {"message_id": 77}

        def fake_telegram_api(method, payload=None, timeout=40):
            answers.append((method, payload or {}))
            return True

        ui.bot.send_kind_page = fake_send_kind_page
        ui.bot.telegram_api = fake_telegram_api
        callback = {
            "id": "cb-1",
            "data": "private|global",
            "from": {"id": 12345},
            "message": {"chat": {"id": -100999}, "message_id": 88},
        }
        result = ui.handle_callback(callback)
        self.assertTrue(result)
        self.assertEqual(routed, [(12345, -100999, "global")])
        self.assertEqual(answers[-1][0], "answerCallbackQuery")
        self.assertIn("Sent privately", answers[-1][1]["text"])


if __name__ == "__main__":
    unittest.main()
