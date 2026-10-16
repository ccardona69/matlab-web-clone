"""
Parser de descenso recursivo para MATLAB.

Precedencia (de menor a mayor), según la documentación de operadores de MATLAB:
  ||  →  &&  →  |  →  &  →  < <= > >= == ~=  →  :  →  + -  →  * / \\ .* ./ .\\
  →  unarios + - ~  →  ^ .^ (y transpuestas ' .')  →  postfijos (), {}, .campo
"""

from __future__ import annotations

from backend.matlab import nodes as N
from backend.matlab.errors import MatlabSyntaxError
from backend.matlab.lexer import Token, tokenize

INVALID_EXPR = (
    "Invalid expression. Check for missing multiplication operator, missing or unbalanced "
    "delimiters, or other syntax error. To construct matrices, use brackets instead of parentheses."
)


class Parser:
    def __init__(self, tokens: list[Token], source: str) -> None:
        self.toks = tokens
        self.p = 0
        self.src = source
        self.index_depth = 0
        self.functions: dict[str, N.FunctionDef] = {}

    # ---------- utilidades ----------

    @property
    def tok(self) -> Token:
        return self.toks[self.p]

    def peek(self, k: int = 1) -> Token:
        return self.toks[min(self.p + k, len(self.toks) - 1)]

    def advance(self) -> Token:
        t = self.toks[self.p]
        self.p += 1
        return t

    def error(self, msg: str = INVALID_EXPR, tok: Token | None = None) -> MatlabSyntaxError:
        t = tok or self.tok
        return MatlabSyntaxError(msg, t.line, t.col)

    def expect_op(self, op: str) -> Token:
        if not self.tok.is_op(op):
            if op == ")":
                raise self.error("Invalid expression. When calling a function or indexing a variable, use parentheses. Otherwise, check for mismatched delimiters.")
            raise self.error()
        return self.advance()

    def skip_newlines(self) -> None:
        while self.tok.kind == "NL" or self.tok.is_op(";", ","):
            self.advance()

    # ---------- programa ----------

    def parse_program(self) -> N.Program:
        stmts = self.parse_block(stop=set(), top=True)
        if self.tok.kind != "EOF":
            raise self.error("Illegal use of reserved keyword \"%s\"." % self.tok.value)
        return N.Program(stmts, self.functions)

    def parse_block(self, stop: set[str], top: bool = False, allow_eof: bool = False) -> list[N.Node]:
        body: list[N.Node] = []
        while True:
            self.skip_newlines()
            t = self.tok
            if t.kind == "EOF":
                if stop and not top and not allow_eof:
                    raise self.error("At least one END is missing. The statement beginning here does not have a matching end.")
                return body
            if t.kind == "KW" and t.value in stop:
                return body
            if t.kind == "KW" and t.value == "function":
                if not top and "function" in stop:
                    return body
                fn = self.parse_function()
                self.functions[fn.name] = fn
                continue
            if t.kind == "KW" and t.value in ("end", "elseif", "else", "case", "otherwise", "catch"):
                if top and t.value == "end" and self.functions:
                    self.advance()
                    continue
                raise self.error(f"Illegal use of reserved keyword \"{t.value}\".")
            body.append(self.parse_statement())

    def end_of_statement(self) -> bool:
        """Consume el terminador; devuelve True si el resultado debe mostrarse."""
        t = self.tok
        if t.is_op(";"):
            self.advance()
            if self.tok.kind == "NL":
                self.advance()
            return False
        if t.is_op(","):
            self.advance()
            return True
        if t.kind == "NL":
            self.advance()
            return True
        if t.kind == "EOF":
            return True
        if t.kind == "KW" and t.value in ("end", "else", "elseif", "case", "otherwise", "catch"):
            return True
        raise self.error()

    def parse_statement(self) -> N.Node:
        t = self.tok
        line = t.line
        node: N.Node
        if t.kind == "CMD":
            self.advance()
            name, args = t.value
            node = N.Command(name, list(args), self.end_of_statement())
        elif t.kind == "KW":
            node = self.parse_keyword_statement()
        elif t.is_op("[") and self._is_multi_assign():
            node = self.parse_multi_assign()
        else:
            expr = self.parse_expr()
            if self.tok.is_op("="):
                self.advance()
                self._check_lvalue(expr)
                value = self.parse_expr()
                node = N.Assign([expr], value, self.end_of_statement())
            else:
                node = N.ExprStmt(expr, self.end_of_statement())
        node.line = line
        return node

    def _check_lvalue(self, expr: N.Node) -> None:
        cur = expr
        while isinstance(cur, (N.Index, N.Field)):
            cur = cur.base
        if not isinstance(cur, N.Id):
            raise self.error("Incorrect use of '=' operator. To assign a value to a variable, use '='. To compare values for equality, use '=='.")

    def _is_multi_assign(self) -> bool:
        depth = 0
        k = self.p
        while k < len(self.toks):
            t = self.toks[k]
            if t.is_op("[", "(", "{"):
                depth += 1
            elif t.is_op("]", ")", "}"):
                depth -= 1
                if depth == 0:
                    return self.toks[k + 1].is_op("=") if k + 1 < len(self.toks) else False
            elif t.kind in ("NL", "EOF"):
                return False
            k += 1
        return False

    def parse_multi_assign(self) -> N.Node:
        self.expect_op("[")
        targets: list[N.Node | None] = []
        while not self.tok.is_op("]"):
            if self.tok.is_op(","):
                self.advance()
                continue
            if self.tok.is_op("~") and (self.peek().is_op(",", "]")):
                self.advance()
                targets.append(None)
                continue
            e = self.parse_postfix()
            self._check_lvalue(e)
            targets.append(e)
        self.expect_op("]")
        self.expect_op("=")
        value = self.parse_expr()
        return N.Assign(targets, value, self.end_of_statement(), multi=True)

    def parse_keyword_statement(self) -> N.Node:
        kw = self.advance()
        v = kw.value
        if v == "if":
            branches = []
            cond = self.parse_expr()
            body = self.parse_block({"elseif", "else", "end"})
            branches.append((cond, body))
            else_body = None
            while True:
                t = self.advance()
                if t.value == "elseif":
                    cond = self.parse_expr()
                    branches.append((cond, self.parse_block({"elseif", "else", "end"})))
                elif t.value == "else":
                    else_body = self.parse_block({"end"})
                    self.advance()
                    break
                else:
                    break
            self._optional_terminator()
            return N.If(branches, else_body)
        if v in ("for", "parfor"):
            paren = False
            if self.tok.is_op("("):
                paren = True
                self.advance()
            name_tok = self.advance()
            if name_tok.kind != "ID":
                raise self.error(tok=name_tok)
            self.expect_op("=")
            iterable = self.parse_expr()
            if paren:
                if self.tok.is_op(","):
                    self.advance()
                    self.parse_expr()
                self.expect_op(")")
            body = self.parse_block({"end"})
            self.advance()
            self._optional_terminator()
            return N.For(name_tok.value, iterable, body)
        if v == "while":
            cond = self.parse_expr()
            body = self.parse_block({"end"})
            self.advance()
            self._optional_terminator()
            return N.While(cond, body)
        if v == "switch":
            subject = self.parse_expr()
            self.skip_newlines()
            cases = []
            otherwise = None
            while True:
                t = self.advance()
                if t.value == "case":
                    val = self.parse_expr()
                    cases.append((val, self.parse_block({"case", "otherwise", "end"})))
                elif t.value == "otherwise":
                    otherwise = self.parse_block({"case", "otherwise", "end"})
                elif t.value == "end":
                    break
                else:
                    raise self.error(tok=t)
            self._optional_terminator()
            return N.Switch(subject, cases, otherwise)
        if v == "try":
            body = self.parse_block({"catch", "end"})
            ident = None
            catch_body: list[N.Node] = []
            t = self.advance()
            if t.value == "catch":
                if self.tok.kind == "ID" and self.tok.line == t.line:
                    ident = self.advance().value
                catch_body = self.parse_block({"end"})
                self.advance()
            self._optional_terminator()
            return N.Try(body, ident, catch_body)
        if v == "break":
            self._optional_terminator()
            return N.Break()
        if v == "continue":
            self._optional_terminator()
            return N.Continue()
        if v == "return":
            self._optional_terminator()
            return N.Return()
        if v in ("global", "persistent"):
            names = []
            while self.tok.kind == "ID":
                names.append(self.advance().value)
            self._optional_terminator()
            return N.Global(names)
        raise self.error(f"Illegal use of reserved keyword \"{v}\".", kw)

    def _optional_terminator(self) -> None:
        if self.tok.is_op(";", ",") or self.tok.kind == "NL":
            self.advance()

    def parse_function(self) -> N.FunctionDef:
        self.advance()  # function
        outputs: list[str] = []
        # Formas: function f, function y = f(x), function [a, b] = f(x)
        if self.tok.is_op("["):
            self.advance()
            while not self.tok.is_op("]"):
                if self.tok.is_op(","):
                    self.advance()
                    continue
                t = self.advance()
                if t.kind != "ID":
                    raise self.error(tok=t)
                outputs.append(t.value)
            self.advance()
            self.expect_op("=")
            name = self.advance().value
        else:
            first = self.advance()
            if first.kind == "CMD":
                raise self.error("Function definition is misplaced or improperly formatted.", first)
            if self.tok.is_op("="):
                self.advance()
                outputs = [first.value]
                name = self.advance().value
            else:
                name = first.value
        while self.tok.is_op("."):
            self.advance()
            name = f"{name}.{self.advance().value}"
        params: list[str] = []
        if self.tok.is_op("("):
            self.advance()
            while not self.tok.is_op(")"):
                if self.tok.is_op(","):
                    self.advance()
                    continue
                t = self.advance()
                if t.is_op("~"):
                    params.append("~")
                elif t.kind == "ID":
                    params.append(t.value)
                else:
                    raise self.error(tok=t)
            self.advance()
        body = self.parse_block({"end", "function"}, allow_eof=True)
        if self.tok.is_kw("end"):
            self.advance()
        fn = N.FunctionDef(name, params, outputs, body)
        return fn

    # ---------- expresiones ----------

    def parse_expr(self) -> N.Node:
        return self.parse_oror()

    def _binary(self, sub, ops: tuple[str, ...]) -> N.Node:
        left = sub()
        while self.tok.kind == "OP" and self.tok.value in ops:
            op = self.advance().value
            right = sub()
            left = N.Bin(op, left, right)
        return left

    def parse_oror(self) -> N.Node:
        return self._binary(self.parse_andand, ("||",))

    def parse_andand(self) -> N.Node:
        return self._binary(self.parse_or, ("&&",))

    def parse_or(self) -> N.Node:
        return self._binary(self.parse_and, ("|",))

    def parse_and(self) -> N.Node:
        return self._binary(self.parse_cmp, ("&",))

    def parse_cmp(self) -> N.Node:
        return self._binary(self.parse_range, ("==", "~=", "<", "<=", ">", ">="))

    def parse_range(self) -> N.Node:
        if self.index_depth and self.tok.is_op(":") and (self.peek().is_op(",", ")", "}")):
            self.advance()
            return N.Colon()
        start = self.parse_add()
        if not self.tok.is_op(":"):
            return start
        self.advance()
        second = self.parse_add()
        if self.tok.is_op(":"):
            self.advance()
            third = self.parse_add()
            return N.Range(start, second, third)
        return N.Range(start, None, second)

    def parse_add(self) -> N.Node:
        return self._binary(self.parse_mul, ("+", "-"))

    def parse_mul(self) -> N.Node:
        return self._binary(self.parse_unary, ("*", "/", "\\", ".*", "./", ".\\"))

    def parse_unary(self) -> N.Node:
        if self.tok.is_op("-", "+", "~"):
            op = self.advance().value
            operand = self.parse_unary()
            if op == "-" and isinstance(operand, N.Num):
                return N.Num(-operand.value)
            if op == "+":
                return N.Un("+", operand)
            return N.Un(op, operand)
        return self.parse_power()

    def parse_power(self) -> N.Node:
        base = self.parse_postfix()
        while self.tok.is_op("^", ".^"):
            op = self.advance().value
            # El exponente admite operadores unarios: 2^-1
            if self.tok.is_op("-", "+", "~"):
                uop = self.advance().value
                exp = self.parse_postfix()
                exp = N.Un(uop, exp) if uop != "+" else exp
            else:
                exp = self.parse_postfix()
            base = N.Bin(op, base, exp)
        return base

    def parse_postfix(self) -> N.Node:
        node = self.parse_primary()
        while True:
            t = self.tok
            if t.is_op("(") and not (t.space_before and self._in_matrix_context()):
                self.advance()
                node = N.Index(node, self.parse_args(")"), False)
            elif t.is_op("{") and not (t.space_before and self._in_matrix_context()):
                self.advance()
                node = N.Index(node, self.parse_args("}"), True)
            elif t.is_op(".") and self.peek().kind in ("ID", "KW"):
                self.advance()
                node = N.Field(node, self.advance().value)
            elif t.is_op(".") and self.peek().is_op("("):
                self.advance()
                self.advance()
                dyn = self.parse_expr()
                self.expect_op(")")
                node = N.Field(node, None, dyn)
            elif t.is_op("'", ".'"):
                self.advance()
                node = N.Postfix(t.value, node)
            else:
                return node

    def _in_matrix_context(self) -> bool:
        return getattr(self, "_matrix_depth", 0) > 0 and self.index_depth == 0

    def parse_args(self, closer: str) -> list[N.Node]:
        args: list[N.Node] = []
        saved_matrix = getattr(self, "_matrix_depth", 0)
        self._matrix_depth = 0
        self.index_depth += 1
        try:
            if self.tok.is_op(closer):
                self.advance()
                return args
            while True:
                args.append(self.parse_expr())
                if self.tok.is_op(","):
                    self.advance()
                    continue
                self.expect_op(closer)
                return args
        finally:
            self.index_depth -= 1
            self._matrix_depth = saved_matrix

    def parse_primary(self) -> N.Node:
        t = self.tok
        if t.kind == "NUM":
            self.advance()
            return N.Num(t.value)
        if t.kind == "STR":
            self.advance()
            return N.Str(t.value, False)
        if t.kind == "DSTR":
            self.advance()
            return N.Str(t.value, True)
        if t.kind == "ID":
            self.advance()
            node = N.Id(t.value)
            node.line = t.line
            return node
        if t.kind == "KW" and t.value == "end" and self.index_depth > 0:
            self.advance()
            return N.End()
        if t.is_op("("):
            self.advance()
            saved_matrix = getattr(self, "_matrix_depth", 0)
            saved_index = self.index_depth
            self._matrix_depth = 0
            self.index_depth = 0 if saved_index == 0 else saved_index
            e = self.parse_expr()
            self._matrix_depth = saved_matrix
            self.index_depth = saved_index
            self.expect_op(")")
            return N.Un("()", e)
        if t.is_op("["):
            return self.parse_matrix("[", "]", cell=False)
        if t.is_op("{"):
            return self.parse_matrix("{", "}", cell=True)
        if t.is_op("@"):
            self.advance()
            if self.tok.is_op("("):
                start_pos = self.tok.pos
                self.advance()
                params = []
                while not self.tok.is_op(")"):
                    if self.tok.is_op(","):
                        self.advance()
                        continue
                    pt = self.advance()
                    if pt.kind == "ID":
                        params.append(pt.value)
                    elif pt.is_op("~"):
                        params.append("~")
                    else:
                        raise self.error(tok=pt)
                self.advance()
                saved_index = self.index_depth
                saved_matrix = getattr(self, "_matrix_depth", 0)
                self.index_depth = 0
                self._matrix_depth = 0
                body = self.parse_expr()
                self.index_depth = saved_index
                self._matrix_depth = saved_matrix
                end_pos = self.tok.pos
                text = "@" + self.src[start_pos:end_pos].strip()
                return N.AnonFn(params, body, _compact_anon_text(text))
            name_tok = self.advance()
            if name_tok.kind != "ID":
                raise self.error(tok=name_tok)
            name = name_tok.value
            while self.tok.is_op(".") and self.peek().kind == "ID":
                self.advance()
                name += "." + self.advance().value
            return N.FuncHandle(name)
        if t.is_op(":") and self.index_depth:
            self.advance()
            return N.Colon()
        if t.kind == "EOF" or t.kind == "NL":
            raise self.error("Invalid expression. Check for missing or extra characters.")
        if t.kind == "KW":
            raise self.error(f"Illegal use of reserved keyword \"{t.value}\".")
        raise self.error()

    def parse_matrix(self, opener: str, closer: str, cell: bool) -> N.Node:
        self.advance()
        rows: list[list[N.Node]] = [[]]
        saved_index = self.index_depth
        self.index_depth = 0 if saved_index == 0 else saved_index
        self._matrix_depth = getattr(self, "_matrix_depth", 0) + 1
        saved_index_flag = self.index_depth
        try:
            # dentro de [] la palabra 'end' solo es válida si estamos en un índice externo
            while not self.tok.is_op(closer):
                t = self.tok
                if t.is_op(","):
                    self.advance()
                    continue
                if t.is_op(";") or t.kind == "NL":
                    self.advance()
                    if rows[-1]:
                        rows.append([])
                    continue
                if t.kind == "EOF":
                    raise self.error("Invalid expression. Check for missing or mismatched delimiters.")
                self.index_depth = saved_index_flag
                rows[-1].append(self.parse_expr())
            self.advance()
        finally:
            self._matrix_depth -= 1
            self.index_depth = saved_index
        if not rows[-1]:
            rows.pop()
        return N.Matrix(rows, cell)


def _compact_anon_text(text: str) -> str:
    # MATLAB muestra las funciones anónimas sin espacios superfluos: @(x)x.^2+1
    out = []
    in_str = False
    prev = ""
    for ch in text:
        if ch == "'" and not prev.isalnum() and prev not in ")]}'":
            in_str = not in_str
        if ch == " " and not in_str:
            prev = ch
            continue
        out.append(ch)
        prev = ch
    return "".join(out)


def parse(source: str, command_candidates=None) -> N.Program:
    tokens = tokenize(source, command_candidates)
    return Parser(tokens, source).parse_program()
