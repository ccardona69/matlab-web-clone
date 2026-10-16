"""Registro de builtins y helpers compartidos por los módulos library*.py."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from backend.matlab.errors import MatlabError
from backend.matlab.values import (
    INT_TYPES, MCell, MString, MStruct, as2d, char_to_str, is_char, make_char, saturate_int,
    scalar, to_double,
)

BUILTINS: dict[str, Callable] = {}


def builtin(*names: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        for name in names:
            BUILTINS[name] = fn
        fn._matlab_name = names[0]
        return fn
    return register


def nargchk(args: list[Any], lo: int, hi: int | None = None) -> None:
    if len(args) < lo:
        raise MatlabError("Not enough input arguments.", "MATLAB:minrhs")
    if hi is not None and len(args) > hi:
        raise MatlabError("Too many input arguments.", "MATLAB:TooManyInputs")


def dbl(v: Any) -> np.ndarray:
    return as2d(to_double(v))


def real(v: Any) -> np.ndarray:
    return np.real(dbl(v)).astype(float)


def text(v: Any) -> str:
    return char_to_str(v)


def is_text(v: Any) -> bool:
    return isinstance(v, MString) or is_char(v)


def num(v: Any) -> float:
    return scalar(v)


def ival(v: Any) -> int:
    x = scalar(v)
    if np.isnan(x):
        raise MatlabError("NaN is not a valid integer value.")
    return int(x)


def bool_arr(a: Any) -> np.ndarray:
    return as2d(np.asarray(a).astype(bool))


def class_name(v: Any) -> str:
    from backend.matlab.values import class_of
    return class_of(v)


def dtype_of(cls: str) -> Any:
    if cls in INT_TYPES:
        return INT_TYPES[cls]
    return {"double": float, "single": np.float32, "logical": bool, "char": "<U1"}.get(cls, float)


def cast_array(a: np.ndarray, cls: str) -> np.ndarray:
    if cls in INT_TYPES:
        return saturate_int(a, cls)
    if cls == "single":
        return a.astype(np.complex64 if np.iscomplexobj(a) else np.float32)
    if cls == "logical":
        return a.astype(bool)
    if cls == "char":
        return codes_to_char(a)
    return a.astype(complex if np.iscomplexobj(a) else float)


def codes_to_char(a: np.ndarray) -> np.ndarray:
    arr = as2d(np.real(a)).astype(np.int64)
    out = np.empty(arr.shape, dtype="<U1")
    for idx in np.ndindex(arr.shape):
        out[idx] = chr(int(arr[idx]))
    return out


def tidy(a: np.ndarray) -> np.ndarray:
    if np.iscomplexobj(a) and a.size and np.all(np.imag(a) == 0):
        return np.real(a).astype(float)
    return a


def default_dim(a: np.ndarray) -> int:
    """Primera dimensión no singleton (base 0)."""
    return 0 if a.shape[0] != 1 else 1


def dim_arg(v: Any) -> int:
    d = ival(v)
    if d < 1:
        raise MatlabError("Dimension argument must be a positive integer scalar within indexing range.")
    return d - 1


def string_list(v: Any) -> list[str]:
    """Cell de cadenas, string array o char matrix -> lista de Python str."""
    if isinstance(v, MCell):
        return [text(x) for x in v.data.ravel(order="F")]
    if isinstance(v, MString):
        return [str(x) for x in v.data.ravel(order="F")]
    if is_char(v) and as2d(v).shape[0] > 1:
        return ["".join(row) for row in as2d(v).tolist()]
    return [text(v)]


def cellstr_of(items: list[str], column: bool = False) -> MCell:
    arr = np.empty((len(items), 1) if column else (1, len(items)), dtype=object)
    for i, s in enumerate(items):
        arr[(i, 0) if column else (0, i)] = make_char(s)
    return MCell(arr)


def cell_items(v: Any) -> list[Any]:
    if not isinstance(v, MCell):
        raise MatlabError("Input must be a cell array.", "MATLAB:cell:invalidInput")
    return list(v.data.ravel(order="F"))


def make_cell(values: list[Any], shape: tuple[int, int] | None = None) -> MCell:
    arr = np.empty(len(values), dtype=object)
    for i, v in enumerate(values):
        arr[i] = v
    shape = shape or (1, len(values))
    return MCell(arr.reshape(shape, order="F"))


def struct_from_dict(d: dict[str, Any]) -> MStruct:
    return MStruct.scalar(d)


__all__ = [
    "BUILTINS", "builtin", "nargchk", "dbl", "real", "text", "is_text", "num", "ival", "bool_arr",
    "class_name", "dtype_of", "cast_array", "codes_to_char", "tidy", "default_dim", "dim_arg",
    "string_list", "cellstr_of", "cell_items", "make_cell", "struct_from_dict", "MString", "MCell",
    "MStruct", "make_char",
]
