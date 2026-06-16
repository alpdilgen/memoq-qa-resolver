import json
from typing import Protocol


class AIClient(Protocol):
    def resolve(self, system_prompt: str, user_content: str, schema: dict) -> dict:
        """Run a structured completion and return the parsed JSON object."""
        ...


class ClaudeAIClient:
    """Standalone Claude Opus 4.8 adapter."""

    def __init__(self, anthropic_client=None, model: str = "claude-opus-4-8"):
        if anthropic_client is None:
            import anthropic
            anthropic_client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
        self._c = anthropic_client
        self.model = model

    def resolve(self, system_prompt: str, user_content: str, schema: dict) -> dict:
        resp = self._c.messages.create(
            model=self.model,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user_content}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)
