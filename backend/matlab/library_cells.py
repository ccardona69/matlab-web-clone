"""Builtins de celdas, structs y mapeo sobre elementos (cellfun, arrayfun)."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from backend.matlab import ops
from backend.matlab.errors import MatlabError
from backend.matlab.registry import (
    builtin, bool_arr, cell_items, cellstr_of, codes_to_char, ival, is_text, nargchk, real, text,
)
from backend.matlab.values import (
    MCell, MStruct, as2d, class_of, empty_double, is_char, make_char, numel, shape_of, to_double,
)


def _dims_of(args: list[Any]) -> tuple[int, int]:
    raw = real(args[0]).ravel() if len(args) == 1 else np.array([ival(args[0]), ival(args[1])], dtype=float)
    vals = []
    for x in raw:
        f = float(x)
        if not f.is_integer():
            raise MatlabError("Size inputs must be integers.", "MATLAB:NonIntegerInput")
        vals.append(int(f))
    if len(args) == 1 and len(vals) == 1:
        vals = [vals[0], vals[0]]
    return max(vals[0], 0), max(vals[1], 0)


@builtin("cell")
def bi_cell(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 0, 2)
    if not args:
        return MCell(np.empty((0, 0), dtype=object))
    r, c = _dims_of(args)
    return MCell.empty(r, c)


@builtin("cell2mat")
def bi_cell2mat(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    c = args[0]
    if not isinstance(c, MCell):
        raise MatlabError("cell2mat: C must be a cell array.", "MATLAB:cell2mat:notCell")
    if c.data.size == 0:
        return np.zeros((0, 0))
    rows = [[c.data[i, j] for j in range(c.data.shape[1])] for i in range(c.data.shape[0])]
    return ops.concat(rows)


@builtin("struct")
def bi_struct(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        return MStruct([], None)
    if len(args) == 1:
        if isinstance(args[0], MStruct):
            return args[0].copy()
        raise MatlabError(
            f"Conversion to struct from {class_of(args[0])} is not possible.",
            "MATLAB:invalidConversion",
        )
    if len(args) % 2:
        raise MatlabError("Invalid arguments to struct. Arguments must be <field,value> pairs.", "MATLAB:struct:WrongNumberOfInputs")
    names = [text(args[i]) for i in range(0, len(args), 2)]
    values = [args[i] for i in range(1, len(args), 2)]
    shape = (1, 1)
    for v in values:
        if isinstance(v, MCell) and v.data.size != 1:
            shape = v.data.shape
            break
    data = np.empty(shape, dtype=object)
    for idx in np.ndindex(shape):
        entry = {}
        for name, v in zip(names, values):
            if isinstance(v, MCell):
                entry[name] = v.data.flat[0] if v.data.size == 1 else v.data[idx]
            else:
                entry[name] = v
        data[idx] = entry
    return MStruct(names, data)


def _struct_arg(v: Any, name: str) -> MStruct:
    if not isinstance(v, MStruct):
        raise MatlabError(f"{name}: argument must be a struct.", "MATLAB:fieldnames:NonStruct")
    return v


@builtin("fieldnames")
def bi_fieldnames(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    if not isinstance(args[0], MStruct):
        raise MatlabError(
            f"Invalid input argument of type '{class_of(args[0])}'. Input must be a structure or a Java or COM object.",
            "MATLAB:fieldnames:InvalidInput",
        )
    return cellstr_of(args[0].fields, column=True)


@builtin("isfield")
def bi_isfield(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    s = args[0]
    fields = s.fields if isinstance(s, MStruct) else []
    if isinstance(args[1], MCell):
        flags = [isinstance(x, np.ndarray) and is_char(x) and text(x) in fields for x in cell_items(args[1])]
        return bool_arr(np.array(flags, dtype=bool).reshape(args[1].data.shape, order="F"))
    return is_text(args[1]) and text(args[1]) in fields and isinstance(s, MStruct)


@builtin("rmfield")
def bi_rmfield(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    s = _struct_arg(args[0], "rmfield")
    names = [text(x) for x in cell_items(args[1])] if isinstance(args[1], MCell) else [text(args[1])]
    for name in names:
        if name not in s.fields:
            raise MatlabError(f"A field named '{name}' doesn't exist.", "MATLAB:rmfield:InvalidFieldname")
    out = s.copy()
    for d in out.data.flat:
        for name in names:
            d.pop(name, None)
    out.fields = [f for f in out.fields if f not in names]
    return out


@builtin("setfield")
def bi_setfield(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3, 3)
    s = _struct_arg(args[0], "setfield")
    name = text(args[1])
    out = s.copy()
    if name not in out.fields:
        out.fields.append(name)
        for d in out.data.flat:
            d[name] = empty_double()
    out.data.flat[0][name] = args[2]
    return out


@builtin("getfield")
def bi_getfield(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    return _struct_arg(args[0], "getfield").get(text(args[1]))


@builtin("struct2cell")
def bi_struct2cell(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    s = _struct_arg(args[0], "struct2cell")
    values = [s.data.flat[0][f] for f in s.fields]
    arr = np.empty((len(values), 1), dtype=object)
    for i, v in enumerate(values):
        arr[i, 0] = v
    return MCell(arr)


@builtin("orderfields")
def bi_orderfields(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    s = _struct_arg(args[0], "orderfields")
    out = s.copy()
    out.fields = sorted(s.fields)
    return out


# ---------- mapeo sobre elementos ----------

def _split_options(args: list[Any]) -> tuple[list[Any], bool]:
    uniform = True
    data = list(args)
    for i in range(len(data) - 2, -1, -2):
        if is_text(data[i]) and text(data[i]).lower() == "uniformoutput":
            uniform = bool(np.all(to_double(data[i + 1]) != 0))
            del data[i:i + 2]
    return data, uniform


def _uniform_array(results: list[list[Any]], shape: tuple[int, int], output: int) -> Any:
    flat: list[Any] = []
    for index, outs in enumerate(results):
        value = outs[output]
        if numel(value) != 1:
            raise MatlabError(
                f"Non-scalar in Uniform output, at index {index + 1}, output {output + 1}. "
                "Set 'UniformOutput' to false.",
                "MATLAB:cellfun:NonScalarInUniformOutput",
            )
        flat.append(value)
    if not flat:
        return np.zeros(shape)
    if all(class_of(v) == "logical" for v in flat):
        return np.array([bool(v.ravel()[0]) for v in flat], dtype=bool).reshape(shape, order="F")
    if all(is_char(v) for v in flat):
        return codes_to_char(np.array([[ord(v.ravel()[0]) if v.size else 0] for v in flat], dtype=float)).reshape(shape, order="F")
    values = [to_double(v).ravel()[0] for v in flat]
    return np.array(values).reshape(shape, order="F")


def _map_over(I: Any, fn: Any, inputs: list[Any], nargout: int, uniform: bool,
              shape: tuple[int, int], elements: Callable[[Any, int], Any], name: str) -> Any:
    count = int(np.prod(shape))
    nout = max(nargout, 1)
    results: list[list[Any]] = []
    for k in range(count):
        call_args = [elements(v, k) for v in inputs]
        outs = I.call_function(fn, call_args, nargout)
        if nargout > 0 and len(outs) < nout:
            raise MatlabError(f"{name}: function returned fewer outputs than requested.")
        results.append(outs[:nout] if outs else [])
    if nargout == 0 and results and not results[0]:
        return None
    outputs: list[Any] = []
    for out_idx in range(nout):
        if uniform:
            outputs.append(_uniform_array([r if r else [make_char("")] for r in results], shape, out_idx))
        else:
            cells = [r[out_idx] if out_idx < len(r) else make_char("") for r in results]
            arr = np.empty(count, dtype=object)
            for i, v in enumerate(cells):
                arr[i] = v
            outputs.append(MCell(arr.reshape(shape, order="F")))
    return outputs if nout > 1 else outputs[0]


def _cell_content(v: Any, k: int) -> Any:
    return v.data.ravel(order="F")[k]


def _array_element(v: Any, k: int) -> Any:
    if isinstance(v, MStruct):
        return MStruct(v.fields, np.array([[v.data.ravel(order="F")[k]]], dtype=object))
    if isinstance(v, MCell):
        return MCell(np.array([[v.data.ravel(order="F")[k]]], dtype=object))
    flat = as2d(v).ravel(order="F")
    return np.array([[flat[k]]], dtype=flat.dtype)


@builtin("cellfun")
def bi_cellfun(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    rest, uniform = _split_options(list(args[1:]))
    fn = args[0]
    if not rest or not all(isinstance(c, MCell) for c in rest):
        raise MatlabError("cellfun: C must be a cell array.", "MATLAB:cellfun:NotACellArray")
    shape = rest[0].data.shape
    return _map_over(I, fn, rest, nargout, uniform, shape, _cell_content, "cellfun")


@builtin("arrayfun")
def bi_arrayfun(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    rest, uniform = _split_options(list(args[1:]))
    fn = args[0]
    if not rest:
        raise MatlabError("arrayfun: not enough input arguments.", "MATLAB:minrhs")
    shape = shape_of(rest[0])
    if any(shape_of(v) != shape for v in rest):
        raise MatlabError("All the input arguments must be the same size and shape.", "MATLAB:arrayfun:InputSizeMismatch")
    return _map_over(I, fn, rest, nargout, uniform, shape, _array_element, "arrayfun")
