"""
Analizador léxico de MATLAB.

Reglas sensibles al contexto que MATLAB aplica y que el clon respeta:
- `'` es transpuesta tras un valor sin espacio intermedio; en otro caso abre un char array.
- Dentro de `[]` y `{}` el espacio separa elementos (`[1 -2]` son dos elementos, `[1 - 2]` uno).
- Los saltos de línea dentro de `[]`/`{}` separan filas.
- Sintaxis de comando (`hold on`, `format long`, `help sin`) al inicio de una sentencia.
- Comentarios `%`, bloques `%{ ... %}` y continuaciones `...`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.matlab.errors import MatlabSyntaxError

KEYWORDS = {
    "if", "elseif", "else", "end", "for", "parfor", "while", "switch", "case", "otherwise",
    "try", "catch", "break", "continue", "return", "function", "global", "persistent",
}

# Ordenados de mayor a menor longitud para que el escaneo sea voraz.
OPERATORS = [
    "...", ".^", ".*", "./", ".\\", ".'", "==", "~=", "<=", ">=", "&&", "||",
    "+", "-", "*", "/", "\\", "^", "'", "<", ">", "&", "|", "~", "!", "=", ":",
    "(", ")", "[", "]", "{", "}", ".", "@", ",", ";",
]

_NUMBER_RE = re.compile(
    r"(?:\d+(?:\.(?![*/^\\'])\d*)?(?:[eEdD][+-]?\d+)?|\.\d+(?:[eEdD][+-]?\d+)?)([ij](?![A-Za-z0-9_]))?"
)
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_CMD_ARG_RE = re.compile(r"""'(?:[^']|'')*'|"(?:[^"]|"")*"|[^\s,;'"]+""")


@dataclass
class Token:
    kind: str  # NUM, STR, DSTR, ID, KW, OP, NL, EOF, CMD
    value: object
    line: int
    col: int
    pos: int
    space_before: bool = False

    def is_op(self, *ops: str) -> bool:
        return self.kind == "OP" and self.value in ops

    def is_kw(self, *kws: str) -> bool:
        return self.kind == "KW" and self.value in kws


def _ends_value(tok: Token | None) -> bool:
    if tok is None:
        return False
    if tok.kind in ("NUM", "STR", "DSTR", "ID"):
        return True
    if tok.kind == "KW" and tok.value == "end":
        return True
    return tok.kind == "OP" and tok.value in (")", "]", "}", "'", ".'")


class Lexer:
    def __init__(self, source: str, command_candidates: callable | None = None) -> None:
        self.src = source.replace("\r\n", "\n").replace("\r", "\n")
        self.n = len(self.src)
        self.i = 0
        self.line = 1
        self.line_start = 0
        self.tokens: list[Token] = []
        self.brackets: list[str] = []
        # Callback que decide si un identificador al inicio de sentencia puede usar sintaxis de comando.
        self.command_candidates = command_candidates or (lambda name: True)

    def error(self, msg: str) -> MatlabSyntaxError:
        return MatlabSyntaxError(msg, self.line, self.i - self.line_start + 1)

    def _push(self, kind: str, value: object, start: int, space: bool) -> Token:
        tok = Token(kind, value, self.line, start - self.line_start + 1, start, space)
        self.tokens.append(tok)
        return tok

    def _prev(self) -> Token | None:
        return self.tokens[-1] if self.tokens else None

    def _at_statement_start(self) -> bool:
        if self.brackets:
            return False
        prev = self._prev()
        return prev is None or prev.kind == "NL" or prev.is_op(";", ",")

    def _in_matrix(self) -> bool:
        return bool(self.brackets) and self.brackets[-1] in "[{"

    def tokenize(self) -> list[Token]:
        src = self.src
        space = False
        while self.i < self.n:
            ch = src[self.i]

            if ch in " \t":
                self.i += 1
                space = True
                continue

            # Comentario de bloque %{ ... %} (debe ocupar su propia línea)
            if ch == "%" and src.startswith("%{", self.i) and src[self.line_start:self.i].strip() == "" \
                    and src[self.i + 2:src.find("\n", self.i) if src.find("\n", self.i) != -1 else self.n].strip() == "":
                depth = 0
                while self.i < self.n:
                    eol = src.find("\n", self.i)
                    eol = self.n if eol == -1 else eol
                    text = src[self.i:eol].strip()
                    if text == "%{":
                        depth += 1
                    elif text == "%}":
                        depth -= 1
                    self.i = eol
                    if depth == 0:
                        break
                    if self.i < self.n:
                        self.i += 1
                        self.line += 1
                        self.line_start = self.i
                continue

            if ch == "%":
                while self.i < self.n and src[self.i] != "\n":
                    self.i += 1
                continue

            if ch == "\n":
                self._newline(space)
                space = False
                continue

            if src.startswith("...", self.i):
                # Continuación: ignora el resto de la línea y el salto.
                eol = src.find("\n", self.i)
                self.i = self.n if eol == -1 else eol + 1
                self.line += 1
                self.line_start = self.i
                space = True
                continue

            prev = self._prev()

            # Separador implícito por espacio dentro de [] o {}
            if self._in_matrix() and space and _ends_value(prev) and self._starts_element(ch):
                self._push("OP", ",", self.i, True)
                prev = self._prev()

            if self._at_statement_start() and (ch.isalpha()):
                if self._try_command_syntax():
                    space = False
                    continue

            if ch.isdigit() or (ch == "." and self.i + 1 < self.n and src[self.i + 1].isdigit()):
                m = _NUMBER_RE.match(src, self.i)
                text = m.group(0)
                start = self.i
                self.i = m.end()
                body = text[:-1] if m.group(1) else text
                value = float(body.replace("d", "e").replace("D", "e"))
                self._push("NUM", complex(0, value) if m.group(1) else value, start, space)
                space = False
                continue

            if ch.isalpha() or ch == "_":
                m = _IDENT_RE.match(src, self.i)
                start = self.i
                self.i = m.end()
                word = m.group(0)
                if word in KEYWORDS and not (prev is not None and prev.is_op(".")):
                    if word == "end" and self.brackets and self.brackets[-1] in "({":
                        self._push("KW", "end", start, space)
                    elif word == "end" and self.brackets and self.brackets[-1] == "[":
                        self._push("KW", "end", start, space)
                    else:
                        self._push("KW", word, start, space)
                else:
                    self._push("ID", word, start, space)
                space = False
                continue

            if ch == '"':
                start = self.i
                self.i += 1
                buf = []
                while True:
                    if self.i >= self.n or src[self.i] == "\n":
                        raise self.error('String is not terminated properly.')
                    c = src[self.i]
                    if c == '"':
                        if self.i + 1 < self.n and src[self.i + 1] == '"':
                            buf.append('"')
                            self.i += 2
                            continue
                        self.i += 1
                        break
                    buf.append(c)
                    self.i += 1
                self._push("DSTR", "".join(buf), start, space)
                space = False
                continue

            if ch == "'":
                is_transpose = _ends_value(prev) and not (space and self._in_matrix()) and not (
                    space and prev is not None and prev.kind == "ID" and self._statement_has_only(prev)
                )
                if is_transpose:
                    self._push("OP", "'", self.i, space)
                    self.i += 1
                    space = False
                    continue
                start = self.i
                self.i += 1
                buf = []
                while True:
                    if self.i >= self.n or src[self.i] == "\n":
                        raise self.error("Character vector is not terminated properly.")
                    c = src[self.i]
                    if c == "'":
                        if self.i + 1 < self.n and src[self.i + 1] == "'":
                            buf.append("'")
                            self.i += 2
                            continue
                        self.i += 1
                        break
                    buf.append(c)
                    self.i += 1
                self._push("STR", "".join(buf), start, space)
                space = False
                continue

            for op in OPERATORS:
                if src.startswith(op, self.i):
                    break
            else:
                raise self.error(f"Invalid text character. Check for unsupported symbol '{ch}'.")

            start = self.i
            self.i += len(op)
            if op == "!":
                op = "~"
            if op in "([{":
                self.brackets.append(op)
            elif op in ")]}":
                if not self.brackets:
                    raise self.error("Invalid expression. When calling a function or indexing a variable, use parentheses. Otherwise, check for mismatched delimiters.")
                opener = self.brackets.pop()
                if {"(": ")", "[": "]", "{": "}"}[opener] != op:
                    raise self.error("Invalid expression. Check for missing or mismatched delimiters.")
            # Fin de fila vacía antes de ']' — elimina separadores colgantes
            if op in ("]", "}") and self.tokens and self.tokens[-1].is_op(",") and self.tokens[-1].space_before:
                self.tokens.pop()
            self._push("OP", op, start, space)
            space = False

        self._push("NL", "\n", self.i, False)
        if self.brackets:
            raise self.error("Invalid expression. Check for missing or mismatched delimiters.")
        self._push("EOF", None, self.i, False)
        return self.tokens

    def _statement_has_only(self, ident_tok: Token) -> bool:
        """`disp 'hola'` usa sintaxis de comando; aquí lo detectamos si el identificador inicia la sentencia."""
        idx = len(self.tokens) - 1
        before = self.tokens[idx - 1] if idx >= 1 else None
        return before is None or before.kind == "NL" or before.is_op(";", ",")

    def _newline(self, space: bool) -> None:
        if self._in_matrix():
            prev = self._prev()
            if prev is not None and not prev.is_op(";", "[", "{", ","):
                self._push("OP", ";", self.i, space)
            elif prev is not None and prev.is_op(","):
                prev.value = ";"
        elif self.brackets:
            pass  # salto de línea dentro de () sin continuación: MATLAB lo trata como error; lo toleramos
        else:
            self._push("NL", "\n", self.i, space)
        self.i += 1
        self.line += 1
        self.line_start = self.i

    def _starts_element(self, ch: str) -> bool:
        src = self.src
        nxt = src[self.i + 1] if self.i + 1 < self.n else ""
        if ch.isalnum() or ch in "_'\"([{@":
            return True
        if ch == "." and nxt.isdigit():
            return True
        if ch in "+-":
            # `[1 -2]` → nuevo elemento; `[1 - 2]` → operador binario
            return nxt not in " \t" and nxt != "=" and not (ch == nxt)
        if ch == "~":
            return nxt != "="
        return False

    def _try_command_syntax(self) -> bool:
        src = self.src
        m = _IDENT_RE.match(src, self.i)
        if not m:
            return False
        name = m.group(0)
        if name in KEYWORDS:
            return False
        j = m.end()
        if j >= self.n or src[j] not in " \t":
            return False
        k = j
        while k < self.n and src[k] in " \t":
            k += 1
        if k >= self.n:
            return False
        c = src[k]
        nxt = src[k + 1] if k + 1 < self.n else ""
        if c in "\n;,%=(":
            return False
        if c in "+-*/\\^<>&|~.:" and (nxt in " \t" or nxt in "=*/^&|" or (c == "." and nxt in "*/^\\'")):
            return False
        if c == "'" or c == '"':
            pass
        elif not (c.isalnum() or c in "_-.'\"/\\*?"):
            return False
        if not self.command_candidates(name):
            return False
        # Extrae argumentos hasta ; , % o fin de línea (respetando comillas)
        end = k
        while end < self.n and src[end] not in "\n;,%":
            if src[end] in "'\"":
                q = src[end]
                end += 1
                while end < self.n and src[end] != "\n":
                    if src[end] == q:
                        if end + 1 < self.n and src[end + 1] == q:
                            end += 2
                            continue
                        break
                    end += 1
            end += 1
        raw = src[k:end].rstrip()
        args = []
        for tok in _CMD_ARG_RE.findall(raw):
            if tok[0] in "'\"" and tok[-1] == tok[0] and len(tok) >= 2:
                tok = tok[1:-1].replace(tok[0] * 2, tok[0])
            args.append(tok)
        start = self.i
        self.i = end
        self._push("CMD", (name, args), start, False)
        return True


def tokenize(source: str, command_candidates: callable | None = None) -> list[Token]:
    return Lexer(source, command_candidates).tokenize()
