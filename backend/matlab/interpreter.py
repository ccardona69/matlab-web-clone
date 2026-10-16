"""Intérprete del árbol sintáctico con espacios de trabajo, funciones de usuario y archivos .m."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from backend.matlab import nodes as N
from backend.matlab import ops
from backend.matlab.display import FormatState, display
from backend.matlab.errors import (
    BreakSignal, ContinueSignal, MatlabError, ReturnSignal, unrecognized,
)
from backend.matlab.parser import parse
from backend.matlab.values import (
    MCell, MFunc, MString, MStruct, as2d, class_of, empty_double, from_python, make_char,
    num, to_double, truthy,
)

MAX_RECURSION = 256
USER_ERROR_BUILTINS = {"error", "assert", "rethrow", "throw", "throwAsCaller", "MException"}


class Frame(dict):
    """Espacio de trabajo de una función o del base workspace."""

    def __init__(self, name: str = "base") -> None:
        super().__init__()
        self.fn_name = name
        self.nargin = 0
        self.nargout = 0
        self.global_names: set[str] = set()


class Interpreter:
    def __init__(self, builtins: dict[str, Callable], folder: Path, graphics: Any) -> None:
        self.builtins = builtins
        self.folder = folder
        self.graphics = graphics
        self.base = Frame("base")
        self.frames: list[Frame] = [self.base]
        self.global_vars: dict[str, Any] = {}
        self.functions: dict[str, N.FunctionDef] = {}
        self.fmt = FormatState()
        self.segments: list[dict[str, str]] = []
        self.events: list[dict[str, Any]] = []
        self.deadline: float | None = None
        self.width = 100
        self.tic_time = time.perf_counter()
        self.rng = np.random.default_rng()
        self._file_cache: dict[str, tuple[float, N.Program]] = {}
        self._end_stack: list[tuple[Any, int, int]] = []
        self.lastwarn = ""

    # ---------- salida ----------

    @property
    def vars(self) -> Frame:
        return self.frames[-1]

    def write(self, text: str, kind: str = "out") -> None:
        if not text:
            return
        if self.segments and self.segments[-1]["kind"] == kind:
            self.segments[-1]["text"] += text
        else:
            self.segments.append({"kind": kind, "text": text})

    def warn(self, message: str) -> None:
        self.lastwarn = message
        self.write(message if message.startswith("Warning:") else f"Warning: {message}", "warn")
        if not message.endswith("\n"):
            self.write("\n", "warn")

    def _flush_warnings(self) -> None:
        while ops.WARN_SINK:
            self.warn(ops.WARN_SINK.pop(0))

    def show(self, name: str, value: Any) -> None:
        self.write(display(name, value, self.fmt, self.width))

    # ---------- ejecución ----------

    def run_source(self, source: str, timeout: float = 30.0) -> None:
        self.deadline = time.perf_counter() + timeout
        program = parse(source, self._command_candidate)
        self.functions.update(program.functions)
        try:
            self.exec_block(program.statements)
        except (BreakSignal, ContinueSignal):
            pass
        except ReturnSignal:
            pass
        finally:
            self._flush_warnings()

    def _command_candidate(self, name: str) -> bool:
        return name not in self.vars

    def check_deadline(self) -> None:
        if self.deadline is not None and time.perf_counter() > self.deadline:
            self.deadline = None
            raise MatlabError(
                "Operation terminated: la ejecución superó el límite de tiempo del servidor del clon.",
                "MATLAB:timeout",
            )

    def exec_block(self, stmts: list[N.Node]) -> None:
        for s in stmts:
            self.exec_stmt(s)

    def exec_stmt(self, s: N.Node) -> None:
        self.check_deadline()
        t = type(s)
        try:
            if t is N.Assign:
                self.exec_assign(s)
            elif t is N.ExprStmt:
                self.exec_expr_stmt(s)
            elif t is N.Command:
                self.exec_command(s)
            elif t is N.If:
                for cond, body in s.branches:
                    if truthy(self.eval(cond)):
                        self.exec_block(body)
                        break
                else:
                    if s.else_body is not None:
                        self.exec_block(s.else_body)
            elif t is N.For:
                self.exec_for(s)
            elif t is N.While:
                while truthy(self.eval(s.cond)):
                    self.check_deadline()
                    try:
                        self.exec_block(s.body)
                    except BreakSignal:
                        break
                    except ContinueSignal:
                        continue
            elif t is N.Switch:
                self.exec_switch(s)
            elif t is N.Try:
                self.exec_try(s)
            elif t is N.Break:
                raise BreakSignal()
            elif t is N.Continue:
                raise ContinueSignal()
            elif t is N.Return:
                raise ReturnSignal()
            elif t is N.Global:
                for name in s.names:
                    self.vars.global_names.add(name)
                    if name not in self.global_vars:
                        self.global_vars[name] = empty_double()
                    self.vars[name] = self.global_vars[name]
            else:
                raise MatlabError(f"Sentencia no soportada: {t.__name__}")
        finally:
            if ops.WARN_SINK:
                self._flush_warnings()

    def eval_text_value(self, source: str) -> Any:
        program = parse(source, self._command_candidate)
        if len(program.statements) != 1 or not isinstance(program.statements[0], N.ExprStmt):
            raise MatlabError("Expression expected.", "MATLAB:parse")
        return self.eval_single(program.statements[0].expr)

    def set_var(self, name: str, value: Any) -> None:
        self.vars[name] = value
        if name in self.vars.global_names:
            self.global_vars[name] = value

    def exec_for(self, s: N.For) -> None:
        it = self.eval(s.iterable)
        if isinstance(it, MCell):
            cols = [MCell(it.data[:, [j]]) for j in range(it.data.shape[1])]
        elif isinstance(it, MStruct):
            cols = [MStruct(it.fields, it.data[:, [j]]) for j in range(it.data.shape[1])]
        elif isinstance(it, MString):
            cols = [MString(it.data[:, [j]]) for j in range(it.data.shape[1])]
        elif isinstance(it, np.ndarray):
            a = as2d(it)
            if a.shape[0] == 1:
                cols = [a[:, j:j + 1] for j in range(a.shape[1])]
            else:
                cols = [a[:, j:j + 1].copy() for j in range(a.shape[1])]
        else:
            cols = [it]
        for col in cols:
            self.check_deadline()
            self.set_var(s.var, col)
            try:
                self.exec_block(s.body)
            except BreakSignal:
                break
            except ContinueSignal:
                continue

    def exec_switch(self, s: N.Switch) -> None:
        subject = self.eval(s.subject)

        def matches(case_val: Any) -> bool:
            if isinstance(case_val, MCell):
                return any(matches(x) for x in case_val.data.flat)
            if isinstance(subject, (MString,)) or (isinstance(subject, np.ndarray) and subject.dtype.kind == "U"):
                try:
                    from backend.matlab.values import char_to_str
                    return char_to_str(subject) == char_to_str(case_val)
                except MatlabError:
                    return False
            if isinstance(case_val, np.ndarray) and case_val.dtype.kind == "U":
                return False
            try:
                a, b = to_double(subject), to_double(case_val)
                return a.size == 1 and b.size == 1 and complex(a.flat[0]) == complex(b.flat[0])
            except MatlabError:
                return False

        for case_expr, body in s.cases:
            if matches(self.eval(case_expr)):
                self.exec_block(body)
                return
        if s.otherwise is not None:
            self.exec_block(s.otherwise)

    def exec_try(self, s: N.Try) -> None:
        try:
            self.exec_block(s.body)
        except MatlabError as e:
            if s.ident:
                self.set_var(s.ident, mexception(e))
            self.exec_block(s.catch_body)

    def exec_expr_stmt(self, s: N.ExprStmt) -> None:
        expr = s.expr
        if isinstance(expr, N.Id) and expr.name in self.vars:
            if s.display:
                self.show(expr.name, self.vars[expr.name])
            return
        results = self.eval_multi(expr, 0)
        if not results:
            return
        value = results[0]
        if isinstance(expr, (N.Index, N.Id)) and self._is_call(expr) is None:
            pass
        self.set_var("ans", value)
        if s.display:
            self.show("ans", value)

    def _is_call(self, expr: N.Node) -> str | None:
        base = expr.base if isinstance(expr, N.Index) else expr
        if isinstance(base, N.Id) and base.name not in self.vars:
            return base.name
        return None

    def exec_command(self, s: N.Command) -> None:
        args = [make_char(a) for a in s.args]
        results = self.call_named(s.name, args, 0)
        if results and s.name not in ("disp", "fprintf"):
            self.set_var("ans", results[0])
            if s.display:
                self.show("ans", results[0])

    # ---------- asignación ----------

    def exec_assign(self, s: N.Assign) -> None:
        if s.multi:
            nout = len(s.targets)
            values = self.eval_multi(s.value, nout)
            if len(values) < sum(1 for t in s.targets if t is not None):
                needed = len(s.targets)
                if len(values) < needed:
                    raise MatlabError("Too many output arguments.", "MATLAB:TooManyOutputs")
            for target, value in zip(s.targets, values):
                if target is None:
                    continue
                name = self.assign_target(target, value)
                if s.display:
                    self.show(name, self.vars[name])
            return
        target = s.targets[0]
        if isinstance(target, N.Index) and target.brace is False and isinstance(s.value, N.Matrix) \
                and not s.value.rows and not s.value.cell:
            name = self.assign_target(target, None, delete=True)
        else:
            if isinstance(target, N.Index) and target.brace:
                values = self.eval_multi(s.value, 1)
                if not values:
                    raise MatlabError("Value not assigned: the right side returned no value.")
                value = values[0]
            else:
                value = self.eval_single(s.value)
            name = self.assign_target(target, value)
        if s.display:
            self.show(name, self.vars[name])

    def assign_target(self, target: N.Node, value: Any, delete: bool = False) -> str:
        chain: list[tuple[str, Any]] = []
        cur = target
        while isinstance(cur, (N.Index, N.Field)):
            if isinstance(cur, N.Index):
                chain.append(("brace" if cur.brace else "paren", cur.args))
            else:
                chain.append(("field", cur.name if cur.name is not None else cur.dynamic))
            cur = cur.base
        chain.reverse()
        name = cur.name
        if isinstance(value, MFunc) and not chain:
            pass
        base = self.vars.get(name)
        if base is None and name in self.vars.global_names:
            base = self.global_vars.get(name)
        if not chain:
            if delete:
                raise MatlabError("Deletion requires an index.")
            self.set_var(name, value)
            return name
        new_val = self._assign_chain(base, chain, value, delete)
        self.set_var(name, new_val)
        return name

    def _eval_index_args(self, base: Any, arg_nodes: list[N.Node]) -> list[Any]:
        out = []
        n = len(arg_nodes)
        for pos, a in enumerate(arg_nodes):
            if isinstance(a, N.Colon):
                out.append(ops.COLON)
                continue
            self._end_stack.append((base, pos, n))
            try:
                vals = self.eval_multi(a, 1, cs_list=True)
            finally:
                self._end_stack.pop()
            out.extend(vals)
        return out

    def _field_name(self, spec: Any) -> str:
        if isinstance(spec, str):
            return spec
        from backend.matlab.values import char_to_str
        return char_to_str(self.eval_single(spec))

    def _assign_chain(self, base: Any, chain: list[tuple[str, Any]], value: Any, delete: bool) -> Any:
        kind, spec = chain[0]
        rest = chain[1:]
        if kind == "field":
            fname = self._field_name(spec)
            if base is None or (isinstance(base, np.ndarray) and base.size == 0):
                base = MStruct.scalar({})
            if not isinstance(base, MStruct):
                raise MatlabError(
                    "Unable to perform assignment because dot indexing is not supported for variables of this type.",
                    "MATLAB:dotIndexingNotSupported",
                )
            if base.data.size != 1:
                raise MatlabError("Scalar structure required for this assignment.", "MATLAB:scalarStructRequired")
            s = base.copy()
            if fname not in s.fields:
                s.fields.append(fname)
                for d in s.data.flat:
                    d[fname] = empty_double()
            elem = s.data.flat[0]
            if rest:
                elem[fname] = self._assign_chain(elem.get(fname), rest, value, delete)
            else:
                if delete:
                    raise MatlabError("Deletion requires an index.")
                elem[fname] = value
            return s
        if kind == "paren":
            if isinstance(base, MFunc):
                raise MatlabError("Unable to perform indexed assignment on a function handle.")
            args = self._eval_index_args(base if base is not None else empty_double(), spec)
            if rest:
                # s(2).campo = v  /  c(2){...}
                if base is None or isinstance(base, MStruct) or (isinstance(base, np.ndarray) and base.size == 0):
                    st = base if isinstance(base, MStruct) else MStruct([], np.empty((0, 0), dtype=object))
                    try:
                        cur_elem = ops.index_get(st, args)
                        elem = cur_elem if cur_elem.data.size == 1 else MStruct.scalar({f: empty_double() for f in st.fields})
                    except MatlabError:
                        elem = MStruct.scalar({f: empty_double() for f in st.fields})
                    new_elem = self._assign_chain(elem, rest, value, delete)
                    st = _ensure_fields(st, new_elem.fields)
                    new_elem = _ensure_fields(new_elem, st.fields)
                    return _struct_set(st, args, new_elem)
                sub = ops.index_get(base, args)
                new_sub = self._assign_chain(sub, rest, value, delete)
                return ops.index_set(base, args, new_sub)
            if delete:
                if base is None:
                    raise unrecognized("?")
                return ops.index_set(base, args, None, delete=True)
            if isinstance(base, MStruct) and isinstance(value, MStruct):
                return _struct_set(base, args, value)
            if isinstance(base, MCell) and not isinstance(value, MCell):
                if isinstance(value, np.ndarray) and value.size == 0:
                    return ops.index_set(base, args, None, delete=True)
                raise MatlabError(
                    "Conversion to cell from %s is not possible." % class_of(value), "MATLAB:invalidConversion"
                )
            return ops.index_set(base, args, value)
        # brace
        if base is None or (isinstance(base, np.ndarray) and base.size == 0):
            base = MCell(np.empty((0, 0), dtype=object))
        if not isinstance(base, MCell):
            raise MatlabError(
                "Unable to perform assignment because brace indexing is not supported for variables of this type.",
                "MATLAB:cellAssToNonCell",
            )
        args = self._eval_index_args(base, spec)
        if rest:
            try:
                cur = ops.index_get(base, args)
                inner = cur.data.flat[0] if cur.data.size == 1 else None
            except MatlabError:
                inner = None
            new_inner = self._assign_chain(inner, rest, value, delete)
        else:
            new_inner = value
        holder = np.empty((1, 1), dtype=object)
        holder[0, 0] = new_inner
        return ops.index_set(base, args, MCell(holder))

    # ---------- evaluación ----------

    def eval_single(self, node: N.Node) -> Any:
        vals = self.eval_multi(node, 1)
        if not vals:
            name = self._is_call(node) or "expression"
            raise MatlabError(
                f"Too many output arguments.", "MATLAB:TooManyOutputs", where=name if name != "expression" else ""
            )
        return vals[0]

    eval = eval_single

    def eval_multi(self, node: N.Node, nargout: int, cs_list: bool = False) -> list[Any]:
        t = type(node)
        if t is N.Num:
            return [num(node.value)]
        if t is N.Str:
            return [MString(node.value) if node.double_quoted else make_char(node.value)]
        if t is N.Id:
            name = node.name
            v = self.vars.get(name)
            if v is not None:
                return [v]
            return self.call_named(name, [], nargout)
        if t is N.Bin:
            if node.op in ("&&", "||"):
                left = self.eval_single(node.left)
                lv = self._logical_scalar(left, node.op)
                if node.op == "&&" and not lv:
                    return [np.array([[False]])]
                if node.op == "||" and lv:
                    return [np.array([[True]])]
                right = self._logical_scalar(self.eval_single(node.right), node.op)
                return [np.array([[bool(right)]])]
            return [ops.binop(node.op, self.eval_single(node.left), self.eval_single(node.right))]
        if t is N.Un:
            return [ops.unop(node.op, self.eval_single(node.operand))]
        if t is N.Postfix:
            return [ops.transpose(self.eval_single(node.operand), node.op == "'")]
        if t is N.Range:
            start = self.eval_single(node.start)
            step = self.eval_single(node.step) if node.step is not None else None
            stop = self.eval_single(node.stop)
            return [ops.colon_range(start, step, stop)]
        if t is N.Matrix:
            rows = []
            for row in node.rows:
                vals = []
                for e in row:
                    vals.extend(self.eval_multi(e, 1, cs_list=True))
                rows.append(vals)
            if node.cell:
                return [_cell_literal(rows)]
            return [ops.concat(rows)]
        if t is N.Index:
            return self.eval_index(node, nargout, cs_list)
        if t is N.Field:
            base_vals = self.eval_multi(node.base, 1)
            if not base_vals:
                raise MatlabError("Dot indexing requires a value.")
            base = base_vals[0]
            fname = self._field_name(node.name if node.name is not None else node.dynamic)
            return self._get_field(base, fname, cs_list)
        if t is N.End:
            if not self._end_stack:
                raise MatlabError("'end' is not valid outside an index expression.")
            base, pos, n = self._end_stack[-1]
            return [num(float(ops.end_value(base, pos, n)))]
        if t is N.Colon:
            return [make_char(":")]
        if t is N.AnonFn:
            closure = {}
            for name in _free_names(node.body, set(node.params)):
                if name in self.vars:
                    closure[name] = self.vars[name]
            return [MFunc(None, node.params, node.body, closure, node.text)]
        if t is N.FuncHandle:
            return [MFunc(node.name, text=f"@{node.name}")]
        raise MatlabError(f"Expresión no soportada: {t.__name__}")

    def _logical_scalar(self, v: Any, op: str) -> bool:
        if isinstance(v, np.ndarray) and v.size == 1:
            return truthy(v)
        if isinstance(v, np.ndarray) and v.size == 0:
            raise MatlabError(
                f"Invalid operand. The operands of the logical {'AND' if op == '&&' else 'OR'} ('{op}') "
                "operator must be convertible to logical scalar values.",
                "MATLAB:nonLogicalConditional",
            )
        raise MatlabError(
            f"Operands to the logical {'AND' if op == '&&' else 'OR'} ({op}) operator must be convertible "
            "to logical scalar values. Use the ANY or ALL functions to reduce operands to logical scalar values.",
            "MATLAB:binaryLogicalOperands",
        )

    def _get_field(self, base: Any, fname: str, cs_list: bool) -> list[Any]:
        if isinstance(base, MStruct):
            if fname not in base.fields:
                raise MatlabError(f"Unrecognized field name \"{fname}\".", "MATLAB:nonExistentField")
            vals = [d[fname] for d in base.data.ravel(order="F")]
            if len(vals) != 1 and not cs_list:
                return vals[:1] if vals else []
            return vals
        if isinstance(base, MCell):
            raise MatlabError(
                "Dot indexing is not supported for variables of this type.", "MATLAB:dotIndexingNotSupported"
            )
        if isinstance(base, MFunc) or isinstance(base, (np.ndarray, MString)):
            raise MatlabError(
                "Dot indexing is not supported for variables of this type.", "MATLAB:dotIndexingNotSupported"
            )
        raise MatlabError("Dot indexing is not supported for variables of this type.")

    def eval_index(self, node: N.Index, nargout: int, cs_list: bool) -> list[Any]:
        base_node = node.base
        if isinstance(base_node, N.Id) and base_node.name not in self.vars:
            if node.brace:
                raise unrecognized(base_node.name)
            args = self._eval_call_args(node.args)
            return self.call_named(base_node.name, args, nargout)
        base_vals = self.eval_multi(base_node, 1)
        if not base_vals:
            raise MatlabError("Indexing requires a value.")
        base = base_vals[0]
        if isinstance(base, MFunc) and not node.brace:
            args = self._eval_call_args(node.args)
            return self.call_function(base, args, nargout)
        args = self._eval_index_args(base, node.args)
        if node.brace:
            if not isinstance(base, MCell):
                raise MatlabError(
                    "Brace indexing is not supported for variables of this type.", "MATLAB:cellRefFromNonCell"
                )
            sub = ops.index_get(base, args)
            vals = list(sub.data.ravel(order="F"))
            if not cs_list and len(vals) > 1 and nargout <= 1:
                return vals[:1]
            return vals
        return [ops.index_get(base, args)]

    def _eval_call_args(self, arg_nodes: list[N.Node]) -> list[Any]:
        out: list[Any] = []
        for a in arg_nodes:
            if isinstance(a, N.Colon):
                out.append(make_char(":"))
                continue
            out.extend(self.eval_multi(a, 1, cs_list=True))
        return out

    # ---------- llamadas ----------

    def resolve(self, name: str) -> Callable | N.FunctionDef | tuple[str, N.Program] | None:
        if name in self.functions:
            return self.functions[name]
        prog = self._load_file(name)
        if prog is not None:
            if name in prog.functions and not prog.statements:
                return prog.functions[name]
            if prog.functions and not prog.statements:
                first = next(iter(prog.functions.values()))
                return first
            return ("script", prog)
        if name in self.builtins:
            return self.builtins[name]
        return None

    def _load_file(self, name: str) -> N.Program | None:
        path = self.folder / f"{name}.m"
        if not path.is_file():
            return None
        mtime = path.stat().st_mtime
        cached = self._file_cache.get(name)
        if cached and cached[0] == mtime:
            return cached[1]
        src = path.read_text(encoding="utf-8", errors="replace")
        prog = parse(src, self._command_candidate)
        # Las subfunciones de un archivo de función son visibles para él
        for fname, fdef in prog.functions.items():
            fdef.source_name = name
        self._file_cache[name] = (mtime, prog)
        return prog

    def call_named(self, name: str, args: list[Any], nargout: int) -> list[Any]:
        target = self.resolve(name)
        if target is None:
            raise unrecognized(name)
        if isinstance(target, tuple):
            if args:
                raise MatlabError(f"Attempt to execute SCRIPT {name} as a function.", "MATLAB:scriptNotAFunction")
            prog = target[1]
            self.functions.update(prog.functions)
            self.exec_block(prog.statements)
            return []
        if isinstance(target, N.FunctionDef):
            return self.call_user(target, args, nargout)
        try:
            res = target(self, args, nargout)
        except MatlabError as e:
            if not e.where and getattr(target, "_matlab_name", None) and name not in USER_ERROR_BUILTINS:
                e.where = target._matlab_name
            raise
        except (ValueError, TypeError, IndexError, np.linalg.LinAlgError, ZeroDivisionError, OverflowError) as e:
            raise MatlabError(_python_error_text(e), "MATLAB:clone:internal", where=name) from e
        if res is None:
            return []
        if not isinstance(res, list):
            res = [res]
        return [from_python(v) for v in res]

    def call_function(self, f: Any, args: list[Any], nargout: int) -> list[Any]:
        if isinstance(f, MFunc):
            if f.body is None:
                return self.call_named(f.name, args, nargout)
            frame = Frame("anonymous")
            frame.update(f.closure)
            for i, p in enumerate(f.params):
                if p == "varargin":
                    frame["varargin"] = MCell(np.array([args[i:]], dtype=object).reshape(1, -1)) if args[i:] else MCell(np.empty((1, 0), dtype=object))
                    break
                if i < len(args) and p != "~":
                    frame[p] = args[i]
            if len(args) > len(f.params) and "varargin" not in f.params:
                raise MatlabError("Too many input arguments.", "MATLAB:TooManyInputs")
            self._push(frame)
            try:
                return self.eval_multi(f.body, max(nargout, 1))
            finally:
                self.frames.pop()
        if isinstance(f, np.ndarray) and f.dtype.kind == "U":
            from backend.matlab.values import char_to_str
            return self.call_named(char_to_str(f), args, nargout)
        if isinstance(f, MString):
            return self.call_named(f.scalar(), args, nargout)
        raise MatlabError("Expected a function handle.", "MATLAB:invalidFunctionHandle")

    def _push(self, frame: Frame) -> None:
        if len(self.frames) > MAX_RECURSION:
            raise MatlabError(
                f"Maximum recursion limit of {MAX_RECURSION} reached.", "MATLAB:recursionLimit"
            )
        self.frames.append(frame)

    def call_user(self, fn: N.FunctionDef, args: list[Any], nargout: int) -> list[Any]:
        params = fn.params
        has_varargin = bool(params) and params[-1] == "varargin"
        fixed = params[:-1] if has_varargin else params
        if len(args) > len(fixed) and not has_varargin:
            raise MatlabError("Too many input arguments.", "MATLAB:TooManyInputs", where=fn.name)
        frame = Frame(fn.name)
        frame.nargin = len(args)
        frame.nargout = nargout
        for i, p in enumerate(fixed):
            if i < len(args) and p != "~":
                frame[p] = args[i]
        if has_varargin:
            rest = args[len(fixed):]
            arr = np.empty((1, len(rest)), dtype=object)
            for i, v in enumerate(rest):
                arr[0, i] = v
            frame["varargin"] = MCell(arr)
        self._push(frame)
        saved_functions = dict(self.functions)
        if fn.source_name:
            prog = self._file_cache.get(fn.source_name)
            if prog:
                self.functions.update(prog[1].functions)
        try:
            try:
                self.exec_block(fn.body)
            except ReturnSignal:
                pass
            outs = fn.outputs
            results: list[Any] = []
            wanted = max(nargout, 1)
            for i, o in enumerate(outs):
                if o == "varargout":
                    vo = frame.get("varargout")
                    if isinstance(vo, MCell):
                        results.extend(list(vo.data.ravel(order="F"))[: max(0, wanted - len(results))])
                    break
                if len(results) >= wanted:
                    break
                if o not in frame:
                    if i < nargout or (i == 0 and nargout == 1):
                        raise MatlabError(
                            f"Output argument \"{o}\" (and possibly others) not assigned a value in the "
                            f"execution with \"{fn.name}\" function.",
                            "MATLAB:unassignedOutputs",
                        )
                    break
                results.append(frame[o])
            if nargout > len(results) and nargout > 0 and outs:
                raise MatlabError("Too many output arguments.", "MATLAB:TooManyOutputs", where=fn.name)
            return results
        finally:
            self.frames.pop()
            self.functions = saved_functions


def _ensure_fields(s: MStruct, fields: list[str]) -> MStruct:
    missing = [f for f in fields if f not in s.fields]
    if not missing:
        return s
    out = s.copy()
    for d in out.data.flat:
        for f in missing:
            d[f] = empty_double()
    out.fields += missing
    return out


def _struct_set(st: MStruct, args: list[Any], elem: MStruct) -> MStruct:
    st = _ensure_fields(st, elem.fields)
    elem = _ensure_fields(elem, st.fields)
    data = st.data
    filler = {f: empty_double() for f in st.fields}
    r, c = data.shape
    holder_arr = np.empty((1, 1), dtype=object)
    holder_arr[0, 0] = elem.data.flat[0]
    # Reutiliza index_set sobre arreglos de objetos con relleno de structs vacíos
    target = MCell(data.copy()) if data.size else MCell(np.empty((0, 0), dtype=object))
    new = ops.index_set(target, args, MCell(holder_arr))
    out = new.data
    for idx in np.ndindex(out.shape):
        v = out[idx]
        if not isinstance(v, dict):
            out[idx] = dict(filler)
    return MStruct(list(st.fields), out)


def _cell_literal(rows: list[list[Any]]) -> MCell:
    built_rows = []
    for row in rows:
        parts = []
        for v in row:
            if isinstance(v, MCell):
                parts.append(v.data)
            else:
                arr = np.empty((1, 1), dtype=object)
                arr[0, 0] = v
                parts.append(arr)
        if parts:
            if len({p.shape[0] for p in parts}) > 1:
                raise MatlabError("Dimensions of arrays being concatenated are not consistent.")
            built_rows.append(np.hstack(parts))
    if not built_rows:
        return MCell(np.empty((0, 0), dtype=object))
    if len({r.shape[1] for r in built_rows}) > 1:
        raise MatlabError("Dimensions of arrays being concatenated are not consistent.")
    return MCell(np.vstack(built_rows))


def _free_names(node: Any, bound: set[str]) -> set[str]:
    names: set[str] = set()

    def walk(n: Any) -> None:
        if isinstance(n, N.Id):
            if n.name not in bound:
                names.add(n.name)
        elif isinstance(n, N.AnonFn):
            for nn in _free_names(n.body, bound | set(n.params)):
                names.add(nn)
        elif isinstance(n, N.Node):
            for v in vars(n).values():
                if isinstance(v, list):
                    for x in v:
                        if isinstance(x, list):
                            for y in x:
                                walk(y)
                        else:
                            walk(x)
                elif isinstance(v, N.Node):
                    walk(v)

    walk(node)
    return names


def mexception(e: MatlabError) -> MStruct:
    return MStruct.scalar({
        "identifier": make_char(e.identifier or ""),
        "message": make_char(e.message),
        "stack": MStruct.scalar({"file": make_char(""), "name": make_char(e.where or ""), "line": num(0.0)}),
    })


def _python_error_text(e: Exception) -> str:
    msg = str(e)
    if "shapes" in msg and "not aligned" in msg:
        return "Incorrect dimensions for matrix multiplication."
    if "broadcast" in msg:
        return "Arrays have incompatible sizes for this operation."
    if "Singular matrix" in msg:
        return "Matrix is singular to working precision."
    if "positional argument" in msg or "takes" in msg and "argument" in msg:
        return "Too many input arguments."
    if "missing" in msg and "argument" in msg:
        return "Not enough input arguments."
    return msg[:300] or e.__class__.__name__
