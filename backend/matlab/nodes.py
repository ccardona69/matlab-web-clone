"""Nodos del árbol sintáctico de MATLAB."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class Node:
    line: int = 0


# ---------- Expresiones ----------

@dataclass
class Num(Node):
    value: float | complex


@dataclass
class Str(Node):
    value: str
    double_quoted: bool = False


@dataclass
class Id(Node):
    name: str


@dataclass
class End(Node):
    pass


@dataclass
class Colon(Node):
    pass


@dataclass
class Bin(Node):
    op: str
    left: Node
    right: Node


@dataclass
class Un(Node):
    op: str
    operand: Node


@dataclass
class Postfix(Node):
    op: str
    operand: Node


@dataclass
class Range(Node):
    start: Node
    step: Node | None
    stop: Node


@dataclass
class Index(Node):
    base: Node
    args: list[Node]
    brace: bool = False


@dataclass
class Field(Node):
    base: Node
    name: str | None
    dynamic: Node | None = None


@dataclass
class Matrix(Node):
    rows: list[list[Node]]
    cell: bool = False


@dataclass
class AnonFn(Node):
    params: list[str]
    body: Node
    text: str


@dataclass
class FuncHandle(Node):
    name: str


# ---------- Sentencias ----------

@dataclass
class ExprStmt(Node):
    expr: Node
    display: bool


@dataclass
class Assign(Node):
    targets: list[Node | None]  # None representa ~
    value: Node
    display: bool
    multi: bool = False


@dataclass
class Command(Node):
    name: str
    args: list[str]
    display: bool


@dataclass
class If(Node):
    branches: list[tuple[Node, list[Node]]]
    else_body: list[Node] | None


@dataclass
class For(Node):
    var: str
    iterable: Node
    body: list[Node]


@dataclass
class While(Node):
    cond: Node
    body: list[Node]


@dataclass
class Switch(Node):
    subject: Node
    cases: list[tuple[Node, list[Node]]]
    otherwise: list[Node] | None


@dataclass
class Try(Node):
    body: list[Node]
    ident: str | None
    catch_body: list[Node]


@dataclass
class Break(Node):
    pass


@dataclass
class Continue(Node):
    pass


@dataclass
class Return(Node):
    pass


@dataclass
class Global(Node):
    names: list[str]


@dataclass
class FunctionDef(Node):
    name: str
    params: list[str]
    outputs: list[str]
    body: list[Node]
    source_name: str = ""


@dataclass
class Program:
    statements: list[Node]
    functions: dict[str, FunctionDef] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
