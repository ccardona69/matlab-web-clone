"""
Parte 1: Ledger de Evidencia REA y Puente Nativo (libMatlabEngine.dll + PE/CLI + UI Graph).
Reconstruido directamente a partir de la evidencia autenticada de REA v6.5.0 sobre
C:\\Program Files\\MATLAB\\R2026b (Release 26.2.0.3386108).
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

MATLAB_ROOT = Path(r"C:\Program Files\MATLAB\R2026b")
LIB_MATLAB_ENGINE_PATH = MATLAB_ROOT / "extern" / "bin" / "win64" / "libMatlabEngine.dll"
LIB_MATLAB_DATA_ARRAY_PATH = MATLAB_ROOT / "extern" / "bin" / "win64" / "libMatlabDataArray.dll"
REA_CLI_PATH = Path(
    r"C:\Users\dav\AppData\Local\npm-cache\_npx\af752b90495482d7\node_modules\.bin\rea.cmd"
)


@dataclass(frozen=True)
class ReaArtifactEvidence:
    evidence_id: str
    artifact_name: str
    local_path: str
    sha256: str
    byte_length: int
    format: str
    architecture: str
    provider_id: str
    operation: str
    confidence: str
    authority: str
    summary: dict[str, Any]
    limitations: list[str]


@dataclass(frozen=True)
class PInvokeDeclaration:
    token: str
    member_token: str
    member_name: str
    import_name: str
    import_scope_name: str
    calling_convention: str
    char_set: str
    row_offset: int


# 11 declaraciones P/Invoke exactas extraídas por REA (ev_a8557a51d9338b26b01fd6067380701e6c52d37b87ddf78a41cbcfa02502d5bb)
PINVOKE_DECLARATIONS: list[PInvokeDeclaration] = [
    PInvokeDeclaration("0x1c000001", "0x0600001e", "cpp_engine_create_session", "cpp_engine_create_session", "libMatlabEngine", "winapi", "unicode", 6970),
    PInvokeDeclaration("0x1c000002", "0x0600001f", "cpp_engine_create_out_of_process_matlab", "cpp_engine_create_out_of_process_matlab", "libMatlabEngine", "winapi", "unicode", 6978),
    PInvokeDeclaration("0x1c000003", "0x06000020", "cpp_engine_attach_shared_matlab", "cpp_engine_attach_shared_matlab", "libMatlabEngine", "winapi", "unicode", 6986),
    PInvokeDeclaration("0x1c000004", "0x06000021", "cpp_engine_find_shared_matlab", "cpp_engine_find_shared_matlab", "libMatlabEngine", "winapi", "unicode", 6994),
    PInvokeDeclaration("0x1c000005", "0x06000022", "cpp_engine_destroy_names", "cpp_engine_destroy_names", "libMatlabEngine", "winapi", "unicode", 7002),
    PInvokeDeclaration("0x1c000006", "0x06000023", "cpp_engine_feval_with_completion", "cpp_engine_feval_with_completion", "libMatlabEngine", "winapi", "unicode", 7010),
    PInvokeDeclaration("0x1c000007", "0x06000024", "cpp_engine_destroy_task_handle", "cpp_engine_destroy_task_handle", "libMatlabEngine", "winapi", "unicode", 7018),
    PInvokeDeclaration("0x1c000008", "0x06000025", "cpp_engine_terminate_out_of_process_matlab", "cpp_engine_terminate_out_of_process_matlab", "libMatlabEngine", "winapi", "unicode", 7026),
    PInvokeDeclaration("0x1c000009", "0x06000026", "cpp_engine_terminate_session", "cpp_engine_terminate_session", "libMatlabEngine", "winapi", "unicode", 7034),
    PInvokeDeclaration("0x1c00000a", "0x06000027", "cpp_engine_cancel_feval_with_completion", "cpp_engine_cancel_feval_with_completion", "libMatlabEngine", "winapi", "unicode", 7042),
    PInvokeDeclaration("0x1c00000b", "0x06000028", "cpp_engine_set_client_language", "cpp_engine_set_client_language", "libMatlabEngine", "winapi", "unicode", 7050),
]

AUTHENTICATED_EVIDENCE_LEDGER: list[ReaArtifactEvidence] = [
    ReaArtifactEvidence(
        evidence_id="ev_baa948b45c56dd4b9de0b702a04772ffee00d5aef0f22d038407f4a83bd99f9e",
        artifact_name="matlab.exe (Launcher 32-bit)",
        local_path=r"C:\Program Files\MATLAB\R2026b\bin\matlab.exe",
        sha256="0685c5bcf12b661975b7632aea1e2dd49e075b8e1010b8690f1dd1ead8a7e928",
        byte_length=346464,
        format="pe32",
        architecture="x86 (machine 332)",
        provider_id="rea-pe-resources",
        operation="inspect_pe_resources",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "role": "Bootstrap launcher que selecciona la arquitectura y delega a bin\\win64\\MATLAB.exe",
            "rsrc_rva": 270336,
            "rsrc_bytes": 70416,
        },
        limitations=["No simula la carga de recursos en tiempo de ejecución de Windows."],
    ),
    ReaArtifactEvidence(
        evidence_id="ev_57492f750879e2aefe3cacb1863d1893f44d3d74e38453487e6bb1bb47d32e61",
        artifact_name="MATLAB.exe (Host 64-bit)",
        local_path=r"C:\Program Files\MATLAB\R2026b\bin\win64\MATLAB.exe",
        sha256="5380cc41fc6f075ba911b501216c1b9f20df800866358be5b92bdcdb879b596d",
        byte_length=126304,
        format="pe32-plus (pei-x86-64)",
        architecture="x86_64 (machine 34404)",
        provider_id="rea-pe-resources + gnu.objdump",
        operation="inspect_pe_resources / inspect_with_objdump",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "entry_point": "0x00000001400017e4",
            "sections": {
                ".text": {"vma": "0x140001000", "size": "0x16bc (5820 bytes)"},
                ".rdata": {"vma": "0x140003000", "size": "0x15ca"},
                ".data": {"vma": "0x140005000", "size": "0x00d8"},
                ".pdata": {"vma": "0x140006000", "size": "0x02ac"},
                ".rsrc": {"vma": "0x140007000", "size": "0x18878 (100472 bytes)"},
                ".reloc": {"vma": "0x140020000", "size": "0x002c"},
            },
            "linked_evidence": [
                "ev_d26713beee6cad48f6767ccb24c58844d03db50cd91e8157ce4af0fda5bd42be",
                "ev_da1e6fac8a7c1b39afb77bbfb8ab80ab5eb93d88cc8f277dd85150f388845883",
                "ev_33046a403e3a0c1637712496a4cccc394b92cbfef90328721c321c3975ef3de4",
            ],
        },
        limitations=["Observación estática sobre archivo PE32+; no implica ejecución del binario."],
    ),
    ReaArtifactEvidence(
        evidence_id="ev_924f92a82a75a538bcd6ab986ee67c270788df70f1056e1ee14e2b5b6166cfbd",
        artifact_name="MATLABWindow.exe (CEF UI Shell)",
        local_path=r"C:\Program Files\MATLAB\R2026b\bin\win64\MATLABWindow.exe",
        sha256="d50d0d837b95b9bdec01666af3bf590ba032c079ecca29c1ac063a6e1e962b6b",
        byte_length=970592,
        format="pe32-plus (pei-x86-64)",
        architecture="x86_64 (machine 34404)",
        provider_id="rea-pe-resources + gnu.objdump",
        operation="inspect_pe_resources / inspect_with_objdump",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "entry_point": "0x00000001400993a0",
            "rsrc_rva": 958464,
            "rsrc_bytes": 2360,
            "linked_evidence": ["ev_7e424a1c6fc7d3b95685ce8b90ac6b804a6e0d6bc048c5d6038d0339d4cc967d"],
            "role": "Contenedor Chromium Embedded Framework (CEF) para la interfaz webgui/jsconsole de R2026b",
        },
        limitations=["Headers y recursos PE32+ inspeccionados estáticamente sin ejecutar CEF."],
    ),
    ReaArtifactEvidence(
        evidence_id="ev_f0a3ddfe99325be07d3cae254d2e269146106878c9dd7799dd9d62c003282539",
        artifact_name="MathWorks.MATLAB.Engine.dll",
        local_path=r"C:\Program Files\MATLAB\R2026b\extern\dotnet\netstandard2.0\MathWorks.MATLAB.Engine.dll",
        sha256="a5c9689c3b8616ecf51817fff13b752f5e8cee4b9adc96b5c6ee540fbf1a003d",
        byte_length=15360,
        format="pe (CIL il-only)",
        architecture="anycpu (.NETStandard,Version=v2.0)",
        provider_id="rea-dotnet-static",
        operation="inspect_managed_artifact / inspect_managed_native_boundaries",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "mvid": "ac132a62-5b7c-4d3e-9149-98476fd5930b",
            "type_defs": 12,
            "method_defs": 78,
            "pinvoke_imports": 11,
            "native_module": "libMatlabEngine",
            "linked_evidence": [
                "ev_4a890d37edadeb2c15d18a70730f78e528dca7d48f209b21af2de8d5b7669dd9",
                "ev_a8557a51d9338b26b01fd6067380701e6c52d37b87ddf78a41cbcfa02502d5bb",
            ],
        },
        limitations=[
            "La inspección estática no carga el ensamblado en un CLR ni ejecuta código objetivo.",
            "Los tokens de metadatos son locales al build (sujetos a SHA-256 y MVID).",
        ],
    ),
    ReaArtifactEvidence(
        evidence_id="ev_8af43d455a967af12b5e56d8c9d026a542ce7270fb53c8512157929c1ef7ad44",
        artifact_name="MathWorks.MATLAB.Types.dll",
        local_path=r"C:\Program Files\MATLAB\R2026b\extern\dotnet\netstandard2.0\MathWorks.MATLAB.Types.dll",
        sha256="363ba1f6f32a1e0042fbe7211b6a5f56238e8e840351958e2181ee3769d76d40",
        byte_length=107008,
        format="pe (CIL il-only)",
        architecture="anycpu (.NETStandard,Version=v2.0)",
        provider_id="rea-dotnet-static",
        operation="inspect_managed_artifact / inspect_managed_native_boundaries",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "mvid": "ef709127-bedd-4dac-a897-6494c6196a0b",
            "type_defs": 91,
            "fields": 301,
            "method_defs": 633,
            "pinvoke_imports": 96,
            "native_modules": ["libMatlabDataArray", "msvcrt", "libc"],
            "linked_evidence": ["ev_cc240413c580f88f0d4a5c0b50bb853dcab3623757a6068124e40f78beba7156"],
        },
        limitations=["Inspección estática de tablas ECMA-335 sin ejecución CLR."],
    ),
    ReaArtifactEvidence(
        evidence_id="ev_408d456edff3b3cedf50c9b04609603a46058899495cf2230755920d892304c0",
        artifact_name="libMatlabEngine.dll",
        local_path=r"C:\Program Files\MATLAB\R2026b\extern\bin\win64\libMatlabEngine.dll",
        sha256="45e825ee94e2dd4021f38bbc0d93829439cdc5f7a7bc4e53f23756714880a833",
        byte_length=65376,
        format="pei-x86-64",
        architecture="x86_64",
        provider_id="gnu.objdump",
        operation="inspect_with_objdump (file_headers / section_headers)",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "entry_point": "0x0000000180008a0c",
            "sections": {
                ".text": "0x8925 bytes @ 0x180001000",
                ".rdata": "0x3738 bytes @ 0x18000a000",
                ".data": "0x0200 bytes @ 0x18000e000",
                ".pdata": "0x0b1c bytes @ 0x180010000",
            },
            "linked_evidence": ["ev_9614ae654118908835d5542b8bcac66810462cb6ea73273e7e53c8e738127094"],
        },
        limitations=["Puente nativo C++ para sesiones de motor MATLAB fuera de proceso."],
    ),
    ReaArtifactEvidence(
        evidence_id="ev_da7a98bba739ec8565820f30f2b2e2db24add0e9699247d2c0c1365d3933e994",
        artifact_name="ui/jsconsole (Command Window WebUI)",
        local_path=r"C:\Program Files\MATLAB\R2026b\ui\jsconsole",
        sha256="d3ad466b5535bf4e86c9d6786db9844634cb80a854c335c3ca029c3fad5b769d",
        byte_length=2029616,
        format="directory (JavaScriptApplicationGraph)",
        architecture="webpackChunk + Dojo AMD",
        provider_id="rea-javascript-application",
        operation="analyze_javascript_application",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "manifest_id": "agm_a96d90c42e04c972ccca2212e0a301c910a8bbd51c7e22c90a5f77fff5de8c2a",
            "chunk": "mwBundle.ui-jsconsole-jsconsole_ui",
            "entry_modules": ["mw-mvm/impl/Connection", "jsconsole_ui/release/jsconsole_ui-lib/dojoConfig-release-global.js"],
        },
        limitations=["Grafo semántico estático; las llamadas dinámicas se registran como candidatos o incógnitas."],
    ),
    ReaArtifactEvidence(
        evidence_id="ev_3300396e1c125942fba70f54d80ee643cb29f7e34126173180e76bceea65f7f2",
        artifact_name="ui/copilot_ui_framework",
        local_path=r"C:\Program Files\MATLAB\R2026b\ui\copilot_ui_framework",
        sha256="4c9457b633fd781cacb0c9da011d7f8bc44adf881b5804383df3a93f939998ec",
        byte_length=1443,
        format="directory (JavaScriptApplicationGraph)",
        architecture="webpackChunk + Dojo AMD",
        provider_id="rea-javascript-application",
        operation="analyze_javascript_application",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "manifest_id": "agm_2ef6fdf6c7769d4ec5e80301d05d18e31e045e0dfdda00a641280802eeefc2b5",
            "files_analyzed": 6,
        },
        limitations=["El bundle minificado principal reservó presupuesto por límite de 1024 MB del worker."],
    ),
    ReaArtifactEvidence(
        evidence_id="ev_2bab9a6823c37119307b8a3889ab55ad5eca27216403b6f62cd33ef131af072a",
        artifact_name="java/jar/matlab.jar",
        local_path=r"C:\Program Files\MATLAB\R2026b\java\jar\matlab.jar",
        sha256="24dc7e7bcd3ac80703255cac1636c54e21f4dfc06dd056f7eb17f766e644070b",
        byte_length=47422,
        format="zip (JAR)",
        architecture="jvm",
        provider_id="rea-artifact-graph",
        operation="inspect_artifact",
        confidence="observed",
        authority="shipped-artifact",
        summary={
            "manifest_id": "agm_d6522dced937c21d7ec27005e06de3f71ddfa9f873357e1f995dec5cf16e32c6",
            "inventory_evidence_id": "ev_576807e9b9bfa561c4dad8bac36bf8c86696b39b474a09c2531bbe19e953889b",
        },
        limitations=["Inventario de contenedor ZIP/JAR sin ejecución en JVM."],
    ),
]


class NativeMatlabBridge:
    """
    Puente nativo hacia libMatlabEngine.dll basado en las 11 firmas P/Invoke
    recuperadas en ev_a8557a51d9338b26b01fd6067380701e6c52d37b87ddf78a41cbcfa02502d5bb.
    No ejecuta procesos sin solicitud explícita; verifica la presencia y símbolos exportados.
    """

    def __init__(self) -> None:
        self.engine_dll_path = LIB_MATLAB_ENGINE_PATH
        self.data_array_dll_path = LIB_MATLAB_DATA_ARRAY_PATH

    def verify_native_binaries(self) -> dict[str, Any]:
        results: dict[str, Any] = {
            "matlab_root_exists": MATLAB_ROOT.exists(),
            "libMatlabEngine": self._inspect_file(self.engine_dll_path, "45e825ee94e2dd4021f38bbc0d93829439cdc5f7a7bc4e53f23756714880a833"),
            "libMatlabDataArray": self._inspect_file(self.data_array_dll_path, None),
            "pinvoke_bindings": [],
        }

        dll_handle = None
        load_error = None
        if self.engine_dll_path.exists():
            try:
                bin_win64 = MATLAB_ROOT / "bin" / "win64"
                extern_win64 = MATLAB_ROOT / "extern" / "bin" / "win64"
                if hasattr(os, "add_dll_directory"):
                    if bin_win64.exists():
                        os.add_dll_directory(str(bin_win64))
                    if extern_win64.exists():
                        os.add_dll_directory(str(extern_win64))
                dll_handle = ctypes.WinDLL(str(self.engine_dll_path))
            except Exception as exc:
                load_error = str(exc)

        for decl in PINVOKE_DECLARATIONS:
            resolved_addr = None
            if dll_handle is not None:
                try:
                    func_ptr = getattr(dll_handle, decl.import_name)
                    resolved_addr = hex(ctypes.cast(func_ptr, ctypes.c_void_p).value or 0)
                except AttributeError:
                    resolved_addr = None
            results["pinvoke_bindings"].append(
                {
                    **asdict(decl),
                    "symbol_resolved": resolved_addr is not None,
                    "memory_address": resolved_addr,
                }
            )

        results["native_dll_loaded"] = dll_handle is not None
        results["native_load_note"] = load_error
        return results

    @staticmethod
    def _inspect_file(path: Path, expected_sha256: str | None) -> dict[str, Any]:
        if not path.exists():
            return {"exists": False, "path": str(path), "sha256": None, "matches_evidence": False}
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "exists": True,
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": digest,
            "matches_evidence": (expected_sha256 is None) or (digest == expected_sha256),
        }


def get_rea_ledger_payload() -> dict[str, Any]:
    bridge = NativeMatlabBridge()
    return {
        "release": "R2026b",
        "version": "26.2.0.3386108",
        "rea_version": "6.5.0",
        "skill_version": "42",
        "evidence_count": len(AUTHENTICATED_EVIDENCE_LEDGER),
        "evidence": [asdict(item) for item in AUTHENTICATED_EVIDENCE_LEDGER],
        "pinvoke_declarations": [asdict(d) for d in PINVOKE_DECLARATIONS],
        "native_bridge_status": bridge.verify_native_binaries(),
    }
