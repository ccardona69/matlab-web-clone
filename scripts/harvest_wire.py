"""Cosecha del wire real del connector MATLAB (apuntes antes del fin del trial).

Cliente Bayeux minimal que habla directamente con el connector real
(https://127.0.0.1:31515, arrancado con ``matlab -batch "connector.ensureServiceOn"``)
y graba TODA la conversacion verbatim en JSONL: peticiones enviadas, respuestas
recibidas y eventos publicados por el servidor. Los JSONL son los "apuntes" que
el emulador (e1_bus_services/app.py) usa para replicar el protocolo cuando la
licencia expire — no se commitean (viven bajo ml-mirror/_captures, ignorado).

Uso:
    python scripts/harvest_wire.py                      # curriculum completo
    python scripts/harvest_wire.py --list               # solo lista comandos
    python scripts/harvest_wire.py --only errors        # una seccion
    python scripts/harvest_wire.py --cmd "magic(5)"     # comando suelto
    python scripts/harvest_wire.py --out DIR            # otra carpeta de salida

Requisitos: MATLAB real vivo con connector.ensureServiceOn activo en
MATLAB_CONNECTOR_URL (default https://127.0.0.1:31515).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

_REPO = Path(__file__).resolve().parent.parent
_DEFAULT_OUT = _REPO / "ml-mirror" / "_captures"

# Orden tomado del wire real del shell JSD (iteracion 3 de e1-request-map.md):
# handshake -> subscribe attach/response -> attach -> subscribe prefix/** ->
# subscribeEvent PromptEvent -> mvmSinks -> eval por comando.
# /messageservice/async es el endpoint Bayeux completo (MVM attach/eval); el
# probe e1 expone /messageservice/json con handshake valido pero sin MVM.
_ENDPOINTS = ("/messageservice/async", "/messageservice/json")

CURRICULUM: list[tuple[str, str]] = [
    # --- escalares / formato ---
    ("scalar", "2+2"),
    ("scalar", "a = 5"),
    ("scalar", "a"),
    ("float", "1/3"),
    ("format", "format long; pi"),
    ("format", "format short; pi"),
    ("format", "format rat; pi"),
    ("format", "format"),
    ("ans", "3*7"),
    ("ans", "ans + 1"),
    # --- matrices / algebra ---
    ("matrix", "A = [1 2 3; 4 5 6; 7 8 10]"),
    ("matrix", "A"),
    ("matrix", "A'"),
    ("matrix", "magic(4)"),
    ("matrix", "ones(2,3)"),
    ("matrix", "zeros(3)"),
    ("matrix", "eye(3)"),
    ("matrix", "inv(A)"),
    ("matrix", "eig(A)"),
    ("matrix", "A \\ [1; 2; 3]"),
    ("matrix", "A * A"),
    ("matrix", "A .* 2"),
    ("matrix", "det(A)"),
    ("matrix", "rank(A)"),
    ("matrix", "1:10"),
    ("matrix", "linspace(0, 1, 5)"),
    ("matrix", "A(2,3)"),
    ("matrix", "A(:,1)"),
    ("matrix", "size(A)"),
    ("matrix", "length(A)"),
    # --- errores (formato exacto es apunte critico) ---
    ("error", "undefined_fn_xyz(1)"),
    ("error", "b = "),                      # syntax error
    ("error", "[1 2] + [1 2 3]"),           # dimension mismatch
    ("error", "A(99)"),                     # index out of bounds
    ("error", "A{1}"),                      # cell indexing on double
    ("error", "inv([1 2; 2 4])"),           # singular
    ("error", "sqrt('x')"),                 # wrong type
    ("error", "nonexistent_var"),
    # --- warnings / especiales ---
    ("warn", "warning('mensaje de prueba')"),
    ("warn", "1/0"),
    ("warn", "0/0"),
    ("warn", "Inf - Inf"),
    ("warn", "warning on"),
    # --- strings / salida ---
    ("string", "'hola mundo'"),
    ("string", "disp('linea suelta')"),
    ("string", "disp(A)"),
    ("string", "sprintf('%.3f', pi)"),
    ("string", "fprintf('x=%d\\n', 42)"),
    ("string", "num2str(pi, '%.5e')"),
    ("string", "strcat('mat', 'lab')"),
    ("string", "\"double quoted\""),
    # --- workspace ---
    ("workspace", "who"),
    ("workspace", "whos"),
    ("workspace", "exist('a')"),
    ("workspace", "exist('zzz')"),
    ("workspace", "clear a"),
    ("workspace", "who"),
    ("workspace", "clear"),
    # --- multi-sentencia / control ---
    ("control", "for i = 1:3, disp(i), end"),
    ("control", "if 1 > 0, disp('si'), else, disp('no'), end"),
    ("control", "x = 1; y = 2; x + y"),
    ("control", "n = 5; while n > 0, n = n - 1; end; n"),
    # --- celdas / structs ---
    ("cell", "c = {1, 'dos', [3 4]}"),
    ("cell", "c{2}"),
    ("struct", "s.nombre = 'ana'; s.edad = 30"),
    ("struct", "s"),
    ("struct", "s.edad"),
    # --- funciones builtin comunes ---
    ("builtin", "sum(1:100)"),
    ("builtin", "mean([1 2 3 4])"),
    ("builtin", "std([1 2 3 4])"),
    ("builtin", "max([3 1 4 1 5])"),
    ("builtin", "sort([3 1 4 1 5])"),
    ("builtin", "factorial(5)"),
    ("builtin", "mod(10, 3)"),
    ("builtin", "abs(-7)"),
    ("builtin", "sqrt(-4)"),
    ("builtin", "exp(1)"),
    ("builtin", "log10(1000)"),
    ("builtin", "isprime(7)"),
    ("builtin", "primes(20)"),
    # --- figuras (el connector responde aunque no haya display) ---
    ("figure", "figure"),
    ("figure", "plot(1:10)"),
    ("figure", "close all"),
    # --- meta ---
    ("meta", "version"),
    ("meta", "computer"),
    ("meta", "pwd"),
    ("meta", "clc"),
    # --- segunda cosecha: ayuda y documentacion ---
    ("help", "help magic"),
    ("help", "help sin"),
    ("help", "lookfor eigenvalue"),
    ("help", "doc format"),
    ("help", "which plot"),
    ("help", "exist('magic')"),
    # --- segunda cosecha: errores extra ---
    ("error2", "A(1, 99)"),
    ("error2", "[1 2; 3]"),
    ("error2", "z = 'a' + [1 2]"),
    ("error2", "s.campo_inexistente"),
    ("error2", "1 + 'a'"),
    ("error2", "error('mi error custom')"),
    ("error2", "try, error('dentro'), catch e, disp(e.message), end"),
    ("error2", "assert(false, 'fallo assert')"),
    ("error2", "A(end+10)"),
    ("error2", "x = [1,2,3"),
    # --- logica / comparadores ---
    ("logic", "1 > 2"),
    ("logic", "true & false"),
    ("logic", "true | false"),
    ("logic", "~true"),
    ("logic", "xor(true, false)"),
    ("logic", "A(A > 5)"),
    ("logic", "any([0 1 0])"),
    ("logic", "all([1 1 0])"),
    ("logic", "find(A > 5)"),
    # --- complejos / especiales ---
    ("complex", "3 + 4i"),
    ("complex", "abs(3 + 4i)"),
    ("complex", "angle(1 + i)"),
    ("complex", "conj(3 + 4i)"),
    ("complex", "real(3 + 4i)"),
    ("complex", "imag(3 + 4i)"),
    ("complex", "eps"),
    ("complex", "realmax"),
    ("complex", "realmin"),
    ("complex", "NaN"),
    # --- algebra lineal extra ---
    ("linalg", "trace(A)"),
    ("linalg", "norm(A)"),
    ("linalg", "cond(A)"),
    ("linalg", "B = [1 2; 3 4]; [L,U] = lu(B)"),
    ("linalg", "B = [1 2; 3 4]; [Q,R] = qr(B)"),
    ("linalg", "B = [4 2; 2 3]; chol(B)"),
    ("linalg", "svd([1 2; 3 4])"),
    ("linalg", "fft([1 2 3 4])"),
    ("linalg", "ifft(fft([1 2 3 4]))"),
    # --- polinomios / convolucion ---
    ("poly", "roots([1 -3 2])"),
    ("poly", "poly([1 2 3])"),
    ("poly", "polyval([1 2 1], 3)"),
    ("poly", "conv([1 1], [1 1])"),
    # --- estadistica ---
    ("stats", "var([1 2 3 4])"),
    ("stats", "median([1 5 2 8])"),
    ("stats", "mode([1 2 2 3])"),
    ("stats", "std([1 2 3 4], 1)"),
    # --- strings extra ---
    ("str2", "upper('hola')"),
    ("str2", "lower('HOLA')"),
    ("str2", "contains('matlab', 'lab')"),
    ("str2", "strfind('abracadabra', 'cad')"),
    ("str2", "strrep('hola hola', 'hola', 'adios')"),
    ("str2", "sprintf('%d-%d\\n%d', 1, 2, 3)"),
    ("str2", "num2str(magic(2))"),
    # --- structs/celdas anidados ---
    ("struct2", "s.direccion.calle = 'main'; s.direccion.num = 7"),
    ("struct2", "s.direccion"),
    ("struct2", "fieldnames(s)"),
    ("struct2", "isfield(s, 'edad')"),
    ("struct2", "rmfield(s, 'edad')"),
    ("struct2", "c2 = {1, {'anidado', [1 2]}}"),
    ("struct2", "celldisp(c2)"),
    # --- archivos (persistencia .mat) ---
    ("files", "save('test_tmp.mat', 'A')"),
    ("files", "clear A; A"),
    ("files", "load('test_tmp.mat')"),
    ("files", "A"),
    ("files", "delete('test_tmp.mat')"),
    ("files", "dir('*.m')"),
    ("files", "type('harvest_dummy.txt')"),
    # --- figuras extra ---
    ("fig2", "x = 0:0.1:2*pi; plot(x, sin(x))"),
    ("fig2", "title('seno'); xlabel('t'); ylabel('y')"),
    ("fig2", "hold on; plot(x, cos(x))"),
    ("fig2", "legend('sin','cos')"),
    ("fig2", "figure(2); bar([1 2 3])"),
    ("fig2", "subplot(2,1,1); plot(1:5)"),
    ("fig2", "scatter(1:5, [3 1 4 1 5])"),
    ("fig2", "close all"),
]


class WireCapture:
    """Graba cada mensaje Bayeux (enviado/recibido) como una linea JSONL."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")
        self._seq = 0

    def record(self, direction: str, endpoint: str, body: Any) -> None:
        self._seq += 1
        self._fh.write(
            json.dumps(
                {
                    "seq": self._seq,
                    "ts": time.time(),
                    "dir": direction,
                    "endpoint": endpoint,
                    "body": body,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        self._fh.flush()

    def marker(self, note: str, extra: dict[str, Any] | None = None) -> None:
        self._seq += 1
        entry = {"seq": self._seq, "ts": time.time(), "dir": "note", "note": note}
        if extra:
            entry.update(extra)
        self._fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


class HarvestClient:
    """Bayeux minimo contra el connector real.

    Un cliente publica los evals; OTRO cliente (`poller`) mantiene UN solo
    /meta/connect continuo en un hilo y recoge todos los eventos — los canales
    MVM no son client-scoped, basta suscribirse al mismo prefijo. Asi el wire
    nunca deja polls zombis (Bayeux solo admite un connect por clientId) y la
    atribucion comando->salida es exacta por orden temporal.
    """

    def __init__(self, base: str, capture: WireCapture):
        self.base = base.rstrip("/")
        self.cap = capture
        self.http = httpx.Client(verify=False, timeout=httpx.Timeout(70.0, connect=10.0))
        self.client_id: str | None = None
        self.endpoint: str | None = None
        self._id = 0
        self._lock = threading.Lock()
        self.prefix: str | None = None  # /mvm/<requestID> del attach real
        # Log de eventos del poller (segundo cliente): (ts, mensaje)
        self.events: list[tuple[float, dict[str, Any]]] = []
        self._stop = threading.Event()

    def _next_id(self) -> str:
        with self._lock:
            self._id += 1
            return str(self._id)

    def _post(
        self, msgs: list[dict[str, Any]], http_timeout: float | None = None
    ) -> list[dict[str, Any]]:
        assert self.endpoint is not None
        self.cap.record("sent", self.endpoint, msgs)
        resp = self.http.post(
            self.base + self.endpoint, json=msgs, timeout=http_timeout
        )
        try:
            body: Any = resp.json()
        except Exception:
            body = {"_raw": resp.text[:4000], "_status": resp.status_code}
        self.cap.record("recv", self.endpoint, body)
        if resp.status_code != 200:
            raise RuntimeError(f"POST {self.endpoint} -> {resp.status_code}: {resp.text[:300]}")
        return body if isinstance(body, list) else [body]

    def handshake(self) -> None:
        """Prueba los endpoints conocidos hasta que el handshake devuelva clientId."""
        if self.endpoint is not None and self.client_id:
            return  # cliente ya conectado (poller reusando endpoint)
        msg = {
            "channel": "/meta/handshake",
            "version": "1.0",
            "minimumVersion": "1.0",
            "supportedConnectionTypes": ["long-polling"],
            "id": self._next_id(),
        }
        last = None
        for ep in _ENDPOINTS:
            self.endpoint = ep
            self.cap.marker("handshake-try", {"endpoint": ep})
            try:
                out = self._post([msg])
            except Exception as exc:  # noqa: BLE001 - se graba y se prueba el siguiente
                self.cap.marker("handshake-error", {"endpoint": ep, "error": str(exc)})
                last = exc
                continue
            if (
                out
                and out[0].get("successful")
                and out[0].get("clientId")
                and out[0].get("supportedConnectionTypes")
            ):
                self.client_id = out[0]["clientId"]
                self.cap.marker("handshake-ok", {"endpoint": ep, "clientId": self.client_id})
                return
            last = RuntimeError(f"handshake rechazado en {ep}: {out!r}")
        raise RuntimeError(f"handshake fallo en todos los endpoints: {last}")

    def subscribe(self, channel: str) -> None:
        self._post([
            {
                "channel": "/meta/subscribe",
                "clientId": self.client_id,
                "subscription": channel,
                "id": self._next_id(),
            }
        ])

    def publish(self, channel: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        return self._post([
            {
                "channel": channel,
                "clientId": self.client_id,
                "data": data,
                "id": self._next_id(),
            }
        ])

    def connect(self, timeout_ms: int = 30000) -> list[dict[str, Any]]:
        """Una ronda de long-poll; devuelve solo mensajes de datos (no /meta/*)."""
        try:
            out = self._post([
                {
                    "channel": "/meta/connect",
                    "clientId": self.client_id,
                    "connectionType": "long-polling",
                    "timeout": timeout_ms,
                    "id": self._next_id(),
                }
            ])
        except httpx.TimeoutException:
            return []
        return [m for m in out if not m.get("channel", "").startswith("/meta/")]

    def _wait_event(self, pred: Any, timeout_s: float) -> dict[str, Any] | None:
        """Espera en self.events el primer mensaje que cumpla pred."""
        end = time.monotonic() + timeout_s
        seen = 0
        while time.monotonic() < end:
            with self._lock:
                pending = self.events[seen:]
                seen = len(self.events)
            for _ts, m in pending:
                if pred(m):
                    return m
            time.sleep(0.05)
        return None

    def _poller_loop(self, poller: "HarvestClient") -> None:
        """Un unico connect continuo del cliente poller; alimenta self.events."""
        while not self._stop.is_set():
            try:
                batch = poller.connect(timeout_ms=30000)
            except Exception as exc:  # noqa: BLE001 - reintenta hasta _stop
                self.cap.marker("poller-error", {"error": str(exc)})
                time.sleep(0.5)
                continue
            now = time.time()
            with self._lock:
                self.events.extend((now, m) for m in batch)

    def start_poller(self) -> None:
        """Crea el segundo cliente Bayeux y arranca su hilo de long-polling."""
        poller = HarvestClient(self.base, self.cap)
        poller.endpoint = self.endpoint
        poller.handshake()
        poller.subscribe("/matlab/mvm/attach/response")
        t = threading.Thread(target=self._poller_loop, args=(poller,), daemon=True)
        t.start()
        self.poller = poller

    def attach(self) -> str:
        """Attach MVM como hace el shell; devuelve el channelPrefix (/mvm/<id>)."""
        attach_id = uuid.uuid4().hex[:8].upper()
        self.publish(
            "/matlab/mvm/attach/request",
            {
                "mvmID": "user-mvm",
                "supportedApiVersions": ["v7_0"],
                "requestID": attach_id,
            },
        )
        m = self._wait_event(
            lambda m: m.get("channel", "").endswith("/attach/response"), 30.0
        )
        if m is None:
            raise RuntimeError("attach sin respuesta en 30s")
        prefix = (m.get("data") or {}).get("channelPrefix")
        if not prefix:
            raise RuntimeError(f"attach sin channelPrefix: {m!r}")
        self.prefix = prefix
        self.cap.marker("attach-ok", {"channelPrefix": prefix})
        return prefix

    def subscribe_prefix(self) -> None:
        """Suscribe el cliente poller a todos los canales del prefijo MVM."""
        assert self.prefix
        wire = f"/matlab{self.prefix}"
        for suffix in (
            "/eval/response",
            "/feval/response",
            "/text/output",
            "/text/error",
            "/mvmSinks/response",
            "/mvmSinks/output",
            "/subscribeEvent/response",
            "/disconnectEvent/response",
            "/event/fireEvent",
        ):
            self.poller.subscribe(wire + suffix)
        self._wait_event(lambda m: False, 0.5)  # deja propagar suscripciones

    def setup_prompt(self) -> None:
        """subscribeEvent PromptEvent + mvmSinks, igual que el shell al arrancar."""
        assert self.prefix
        wire = f"/matlab{self.prefix}"
        self.publish(
            f"{wire}/mvmSinks/request",
            {"outSinkTraits": {}, "errSinkTraits": {}, "requestID": uuid.uuid4().hex[:8].upper()},
        )
        self.publish(
            f"{wire}/subscribeEvent/request",
            {"eventName": "mlutil::prompt::PromptEvent", "requestID": uuid.uuid4().hex[:8].upper()},
        )
        self._wait_event(lambda m: False, 1.0)  # deja llegar los primeros fires

    def eval_command(self, cmd: str, wait_s: float = 30.0) -> dict[str, Any]:
        """Envia un eval y recoge eventos hasta eval/response + 1.2s de calma."""
        assert self.prefix
        wire = f"/matlab{self.prefix}"
        request_id = uuid.uuid4().hex[:8].upper()
        self.cap.marker("command", {"command": cmd, "requestID": request_id})
        self.publish(
            f"{wire}/eval/request",
            {"command": cmd, "isUserEval": True, "requestID": request_id},
        )
        got = self._wait_event(
            lambda m: m.get("channel", "").endswith("/eval/response")
            and (m.get("data") or {}).get("requestID") == request_id,
            wait_s,
        )
        # La salida de mvmSinks puede llegar DESPUES del eval/response (canal
        # sin requestID): se espera 1.2s sin eventos nuevos para cerrar la
        # ventana de atribucion del comando.
        if got is not None:
            last_n = -1
            quiet_since = time.monotonic()
            while time.monotonic() - quiet_since < 1.2:
                with self._lock:
                    n = len(self.events)
                if n != last_n:
                    last_n = n
                    quiet_since = time.monotonic()
                time.sleep(0.05)
        self.cap.marker(
            "command-done",
            {
                "command": cmd,
                "requestID": request_id,
                "answered": got is not None,
            },
        )
        return {"requestID": request_id, "answered": got is not None}
        self.cap.marker(
            "command-done",
            {
                "command": cmd,
                "requestID": request_id,
                "events": len(events),
                "answered": got_response,
            },
        )
        return {"requestID": request_id, "answered": got_response, "events": len(events)}


def run_harvest(commands: list[tuple[str, str]], out_dir: Path, base: str) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    capture_path = out_dir / f"wire-{stamp}.jsonl"
    index_path = out_dir / f"wire-{stamp}.index.json"
    cap = WireCapture(capture_path)
    client = HarvestClient(base, cap)
    print(f"[harvest] capturando en {capture_path}")
    print(f"[harvest] connector: {base}")
    try:
        client.handshake()
        print(f"[harvest] handshake OK ({client.endpoint})")
        client.start_poller()
        client.attach()
        print(f"[harvest] attach OK -> {client.prefix}")
        client.subscribe_prefix()
        client.setup_prompt()
        results = []
        for i, (section, cmd) in enumerate(commands, 1):
            try:
                res = client.eval_command(cmd)
            except Exception as exc:  # noqa: BLE001 - se anota y se sigue
                cap.marker("command-error", {"command": cmd, "error": str(exc)})
                res = {"answered": False}
            results.append({"section": section, "command": cmd, **res})
            flag = "ok" if res["answered"] else "SIN-RESP"
            print(f"[{i:3d}/{len(commands)}] {flag}  {cmd}", flush=True)
        client._stop.set()
        time.sleep(0.3)
    finally:
        cap.close()
        index_path.write_text(
            json.dumps(
                {
                    "captured_at": stamp,
                    "connector": base,
                    "capture": capture_path.name,
                    "commands": [
                        {"section": s, "command": c} for s, c in commands
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    print(f"[harvest] fin. indice: {index_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Cosecha del wire MATLAB -> JSONL")
    ap.add_argument("--url", default=os.environ.get("MATLAB_CONNECTOR_URL", "https://127.0.0.1:31515"))
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    ap.add_argument("--only", help="solo esta seccion del curriculum")
    ap.add_argument("--cmd", help="un comando suelto en vez del curriculum")
    ap.add_argument("--list", action="store_true", help="lista el curriculum y sale")
    args = ap.parse_args()

    if args.list:
        for section, cmd in CURRICULUM:
            print(f"{section:10s}  {cmd}")
        return 0

    commands = [("cli", args.cmd)] if args.cmd else CURRICULUM
    if args.only:
        wanted = set(args.only.split(","))
        commands = [(s, c) for s, c in CURRICULUM if s in wanted]
        if not commands:
            print(f"seccion desconocida: {args.only}", file=sys.stderr)
            return 2
    run_harvest(commands, args.out, args.url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
