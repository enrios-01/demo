# app.py
import os
import tempfile
from io import BytesIO
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
from logic import ProcesadorLogico

# ---------------------------
# Configuración general
# ---------------------------
st.set_page_config(
    page_title="Validador de Reportes - Tarjeta Naranja",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 Validador de Reportes - Tarjeta NARANJA")

# ---------------------------
# Estado global
# ---------------------------
if "procesador" not in st.session_state:
    st.session_state.procesador = ProcesadorLogico()

if "df_combinado" not in st.session_state:
    st.session_state.df_combinado = None

if "porcentajes_config" not in st.session_state:
    st.session_state.porcentajes_config = {}

if "reporte_por_plan" not in st.session_state:
    st.session_state.reporte_por_plan = {}

if "df_preview" not in st.session_state:
    st.session_state.df_preview = None

procesador: ProcesadorLogico = st.session_state.procesador


# ============================================================
# Funciones que se conservan/adaptan desde InterfazGrafica
# ============================================================

def construir_resumen_inicial():
    """
    (Conservada) Arma un resumen por cada 'Tipo y Nº' cargado:
    - Conteos VTA/DEV
    - Tabla de operaciones
    - Metadatos
    - Resumen impositivo
    """
    if not procesador.operaciones_por_resumen:
        st.info("No hay resúmenes cargados todavía.")
        return

    for clave, df in procesador.operaciones_por_resumen.items():
        st.markdown(f"### 📄 Resumen: **{clave}**")

        # Conteos
        vta = df[df["tipo_operacion"].astype(str).str.upper() == "VTA"]
        dev = df[df["tipo_operacion"].astype(str).str.upper().str.startswith("DEV")]

        c1, c2, c3 = st.columns(3)
        c1.metric("Operaciones totales", f"{len(df):,}")
        c2.metric("Ventas (VTA)", f"{len(vta):,}")
        c3.metric("Devoluciones (DEV)", f"{len(dev):,}")

        # Tabla de operaciones
        st.dataframe(df, use_container_width=True)

        # Metadatos
        meta = procesador.metadatos_por_resumen.get(clave, {})
        if meta:
            with st.expander("📑 Metadatos extraídos"):
                st.json(meta)

        # Resumen impositivo
        imp = procesador.resumen_impositivo_por_resumen.get(clave, {})
        if imp:
            with st.expander("🧾 Resumen impositivo"):
                st.json(imp)


def combinar_datos_archivos():
    """
    (Conservada) Combina TODAS las operaciones de todos los resúmenes en un único DF
    y lo fija como dataframe_operaciones activo para el resto del pipeline.
    """
    if not procesador.operaciones_por_resumen:
        st.warning("No hay archivos para combinar.")
        return None

    df_combinado = pd.concat(
        procesador.operaciones_por_resumen.values(), ignore_index=True
    )

    # IMPORTANTE: fijar combinado como base para detectar planes y recalcular
    procesador.dataframe_operaciones = df_combinado.copy()
    st.session_state.df_combinado = df_combinado
    return df_combinado


def pedir_porcentajes():
    """
    (Conservada) Editor de porcentajes por 'variante_plan' (arancel/interes/bonificacion)
    usando st.data_editor. Devuelve un diccionario listo para pasar a recalcular.
    """
    # Detectar configuraciones si aún no se detectaron
    if not procesador.diccionario_porcentajes_originales:
        _ = procesador.detectar_configuraciones_plan()

    if not procesador.diccionario_porcentajes_originales:
        st.info("No se detectaron variantes de plan. ¿Cargaste y combinaste los archivos?")
        return {}

    data = []
    for variante, vals in procesador.diccionario_porcentajes_originales.items():
        data.append({
            "variante_plan": variante,
            "arancel": float(vals.get("arancel", 0)),
            "interes": float(vals.get("interes", 0)),
            "bonificacion": float(vals.get("bonificacion", 0)),
        })

    df = pd.DataFrame(data).sort_values("variante_plan").reset_index(drop=True)

    st.caption("Editá los porcentajes para recalcular.")
    edited = st.data_editor(
        df,
        num_rows="fixed",
        use_container_width=True,
        key="editor_porcentajes",
    )

    dicc = {
        row["variante_plan"]: {
            "arancel": float(row["arancel"]),
            "interes": float(row["interes"]),
            "bonificacion": float(row["bonificacion"]),
        }
        for _, row in edited.iterrows()
    }
    return dicc


def construir_vista_previa():
    """
    (Conservada) Construye una vista previa post-recalculo:
    - DataFrame completo de resultados
    - Tabla de errores (estado == 'Incorrecta')
    - Resumen agregados por variante
    """
    if procesador.dataframe_resultados is None or procesador.dataframe_resultados.empty:
        st.warning("No hay resultados para vista previa. Ejecutá el recálculo.")
        return

    df = procesador.dataframe_resultados.copy()
    st.subheader("Tabla completa de resultados")
    st.dataframe(df, use_container_width=True)

    errores = df[df["estado"] == "Incorrecta"].copy()
    if not errores.empty:
        st.subheader("❌ Operaciones con errores")
        st.dataframe(errores, use_container_width=True)

        # Resumen por variante
        st.subheader("📌 Resumen de errores por variante")
        resumen = (errores
                   .groupby("variante_plan")
                   .agg(operaciones_erroneas=("estado", "count"),
                        diferencia_total=("diferencia", "sum"))
                   .reset_index()
                   .sort_values("operaciones_erroneas", ascending=False))
        st.dataframe(resumen, use_container_width=True)
    else:
        st.success("✅ No se encontraron operaciones con errores.")


def mostrar_resultados_recalculo():
    """
    (Conservada) Muestra resultados del recálculo y el reporte por plan.
    """
    if procesador.dataframe_resultados is None:
        st.info("Aún no hay recálculo. Andá a la pestaña 'Recalcular & Errores'.")
        return

    construir_vista_previa()

    # Reporte por plan (usa lógica del ProcesadorLogico)
    st.subheader("📑 Reporte por plan")
    reporte = procesador.generar_reporte_por_plan()
    st.session_state.reporte_por_plan = reporte

    if not reporte:
        st.info("No hay errores para reportar por plan.")
        return

    # Mostrar resumen del reporte (sin el DataFrame pesado en el JSON)
    resumen_liviano = {
        k: {
            "total_operaciones": v["total_operaciones"],
            "operaciones_erroneas": v["operaciones_erroneas"],
            "diferencia_total": v["diferencia_total"],
            "porcentajes_originales": v["porcentajes_originales"],
            "porcentajes_ajustados": v.get("porcentajes_ajustados", {}),
        }
        for k, v in reporte.items()
    }
    st.json(resumen_liviano)

    # Detalle expandible por plan
    for variante, datos in reporte.items():
        with st.expander(f"🔎 Detalle de errores: {variante}"):
            st.dataframe(datos["detalle_errores"], use_container_width=True)


def _crear_figura_pie_desde_df(df: pd.DataFrame):
    """
    Auxiliar para graficar distribución de planes (solo VTA) desde un DF.
    """
    ventas = df[df["tipo_operacion"].astype(str).str.upper() == "VTA"]
    if ventas.empty:
        return None

    conteo = ventas["plan"].astype(str).value_counts()

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.pie(conteo.values.tolist(), labels=conteo.index.tolist(), autopct="%1.1f%%")
    ax.set_title("Distribución de Planes (Ventas)")
    fig.tight_layout()
    return fig


def actualizar_grafico_planes():
    """
    (Conservada) Muestra el gráfico de distribución de planes.
    - En UI: mostramos con matplotlib -> st.pyplot(fig)
    - Para PDF: el procesador ya tiene guardar_grafico_planes_temp()
    """
    df_base = st.session_state.df_combinado or procesador.dataframe_operaciones
    if df_base is None or df_base.empty:
        st.info("No hay datos para graficar. Cargá y combiná archivos.")
        return

    fig = _crear_figura_pie_desde_df(df_base)
    if fig is None:
        st.info("No hay ventas (VTA) para graficar.")
        return
    st.pyplot(fig)


def manejar_exportacion():
    """
    (Conservada) Exporta CSV/Excel/PDF usando la lógica del ProcesadorLogico.
    - Usa archivos temporales y expone botones de descarga.
    """
    if procesador.dataframe_resultados is None or procesador.dataframe_resultados.empty:
        st.warning("No hay resultados para exportar. Ejecutá el recálculo primero.")
        return

    st.caption("Elegí el/los formatos y descargá los archivos generados.")
    col1, col2, col3 = st.columns(3)
    chk_csv = col1.checkbox("CSV", value=True)
    chk_xlsx = col2.checkbox("Excel", value=True)
    chk_pdf = col3.checkbox("PDF", value=True)

    formatos = []
    if chk_csv: formatos.append("csv")
    if chk_xlsx: formatos.append("excel")
    if chk_pdf: formatos.append("pdf")

    if not formatos:
        st.info("Seleccioná al menos un formato.")
        return

    if st.button("📦 Generar archivos"):
        with st.spinner("Generando exportaciones…"):
            with tempfile.TemporaryDirectory() as tmpdir:
                base = os.path.join(tmpdir, "reporte")
                rutas = procesador.exportacion_de_informes(formatos, ruta_base=base)

                # Mostrar botones de descarga
                for fmt, ruta in rutas.items():
                    if not os.path.exists(ruta):
                        continue
                    with open(ruta, "rb") as f:
                        data = f.read()
                    if fmt == "csv":
                        mime = "text/csv"
                    elif fmt == "excel":
                        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    else:
                        mime = "application/pdf"

                    st.download_button(
                        label=f"⬇️ Descargar {fmt.upper()}",
                        data=data,
                        file_name=f"reporte.{ 'xlsx' if fmt=='excel' else fmt }",
                        mime=mime,
                    )
        st.success("Exportaciones listas ✅")


def manejar_recalculo():
    """
    (Conservada) Orquesta el recálculo:
    - Usa porcentajes editados; si no, usa los originales detectados.
    - Llama a recalcular_con_porcentajes_ajustados()
    - Actualiza vista previa y reporte por plan
    """
    if procesador.dataframe_operaciones is None or procesador.dataframe_operaciones.empty:
        st.warning("No hay datos para recalcular. Cargá y combiná archivos.")
        return

    # Si el usuario aún no editó porcentajes, usar originales detectados
    porcentajes = st.session_state.porcentajes_config
    if not porcentajes:
        if not procesador.diccionario_porcentajes_originales:
            _ = procesador.detectar_configuraciones_plan()
        porcentajes = procesador.diccionario_porcentajes_originales

    with st.spinner("Recalculando…"):
        df_res = procesador.recalcular_con_porcentajes_ajustados(porcentajes)
        st.session_state.df_preview = df_res

    st.success("Recalculo completado ✅")
    construir_vista_previa()


# ============================================================
# Interfaz (layout Streamlit)
# ============================================================

with st.sidebar:
    st.header("⚙️ Acciones")
    if st.button("🧹 Limpiar todo"):
        st.session_state.clear()
        st.experimental_rerun()

    st.markdown("---")
    st.caption("Subí uno o más PDFs del resumen de Tarjeta Naranja.")

uploaded_files = st.file_uploader(
    "📂 Subí tus archivos PDF",
    type=["pdf"],
    accept_multiple_files=True,
)

# Cargar PDFs
if uploaded_files:
    with st.spinner("Procesando PDFs…"):
        for archivo in uploaded_files:
            # Extraer datos
            df_ops = procesador.extraer_operaciones_del_pdf(archivo)
            meta = procesador.extraer_metadatos_del_pdf(archivo)

            # Determinar clave única (Tipo y Nº o nombre de archivo)
            base_key = meta.get("tipo_numero", archivo.name).strip() or archivo.name
            key = base_key
            idx = 2
            while key in procesador.operaciones_por_resumen:
                key = f"{base_key} ({idx})"
                idx += 1

            # Guardar en estructuras por-resumen
            procesador.operaciones_por_resumen[key] = df_ops.copy()
            procesador.metadatos_por_resumen[key] = meta
            procesador.resumen_impositivo_por_resumen[key] = procesador.resumen_impositivo

    st.success("Carga finalizada ✅")

# Tabs principales
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Resumen inicial",
    "🧩 Combinar & Detectar",
    "⚙️ Configuración",
    "🔄 Recalcular & Errores",
    "📈 Gráfico",
    "💾 Exportar",
])

# --- TAB 1: Resumen inicial
with tab1:
    construir_resumen_inicial()

# --- TAB 2: Combinar & Detectar
with tab2:
    st.subheader("Combinar todos los resúmenes en una sola vista")
    if st.button("🔗 Combinar archivos"):
        dfc = combinar_datos_archivos()
        if dfc is not None:
            st.success(f"Combinados {len(dfc):,} registros.")
            st.dataframe(dfc, use_container_width=True)

    st.markdown("---")
    st.subheader("Detectar configuraciones de planes (desde combinado)")
    if st.button("🧭 Detectar planes"):
        if st.session_state.df_combinado is None:
            st.info("Primero combiná los archivos.")
        else:
            procesador.dataframe_operaciones = st.session_state.df_combinado.copy()
            dicc = procesador.detectar_configuraciones_plan()
            if dicc:
                st.success(f"Detectadas {len(dicc)} variantes de plan.")
                st.json(dicc)
            else:
                st.warning("No se detectaron variantes.")

# --- TAB 3: Configuración de planes
with tab3:
    st.subheader("Editar porcentajes por variante de plan")
    dicc_nuevos = pedir_porcentajes()
    c1, c2 = st.columns(2)
    if c1.button("💾 Guardar configuración"):
        st.session_state.porcentajes_config = dicc_nuevos
        st.success("Configuración guardada en memoria.")
    if c2.button("↩️ Restaurar originales"):
        st.session_state.porcentajes_config = procesador.diccionario_porcentajes_originales
        st.info("Se restauraron los porcentajes originales detectados.")

# --- TAB 4: Recalcular & Errores
with tab4:
    st.subheader("Recalcular liquidación y ver errores")
    if st.button("🔄 Ejecutar recálculo"):
        manejar_recalculo()
    else:
        # Si ya hay preview previa, mostrar
        if st.session_state.df_preview is not None:
            construir_vista_previa()
        else:
            st.info("Aún no ejecutaste el recálculo.")

    st.markdown("---")
    st.subheader("Reporte por plan")
    if st.session_state.reporte_por_plan:
        # Resumen liviano ya mostrado en mostrar_resultados_recalculo()
        # Permitimos re-generarlo explícitamente
        if st.button("📑 Regenerar reporte"):
            mostrar_resultados_recalculo()
    else:
        if procesador.dataframe_resultados is not None:
            mostrar_resultados_recalculo()

# --- TAB 5: Gráfico
with tab5:
    st.subheader("Distribución de planes (Ventas - VTA)")
    actualizar_grafico_planes()

# --- TAB 6: Exportar
with tab6:
    st.subheader("Exportación de resultados")
    manejar_exportacion()


# ---------- NUEVAS FUNCIONALIDADES A IMPLEMENTAR ----------

def manejar_carga_pdf_streamlit(uploaded_files):
    """
    Reemplazo completo de manejar_carga_pdf con detección de duplicados
    """
    if "archivos_cargados" not in st.session_state:
        st.session_state.archivos_cargados = {}
    
    if "archivos_duplicados" not in st.session_state:
        st.session_state.archivos_duplicados = {}
    
    for i, archivo in enumerate(uploaded_files):
        with st.spinner(f"Procesando {archivo.name} ({i+1}/{len(uploaded_files)})..."):
            # Extraer datos
            df_ops = procesador.extraer_operaciones_del_pdf(archivo)
            meta = procesador.extraer_metadatos_del_pdf(archivo)
            
            # Verificar duplicados por Tipo y Nº
            tipo_numero = meta.get("tipo_numero", archivo.name)
            duplicado = False
            archivo_duplicado = None
            
            for ruta, datos in st.session_state.archivos_cargados.items():
                if datos["metadatos"].get("tipo_numero") == tipo_numero and ruta != archivo.name:
                    duplicado = True
                    archivo_duplicado = ruta
                    break
            
            if duplicado:
                st.session_state.archivos_duplicados[archivo.name] = {
                    "dataframe": df_ops,
                    "metadatos": meta,
                    "procesador": ProcesadorLogico(),  # Nuevo procesador para este archivo
                    "duplicado_de": archivo_duplicado
                }
                st.warning(f"Archivo duplicado detectado: {tipo_numero}")
            else:
                st.session_state.archivos_cargados[archivo.name] = {
                    "dataframe": df_ops,
                    "metadatos": meta,
                    "procesador": procesador  # Usar el procesador principal
                }

def mostrar_y_resolver_duplicados():
    """
    Interfaz para resolver conflictos de archivos duplicados
    """
    if not st.session_state.get("archivos_duplicados"):
        return
    
    st.subheader("📝 Resolución de archivos duplicados")
    
    for archivo, datos in st.session_state.archivos_duplicados.items():
        with st.expander(f"Conflicto: {archivo}"):
            st.write(f"**Archivo:** {archivo}")
            st.write(f"**Tipo y Nº:** {datos['metadatos'].get('tipo_numero', 'No identificado')}")
            st.write(f"**Duplicado de:** {datos['duplicado_de']}")
            
            opcion = st.radio(
                f"¿Qué deseas hacer con {archivo}?",
                ["Reemplazar archivo existente", "Conservar ambos (cambiar Tipo y Nº)", "Descartar archivo nuevo"],
                key=f"opcion_duplicado_{archivo}"
            )
            
            if opcion == "Conservar ambos (cambiar Tipo y Nº)":
                nuevo_tipo_numero = st.text_input(
                    "Nuevo valor para Tipo y Nº:",
                    value=datos["metadatos"].get("tipo_numero", ""),
                    key=f"nuevo_tipo_{archivo}"
                )
                if st.button("Aplicar cambios", key=f"aplicar_{archivo}"):
                    if nuevo_tipo_numero:
                        datos["metadatos"]["tipo_numero"] = nuevo_tipo_numero
                        st.session_state.archivos_cargados[archivo] = datos
                        del st.session_state.archivos_duplicados[archivo]
                        st.rerun()
            
            elif opcion == "Reemplazar archivo existente":
                if st.button("Confirmar reemplazo", key=f"reemplazar_{archivo}"):
                    # Eliminar el existente y agregar el nuevo
                    del st.session_state.archivos_cargados[datos["duplicado_de"]]
                    st.session_state.archivos_cargados[archivo] = datos
                    del st.session_state.archivos_duplicados[archivo]
                    st.rerun()
            
            elif opcion == "Descartar archivo nuevo":
                if st.button("Confirmar descarte", key=f"descarte_{archivo}"):
                    del st.session_state.archivos_duplicados[archivo]
                    st.rerun()

def mostrar_tabla_archivos():
    """
    Tabla interactiva de archivos cargados con acciones
    """
    if not st.session_state.get("archivos_cargados"):
        st.info("No hay archivos cargados")
        return
    
    # Preparar datos para la tabla
    datos_tabla = []
    for archivo, datos in st.session_state.archivos_cargados.items():
        operaciones = len(datos["dataframe"]) if datos["dataframe"] is not None else 0
        datos_tabla.append({
            "Archivo": archivo,
            "Tipo y Nº": datos["metadatos"].get("tipo_numero", "Sin identificar"),
            "Operaciones": operaciones,
            "Acciones": archivo  # Identificador para acciones
        })
    
    df = pd.DataFrame(datos_tabla)
    
    # Usar aggrid para tabla interactiva con botones
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_column("Acciones", header_name="Acciones", cellRenderer=JsCode('''
        function(params) {
            return '<button onclick="alert(\'Eliminar ' + params.value + '\')">Eliminar</button>'
        }
    '''))
    
    grid_options = gb.build()
    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        height=200,
        width="100%",
        theme="streamlit",
        allow_unsafe_jscode=True
    )
    
    # Manejar acciones (simplificado - en realidad necesitarías más lógica JS)
    if grid_response['selected_rows']:
        st.write("Acción seleccionada para:", grid_response['selected_rows'])

# ---------- MEJORAS A LAS FUNCIONES EXISTENTES ----------

def pedir_porcentajes_mejorado():
    """
    Versión mejorada con validación y previsualización
    """
    if not procesador.diccionario_porcentajes_originales:
        st.info("No se detectaron configuraciones de plan. Combine archivos primero.")
        return {}
    
    data = []
    for variante, vals in procesador.diccionario_porcentajes_originales.items():
        data.append({
            "variante_plan": variante,
            "arancel_original": float(vals.get("arancel", 0)),
            "interes_original": float(vals.get("interes", 0)),
            "bonificacion_original": float(vals.get("bonificacion", 0)),
            "arancel_ajustado": float(vals.get("arancel", 0)),
            "interes_ajustado": float(vals.get("interes", 0)),
            "bonificacion_ajustado": float(vals.get("bonificacion", 0)),
        })
    
    df = pd.DataFrame(data).sort_values("variante_plan").reset_index(drop=True)
    
    # Editor de porcentajes con columnas editables
    st.markdown("### 📊 Configuración de porcentajes por plan")
    st.caption("Edite las columnas 'ajustado' para modificar los porcentajes. Los cambios se aplicarán al recalcular.")
    
    # Configurar columnas editables
    column_config = {
        "variante_plan": st.column_config.TextColumn("Variante de Plan", width="large"),
        "arancel_original": st.column_config.NumberColumn("Arancel Original (%)", format="%.2f", disabled=True),
        "interes_original": st.column_config.NumberColumn("Interés Original (%)", format="%.2f", disabled=True),
        "bonificacion_original": st.column_config.NumberColumn("Bonificación Original (%)", format="%.2f", disabled=True),
        "arancel_ajustado": st.column_config.NumberColumn("Arancel Ajustado (%)", format="%.2f", min_value=0.0, max_value=100.0),
        "interes_ajustado": st.column_config.NumberColumn("Interés Ajustado (%)", format="%.2f", min_value=0.0, max_value=100.0),
        "bonificacion_ajustado": st.column_config.NumberColumn("Bonificación Ajustada (%)", format="%.2f", min_value=0.0, max_value=100.0),
    }
    
    edited_df = st.data_editor(
        df,
        column_config=column_config,
        num_rows="fixed",
        use_container_width=True,
        key="editor_porcentajes_mejorado"
    )
    
    # Convertir a diccionario de porcentajes
    nuevos_porcentajes = {}
    for _, row in edited_df.iterrows():
        nuevos_porcentajes[row["variante_plan"]] = {
            "arancel": row["arancel_ajustado"],
            "interes": row["interes_ajustado"],
            "bonificacion": row["bonificacion_ajustado"]
        }
    
    # Mostrar resumen de cambios
    st.markdown("### 📈 Resumen de cambios")
    for variante in nuevos_porcentajes:
        original = next((item for item in data if item["variante_plan"] == variante), {})
        if original:
            cambios = []
            for campo in ["arancel", "interes", "bonificacion"]:
                if original[f"{campo}_original"] != nuevos_porcentajes[variante][campo]:
                    cambios.append(f"{campo}: {original[f'{campo}_original']}% → {nuevos_porcentajes[variante][campo]}%")
            
            if cambios:
                st.info(f"**{variante}**: {' | '.join(cambios)}")
    

    return nuevos_porcentajes
