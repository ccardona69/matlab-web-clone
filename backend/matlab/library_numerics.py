"""Álgebra lineal, polinomios, señal, interpolación, optimización, integración y EDOs (solo NumPy)."""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from backend.matlab import ops
from backend.matlab.errors import MatlabError
from backend.matlab.registry import (
    builtin, dbl, default_dim, dim_arg, ival, is_text, nargchk, num, text, tidy,
)
from backend.matlab.values import MStruct, as2d, empty_double, to_double

EPS = float(np.finfo(float).eps)


def _vec(a: Any) -> np.ndarray:
    return np.asarray(dbl(a)).ravel(order="F")


def _col(a: Any) -> np.ndarray:
    return as2d(np.asarray(a).reshape(-1, 1))


def _row(a: Any) -> np.ndarray:
    return as2d(np.asarray(a).reshape(1, -1))


def _call(I: Any, f: Any, *args: Any) -> np.ndarray:
    values = [as2d(np.asarray(a, dtype=float)) if not np.iscomplexobj(a) else as2d(np.asarray(a)) for a in args]
    out = I.call_function(f, values, 1)
    if not out:
        raise MatlabError("Function returned no value.")
    return np.asarray(dbl(out[0]))


def _scalar_fn(I: Any, f: Any) -> Callable[[float], float]:
    def scalar(x: float) -> float:
        return float(np.real(_call(I, f, np.array([[x]], dtype=float)).ravel()[0]))
    return scalar


def _square(a: Any, name: str) -> np.ndarray:
    m = as2d(to_double(a)).astype(complex if np.iscomplexobj(to_double(a)) else float)
    if m.shape[0] != m.shape[1]:
        raise MatlabError("Matrix must be square.", "MATLAB:square")
    return m


# ---------- álgebra lineal ----------

@builtin("inv", "inverse")
def bi_inv(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = _square(args[0], "inv")
    if a.size == 0:
        return empty_double()
    if np.linalg.matrix_rank(a) < a.shape[0]:
        I.warn("Matrix is singular to working precision.", "MATLAB:singularMatrix")
        return np.full(a.shape, np.inf)
    if np.linalg.cond(a) > 1 / EPS:
        I.warn("Matrix is close to singular or badly scaled. Results may be inaccurate. RCOND = %.6e." % (1 / np.linalg.cond(a)), "MATLAB:nearlySingularMatrix")
    return tidy(np.linalg.inv(a))


@builtin("pinv")
def bi_pinv(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    return tidy(np.linalg.pinv(as2d(to_double(args[0]))))


@builtin("det")
def bi_det(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = _square(args[0], "det")
    return float(np.linalg.det(a)) if a.size else 1.0


@builtin("rank")
def bi_rank(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = as2d(to_double(args[0]))
    return float(np.linalg.matrix_rank(a)) if a.size else 0.0


@builtin("trace")
def bi_trace(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return tidy(np.array([[np.trace(_square(args[0], "trace"))]]))


@builtin("cond")
def bi_cond(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = as2d(to_double(args[0]))
    return float(np.linalg.cond(a)) if a.size else 0.0


def _is_hermitian(a: np.ndarray) -> bool:
    return a.shape[0] == a.shape[1] and np.allclose(a, a.conj().T, rtol=0, atol=1e-12 * max(1.0, np.max(np.abs(a))))


@builtin("eig")
def bi_eig(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = _square(args[0], "eig")
    if _is_hermitian(a):
        vals, vecs = np.linalg.eigh(a)
    else:
        vals, vecs = np.linalg.eig(a)
    if nargout <= 1:
        return _col(tidy(vals))
    return [tidy(vecs), tidy(np.diag(vals))]


@builtin("svd")
def bi_svd(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = as2d(to_double(args[0]))
    econ = len(args) > 1
    if nargout <= 1:
        return _col(np.linalg.svd(a, compute_uv=False))
    u, s, vh = np.linalg.svd(a, full_matrices=not econ)
    smat = np.zeros((u.shape[1], vh.shape[0]))
    smat[:s.size, :s.size] = np.diag(s)
    return [u, smat, vh.conj().T]


@builtin("qr")
def bi_qr(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    q, r = np.linalg.qr(as2d(to_double(args[0])))
    return [q, r] if nargout >= 2 else r


def _lu_pivot(a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n, m = a.shape
    u = a.astype(float).copy()
    l_mat = np.eye(n)
    perm = np.eye(n)
    for k in range(min(n, m)):
        p = k + int(np.argmax(np.abs(u[k:, k])))
        if p != k:
            u[[k, p], :] = u[[p, k], :]
            perm[[k, p], :] = perm[[p, k], :]
            l_mat[[k, p], :k] = l_mat[[p, k], :k]
        if u[k, k] == 0:
            continue
        for i in range(k + 1, n):
            l_mat[i, k] = u[i, k] / u[k, k]
            u[i, :] -= l_mat[i, k] * u[k, :]
    return l_mat[:, :min(n, m)], np.triu(u), perm


@builtin("lu")
def bi_lu(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = as2d(to_double(args[0]))
    l_mat, u, perm = _lu_pivot(a)
    if nargout <= 2:
        return [perm.T @ l_mat, u]
    return [l_mat, u, perm]


@builtin("chol")
def bi_chol(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = _square(args[0], "chol")
    try:
        lower = np.linalg.cholesky(a)
    except np.linalg.LinAlgError:
        raise MatlabError("Matrix must be positive definite.", "MATLAB:posdef") from None
    return [lower.conj().T, 0.0] if nargout >= 2 else lower.conj().T


@builtin("expm")
def bi_expm(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = _square(args[0], "expm")
    norm = np.linalg.norm(a, np.inf)
    squarings = max(0, int(math.ceil(math.log2(norm))) + 1) if norm > 0.5 else 0
    scaled = a / (2 ** squarings)
    result = np.eye(a.shape[0], dtype=a.dtype)
    term = np.eye(a.shape[0], dtype=a.dtype)
    for k in range(1, 30):
        term = term @ scaled / k
        result = result + term
    for _ in range(squarings):
        result = result @ result
    return tidy(result)


@builtin("null")
def bi_null(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = as2d(to_double(args[0]))
    _, s, vh = np.linalg.svd(a)
    tol = max(a.shape) * (s[0] if s.size else 0.0) * EPS
    rank = int(np.sum(s > tol))
    return tidy(vh[rank:].conj().T) if a.shape[1] > rank else np.zeros((a.shape[1], 0))


@builtin("orth")
def bi_orth(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = as2d(to_double(args[0]))
    u, s, _ = np.linalg.svd(a)
    tol = max(a.shape) * (s[0] if s.size else 0.0) * EPS
    rank = int(np.sum(s > tol))
    return tidy(u[:, :rank])


@builtin("linsolve")
def bi_linsolve(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    return ops.binop("\\", args[0], args[1])


# ---------- polinomios ----------

@builtin("polyfit")
def bi_polyfit(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3, 3)
    x, y = _vec(args[0]), _vec(args[1])
    if x.size != y.size:
        raise MatlabError(
            "The query points and the fitted values must have the same number of elements.",
            "MATLAB:polyfit:XYSizeMismatch",
        )
    coeffs = np.polyfit(np.real(x), np.real(y), ival(args[2]))
    return _row(coeffs)


@builtin("polyval")
def bi_polyval(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    p = _vec(args[0])
    x = as2d(to_double(args[1]))
    return tidy(np.polyval(p, x))


@builtin("roots")
def bi_roots(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    p = _vec(args[0])
    if p.size == 0:
        return empty_double()
    return _col(tidy(np.roots(p)))


@builtin("poly")
def bi_poly(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    a = as2d(to_double(args[0]))
    coeffs = np.poly(a) if a.shape[0] == a.shape[1] and a.shape[0] > 1 else np.poly(a.ravel())
    return _row(tidy(coeffs))


@builtin("conv")
def bi_conv(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    return _row(tidy(np.convolve(_vec(args[0]), _vec(args[1]), mode="full")))


@builtin("deconv")
def bi_deconv(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 2)
    y, a = _vec(args[0]), _vec(args[1])
    if a.size == 0 or a[0] == 0:
        raise MatlabError("Divisor must have a nonzero leading coefficient.")
    if y.size < a.size:
        return [0.0, _row(y)]
    q, r = np.polydiv(y, a)
    rem = np.zeros(y.size)
    rem[y.size - r.size:] = r
    return [_row(q), _row(rem)] if nargout >= 2 else _row(q)


@builtin("polyder")
def bi_polyder(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    return _row(np.polyder(_vec(args[0])))


@builtin("polyint")
def bi_polyint(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 3)
    k = num(args[1]) if len(args) > 1 else 0.0
    return _row(np.polyint(_vec(args[0]), k=k))


@builtin("filter")
def bi_filter(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3, 5)
    b, a, x = _vec(args[0]), _vec(args[1]), as2d(to_double(args[2]))
    if a.size == 0 or a[0] == 0:
        raise MatlabError("filter: a(1) must be nonzero.")
    b, a = b / a[0], a / a[0]
    n = max(b.size, a.size)
    b = np.pad(b, (0, n - b.size))
    a = np.pad(a, (0, n - a.size))
    shape = x.shape
    xv = x.ravel(order="F")
    y = np.zeros(xv.size)
    for k in range(xv.size):
        acc = 0.0
        for j in range(n):
            if k - j < 0:
                break
            acc += b[j] * xv[k - j]
            if j > 0:
                acc -= a[j] * y[k - j]
        y[k] = acc
    return y.reshape(shape, order="F")


# ---------- transformadas ----------

def _fft_along(args: list[Any], fn: Callable[..., np.ndarray]) -> Any:
    nargchk(args, 1, 3)
    a = as2d(to_double(args[0]))
    n = ival(args[1]) if len(args) > 1 and args[1].size else None
    dim = dim_arg(args[2]) if len(args) > 2 else default_dim(a)
    return fn(a, n=n, axis=dim)


@builtin("fft")
def bi_fft(I: Any, args: list[Any], nargout: int) -> Any:
    return _fft_along(args, np.fft.fft)


@builtin("ifft")
def bi_ifft(I: Any, args: list[Any], nargout: int) -> Any:
    return _fft_along(args, np.fft.ifft)


@builtin("fftshift")
def bi_fftshift(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = as2d(to_double(args[0]))
    return np.fft.fftshift(a)


@builtin("ifftshift")
def bi_ifftshift(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    a = as2d(to_double(args[0]))
    return np.fft.ifftshift(a)


# ---------- interpolación ----------

def _segment_coeffs(x: np.ndarray, y: np.ndarray, method: str) -> np.ndarray:
    n = x.size
    h = np.diff(x)
    slopes = np.diff(y) / h
    if method == "linear":
        coeffs = np.zeros((n - 1, 4))
        coeffs[:, 0] = y[:-1]
        coeffs[:, 1] = slopes
        return coeffs
    if method == "pchip":
        d = _pchip_slopes(x, y, h, slopes)
        coeffs = np.zeros((n - 1, 4))
        coeffs[:, 0] = y[:-1]
        coeffs[:, 1] = d[:-1]
        coeffs[:, 2] = (3 * slopes - 2 * d[:-1] - d[1:]) / h
        coeffs[:, 3] = (d[:-1] + d[1:] - 2 * slopes) / h ** 2
        return coeffs
    m_vals = _not_a_knot_moments(x, y, h)
    coeffs = np.zeros((n - 1, 4))
    coeffs[:, 0] = y[:-1]
    coeffs[:, 1] = slopes - h * (2 * m_vals[:-1] + m_vals[1:]) / 6
    coeffs[:, 2] = m_vals[:-1] / 2
    coeffs[:, 3] = (m_vals[1:] - m_vals[:-1]) / (6 * h)
    return coeffs


def _not_a_knot_moments(x: np.ndarray, y: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = x.size
    if n == 3:
        p = np.polyfit(x, y, 2)
        return np.full(3, 2 * p[0])
    a = np.zeros((n, n))
    rhs = np.zeros(n)
    for i in range(1, n - 1):
        a[i, i - 1] = h[i - 1]
        a[i, i] = 2 * (h[i - 1] + h[i])
        a[i, i + 1] = h[i]
        rhs[i] = 6 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
    a[0, 0], a[0, 1], a[0, 2] = h[1], -(h[0] + h[1]), h[0]
    a[-1, -3], a[-1, -2], a[-1, -1] = h[-1], -(h[-2] + h[-1]), h[-2]
    return np.linalg.solve(a, rhs)


def _pchip_slopes(x: np.ndarray, y: np.ndarray, h: np.ndarray, delta: np.ndarray) -> np.ndarray:
    n = x.size
    d = np.zeros(n)
    for k in range(1, n - 1):
        if delta[k - 1] * delta[k] > 0:
            w1 = 2 * h[k] + h[k - 1]
            w2 = h[k] + 2 * h[k - 1]
            d[k] = (w1 + w2) / (w1 / delta[k - 1] + w2 / delta[k])
    d[0] = _pchip_end(h[0], h[1], delta[0], delta[1])
    d[-1] = _pchip_end(h[-1], h[-2], delta[-1], delta[-2])
    return d


def _pchip_end(h0: float, h1: float, d0: float, d1: float) -> float:
    s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if np.sign(s) != np.sign(d0):
        return 0.0
    if np.sign(d0) != np.sign(d1) and abs(s) > abs(3 * d0):
        return 3 * d0
    return s


def _interp_values(x: np.ndarray, y: np.ndarray, xi: np.ndarray, method: str, extrap: bool) -> np.ndarray:
    if method == "nearest":
        mids = (x[1:] + x[:-1]) / 2
        out = y[np.searchsorted(mids, xi, side="right")]
    else:
        coeffs = _segment_coeffs(x, y, method)
        k = np.clip(np.searchsorted(x, xi, side="right") - 1, 0, x.size - 2)
        t = xi - x[k]
        c = coeffs[k]
        out = c[:, 0] + t * (c[:, 1] + t * (c[:, 2] + t * c[:, 3]))
    if not extrap:
        out = np.where((xi < x[0]) | (xi > x[-1]), np.nan, out)
    return out


@builtin("interp1")
def bi_interp1(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 5)
    rest = list(args)
    if len(args) >= 3 and not is_text(args[2]):
        x, y, xi = _vec(args[0]), _vec(args[1]), as2d(to_double(args[2]))
        if x.size != y.size:
            raise MatlabError("X and V must be of the same length.", "MATLAB:interp1:YVectorInvalidNumRows")
        rest = args[3:]
    else:
        y, xi = _vec(args[0]), as2d(to_double(args[1]))
        x = np.arange(1, y.size + 1, dtype=float)
        rest = args[2:]
    method = "linear"
    extrap = False
    for opt in rest:
        label = text(opt).lower() if is_text(opt) else ""
        if label == "extrap":
            extrap = True
        elif label in ("linear", "nearest", "spline", "pchip", "cubic"):
            method = "pchip" if label == "cubic" else label
    order = np.argsort(x)
    x, y = x[order], y[order]
    if x.size < 2:
        raise MatlabError("interp1 requires at least two sample points.")
    if method == "spline" and x.size == 2:
        method = "linear"
    result = _interp_values(np.real(x), np.real(y), np.real(xi).ravel(order="F"), method, extrap)
    return result.reshape(xi.shape, order="F")


# ---------- raíces y optimización ----------

def _brent_root(f: Callable[[float], float], a: float, b: float, fa: float, fb: float) -> float:
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa
    c, fc = a, fa
    d = b - a
    bisected = True
    for _ in range(200):
        if fb == 0 or abs(b - a) < 1e-15 * max(1.0, abs(b)):
            break
        if fa != fc and fb != fc:
            s = (a * fb * fc / ((fa - fb) * (fa - fc)) + b * fa * fc / ((fb - fa) * (fb - fc))
                 + c * fa * fb / ((fc - fa) * (fc - fb)))
        else:
            s = b - fb * (b - a) / (fb - fa)
        lo, hi = sorted(((3 * a + b) / 4, b))
        if not (lo < s < hi) or (bisected and abs(s - b) >= abs(b - c) / 2) \
                or (not bisected and abs(s - b) >= abs(c - d) / 2) \
                or (bisected and abs(b - c) < 1e-15) or (not bisected and abs(c - d) < 1e-15):
            s = (a + b) / 2
            bisected = True
        else:
            bisected = False
        fs = f(s)
        d, c, fc = c, b, fb
        if fa * fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b, fa, fb = b, a, fb, fa
    return b


def _bracket_root(f: Callable[[float], float], x0: float) -> tuple[float, float] | None:
    f0 = f(x0)
    step = max(abs(x0), 1.0) * 0.02
    for k in range(60):
        for sign in (1.0, -1.0):
            x = x0 + sign * step * (2 ** k)
            fx = f(x)
            if fx == 0:
                return x, x
            if np.sign(fx) != np.sign(f0):
                return (x0, x) if sign > 0 else (x, x0)
    return None


@builtin("fzero")
def bi_fzero(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    f = _scalar_fn(I, args[0])
    start = _vec(args[1])
    if start.size >= 2:
        a, b = float(start[0]), float(start[1])
        fa, fb = f(a), f(b)
        if np.sign(fa) == np.sign(fb) and fa != 0 and fb != 0:
            raise MatlabError("The function must have different signs at the interval endpoints.", "MATLAB:fzero:SignChangeNotFound")
    else:
        x0 = float(start[0])
        bracket = _bracket_root(f, x0)
        if bracket is None:
            raise MatlabError("Exiting fzero: aborting search for an interval containing a sign change because NaN or Inf function value encountered during search.")
        a, b = bracket
        if a == b:
            return [a, f(a), 1.0] if nargout > 1 else a
        fa, fb = f(a), f(b)
    root = a if fa == 0 else (b if fb == 0 else _brent_root(f, a, b, fa, fb))
    if nargout <= 1:
        return root
    return [root, f(root), 1.0]


def _nelder_mead(f: Callable[[np.ndarray], float], x0: np.ndarray, tol_x: float = 1e-4, tol_f: float = 1e-4,
                 max_iter: int = 0) -> np.ndarray:
    n = x0.size
    max_iter = max_iter or 200 * n
    simplex = [x0.copy()]
    for i in range(n):
        point = x0.copy()
        point[i] = point[i] * 1.05 if point[i] != 0 else 0.00025
        simplex.append(point)
    values = [f(p) for p in simplex]
    for _ in range(max_iter):
        order = np.argsort(values)
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        if max(np.max(np.abs(p - simplex[0])) for p in simplex[1:]) <= tol_x and \
                max(abs(v - values[0]) for v in values[1:]) <= tol_f:
            break
        centroid = np.mean(simplex[:-1], axis=0)
        xr = centroid + (centroid - simplex[-1])
        fr = f(xr)
        if fr < values[0]:
            xe = centroid + 2 * (centroid - simplex[-1])
            fe = f(xe)
            if fe < fr:
                simplex[-1], values[-1] = xe, fe
            else:
                simplex[-1], values[-1] = xr, fr
        elif fr < values[-2]:
            simplex[-1], values[-1] = xr, fr
        else:
            if fr < values[-1]:
                xc = centroid + 0.5 * (xr - centroid)
            else:
                xc = centroid + 0.5 * (simplex[-1] - centroid)
            fc = f(xc)
            if fc < min(fr, values[-1]):
                simplex[-1], values[-1] = xc, fc
            else:
                best = simplex[0]
                simplex = [best + 0.5 * (p - best) for p in simplex]
                values = [values[0]] + [f(p) for p in simplex[1:]]
    return simplex[int(np.argmin(values))]


@builtin("fminsearch")
def bi_fminsearch(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2, 3)
    x0 = as2d(to_double(args[1])).astype(float)
    shape = x0.shape

    def objective(v: np.ndarray) -> float:
        out = _call(I, args[0], v.reshape(shape, order="F"))
        return float(np.real(out.ravel()[0]))

    best = _nelder_mead(objective, x0.ravel(order="F"))
    result = best.reshape(shape, order="F")
    if nargout <= 1:
        return result
    return [result, objective(best), 1.0]


@builtin("fminbnd")
def bi_fminbnd(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3, 4)
    f = _scalar_fn(I, args[0])
    a, b = num(args[1]), num(args[2])
    ratio = (math.sqrt(5) - 1) / 2
    c, d = b - ratio * (b - a), a + ratio * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(300):
        if abs(b - a) <= 1e-10 * (abs(a) + abs(b)) + 1e-14:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = f(d)
    x = (a + b) / 2
    if nargout <= 1:
        return x
    return [x, f(x), 1.0]


# ---------- integración ----------

GK_NODES = np.array([0.991455371120813, 0.949107912342759, 0.864864423359769, 0.741531185599394,
                     0.586087235467691, 0.405845151377397, 0.207784955007898, 0.0])
GK_WEIGHTS = np.array([0.022935322010529, 0.063092092629979, 0.104790010322250, 0.140653259715525,
                       0.169004726639267, 0.190350578064785, 0.204432940075298, 0.209482141084728])
G_WEIGHTS = np.array([0.129484966168870, 0.279705391489277, 0.381830050505119, 0.417959183673469])


def _gk15(I: Any, f: Any, a: float, b: float) -> tuple[float, float]:
    half = 0.5 * (b - a)
    centre = 0.5 * (a + b)
    xs = centre + half * np.concatenate([-GK_NODES[:-1], [0.0], GK_NODES[:-1][::-1]])
    ys = np.real(_call(I, f, xs.reshape(1, -1))).ravel()
    if ys.size == 1:
        ys = np.full(xs.size, ys[0])
    if ys.size != xs.size:
        raise MatlabError("Integrand function must return a value with the same size as its input.")
    k15 = ys[7] * GK_WEIGHTS[7] + np.sum(ys[:7] * GK_WEIGHTS[:7]) + np.sum(ys[8:] * GK_WEIGHTS[:7][::-1])
    g7 = ys[7] * G_WEIGHTS[3] + G_WEIGHTS[0:3].dot(ys[[1, 3, 5]] + ys[[13, 11, 9]])
    return k15 * half, abs((k15 - g7) * half)


def _integrate(I: Any, f: Any, a: float, b: float, abs_tol: float, rel_tol: float) -> float:
    intervals = [(a, b) + _gk15(I, f, a, b)]
    for _ in range(650):
        total = sum(seg[2] for seg in intervals)
        err = sum(seg[3] for seg in intervals)
        if err <= max(abs_tol, rel_tol * abs(total)):
            return total
        worst = max(range(len(intervals)), key=lambda i: intervals[i][3])
        lo, hi = intervals.pop(worst)[:2]
        mid = 0.5 * (lo + hi)
        intervals.append((lo, mid) + _gk15(I, f, lo, mid))
        intervals.append((mid, hi) + _gk15(I, f, mid, hi))
    return sum(seg[2] for seg in intervals)


def _quad_builtin(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 3)
    a, b = num(args[1]), num(args[2])
    abs_tol, rel_tol = 1e-10, 1e-6
    for i in range(3, len(args) - 1, 2):
        label = text(args[i]).lower()
        if label == "abstol":
            abs_tol = num(args[i + 1])
        elif label == "reltol":
            rel_tol = num(args[i + 1])
    if math.isinf(a) or math.isinf(b):
        raise MatlabError("integral: infinite limits are not supported by this clon.")
    return _integrate(I, args[0], a, b, abs_tol, rel_tol)


builtin("integral", "quad", "quadgk", "quadl", "quadv")(_quad_builtin)


# ---------- EDOs ----------

DOPRI5 = {
    "c": [0, 1 / 5, 3 / 10, 4 / 5, 8 / 9, 1, 1],
    "a": [
        [],
        [1 / 5],
        [3 / 40, 9 / 40],
        [44 / 45, -56 / 15, 32 / 9],
        [19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729],
        [9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656],
        [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84],
    ],
    "b_high": [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84, 0],
    "b_low": [5179 / 57600, 0, 7571 / 16695, 393 / 640, -92097 / 339200, 187 / 2100, 1 / 40],
    "order": 5,
}

BS23 = {
    "c": [0, 1 / 2, 3 / 4, 1],
    "a": [[], [1 / 2], [0, 3 / 4], [2 / 9, 1 / 3, 4 / 9]],
    "b_high": [2 / 9, 1 / 3, 4 / 9, 0],
    "b_low": [7 / 24, 1 / 4, 1 / 3, 1 / 8],
    "order": 3,
}


def _odeset_options(opts: Any) -> dict[str, float]:
    values = {"RelTol": 1e-3, "AbsTol": 1e-6, "MaxStep": math.inf, "Refine": 4}
    if isinstance(opts, MStruct) and opts.data.size:
        for field in opts.fields:
            for key in values:
                if field.lower() == key.lower():
                    values[key] = float(num(opts.data.flat[0][field]))
    return values


def _rk_solve(I: Any, f: Any, tspan: np.ndarray, y0: np.ndarray, opts: dict[str, float],
              tableau: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    t0, tf = float(tspan[0]), float(tspan[-1])
    direction = 1.0 if tf >= t0 else -1.0
    rtol, atol = opts["RelTol"], opts["AbsTol"]
    max_step = opts["MaxStep"]
    fixed_output = tspan.size > 2
    refine = max(1, int(opts["Refine"])) if not fixed_output else 1
    c, a = tableau["c"], tableau["a"]
    b_high, b_low = tableau["b_high"], tableau["b_low"]
    order = tableau["order"]

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        out = _call(I, f, np.array([[t]], dtype=float), _col(y))
        return np.real(out).ravel().astype(float)

    t, y = t0, y0.astype(float).copy()
    k1 = rhs(t, y)
    h = direction * min(abs(tf - t0) / 100, max_step if math.isfinite(max_step) else math.inf)
    if h == 0:
        h = direction * 1e-3
    times, states = [t], [y.copy()]
    targets = list(tspan[1:]) if fixed_output else []
    next_target = 0
    steps = 0
    while direction * (tf - t) > 0:
        steps += 1
        if steps > 200000:
            raise MatlabError("ode45: too many steps.")
        if direction * (t + h - tf) > 0:
            h = tf - t
        ks = [k1]
        for s in range(1, len(c)):
            y_stage = y + h * sum(a[s][j] * ks[j] for j in range(s))
            ks.append(rhs(t + c[s] * h, y_stage))
        y_new = y + h * sum(b_high[j] * ks[j] for j in range(len(ks)))
        err_vec = h * sum((b_high[j] - b_low[j]) * ks[j] for j in range(len(ks)))
        scale = atol + rtol * np.maximum(np.abs(y), np.abs(y_new))
        err = float(np.max(np.abs(err_vec) / scale)) if err_vec.size else 0.0
        if err <= 1.0 or abs(h) < 1e-12:
            k_new = ks[-1] if c[-1] == 1 else rhs(t + h, y_new)
            if fixed_output:
                while next_target < len(targets) and direction * (targets[next_target] - (t + h)) <= 0:
                    tau = targets[next_target]
                    states.append(_hermite(t, t + h, y, y_new, k1, k_new, tau))
                    times.append(tau)
                    next_target += 1
            else:
                for r in range(1, refine):
                    tau = t + h * r / refine
                    times.append(tau)
                    states.append(_hermite(t, t + h, y, y_new, k1, k_new, tau))
                times.append(t + h)
                states.append(y_new.copy())
            t, y, k1 = t + h, y_new, k_new
        factor = 0.9 * (err ** (-1.0 / order)) if err > 0 else 5.0
        h = h * min(5.0, max(0.2, factor))
        if math.isfinite(max_step):
            h = direction * min(abs(h), max_step)
    if fixed_output and states and times[-1] != tf:
        times.append(tf)
        states.append(y.copy())
    return np.array(times), np.array(states)


def _hermite(t0: float, t1: float, y0: np.ndarray, y1: np.ndarray, f0: np.ndarray, f1: np.ndarray, tau: float) -> np.ndarray:
    h = t1 - t0
    s = (tau - t0) / h
    h00 = 2 * s ** 3 - 3 * s ** 2 + 1
    h10 = s ** 3 - 2 * s ** 2 + s
    h01 = -2 * s ** 3 + 3 * s ** 2
    h11 = s ** 3 - s ** 2
    return h00 * y0 + h10 * h * f0 + h01 * y1 + h11 * h * f1


def _ode_builtin(tableau: dict[str, Any]) -> Callable[..., Any]:
    def body(I: Any, args: list[Any], nargout: int) -> Any:
        nargchk(args, 3, 4)
        tspan = _vec(args[1]).real
        if tspan.size < 2:
            raise MatlabError("TSPAN must contain at least 2 elements.")
        y0 = _vec(args[2]).real
        opts = _odeset_options(args[3] if len(args) > 3 else None)
        times, states = _rk_solve(I, args[0], tspan, y0, opts, tableau)
        if nargout <= 1:
            return MStruct.scalar({"x": _col(times), "y": as2d(states.T)})
        return [_col(times), as2d(states)]
    return body


builtin("ode45")(_ode_builtin(DOPRI5))
builtin("ode23")(_ode_builtin(BS23))


@builtin("odeset")
def bi_odeset(I: Any, args: list[Any], nargout: int) -> Any:
    pairs: dict[str, Any] = {}
    if args and isinstance(args[0], MStruct):
        for field in args[0].fields:
            pairs[field] = args[0].data.flat[0][field]
        args = args[1:]
    for i in range(0, len(args) - 1, 2):
        pairs[text(args[i])] = args[i + 1]
    return MStruct.scalar(pairs) if pairs else MStruct([], None)


