"""
Motor Handle Graphics del clon (figuras, ejes, items y render con Matplotlib en Agg).

Modelo: Graphics -> Figure (con grid de subplots o tiledlayout) -> Axes -> Item.
Cada cambio incrementa Figure.version; el render se cachea por versión, tamaño, dpr y tema.
"""

from __future__ import annotations

import base64
import io
import math
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure as MplFigure  # noqa: E402
from matplotlib.mathtext import MathTextParser  # noqa: E402

from backend.hg_colormaps import get_colormap  # noqa: E402

COLOR_ORDER = [
    (0.0, 0.4470, 0.7410), (0.8500, 0.3250, 0.0980), (0.9290, 0.6940, 0.1250), (0.4940, 0.1840, 0.5560),
    (0.4660, 0.6740, 0.1880), (0.3010, 0.7450, 0.9330), (0.6350, 0.0780, 0.1840),
]
LETTER_COLORS = {
    "r": (1.0, 0.0, 0.0), "g": (0.0, 1.0, 0.0), "b": (0.0, 0.0, 1.0), "c": (0.0, 1.0, 1.0),
    "m": (1.0, 0.0, 1.0), "y": (1.0, 1.0, 0.0), "k": (0.0, 0.0, 0.0), "w": (1.0, 1.0, 1.0),
}
NAMED_COLORS = {
    "red": "r", "green": "g", "blue": "b", "cyan": "c", "magenta": "m", "yellow": "y",
    "black": "k", "white": "w",
}
LINE_STYLES = ("--", "-.", "-", ":")
MARKER_CHARS = "o+*.xsd^v><ph"
LEGEND_LOCATIONS = {
    "northeast": "upper right", "northwest": "upper left", "southeast": "lower right",
    "southwest": "lower left", "north": "upper center", "south": "lower center", "east": "center right",
    "west": "center left", "best": "best", "bestoutside": "upper left",
}
THEMES = {
    "light": {"fig": "#FFFFFF", "ax": "#FFFFFF", "text": "#262626", "grid": (0.0, 0.0, 0.0, 0.15),
              "pane": (0.94, 0.94, 0.94, 1.0), "spine": "#262626"},
    "dark": {"fig": "#1E1E1E", "ax": "#1E1E1E", "text": "#D9D9D9", "grid": (1.0, 1.0, 1.0, 0.15),
             "pane": (0.14, 0.14, 0.14, 1.0), "spine": "#BFBFBF"},
}
DEFAULT_SIZE = (560, 420)
DATATIP_KINDS = ("line", "scatter", "stem", "stairs", "bar", "area")
SURFACE_KINDS = ("surf", "mesh", "contour", "contourf", "imagesc", "pcolor")


@dataclass
class Item:
    id: int
    kind: str
    data: dict[str, Any]
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class Axes:
    cells: list[int] | None = None
    is_3d: bool = False
    polar: bool = False
    hold: bool = False
    items: list[Item] = field(default_factory=list)
    color_index: int = 0
    title: str = ""
    subtitle: str = ""
    xlabel: str = ""
    ylabel: str = ""
    zlabel: str = ""
    xlim: tuple[float, float] | None = None
    ylim: tuple[float, float] | None = None
    zlim: tuple[float, float] | None = None
    view_xlim: tuple[float, float] | None = None
    view_ylim: tuple[float, float] | None = None
    xscale: str = "linear"
    yscale: str = "linear"
    grid: bool = False
    minor_grid: bool = False
    box: bool | None = None
    axis_mode: str = "normal"
    reverse_y: bool = False
    view: tuple[float, float] | None = None
    colormap: str = "parula"
    clim: tuple[float, float] | None = None
    colorbar: bool = False
    legend: dict[str, Any] | None = None


@dataclass
class Figure:
    number: int
    name: str = ""
    axes: list[Axes] = field(default_factory=list)
    current: int | None = None
    grid: tuple[int, int] | None = None
    tiled: str | None = None
    next_tile: int = 1
    sgtitle: str = ""
    version: int = 0
    visible: bool = True


def _tex(text: str) -> str:
    """Convierte texto con TeX básico (^, _, \\alpha) a mathtext seguro; si no parsea, texto plano."""
    if not re.search(r"[\\^_]", text):
        return text
    candidate = "$" + text.replace("$", r"\$").replace(" ", r"\ ") + "$"
    try:
        MathTextParser("agg").parse(candidate)
        return candidate
    except Exception:  # noqa: BLE001 - cualquier fallo de mathtext cae a texto plano
        return text


def _font_family() -> str:
    names = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in ("Arial", "Helvetica"):
        if candidate in names:
            return candidate
    return "DejaVu Sans"


def color_from_spec(value: Any) -> tuple[float, float, float] | None:
    """Acepta letra/nombre ('red'), '#RRGGBB' o vector RGB (ya convertido a tupla)."""
    if value is None:
        return None
    if isinstance(value, (tuple, list, np.ndarray)):
        arr = [float(v) for v in np.ravel(value)]
        if len(arr) == 3:
            return (arr[0], arr[1], arr[2])
        return None
    text = str(value).strip().lower()
    if text in ("none", "auto", "flat", ""):
        return None
    if text.startswith("#") and len(text) == 7:
        return tuple(int(text[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]
    if text in NAMED_COLORS:
        return LETTER_COLORS[NAMED_COLORS[text]]
    if text in LETTER_COLORS:
        return LETTER_COLORS[text]
    return None


def parse_linespec(spec: str) -> dict[str, Any] | None:
    """'r--o' -> color, estilo y marcador; devuelve None si no es una especificación válida."""
    if not spec or not re.fullmatch(r"[rgbcmykw:\-.+*ox sd^v><ph]*", spec.lower()):
        return None
    text = spec.lower()
    out: dict[str, Any] = {"color": None, "linestyle": None, "marker": None}
    i = 0
    while i < len(text):
        matched = False
        for style in LINE_STYLES:
            if text.startswith(style, i):
                out["linestyle"] = style
                i += len(style)
                matched = True
                break
        if matched:
            continue
        ch = text[i]
        if ch in LETTER_COLORS:
            out["color"] = LETTER_COLORS[ch]
        elif ch in MARKER_CHARS:
            out["marker"] = ch
        i += 1
    if out["linestyle"] is None and out["marker"] is not None:
        out["linestyle"] = "none"
    return out


def _next_color(ax: Axes) -> tuple[float, float, float]:
    color = COLOR_ORDER[ax.color_index % len(COLOR_ORDER)]
    ax.color_index += 1
    return color


def _data_range(values: list[np.ndarray]) -> tuple[float, float] | None:
    flat = [np.asarray(v, dtype=float).ravel() for v in values if v is not None and np.size(v)]
    if not flat:
        return None
    joined = np.concatenate(flat)
    joined = joined[np.isfinite(joined)]
    if joined.size == 0:
        return None
    lo, hi = float(joined.min()), float(joined.max())
    if lo == hi:
        return lo - 0.5, hi + 0.5
    pad = (hi - lo) * 0.05
    return lo - pad, hi + pad


class HandleGraphicsEngine:
    """Gestor de figuras. Las funciones de MATLAB se traducen a estas operaciones."""

    def __init__(self, theme: str = "light") -> None:
        self.figures: dict[int, Figure] = {}
        self.current: int | None = None
        self.theme = theme
        self._cache: dict[tuple, dict[str, Any]] = {}
        self._items: dict[int, tuple[int, int, Item]] = {}
        self._next_item = 1

    # ---------- figuras y ejes ----------

    def figure(self, number: int | None = None, name: str = "") -> Figure:
        if number is None:
            number = max(self.figures.keys(), default=0) + 1
        number = int(number)
        if number not in self.figures:
            self.figures[number] = Figure(number=number, name=name or f"Figure {number}")
        elif name:
            self.figures[number].name = name
        self.current = number
        return self.figures[number]

    def gcf(self) -> Figure:
        if self.current is None or self.current not in self.figures:
            return self.figure(1)
        return self.figures[self.current]

    def _ensure_axes(self, fig: Figure) -> int:
        if fig.current is None or fig.current >= len(fig.axes):
            fig.axes.append(Axes(cells=None))
            fig.current = len(fig.axes) - 1
        return fig.current

    def gca(self) -> Axes:
        fig = self.gcf()
        return fig.axes[self._ensure_axes(fig)]

    def touch(self, fig: Figure | None = None) -> None:
        (fig or self.gcf()).version += 1

    def clf(self) -> None:
        fig = self.gcf()
        fig.axes.clear()
        fig.current = None
        fig.grid = None
        fig.tiled = None
        fig.next_tile = 1
        fig.sgtitle = ""
        self.touch(fig)

    def cla(self) -> None:
        ax = self.gca()
        ax.items.clear()
        ax.color_index = 0
        self.touch()

    def close(self, target: str | int = "current") -> None:
        if isinstance(target, str) and target.lower() == "all":
            self.figures.clear()
            self.current = None
        elif isinstance(target, str) and target.lower() == "current":
            if self.current is not None:
                self.figures.pop(self.current, None)
                self.current = max(self.figures.keys(), default=None)
        else:
            number = int(target)
            self.figures.pop(number, None)
            if self.current == number:
                self.current = max(self.figures.keys(), default=None)

    def subplot(self, rows: int, cols: int, index: Any) -> int:
        """Selecciona (o crea) el eje en la celda(s) indicadas; devuelve su índice en la figura."""
        fig = self.gcf()
        cells = sorted({int(i) for i in np.ravel(index)})
        if any(c < 1 or c > rows * cols for c in cells):
            raise ValueError("subplot index out of range")
        fig.grid = (int(rows), int(cols))
        fig.tiled = None
        for pos, ax in enumerate(fig.axes):
            if ax.cells == cells:
                fig.current = pos
                return pos
        fig.axes.append(Axes(cells=cells))
        fig.current = len(fig.axes) - 1
        self.touch(fig)
        return fig.current

    def tiledlayout(self, rows: int | str, cols: int | None = None) -> None:
        fig = self.gcf()
        fig.axes.clear()
        fig.current = None
        fig.next_tile = 1
        if isinstance(rows, str):
            fig.tiled, fig.grid = "flow", None
        else:
            fig.tiled, fig.grid = "grid", (int(rows), int(cols or 1))
        self.touch(fig)

    def nexttile(self, index: int | None = None) -> int:
        fig = self.gcf()
        if fig.tiled is None:
            self.tiledlayout("flow")
            fig = self.gcf()
        if index is not None:
            fig.next_tile = int(index)
        tile = fig.next_tile
        for pos, ax in enumerate(fig.axes):
            if ax.cells == [tile]:
                fig.current = pos
                fig.next_tile = tile + 1
                return pos
        fig.axes.append(Axes(cells=[tile]))
        fig.current = len(fig.axes) - 1
        fig.next_tile = tile + 1
        self.touch(fig)
        return fig.current

    def set_hold(self, mode: Any = True) -> bool:
        ax = self.gca()
        if isinstance(mode, str):
            mode = mode.strip().lower() in ("on", "all", "true", "1")
        ax.hold = bool(mode)
        self.touch()
        return ax.hold

    def begin_plot(self, is_3d: bool = False, polar: bool = False) -> Axes:
        ax = self.gca()
        if not ax.hold:
            ax.items.clear()
            ax.color_index = 0
            ax.is_3d = is_3d
            ax.polar = polar
        else:
            ax.is_3d = ax.is_3d or is_3d
            ax.polar = ax.polar or polar
        self.touch()
        return ax

    def add_item(self, kind: str, data: dict[str, Any], props: dict[str, Any] | None = None) -> float:
        """Añade un item al eje actual (la función de plotting debe haber llamado antes a begin_plot)."""
        fig = self.gcf()
        ax = fig.axes[self._ensure_axes(fig)]
        item = Item(self._next_item, kind, data, dict(props or {}))
        self._next_item += 1
        ax.items.append(item)
        self._items[item.id] = (fig.number, fig.current or 0, item)
        self.touch(fig)
        return round(fig.number + item.id / 10000.0, 4)

    def add_line(self, x: Any, y: Any, style: str = "", **props: Any) -> float:
        """Línea simple (usada por la API de Simulink y por plot)."""
        spec = parse_linespec(style) or {"color": None, "linestyle": "-", "marker": None}
        ax = self.begin_plot()
        color = spec["color"] or _next_color(ax)
        merged = {"color": color, "linestyle": spec["linestyle"] or "-", "marker": spec["marker"] or "none",
                  "linewidth": 0.5, "markersize": 6, "label": props.pop("DisplayName", "")}
        merged.update(props)
        return self.add_item("line", {"x": np.asarray(x, float).ravel(), "y": np.asarray(y, float).ravel()},
                             merged)

    # ---------- interacción ----------

    def set_axes_limits(self, number: int, axes_index: int, xlim: Any, ylim: Any) -> None:
        ax = self._axes(number, axes_index)
        if xlim is not None:
            ax.view_xlim = (float(xlim[0]), float(xlim[1]))
        if ylim is not None:
            ax.view_ylim = (float(ylim[0]), float(ylim[1]))
        self.touch(self.figures[number])

    def reset_axes_view(self, number: int, axes_index: int | None = None) -> None:
        fig = self.figures[number]
        targets = fig.axes if axes_index is None else [self._axes(number, axes_index)]
        for ax in targets:
            ax.view_xlim = None
            ax.view_ylim = None
            ax.view = None if ax.is_3d else ax.view
        self.touch(fig)

    def set_view(self, number: int, axes_index: int, az: float, el: float) -> None:
        ax = self._axes(number, axes_index)
        ax.view = (float(az), float(el))
        self.touch(self.figures[number])

    def _axes(self, number: int, axes_index: int) -> Axes:
        fig = self.figures.get(number)
        if fig is None:
            raise KeyError(number)
        if axes_index < 1 or axes_index > len(fig.axes):
            raise IndexError("axes index out of range")
        return fig.axes[axes_index - 1]

    def datatip(self, number: int, axes_index: int, x: float, y: float) -> dict[str, Any]:
        ax = self._axes(number, axes_index)
        best: dict[str, Any] | None = None
        best_dist = math.inf
        xr = ax.view_xlim or ax.xlim or self._extent(ax, "x")
        yr = ax.view_ylim or ax.ylim or self._extent(ax, "y")
        if xr is None or yr is None:
            return {"found": False}
        xs_span = _span(xr, ax.xscale)
        ys_span = _span(yr, ax.yscale)
        for pos, item in enumerate(ax.items):
            if item.kind in SURFACE_KINDS:
                cand = _nearest_vertex(item, x, y, xs_span, ys_span, ax)
            elif item.kind in DATATIP_KINDS:
                cand = _nearest_point(item, x, y, xs_span, ys_span, ax)
            else:
                continue
            if cand and cand["dist"] < best_dist:
                best_dist = cand["dist"]
                best = {**cand, "series": item.props.get("label") or f"data{pos + 1}",
                        "color": _hex(item.props.get("color", COLOR_ORDER[0])), "index": cand["index"]}
        if best is None:
            return {"found": False}
        best.pop("dist", None)
        return {"found": True, **best}

    def _extent(self, ax: Axes, axis: str) -> tuple[float, float] | None:
        values: list[np.ndarray] = []
        for item in ax.items:
            if axis == "x":
                values.append(item.data.get("x"))
            else:
                values.append(item.data.get("y"))
        return _data_range(values)

    # ---------- render ----------

    def render_all(self, width: int = DEFAULT_SIZE[0], height: int = DEFAULT_SIZE[1]) -> list[dict[str, Any]]:
        return [self.render(n, width, height) for n in sorted(self.figures) if self.figures[n].axes]

    def figure_list(self) -> list[dict[str, Any]]:
        return [{"number": n, "name": f.name, "version": f.version} for n, f in sorted(self.figures.items())]

    def render(self, number: int, width: int = DEFAULT_SIZE[0], height: int = DEFAULT_SIZE[1],
               dpr: float = 1.0, theme: str | None = None) -> dict[str, Any]:
        fig = self.figures[number]
        theme = theme or self.theme
        key = (number, fig.version, width, height, round(dpr, 3), theme)
        if key in self._cache:
            return self._cache[key]
        mfig, boxes = self._build(fig, width, height, theme)
        buf = io.BytesIO()
        FigureCanvasAgg(mfig)
        mfig.savefig(buf, format="png", dpi=100 * dpr, facecolor=THEMES[theme]["fig"])
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        result = {
            "number": number,
            "name": fig.name,
            "version": fig.version,
            "image_data_url": "data:image/png;base64," + data,
            "width": width,
            "height": height,
            "axes": [self._axes_meta(i + 1, ax, boxes[i], width, height) for i, ax in enumerate(fig.axes)],
        }
        self._cache = {k: v for k, v in self._cache.items() if k[0] != number or k[1] == fig.version}
        self._cache[key] = result
        return result

    def save(self, number: int, path: Path, width: int = DEFAULT_SIZE[0], height: int = DEFAULT_SIZE[1],
             theme: str | None = None) -> None:
        fig = self.figures[number]
        theme = theme or self.theme
        mfig, _ = self._build(fig, width, height, theme)
        fmt = path.suffix.lstrip(".").lower()
        FigureCanvasAgg(mfig)
        mfig.savefig(str(path), format=fmt, dpi=150, facecolor=THEMES[theme]["fig"])

    def _axes_meta(self, index: int, ax: Axes, box: tuple[float, float, float, float], w: int, h: int) -> dict[str, Any]:
        left, top, width_f, height_f = box
        return {
            "index": index,
            "bbox_px": [round(left * w, 2), round(top * h, 2), round(width_f * w, 2), round(height_f * h, 2)],
            "xlim": list(ax.view_xlim or ax.xlim or []),
            "ylim": list(ax.view_ylim or ax.ylim or []),
            "zlim": list(ax.zlim or []),
            "xscale": ax.xscale,
            "yscale": ax.yscale,
            "is_3d": ax.is_3d,
            "view": list(ax.view) if ax.view else ([-37.5, 30.0] if ax.is_3d else []),
        }

    def _build(self, fig: Figure, width: int, height: int, theme: str) -> tuple[MplFigure, list[tuple[float, float, float, float]]]:
        colors = THEMES[theme]
        family = _font_family()
        mfig = MplFigure(figsize=(width / 100, height / 100), dpi=100, facecolor=colors["fig"])
        created: list[Any] = []
        with matplotlib.rc_context({"font.family": family, "font.size": 9, "axes.unicode_minus": False}):
            rows, cols = self._grid_shape(fig)
            if fig.axes:
                gs = mfig.add_gridspec(rows, cols, left=0.12, right=0.95, bottom=0.12,
                                       top=0.84 if fig.sgtitle else 0.88, wspace=0.35, hspace=0.5)
            for pos, ax_spec in enumerate(fig.axes):
                cells = self._cells_of(fig, pos, rows, cols)
                r0, r1 = min((c - 1) // cols for c in cells), max((c - 1) // cols for c in cells) + 1
                c0, c1 = min((c - 1) % cols for c in cells), max((c - 1) % cols for c in cells) + 1
                kwargs: dict[str, Any] = {}
                if ax_spec.is_3d:
                    kwargs["projection"] = "3d"
                elif ax_spec.polar:
                    kwargs["projection"] = "polar"
                axis = mfig.add_subplot(gs[r0:r1, c0:c1], **kwargs)
                self._style_axes(axis, ax_spec, colors)
                self._draw_axes(axis, ax_spec, colors)
                created.append(axis)
            if fig.sgtitle:
                mfig.suptitle(_tex(fig.sgtitle), color=colors["text"], fontsize=10, fontweight="bold")
            FigureCanvasAgg(mfig)
            mfig.canvas.draw()
        boxes = []
        for axis in created:
            pos_box = axis.get_position()
            boxes.append((pos_box.x0, 1 - pos_box.y1, pos_box.width, pos_box.height))
        return mfig, boxes

    def _grid_shape(self, fig: Figure) -> tuple[int, int]:
        if fig.tiled == "grid" and fig.grid:
            return fig.grid
        if fig.tiled == "flow":
            n = max(len(fig.axes), 1)
            cols = math.ceil(math.sqrt(n))
            return math.ceil(n / cols), cols
        if fig.grid:
            return fig.grid
        return 1, 1

    def _cells_of(self, fig: Figure, pos: int, rows: int, cols: int) -> list[int]:
        ax = fig.axes[pos]
        if ax.cells is not None:
            return ax.cells
        if fig.tiled == "flow":
            return [pos + 1]
        return [1] if rows * cols == 1 else [pos + 1]

    def _style_axes(self, axis: Any, spec: Axes, colors: dict[str, Any]) -> None:
        text = colors["text"]
        axis.set_facecolor(colors["ax"])
        if not spec.polar:
            axis.tick_params(direction="in", labelsize=9, colors=text, top=not spec.is_3d, right=not spec.is_3d)
        else:
            axis.tick_params(labelsize=9, colors=text)
        for label in (axis.xaxis.label, axis.yaxis.label):
            label.set_color(text)
        if spec.is_3d:
            for pane in (axis.xaxis.pane, axis.yaxis.pane, axis.zaxis.pane):
                pane.set_facecolor(colors["pane"])
                pane.set_edgecolor(colors["grid"][:3] + (0.25,))
        box_on = spec.box if spec.box is not None else not spec.is_3d
        for spine in axis.spines.values():
            spine.set_visible(box_on)
            spine.set_color(colors["spine"])
        if spec.grid and not spec.polar:
            axis.grid(True, which="major", color=colors["grid"], linewidth=0.6)
        if spec.minor_grid and not spec.polar:
            axis.grid(True, which="minor", color=colors["grid"], linewidth=0.3)
        if spec.xscale == "log":
            axis.set_xscale("log")
        if spec.yscale == "log":
            axis.set_yscale("log")
        if spec.reverse_y:
            axis.invert_yaxis()
        if spec.title:
            axis.set_title(_tex(spec.title), fontsize=9 * 1.1, fontweight="bold", color=text)
        if spec.subtitle:
            axis.text(0.5, 1.0, _tex(spec.subtitle), transform=axis.transAxes, ha="center", va="bottom",
                      fontsize=8, color=text)
        if spec.xlabel:
            axis.set_xlabel(_tex(spec.xlabel), fontsize=9, color=text)
        if spec.ylabel:
            axis.set_ylabel(_tex(spec.ylabel), fontsize=9, color=text)
        if spec.is_3d and spec.zlabel:
            axis.set_zlabel(_tex(spec.zlabel), fontsize=9, color=text)
        if spec.is_3d:
            az, el = spec.view or (-37.5, 30.0)
            axis.view_init(elev=el, azim=az)
        if spec.axis_mode == "off":
            axis.set_axis_off()
        elif spec.axis_mode in ("equal", "image"):
            axis.set_aspect("equal", adjustable="box")
        elif spec.axis_mode == "square":
            axis.set_aspect(1.0, adjustable="box")

    def _draw_axes(self, axis: Any, spec: Axes, colors: dict[str, Any]) -> None:
        handles: list[tuple[Any, str]] = []
        mappable = None
        for item in spec.items:
            artist, label, mapp = _draw_item(axis, item, spec, colors)
            if label:
                handles.append((artist, label))
            mappable = mapp or mappable
        view_x = spec.view_xlim or spec.xlim
        view_y = spec.view_ylim or spec.ylim
        if view_x and not spec.polar:
            axis.set_xlim(*view_x)
        if view_y and not spec.polar:
            axis.set_ylim(*view_y)
        if spec.is_3d and spec.zlim:
            axis.set_zlim(*spec.zlim)
        if spec.axis_mode == "tight" and not spec.is_3d:
            axis.autoscale_view(tight=True)
        if spec.legend and spec.legend.get("visible", True) and handles:
            loc = LEGEND_LOCATIONS.get(str(spec.legend.get("location", "best")).lower(), "best")
            labels = spec.legend.get("labels") or [h[1] for h in handles]
            legend = axis.legend([h[0] for h in handles][: len(labels)], labels[: len(handles)], loc=loc,
                                 fontsize=8, frameon=True)
            legend.get_frame().set_facecolor(colors["ax"])
            legend.get_frame().set_edgecolor(colors["spine"])
            for text in legend.get_texts():
                text.set_color(colors["text"])
        if spec.colorbar and mappable is not None:
            cb = axis.figure.colorbar(mappable, ax=axis, fraction=0.046, pad=0.04)
            cb.ax.tick_params(colors=colors["text"], labelsize=9)
            cb.outline.set_edgecolor(colors["spine"])
        if spec.clim and mappable is not None:
            mappable.set_clim(*spec.clim)


def _span(limits: tuple[float, float], scale: str) -> float:
    lo, hi = limits
    if scale == "log" and lo > 0 and hi > 0:
        return max(math.log10(hi) - math.log10(lo), 1e-12)
    return max(hi - lo, 1e-12)


def _hex(color: Any) -> str:
    rgb = color_from_spec(color) or COLOR_ORDER[0]
    return "#%02X%02X%02X" % tuple(int(round(c * 255)) for c in rgb)


def _nearest_point(item: Item, x: float, y: float, xs: float, ys: float, ax: Axes) -> dict[str, Any] | None:
    xs_arr = np.asarray(item.data.get("x", []), float).ravel()
    ys_arr = np.asarray(item.data.get("y", []), float).ravel()
    n = min(xs_arr.size, ys_arr.size)
    if n == 0:
        return None
    px, py = xs_arr[:n], ys_arr[:n]
    tx, ty = (np.log10(np.where(px > 0, px, np.nan)), np.log10(np.where(py > 0, py, np.nan))) if ax.xscale == "log" else (px, py)
    qx, qy = (math.log10(x) if ax.xscale == "log" and x > 0 else x), (math.log10(y) if ax.yscale == "log" and y > 0 else y)
    with np.errstate(invalid="ignore"):
        dist = np.hypot((tx - qx) / xs, (ty - qy) / ys)
    if np.all(np.isnan(dist)):
        return None
    k = int(np.nanargmin(dist))
    return {"dist": float(dist[k]), "x": float(px[k]), "y": float(py[k]), "index": k + 1}


def _nearest_vertex(item: Item, x: float, y: float, xs: float, ys: float, ax: Axes) -> dict[str, Any] | None:
    X = np.asarray(item.data.get("X", item.data.get("x")), float)
    Y = np.asarray(item.data.get("Y", item.data.get("y")), float)
    Z = np.asarray(item.data.get("Z", item.data.get("z")), float)
    if X.ndim == 1 and Y.ndim == 1 and Z.ndim == 2:
        X, Y = np.meshgrid(X, Y)
    if X.shape != Y.shape or X.shape != Z.shape:
        return None
    dist = np.hypot((X - x) / xs, (Y - y) / ys)
    k = int(np.argmin(dist))
    r, c = np.unravel_index(k, X.shape)
    return {"dist": float(dist[r, c]), "x": float(X[r, c]), "y": float(Y[r, c]), "z": float(Z[r, c]),
            "index": int(k + 1)}


def _draw_item(axis: Any, item: Item, spec: Axes, colors: dict[str, Any]) -> tuple[Any, str, Any]:
    p = item.props
    d = item.data
    label = str(p.get("label", "") or "")
    color = p.get("color", COLOR_ORDER[0])
    kind = item.kind
    if kind == "line":
        if spec.polar:
            artist, = axis.plot(d["x"], d["y"], color=color, linestyle=p.get("linestyle", "-"),
                                marker=p.get("marker", "none"), linewidth=p.get("linewidth", 0.5),
                                markersize=p.get("markersize", 6))
        elif "z" in d:
            artist, = axis.plot(d["x"], d["y"], d["z"], color=color, linestyle=p.get("linestyle", "-"),
                                marker=p.get("marker", "none"), linewidth=p.get("linewidth", 0.5))
        else:
            artist, = axis.plot(d["x"], d["y"], color=color, linestyle=p.get("linestyle", "-"),
                                marker=p.get("marker", "none"), linewidth=p.get("linewidth", 0.5),
                                markersize=p.get("markersize", 6),
                                markerfacecolor=color_from_spec(p.get("MarkerFaceColor")) or color,
                                markeredgecolor=color_from_spec(p.get("MarkerEdgeColor")) or color)
        return artist, label, None
    if kind == "scatter":
        size = float(p.get("size", 36))
        cdata = d.get("c")
        marker = p.get("marker", "o")
        if cdata is not None and np.size(cdata) == np.size(d["x"]) and np.size(cdata) > 1:
            if spec.is_3d:
                artist = axis.scatter(d["x"], d["y"], d["z"], c=cdata, s=size, cmap=get_colormap(spec.colormap), marker=marker)
            else:
                artist = axis.scatter(d["x"], d["y"], c=cdata, s=size, cmap=get_colormap(spec.colormap), marker=marker)
            return artist, label, artist
        face = p.get("face", color)
        edge = "none" if p.get("filled") else color
        if spec.is_3d and "z" in d:
            artist = axis.scatter(d["x"], d["y"], d["z"], s=size, color=face, edgecolors=edge, marker=marker)
        else:
            artist = axis.scatter(d["x"], d["y"], s=size, color=face, edgecolors=edge, marker=marker)
        return artist, label, None
    if kind == "bar" or kind == "barh":
        x = np.asarray(d["x"], float).ravel()
        Y = np.asarray(d["y"], float)
        Y = Y.reshape(x.size, -1) if Y.ndim > 1 else Y.reshape(-1, 1)
        width = float(p.get("width", 0.8))
        stacked = bool(p.get("stacked", False))
        groups = Y.shape[1]
        artist = None
        bottom = np.zeros(x.size)
        for g in range(groups):
            gc = color if groups == 1 else COLOR_ORDER[g % len(COLOR_ORDER)]
            if stacked:
                pos, w = x, width
            else:
                w = width / groups
                pos = x - width / 2 + w * (g + 0.5)
            fn = axis.bar if kind == "bar" else axis.barh
            kwargs = {"color": gc, "width": w} if kind == "bar" else {"color": gc, "height": w}
            if stacked:
                kwargs["bottom" if kind == "bar" else "left"] = bottom
            artist = fn(pos, Y[:, g], **kwargs)
            if stacked:
                bottom = bottom + Y[:, g]
        return (artist.patches[0] if artist is not None and len(artist.patches) else None), label, None
    if kind == "area":
        axis.fill_between(d["x"], 0, d["y"], color=color, alpha=0.5, linewidth=0)
        artist, = axis.plot(d["x"], d["y"], color=color, linewidth=0.5)
        return artist, label, None
    if kind == "stem":
        axis.vlines(d["x"], 0, d["y"], colors=color, linewidth=0.5)
        artist = axis.plot(d["x"], d["y"], "o", color=color, markersize=4)[0]
        return artist, label, None
    if kind == "stairs":
        artist, = axis.step(d["x"], d["y"], where="post", color=color, linewidth=0.5)
        return artist, label, None
    if kind == "histogram":
        edges = np.asarray(d["edges"], float)
        counts = np.asarray(d["counts"], float)
        artist = axis.bar(edges[:-1], counts, width=np.diff(edges), align="edge", color=p.get("FaceColor", color),
                          edgecolor=p.get("EdgeColor", colors["text"]), linewidth=0.5,
                          alpha=float(p.get("FaceAlpha", 0.6)))
        return artist.patches[0] if len(artist.patches) else None, label, None
    if kind == "errorbar":
        artist = axis.errorbar(d["x"], d["y"], yerr=d.get("err"), color=color, linewidth=0.5, capsize=3)
        return artist.lines[0], label, None
    if kind == "pie":
        wedges, *_ = axis.pie(d["y"], labels=d.get("labels") or None, colors=[COLOR_ORDER[i % 7] for i in range(len(d["y"]))],
                              textprops={"color": colors["text"]})
        return wedges[0], "", None
    if kind == "fill":
        artist = axis.fill(d["x"], d["y"], color=color, alpha=float(p.get("FaceAlpha", 0.5)))[0]
        return artist, label, None
    if kind == "surf":
        artist = axis.plot_surface(d["X"], d["Y"], d["Z"], cmap=get_colormap(spec.colormap), linewidth=0,
                                   antialiased=False, shade=True)
        return artist, label, artist
    if kind == "mesh":
        artist = axis.plot_wireframe(d["X"], d["Y"], d["Z"], color=color, linewidth=0.5, rstride=1, cstride=1)
        return artist, label, None
    if kind in ("contour", "contourf"):
        cmap = get_colormap(spec.colormap)
        levels = int(p.get("levels", 10))
        fn = axis.contour if kind == "contour" else axis.contourf
        artist = fn(d["X"], d["Y"], d["Z"], levels=levels, cmap=cmap)
        return artist, label, artist
    if kind == "imagesc":
        z = np.asarray(d["Z"], float)
        xr = d.get("xr") or (1, z.shape[1])
        yr = d.get("yr") or (1, z.shape[0])
        artist = axis.imshow(z, cmap=get_colormap(spec.colormap), origin="upper", aspect="auto",
                             extent=[xr[0], xr[-1], yr[-1], yr[0]])
        return artist, label, artist
    if kind == "pcolor":
        artist = axis.pcolormesh(d["X"], d["Y"], d["Z"], shading="auto", cmap=get_colormap(spec.colormap))
        return artist, label, artist
    if kind == "quiver":
        artist = axis.quiver(d["X"], d["Y"], d["U"], d["V"], color=color)
        return artist, label, None
    if kind == "text":
        axis.text(float(d["x"]), float(d["y"]), _tex(str(d["s"])), fontsize=9, color=colors["text"])
        return None, "", None
    if kind in ("xline", "yline"):
        if kind == "xline":
            artist = axis.axvline(float(d["v"]), color=color, linewidth=0.8)
        else:
            artist = axis.axhline(float(d["v"]), color=color, linewidth=0.8)
        if d.get("s"):
            axis.text(float(d["v"]), 0.98, _tex(str(d["s"])), transform=axis.get_xaxis_transform() if kind == "xline" else axis.get_yaxis_transform(), fontsize=8, color=colors["text"])
        return artist, label, None
    return None, "", None
