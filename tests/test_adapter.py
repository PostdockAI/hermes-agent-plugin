from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from gateway.config import Platform, PlatformConfig

from adapter import CursorStore, MyagentAdapter, _response_message_id


class FakeClient:
    def __init__(self, entries=None):
        self.entries = entries or []
        self.bookmarks = []

    async def read_inbox(self, after_sequence):
        return {
            "entries": [entry for entry in self.entries if entry["sequence"] > after_sequence],
            "next_after_sequence": None,
        }

    async def bookmark(self, sequence):
        self.bookmarks.append(sequence)

    async def close(self):
        return None


def entry(sequence, sender, message_id, text):
    return {
        "sequence": sequence,
        "type": "message.received",
        "occurred_at": "2026-09-08T00:00:00.000Z",
        "payload": {
            "from": sender,
            "message_id": message_id,
            "content": {"encoding": "plaintext", "text": text},
            "attachment_ids": [],
        },
    }


class AdapterContractTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, client, directory):
        config = PlatformConfig(
            enabled=True,
            extra={
                "state_path": str(Path(directory) / "cursor.json"),
                "workspace": directory,
            },
        )
        adapter = MyagentAdapter(config, client=client, platform=Platform.WEBHOOK)
        adapter.address = "owner/worker"
        adapter._running = True
        return adapter

    async def test_multiple_senders_share_one_session_lane(self):
        first = "01991f2c-4f64-7000-8000-000000000201"
        second = "01991f2c-4f64-7000-8000-000000000202"
        client = FakeClient([
            entry(1, "alice/agent", first, "first"),
            entry(2, "bob/agent", second, "second"),
        ])
        with tempfile.TemporaryDirectory() as directory:
            adapter = self.make_adapter(client, directory)
            adapter.handle_message = AsyncMock()
            await adapter._drain_once()
            events = [call.args[0] for call in adapter.handle_message.await_args_list]
            self.assertEqual([event.source.chat_id for event in events], ["owner/worker", "owner/worker"])
            self.assertEqual([event.source.user_id for event in events], ["alice/agent", "bob/agent"])
            self.assertEqual(adapter.workspace, Path(directory).resolve())
            self.assertIn('"external_untrusted":true', events[0].text)
            self.assertIn('"from_address":"bob/agent"', events[1].text)
            self.assertIn(f'"reply_message_id":"{_response_message_id(first)}"', events[0].text)
            self.assertIn('"must_call":"mcp__myagent__send_message"', events[0].text)
            self.assertIn('"for_this_message":true', events[1].text)
            self.assertNotIn('"reply":', events[0].text)
            self.assertEqual(client.bookmarks, [1, 2])
            self.assertEqual(CursorStore(Path(directory) / "cursor.json").load(), 2)

    async def test_ordinary_assistant_output_is_suppressed(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            adapter = self.make_adapter(client, directory)
            result = await adapter.send("owner/worker", "This text must not be delivered")
            self.assertTrue(result.success)
            self.assertEqual(result.message_id, "suppressed-mcp-only")
            self.assertEqual(client.bookmarks, [])


if __name__ == "__main__":
    unittest.main()
