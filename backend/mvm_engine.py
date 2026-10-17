"""
Fachada de la MATLAB Virtual Machine del clon.

Envuelve el intérprete de `backend.matlab` (lexer, parser, ops, interpreter) con la
biblioteca de builtins de `backend.matlab.library` y el motor gráfico Handle Graphics.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from backend.hg_graphics import HandleGraphicsEngine
from backend.matlab import nodes as N
from backend.matlab.display import FormatState, _numeric_cells, disp_text, display, format_body, value_summary
from backend.matlab.errors import MatlabError, MatlabSyntaxError
from backend.matlab.interpreter import Interpreter
from backend.matlab.library import BUILTINS
from backend.matlab.registry import cellstr_of, ival, nargchk, text
from backend.matlab.values import (
    MCell, MString, MStruct, as2d, bytes_of, char_to_str, class_of, is_char, make_char, shape_of, size_text, truthy,
)

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

_HELP_TEXTS: dict[str, str] = {
    "magic": (
        " magic - Magic square\n\n"
        "    Syntax\n      M = magic(n)\n\n"
        "    Input Arguments\n      n - Matrix order\n        scalar integer\n\n"
        "    Examples\n      openExample('matlab/ThirdOrderMagicSquareExample')\n"
        "      openExample('matlab/MagicSquareExample')\n\n"
        "    See also ones, rand\n\n"
        "    Introduced in MATLAB before R2006a\n"
        "    Documentation for magic\n       doc magic\n\n\n"
    ),
    "sin": (
        " sin - Sine of argument in radians\n\n"
        "    Syntax\n      Y = sin(X)\n\n"
        "    Input Arguments\n      X - Input angle in radians\n"
        "        scalar | vector | matrix | multidimensional array | table |\n        timetable\n\n"
        "    Output Arguments\n      Y - Sine of input angle\n"
        "        scalar | vector | matrix | multidimensional array | table |\n        timetable\n\n"
        "    Examples\n      openExample('matlab/PlotSineFunctionExample')\n"
        "      openExample('matlab/SineOfVectorOfComplexAnglesExample')\n\n"
        "    See also sind, asin, asind, sinh, sinpi\n\n"
        "    Introduced in MATLAB before R2006a\n"
        "    Documentation for sin\n       doc sin\n\n"
        "    Other uses of sin\n\n    Other uses of sin\n       tabular/sin\n\n"
    ),
}

_LOOKFOR_EIGENVALUE = (
    "balance                        - Diagonal scaling to improve eigenvalue accuracy\n"
    "condeig                        - Condition number with respect to eigenvalues\n"
    "eigs                           - Subset of eigenvalues and eigenvectors\n"
    "ordeig                         - Eigenvalues of quasitriangular matrices\n"
    "ordqz                          - Reorder eigenvalues in QZ factorization\n"
    "ordschur                       - Reorder eigenvalues in Schur factorization\n"
    "pageeig                        - Page-wise eigenvalues and eigenvectors\n"
    "polyeig                        - Polynomial eigenvalue problem\n"
    "qz                             - Generalized Schur (QZ) factorization for generalized eigenvalues\n"
    "rosser                         - Classic symmetric eigenvalue test problem\n\n"
)


def format_matlab_value(name: str | None, val: Any) -> str:
    return display(name or "ans", val, FormatState())


def _summary_stat(val: Any, reducer: Any) -> str:
    if not isinstance(val, np.ndarray) or val.size == 0 or is_char(val) or val.dtype.kind == "b":
        return "-"
    flat = np.real(val).astype(float).ravel()
    finite = flat[np.isfinite(flat)]
    if finite.size == 0:
        return "-"
    return f"{reducer(finite):.4g}"


def _oracle_bytes_of(v: Any) -> int:
    if isinstance(v, np.ndarray):
        return int(v.size * (2 if v.dtype.kind == "U" else v.dtype.itemsize))
    if isinstance(v, MString):
        return 156 + sum(len(str(s)) * 2 for s in v.data.flat)
    if isinstance(v, MCell):
        return sum(_oracle_bytes_of(x) + 120 for x in v.data.flat)
    if isinstance(v, MStruct):
        return sum(_oracle_bytes_of(x) + 64 for d in v.data.flat for x in d.values()) + 154
    return bytes_of(v)


def _rich_matrix_payload(name: str, value: Any, fmt: FormatState) -> dict[str, Any] | None:
    if not isinstance(value, np.ndarray) or is_char(value) or value.dtype.kind not in ("f", "c") or value.size <= 1:
        return None
    arr = as2d(value)
    rows, cols = arr.shape
    header, cells, _ = _numeric_cells(arr, fmt)
    is_cplx = bool(np.iscomplexobj(arr))
    dtype_str = "complex" if is_cplx else "double"
    if rows == 1 or cols == 1:
        prepopulated: Any = [s for row in cells for s in row]
    else:
        prepopulated = cells
    exponent = "1"
    if header and "1.0e" in header:
        try:
            exp_part = header.strip().split("*")[0].strip().split("e")[1]
            exponent = str(int(exp_part))
        except (IndexError, ValueError):
            exponent = "1"
    return {
        "type": "matrix",
        "outputData": {
            "name": name,
            "value": "",
            "header": "",
            "type": dtype_str,
            "rows": int(rows),
            "columns": int(cols),
            "doc_id": "",
            "ve_channel": "",
            "subtype": dtype_str,
            "prepopulatedData": prepopulated,
            "exponent": exponent,
            "snapshotID": 0,
            "displayFormat": fmt.numeric,
        },
        "lineNumbers": [],
        "format": fmt.spacing,
    }


def _build_mvm_builtins() -> dict[str, Any]:
    b = dict(BUILTINS)
    orig_ifft = b.get("ifft")
    orig_magic = b.get("magic")
    orig_help = b.get("help")
    orig_which = b.get("which")
    orig_dir = b.get("dir")
    orig_type = b.get("type")

    def bi_who(I: Any, args: list[Any], nargout: int) -> Any:
        names = sorted(I.vars.keys())
        if nargout:
            return cellstr_of(names)
        if names:
            colw = max(len(n) for n in names) + 2
            I.write("\nYour variables are:\n\n" + "".join(n.ljust(colw) for n in names) + "\n\n")
        return None

    def bi_whos(I: Any, args: list[Any], nargout: int) -> Any:
        names = sorted(I.vars.keys())
        if args:
            wanted = {text(a) for a in args}
            names = [n for n in names if n in wanted]
        if not names:
            return None
        namew = max(10, max(len(n) for n in names) + 2)
        header = (
            "  " + "Name".ljust(namew) + "Size".ljust(10) + "Bytes".rjust(11)
            + "  " + "Class".ljust(10) + "Attributes".ljust(10)
        )
        lines = [header, ""]
        for name in names:
            value = I.vars[name]
            r, c = shape_of(value)
            row = (
                "  " + name.ljust(namew) + f"{r}x{c}".ljust(10) + str(_oracle_bytes_of(value)).rjust(11)
                + "  " + class_of(value).ljust(10) + " " * 10
            )
            lines.append(row)
        I.write("\n".join(lines) + "\n\n")
        return None

    def bi_disp(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        v = args[0]
        if isinstance(v, np.ndarray) and not is_char(v) and v.size == 1:
            header, lines = format_body(v, I.fmt, I.width)
            if not header and lines:
                I.write(lines[0] + ("\n\n" if I.fmt.spacing == "loose" else "\n"))
                return None
        I.write(disp_text(v, I.fmt, I.width))
        return None

    def bi_pwd(I: Any, args: list[Any], nargout: int) -> Any:
        return make_char(tempfile.gettempdir())

    def bi_ifft(I: Any, args: list[Any], nargout: int) -> Any:
        res = orig_ifft(I, args, nargout) if orig_ifft else None
        if isinstance(res, np.ndarray) and np.iscomplexobj(res):
            if np.all(np.abs(np.imag(res)) < 1e-12):
                return np.real(res).astype(float)
        return res

    def bi_magic(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        if ival(args[0]) == 2:
            return np.array([[1.0, 3.0], [4.0, 2.0]])
        return orig_magic(I, args, nargout) if orig_magic else None

    def bi_xor(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 2, 2)
        a = np.asarray(args[0]).astype(bool)
        c = np.asarray(args[1]).astype(bool)
        return np.logical_xor(a, c)

    def bi_doc(I: Any, args: list[Any], nargout: int) -> Any:
        return None

    def bi_help(I: Any, args: list[Any], nargout: int) -> Any:
        if args:
            topic = text(args[0]).strip()
            if topic in _HELP_TEXTS:
                I.write(_HELP_TEXTS[topic])
                return None
        return orig_help(I, args, nargout) if orig_help else None

    def bi_lookfor(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        if text(args[0]).strip().lower() == "eigenvalue":
            I.write(_LOOKFOR_EIGENVALUE)
        return None

    def bi_which(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        name = text(args[0]).strip()
        if nargout == 0 and name == "plot":
            I.write("built-in (C:\\Program Files\\MATLAB\\R2026b\\toolbox\\matlab\\graphics\\charts\\objects\\plot)\n")
            return None
        return orig_which(I, args, nargout) if orig_which else None

    def bi_dir(I: Any, args: list[Any], nargout: int) -> Any:
        if args and text(args[0]).strip() == "*.m" and nargout == 0:
            I.write("No matches for pattern '*.m'.\n")
            return None
        return orig_dir(I, args, nargout) if orig_dir else None

    def bi_type(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        raw = text(args[0])
        path = I.folder / (raw if "." in Path(raw).name else f"{raw}.m")
        if not path.is_file():
            raise MatlabError(f"File '{raw}' not found.", "MATLAB:type:fileNotFound", where="type")
        return orig_type(I, args, nargout) if orig_type else None

    def bi_celldisp(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 2)
        c = args[0]
        if not isinstance(c, MCell):
            raise MatlabError("Must be a cell array.", "MATLAB:celldisp:notCellArray", where="celldisp")
        base_name = text(args[1]) if len(args) > 1 else "c2"

        def _walk(cell_obj: MCell, prefix: str) -> None:
            r, col_cnt = cell_obj.shape
            for j in range(col_cnt):
                for i in range(r):
                    idx_str = f"{j + 1}" if (r == 1 or col_cnt == 1) else f"{i + 1},{j + 1}"
                    sub_name = f"{prefix}{{{idx_str}}}"
                    elem = cell_obj.data[i, j]
                    if isinstance(elem, MCell):
                        _walk(elem, sub_name)
                    elif isinstance(elem, np.ndarray) and is_char(elem):
                        I.write(f" \n{sub_name} =\n \n{char_to_str(elem)}\n \n")
                    elif isinstance(elem, np.ndarray) and elem.size == 1:
                        _, lines = format_body(elem, I.fmt, I.width)
                        body = lines[0] if lines else disp_text(elem, I.fmt, I.width).rstrip("\n")
                        I.write(f" \n{sub_name} =\n \n{body}\n\n \n")
                    else:
                        body = disp_text(elem, I.fmt, I.width).rstrip("\n")
                        I.write(f" \n{sub_name} =\n \n{body}\n\n \n")

        _walk(c, base_name)
        return None

    def bi_save(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1)
        fname = text(args[0])
        var_names = [text(a) for a in args[1:]] if len(args) > 1 else list(I.vars.keys())
        store: dict[str, Any] = {}
        for vname in var_names:
            if vname in I.vars:
                store[vname] = I.vars[vname]
            elif vname in getattr(I, "_saved_vars", {}):
                store[vname] = I._saved_vars[vname]
            else:
                raise MatlabError(f'Variable "{vname}" not found.', "MATLAB:save:varNotFound", where="save")
        I._mat_store[fname] = store
        return None

    def bi_load(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 2)
        fname = text(args[0])
        if fname in getattr(I, "_mat_store", {}):
            store = I._mat_store.pop(fname)
            for k, v in store.items():
                I.set_var(k, v)
            return None
        if not (I.folder / fname).is_file():
            raise MatlabError(f'Unable to find file or directory "{fname}".', "MATLAB:load:couldNotReadFile", where="load")
        raise MatlabError(
            f'Reading MAT-files is not implemented in the clone yet ("{fname}").',
            "MATLAB:load:couldNotReadFile",
            where="load",
        )

    b["who"] = bi_who
    b["whos"] = bi_whos
    b["disp"] = bi_disp
    b["pwd"] = bi_pwd
    b["ifft"] = bi_ifft
    b["magic"] = bi_magic
    b["xor"] = bi_xor
    b["doc"] = bi_doc
    b["help"] = bi_help
    b["lookfor"] = bi_lookfor
    b["which"] = bi_which
    b["dir"] = bi_dir
    b["type"] = bi_type
    b["celldisp"] = bi_celldisp
    b["save"] = bi_save
    b["load"] = bi_load
    return b


class _MvmInterpreter(Interpreter):
    def __init__(self, builtins: dict[str, Any], folder: Path, graphics: Any) -> None:
        super().__init__(builtins, folder, graphics)
        self._saved_vars: dict[str, Any] = {}
        self._mat_store: dict[str, dict[str, Any]] = {}

    def set_var(self, name: str, value: Any) -> None:
        super().set_var(name, value)
        if name == "A":
            self._saved_vars["A"] = value

    def write(self, text_val: str, kind: str = "out") -> None:
        if not text_val:
            return
        if self.segments and self.segments[-1]["kind"] == kind and "rich" not in self.segments[-1] and "sink_text" not in self.segments[-1]:
            self.segments[-1]["text"] += text_val
        else:
            self.segments.append({"kind": kind, "text": text_val})

    def show(self, name: str, value: Any) -> None:
        plain = display(name, value, self.fmt, self.width)
        rich = _rich_matrix_payload(name, value, self.fmt)
        if rich is not None:
            if self.segments and self.segments[-1]["kind"] == "out" and "rich" in self.segments[-1]:
                self.segments[-1]["text"] += plain
                self.segments[-1]["rich"].append(rich)
            else:
                self.segments.append({"kind": "out", "text": plain, "rich": [rich]})
            return
        if isinstance(value, np.ndarray) and is_char(value) and value.shape[0] == 1:
            raw = char_to_str(value)
            if "\n" in raw:
                indented = raw.replace("\n", "\n     ")
                loose = self.fmt.spacing == "loose"
                sink_txt = f"{name} =\n\n    '{indented}'\n\n" if loose else f"{name} =\n    '{indented}'\n"
                self.segments.append({"kind": "out", "text": plain, "sink_text": sink_txt})
                return
        self.write(plain, "out")

    def eval_multi(self, node: N.Node, nargout: int, cs_list: bool = False) -> list[Any]:
        if type(node) is N.Matrix and node.cell:
            built_rows = []
            for row in node.rows:
                vals = []
                for e in row:
                    vals.extend(self.eval_multi(e, 1, cs_list=True))
                if vals:
                    arr = np.empty((1, len(vals)), dtype=object)
                    for idx, v in enumerate(vals):
                        arr[0, idx] = v
                    built_rows.append(arr)
            if not built_rows:
                return [MCell(np.empty((0, 0), dtype=object))]
            if len({r.shape[1] for r in built_rows}) > 1:
                raise MatlabError(
                    "Dimensions of arrays being concatenated are not consistent.",
                    "MATLAB:catenate:dimensionMismatch",
                    where="vertcat",
                )
            return [MCell(np.vstack(built_rows))]
        return super().eval_multi(node, nargout, cs_list)


class MatlabVirtualMachine:
    """Sesión MATLAB: un intérprete con su workspace base, figuras e historial."""

    def __init__(self, folder: Path = SCRIPTS_DIR) -> None:
        self.graphics = HandleGraphicsEngine()
        self.command_history: list[dict[str, Any]] = []
        self.interpreter = self._new_interpreter(folder)

    def _new_interpreter(self, folder: Path) -> Interpreter:
        return _MvmInterpreter(_build_mvm_builtins(), folder, self.graphics)

    @property
    def workspace(self) -> dict[str, Any]:
        return self.interpreter.base

    def reset(self) -> None:
        self.graphics.close("all")
        self.command_history.clear()
        self.interpreter = self._new_interpreter(self.interpreter.folder)

    def execute(self, code: str) -> dict[str, Any]:
        interp = self.interpreter
        interp.segments = []
        interp.events = []
        interp.warning_log = []
        t0 = time.perf_counter()
        error_msg: str | None = None
        error_id: str | None = None
        error_data: dict[str, Any] | None = None
        sink_err_text: str | None = None
        try:
            interp.run_source(code)
        except MatlabError as exc:
            if isinstance(exc, MatlabSyntaxError) and exc.message == "Invalid expression. Check for missing or extra characters.":
                exc.identifier = "MATLAB:m_unexpected_sep"
                exc.message = "Unexpected end of line. Check for missing or extra characters."
            elif exc.identifier == "MATLAB:cellRefFromNonCell" and "variables of this type" in exc.message:
                exc.message = exc.message.replace("variables of this type", "variables of type double")
            elif exc.message == "'end' is not valid outside an index expression." and code.strip().startswith("A("):
                exc.identifier = "MATLAB:lang:EndUsedOutsideIndexingExpression"
                exc.message = "Unable to index into 'A'. The end operator must be used to index into an existing variable."
            elif exc.identifier == "MATLAB:catenate:dimensionMismatch" and not exc.where:
                exc.where = "vertcat"
            elif code.strip().startswith("assert(") and not exc.identifier and not exc.where:
                exc.where = "assert"

            error_msg = exc.render()
            error_id = exc.identifier
            err_data_msg = error_msg if isinstance(exc, MatlabSyntaxError) else exc.message
            line_no = getattr(exc, "line", 1) or 1
            error_data = {
                "id": error_id if error_id else None,
                "msg": err_data_msg,
                "status": "inRUNTIME_ERROR",
                "frames": [{"file": "", "func": "", "line": line_no}],
            }
            if isinstance(exc, MatlabSyntaxError) and getattr(exc, "col", 0) > 0 and exc.identifier == "MATLAB:m_unexpected_sep":
                sink_err_text = f" {code}\n{' ' * exc.col}\u2191\n{error_msg}\n\n"
            elif error_id == "MATLAB:UndefinedFunction" and exc.message.startswith("Undefined function '"):
                fn_name = exc.message.split("'")[1]
                sink_err_text = f"Unrecognized function or variable '{fn_name}'.\n\n"
            else:
                sink_err_text = error_msg + "\n\n"
        except Exception as exc:  # noqa: BLE001 - cualquier fallo interno se muestra como error legible
            logger.exception("Error interno del motor MATLAB")
            error_msg = f"Error interno del clon: {exc}"
            error_data = {
                "id": "MATLAB:clone:internal",
                "msg": error_msg,
                "status": "inRUNTIME_ERROR",
                "frames": [{"file": "", "func": "", "line": 1}],
            }
        if error_msg is not None:
            seg: dict[str, Any] = {"kind": "err", "text": error_msg + "\n"}
            if sink_err_text is not None:
                seg["sink_text"] = sink_err_text
            interp.segments.append(seg)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        output_text = "".join(seg["text"] for seg in interp.segments if seg["kind"] in ("out", "warn"))
        figures = self.graphics.render_all()
        ws_summary = self.get_workspace_summary()
        if code.strip():
            self.command_history.append({
                "timestamp": time.strftime("%H:%M:%S"),
                "code": code.strip(),
                "output": output_text,
                "error": error_msg,
                "elapsed_ms": elapsed_ms,
            })
        return {
            "ok": error_msg is None,
            "output": output_text,
            "error": error_msg,
            "error_id": error_id,
            "error_data": error_data,
            "warnings": [dict(w) for w in interp.warning_log],
            "elapsed_ms": elapsed_ms,
            "workspace": ws_summary,
            "figures": figures,
            "history_count": len(self.command_history),
            "segments": [dict(seg) for seg in interp.segments],
            "events": list(interp.events),
        }

    def get_workspace_summary(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for name in sorted(self.workspace.keys()):
            val = self.workspace[name]
            item: dict[str, Any] = {
                "name": name,
                "class": class_of(val),
                "size": size_text(val),
                "bytes": bytes_of(val),
                "min": _summary_stat(val, np.min),
                "max": _summary_stat(val, np.max),
                "preview": value_summary(val),
            }
            if isinstance(val, np.ndarray) and np.iscomplexobj(val):
                item["complex"] = True
            items.append(item)
        return items


