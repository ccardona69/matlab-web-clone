"""Builtins matemáticos elementales, reducciones, orden, búsqueda y conjuntos."""

from __future__ import annotations

import itertools
import math
from typing import Any, Callable

import numpy as np

from backend.matlab import ops
from backend.matlab.errors import MatlabError
from backend.matlab.registry import (
    builtin, bool_arr, codes_to_char, dbl, default_dim, dim_arg, ival, is_text, nargchk, num,
    real, string_list, text, tidy,
)
from backend.matlab.values import (
    INT_TYPES, MCell, MString, as2d, class_of, empty_double, is_char, numel, saturate_int,
    to_double,
)


def restore_class(result: np.ndarray, cls: str) -> np.ndarray:
    if cls in INT_TYPES:
        return saturate_int(result, cls)
    if cls == "single":
        return result.astype(np.float32)
    return result


def _unary(names: tuple[str, ...], fn: Callable[[np.ndarray], np.ndarray],
           complex_when: Callable[[np.ndarray], np.ndarray] | None = None,
           keeps_class: bool = False) -> None:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        cls = class_of(args[0])
        if not keeps_class and cls in ("char", "string"):
            # Capturado de MATLAB R2026b: sqrt/exp/log/sin rechazan char; abs/sign/floor... lo aceptan
            raise MatlabError("Invalid data type. Argument must be double or single.", "MATLAB:math:mustBeFloat")
        a = dbl(args[0])
        if complex_when is not None and not np.iscomplexobj(a) and np.any(complex_when(a.real)):
            a = a.astype(complex)
        with np.errstate(all="ignore"):
            r = fn(a)
        if keeps_class:
            return restore_class(as2d(np.asarray(r)), cls)
        return tidy(as2d(np.asarray(r)))
    builtin(*names)(body)


_unary(("abs",), lambda a: np.abs(a), keeps_class=True)
_unary(("sign",), lambda a: np.sign(np.real(a)), keeps_class=True)
_unary(("sqrt",), np.sqrt, complex_when=lambda a: a < 0)
_unary(("exp",), np.exp)
_unary(("log",), np.log, complex_when=lambda a: a < 0)
_unary(("log2",), np.log2, complex_when=lambda a: a < 0)
_unary(("log10",), np.log10, complex_when=lambda a: a < 0)
_unary(("log1p",), np.log1p, complex_when=lambda a: a < -1)
_unary(("expm1",), np.expm1)
_unary(("sin",), np.sin)
_unary(("cos",), np.cos)
_unary(("tan",), np.tan)
_unary(("asin",), np.arcsin, complex_when=lambda a: np.abs(a) > 1)
_unary(("acos",), np.arccos, complex_when=lambda a: np.abs(a) > 1)
_unary(("atan",), np.arctan)
_unary(("sinh",), np.sinh)
_unary(("cosh",), np.cosh)
_unary(("tanh",), np.tanh)
_unary(("asinh",), np.arcsinh)
_unary(("acosh",), np.arccosh, complex_when=lambda a: a < 1)
_unary(("atanh",), np.arctanh, complex_when=lambda a: np.abs(a) > 1)
_unary(("sec",), lambda a: 1 / np.cos(a))
_unary(("csc",), lambda a: 1 / np.sin(a))
_unary(("cot",), lambda a: 1 / np.tan(a))
_unary(("sind",), lambda a: np.sin(np.deg2rad(a)))
_unary(("cosd",), lambda a: np.cos(np.deg2rad(a)))
_unary(("tand",), lambda a: np.tan(np.deg2rad(a)))
_unary(("deg2rad",), np.deg2rad)
_unary(("rad2deg",), np.rad2deg)
_unary(("floor",), np.floor, keeps_class=True)
_unary(("ceil",), np.ceil, keeps_class=True)
_unary(("fix",), np.trunc, keeps_class=True)
_unary(("real",), lambda a: np.real(a))
_unary(("imag",), lambda a: np.imag(a))
_unary(("conj",), lambda a: np.conj(a))
_unary(("angle", "arg"), lambda a: np.angle(a))


def round_half_away(a: np.ndarray) -> np.ndarray:
    return np.sign(a) * np.floor(np.abs(a) + 0.5)


@builtin("round")
def bi_round(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    cls = class_of(args[0])
    a = dbl(args[0])
    if len(args) == 2:
        scale = 10.0 ** ival(args[1])
        return restore_class(round_half_away(a * scale) / scale, cls)
    return restore_class(as2d(round_half_away(a)), cls)


@builtin("complex")
def bi_complex(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    re_part = real(args[0])
    im_part = real(args[1]) if len(args) > 1 else np.zeros_like(re_part)
    return re_part + 1j * im_part


def _binary(names: tuple[str, ...], fn: Callable[[np.ndarray, np.ndarray], np.ndarray]) -> None:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 2, 2)
        cls = _pick_class(args[0], args[1])
        x, y = np.broadcast_arrays(as2d(dbl(args[0])), as2d(dbl(args[1])))
        with np.errstate(all="ignore"):
            r = fn(x, y)
        return restore_class(tidy(as2d(np.asarray(r))), cls)
    builtin(*names)(body)


def _pick_class(a: Any, b: Any) -> str:
    for v in (a, b):
        if class_of(v) in INT_TYPES:
            return class_of(v)
    return "double"


def _mod(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x, y = np.real(x).astype(float), np.real(y).astype(float)
    r = x - np.floor(x / np.where(y == 0, 1, y)) * y
    return np.where(y == 0, x, r)


def _rem(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x, y = np.real(x).astype(float), np.real(y).astype(float)
    r = x - np.trunc(x / np.where(y == 0, 1, y)) * y
    return np.where(y == 0, np.nan, r)


_binary(("mod",), _mod)
_binary(("rem",), _rem)
_binary(("atan2",), np.arctan2)
_binary(("hypot",), np.hypot)
_binary(("power", "realpow"), lambda x, y: np.power(x.astype(complex) if np.iscomplexobj(x) or np.any(x < 0) else x, y))
_binary(("nthroot",), lambda x, n: np.where(x < 0, -np.power(-x, 1 / n), np.power(x, 1 / n)))


def _operator_alias(names: tuple[str, ...], op: str) -> None:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 2, 2)
        return ops.binop(op, args[0], args[1])
    builtin(*names)(body)


_operator_alias(("plus",), "+")
_operator_alias(("minus",), "-")
_operator_alias(("times",), ".*")
_operator_alias(("mtimes",), "*")
_operator_alias(("rdivide",), "./")
_operator_alias(("ldivide",), ".\\")
_operator_alias(("mrdivide",), "/")
_operator_alias(("mldivide",), "\\")
_operator_alias(("mpower",), "^")


def _int_binary(names: tuple[str, ...], fn: Callable[[np.ndarray, np.ndarray], np.ndarray]) -> None:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 2, 2)
        x, y = np.broadcast_arrays(as2d(to_double(args[0])), as2d(to_double(args[1])))
        out = tidy(as2d(np.asarray(fn(np.real(x).astype(np.int64), np.real(y).astype(np.int64)))))
        int_cls = next((class_of(a) for a in args[:2] if class_of(a) in INT_TYPES), None)
        if int_cls is None:
            return out.astype(float)
        return out.astype(INT_TYPES[int_cls])
    builtin(*names)(body)


_int_binary(("gcd",), np.gcd)
_int_binary(("lcm",), np.lcm)


@builtin("factorial")
def bi_factorial(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = real(args[0])
    if np.any(a < 0) or np.any(a != np.floor(a)):
        raise MatlabError("Input must be a non-negative integer.")
    return np.vectorize(lambda v: float(math.factorial(int(v))) if v <= 170 else math.inf, otypes=[float])(a)


@builtin("nchoosek")
def bi_nchoosek(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    n_arg, k = args[0], ival(args[1])
    if numel(n_arg) == 1:
        n = ival(n_arg)
        if n < 0 or k < 0 or k > n:
            return 0.0
        return float(math.comb(n, k))
    items = real(n_arg).ravel()
    combos = list(itertools.combinations(items, k))
    if not combos:
        return np.zeros((0, k))
    return np.array(combos, dtype=float)


def _is_prime_scalar(v: float) -> bool:
    if v < 2 or v != math.floor(v):
        return False
    n = int(v)
    if n < 4:
        return True
    if n % 2 == 0:
        return False
    for d in range(3, int(math.isqrt(n)) + 1, 2):
        if n % d == 0:
            return False
    return True


@builtin("isprime")
def bi_isprime(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = real(args[0])
    return bool_arr(np.vectorize(_is_prime_scalar, otypes=[bool])(a) if a.size else np.zeros(a.shape, bool))


@builtin("primes")
def bi_primes(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    n = int(num(args[0]))
    if n < 2:
        return np.zeros((1, 0))
    sieve = np.ones(n + 1, dtype=bool)
    sieve[:2] = False
    for p in range(2, math.isqrt(n) + 1):
        if sieve[p]:
            sieve[p * p::p] = False
    return np.flatnonzero(sieve).astype(float).reshape(1, -1)


@builtin("factor")
def bi_factor(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    n = int(num(args[0]))
    if n < 1:
        raise MatlabError("Input must be a positive integer.")
    factors: list[float] = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(float(d))
            n //= d
        d += 1
    if n > 1 or not factors:
        factors.append(float(n))
    return np.array([factors])


# ---------- reducciones ----------

def _reduce_setup(args: list[Any], start: int = 1) -> tuple[np.ndarray, int | None, bool]:
    """Devuelve (datos, dimensión o None, es 'all')."""
    a = dbl(args[0])
    if len(args) > start and is_text(args[start]) and text(args[start]).lower() == "all":
        return a.reshape(-1, 1), 0, True
    dim = None
    if len(args) > start and not (isinstance(args[start], np.ndarray) and args[start].size == 0):
        dim = dim_arg(args[start])
    return a, dim, False


def _along(a: np.ndarray, d: int, fn: Callable[..., np.ndarray]) -> np.ndarray:
    if d >= 2:
        return fn(a[:, :, np.newaxis], axis=2, keepdims=True)[:, :, 0]
    return fn(a, axis=d, keepdims=True)


def _reduce(a: np.ndarray, dim: int | None, fn: Callable[..., np.ndarray], empty: float | None) -> np.ndarray:
    if dim is None and a.shape == (0, 0):
        return np.array([[empty if empty is not None else 0.0]])
    d = default_dim(a) if dim is None else dim
    with np.errstate(all="ignore"):
        return as2d(_along(a, d, fn))


def _sum_like(names: tuple[str, ...], fn: Callable[..., np.ndarray], empty: float) -> None:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 3)
        cls = class_of(args[0])
        a, dim, _ = _reduce_setup(args)
        r = _reduce(a, dim, fn, empty)
        return restore_class(r, cls if cls in INT_TYPES or cls == "single" else "double")
    builtin(*names)(body)


_sum_like(("sum",), np.sum, 0.0)
_sum_like(("prod",), np.prod, 1.0)
_sum_like(("mean", "average"), np.mean, float("nan"))
_sum_like(("median",), np.median, float("nan"))


@builtin("mode")
def bi_mode(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a, dim, _ = _reduce_setup(args)
    if a.shape == (0, 0):
        return np.array([[float("nan")]])
    d = default_dim(a) if dim is None else dim
    moved = np.moveaxis(a, d, 0)
    flat = moved.reshape(moved.shape[0], -1)
    modes = []
    for col in flat.T:
        vals, counts = np.unique(col, return_counts=True)
        modes.append(vals[np.argmax(counts)])
    out = np.array(modes).reshape((1,) + moved.shape[1:])
    return as2d(np.moveaxis(out, 0, d))


def _spread(names: tuple[str, ...], ddof_default: int) -> None:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 3)
        a = dbl(args[0])
        weight = 0
        if len(args) > 1 and not (isinstance(args[1], np.ndarray) and args[1].size == 0):
            weight = ival(args[1])
        dim = dim_arg(args[2]) if len(args) > 2 else None
        ddof = 1 if weight == 0 else 0
        n_along = a.shape[default_dim(a) if dim is None else dim] if a.size else 0
        d = default_dim(a) if dim is None else dim
        if a.shape == (0, 0):
            return np.array([[float("nan")]])
        with np.errstate(all="ignore"):
            if names[0] == "std":
                r = _along(a, d, lambda x, axis, keepdims: np.std(x, axis=axis, ddof=ddof, keepdims=keepdims))
            else:
                r = _along(a, d, lambda x, axis, keepdims: np.var(x, axis=axis, ddof=ddof, keepdims=keepdims))
        if n_along == 1:
            r = np.zeros_like(r)
        return as2d(r)
    builtin(*names)(body)


_spread(("std",), 1)
_spread(("var",), 1)


def _cumulative(names: tuple[str, ...], fn: Callable[..., np.ndarray]) -> None:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 2)
        a = dbl(args[0])
        d = dim_arg(args[1]) if len(args) > 1 else default_dim(a)
        return as2d(fn(a, axis=d))
    builtin(*names)(body)


_cumulative(("cumsum",), np.cumsum)
_cumulative(("cumprod",), np.cumprod)
_cumulative(("cummax",), np.maximum.accumulate)
_cumulative(("cummin",), np.minimum.accumulate)


@builtin("diff")
def bi_diff(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 3)
    a = dbl(args[0])
    order = ival(args[1]) if len(args) > 1 and args[1].size else 1
    d = dim_arg(args[2]) if len(args) > 2 else default_dim(a)
    if order >= a.shape[d]:
        return np.zeros((0, a.shape[1]) if d == 0 else (a.shape[0], 0))
    return as2d(np.diff(a, n=order, axis=d))


# ---------- máximo y mínimo ----------

def _extreme(a: np.ndarray, d: int, is_max: bool) -> tuple[np.ndarray, np.ndarray]:
    x = np.real(a).astype(float) if not np.iscomplexobj(a) else np.abs(a)
    fill = -np.inf if is_max else np.inf
    keyed = np.where(np.isnan(x), fill, x)
    idx = np.argmax(keyed, axis=d) if is_max else np.argmin(keyed, axis=d)
    idx_e = np.expand_dims(idx, d)
    vals = np.take_along_axis(x, idx_e, axis=d)
    return as2d(vals), as2d(idx_e.astype(float) + 1)


def _extremum(is_max: bool) -> Callable[..., Any]:
    name = "max" if is_max else "min"

    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 3)
        cls = class_of(args[0])
        if len(args) == 2:
            x, y = np.broadcast_arrays(as2d(dbl(args[0])), as2d(dbl(args[1])))
            r = np.fmax(x, y) if is_max else np.fmin(x, y)
            return restore_class(as2d(r), _pick_class(args[0], args[1]))
        a = dbl(args[0])
        if len(args) == 3 and not (isinstance(args[1], np.ndarray) and args[1].size == 0):
            raise MatlabError(f"Second argument must be empty when computing {name} along a dimension.")
        if a.size == 0:
            return [empty_double(), empty_double()] if nargout >= 2 else empty_double()
        if len(args) == 3 and text_all(args[2]):
            a = a.reshape(-1, 1)
            d = 0
        else:
            d = dim_arg(args[2]) if len(args) == 3 else default_dim(a)
        vals, idx = _extreme(a, d, is_max)
        vals = restore_class(vals, cls if cls in INT_TYPES or cls == "single" else "double")
        return [vals, idx] if nargout >= 2 else vals
    body.__name__ = name
    return body


def text_all(v: Any) -> bool:
    return is_text(v) and text(v).lower() == "all"


builtin("max")(_extremum(True))
builtin("min")(_extremum(False))


def _logical_reduce(names: tuple[str, ...], fn: Callable[..., np.ndarray], empty: bool) -> None:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 2)
        a = dbl(args[0])
        mask = (a != 0).astype(float)
        if len(args) == 2 and text_all(args[1]):
            mask = mask.reshape(-1, 1)
            return np.array([[bool(fn(mask, axis=0, keepdims=True).ravel()[0])]])
        if a.shape == (0, 0):
            return np.array([[empty]])
        dim = dim_arg(args[1]) if len(args) == 2 else default_dim(a)
        return bool_arr(_along(mask, dim, fn))
    builtin(*names)(body)


_logical_reduce(("any",), np.any, False)
_logical_reduce(("all",), np.all, True)


@builtin("find")
def bi_find(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 3)
    a = dbl(args[0])
    flat = np.flatnonzero((a != 0).ravel(order="F"))
    if len(args) >= 2:
        k = ival(args[1])
        direction = text(args[2]).lower() if len(args) == 3 else "first"
        flat = flat[-k:] if direction == "last" and k > 0 else flat[:k]
    rows = a.shape[0]
    row_result = rows == 1 and a.shape[1] != 1 or (a.size == 1 and rows == 1)

    def shaped(vec: np.ndarray) -> np.ndarray:
        if vec.size == 0:
            return np.zeros((1, 0)) if row_result else np.zeros((0, 1))
        return vec.reshape(1, -1) if row_result else vec.reshape(-1, 1)

    if nargout <= 1:
        return shaped(flat.astype(float) + 1)
    r_idx = (flat % rows).astype(float) + 1
    c_idx = (flat // rows).astype(float) + 1
    if nargout == 2:
        return [shaped(r_idx), shaped(c_idx)]
    vals = a.ravel(order="F")[flat]
    return [shaped(r_idx), shaped(c_idx), shaped(vals)]


# ---------- orden ----------

@builtin("sort")
def bi_sort(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 3)
    desc = any(is_text(a) and text(a).lower() == "descend" for a in args[1:])
    dim_given = [a for a in args[1:] if not is_text(a)]
    if isinstance(args[0], MCell):
        items = string_list(args[0])
        order = sorted(range(len(items)), key=lambda i: items[i], reverse=desc)
        cell_data = args[0].data.ravel(order="F")
        out = np.empty(len(order), dtype=object)
        for pos, i in enumerate(order):
            out[pos] = cell_data[i]
        shaped = out.reshape(args[0].data.shape, order="F")
        idx = np.array(order, dtype=float).reshape(args[0].data.shape, order="F") + 1
        return [MCell(shaped), as2d(idx)] if nargout >= 2 else MCell(shaped)
    x = args[0]
    a = real(x)
    d = dim_arg(dim_given[0]) if dim_given else default_dim(a)
    keyed = -a if desc else a
    idx = np.argsort(keyed, axis=d, kind="stable")
    s = np.take_along_axis(a, idx, axis=d)
    if is_char(x):
        out = codes_to_char(s)
    elif class_of(x) == "logical":
        out = s.astype(bool)
    else:
        out = restore_class(s, class_of(x))
    return [out, as2d(idx.astype(float) + 1)] if nargout >= 2 else out


@builtin("sortrows")
def bi_sortrows(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    data = as2d(to_double(args[0]))
    cols = list(range(1, data.shape[1] + 1)) if len(args) < 2 else [int(v) for v in real(args[1]).ravel()]
    keys = [np.real(data[:, abs(c) - 1]) * (-1 if c < 0 else 1) for c in cols]
    idx = np.lexsort(keys[::-1])
    out = data[idx]
    return [out, _col(list(idx.astype(float) + 1))] if nargout >= 2 else out


# ---------- conjuntos y búsqueda ----------

@builtin("unique")
def bi_unique(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 3)
    opts = [text(a).lower() for a in args[1:] if is_text(a)]
    stable = "stable" in opts
    last = "last" in opts
    if isinstance(args[0], MCell):
        row = args[0].data.shape[0] == 1
        uniq, ia, ic = _unique_keys(string_list(args[0]), stable, last)
        out_cell = _cell_column_or_row(uniq, row) if uniq else MCell(np.empty((0, 0), dtype=object))
        return [out_cell, _col(ia), _col(ic)] if nargout >= 2 else out_cell
    a = as2d(args[0]) if is_char(args[0]) else dbl(args[0])
    row = a.shape[0] == 1
    flat = a.ravel(order="F").tolist()
    uniq, ia, ic = _unique_keys(flat, stable, last)
    values = np.array(uniq, dtype=a.dtype).reshape(-1, 1)
    values = values.reshape(1, -1) if row else values
    if nargout >= 2:
        return [values, _col(ia), _col(ic)]
    return values


def _unique_keys(items: list[Any], stable: bool, last: bool) -> tuple[list[Any], list[float], list[float]]:
    order_first: dict[Any, int] = {}
    order_last: dict[Any, int] = {}
    for pos, v in enumerate(items):
        order_first.setdefault(v, pos)
        order_last[v] = pos
    keys = list(order_first.keys())
    if not stable:
        keys = sorted(keys)
    position = {k: i for i, k in enumerate(keys)}
    pick = order_last if last else order_first
    ia = [float(pick[k] + 1) for k in keys]
    ic = [float(position[v] + 1) for v in items]
    return keys, ia, ic


def _col(values: list[float]) -> np.ndarray:
    return np.array(values, dtype=float).reshape(-1, 1)


def _cell_column_or_row(items: list[str], row: bool) -> MCell:
    from backend.matlab.registry import cellstr_of
    return cellstr_of(items, column=not row)


@builtin("ismember")
def bi_ismember(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    s_arg = args[1]
    if isinstance(s_arg, MCell) or (isinstance(args[0], (MCell, MString)) and not isinstance(args[0], np.ndarray)):
        pool = string_list(s_arg)
        if isinstance(args[0], MCell):
            queries = string_list(args[0])
            shape = args[0].data.shape
        else:
            queries = [text(args[0])]
            shape = (1, 1)
        lookup = {}
        for pos, s in enumerate(pool):
            lookup.setdefault(s, pos + 1)
        tf = np.array([q in lookup for q in queries], dtype=bool).reshape(shape, order="F")
        loc = np.array([float(lookup.get(q, 0)) for q in queries]).reshape(shape, order="F")
        return [bool_arr(tf), as2d(loc)] if nargout >= 2 else bool_arr(tf)
    a = dbl(args[0]) if not is_char(args[0]) else as2d(args[0]).astype(object)
    pool_arr = real(s_arg).ravel(order="F") if not is_char(s_arg) else np.array(list(as2d(s_arg).ravel()), dtype=object)
    lookup = {}
    for pos, v in enumerate(pool_arr.tolist()):
        lookup.setdefault(v, pos + 1)
    flat = a.ravel(order="F").tolist()
    tf = np.array([v in lookup for v in flat], dtype=bool).reshape(a.shape, order="F")
    loc = np.array([float(lookup.get(v, 0)) for v in flat]).reshape(a.shape, order="F")
    return [bool_arr(tf), as2d(loc)] if nargout >= 2 else bool_arr(tf)


@builtin("histcounts")
def bi_histcounts(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    x = real(args[0]).ravel()
    bins: Any = 10
    if len(args) == 2:
        bins = real(args[1]).ravel() if real(args[1]).size > 1 else ival(args[1])
    counts, edges = np.histogram(x, bins=bins)
    return [as2d(counts.astype(float)), as2d(edges.astype(float))] if nargout >= 2 else as2d(counts.astype(float))


def _trapezoid(y: np.ndarray, x: np.ndarray | None, axis: int) -> np.ndarray:
    fn = getattr(np, "trapezoid", None) or np.trapz
    return fn(y, x=x, axis=axis)


@builtin("trapz")
def bi_trapz(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    if len(args) == 1:
        y = dbl(args[0])
        return as2d(_trapezoid(y, None, default_dim(y)))
    x, y = real(args[0]).ravel(), dbl(args[1])
    return as2d(_trapezoid(y, x, default_dim(y)))


@builtin("cumtrapz")
def bi_cumtrapz(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    y = dbl(args[-1]).astype(float)
    x = real(args[0]).ravel() if len(args) == 2 else np.arange(y.size if y.shape[0] == 1 else y.shape[0], dtype=float)
    d = default_dim(y)
    yv = np.moveaxis(y, d, 0)
    dx = np.diff(x)
    seg = (yv[1:] + yv[:-1]) / 2 * dx.reshape((-1,) + (1,) * (yv.ndim - 1))
    out = np.concatenate([np.zeros((1,) + yv.shape[1:]), np.cumsum(seg, axis=0)], axis=0)
    return as2d(np.moveaxis(out, 0, d))


@builtin("dot")
def bi_dot(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    a, b = dbl(args[0]), dbl(args[1])
    if a.size != b.size:
        raise MatlabError("Vectors must be the same length.")
    if a.shape[0] == 1 or a.shape[1] == 1:
        return float(np.sum(np.conj(a.ravel()) * b.ravel()))
    return as2d(np.sum(np.conj(a) * b, axis=0, keepdims=True))


@builtin("cross")
def bi_cross(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    a, b = dbl(args[0]), dbl(args[1])
    if a.size != 3 or b.size != 3:
        raise MatlabError("CROSS requires 3-element vectors in this clon.")
    return np.cross(a.ravel(), b.ravel()).reshape(a.shape)


@builtin("norm")
def bi_norm(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = dbl(args[0]).astype(complex if np.iscomplexobj(args[0]) else float)
    order: Any = 2
    if len(args) == 2:
        if is_text(args[1]):
            label = text(args[1]).lower()
            order = "fro" if label == "fro" else math.inf
        else:
            order = num(args[1])
            if math.isinf(order):
                order = math.inf
    if isinstance(order, str) and (a.shape[0] == 1 or a.shape[1] == 1):
        order = 2
    if a.size == 0:
        return 0.0
    return float(np.linalg.norm(a, ord=order))


