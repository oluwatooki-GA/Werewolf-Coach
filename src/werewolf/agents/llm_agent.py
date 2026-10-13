"""A player that is a language model: builds a prompt from its view, calls the client, answers."""

import json
from collections.abc import Callable

from werewolf.agents.prompt import build_messages
from werewolf.agents.wire import WireError, json_schema_for, to_action_json
from werewolf.engine.actions import Belief, FatalAgentError, Reply, Task, Usage
from werewolf.engine.views import PlayerView
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import LedgerBlocked, LedgerError
from werewolf.llm.types import RateLimited, Request


class LLMAgent:
    """One player in one game. It keeps its own belief table between calls."""

    def __init__(
        self,
        name: str,
        client: LLMClient,
        model: str,
        *,
        card: str = "",
        cache_salt: str = "",
        game_id: str = "",
        temperature: float = 0.7,
        max_tokens: int = 300,
        summarize: bool = False,
        on_prompt: Callable[[str, list[dict[str, str]]], None] | None = None,
    ) -> None:
        self._name = name
        self._client = client
        self._model = model
        self._card = card
        self._salt = cache_salt
        self._game_id = game_id
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._on_prompt = on_prompt
        self._summarize = summarize
        self._beliefs: dict[str, Belief] = {}
        self._summary = ""

    async def act(self, view: PlayerView, task: Task) -> object:
        messages = build_messages(
            view,
            task,
            card=self._card,
            beliefs=self._beliefs,
            summary=self._summary,
            from_round=view.round if self._summarize else 1,  # older rounds live in the summary
        )
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
        text = done.text
        if not done.truncated:
            try:
                text = to_action_json(task.kind, done.text)
            except WireError:
                pass  # hand the engine the raw text; it rejects it and asks again with the reason
            else:
                self._remember(task.kind, text)
        return Reply(text=text, usage=usage)

    def _remember(self, kind: str, action_json: str) -> None:
        data = json.loads(action_json)
        if kind == "memory":
            summary = str(data.get("summary", "")).strip()
            if summary:  # an empty summary keeps the old one
                self._summary = summary
        for player, belief in data.get("beliefs", {}).items():
            self._beliefs[player] = Belief(**belief)
