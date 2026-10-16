"""Operadores, concatenación e indexado con semántica MATLAB (column-major, 1-based)."""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.matlab.errors import (
    MatlabError, bad_index, incompatible_sizes, index_exceeds, matmul_dims,
)
from backend.matlab.values import (
    INT_TYPES, MCell, MFunc, MString, MStruct, as2d, class_of, empty_double, is_char,
    make_char, numel, saturate_int, shape_of, to_double,
)

COLON = object()  # marcador de ':' en índices

np.seterr(all="ignore")


# ---------- clases de resultado ----------

def _result_class(a: Any, b: Any) -> str:
    ca, cb = class_of(a), class_of(b)
    ia, ib = ca in INT_TYPES, cb in INT_TYPES
    if ia and ib and ca != cb:
        raise MatlabError(
            f"Integers can only be combined with integers of the same class, or scalar doubles.",
            "MATLAB:mixedClasses",
        )
    if ia:
        return ca
    if ib:
        return cb
    if "single" in (ca, cb):
        return "single"
    return "double"


def _cast(result: np.ndarray, cls: str) -> np.ndarray:
    if cls in INT_TYPES:
        return saturate_int(result, cls)
    if cls == "single":
        return result.astype(np.complex64 if np.iscomplexobj(result) else np.float32)
    return result


def _clean_complex(r: np.ndarray) -> np.ndarray:
    if np.iscomplexobj(r) and r.size and np.all(np.imag(r) == 0):
        return np.real(r).astype(float)
    return r


def _broadcast(fn, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x, y = as2d(x), as2d(y)
    if x.shape != y.shape:
        for dx, dy in zip(x.shape, y.shape):
            if dx != dy and dx != 1 and dy != 1:
                raise incompatible_sizes()
    return fn(x, y)


def _string_binop(op: str, a: Any, b: Any) -> Any:
    def as_strs(v: Any) -> np.ndarray:
        if isinstance(v, MString):
            return v.data
        if is_char(v):
            arr = np.empty((1, 1), dtype=object)
            arr[0, 0] = "".join(as2d(v).ravel().tolist()) if v.size else ""
            return arr
        if isinstance(v, np.ndarray):
            arr = np.empty(as2d(v).shape, dtype=object)
            for idx, x in np.ndenumerate(as2d(v)):
                arr[idx] = _num_to_string(x)
            return arr
        if isinstance(v, MCell):
            return np.vectorize(lambda e: "".join(as2d(e).ravel().tolist()) if is_char(e) else str(e), otypes=[object])(v.data)
        raise MatlabError(f"Operator '{op}' is not supported for operands of type '{class_of(v)}'.")

    x, y = as_strs(a), as_strs(b)
    if op == "+":
        return MString(np.vectorize(lambda p, q: p + q, otypes=[object])(*np.broadcast_arrays(x, y)))
    cmp = {
        "==": lambda p, q: p == q, "~=": lambda p, q: p != q, "<": lambda p, q: p < q,
        "<=": lambda p, q: p <= q, ">": lambda p, q: p > q, ">=": lambda p, q: p >= q,
    }
    if op in cmp:
        return np.vectorize(cmp[op], otypes=[bool])(*np.broadcast_arrays(x, y))
    raise MatlabError(f"Operator '{op}' is not supported for operands of type 'string'.")


def _num_to_string(x: Any) -> str:
    if isinstance(x, (bool, np.bool_)):
        return "true" if x else "false"
    f = float(np.real(x))
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return f"{f:.5g}"


def binop(op: str, a: Any, b: Any) -> Any:
    if isinstance(a, MString) or isinstance(b, MString):
        return _string_binop(op, a, b)
    if op in ("&&", "||"):
        raise MatlabError("internal: short-circuit handled by interpreter")
    x, y = to_double(a), to_double(b)
    cls = _result_class(a, b)
    int_mode = cls in INT_TYPES
    if int_mode:
        x, y = x.astype(float), y.astype(float)
    if op in ("==", "~=", "<", "<=", ">", ">="):
        fn = {
            "==": np.equal, "~=": np.not_equal, "<": np.less, "<=": np.less_equal,
            ">": np.greater, ">=": np.greater_equal,
        }[op]
        if op in ("<", "<=", ">", ">=") and (np.iscomplexobj(x) or np.iscomplexobj(y)):
            x, y = np.real(x), np.real(y)
        return _broadcast(fn, x, y)
    if op in ("&", "|"):
        for v in (x, y):
            if np.any(np.isnan(np.real(v))):
                raise MatlabError("NaN's cannot be converted to logicals.", "MATLAB:nologicalnan")
        fn = np.logical_and if op == "&" else np.logical_or
        return _broadcast(fn, x != 0, y != 0)
    if op == "+":
        r = _broadcast(np.add, x, y)
    elif op == "-":
        r = _broadcast(np.subtract, x, y)
    elif op == ".*":
        r = _broadcast(np.multiply, x, y)
    elif op == "./":
        r = _broadcast(_divide, x, y)
    elif op == ".\\":
        r = _broadcast(_divide, y, x)
    elif op == ".^":
        r = _broadcast(_power, x, y)
    elif op == "*":
        if x.size == 1 or y.size == 1:
            r = np.multiply(as2d(x), as2d(y))
        else:
            x2, y2 = as2d(x), as2d(y)
            if x2.shape[1] != y2.shape[0]:
                raise matmul_dims()
            r = x2 @ y2
    elif op == "/":
        if y.size == 1:
            r = _divide(as2d(x), as2d(y))
        else:
            r = mrdivide(x, y)
    elif op == "\\":
        if x.size == 1:
            r = _divide(as2d(y), as2d(x))
        else:
            r = mldivide(x, y)
    elif op == "^":
        r = mpower(x, y)
    else:
        raise MatlabError(f"Operador no soportado: {op}")
    r = _clean_complex(as2d(np.asarray(r)))
    return _cast(r, cls) if cls != "double" else r


def _divide(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    with np.errstate(all="ignore"):
        if np.iscomplexobj(x) or np.iscomplexobj(y):
            return np.true_divide(x, y)
        return np.true_divide(x.astype(float), y.astype(float))


def _power(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    with np.errstate(all="ignore"):
        xf = x.astype(complex) if np.iscomplexobj(x) else x.astype(float)
        yf = y.astype(complex) if np.iscomplexobj(y) else y.astype(float)
        if not np.iscomplexobj(xf) and not np.iscomplexobj(yf):
            xb, yb = np.broadcast_arrays(xf, yf)
            if np.any((xb < 0) & (yb != np.round(yb))):
                return np.power(xb.astype(complex), yb)
        return np.power(xf, yf)


WARN_SINK: list[str] = []


def mldivide(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    A, B = as2d(a).astype(complex if np.iscomplexobj(a) else float), as2d(b)
    B = B.astype(complex if np.iscomplexobj(B) or np.iscomplexobj(A) else float)
    if A.shape[0] != B.shape[0]:
        raise MatlabError(
            "Matrix dimensions must agree.", "MATLAB:dimagree",
        )
    if A.shape[0] == A.shape[1]:
        cond = np.linalg.cond(A) if A.size else 0
        if not np.isfinite(cond) or cond > 1 / np.finfo(float).eps:
            WARN_SINK.append("Warning: Matrix is singular to working precision.")
            with np.errstate(all="ignore"):
                try:
                    return np.linalg.solve(A, B)
                except np.linalg.LinAlgError:
                    return np.full((A.shape[1], B.shape[1]), np.inf)
        return np.linalg.solve(A, B)
    sol, *_ = np.linalg.lstsq(A, B, rcond=None)
    if np.linalg.matrix_rank(A) < min(A.shape):
        WARN_SINK.append(f"Warning: Rank deficient, rank = {np.linalg.matrix_rank(A)}.")
    return sol


def mrdivide(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    A, B = as2d(a), as2d(b)
    if A.shape[1] != B.shape[1]:
        raise MatlabError("Matrix dimensions must agree.", "MATLAB:dimagree")
    return mldivide(B.T, A.T).T


def mpower(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    A, B = as2d(a), as2d(b)
    if A.size == 1 and B.size == 1:
        return _power(A, B)
    if B.size == 1 and A.shape[0] == A.shape[1]:
        p = complex(B.flat[0])
        if p.imag == 0 and p.real == round(p.real):
            n = int(p.real)
            if n >= 0:
                return np.linalg.matrix_power(A, n)
            return np.linalg.matrix_power(np.linalg.inv(A), -n)
        w, V = np.linalg.eig(A)
        return V @ np.diag(w.astype(complex) ** p) @ np.linalg.inv(V)
    if A.size == 1 and B.shape[0] == B.shape[1]:
        w, V = np.linalg.eig(B)
        return V @ np.diag(complex(A.flat[0]) ** w) @ np.linalg.inv(V)
    raise MatlabError(
        "Incorrect dimensions for raising a matrix to a power. Check that the matrix is square and the "
        "power is a scalar. To operate on each element of the matrix individually, use POWER (.^) for "
        "elementwise power.",
        "MATLAB:mpower:notScalarAndSquareMatrix",
    )


def unop(op: str, a: Any) -> Any:
    if op == "()":
        return a
    if op == "~":
        x = to_double(a)
        if np.any(np.isnan(np.real(x))):
            raise MatlabError("NaN's cannot be converted to logicals.", "MATLAB:nologicalnan")
        return as2d(x == 0)
    x = to_double(a)
    if op == "-":
        cls = class_of(a)
        if cls in INT_TYPES:
            return saturate_int(-x.astype(float), cls)
        return as2d(-x)
    if op == "+":
        return as2d(x)
    raise MatlabError(f"Operador unario no soportado: {op}")


def transpose(a: Any, conj: bool) -> Any:
    if isinstance(a, MCell):
        return MCell(a.data.T.copy())
    if isinstance(a, MString):
        return MString(a.data.T.copy())
    if isinstance(a, MStruct):
        return MStruct(a.fields, a.data.T.copy())
    if isinstance(a, np.ndarray):
        t = as2d(a).T
        return np.conj(t) if conj and np.iscomplexobj(t) else t.copy()
    raise MatlabError(f"Transpose is not supported for operands of type '{class_of(a)}'.")


def colon_range(start: Any, step: Any, stop: Any) -> np.ndarray:
    def sc(v: Any) -> float:
        d = to_double(v)
        if d.size == 0:
            return float("nan")
        return float(np.real(d.flat[0]))

    s0, st, s1 = sc(start), (1.0 if step is None else sc(step)), sc(stop)
    if any(np.isnan(v) for v in (s0, st, s1)) or st == 0 or (st > 0 and s0 > s1) or (st < 0 and s0 < s1):
        return np.zeros((1, 0))
    n = int(np.floor((s1 - s0) / st * (1 + 1e-12) + 1e-10)) + 1
    r = (s0 + st * np.arange(n, dtype=float)).reshape(1, -1)
    cls = _result_class(start, stop) if step is None else _result_class(_result_class_val(start, step), stop)
    return _cast(r, cls) if cls != "double" else r


def _result_class_val(a: Any, b: Any) -> Any:
    cls = _result_class(a, b)
    return np.zeros((1, 1), dtype=INT_TYPES[cls]) if cls in INT_TYPES else np.zeros((1, 1))


# ---------- concatenación ----------

def concat(rows: list[list[Any]]) -> Any:
    row_vals = []
    for row in rows:
        items = [v for v in row if not (isinstance(v, np.ndarray) and v.size == 0 and v.shape in ((0, 0), (1, 0), (0, 1)))]
        if not items:
            continue
        row_vals.append(_hcat(items))
    if not row_vals:
        if rows and any(is_char(v) for r in rows for v in r):
            return make_char("")
        return empty_double()
    if len(row_vals) == 1:
        return row_vals[0]
    return _vcat(row_vals)


def _common_kind(items: list[Any]) -> str:
    if any(isinstance(v, MCell) for v in items):
        return "cell"
    if any(isinstance(v, MString) for v in items):
        return "string"
    if any(isinstance(v, MStruct) for v in items):
        return "struct"
    if any(isinstance(v, MFunc) for v in items):
        raise MatlabError("Nonscalar arrays of function handles are not allowed; use cell arrays instead.")
    if any(is_char(v) for v in items):
        return "char"
    return "numeric"


def _to_kind(v: Any, kind: str) -> Any:
    if kind == "cell":
        if isinstance(v, MCell):
            return v.data
        arr = np.empty((1, 1), dtype=object)
        arr[0, 0] = v
        return arr
    if kind == "string":
        if isinstance(v, MString):
            return v.data
        from backend.matlab.ops import _string_binop  # noqa
        arr = np.empty((1, 1), dtype=object)
        arr[0, 0] = "".join(as2d(v).ravel().tolist()) if is_char(v) else _num_to_string(as2d(v).flat[0])
        return arr
    if kind == "struct":
        if not isinstance(v, MStruct):
            raise MatlabError("Concatenation of struct with non-struct values is not allowed.")
        return v
    if kind == "char":
        if is_char(v):
            return as2d(v)
        d = to_double(v)
        return np.vectorize(lambda c: chr(int(c)), otypes=["<U1"])(as2d(d)) if d.size else np.zeros((0, 0), "<U1")
    return as2d(v)


def _numeric_class(items: list[Any]) -> str:
    classes = [class_of(v) for v in items]
    for c in classes:
        if c in INT_TYPES:
            return c
    if "single" in classes:
        return "single"
    if all(c == "logical" for c in classes):
        return "logical"
    return "double"


def _hcat(items: list[Any]) -> Any:
    kind = _common_kind(items)
    if kind == "struct":
        fields = items[0].fields
        for s in items:
            if set(s.fields) != set(fields):
                raise MatlabError("Concatenation of structures requires same field names.", "MATLAB:catenate:structFieldBad")
        return MStruct(fields, np.hstack([s.data for s in items]))
    parts = [_to_kind(v, kind) for v in items]
    rows = {p.shape[0] for p in parts}
    if len(rows) > 1:
        raise MatlabError("Dimensions of arrays being concatenated are not consistent.", "MATLAB:catenate:dimensionMismatch")
    if kind == "numeric":
        cls = _numeric_class(items)
        res = np.hstack([to_double(p) if cls != "logical" else p for p in parts])
        return _cast(res, cls) if cls in INT_TYPES or cls == "single" else (res.astype(bool) if cls == "logical" else _clean_complex(res))
    if kind == "cell":
        return MCell(np.hstack(parts))
    if kind == "string":
        return MString(np.hstack(parts))
    return np.hstack(parts)


def _vcat(items: list[Any]) -> Any:
    kind = _common_kind(items)
    if kind == "struct":
        return MStruct(items[0].fields, np.vstack([s.data for s in items]))
    parts = [_to_kind(v, kind) for v in items]
    cols = {p.shape[1] for p in parts}
    if len(cols) > 1:
        if kind == "char":
            raise MatlabError("Dimensions of arrays being concatenated are not consistent.", "MATLAB:catenate:dimensionMismatch")
        raise MatlabError("Dimensions of arrays being concatenated are not consistent.", "MATLAB:catenate:dimensionMismatch")
    if kind == "numeric":
        cls = _numeric_class(items)
        res = np.vstack([to_double(p) if cls != "logical" else p for p in parts])
        return _cast(res, cls) if cls in INT_TYPES or cls == "single" else (res.astype(bool) if cls == "logical" else _clean_complex(res))
    if kind == "cell":
        return MCell(np.vstack(parts))
    if kind == "string":
        return MString(np.vstack(parts))
    return np.vstack(parts)


# ---------- indexado ----------

def _data_of(v: Any) -> np.ndarray:
    if isinstance(v, (MCell, MString, MStruct)):
        return v.data
    return as2d(v)


def _wrap_like(v: Any, data: np.ndarray) -> Any:
    if isinstance(v, MCell):
        return MCell(data)
    if isinstance(v, MString):
        return MString(data)
    if isinstance(v, MStruct):
        return MStruct(v.fields, data)
    return data


def _subs(idx: Any, extent: int, pos: int | None) -> np.ndarray | slice:
    if idx is COLON:
        return slice(None)
    if isinstance(idx, np.ndarray) and idx.dtype.kind == "U" and idx.size == 1 and idx.flat[0] == ":":
        return slice(None)
    if isinstance(idx, np.ndarray) and idx.dtype.kind == "b":
        flat = idx.ravel(order="F")
        if flat.size > extent and np.any(flat[extent:]):
            raise index_exceeds(extent, pos)
        return np.flatnonzero(flat)
    if not isinstance(idx, np.ndarray):
        raise MatlabError(f"Unable to use a value of type {class_of(idx)} as an index.", "MATLAB:index:invalidType")
    d = to_double(idx)
    if np.iscomplexobj(d):
        raise bad_index()
    flat = d.ravel(order="F").astype(float)
    if flat.size and (np.any(flat < 1) or np.any(flat != np.floor(flat)) or np.any(np.isnan(flat))):
        raise bad_index()
    out = flat.astype(np.int64) - 1
    return out


def index_get(v: Any, args: list[Any]) -> Any:
    if isinstance(v, MFunc):
        raise MatlabError("internal: function handle call")
    data = _data_of(v)
    if len(args) == 0:
        return v
    r, c = data.shape
    if len(args) == 1:
        idx = args[0]
        n = r * c
        sub = _subs(idx, n, None)
        flat = data.ravel(order="F")
        if isinstance(sub, slice):
            res = flat.reshape(-1, 1)
            return _wrap_like(v, res)
        if sub.size and sub.max() >= n:
            raise index_exceeds(n)
        picked = flat[sub]
        ish = shape_of(idx) if isinstance(idx, np.ndarray) else (1, sub.size)
        if isinstance(idx, np.ndarray) and idx.dtype.kind == "b":
            # logical: columna salvo que el origen sea fila
            res = picked.reshape(1, -1) if r == 1 else picked.reshape(-1, 1)
        elif (r == 1 or c == 1) and (ish[0] == 1 or ish[1] == 1):
            res = picked.reshape(1, -1) if r == 1 and n > 0 else picked.reshape(-1, 1)
            if n == 1:
                res = picked.reshape(ish)
        else:
            res = picked.reshape(ish, order="F")
        return _wrap_like(v, res)
    # 2-D (los índices extra deben ser 1)
    for extra in args[2:]:
        s = _subs(extra, 1, 3)
        if not isinstance(s, slice) and (s.size == 0 or np.any(s != 0)):
            raise index_exceeds(1, 3)
    si = _subs(args[0], r, 1)
    sj = _subs(args[1], c, 2)
    if not isinstance(si, slice) and si.size and si.max() >= r:
        raise index_exceeds(r, 1)
    if not isinstance(sj, slice) and sj.size and sj.max() >= c:
        raise index_exceeds(c, 2)
    rows = np.arange(r) if isinstance(si, slice) else si
    cols = np.arange(c) if isinstance(sj, slice) else sj
    return _wrap_like(v, data[np.ix_(rows, cols)])


def _fill_value(v: Any) -> Any:
    if isinstance(v, MCell):
        return empty_double()
    if isinstance(v, MString):
        return None
    if is_char(v):
        return "\x00"
    return 0


def _grow(data: np.ndarray, rows: int, cols: int, fill: Any) -> np.ndarray:
    r, c = data.shape
    if rows <= r and cols <= c:
        return data
    nr, nc = max(r, rows), max(c, cols)
    if data.dtype == object:
        new = np.empty((nr, nc), dtype=object)
        for idx in np.ndindex(nr, nc):
            new[idx] = empty_double() if fill is not None else None
        if fill is None:
            for idx in np.ndindex(nr, nc):
                new[idx] = ""
    else:
        new = np.full((nr, nc), fill, dtype=data.dtype)
    new[:r, :c] = data
    return new


def _coerce_rhs(lhs: Any, rhs: Any) -> tuple[Any, np.ndarray]:
    """Devuelve (lhs convertido, datos de rhs) con las reglas de clase de MATLAB."""
    if isinstance(lhs, MCell):
        if isinstance(rhs, MCell):
            return lhs, rhs.data
        raise MatlabError(
            "Conversion to cell from %s is not possible." % class_of(rhs), "MATLAB:invalidConversion"
        )
    if isinstance(lhs, MString):
        if isinstance(rhs, MString):
            return lhs, rhs.data
        conv = _to_kind(rhs, "string")
        return lhs, conv
    if isinstance(lhs, MStruct):
        if isinstance(rhs, MStruct):
            return lhs, rhs.data
        raise MatlabError("Conversion to struct from %s is not possible." % class_of(rhs))
    if isinstance(rhs, (MCell, MStruct, MString, MFunc)):
        if isinstance(lhs, np.ndarray) and lhs.size == 0:
            return _empty_like_value(rhs), _data_of(rhs) if not isinstance(rhs, MFunc) else None
        raise MatlabError(
            f"Unable to perform assignment because value of type '{class_of(rhs)}' is not convertible to '{class_of(lhs)}'.",
            "MATLAB:invalidConversion",
        )
    lcls, rcls = class_of(lhs), class_of(rhs)
    rdata = as2d(rhs)
    if lcls in INT_TYPES:
        return lhs, saturate_int(to_double(rdata), lcls)
    if lcls == "char":
        if rcls == "char":
            return lhs, rdata
        return lhs, _to_kind(rdata, "char")
    if lcls == "logical" and rcls != "logical":
        lhs = lhs.astype(float)
    if lcls in ("double", "logical", "single") and rcls in INT_TYPES and lhs.size == 0:
        lhs = lhs.astype(rdata.dtype)
        return lhs, rdata
    rd = to_double(rdata) if rcls in ("char", "logical") and lcls != "logical" else rdata
    if np.iscomplexobj(rd) and not np.iscomplexobj(lhs):
        lhs = lhs.astype(complex)
    if lcls == "double" and rcls == "single":
        pass
    if lcls == "double" and lhs.size == 0 and rcls == "char":
        return make_char(""), rdata
    return lhs, rd


def _empty_like_value(rhs: Any) -> Any:
    if isinstance(rhs, MCell):
        return MCell(np.empty((0, 0), dtype=object))
    if isinstance(rhs, MString):
        return MString(np.empty((0, 0), dtype=object))
    if isinstance(rhs, MStruct):
        return MStruct(rhs.fields, np.empty((0, 0), dtype=object))
    return empty_double()


def index_set(target: Any, args: list[Any], rhs: Any, delete: bool = False) -> Any:
    if target is None:
        if isinstance(rhs, (MCell, MString, MStruct)):
            target = _empty_like_value(rhs)
        elif is_char(rhs):
            target = np.zeros((0, 0), dtype="<U1")
        elif isinstance(rhs, np.ndarray):
            target = np.zeros((0, 0), dtype=rhs.dtype)
        else:
            target = empty_double()
    if delete:
        return index_delete(target, args)
    if isinstance(target, MStruct) and not isinstance(rhs, MStruct):
        raise MatlabError("Conversion to struct from %s is not possible." % class_of(rhs))
    target, rdata = _coerce_rhs(target, rhs)
    if isinstance(target, MStruct) and isinstance(rhs, MStruct):
        target = _align_struct_fields(target, rhs)
        rdata = _align_struct_fields(rhs, target).data
    data = _data_of(target).copy() if isinstance(target, np.ndarray) else _data_of(target).copy()
    if isinstance(target, np.ndarray) and target.dtype != rdata.dtype and target.dtype.kind != "U":
        if np.iscomplexobj(rdata) and not np.iscomplexobj(data):
            data = data.astype(complex)
        elif data.dtype.kind == "b" and rdata.dtype.kind != "b":
            data = data.astype(float)
        elif data.dtype.kind == "f" and rdata.dtype.kind in "iu" and data.size == 0:
            data = data.astype(rdata.dtype)
    fill = _fill_value(target)
    r, c = data.shape
    nrhs = rdata.size
    if len(args) == 1:
        idx = args[0]
        if idx is COLON or (isinstance(idx, np.ndarray) and idx.dtype.kind == "U"):
            if nrhs == 1:
                data[...] = rdata.flat[0]
            elif nrhs == data.size:
                data = rdata.ravel(order="F").reshape(data.shape, order="F").astype(data.dtype, copy=False)
            else:
                raise _numel_mismatch(data.size, nrhs)
            return _wrap_like(target, data)
        sub = _subs(idx, r * c, None)
        k = sub.size
        if k == 0:
            return _wrap_like(target, data)
        need = int(sub.max()) + 1
        if need > r * c:
            if r == 0 and c == 0:
                data = _grow(data, 1, need, fill)
            elif r == 1:
                data = _grow(data, 1, need, fill)
            elif c == 1:
                data = _grow(data, need, 1, fill)
            else:
                raise MatlabError(
                    "Attempt to grow array along ambiguous dimension.", "MATLAB:indexed:ambiguousGrowth"
                )
        flat = data.ravel(order="F").copy()
        if nrhs == 1:
            flat[sub] = rdata.flat[0]
        elif nrhs == k:
            flat[sub] = rdata.ravel(order="F")
        else:
            raise _numel_mismatch(k, nrhs)
        return _wrap_like(target, flat.reshape(data.shape, order="F"))
    si = _subs(args[0], r, 1)
    sj = _subs(args[1], c, 2)
    rows = np.arange(r) if isinstance(si, slice) else si
    cols = np.arange(c) if isinstance(sj, slice) else sj
    if isinstance(si, slice) and r == 0:
        rows = np.arange(rdata.shape[0])
    if isinstance(sj, slice) and c == 0:
        cols = np.arange(rdata.shape[1] if rdata.ndim == 2 else 1)
    need_r = int(rows.max()) + 1 if rows.size else 0
    need_c = int(cols.max()) + 1 if cols.size else 0
    data = _grow(data, need_r, need_c, fill)
    if rows.size == 0 or cols.size == 0:
        return _wrap_like(target, data)
    if nrhs == 1:
        data[np.ix_(rows, cols)] = rdata.flat[0]
    elif rdata.shape == (rows.size, cols.size):
        data[np.ix_(rows, cols)] = rdata
    elif nrhs == rows.size * cols.size:
        data[np.ix_(rows, cols)] = rdata.ravel(order="F").reshape((rows.size, cols.size), order="F")
    else:
        raise MatlabError(
            f"Unable to perform assignment because the size of the left side is {rows.size}-by-{cols.size} "
            f"and the size of the right side is {rdata.shape[0]}-by-{rdata.shape[1]}.",
            "MATLAB:subsassigndimmismatch",
        )
    return _wrap_like(target, data)


def _align_struct_fields(a: MStruct, b: MStruct) -> MStruct:
    missing = [f for f in b.fields if f not in a.fields]
    if not missing:
        return a
    out = a.copy()
    for d in out.data.flat:
        for f in missing:
            d[f] = empty_double()
    out.fields = out.fields + missing
    return out


def _numel_mismatch(k: int, n: int) -> MatlabError:
    return MatlabError(
        f"Unable to perform assignment because the left and right sides have a different number of elements.",
        "MATLAB:index:lhsrhsnumelmismatch",
    ) if k != n else MatlabError("Assignment error.")


def index_delete(target: Any, args: list[Any]) -> Any:
    data = _data_of(target)
    r, c = data.shape
    if len(args) == 1:
        sub = _subs(args[0], r * c, None)
        if isinstance(sub, slice):
            return _wrap_like(target, data[:0, :0] if data.dtype != object else np.empty((0, 0), dtype=object))
        if sub.size and sub.max() >= r * c:
            raise index_exceeds(r * c)
        keep = np.setdiff1d(np.arange(r * c), sub)
        flat = data.ravel(order="F")[keep]
        res = flat.reshape(-1, 1) if c == 1 and r > 1 else flat.reshape(1, -1)
        return _wrap_like(target, res)
    si = _subs(args[0], r, 1)
    sj = _subs(args[1], c, 2)
    if isinstance(si, slice) or (not isinstance(si, slice) and set(si.tolist()) >= set(range(r)) and r > 0):
        cols = np.arange(c) if isinstance(sj, slice) else sj
        keep = np.setdiff1d(np.arange(c), cols)
        return _wrap_like(target, data[:, keep])
    if isinstance(sj, slice) or (set(sj.tolist()) >= set(range(c)) and c > 0):
        keep = np.setdiff1d(np.arange(r), si)
        return _wrap_like(target, data[keep, :])
    raise MatlabError("A null assignment can have only one non-colon index.", "MATLAB:nullAssignmentNonColon")


def end_value(v: Any, position: int, nargs: int) -> int:
    r, c = shape_of(v)
    if nargs == 1:
        return r * c
    if position == 0:
        return r
    if position == 1:
        return c if nargs == 2 else c
    return 1


def ensure_numel_for_cs(values: list[Any]) -> Any:
    return values
