"""Builtins de cadenas, formato (printf) y salida de consola."""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np

from backend.matlab.display import disp_text
from backend.matlab.errors import MatlabError
from backend.matlab.registry import (
    builtin, bool_arr, cellstr_of, cell_items, codes_to_char, dbl, ival, is_text, make_cell,
    nargchk, real, string_list, text,
)
from backend.matlab.values import (
    MCell, MFunc, MString, MStruct, as2d, class_of, empty_double, is_char, make_char, numel,
    to_double,
)

ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", "'": "'", '"': '"', "r": "\r", "a": "\a", "b": "\b",
           "f": "\f", "v": "\v"}
SPEC_RE = re.compile(r"%(?P<flags>[-+ 0#]*)(?P<width>\*|\d+)?(?:\.(?P<prec>\*|\d+))?[lh]*(?P<conv>[diuoxXfeEgGcsaA%])")
ESCAPE_RE = re.compile(r"\\(.)", re.S)


def process_escapes(s: str) -> str:
    return ESCAPE_RE.sub(lambda m: ESCAPES.get(m.group(1), "\\" + m.group(1)), s)


def chars_of(v: Any) -> str:
    if isinstance(v, MString):
        return v.scalar()
    if is_char(v):
        return "".join(as2d(v).ravel(order="F").tolist())
    return text(v)


def _printf_atoms(args: list[Any]) -> list[Any]:
    atoms: list[Any] = []
    for v in args:
        if isinstance(v, MCell):
            raise MatlabError("Wrong type argument 'cell array'.")
        if isinstance(v, (MStruct, MFunc)):
            raise MatlabError(f"Wrong type argument '{class_of(v)}'.")
        if is_char(v) or isinstance(v, MString):
            atoms.append(chars_of(v))
        else:
            atoms.extend(np.real(dbl(v)).ravel(order="F").tolist())
    return atoms


def _special_text(value: float, flags: str, width: str | None) -> str:
    s = "NaN" if math.isnan(value) else ("Inf" if value > 0 else "-Inf")
    spec = "%" + flags.replace("0", "") + (width or "") + "s"
    return spec % s


def _format_one(conv: str, flags: str, width: str | None, prec: str | None, value: Any) -> str:
    if isinstance(value, str):
        if conv in "sc":
            spec = "%" + flags.replace("0", "") + (width or "") + ("." + prec if prec is not None else "") + "s"
            return spec % value
        return _format_one(conv, flags, width, prec, float(ord(value[0])) if value else "")
    if value == "":
        return ""
    if conv == "%":
        return "%"
    if conv == "s":
        if float(value).is_integer() and 0 <= value <= 0x10FFFF and value < 1e6:
            value = chr(int(value))
            return ("%" + flags.replace("0", "") + (width or "") + "s") % value
        return _format_one("g", flags, width, prec, value)
    if math.isinf(value) or math.isnan(value):
        return _special_text(value, flags, width)
    py_prec = "." + prec if prec is not None else ""
    if conv == "c":
        return ("%" + flags + (width or "") + "s") % chr(int(value))
    if conv in "diuxXo":
        if not float(value).is_integer():
            return ("%" + flags + (width or "") + py_prec + "e") % value
        conv_py = "d" if conv in "iu" else conv
        return ("%" + flags + (width or "") + py_prec + conv_py) % int(value)
    if conv in "aA":
        conv = "e"
    return ("%" + flags + (width or "") + py_prec + conv) % value


def format_printf(fmt: str, atoms_in: list[Any]) -> str:
    fmt = process_escapes(fmt)
    specs = list(SPEC_RE.finditer(fmt))
    atoms = list(atoms_in)
    if not specs:
        return fmt
    out: list[str] = []
    while True:
        pos = 0
        consumed = len(atoms)
        for m in specs:
            out.append(fmt[pos:m.start()])
            pos = m.end()
            conv = m.group("conv")
            flags = m.group("flags") or ""
            width = m.group("width")
            prec = m.group("prec")
            if conv == "%":
                out.append("%")
                continue
            if width == "*":
                width = str(int(atoms.pop(0))) if atoms else None
            if prec == "*":
                prec = str(int(atoms.pop(0))) if atoms else None
            if not atoms:
                continue
            value = atoms[0]
            if isinstance(value, str) and conv not in "sc" and value != "":
                atoms[0:1] = [float(ord(ch)) for ch in value]
                value = atoms[0]
            atoms.pop(0)
            out.append(_format_one(conv, flags, width, prec, value))
        out.append(fmt[pos:])
        if not atoms or not atoms_in or len(atoms) == consumed:
            break
    return "".join(out)


def _format_args(args: list[Any], name: str) -> str:
    nargchk(args, 1)
    if isinstance(args[0], MCell):
        raise MatlabError(f"{name}: format must be a character vector or string scalar.")
    return format_printf(chars_of(args[0]), _printf_atoms(args[1:]))


@builtin("sprintf")
def bi_sprintf(I: Any, args: list[Any], nargout: int) -> Any:
    return make_char(_format_args(args, "sprintf"))


@builtin("printf")
def bi_printf(I: Any, args: list[Any], nargout: int) -> Any:
    I.write(_format_args(args, "printf"))
    return None


@builtin("fprintf")
def bi_fprintf(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    fid = 1
    if not is_text(args[0]) and len(args) >= 2 and numel(args[0]) == 1:
        fid = ival(args[0])
        args = args[1:]
    if fid not in (1, 2):
        raise MatlabError("Invalid file identifier. Use fopen to generate a valid file identifier.")
    text_out = _format_args(args, "fprintf")
    I.write(text_out, "err" if fid == 2 else "out")
    return float(len(text_out.encode("utf-8"))) if nargout else None


@builtin("disp")
def bi_disp(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    out = disp_text(args[0], I.fmt, I.width)
    if nargout:
        return make_char(out)
    I.write(out)
    return None


@builtin("display")
def bi_display(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    I.show("ans", args[0])
    return None


@builtin("num2str")
def bi_num2str(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    v = args[0]
    if is_text(v):
        return v
    a = real(v)
    if len(args) == 2:
        if is_text(args[1]):
            return make_char(format_printf(chars_of(args[1]), a.ravel(order="F").tolist()))
        prec = ival(args[1])
        return _rows_to_char([[f"{x:.{prec}g}" for x in row] for row in a], "  ")
    return _num_rows(a)


def _num_rows(a: np.ndarray) -> np.ndarray:
    if a.size == 0:
        return make_char("")
    finite = a[np.isfinite(a)]
    maxabs = float(np.max(np.abs(finite))) if finite.size else 0.0
    neg = bool(np.any(a < 0))
    if a.size == 1:
        x = float(a.flat[0])
        if math.isnan(x) or math.isinf(x):
            return make_char("NaN" if math.isnan(x) else ("Inf" if x > 0 else "-Inf"))
        if x == round(x):
            return make_char(str(int(x)))
        ndgt = int(math.floor(math.log10(abs(x)))) if x != 0 else 0
        ndgt = min(max(ndgt + 5, 5), 16)
        return make_char(f"{x:.{ndgt}g}")
    all_int = bool(np.all(finite == np.round(finite))) and finite.size == a.size
    if all_int:
        ndgt = int(math.floor(math.log10(maxabs))) + 1 if maxabs > 0 else 1
        ndgt += 1 if neg else 0
        width = ndgt + 2
        rows = [["%*d" % (width, int(x)) if np.isfinite(x) else _special_text(x, "", str(width)) for x in row] for row in a]
        return _rows_to_char(rows, "", trim=True)
    ndgt = int(math.floor(math.log10(maxabs))) if maxabs > 0 else 0
    ndgt = min(max(ndgt + 5, 5), 16)
    width = ndgt + 7 + (1 if neg else 0)
    rows = [[_special_text(x, "", str(width)) if not np.isfinite(x) else ("%" + str(width) + "." + str(ndgt) + "g") % x
             for x in row] for row in a]
    return _rows_to_char(rows, "", trim=True)


def _rows_to_char(rows: list[list[str]], sep: str, trim: bool = False) -> np.ndarray:
    lines = [sep.join(row) for row in rows]
    if trim and lines:
        lead = min(len(line) - len(line.lstrip(" ")) for line in lines)
        lines = [line[lead:].rstrip() for line in lines]
    return char_matrix(lines)


def char_matrix(lines: list[str]) -> np.ndarray:
    if not lines:
        return np.zeros((0, 0), dtype="<U1")
    width = max(len(s) for s in lines)
    padded = [s.ljust(width) for s in lines]
    if width == 0:
        return np.zeros((len(lines), 0), dtype="<U1")
    return np.array([list(s) for s in padded], dtype="<U1")


@builtin("char")
def bi_char(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    if len(args) == 1 and not isinstance(args[0], MCell):
        return _to_char_array(args[0])
    lines: list[str] = []
    for v in args:
        lines.extend(string_list(v) if isinstance(v, MCell) or is_text(v) else [chars_of(_to_char_array(v))])
    return char_matrix(lines)


def _to_char_array(v: Any) -> np.ndarray:
    if is_text(v):
        return as2d(v) if is_char(v) else make_char(chars_of(v))
    codes = to_double(v)
    return codes_to_char(as2d(codes)) if codes.size else make_char("")


@builtin("int2str")
def bi_int2str(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = real(args[0])
    return _num_rows(np.round(a))


def _mat2str_value(x: float, prec: int) -> str:
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Inf" if x > 0 else "-Inf"
    return f"{x:.{prec}g}"


@builtin("mat2str")
def bi_mat2str(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    v = args[0]
    prec = ival(args[1]) if len(args) > 1 else 15
    if is_char(v):
        rows = ['"' + "".join(row).replace('"', '""') + '"' for row in as2d(v).tolist()]
        return make_char(rows[0] if len(rows) == 1 else "[" + ";".join(rows) + "]")
    a = as2d(to_double(v)) if not (isinstance(v, np.ndarray) and v.dtype.kind == "b") else as2d(v)
    if a.dtype.kind == "b":
        cells = [["true" if x else "false" for x in row] for row in a.tolist()]
    elif np.iscomplexobj(a):
        cells = [[f"{_mat2str_value(complex(x).real, prec)}{'+' if complex(x).imag >= 0 else '-'}"
                  f"{_mat2str_value(abs(complex(x).imag), prec)}i" for x in row] for row in a.tolist()]
    else:
        cells = [[_mat2str_value(float(x), prec) for x in row] for row in a.tolist()]
    body = ";".join(" ".join(row) for row in cells)
    if a.size == 1:
        return make_char(body)
    return make_char("[" + body + "]")


@builtin("str2num")
def bi_str2num(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    try:
        return I.eval_text_value("[" + chars_of(args[0]) + "]")
    except MatlabError:
        return empty_double()


def _parse_double(s: str) -> float:
    cleaned = s.strip().replace("d", "e").replace("D", "e")
    if cleaned.lower() in ("inf", "+inf"):
        return math.inf
    if cleaned.lower() == "-inf":
        return -math.inf
    try:
        return float(cleaned)
    except ValueError:
        return math.nan


@builtin("str2double")
def bi_str2double(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    v = args[0]
    if isinstance(v, MCell):
        vals = [_parse_double(chars_of(x)) if is_text(x) else math.nan for x in v.data.ravel(order="F")]
        return np.array(vals, dtype=float).reshape(v.data.shape, order="F")
    if is_text(v):
        return _parse_double(chars_of(v))
    return math.nan


@builtin("strcat")
def bi_strcat(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    if any(isinstance(a, MCell) for a in args):
        shape = next(a.data.shape for a in args if isinstance(a, MCell))
        n = int(np.prod(shape))
        parts = []
        for a in args:
            items = cell_items(a) if isinstance(a, MCell) else [a] * n
            parts.append([chars_of(x) for x in items])
        joined = ["".join(p[i] for p in parts) for i in range(n)]
        return make_cell([make_char(s) for s in joined], shape)
    out = ""
    for a in args:
        out += chars_of(a).rstrip() if is_char(a) else chars_of(a)
    return make_char(out)


def _string_compare(args: list[Any], fn: Any) -> Any:
    a, b = args[0], args[1]
    if isinstance(a, MCell) or isinstance(b, MCell):
        cell = a if isinstance(a, MCell) else b
        other = b if cell is a else a
        if isinstance(other, MCell):
            if other.data.shape != cell.data.shape:
                return np.zeros(cell.data.shape, dtype=bool)
            res = [is_text(x) and is_text(y) and fn(chars_of(x), chars_of(y)) for x, y in zip(cell.data.ravel(order="F"), other.data.ravel(order="F"))]
        else:
            res = [is_text(x) and is_text(other) and fn(chars_of(x), chars_of(other)) for x in cell.data.ravel(order="F")]
        return bool_arr(np.array(res, dtype=bool).reshape(cell.data.shape, order="F"))
    if not (is_text(a) and is_text(b)):
        return False
    return bool(fn(chars_of(a), chars_of(b)))


@builtin("strcmp")
def bi_strcmp(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    return _string_compare(args, lambda x, y: x == y)


@builtin("strcmpi")
def bi_strcmpi(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    return _string_compare(args, lambda x, y: x.lower() == y.lower())


@builtin("strncmp")
def bi_strncmp(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3, 3)
    n = ival(args[2])
    return _string_compare(args[:2], lambda x, y: len(x) >= n and len(y) >= n and x[:n] == y[:n])


@builtin("strncmpi")
def bi_strncmpi(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3, 3)
    n = ival(args[2])
    return _string_compare(args[:2], lambda x, y: len(x) >= n and len(y) >= n and x[:n].lower() == y[:n].lower())


def _map_text(v: Any, fn: Any) -> Any:
    if isinstance(v, MCell):
        return make_cell([_map_text(x, fn) for x in v.data.ravel(order="F")], v.data.shape)
    if isinstance(v, MString):
        return MString(np.array([[fn(s)] for s in v.data.ravel(order="F")], dtype=object).reshape(v.data.shape, order="F"))
    if is_char(v):
        lines = [fn("".join(row)) for row in as2d(v).tolist()]
        return make_char(lines[0]) if len(lines) == 1 else char_matrix(lines)
    return v


@builtin("upper", "toupper")
def bi_upper(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return _map_text(args[0], str.upper)


@builtin("lower", "tolower")
def bi_lower(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return _map_text(args[0], str.lower)


@builtin("strtrim")
def bi_strtrim(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    if not (is_text(args[0]) or isinstance(args[0], MCell)):
        raise MatlabError("S must be a string or cellstr")
    return _map_text(args[0], lambda s: s.strip(" \t\n\v\f\r\0"))


@builtin("deblank")
def bi_deblank(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return _map_text(args[0], lambda s: s.rstrip(" \t\n\v\f\r\0"))


@builtin("blanks")
def bi_blanks(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return make_char(" " * ival(args[0]))


@builtin("newline")
def bi_newline(I: Any, args: list[Any], nargout: int) -> Any:
    return make_char("\n")


@builtin("strfind")
def bi_strfind(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 4)
    pattern = chars_of(args[1])

    def find_all(s: str) -> np.ndarray:
        if not pattern or len(pattern) > len(s):
            return np.zeros((1, 0))
        hits = [float(i + 1) for i in range(len(s) - len(pattern) + 1) if s.startswith(pattern, i)]
        return np.array(hits, dtype=float).reshape(1, -1) if hits else np.zeros((1, 0))

    if isinstance(args[0], MCell):
        return make_cell([find_all(chars_of(x)) for x in cell_items(args[0])], args[0].data.shape)
    return find_all(chars_of(args[0]))


@builtin("strrep")
def bi_strrep(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3, 3)
    old, new = chars_of(args[1]), chars_of(args[2])
    return _map_text(args[0], lambda s: s.replace(old, new) if old else s)


def _split_by(s: str, delims: list[str]) -> list[str]:
    pattern = "|".join(re.escape(d) for d in sorted(delims, key=len, reverse=True))
    return re.split(pattern, s) if pattern else [s]


@builtin("strsplit", "split")
def bi_strsplit(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 4)
    s = chars_of(args[0])
    if len(args) >= 2:
        delims = [process_escapes(d) for d in string_list(args[1])] if isinstance(args[1], MCell) \
            else [process_escapes(chars_of(args[1]))]
    else:
        delims = [" "]
    return cellstr_of(_split_by(s, delims))


@builtin("strjoin", "join")
def bi_strjoin(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    items = string_list(args[0])
    delim = process_escapes(chars_of(args[1])) if len(args) > 1 else " "
    return make_char(delim.join(items))


@builtin("replace")
def bi_replace(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3, 3)
    return bi_strrep(I, args, nargout)


@builtin("string")
def bi_string(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    v = args[0]
    if isinstance(v, MString):
        return v
    if isinstance(v, MCell):
        return MString(np.array([[chars_of(x)] for x in v.data.ravel(order="F")], dtype=object).reshape(v.data.shape, order="F"))
    if is_char(v):
        return MString(chars_of(v))
    return MString(chars_of(_num_rows(real(v))))


@builtin("strlength")
def bi_strlength(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    if isinstance(args[0], MCell):
        return np.array([len(chars_of(x)) for x in args[0].data.ravel(order="F")], dtype=float).reshape(args[0].data.shape, order="F")
    return float(len(chars_of(args[0])))


@builtin("cellstr")
def bi_cellstr(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    v = args[0]
    if isinstance(v, MCell):
        return v
    items = string_list(v)
    return cellstr_of([s.rstrip() for s in items], column=True)


@builtin("contains")
def bi_contains(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    pats = string_list(args[1])
    if isinstance(args[0], MCell):
        return bool_arr(np.array([[any(p in chars_of(x) for p in pats)] for x in args[0].data.ravel(order="F")], dtype=bool).reshape(args[0].data.shape, order="F"))
    return any(p in chars_of(args[0]) for p in pats)


def _affix_test(args: list[Any], check: Any) -> Any:
    nargchk(args, 2, 2)
    pats = string_list(args[1])
    if isinstance(args[0], MCell):
        vals = [any(check(chars_of(x), p) for p in pats) for x in args[0].data.ravel(order="F")]
        return bool_arr(np.array(vals, dtype=bool).reshape(args[0].data.shape, order="F"))
    return any(check(chars_of(args[0]), p) for p in pats)


@builtin("startsWith")
def bi_startswith(I: Any, args: list[Any], nargout: int) -> Any:
    return _affix_test(args, lambda s, p: s.startswith(p))


@builtin("endsWith")
def bi_endswith(I: Any, args: list[Any], nargout: int) -> Any:
    return _affix_test(args, lambda s, p: s.endswith(p))


def _char_predicate(names: tuple[str, ...], test: Any) -> None:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        if not is_char(args[0]):
            return bool_arr(np.zeros(as2d(to_double(args[0])).shape, dtype=bool))
        arr = as2d(args[0])
        return bool_arr(np.vectorize(test, otypes=[bool])(arr) if arr.size else np.zeros(arr.shape, dtype=bool))
    builtin(*names)(fn)


_char_predicate(("isspace",), lambda c: c in " \t\n\v\f\r")
_char_predicate(("isletter", "isalpha"), lambda c: c.isalpha())
_char_predicate(("isdigit",), lambda c: c.isdigit())
_char_predicate(("isupper",), lambda c: c.isupper())
_char_predicate(("islower",), lambda c: c.islower())

STRPROP_TESTS = {
    "alpha": str.isalpha, "digit": str.isdigit, "alphanum": str.isalnum, "upper": str.isupper,
    "lower": str.islower, "wspace": lambda c: c in " \t\n\v\f\r", "punct": lambda c: not c.isalnum() and c.isprintable() and not c.isspace(),
}


@builtin("isstrprop")
def bi_isstrprop(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    kind = chars_of(args[1])
    if kind not in STRPROP_TESTS:
        raise MatlabError(f"Unsupported string property '{kind}'.")
    test = STRPROP_TESTS[kind]
    arr = as2d(args[0]) if is_char(args[0]) else as2d(to_double(args[0]))
    if is_char(args[0]):
        return bool_arr(np.vectorize(lambda c: test(c), otypes=[bool])(arr))
    return bool_arr(np.zeros(arr.shape, dtype=bool))


@builtin("num2cell")
def bi_num2cell(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = as2d(to_double(args[0])) if not isinstance(args[0], MCell) else args[0].data
    vals = [as2d(np.array([[x]], dtype=a.dtype)) for x in a.ravel(order="F")]
    return make_cell(vals, a.shape)


def _base_convert(value: float, base: int, length: int | None) -> str:
    n = int(value)
    digits = "0123456789ABCDEF"
    out = ""
    while n > 0:
        out = digits[n % base] + out
        n //= base
    if not out:
        out = "0"
    return out.rjust(length or 0, "0")


def _dec_to_base(args: list[Any], base: int) -> Any:
    nargchk(args, 1, 2)
    length = ival(args[1]) if len(args) > 1 else None
    values = real(args[0]).ravel(order="F").tolist()
    rows = [_base_convert(v, base, length) for v in values]
    width = max((len(r) for r in rows), default=0)
    rows = [r.rjust(width, "0") for r in rows]
    return char_matrix(rows) if len(rows) != 1 else make_char(rows[0])


def _base_to_dec(args: list[Any], base: int) -> Any:
    nargchk(args, 1, 1)
    items = string_list(args[0])
    vals = []
    for s in items:
        cleaned = s.strip().replace(" ", "")
        try:
            vals.append(float(int(cleaned, base)) if cleaned else math.nan)
        except ValueError:
            vals.append(math.nan)
    return np.array(vals, dtype=float).reshape(-1, 1) if len(vals) != 1 else vals[0]


@builtin("dec2bin")
def bi_dec2bin(I: Any, args: list[Any], nargout: int) -> Any:
    return _dec_to_base(args, 2)


@builtin("dec2hex")
def bi_dec2hex(I: Any, args: list[Any], nargout: int) -> Any:
    return _dec_to_base(args, 16)


@builtin("bin2dec")
def bi_bin2dec(I: Any, args: list[Any], nargout: int) -> Any:
    return _base_to_dec(args, 2)


@builtin("hex2dec")
def bi_hex2dec(I: Any, args: list[Any], nargout: int) -> Any:
    return _base_to_dec(args, 16)


# ---------- expresiones regulares ----------

def _convert_pattern(pat: str) -> str:
    return pat.replace("(?<", "(?P<").replace("(?P<=", "(?<=").replace("(?P<!", "(?<!")


def _expand_replacement(rep: str, m: re.Match[str]) -> str:
    def group_text(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if idx > (m.re.groups or 0):
            return ""
        return m.group(idx) or ""
    return re.sub(r"\$(\d+)", group_text, rep)


def _regex_flags(opts: list[str], ignore_case: bool) -> int:
    flags = re.I if ignore_case or "ignorecase" in opts else 0
    return flags


@builtin("regexprep")
def bi_regexprep(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3)
    pat = _convert_pattern(chars_of(args[1]))
    rep = chars_of(args[2])
    opts = [chars_of(a).lower() for a in args[3:] if is_text(a)]
    flags = _regex_flags(opts, False)
    count = 1 if "once" in opts else 0

    def apply(s: str) -> str:
        return re.sub(pat, lambda m: _expand_replacement(rep, m), s, count=count, flags=flags)

    return _map_text(args[0], apply)


@builtin("regexp")
def bi_regexp(I: Any, args: list[Any], nargout: int) -> Any:
    return _regexp(args, nargout, False)


@builtin("regexpi")
def bi_regexpi(I: Any, args: list[Any], nargout: int) -> Any:
    return _regexp(args, nargout, True)


REGEXP_DEFAULT_ORDER = ["start", "end", "tokenExtents", "match", "tokens", "names", "split"]
REGEXP_OUTPUT_NAMES = {k.lower(): k for k in REGEXP_DEFAULT_ORDER}


def _regexp(args: list[Any], nargout: int, ignore_case: bool) -> Any:
    nargchk(args, 2)
    s = chars_of(args[0])
    pat = _convert_pattern(chars_of(args[1]))
    opts = [chars_of(a) for a in args[2:]]
    lowered = [o.lower() for o in opts]
    once = "once" in lowered
    compiled = re.compile(pat, _regex_flags(lowered, ignore_case))
    matches = list(compiled.finditer(s))
    if once:
        matches = matches[:1]
    selected = [REGEXP_OUTPUT_NAMES[o] for o in lowered if o in REGEXP_OUTPUT_NAMES] or REGEXP_DEFAULT_ORDER
    results = [_regexp_output(name, s, matches, compiled, once) for name in selected]
    if nargout <= 1:
        return results[0]
    return results[:nargout]


def _regexp_output(name: str, s: str, matches: list[re.Match[str]], compiled: re.Pattern[str], once: bool) -> Any:
    def positions(values: list[float]) -> Any:
        if once:
            return values[0] if values else empty_double()
        return np.array(values, dtype=float).reshape(1, -1) if values else np.zeros((1, 0))

    def group_strings(m: re.Match[str]) -> list[str]:
        return [m.group(0)] if compiled.groups == 0 else [g or "" for g in m.groups()]

    if name == "start":
        return positions([float(m.start() + 1) for m in matches])
    if name == "end":
        return positions([float(m.end()) for m in matches])
    if name == "tokenExtents":
        return make_cell([])
    if name == "match":
        if once:
            return make_char(matches[0].group(0)) if matches else make_char("")
        return make_cell([make_char(m.group(0)) for m in matches]) if matches else make_cell([])
    if name == "tokens":
        if once:
            return make_cell([make_char(t) for t in group_strings(matches[0])]) if matches else make_cell([])
        cells = [make_cell([make_char(t) for t in group_strings(m)]) for m in matches]
        return make_cell(cells) if cells else make_cell([])
    if name == "names":
        fields = list(compiled.groupindex.keys())
        dicts = []
        for m in matches or [None]:
            dicts.append({f: make_char((m.group(f) or "") if m else "") for f in fields})
        if len(dicts) == 1:
            return MStruct.scalar(dicts[0]) if fields else MStruct([], None)
        arr = np.empty((1, len(dicts)), dtype=object)
        for i, d in enumerate(dicts):
            arr[0, i] = d
        return MStruct(fields, arr)
    if name == "split":
        pieces = []
        last = 0
        for m in matches:
            pieces.append(make_char(s[last:m.start()]))
            last = m.end()
        pieces.append(make_char(s[last:]))
        return make_cell(pieces)
    raise MatlabError(f"Unsupported regexp output '{name}'.")
