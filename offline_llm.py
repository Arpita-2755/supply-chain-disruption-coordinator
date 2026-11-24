"""A deterministic, offline stand-in for an LLM chat service.

Why it exists: every agent is a Semantic Kernel ChatCompletionAgent, and a
ChatCompletionAgent needs a chat service. When no API key is configured we plug
in this class instead of OpenAI. Each agent's prompt ends with a rule-based
"DRAFT:" written by deterministic code; this service simply returns that draft.
So offline mode exercises the same Semantic Kernel code path, with zero network
calls and 100% reproducible output.
"""
from __future__ import annotations

from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import AuthorRole, ChatMessageContent

DRAFT_MARKER = "DRAFT:"


class OfflineChatCompletion(ChatCompletionClientBase):
    """Returns the rule-based draft found in the latest user message."""

    async def _inner_get_chat_message_contents(self, chat_history, settings) -> list[ChatMessageContent]:
        last = str(chat_history.messages[-1].content) if chat_history.messages else ""
        text = last.split(DRAFT_MARKER, 1)[1].strip() if DRAFT_MARKER in last else last.strip()
        return [ChatMessageContent(role=AuthorRole.ASSISTANT, content=text, ai_model_id=self.ai_model_id)]
