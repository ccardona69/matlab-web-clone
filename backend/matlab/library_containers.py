"""Builtins mínimos de containers.Map y dictionary (construcción y errores base)."""

from __future__ import annotations

from typing import Any

from backend.matlab.registry import builtin, text
from backend.matlab.values import MDictionary, MMap


@builtin("containers.Map")
def bi_containers_map(I: Any, args: list[Any], nargout: int) -> Any:
    key_type = "char"
    value_type = "any"
    rest = list(args)
    while rest and text(rest[0]).lower() in ("keytype", "valuetype"):
        kind = text(rest.pop(0)).lower()
        if not rest:
            break
        value = text(rest.pop(0))
        if kind == "keytype":
            key_type = value
        else:
            value_type = value
    return MMap(key_type, value_type)


@builtin("dictionary")
def bi_dictionary(I: Any, args: list[Any], nargout: int) -> Any:
    return MDictionary()
