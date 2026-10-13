from decimal import Decimal
from pathlib import Path

from werewolf.llm.cache import FileCache, cache_key
from werewolf.llm.types import Completion, Request


def request(**kw: object) -> Request:
    base: dict[str, object] = {
        "model": "gpt-4.1-nano",
        "messages": [{"role": "user", "content": "hello"}],
        "schema": {"type": "object"},
        "temperature": 0.7,
        "max_tokens": 300,
    }
    return Request.model_validate({**base, **kw})


def completion(text: str = "hi") -> Completion:
    return Completion(
        model="gpt-4.1-nano",
        text=text,
        prompt_tokens=10,
        completion_tokens=2,
        cached_tokens=0,
        cost=Decimal("0.0000018"),
        latency_s=0.5,
    )


def test_the_key_changes_with_everything_that_changes_the_answer() -> None:
    base = cache_key(request())
    changed = [
        request(model="gpt-4.1-mini"),
        request(messages=[{"role": "user", "content": "hello!"}]),
        request(schema={"type": "array"}),
        request(temperature=0.2),
        request(max_tokens=200),
        request(cache_salt="run-2"),
    ]
    assert all(cache_key(r) != base for r in changed)
    assert len({cache_key(r) for r in changed}) == len(changed)


def test_the_key_ignores_the_routing_hint() -> None:
    assert cache_key(request(prompt_cache_key="game-1:Ada")) == cache_key(request())


def test_the_key_is_stable_text() -> None:
    key = cache_key(request())
    assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)


def test_a_stored_completion_comes_back_equal(tmp_path: Path) -> None:
    cache = FileCache(tmp_path)
    cache.put("k", completion("stored"))
    assert cache.get("k") == completion("stored")


def test_a_missing_key_is_a_miss(tmp_path: Path) -> None:
    assert FileCache(tmp_path).get("nope") is None


def test_a_corrupt_file_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    cache = FileCache(tmp_path)
    (tmp_path / "bad.json").write_text("{not json")
    assert cache.get("bad") is None
    cache.put("bad", completion())  # and it can be overwritten
    assert cache.get("bad") == completion()


def test_a_file_that_is_json_but_the_wrong_shape_is_a_miss(tmp_path: Path) -> None:
    (tmp_path / "odd.json").write_text('{"text": 5}')
    assert FileCache(tmp_path).get("odd") is None


def test_the_directory_is_created_on_first_write(tmp_path: Path) -> None:
    cache = FileCache(tmp_path / "a" / "b")
    cache.put("k", completion())
    assert cache.get("k") is not None
