"""
Modelo de valores del clon.

Las clases siguen la taxonomía `MathWorks.MATLAB.Types.ArrayType` recuperada con REA
(ev_4b3e6b60aa8759c5f867ab59d916859b99481243e6fe6f8d85a2b29a9297e80e): LOGICAL, CHAR,
MATLAB_STRING, DOUBLE, SINGLE, INT8…UINT64, sus variantes complejas, CELL y STRUCT, con
`MemoryLayout.ColumnMajor` como disposición de memoria (indexado lineal por columnas).

Representación:
- numéricos, logical y char → numpy.ndarray 2-D (char usa dtype '<U1')
- string → MString, cell → MCell, struct (escalar o arreglo) → MStruct, handle → MFunc
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.matlab.errors import MatlabError

INT_TYPES = {
    "int8": np.int8, "uint8": np.uint8, "int16": np.int16, "uint16": np.uint16,
    "int32": np.int32, "uint32": np.uint32, "int64": np.int64, "uint64": np.uint64,
}
NUMERIC_CLASSES = {"double", "single", *INT_TYPES}


class MString:
    """Arreglo de strings (comillas dobles)."""

    __slots__ = ("data",)

    def __init__(self, data: Any) -> None:
        if isinstance(data, str):
            arr = np.empty((1, 1), dtype=object)
            arr[0, 0] = data
            data = arr
        self.data = np.asarray(data, dtype=object)
        if self.data.ndim == 1:
            self.data = self.data.reshape(1, -1)
        elif self.data.ndim == 0:
            self.data = self.data.reshape(1, 1)

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape

    def scalar(self) -> str:
        return str(self.data.flat[0]) if self.data.size else ""


class MCell:
    __slots__ = ("data",)

    def __init__(self, data: Any) -> None:
        arr = np.asarray(data, dtype=object) if not isinstance(data, np.ndarray) else data
        if arr.ndim == 0:
            arr = arr.reshape(1, 1)
        elif arr.ndim == 1:
            arr = arr.reshape(1, -1)
        self.data = arr

    @staticmethod
    def empty(r: int, c: int) -> "MCell":
        arr = np.empty((r, c), dtype=object)
        for idx in np.ndindex(r, c):
            arr[idx] = empty_double()
        return MCell(arr)

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape


class MStruct:
    """Struct escalar o arreglo de structs (cada elemento es un dict con los mismos campos)."""

    __slots__ = ("fields", "data")

    def __init__(self, fields: list[str] | None = None, data: np.ndarray | None = None) -> None:
        self.fields = list(fields or [])
        if data is None:
            data = np.empty((1, 1), dtype=object)
            data[0, 0] = {f: empty_double() for f in self.fields}
        self.data = data

    @staticmethod
    def scalar(values: dict[str, Any]) -> "MStruct":
        arr = np.empty((1, 1), dtype=object)
        arr[0, 0] = dict(values)
        return MStruct(list(values.keys()), arr)

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape

    def get(self, name: str) -> Any:
        if name not in self.fields:
            raise MatlabError(f"Unrecognized field name \"{name}\".", "MATLAB:nonExistentField")
        return self.data.flat[0][name]

    def copy(self) -> "MStruct":
        arr = np.empty(self.data.shape, dtype=object)
        for idx in np.ndindex(self.data.shape):
            arr[idx] = dict(self.data[idx])
        return MStruct(list(self.fields), arr)


@dataclass
class MFunc:
    name: str | None = None
    params: list[str] = field(default_factory=list)
    body: Any = None
    closure: dict[str, Any] = field(default_factory=dict)
    text: str = ""

    def display_text(self) -> str:
        return self.text if self.body is not None else f"@{self.name}"


# ---------- constructores ----------

def empty_double() -> np.ndarray:
    return np.zeros((0, 0), dtype=float)


def num(x: Any) -> np.ndarray:
    return np.array([[x]], dtype=complex if isinstance(x, complex) else float)


def make_char(s: str) -> np.ndarray:
    if s == "":
        return np.zeros((0, 0), dtype="<U1")
    return np.array([list(s)], dtype="<U1")


def logical(x: bool) -> np.ndarray:
    return np.array([[bool(x)]], dtype=bool)


def as2d(a: np.ndarray) -> np.ndarray:
    if a.ndim == 2:
        return a
    if a.ndim == 0:
        return a.reshape(1, 1)
    if a.ndim == 1:
        return a.reshape(1, -1)
    return a


def from_python(v: Any) -> Any:
    """Convierte un resultado Python/numpy al modelo de valores MATLAB."""
    if isinstance(v, (MString, MCell, MStruct, MFunc, MMap, MDictionary)):
        return v
    if isinstance(v, np.ndarray):
        if v.dtype == object:
            return MCell(as2d(v))
        if v.dtype.kind == "U" and v.dtype.itemsize > 4:
            return MString(as2d(v.astype(object)))
        return as2d(v)
    if isinstance(v, bool) or isinstance(v, np.bool_):
        return logical(bool(v))
    if isinstance(v, (int, float, np.integer, np.floating)):
        if isinstance(v, np.integer) and type(v).__name__ in INT_TYPES:
            return np.array([[v]], dtype=v.dtype)
        return num(float(v))
    if isinstance(v, (complex, np.complexfloating)):
        return num(complex(v))
    if isinstance(v, str):
        return make_char(v)
    if v is None:
        return empty_double()
    if isinstance(v, (list, tuple)):
        return as2d(np.array(v, dtype=float))
    raise MatlabError(f"Tipo no soportado en el clon: {type(v).__name__}")


# ---------- introspección ----------

def class_of(v: Any) -> str:
    if isinstance(v, np.ndarray):
        k = v.dtype.kind
        if k == "b":
            return "logical"
        if k == "U":
            return "char"
        if v.dtype in (np.float32, np.complex64):
            return "single"
        if k in "iu":
            return v.dtype.name
        return "double"
    if isinstance(v, MString):
        return "string"
    if isinstance(v, MCell):
        return "cell"
    if isinstance(v, MStruct):
        return "struct"
    if isinstance(v, MFunc):
        return "function_handle"
    return type(v).__name__


def shape_of(v: Any) -> tuple[int, int]:
    if isinstance(v, np.ndarray):
        return as2d(v).shape
    if isinstance(v, (MString, MCell, MStruct)):
        return v.shape
    return (1, 1)


def numel(v: Any) -> int:
    r, c = shape_of(v)
    return r * c


def is_char(v: Any) -> bool:
    return isinstance(v, np.ndarray) and v.dtype.kind == "U"


def is_numeric_like(v: Any) -> bool:
    return isinstance(v, np.ndarray)


def char_to_str(v: Any) -> str:
    if isinstance(v, MString):
        return v.scalar()
    if is_char(v):
        if v.size == 0:
            return ""
        if v.shape[0] == 1:
            return "".join(v[0].tolist())
        return "\n".join("".join(row) for row in v.tolist())
    if isinstance(v, np.ndarray) and v.size and v.dtype.kind in "fiub":
        return "".join(chr(int(c)) for c in v.ravel(order="F"))
    raise MatlabError("Argument must be a character vector or string scalar.", "MATLAB:invalidType")


def to_str(v: Any) -> str:
    return char_to_str(v)


def to_double(v: Any) -> np.ndarray:
    """Convierte a arreglo numérico para aritmética (char→códigos, logical→double)."""
    if isinstance(v, np.ndarray):
        if v.dtype.kind == "U":
            if v.size == 0:
                return np.zeros(v.shape, dtype=float)
            return np.vectorize(ord, otypes=[float])(v)
        if v.dtype.kind == "b":
            return v.astype(float)
        return v
    if isinstance(v, MString):
        raise MatlabError("Operator not supported for operands of type 'string'.")
    if isinstance(v, MCell):
        raise MatlabError("Operator not supported for operands of type 'cell'.", "MATLAB:UndefinedFunction")
    if isinstance(v, MStruct):
        raise MatlabError("Operator not supported for operands of type 'struct'.", "MATLAB:UndefinedFunction")
    if isinstance(v, MFunc):
        raise MatlabError("Operator not supported for operands of type 'function_handle'.", "MATLAB:UndefinedFunction")
    return from_python(v)


def scalar(v: Any, what: str = "value") -> float:
    a = to_double(v)
    if a.size < 1:
        raise MatlabError(f"Expected {what} to be a scalar.", "MATLAB:expectedScalar")
    x = a.flat[0]
    if isinstance(x, (complex, np.complexfloating)):
        return float(np.real(x))
    return float(x)


def int_scalar(v: Any, what: str = "value") -> int:
    x = scalar(v, what)
    if np.isnan(x):
        raise MatlabError("NaN is not a valid integer value.")
    return int(round(x))


def truthy(v: Any) -> bool:
    """Condición de if/while: verdadera si no está vacía y todos sus elementos son no nulos."""
    if isinstance(v, np.ndarray):
        if v.size == 0:
            return False
        a = to_double(v)
        if np.iscomplexobj(a):
            a = np.abs(a)
        if np.any(np.isnan(a)):
            raise MatlabError("NaN's cannot be converted to logicals.", "MATLAB:nologicalnan")
        return bool(np.all(a != 0))
    if isinstance(v, MString):
        raise MatlabError("Conversion to logical from string is not possible.")
    raise MatlabError(f"Conversion to logical from {class_of(v)} is not possible.")


def saturate_int(values: np.ndarray, cls: str) -> np.ndarray:
    dt = INT_TYPES[cls]
    info = np.iinfo(dt)
    v = np.real(np.asarray(values)).astype(float)
    v = np.where(np.isnan(v), 0, v)
    # MATLAB redondea a la mitad alejándose de cero y satura en los límites del tipo
    v = np.sign(v) * np.floor(np.abs(v) + 0.5)
    return np.clip(v, info.min, info.max).astype(dt)


def size_text(v: Any) -> str:
    r, c = shape_of(v)
    return f"{r}×{c}"


def bytes_of(v: Any) -> int:
    if isinstance(v, np.ndarray):
        return int(v.size * (2 if v.dtype.kind == "U" else v.dtype.itemsize))
    if isinstance(v, MString):
        return 150 + sum(len(str(s)) * 2 for s in v.data.flat)
    if isinstance(v, MCell):
        return sum(bytes_of(x) + 104 for x in v.data.flat)
    if isinstance(v, MStruct):
        return sum(bytes_of(x) + 64 for d in v.data.flat for x in d.values()) + 176
    return 32


class MMap:
    """containers.Map mínimo (construcción y presentación)."""

    def __init__(self, key_type: str = "char", value_type: str = "any") -> None:
        self.keys: list[Any] = []
        self.values: list[Any] = []
        self.key_type = key_type
        self.value_type = value_type


class MDictionary:
    """Objeto dictionary mínimo (aún sin entradas configuradas)."""

    def __init__(self) -> None:
        self.entries: list[tuple[Any, Any]] = []
