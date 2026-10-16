"""Builtins núcleo: constantes, construcción de arreglos, tamaño, tipos y conversiones.

Los demás módulos `library_*.py` se registran en el mismo `BUILTINS` al importarse.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.matlab import ops
from backend.matlab.errors import MatlabError
from backend.matlab.registry import (
    BUILTINS, builtin, bool_arr, cast_array, codes_to_char, default_dim, dim_arg, dtype_of, ival,
    is_text, nargchk, num, real, text, tidy,
)
from backend.matlab.values import (
    INT_TYPES, MCell, MFunc, MString, MStruct, as2d, class_of, empty_double, is_char, numel,
    shape_of, to_double,
)

__all__ = ["BUILTINS"]

FLOAT_CLASSES = ("double", "single")


def wrap_like(v: Any, data: np.ndarray) -> Any:
    if isinstance(v, MCell):
        return MCell(data)
    if isinstance(v, MString):
        return MString(data)
    if isinstance(v, MStruct):
        return MStruct(v.fields, data)
    return data


def size_args(args: list[Any]) -> tuple[tuple[int, int], str]:
    """Interpreta (n), (m,n), ([m n]) y un nombre de clase final."""
    vals = list(args)
    cls = "double"
    if vals and is_text(vals[-1]):
        cls = text(vals.pop())
        if cls == "like":
            raise MatlabError("'like' is not supported by this clon.")
    if not vals:
        return (1, 1), cls
    if len(vals) == 1:
        dims = real(vals[0]).ravel()
        if dims.size == 0:
            return (0, 0), cls
        r = dims[0]
        c = dims[1] if dims.size > 1 else dims[0]
    else:
        r, c = real(vals[0]).ravel()[0], real(vals[1]).ravel()[0]
    return (max(int(np.nan_to_num(r)), 0), max(int(np.nan_to_num(c)), 0)), cls


def filled(args: list[Any], value: Any) -> np.ndarray:
    shape, cls = size_args(args)
    if cls == "char":
        return np.full(shape, chr(int(value)), dtype="<U1")
    return np.full(shape, value, dtype=dtype_of(cls))


def _const(value: float) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        if not args:
            return value
        return filled(args, value)
    return fn


def _register_constant(names: tuple[str, ...], value: float) -> None:
    builtin(*names)(_const(value))


_register_constant(("pi",), float(np.pi))
_register_constant(("Inf", "inf"), float("inf"))
_register_constant(("NaN", "nan"), float("nan"))
_register_constant(("realmax",), float(np.finfo(float).max))
_register_constant(("realmin",), float(np.finfo(float).tiny))
_register_constant(("flintmax",), 2.0 ** 53)


@builtin("eps")
def bi_eps(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        return float(np.finfo(float).eps)
    if is_text(args[0]):
        return float(np.finfo(np.float32).eps) if text(args[0]) == "single" else float(np.finfo(float).eps)
    return np.spacing(np.abs(real(args[0])))


@builtin("i", "j", "I", "J")
def bi_imag_unit(I: Any, args: list[Any], nargout: int) -> Any:
    return 1j


@builtin("true")
def bi_true(I: Any, args: list[Any], nargout: int) -> Any:
    return filled(args, True) if args else np.array([[True]])


@builtin("false")
def bi_false(I: Any, args: list[Any], nargout: int) -> Any:
    return filled(args, False) if args else np.array([[False]])


def _int_limit(upper: bool) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 0, 1)
        cls = "int32"
        if args:
            cls = class_of(args[0]) if not is_text(args[0]) else text(args[0])
        if cls not in INT_TYPES:
            raise MatlabError(f"Unrecognized numeric class name '{cls}'.")
        info = np.iinfo(INT_TYPES[cls])
        return np.array([[info.max if upper else info.min]], dtype=INT_TYPES[cls])
    return fn


builtin("intmax")(_int_limit(True))
builtin("intmin")(_int_limit(False))


# ---------- construcción ----------

@builtin("zeros")
def bi_zeros(I: Any, args: list[Any], nargout: int) -> Any:
    return filled(args, 0)


@builtin("ones")
def bi_ones(I: Any, args: list[Any], nargout: int) -> Any:
    return filled(args, 1)


@builtin("eye")
def bi_eye(I: Any, args: list[Any], nargout: int) -> Any:
    shape, cls = size_args(args)
    return cast_array(np.eye(*shape), cls)


@builtin("rand")
def bi_rand(I: Any, args: list[Any], nargout: int) -> Any:
    shape, _ = size_args(args)
    return I.rng.random(shape)


@builtin("randn")
def bi_randn(I: Any, args: list[Any], nargout: int) -> Any:
    shape, _ = size_args(args)
    return I.rng.standard_normal(shape)


@builtin("randi")
def bi_randi(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    lims = real(args[0]).ravel()
    lo, hi = (1, int(lims[0])) if lims.size == 1 else (int(lims[0]), int(lims[1]))
    if hi < lo:
        raise MatlabError("Upper bound must be greater than or equal to the lower bound.")
    shape, _ = size_args(args[1:])
    return I.rng.integers(lo, hi + 1, size=shape).astype(float)


@builtin("rng")
def bi_rng(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        return None
    arg = args[0]
    if is_text(arg):
        mode = text(arg).lower()
        if mode in ("default", "shuffle"):
            I.rng = np.random.default_rng(0 if mode == "default" else None)
            return None
        raise MatlabError(f"Invalid argument for rng: '{text(arg)}'.")
    I.rng = np.random.default_rng(ival(arg))
    return None


@builtin("linspace")
def bi_linspace(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    n = ival(args[2]) if len(args) == 3 else 100
    return np.linspace(num(args[0]), num(args[1]), max(n, 1)).reshape(1, -1)


@builtin("logspace")
def bi_logspace(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    n = ival(args[2]) if len(args) == 3 else 50
    return np.logspace(num(args[0]), num(args[1]), n).reshape(1, -1)


def magic_square(n: int) -> np.ndarray:
    if n < 1:
        return np.zeros((0, 0))
    if n == 2:
        return np.array([[4.0, 3.0], [1.0, 2.0]])
    if n % 2 == 1:
        k = np.arange(n * n)
        shift = k // n
        c = np.mod(k + 1 - shift + (n - 3) // 2, n)
        r = np.mod(n * n - k + 2 * shift, n)
        lin = np.zeros(n * n)
        lin[c * n + r] = k + 1
        return lin.reshape((n, n), order="F")
    if n % 4 == 0:
        a = np.arange(1, n * n + 1, dtype=float).reshape(n, n)
        for group in ([*range(1, n + 1, 4), *range(4, n + 1, 4)], [*range(2, n + 1, 4), *range(3, n + 1, 4)]):
            idx = np.array(group) - 1
            ix = np.ix_(idx, idx[::-1])
            a[ix] = (n * n + 1) - a[ix]
        return a
    m = n // 2
    a = magic_square(m)
    a = np.block([[a, a + 2 * m * m], [a + 3 * m * m, a + m * m]])
    k = (m - 1) // 2
    if k > 1:
        i_idx = np.arange(1, m + 1)
        j_idx = np.array([*range(2, k + 1), *range(n - k + 2, n + 1)])
        _swap_rows(a, i_idx, j_idx, m)
    i_idx = np.array([*range(1, k + 1), *range(k + 2, m + 1)])
    _swap_rows(a, i_idx, np.array([1]), m)
    i_idx = np.array([k + 1])
    _swap_rows(a, i_idx, i_idx, m)
    return a


def _swap_rows(a: np.ndarray, i_idx: np.ndarray, j_idx: np.ndarray, m: int) -> None:
    top = np.concatenate([i_idx, i_idx + m]) - 1
    bottom = np.concatenate([i_idx + m, i_idx]) - 1
    cols = j_idx - 1
    a[np.ix_(top, cols)] = a[np.ix_(bottom, cols)].copy()


@builtin("magic")
def bi_magic(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return magic_square(ival(args[0]))


@builtin("meshgrid")
def bi_meshgrid(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 3)
    if len(args) == 3:
        raise MatlabError("3-D meshgrid is not supported by this clon.")
    x = real(args[0]).ravel()
    y = real(args[1]).ravel() if len(args) > 1 else x
    xx, yy = np.meshgrid(x, y)
    return [xx, yy]


@builtin("ndgrid")
def bi_ndgrid(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    x = real(args[0]).ravel()
    y = real(args[1]).ravel() if len(args) > 1 else x
    xx, yy = np.meshgrid(x, y, indexing="ij")
    return [xx, yy]


@builtin("repmat")
def bi_repmat(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    v = args[0]
    if len(args) == 2:
        reps = real(args[1]).ravel()
        m, n = (int(reps[0]), int(reps[0])) if reps.size == 1 else (int(reps[0]), int(reps[1]))
    else:
        m, n = ival(args[1]), ival(args[2])
    data = as2d(v.data) if isinstance(v, (MCell, MString, MStruct)) else as2d(v)
    return wrap_like(v, np.tile(data, (max(m, 0), max(n, 0))))


@builtin("reshape")
def bi_reshape(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    v = args[0]
    data = v.data if isinstance(v, (MCell, MString, MStruct)) else as2d(v)
    total = data.size
    if len(args) == 2:
        dims = [int(x) for x in real(args[1]).ravel()]
    else:
        dims = [None if (isinstance(a, np.ndarray) and a.size == 0) else ival(a) for a in args[1:]]
    if dims.count(None) > 1:
        raise MatlabError("Only one dimension can be unknown.")
    known = int(np.prod([d for d in dims if d is not None])) if any(d is not None for d in dims) else 1
    if None in dims:
        if known == 0 or total % known:
            raise MatlabError("To RESHAPE the number of elements must not change.")
        dims[dims.index(None)] = total // known
    if int(np.prod(dims)) != total:
        raise MatlabError("To RESHAPE the number of elements must not change.")
    while len(dims) > 2 and dims[-1] == 1:
        dims.pop()
    shape = (dims[0], int(np.prod(dims[1:])))
    return wrap_like(v, data.ravel(order="F").reshape(shape, order="F"))


@builtin("cat")
def bi_cat(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    dim = ival(args[0])
    items = list(args[1:])
    if dim == 1:
        return ops.concat([[v] for v in items])
    if dim == 2:
        return ops.concat([items])
    raise MatlabError("N-D concatenation is not supported by this clon.")


@builtin("horzcat")
def bi_horzcat(I: Any, args: list[Any], nargout: int) -> Any:
    return ops.concat([list(args)]) if args else empty_double()


@builtin("vertcat")
def bi_vertcat(I: Any, args: list[Any], nargout: int) -> Any:
    return ops.concat([[v] for v in args]) if args else empty_double()


@builtin("diag")
def bi_diag(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    k = ival(args[1]) if len(args) > 1 else 0
    a = as2d(args[0])
    if a.shape[0] == 1 or a.shape[1] == 1:
        return np.diag(a.ravel(), k)
    return np.diag(a, k).reshape(-1, 1)


@builtin("blkdiag")
def bi_blkdiag(I: Any, args: list[Any], nargout: int) -> Any:
    mats = [as2d(to_double(a)) for a in args]
    rows = sum(m.shape[0] for m in mats)
    cols = sum(m.shape[1] for m in mats)
    out = np.zeros((rows, cols), dtype=complex if any(np.iscomplexobj(m) for m in mats) else float)
    r = c = 0
    for m in mats:
        out[r:r + m.shape[0], c:c + m.shape[1]] = m
        r += m.shape[0]
        c += m.shape[1]
    return tidy(out)


@builtin("tril")
def bi_tril(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    return np.tril(as2d(to_double(args[0])), ival(args[1]) if len(args) > 1 else 0)


@builtin("triu")
def bi_triu(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    return np.triu(as2d(to_double(args[0])), ival(args[1]) if len(args) > 1 else 0)


@builtin("fliplr")
def bi_fliplr(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    v = args[0]
    return wrap_like(v, np.fliplr(v.data if isinstance(v, (MCell, MString, MStruct)) else as2d(v)))


@builtin("flipud")
def bi_flipud(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    v = args[0]
    return wrap_like(v, np.flipud(v.data if isinstance(v, (MCell, MString, MStruct)) else as2d(v)))


@builtin("flip")
def bi_flip(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    v = args[0]
    data = v.data if isinstance(v, (MCell, MString, MStruct)) else as2d(v)
    dim = dim_arg(args[1]) if len(args) > 1 else default_dim(data)
    return wrap_like(v, np.flip(data, axis=dim))


@builtin("rot90")
def bi_rot90(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    k = ival(args[1]) if len(args) > 1 else 1
    return np.rot90(as2d(to_double(args[0])), k)


@builtin("circshift")
def bi_circshift(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    v = args[0]
    data = v.data if isinstance(v, (MCell, MString, MStruct)) else as2d(v)
    shifts = real(args[1]).ravel().astype(int)
    if len(args) == 3:
        axes = [dim_arg(args[2])]
    elif shifts.size > 1:
        axes = [0, 1]
    else:
        axes = [default_dim(data)]
    if shifts.size == 1:
        shifts = np.repeat(shifts, len(axes))
    return wrap_like(v, np.roll(data, tuple(int(s) for s in shifts), axis=tuple(axes)))


@builtin("kron")
def bi_kron(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    return np.kron(as2d(to_double(args[0])), as2d(to_double(args[1])))


@builtin("colon")
def bi_colon(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    if len(args) == 2:
        return ops.colon_range(args[0], None, args[1])
    return ops.colon_range(args[0], args[1], args[2])


@builtin("peaks")
def bi_peaks(I: Any, args: list[Any], nargout: int) -> Any:
    if len(args) == 2:
        x, y = real(args[0]), real(args[1])
    else:
        n = ival(args[0]) if args else 49
        x, y = np.meshgrid(np.linspace(-3, 3, n), np.linspace(-3, 3, n))
    z = (3 * (1 - x) ** 2 * np.exp(-(x ** 2) - (y + 1) ** 2)
         - 10 * (x / 5 - x ** 3 - y ** 5) * np.exp(-x ** 2 - y ** 2)
         - np.exp(-(x + 1) ** 2 - y ** 2) / 3)
    if nargout >= 3:
        return [x, y, z]
    return z


# ---------- tamaño ----------

@builtin("size")
def bi_size(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    shape = shape_of(args[0])
    if len(args) == 2:
        d = ival(args[1])
        if d < 1:
            raise MatlabError("SIZE requires a positive dimension.")
        return float(shape[d - 1]) if d <= 2 else 1.0
    if nargout <= 1:
        return np.array([[float(shape[0]), float(shape[1])]])
    outs: list[Any] = [float(shape[0]), float(shape[1])]
    outs.extend([1.0] * (nargout - 2))
    return outs[:nargout]


@builtin("length")
def bi_length(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    r, c = shape_of(args[0])
    return float(0 if r * c == 0 else max(r, c))


@builtin("numel")
def bi_numel(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    return float(numel(args[0]))


@builtin("ndims")
def bi_ndims(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return 2.0


@builtin("isempty")
def bi_isempty(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return numel(args[0]) == 0


@builtin("isscalar")
def bi_isscalar(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return numel(args[0]) == 1


@builtin("isvector")
def bi_isvector(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    r, c = shape_of(args[0])
    return (r == 1 or c == 1) and r * c >= 1


@builtin("isrow")
def bi_isrow(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return shape_of(args[0])[0] == 1


@builtin("iscolumn")
def bi_iscolumn(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return shape_of(args[0])[1] == 1


@builtin("ismatrix")
def bi_ismatrix(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return True


@builtin("issquare")
def bi_issquare(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    r, c = shape_of(args[0])
    return r == c


# ---------- tipos ----------

@builtin("class")
def bi_class(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return class_of(args[0])


@builtin("isa")
def bi_isa(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    cls = class_of(args[0])
    want = text(args[1])
    if want == "numeric":
        return cls in INT_TYPES or cls in FLOAT_CLASSES
    if want == "float":
        return cls in FLOAT_CLASSES
    if want == "integer":
        return cls in INT_TYPES
    return cls == want


def _type_predicate(name: str, test: Any) -> None:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        return bool(test(args[0]))
    builtin(name)(fn)


_type_predicate("isnumeric", lambda v: isinstance(v, np.ndarray) and v.dtype.kind in "iufc")
_type_predicate("isfloat", lambda v: isinstance(v, np.ndarray) and class_of(v) in FLOAT_CLASSES)
_type_predicate("isinteger", lambda v: class_of(v) in INT_TYPES)
_type_predicate("islogical", lambda v: isinstance(v, np.ndarray) and v.dtype.kind == "b")
_type_predicate("isbool", lambda v: isinstance(v, np.ndarray) and v.dtype.kind == "b")
_type_predicate("ischar", is_char)
_type_predicate("iscell", lambda v: isinstance(v, MCell))
_type_predicate("isstruct", lambda v: isinstance(v, MStruct))
_type_predicate("isstring", lambda v: isinstance(v, MString))
_type_predicate("is_function_handle", lambda v: isinstance(v, MFunc))
_type_predicate("isreal", lambda v: isinstance(v, np.ndarray) and not np.iscomplexobj(v))
_type_predicate("iscellstr", lambda v: isinstance(v, MCell) and all(is_char(x) or x.size == 0 for x in v.data.ravel()))


def _elementwise_test(name: str, test: Any) -> None:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        v = args[0]
        if is_char(v):
            return np.zeros(as2d(v).shape, dtype=bool)
        if not isinstance(v, np.ndarray):
            raise MatlabError(f"{name} is not supported for {class_of(v)} inputs.")
        return bool_arr(test(as2d(to_double(v))))
    builtin(name)(fn)


_elementwise_test("isnan", np.isnan)
_elementwise_test("isinf", np.isinf)
_elementwise_test("isfinite", np.isfinite)


# ---------- conversiones ----------

def _to_class_array(v: Any, cls: str) -> np.ndarray:
    if isinstance(v, (MCell, MStruct, MFunc)):
        raise MatlabError(f"Conversion to {cls} from {class_of(v)} is not possible.", "MATLAB:invalidConversion")
    if isinstance(v, MString):
        v = np.array([[float(ord(c)) for c in v.scalar()]]) if v.data.size == 1 else v
    if cls == "logical":
        a = to_double(v)
        if np.any(np.isnan(np.real(a))):
            raise MatlabError("NaN can't be converted to logical value.", "MATLAB:unableToConvertNaN")
        return a != 0
    if cls == "char":
        return codes_to_char(to_double(v)) if not is_char(v) else as2d(v)
    return cast_array(as2d(to_double(v)), cls)


def _class_converter(cls: str) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1, 1)
        return _to_class_array(args[0], cls)
    return fn


for _cls in ("double", "single", "logical", *INT_TYPES):
    builtin(_cls)(_class_converter(_cls))


@builtin("cast")
def bi_cast(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    cls = text(args[1])
    if cls not in ("double", "single", "logical", "char", *INT_TYPES):
        raise MatlabError(f"Invalid data type specified: '{cls}'.")
    return _to_class_array(args[0], cls)


# ---------- igualdad ----------

def values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, MCell) or isinstance(b, MCell):
        if not (isinstance(a, MCell) and isinstance(b, MCell)) or a.data.shape != b.data.shape:
            return False
        return all(values_equal(x, y) for x, y in zip(a.data.ravel(order="F"), b.data.ravel(order="F")))
    if isinstance(a, MStruct) or isinstance(b, MStruct):
        if not (isinstance(a, MStruct) and isinstance(b, MStruct)) or a.data.shape != b.data.shape:
            return False
        if set(a.fields) != set(b.fields):
            return False
        return all(values_equal(x[f], y[f]) for x, y in zip(a.data.ravel(order="F"), b.data.ravel(order="F")) for f in a.fields)
    if isinstance(a, MFunc) or isinstance(b, MFunc):
        return a is b
    sa, sb = _as_text_or_num(a), _as_text_or_num(b)
    return sa.shape == sb.shape and bool(np.array_equal(sa, sb))


def _as_text_or_num(v: Any) -> np.ndarray:
    if isinstance(v, MString):
        return np.array(v.data.tolist(), dtype=object)
    return as2d(to_double(v))


@builtin("isequal")
def bi_isequal(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    return all(values_equal(args[0], other) for other in args[1:])


@builtin("isequaln")
def bi_isequaln(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    return all(values_equal(args[0], other) for other in args[1:])


from backend.matlab import (  # noqa: E402,F401
    library_cells, library_graphics, library_math, library_numerics, library_strings, library_system,
)
