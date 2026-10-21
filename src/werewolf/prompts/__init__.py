"""The words the models are shown, kept in YAML files beside this module so they can be read,
changed and compared without touching code. Python decides which pieces to use and fills in the
`${name}` placeholders; it never changes the wording."""

from functools import cache
from pathlib import Path
from string import Template
from typing import Any

import yaml

DIR = Path(__file__).parent


@cache
def load(file: str, /) -> dict[str, Any]:
    """One prompt file as a dict. It is read once."""
    data = yaml.safe_load((DIR / f"{file}.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def text(file: str, key: str, /, **values: object) -> str:
    """The text under `key`, with each ${placeholder} replaced. A missing value is an error."""
    return Template(load(file)[key]).substitute({k: str(v) for k, v in values.items()})
