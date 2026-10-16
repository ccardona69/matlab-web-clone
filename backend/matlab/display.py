"""
Presentación de valores en la Command Window con las reglas de `format` de MATLAB
(short/long/shortG/longG/shortE/longE y espaciado loose/compact).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.matlab.values import (
    MCell, MFunc, MString, MStruct, as2d, char_to_str, class_of, is_char, shape_of,
)


@dataclass
class FormatState:
    numeric: str = "short"  # short | long | shortg | longg | shorte | longe
    spacing: str = "loose"  # loose | compact


def _is_intlike(a: np.ndarray) -> bool:
    finite = a[np.isfinite(a)]
    return finite.size == 0 or bool(np.all(finite == np.round(finite)))


def _special(x: float) -> str | None:
    if np.isnan(x):
        return "NaN"
    if np.isinf(x):
        return "Inf" if x > 0 else "-Inf"
    return None


def _decimals(fmt: FormatState) -> int:
    return 15 if fmt.numeric.startswith("long") else 4


def format_real_scalar_compact(x: float, fmt: FormatState | None = None) -> str:
    """Formato corto usado dentro de structs, celdas y num2str."""
    fmt = fmt or FormatState()
    sp = _special(x)
    if sp:
        return sp
    if x == round(x) and abs(x) < 1e15:
        return str(int(x))
    d = _decimals(fmt)
    ax = abs(x)
    if fmt.numeric in ("shortg", "longg"):
        return f"{x:.{5 if fmt.numeric == 'shortg' else 15}g}"
    if ax >= 1000 or ax < 0.001:
        return f"{x:.{d}e}"
    return f"{x:.{d}f}"


def _numeric_cells(a: np.ndarray, fmt: FormatState) -> tuple[str | None, list[list[str]], int]:
    """Devuelve (cabecera de escala, celdas por fila, ancho de columna)."""
    a = as2d(a)
    if np.iscomplexobj(a):
        return _complex_cells(a, fmt)
    if a.dtype.kind == "b":
        cells = [["1" if v else "0" for v in row] for row in a]
        return None, cells, 4
    if a.dtype.kind in "iu":
        cells = [[str(int(v)) for v in row] for row in a]
        w = max((len(s) for r in cells for s in r), default=1)
        return None, cells, w + 2
    af = a.astype(float)
    scalar = af.size == 1
    if fmt.numeric in ("shortg", "longg"):
        digits = 5 if fmt.numeric == "shortg" else 15
        cells = [[_special(v) or f"{v:.{digits}g}" for v in row] for row in af]
        w = max((len(s) for r in cells for s in r), default=1)
        return None, cells, w + (3 if scalar else 5)
    if fmt.numeric in ("shorte", "longe"):
        d = _decimals(fmt)
        cells = [[_special(v) or f"{v:.{d}e}" for v in row] for row in af]
        w = max((len(s) for r in cells for s in r), default=1)
        return None, cells, w + 3
    if _is_intlike(af):
        finite = af[np.isfinite(af)]
        if finite.size and np.max(np.abs(finite)) >= 1e9:
            d = _decimals(fmt)
            cells = [[_special(v) or f"{v:.{d}e}" for v in row] for row in af]
            w = max(len(s) for r in cells for s in r)
            return None, cells, w + 3
        cells = [[_special(v) or str(int(v)) for v in row] for row in af]
        w = max((len(s) for r in cells for s in r), default=1)
        return None, cells, 6 if w <= 5 else w + 6
    d = _decimals(fmt)
    finite = af[np.isfinite(af)]
    amax = float(np.max(np.abs(finite))) if finite.size else 0.0
    exp10 = int(math.floor(math.log10(amax))) if amax > 0 else 0
    if scalar:
        x = float(af.flat[0])
        sp = _special(x)
        if sp:
            return None, [[sp]], len(sp) + 3
        if amax >= 1000 or amax < 0.001:
            s = f"{x:.{d}e}"
            return None, [[s]], len(s) + 3
        s = f"{x:.{d}f}"
        return None, [[s]], max(10 if d == 4 else 20, len(s) + 3)
    header = None
    scale = 1.0
    if exp10 >= 3 or exp10 < -3:
        scale = 10.0 ** exp10
        sign = "+" if exp10 >= 0 else "-"
        header = f"   1.0e{sign}{abs(exp10):02d} *"
    cells = []
    for row in af:
        out = []
        for v in row:
            sp = _special(v)
            if sp:
                out.append(sp)
            elif v == 0:
                out.append("0")
            else:
                out.append(f"{v / scale:.{d}f}")
        cells.append(out)
    w = max(len(s) for r in cells for s in r)
    return header, cells, max(w + 4, 10 if d == 4 else 21)


def _complex_cells(a: np.ndarray, fmt: FormatState) -> tuple[str | None, list[list[str]], int]:
    d = _decimals(fmt)
    re_all = np.real(a)
    im_all = np.imag(a)
    allv = np.concatenate([np.abs(re_all[np.isfinite(re_all)]), np.abs(im_all[np.isfinite(im_all)])])
    amax = float(np.max(allv)) if allv.size else 0.0
    use_e = amax >= 1e5 or (0 < amax < 0.001)
    cells = []
    for row in a:
        out = []
        for z in row:
            re, im = float(np.real(z)), float(np.imag(z))
            rs = _special(re) or (f"{re:.{d}e}" if use_e else f"{re:.{d}f}")
            ims = _special(abs(im)) or (f"{abs(im):.{d}e}" if use_e else f"{abs(im):.{d}f}")
            sign = "-" if (im < 0 or (im == 0 and math.copysign(1, im) < 0)) else "+"
            out.append(f"{rs} {sign} {ims}i")
        cells.append(out)
    w = max(len(s) for r in cells for s in r)
    return None, cells, w + 3


def _layout_columns(cells: list[list[str]], colw: int, width: int, fmt: FormatState) -> list[str]:
    nrows = len(cells)
    ncols = len(cells[0]) if cells else 0
    per_chunk = max(1, (width - 2) // max(colw, 1))
    lines: list[str] = []
    max_rows = 2000
    if ncols <= per_chunk:
        for r in cells[:max_rows]:
            lines.append("".join(s.rjust(colw) for s in r))
        if nrows > max_rows:
            lines.append(f"  ... ({nrows - max_rows} filas más no mostradas)")
        return lines
    for start in range(0, ncols, per_chunk):
        stop = min(ncols, start + per_chunk)
        label = f"  Columns {start + 1} through {stop}" if stop - start > 1 else f"  Column {start + 1}"
        if start > 0 and fmt.spacing == "loose":
            lines.append("")
        lines.append(label)
        if fmt.spacing == "loose":
            lines.append("")
        for r in cells[:max_rows]:
            lines.append("".join(s.rjust(colw) for s in r[start:stop]))
    return lines


def _type_header(v: Any) -> str:
    r, c = shape_of(v)
    cls = class_of(v)
    if r == 1 and c > 1:
        kind = "row vector"
    elif c == 1 and r > 1:
        kind = "column vector"
    else:
        kind = "matrix"
    return f"  {r}×{c} {cls} {kind}" if (r * c) != 1 else f"  {cls}"


def value_summary(v: Any, fmt: FormatState | None = None, in_cell: bool = False) -> str:
    """Resumen de una línea (campos de struct, elementos de celda)."""
    fmt = fmt or FormatState()
    r, c = shape_of(v)
    if isinstance(v, np.ndarray):
        if is_char(v):
            if r <= 1:
                return f"'{char_to_str(v)}'" if v.size else ("''" if not in_cell else "0×0 char")
            return f"{r}×{c} char"
        if v.size == 0:
            return "[]" if (r, c) == (0, 0) else f"{r}×{c} {class_of(v)}"
        if r == 1 and c <= 10 and not np.iscomplexobj(v):
            vals = " ".join(format_real_scalar_compact(float(x), fmt) for x in as2d(v).astype(float)[0])
            if v.size == 1 and not in_cell:
                return vals
            return f"[{vals}]"
        if v.size == 1 and np.iscomplexobj(v):
            z = complex(v.flat[0])
            return f"{z.real:.4f} {'+' if z.imag >= 0 else '-'} {abs(z.imag):.4f}i"
        return f"{r}×{c} {class_of(v)}"
    if isinstance(v, MString):
        if v.data.size == 1:
            return f'"{v.scalar()}"'
        return f"{r}×{c} string"
    if isinstance(v, MCell):
        return f"{r}×{c} cell"
    if isinstance(v, MStruct):
        return f"{r}×{c} struct"
    if isinstance(v, MFunc):
        return v.display_text()
    return str(v)


def _cell_element(v: Any, fmt: FormatState) -> str:
    s = value_summary(v, fmt, in_cell=True)
    if isinstance(v, np.ndarray) and not is_char(v) and v.size >= 1 and "×" not in s:
        if not s.startswith("["):
            s = f"[{s}]"
    if isinstance(v, MString) and v.data.size == 1:
        s = f"[{s}]"
    return "{" + s + "}"


def format_body(v: Any, fmt: FormatState, width: int = 100) -> tuple[str | None, list[str]]:
    """Cabecera opcional y líneas del cuerpo para mostrar un valor."""
    r, c = shape_of(v)
    if isinstance(v, np.ndarray):
        v = as2d(v)
        if is_char(v):
            if v.size == 0:
                return f"  {r}×{c} empty char array", []
            if r == 1:
                return None, [f"    '{char_to_str(v)}'"]
            return f"  {r}×{c} char array", [f"    '{''.join(row)}'" for row in v.tolist()]
        if v.size == 0:
            if (r, c) == (0, 0) and class_of(v) == "double":
                return None, ["     []"]
            return f"  {r}×{c} empty {class_of(v)} {'matrix' if r != 1 and c != 1 else ('row vector' if r == 1 else 'column vector')}", []
        header, cells, colw = _numeric_cells(v, fmt)
        lines = _layout_columns(cells, colw, width, fmt)
        cls = class_of(v)
        if cls != "double":
            th = _type_header(v)
            if cls == "logical" and v.size > 1:
                th = th.replace("logical matrix", "logical array").replace("logical row vector", "logical array").replace("logical column vector", "logical array")
            if header:
                return th, [header, ""] + lines if fmt.spacing == "loose" else [header] + lines
            return th, lines
        if header:
            return None, ([header, ""] if fmt.spacing == "loose" else [header]) + lines
        return None, lines
    if isinstance(v, MString):
        if v.data.size == 1:
            return None, [f'    "{v.scalar()}"']
        cells = [[f'"{s}"' for s in row] for row in v.data.tolist()]
        w = max(len(s) for row in cells for s in row) + 4
        return f"  {r}×{c} string array", ["    " + "".join(s.ljust(w) for s in row).rstrip() for row in cells]
    if isinstance(v, MCell):
        if v.data.size == 0:
            return f"  {r}×{c} empty cell array", []
        cells = [[_cell_element(x, fmt) for x in row] for row in v.data.tolist()]
        widths = [max(len(cells[i][j]) for i in range(r)) for j in range(c)]
        lines = ["    " + "    ".join(cells[i][j].ljust(widths[j]) for j in range(c)).rstrip() for i in range(r)]
        return f"  {r}×{c} cell array", lines
    if isinstance(v, MStruct):
        if v.data.size == 1:
            d = v.data.flat[0]
            if not v.fields:
                return "  struct with no fields.", []
            namew = max(len(f) for f in v.fields)
            lines = [f"    {f.rjust(namew)}: {value_summary(d[f], fmt)}" for f in v.fields]
            return "  struct with fields:", lines
        return f"  {r}×{c} struct array with fields:", [f"    {f}" for f in v.fields]
    if isinstance(v, MFunc):
        return "  function_handle with value:", [f"    {v.display_text()}"]
    return None, [f"    {v}"]


def display(name: str, v: Any, fmt: FormatState, width: int = 100) -> str:
    header, lines = format_body(v, fmt, width)
    loose = fmt.spacing == "loose"
    # Strings escalares y celdas vacías siguen el estilo compacto "x = valor" de MATLAB moderno
    if isinstance(v, MString) and v.data.size == 1:
        return f"{name} = \n\n{lines[0]}\n\n" if loose else f"{name} = \n{lines[0]}\n"
    out = [f"{name} ="]
    if loose:
        out.append("")
    if header:
        out.append(header)
        if loose and lines:
            out.append("")
    out.extend(lines)
    text = "\n".join(out) + "\n"
    if loose:
        text += "\n"
    return text


def disp_text(v: Any, fmt: FormatState, width: int = 100) -> str:
    if isinstance(v, np.ndarray) and is_char(v):
        if v.size == 0:
            return ""
        return "\n".join("".join(row) for row in as2d(v).tolist()) + "\n"
    if isinstance(v, MString):
        if v.data.size == 1:
            return v.scalar() + "\n"
    if isinstance(v, np.ndarray) and v.size == 0:
        return ""
    header, lines = format_body(v, fmt, width)
    if isinstance(v, (MCell, MStruct, MString)):
        return "\n".join(lines) + "\n"
    if isinstance(v, np.ndarray) and v.size == 1 and not header:
        return lines[0].strip() + "\n"
    if isinstance(v, np.ndarray) and class_of(v) not in ("double",) and header and not header.startswith("  1.0e"):
        return "\n".join(lines) + "\n"
    return "\n".join(([header, ""] if header else []) + lines) + "\n"
