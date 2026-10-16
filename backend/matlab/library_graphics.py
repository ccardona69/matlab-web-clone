"""Funciones de gráficos de MATLAB sobre el motor Handle Graphics (backend/hg_graphics.py)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from backend.hg_graphics import COLOR_ORDER, color_from_spec, parse_linespec
from backend.matlab.errors import MatlabError
from backend.matlab.registry import builtin, is_text, ival, nargchk, string_list, text
from backend.matlab.values import MFunc, as2d, to_double

LINE_NAME_VALUES = {"linewidth", "color", "linestyle", "marker", "markersize", "markerfacecolor",
                    "markeredgecolor", "displayname"}
FIGURE_EXTENSIONS = {".png", ".svg", ".pdf", ".jpg", ".jpeg"}


def _ret(value: Any, nargout: int) -> Any:
    return value if nargout > 0 else None


def _arr(v: Any) -> np.ndarray:
    return as2d(to_double(v))


def _vec(v: Any) -> np.ndarray:
    return np.asarray(_arr(v)).ravel(order="F").astype(complex if np.iscomplexobj(_arr(v)) else float)


def parse_pairs(args: list[Any]) -> dict[str, Any]:
    """Name-value insensibles a mayúsculas; claves normalizadas a minúsculas."""
    props: dict[str, Any] = {}
    if len(args) % 2:
        raise MatlabError("Invalid name-value pair arguments.", "MATLAB:graphics:NameValuePair")
    for i in range(0, len(args), 2):
        if not is_text(args[i]):
            raise MatlabError("Name-value pair names must be character vectors.", "MATLAB:graphics:NameValuePair")
        value = args[i + 1]
        props[text(args[i]).lower()] = text(value) if is_text(value) else _arr(value).astype(float).ravel()
    return props


def _line_props(props: dict[str, Any], spec: dict[str, Any] | None, color: tuple[float, float, float]) -> dict[str, Any]:
    spec = spec or {}
    explicit = color_from_spec(props["color"]) if "color" in props else None
    out: dict[str, Any] = {
        "color": explicit or spec.get("color") or color,
        "linestyle": props.get("linestyle", spec.get("linestyle") or "-"),
        "marker": props.get("marker", spec.get("marker") or "none"),
        "linewidth": float(props.get("linewidth", 0.5)),
        "markersize": float(props.get("markersize", 6)),
        "label": props.get("displayname", ""),
    }
    for key, prop in (("MarkerFaceColor", "markerfacecolor"), ("MarkerEdgeColor", "markeredgecolor")):
        if prop in props:
            out[key] = props[prop]
    return out


def _split_series(args: list[Any]) -> tuple[list[tuple[Any, np.ndarray, str]], dict[str, Any]]:
    """Trozos (x?, y, estilo) seguidos de name-value opcionales."""
    series: list[tuple[Any, np.ndarray, str]] = []
    i = 0
    while i < len(args) and not is_text(args[i]):
        first = _arr(args[i])
        if i + 1 < len(args) and not is_text(args[i + 1]):
            series.append((first, _arr(args[i + 1]), ""))
            i += 2
        else:
            series.append((None, first, ""))
            i += 1
        if i < len(args) and is_text(args[i]) and parse_linespec(text(args[i])) is not None:
            style = text(args[i])
            x, y, _ = series[-1]
            series[-1] = (x, y, style)
            i += 1
    return series, parse_pairs(list(args[i:]))


def _columns(x: Any, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (x de longitud n, Y con n filas y una columna por línea)."""
    if y.shape[0] == 1 and y.shape[1] > 1:
        y = y.T
    n = y.shape[0]
    xv = np.arange(1, n + 1, dtype=float) if x is None else np.real(_vec(x))
    return xv, y


def _plot_lines(I: Any, args: list[Any], nargout: int, is_3d: bool = False) -> Any:
    series, props = _split_series(args)
    if not series:
        raise MatlabError("Not enough input arguments.", "MATLAB:minrhs")
    ax = I.graphics.begin_plot(is_3d=is_3d)
    handles = []
    for x, y, style in series:
        spec = parse_linespec(style) if style else None
        pieces = [(None, np.real(y)), (None, np.imag(y))] if np.iscomplexobj(y) else [(x, y)]
        for xv, yv in pieces:
            xs, Y = _columns(xv, yv)
            for col in range(Y.shape[1]):
                color = (spec or {}).get("color") or _next(ax)
                payload = {"x": xs, "y": Y[:, col]}
                handles.append(I.graphics.add_item("line", payload, _line_props(props, spec, color)))
    return _ret(handles[0] if len(handles) == 1 else np.array([handles]), nargout)


def _next(ax: Any) -> tuple[float, float, float]:
    color = COLOR_ORDER[ax.color_index % len(COLOR_ORDER)]
    ax.color_index += 1
    return color


@builtin("plot")
def bi_plot(I: Any, args: list[Any], nargout: int) -> Any:
    return _plot_lines(I, args, nargout)


def _log_plot(kind: str) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        result = _plot_lines(I, args, nargout)
        ax = I.graphics.gca()
        if kind in ("semilogx", "loglog"):
            ax.xscale = "log"
        if kind in ("semilogy", "loglog"):
            ax.yscale = "log"
        return result
    return fn


builtin("semilogx")(_log_plot("semilogx"))
builtin("semilogy")(_log_plot("semilogy"))
builtin("loglog")(_log_plot("loglog"))


@builtin("plot3")
def bi_plot3(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3)
    x, y, z = _vec(args[0]), _vec(args[1]), _vec(args[2])
    rest = list(args[3:])
    spec = parse_linespec(text(rest[0])) if rest and is_text(rest[0]) else None
    if spec is not None:
        rest = rest[1:]
    ax = I.graphics.begin_plot(is_3d=True)
    color = (spec or {}).get("color") or _next(ax)
    return _ret(I.graphics.add_item("line", {"x": x, "y": y, "z": z}, _line_props(parse_pairs(rest), spec, color)),
                nargout)


@builtin("line")
def bi_line(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    ax = I.graphics.gca()
    data: dict[str, Any] = {"x": _vec(args[0]), "y": _vec(args[1])}
    rest = list(args[2:])
    if rest and not is_text(rest[0]):
        data["z"] = _vec(rest[0])
        rest = rest[1:]
    return _ret(I.graphics.add_item("line", data, _line_props(parse_pairs(rest), None, _next(ax))), nargout)


def _scatter(is_3d: bool) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 2)
        nums: list[np.ndarray] = []
        i = 0
        while i < len(args) and not is_text(args[i]) and len(nums) < (4 if is_3d else 3):
            nums.append(_vec(args[i]).real)
            i += 1
        filled = any(is_text(a) and text(a).lower() == "filled" for a in args[i:])
        props = parse_pairs([a for a in args[i:] if not (is_text(a) and text(a).lower() == "filled")])
        ax = I.graphics.begin_plot(is_3d=is_3d)
        has_c = len(nums) > (3 if is_3d else 2)
        data: dict[str, Any] = {"x": nums[0], "y": nums[1]}
        offset = 2
        if is_3d:
            data["z"] = nums[2]
            offset = 3
        size = nums[offset] if len(nums) > offset else np.array([float(props.get("sizedata", 36))])
        style: dict[str, Any] = {"size": size if size.size > 1 else float(size[0]), "filled": filled,
                                 "marker": props.get("marker", "o"), "label": props.get("displayname", "")}
        if has_c and nums[offset + 1 if len(nums) > offset + 1 else offset].size == nums[0].size:
            data["c"] = nums[-1]
        else:
            face = color_from_spec(props.get("markerfacecolor")) or color_from_spec(props.get("color")) or _next(ax)
            style["color"] = face
            style["face"] = face
        return _ret(I.graphics.add_item("scatter", data, style), nargout)
    return fn


builtin("scatter")(_scatter(False))
builtin("scatter3")(_scatter(True))


def _bar_common(I: Any, args: list[Any], nargout: int, horizontal: bool) -> Any:
    nargchk(args, 1)
    if len(args) >= 2 and not is_text(args[1]) and _arr(args[0]).size == _arr(args[1]).shape[0]:
        x, Y = _vec(args[0]), _arr(args[1])
        rest = args[2:]
    else:
        Y = _arr(args[0])
        x = np.arange(1, Y.shape[0] + 1, dtype=float)
        rest = args[1:]
    width = 0.8
    stacked = False
    props: dict[str, Any] = {}
    i = 0
    if rest and not is_text(rest[0]):
        width = float(_vec(rest[0])[0])
        i = 1
    if i < len(rest) and is_text(rest[i]) and text(rest[i]).lower() in ("stacked", "grouped"):
        stacked = text(rest[i]).lower() == "stacked"
        i += 1
    props = parse_pairs(list(rest[i:]))
    ax = I.graphics.begin_plot()
    color = _next(ax) if Y.shape[1] == 1 else None
    kind = "barh" if horizontal else "bar"
    return _ret(I.graphics.add_item(kind, {"x": x, "y": Y},
                                    {"width": width, "stacked": stacked, "color": color or COLOR_ORDER[0],
                                     "label": props.get("displayname", "")}), nargout)


@builtin("bar")
def bi_bar(I: Any, args: list[Any], nargout: int) -> Any:
    return _bar_common(I, args, nargout, horizontal=False)


@builtin("barh")
def bi_barh(I: Any, args: list[Any], nargout: int) -> Any:
    return _bar_common(I, args, nargout, horizontal=True)


@builtin("area")
def bi_area(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    if len(args) >= 2 and not is_text(args[1]):
        x, Y = _vec(args[0]), _arr(args[1])
    else:
        Y = _arr(args[0])
        x = np.arange(1, Y.shape[0] + 1, dtype=float)
    ax = I.graphics.begin_plot()
    last = None
    for col in range(Y.shape[1]):
        last = I.graphics.add_item("area", {"x": x, "y": Y[:, col]}, {"color": _next(ax)})
    return _ret(last, nargout)


@builtin("stem")
def bi_stem(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    series, props = _split_series(args)
    ax = I.graphics.begin_plot()
    handles = []
    for x, y, style in series:
        spec = parse_linespec(style) if style else None
        xs, Y = _columns(x, y)
        for col in range(Y.shape[1]):
            color = (spec or {}).get("color") or _next(ax)
            handles.append(I.graphics.add_item("stem", {"x": xs, "y": Y[:, col]}, {"color": color}))
    return _ret(handles[-1] if handles else None, nargout)


@builtin("stairs")
def bi_stairs(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    series, _ = _split_series(args)
    ax = I.graphics.begin_plot()
    handles = []
    for x, y, style in series:
        spec = parse_linespec(style) if style else None
        xs, Y = _columns(x, y)
        for col in range(Y.shape[1]):
            color = (spec or {}).get("color") or _next(ax)
            handles.append(I.graphics.add_item("stairs", {"x": xs, "y": Y[:, col]}, {"color": color}))
    return _ret(handles[-1] if handles else None, nargout)


def _histogram_edges(data: np.ndarray, bins: Any, props: dict[str, Any]) -> np.ndarray:
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return np.array([0.0, 1.0])
    if "binwidth" in props:
        width = float(props["binwidth"][0])
        start = math.floor(finite.min() / width) * width
        stop = math.ceil(finite.max() / width) * width
        stop = stop + width if stop == finite.max() else stop
        return np.arange(start, stop + width * 0.5, width)
    if isinstance(bins, np.ndarray) and bins.size > 1:
        return bins
    if isinstance(bins, int):
        return np.histogram_bin_edges(finite, bins=bins)
    return np.histogram_bin_edges(finite, bins="auto")


def _normalize(counts: np.ndarray, edges: np.ndarray, mode: str) -> np.ndarray:
    total = counts.sum() or 1.0
    widths = np.diff(edges)
    if mode == "probability":
        return counts / total
    if mode == "pdf":
        return counts / (total * widths)
    if mode == "countdensity":
        return counts / widths
    if mode == "cumcount":
        return np.cumsum(counts)
    if mode == "cdf":
        return np.cumsum(counts) / total
    return counts


@builtin("histogram")
def bi_histogram(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    data = _vec(args[0]).real
    rest = list(args[1:])
    bins: Any = None
    if rest and not is_text(rest[0]):
        bins = _vec(rest[0]).real if _vec(rest[0]).size > 1 else ival(rest[0])
        rest = rest[1:]
    props = parse_pairs(rest)
    if "numbins" in props:
        bins = int(props["numbins"][0])
    edges = _histogram_edges(data, bins, props)
    counts, edges = np.histogram(data, bins=edges)
    heights = _normalize(counts.astype(float), edges, str(props.get("normalization", "count")).lower())
    ax = I.graphics.begin_plot()
    style: dict[str, Any] = {"color": _next(ax), "label": props.get("displayname", ""),
                             "FaceAlpha": float(props["facealpha"][0]) if "facealpha" in props else 0.6}
    for key, prop in (("FaceColor", "facecolor"), ("EdgeColor", "edgecolor")):
        if prop in props:
            style[key] = props[prop]
    handle = I.graphics.add_item("histogram", {"edges": edges, "counts": heights}, style)
    return _ret(handle, nargout)


@builtin("hist")
def bi_hist(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    data = _vec(args[0]).real
    bins = 10
    if len(args) > 1 and not is_text(args[1]):
        arg = _vec(args[1]).real
        bins = arg if arg.size > 1 else int(arg[0])
    counts, edges = np.histogram(data, bins=bins)
    ax = I.graphics.begin_plot()
    I.graphics.add_item("histogram", {"edges": edges, "counts": counts.astype(float)}, {"color": _next(ax)})
    centres = (edges[:-1] + edges[1:]) / 2
    if nargout == 0:
        return None
    return [as2d(counts.astype(float)), as2d(centres)]


@builtin("errorbar")
def bi_errorbar(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    x, y = _vec(args[0]), _vec(args[1])
    err = _vec(args[2]) if len(args) > 2 and not is_text(args[2]) else np.zeros_like(y)
    ax = I.graphics.begin_plot()
    return _ret(I.graphics.add_item("errorbar", {"x": x, "y": y, "err": err}, {"color": _next(ax)}), nargout)


@builtin("pie")
def bi_pie(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    values = _vec(args[0]).real
    labels = string_list(args[1]) if len(args) > 1 else []
    I.graphics.begin_plot()
    return _ret(I.graphics.add_item("pie", {"y": values, "labels": labels}, {}), nargout)


@builtin("fill", "patch")
def bi_fill(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    x, y = _vec(args[0]).real, _vec(args[1]).real
    rest = list(args[2:])
    color_arg = None
    if rest and not is_text(rest[0]):
        color_arg = color_from_spec(rest.pop(0))
    props = parse_pairs(rest)
    ax = I.graphics.begin_plot()
    color = color_arg or color_from_spec(props.get("facecolor")) or _next(ax)
    return _ret(I.graphics.add_item("fill", {"x": x, "y": y}, {"color": color}), nargout)


@builtin("fplot")
def bi_fplot(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    lims = _vec(args[1]).real if len(args) > 1 and not is_text(args[1]) else np.array([-5.0, 5.0])
    if lims.size != 2:
        raise MatlabError("fplot: second argument must be [xmin xmax].")
    x = np.linspace(lims[0], lims[1], 400)
    values = _function_values(I, args[0], x)
    ax = I.graphics.begin_plot()
    return _ret(I.graphics.add_item("line", {"x": x, "y": values},
                                    {"color": _next(ax), "linestyle": "-", "marker": "none", "linewidth": 0.5}), nargout)


def _function_values(I: Any, f: Any, x: np.ndarray) -> np.ndarray:
    try:
        out = I.call_function(f, [as2d(x.reshape(1, -1))], 1)
        values = np.real(_arr(out[0])).ravel()
        if values.size == x.size:
            return values
    except MatlabError:
        pass
    return np.array([float(np.real(_arr(I.call_function(f, [as2d(np.array([[v]]))], 1)[0]).ravel()[0])) for v in x])


def _grid_args(args: list[Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(args) >= 3:
        X, Y, Z = _arr(args[0]).astype(float), _arr(args[1]).astype(float), _arr(args[2]).astype(float)
        if X.ndim == 2 and X.shape[0] == 1 and Y.shape[1] == 1:
            X, Y = np.meshgrid(X.ravel(), Y.ravel())
        return X, Y, Z
    Z = _arr(args[0]).astype(float)
    X, Y = np.meshgrid(np.arange(1, Z.shape[1] + 1, dtype=float), np.arange(1, Z.shape[0] + 1, dtype=float))
    return X, Y, Z


def _surface(kind: str, is_3d: bool = True) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1)
        numeric = [a for a in args if not is_text(a)]
        X, Y, Z = _grid_args(numeric)
        ax = I.graphics.begin_plot(is_3d=is_3d)
        ax.view = ax.view or (-37.5, 30.0)
        return _ret(I.graphics.add_item(kind, {"X": X, "Y": Y, "Z": Z}, {}), nargout)
    return fn


builtin("surf", "surfc")(_surface("surf"))
builtin("mesh", "meshc")(_surface("mesh"))


@builtin("waterfall")
def bi_waterfall(I: Any, args: list[Any], nargout: int) -> Any:
    return _surface("mesh")(I, args, nargout)


def _contour(kind: str, is_3d: bool) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1)
        numeric = [a for a in args if not is_text(a)]
        levels: Any = 10
        grid_args = numeric[:3] if len(numeric) >= 3 else numeric[:1]
        if len(numeric) in (2, 4):
            spec_levels = _vec(numeric[-1]).real
            levels = spec_levels if spec_levels.size > 1 else int(spec_levels[0])
        X, Y, Z = _grid_args(grid_args)
        I.graphics.begin_plot(is_3d=is_3d)
        return _ret(I.graphics.add_item(kind, {"X": X, "Y": Y, "Z": Z}, {"levels": levels}), nargout)
    return fn


builtin("contour")(_contour("contour", False))
builtin("contourf")(_contour("contourf", False))
builtin("contour3")(_contour("contour", True))


def _image(kind: str, equal: bool) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1)
        numeric = [a for a in args if not is_text(a)]
        if len(numeric) >= 3:
            xr = _vec(numeric[0]).real
            yr = _vec(numeric[1]).real
            Z = _arr(numeric[2]).astype(float)
        else:
            Z = _arr(numeric[0]).astype(float)
            xr = np.arange(1, Z.shape[1] + 1, dtype=float)
            yr = np.arange(1, Z.shape[0] + 1, dtype=float)
        ax = I.graphics.begin_plot()
        ax.reverse_y = True
        if equal:
            ax.axis_mode = "image"
        return _ret(I.graphics.add_item(kind, {"Z": Z, "xr": xr, "yr": yr}, {}), nargout)
    return fn


builtin("imagesc")(_image("imagesc", False))
builtin("image")(_image("imagesc", True))


@builtin("pcolor")
def bi_pcolor(I: Any, args: list[Any], nargout: int) -> Any:
    X, Y, Z = _grid_args([a for a in args if not is_text(a)])
    I.graphics.begin_plot()
    return _ret(I.graphics.add_item("pcolor", {"X": X, "Y": Y, "Z": Z}, {}), nargout)


@builtin("quiver")
def bi_quiver(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 4)
    X, Y, U, V = (_arr(args[k]).astype(float) for k in range(4))
    ax = I.graphics.begin_plot()
    return _ret(I.graphics.add_item("quiver", {"X": X, "Y": Y, "U": U, "V": V}, {"color": _next(ax)}), nargout)


@builtin("polarplot")
def bi_polarplot(I: Any, args: list[Any], nargout: int) -> Any:
    series, _ = _split_series(args)
    ax = I.graphics.begin_plot(polar=True)
    handles = []
    for theta, r, style in series:
        spec = parse_linespec(style) if style else None
        xs, Y = _columns(theta, r)
        for col in range(Y.shape[1]):
            color = (spec or {}).get("color") or _next(ax)
            handles.append(I.graphics.add_item("line", {"x": xs, "y": Y[:, col]},
                                               {"color": color, "linestyle": (spec or {}).get("linestyle") or "-",
                                                "marker": (spec or {}).get("marker") or "none", "linewidth": 0.5,
                                                "markersize": 6}))
    return _ret(handles[-1] if handles else None, nargout)


@builtin("xline")
def bi_xline(I: Any, args: list[Any], nargout: int) -> Any:
    return _reference_line(I, "xline", args, nargout)


@builtin("yline")
def bi_yline(I: Any, args: list[Any], nargout: int) -> Any:
    return _reference_line(I, "yline", args, nargout)


def _reference_line(I: Any, kind: str, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    value = float(_vec(args[0]).real[0])
    label = text(args[1]) if len(args) > 1 and is_text(args[1]) else ""
    I.graphics.gca()
    handle = I.graphics.add_item(kind, {"v": value, "s": label}, {"color": COLOR_ORDER[0]})
    return _ret(handle, nargout)


@builtin("text")
def bi_text(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3)
    I.graphics.gca()
    return _ret(I.graphics.add_item("text", {"x": float(_vec(args[0])[0].real), "y": float(_vec(args[1])[0].real),
                                             "s": text(args[2])}, {}), nargout)


# ---------- figuras, ejes y ajustes ----------

@builtin("figure")
def bi_figure(I: Any, args: list[Any], nargout: int) -> Any:
    number = None
    rest = list(args)
    if rest and not is_text(rest[0]):
        number = ival(rest[0])
        rest = rest[1:]
    props = parse_pairs(rest)
    fig = I.graphics.figure(number, name=props.get("name", ""))
    return _ret(float(fig.number), nargout)


@builtin("gcf")
def bi_gcf(I: Any, args: list[Any], nargout: int) -> Any:
    return float(I.graphics.gcf().number)


@builtin("gca")
def bi_gca(I: Any, args: list[Any], nargout: int) -> Any:
    fig = I.graphics.gcf()
    I.graphics._ensure_axes(fig)
    return float(fig.number) + float(fig.current or 0) / 1000.0


@builtin("clf")
def bi_clf(I: Any, args: list[Any], nargout: int) -> Any:
    I.graphics.clf()
    return None


@builtin("cla")
def bi_cla(I: Any, args: list[Any], nargout: int) -> Any:
    I.graphics.cla()
    return None


@builtin("close")
def bi_close(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        I.graphics.close("current")
    elif is_text(args[0]):
        I.graphics.close(text(args[0]))
    else:
        I.graphics.close(ival(args[0]))
    return None


@builtin("subplot")
def bi_subplot(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 3)
    if len(args) == 1:
        code = ival(args[0])
        rows, cols, index = code // 100, (code // 10) % 10, np.array([code % 10])
    else:
        rows, cols, index = ival(args[0]), ival(args[1]), _vec(args[2]).real
    I.graphics.subplot(rows, cols, index)
    return None


@builtin("tiledlayout")
def bi_tiledlayout(I: Any, args: list[Any], nargout: int) -> Any:
    if args and is_text(args[0]) and text(args[0]).lower() == "flow":
        I.graphics.tiledlayout("flow")
    elif len(args) >= 2:
        I.graphics.tiledlayout(ival(args[0]), ival(args[1]))
    else:
        raise MatlabError("tiledlayout requires rows and columns or 'flow'.")
    return None


@builtin("nexttile")
def bi_nexttile(I: Any, args: list[Any], nargout: int) -> Any:
    index = ival(args[0]) if args and not is_text(args[0]) else None
    I.graphics.nexttile(index)
    return None


@builtin("hold")
def bi_hold(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        I.graphics.set_hold(not I.graphics.gca().hold)
    else:
        mode = text(args[0]).lower()
        if mode not in ("on", "off", "all", "reset"):
            raise MatlabError(f"Invalid argument for hold: '{mode}'.")
        I.graphics.set_hold(mode != "off" and mode != "reset")
    return None


@builtin("grid")
def bi_grid(I: Any, args: list[Any], nargout: int) -> Any:
    ax = I.graphics.gca()
    mode = text(args[0]).lower() if args else "toggle"
    if mode == "minor":
        ax.minor_grid = True
    elif mode == "toggle":
        ax.grid = not ax.grid
    else:
        ax.grid = mode == "on"
    I.graphics.touch()
    return None


@builtin("box")
def bi_box(I: Any, args: list[Any], nargout: int) -> Any:
    ax = I.graphics.gca()
    mode = text(args[0]).lower() if args else "toggle"
    ax.box = (not ax.box if ax.box is not None else False) if mode == "toggle" else mode == "on"
    I.graphics.touch()
    return None


def _label_setter(attr: str) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 1)
        ax = I.graphics.gca()
        setattr(ax, attr, text(args[0]))
        I.graphics.touch()
        return None
    return fn


for _name, _attr in (("title", "title"), ("subtitle", "subtitle"), ("xlabel", "xlabel"),
                     ("ylabel", "ylabel"), ("zlabel", "zlabel")):
    builtin(_name)(_label_setter(_attr))


@builtin("sgtitle")
def bi_sgtitle(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    I.graphics.gcf().sgtitle = text(args[0])
    I.graphics.touch()
    return None


@builtin("legend")
def bi_legend(I: Any, args: list[Any], nargout: int) -> Any:
    ax = I.graphics.gca()
    keywords = {"location", "visible", "show", "hide", "off", "on"}
    labels: list[str] = []
    location = "best"
    visible = True
    i = 0
    while i < len(args):
        token = text(args[i]).lower() if is_text(args[i]) else None
        if token == "location" and i + 1 < len(args):
            location = text(args[i + 1]).lower()
            i += 2
            continue
        if token in ("off", "hide"):
            visible = False
        elif token in ("on", "show"):
            visible = True
        elif token is not None and token not in keywords:
            labels.append(text(args[i]))
        i += 1
    ax.legend = {"labels": labels, "location": location, "visible": visible}
    I.graphics.touch()
    return None


@builtin("axis")
def bi_axis(I: Any, args: list[Any], nargout: int) -> Any:
    ax = I.graphics.gca()
    if not args:
        return None
    if not is_text(args[0]):
        lims = _vec(args[0]).real
        if lims.size in (4, 6):
            ax.xlim = (float(lims[0]), float(lims[1]))
            ax.ylim = (float(lims[2]), float(lims[3]))
            if lims.size == 6:
                ax.zlim = (float(lims[4]), float(lims[5]))
    else:
        mode = text(args[0]).lower()
        if mode == "ij":
            ax.reverse_y = True
        elif mode == "xy":
            ax.reverse_y = False
        elif mode == "auto":
            ax.xlim = ax.ylim = ax.zlim = None
        elif mode == "on":
            ax.box = True
        elif mode in ("off", "equal", "tight", "square", "image", "normal"):
            ax.axis_mode = mode
    I.graphics.touch()
    return None


def _limit_fn(axis_attr: str) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        ax = I.graphics.gca()
        if not args:
            current = getattr(ax, axis_attr)
            if current is None:
                return _ret(np.array([[0.0, 1.0]]), nargout)
            return _ret(np.array([[current[0], current[1]]], dtype=float), nargout)
        lims = _vec(args[0]).real
        if lims.size != 2:
            raise MatlabError(f"{axis_attr[:1]}lim: limits must be a 2-element vector.")
        setattr(ax, axis_attr, (float(lims[0]), float(lims[1])))
        I.graphics.touch()
        return None
    return fn


builtin("xlim")(_limit_fn("xlim"))
builtin("ylim")(_limit_fn("ylim"))
builtin("zlim")(_limit_fn("zlim"))


@builtin("colormap")
def bi_colormap(I: Any, args: list[Any], nargout: int) -> Any:
    ax = I.graphics.gca()
    if args and is_text(args[0]):
        ax.colormap = text(args[0]).lower()
        I.graphics.touch()
    return None


@builtin("colorbar")
def bi_colorbar(I: Any, args: list[Any], nargout: int) -> Any:
    I.graphics.gca().colorbar = True
    I.graphics.touch()
    return None


@builtin("clim")
def bi_clim(I: Any, args: list[Any], nargout: int) -> Any:
    if args:
        lims = _vec(args[0]).real
        I.graphics.gca().clim = (float(lims[0]), float(lims[1]))
        I.graphics.touch()
    return None


@builtin("shading")
def bi_shading(I: Any, args: list[Any], nargout: int) -> Any:
    return None


@builtin("view")
def bi_view(I: Any, args: list[Any], nargout: int) -> Any:
    ax = I.graphics.gca()
    if not args:
        return _ret(np.array([[ax.view[0], ax.view[1]]]) if ax.view else np.array([[-37.5, 30.0]]), nargout)
    if len(args) == 1 and not is_text(args[0]) and _vec(args[0]).size == 1:
        ax.view = (0.0, 90.0) if ival(args[0]) == 2 else (-37.5, 30.0)
    else:
        ax.view = (float(_vec(args[0]).real[0]), float(_vec(args[1]).real[0]))
    I.graphics.touch()
    return None


def _noop(I: Any, args: list[Any], nargout: int) -> Any:
    return None


for _name in ("drawnow", "shg", "refresh", "more_graphics_noop"):
    builtin(_name)(_noop)


def _target_figure(I: Any, args: list[Any]) -> tuple[Any, str | None]:
    """Primer argumento opcional de figura/eje y ruta de salida (último texto)."""
    fig = I.graphics.gcf()
    numeric = [a for a in args if not is_text(a)]
    if numeric and _vec(numeric[0]).size == 1 and float(_vec(numeric[0]).real[0]) in I.graphics.figures:
        fig = I.graphics.figures[int(_vec(numeric[0]).real[0])]
    texts = [text(a) for a in args if is_text(a)]
    return fig, (texts[-1] if texts else None)


def _write_figure(I: Any, fig: Any, name: str, default_ext: str = ".png") -> str:
    path = Path(name)
    if not path.suffix:
        path = path.with_suffix(default_ext)
    safe = Path(path.name)
    if safe.suffix.lower() not in FIGURE_EXTENSIONS:
        raise MatlabError(f"Unsupported figure format '{safe.suffix}'.")
    target = Path(I.folder) / safe.name
    previous = I.graphics.current
    I.graphics.current = fig.number
    try:
        I.graphics.save(fig.number, target)
    finally:
        I.graphics.current = previous
    I.events.append({"type": "file_written", "file": safe.name})
    return safe.name


@builtin("saveas")
def bi_saveas(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    fig, _ = _target_figure(I, args[:1])
    _write_figure(I, fig, text(args[1]))
    return None


@builtin("exportgraphics")
def bi_exportgraphics(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    fig, _ = _target_figure(I, args[:1])
    _write_figure(I, fig, text(args[1]))
    return None


@builtin("print")
def bi_print(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    texts = [text(a) for a in args if is_text(a)]
    fig = I.graphics.gcf()
    target = texts[-1] if texts else "figure"
    driver = next((t for t in texts if t.startswith("-d")), "-dpng")
    ext = {"-dpng": ".png", "-dsvg": ".svg", "-dpdf": ".pdf", "-djpeg": ".jpg"}.get(driver, ".png")
    _write_figure(I, fig, target, ext)
    return None


# ---------- colormaps con nombre ----------

def _colormap_name(name: str) -> Any:
    def fn(I: Any, args: list[Any], nargout: int) -> Any:
        return name
    return fn


for _name in ("parula", "jet", "hot", "cool", "gray", "turbo", "hsv", "spring", "summer", "autumn", "winter",
              "bone", "copper", "pink", "lines"):
    builtin(_name)(_colormap_name(_name))
