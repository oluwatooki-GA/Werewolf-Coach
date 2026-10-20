"""A player that is a language model: builds a prompt from its view, calls the client, answers."""

import json
from collections.abc import Callable

from werewolf.agents.leakguard import REWRITE, guard_request, reveals
from werewolf.agents.prompter import Prompter
from werewolf.agents.wire import WireError, json_schema_for, to_action_json
from werewolf.engine.actions import FatalAgentError, Reply, Task, Usage
from werewolf.engine.views import PlayerView, WolfChat
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import LedgerBlocked, LedgerError
from werewolf.llm.types import Completion, RateLimited, Request

GUARD_TOKENS = 100  # the guard answers with one true or false


def _action_json(kind: str, text: str) -> str | None:
    """The engine's action JSON for the model's answer, or None if it cannot be read."""
    try:
        return to_action_json(kind, text)
    except WireError:
        return None


def _usage_of(done: Completion) -> Usage:
    return Usage(
        model=done.model,
        prompt_tokens=done.prompt_tokens,
        completion_tokens=done.completion_tokens,
        cached_tokens=done.cached_tokens,
        cost=done.cost,
        latency_s=done.latency_s,
        cache_hit=done.cache_hit,
        truncated=done.truncated,
    )


def _plus(a: Usage, b: Usage) -> Usage:
    """Two calls made for one answer count as one: the log shows what the answer really cost."""
    return a.model_copy(
        update={
            "prompt_tokens": a.prompt_tokens + b.prompt_tokens,
            "completion_tokens": a.completion_tokens + b.completion_tokens,
            "cached_tokens": a.cached_tokens + b.cached_tokens,
            "cost": a.cost + b.cost,
            "latency_s": a.latency_s + b.latency_s,
            "cache_hit": a.cache_hit and b.cache_hit,
        }
    )


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

    async def _complete(self, request: Request) -> Completion:
        try:
            return await self._client.complete(request)
        except (LedgerBlocked, LedgerError, RateLimited) as exc:
            raise FatalAgentError(str(exc)) from exc  # a hard stop, not a bad answer

    async def _answer(self, view: PlayerView, task: Task) -> Completion:
        messages = self._prompter.messages(view, task)
        if self._on_prompt is not None:
            self._on_prompt(self._name, messages)
        return await self._complete(
            Request(
                model=self._model,
                messages=messages,
                schema=json_schema_for(task.kind),
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                cache_salt=self._salt,
                prompt_cache_key=f"{self._game_id}:{self._name}" if self._game_id else None,
            )
        )

    async def _gives_away_the_wolf_chat(self, view: PlayerView, action: str) -> Completion | None:
        """The guard's call, if this is a wolf about to say something that could repeat the chat."""
        secrets = [e.text for e in view.events if isinstance(e, WolfChat)]
        message = json.loads(action).get("message") or ""
        if not (view.partner and secrets and message.strip()):
            return None
        request = guard_request(
            self._model, secrets, message, salt=self._salt, max_tokens=GUARD_TOKENS
        )
        try:
            return await self._complete(request)
        except FatalAgentError:
            raise
        except Exception:  # a failed check must not cost the wolf its turn
            return None

    async def act(self, view: PlayerView, task: Task) -> object:
        done = await self._answer(view, task)
        usage = _usage_of(done)
        action = None if done.truncated else _action_json(task.kind, done.text)
        if action is not None and task.kind == "bid":
            verdict = await self._gives_away_the_wolf_chat(view, action)
            if verdict is not None:
                usage = _plus(usage, _usage_of(verdict))
                if reveals(verdict.text):
                    again = await self._answer(view, task.model_copy(update={"error": REWRITE}))
                    usage = _plus(usage, _usage_of(again))
                    done = again
                    action = None if done.truncated else _action_json(task.kind, done.text)
        text = done.text  # an unreadable answer goes to the engine as it came; it asks again
        if action is not None:
            text = action
            self._prompter.learn(task.kind, action)
        return Reply(text=text, usage=usage)
