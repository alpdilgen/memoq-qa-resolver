import json
from qa_engine.aiclient import ClaudeAIClient


class _FakeAnthropic:
    class messages:
        last = {}
        @staticmethod
        def create(**kw):
            _FakeAnthropic.messages.last = kw
            return type("M", (), {"content": [type("B", (), {"type": "text",
                        "text": json.dumps({"ok": True})})()]})()


def test_claude_client_resolve_builds_request_and_parses():
    c = ClaudeAIClient(anthropic_client=_FakeAnthropic(), model="claude-opus-4-8")
    out = c.resolve("sys", "user", {"type": "object"})
    assert out == {"ok": True}
    kw = _FakeAnthropic.messages.last
    assert kw["model"] == "claude-opus-4-8"
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"]["format"]["schema"] == {"type": "object"}
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
