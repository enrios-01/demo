"""
Server Streamlit Version (safe main)
-----------------------------------

Este módulo funciona en dos modos:
1) **Streamlit** (para deploy en https://share.streamlit.io/ u otro hosting Streamlit)
2) **CLI/Pruebas** cuando `streamlit` no está instalado, evitando:
   - `ModuleNotFoundError: No module named 'streamlit'` (import condicional)
   - `SystemExit: 0` en sandboxes (no usamos `sys.exit()` en `__main__`).

¿Cómo ejecutarlo?
- **Streamlit**: `streamlit run server.py`
- **CLI** (sin Streamlit): `python server.py --file ruta/al/archivo.ext --run`
- **Tests**: `python server.py --test`
"""

from __future__ import annotations
import os
import sys
import argparse
import unittest
from typing import Optional

# ---------------------------------------------------------------
# Carga segura de Streamlit (evita ModuleNotFoundError en sandbox)
# ---------------------------------------------------------------
try:  # Import condicional: no rompe si streamlit no está instalado
    import importlib
    st = importlib.import_module("streamlit")  # type: ignore
    HAS_STREAMLIT = True
except Exception:
    st = None  # type: ignore
    HAS_STREAMLIT = False


# -----------------
# Lógica reutilizable
# -----------------
DEFAULT_PREVIEW_LEN = 2000

def get_base_path() -> str:
    """Devuelve la ruta base del archivo actual."""
    return os.path.dirname(os.path.abspath(__file__))


def _strip_non_printable(text: str) -> str:
    """Elimina caracteres no imprimibles (control chars) para salidas limpias.
    Mantiene caracteres UTF-8 válidos como acentos y ñ.
    """
    # str.isprintable() descarta \x00, \x01, etc., pero mantiene acentos
    return "".join(ch for ch in text if ch.isprintable())


def process_content(content_bytes: bytes, preview_len: int = DEFAULT_PREVIEW_LEN) -> str:
    """Decodifica bytes a texto ignorando errores, limpia no imprimibles y recorta.

    Args:
        content_bytes: contenido binario (subida de archivo en Streamlit o lectura en CLI)
        preview_len: cantidad de caracteres para mostrar en el preview
    Returns:
        Cadena decodificada (UTF-8 con errores ignorados) sin controles, recortada a `preview_len`.
    """
    if not isinstance(content_bytes, (bytes, bytearray)):
        # Tolerancia: si ya viene como str, lo usamos directamente
        text = str(content_bytes)
    else:
        text = content_bytes.decode("utf-8", errors="ignore")
    text = _strip_non_printable(text)
    # Evitar negativos/valores raros
    try:
        plen = int(preview_len)
    except Exception:
        plen = DEFAULT_PREVIEW_LEN
    if plen < 0:
        plen = 0
    return text[: plen]


# -----------------
# UI de Streamlit
# -----------------

def run_streamlit_app() -> None:
    assert HAS_STREAMLIT and st is not None, "Streamlit no está disponible"

    # Config y cabecera
    st.set_page_config(page_title="Demo App", layout="wide")
    st.title("Demo Backend con Streamlit")

    base_path = get_base_path()
    st.write(f"Ruta base: {base_path}")

    # Carga/preview de archivo
    st.subheader("Procesamiento de datos")
    uploaded_file = st.file_uploader(
        "Subí un archivo para procesar", type=["txt", "csv", "xlsx", "pdf"]
    )

    if uploaded_file is not None:
        st.write(f"Archivo recibido: {uploaded_file.name}")
        content = uploaded_file.read()
        preview = process_content(content, DEFAULT_PREVIEW_LEN)
        st.text_area("Contenido del archivo:", value=preview, height=300)

    # Acción principal
    if st.button("Ejecutar lógica principal"):
        # Colocá aquí la lógica de negocio real (antes en tu backend)
        st.success("Lógica ejecutada correctamente.")

    st.info("Fin del módulo. Adaptado para Streamlit.")


# --------------
# Modo CLI (fallback)
# --------------

def run_cli(argv: Optional[list[str]] = None) -> int:
    """Entrada por CLI cuando Streamlit no está instalado o no se ejecuta el runtime.
    Devuelve un código de salida entero, pero **no se hace sys.exit()** en `__main__`.
    """
    parser = argparse.ArgumentParser(description="Demo Backend CLI (fallback sin Streamlit)")
    parser.add_argument("--file", dest="file", help="Ruta a un archivo para previsualizar", default=None)
    parser.add_argument("--run", action="store_true", help="Ejecuta la lógica principal")
    parser.add_argument("--preview-len", type=int, default=DEFAULT_PREVIEW_LEN, help="Largo del preview")
    parser.add_argument("--print-base-path", action="store_true", help="Muestra la ruta base y sale")
    parser.add_argument("--test", action="store_true", help="Ejecuta los tests unitarios y sale")

    args = parser.parse_args(argv)

    if args.test:
        return run_tests()

    if args.print_base_path:
        print(f"Ruta base: {get_base_path()}")

    if args.file:
        if not os.path.exists(args.file):
            print(f"[ERROR] No existe el archivo: {args.file}")
            return 1
        with open(args.file, "rb") as fh:
            content = fh.read()
        preview = process_content(content, args.preview_len)
        print("--- Preview del archivo ---")
        print(preview)
        print("---------------------------")

    if args.run:
        print("Lógica ejecutada correctamente.")

    if not (args.file or args.run or args.print_base_path):
        parser.print_help()

    return 0


# ---------
# Test cases
# ---------
class TestLogic(unittest.TestCase):
    # EXISTENTES (no tocar)
    def test_process_content_plain_text(self):
        data = b"Hola mundo"
        out = process_content(data, 5)
        self.assertEqual(out, "Hola ")

    def test_process_content_binary_bytes(self):
        data = b"\x00\x01\xffABC\x00DEF"
        out = process_content(data, 6)
        # Debe contener caracteres ASCII decodificados y estar recortado
        self.assertEqual(out, "ABCDEF"[:6])

    def test_process_content_utf8(self):
        text = "áéíóú ñ"
        data = text.encode("utf-8")
        out = process_content(data, 20)
        self.assertIn("áéíóú", out)
        self.assertIn("ñ", out)

    def test_get_base_path_exists(self):
        base = get_base_path()
        self.assertTrue(os.path.isdir(base))

    # NUEVOS (agregados)
    def test_process_content_str_passthrough(self):
        out = process_content("cadena ya decodificada", 10)
        self.assertEqual(out, "cadena ya")

    def test_process_content_negative_preview(self):
        data = b"ABCDEFG"
        out = process_content(data, -5)
        self.assertEqual(out, "")

    def test_strip_non_printable(self):
        raw = "\x00\x01A\x02B\x03C"
        # _strip_non_printable es auxiliar interna; probamos mediante process_content
        out = process_content(raw, 10)  # type: ignore[arg-type]
        self.assertEqual(out, "ABC")


def run_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestLogic)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


# -----------------
# Auto-selección de modo (sin sys.exit())
# -----------------
if __name__ == "__main__":
    # Detecta si estamos dentro del runtime de Streamlit
    IS_STREAMLIT_RUNTIME = bool(
        os.environ.get("STREAMLIT_RUNTIME") or os.environ.get("STREAMLIT_SERVER_PORT")
    )

    exit_code = 0
    if HAS_STREAMLIT and IS_STREAMLIT_RUNTIME:
        run_streamlit_app()
    elif HAS_STREAMLIT and not IS_STREAMLIT_RUNTIME and "--test" not in sys.argv:
        # Si Streamlit está instalado pero se ejecuta con `python server.py`,
        # ofrecemos el modo CLI para conveniencia local.
        exit_code = run_cli(sys.argv[1:])
    else:
        # Fallback completo sin Streamlit instalado
        exit_code = run_cli(sys.argv[1:])

    # No hacemos sys.exit() para evitar SystemExit en entornos tipo notebook/sandbox.
    # Si necesitás usar el código de salida en CI, podés leerlo desde logs o adaptar a tu runner.
    _ = exit_code
