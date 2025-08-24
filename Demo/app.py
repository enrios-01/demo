"""
App Streamlit principal
----------------------
Versión reescrita para usar las funciones adaptadas de `server.py` (sin PyQt6).

Flujo:
- Usa `process_content` para previsualizar archivos subidos.
- Usa `get_base_path` para mostrar información del entorno.
- Botón principal ejecuta lógica placeholder.

Requisitos: `streamlit`
"""

import streamlit as st
import os
from server import get_base_path, process_content, DEFAULT_PREVIEW_LEN


def main():
    st.set_page_config(page_title="Demo App", layout="wide")
    st.title("Demo App (Frontend)")

    # Información básica
    st.write(f"Ruta base del backend: {get_base_path()}")

    # Carga de archivo y preview
    st.subheader("Subida y previsualización de archivos")
    uploaded_file = st.file_uploader("Elegí un archivo", type=["txt", "csv", "xlsx", "pdf"])
    if uploaded_file:
        st.write(f"Archivo recibido: {uploaded_file.name}")
        content = uploaded_file.read()
        preview = process_content(content, DEFAULT_PREVIEW_LEN)
        st.text_area("Contenido del archivo (preview):", value=preview, height=300)

    # Botón principal
    if st.button("Ejecutar lógica principal"):
        # Aquí iría la lógica real del backend (aún no definida)
        st.success("Lógica ejecutada correctamente.")

    st.info("Fin del frontend adaptado.")


if __name__ == "__main__":
    main()
