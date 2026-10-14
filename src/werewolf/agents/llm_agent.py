"""A player that is a language model: builds a prompt from its view, calls the client, answers."""

from collections.abc import Callable

from werewolf.agents.prompter import Prompter
from werewolf.agents.wire import WireError, json_schema_for, to_action_json
from werewolf.engine.actions import FatalAgentError, Reply, Task, Usage
from werewolf.engine.views import PlayerView
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import LedgerBlocked, LedgerError
from werewolf.llm.types import RateLimited, Request


def _action_json(kind: str, text: str) -> str | None:
    """The engine's action JSON for the model's answer, or None if it cannot be read."""
    try:
        return to_action_json(kind, text)
    except WireError:
        return None


class LLMAgent:
    """One player in one game. It keeps its own belief table between calls."""

    def __init__(
        self,
        name: str,
        client: LLMClient,
        model: str,
        *,
        card: str = "",
        persona: str = "",
        cache_salt: str = "",
        game_id: str = "",
        temperature: float = 0.7,
        max_tokens: int = 300,
        summarize: bool = False,
        keep_notes: int = 0,
        on_prompt: Callable[[str, list[dict[str, str]]], None] | None = None,
    ) -> None:
        self._name = name
        self._client = client
        self._model = model
        self._salt = cache_salt
        self._game_id = game_id
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._on_prompt = on_prompt
        self._prompter = Prompter(
            card=card, persona=persona, summarize=summarize, keep_notes=keep_notes
        )

    async def act(self, view: PlayerView, task: Task) -> object:
        messages = self._prompter.messages(view, task)
        if self._on_prompt is not None:
            self._on_prompt(self._name, messages)
        request = Request(
            model=self._model,
            messages=messages,
            schema=json_schema_for(task.kind),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            cache_salt=self._salt,
            prompt_cache_key=f"{self._game_id}:{self._name}" if self._game_id else None,
        )
        try:
            done = await self._client.complete(request)
        except (LedgerBlocked, LedgerError, RateLimited) as exc:
            raise FatalAgentError(str(exc)) from exc  # a hard stop, not a bad answer

        usage = Usage(
            model=done.model,
            prompt_tokens=done.prompt_tokens,
            completion_tokens=done.completion_tokens,
            cached_tokens=done.cached_tokens,
            cost=done.cost,
            latency_s=done.latency_s,
            cache_hit=done.cache_hit,
            truncated=done.truncated,
        )
        text = done.text  # an unreadable answer goes to the engine as it came; it asks again
        action = None if done.truncated else _action_json(task.kind, done.text)
        if action is not None:
            text = action
            self._prompter.learn(task.kind, action)
        return Reply(text=text, usage=usage)
