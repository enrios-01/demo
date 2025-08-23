import streamlit as st
import pandas as pd
import base64
from PIL import Image
import io

# Importar el backend
from server import DemoBackend

# Configurar página
st.set_page_config(
    page_title="Analizador de Resúmenes Naranja",
    page_icon="🧡",
    layout="wide"
)

# Inicializar backend en session state
if 'backend' not in st.session_state:
    st.session_state.backend = DemoBackend()

def main():
    st.title("🧡 Analizador de Resúmenes Naranja")
    st.markdown("---")
    
    # Sidebar para carga de archivos
    with st.sidebar:
        st.header("📁 Cargar Resúmenes")
        archivos = st.file_uploader(
            "Selecciona archivos PDF", 
            type=['pdf'],
            accept_multiple_files=True
        )
        
        if archivos:
            for archivo in archivos:
                if archivo.name not in st.session_state.backend.archivos_procesados:
                    with st.spinner(f"Procesando {archivo.name}..."):
                        resultado = st.session_state.backend.procesar_pdf(
                            archivo.read(), 
                            archivo.name
                        )
                        
                        if resultado['success']:
                            st.success(f"✅ {archivo.name}")
                            st.json(resultado['metadatos'])
                        else:
                            st.error(f"❌ Error: {resultado['error']}")
    
    # Pestañas principales
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dashboard", 
        "⚙️ Configuración", 
        "📈 Resultados", 
        "💾 Exportar"
    ])
    
    with tab1:
        mostrar_dashboard()
    
    with tab2:
        mostrar_configuracion()
    
    with tab3:
        mostrar_resultados()
    
    with tab4:
        mostrar_exportacion()

def mostrar_dashboard():
    st.header("Dashboard de Análisis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Mostrar gráfico
        grafico_base64 = st.session_state.backend.generar_grafico()
        if grafico_base64:
            st.subheader("Distribución de Planes")
            st.image(base64.b64decode(grafico_base64))
        else:
            st.info("Carga archivos PDF para ver el gráfico")
    
    with col2:
        # Mostrar estadísticas
        st.subheader("Estadísticas")
        if st.session_state.backend.procesador.dataframe_operaciones is not None:
            df = st.session_state.backend.procesador.dataframe_operaciones
            total_ops = len(df)
            ventas = len(df[df['tipo_operacion'].str.upper() == 'VTA'])
            devoluciones = len(df[df['tipo_operacion'].str.upper() == 'DEV'])
            
            st.metric("Operaciones Totales", total_ops)
            st.metric("Ventas (VTA)", ventas)
            st.metric("Devoluciones (DEV)", devoluciones)
            st.metric("Archivos Cargados", len(st.session_state.backend.archivos_procesados))
        else:
            st.info("No hay datos para mostrar")

def mostrar_configuracion():
    st.header("Configuración de Porcentajes")
    
    if not st.session_state.backend.archivos_procesados:
        st.info("Primero carga algunos archivos PDF")
        return
    
    # Recopilar todas las configuraciones únicas
    todas_configuraciones = {}
    for archivo, datos in st.session_state.backend.archivos_procesados.items():
        for plan, porcentajes in datos['configuraciones'].items():
            if plan not in todas_configuraciones:
                todas_configuraciones[plan] = porcentajes
    
    # Mostrar formulario de configuración
    with st.form("config_porcentajes"):
        st.subheader("Ajustar Porcentajes por Plan")
        
        porcentajes_ajustados = {}
        for plan, porcentajes in todas_configuraciones.items():
            st.markdown(f"**{plan}**")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                arancel = st.number_input(
                    "Arancel %", 
                    value=float(porcentajes['arancel']),
                    key=f"arancel_{plan}",
                    format="%.2f"
                )
            with col2:
                interes = st.number_input(
                    "Interés %", 
                    value=float(porcentajes['interes']),
                    key=f"interes_{plan}",
                    format="%.2f"
                )
            with col3:
                bonificacion = st.number_input(
                    "Bonificación %", 
                    value=float(porcentajes['bonificacion']),
                    key=f"bonif_{plan}",
                    format="%.2f"
                )
            
            porcentajes_ajustados[plan] = {
                'arancel': arancel,
                'interes': interes,
                'bonificacion': bonificacion
            }
        
        if st.form_submit_button("🔄 Recalcular Operaciones"):
            with st.spinner("Recalculando..."):
                resultado = st.session_state.backend.recalcular_operaciones(porcentajes_ajustados)
                if resultado['success']:
                    st.success("✅ Recalculo completado")
                    st.session_state.reporte = resultado['reporte']
                else:
                    st.error(f"❌ Error: {resultado['error']}")

def mostrar_resultados():
    st.header("Resultados del Análisis")
    
    if 'reporte' not in st.session_state:
        st.info("Configura los porcentajes y haz clic en 'Recalcular'")
        return
    
    reporte = st.session_state.reporte
    
    for plan, datos in reporte.items():
        with st.expander(f"📋 {plan}"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Operaciones Totales", datos['total_operaciones'])
                st.metric("Operaciones con Error", datos['operaciones_erroneas'])
                st.metric("Diferencia Total", f"${datos['diferencia_total']:,.2f}")
            
            with col2:
                st.write("**Porcentajes Originales:**")
                st.json(datos['porcentajes_originales'])
                st.write("**Porcentajes Ajustados:**")
                st.json(datos['porcentajes_ajustados'])
            
            # Mostrar tabla de operaciones con error
            if not datos['detalle_errores'].empty:
                st.write("**Operaciones con Error:**")
                st.dataframe(datos['detalle_errores'])

def mostrar_exportacion():
    st.header("Exportar Resultados")
    
    if st.session_state.backend.procesador.dataframe_resultados is None:
        st.info("Primero procesa algunos archivos y realiza el recálculo")
        return
    
    formato = st.selectbox(
        "Seleccionar formato de exportación",
        ["csv", "xlsx", "pdf"]
    )
    
    if st.button("💾 Descargar Resultados"):
        with st.spinner("Generando archivo..."):
            contenido = st.session_state.backend.exportar_resultados(formato)
            
            if contenido:
                # Crear botón de descarga MÁS ROBUSTO
                import base64
                b64 = base64.b64encode(contenido).decode()
                download_name = f"resultados_naranja.{formato}"
                
                st.markdown(
                    f'<a href="data:application/octet-stream;base64,{b64}" download="{download_name}" style="background-color:#4CAF50;color:white;padding:10px 20px;text-align:center;text-decoration:none;display:inline-block;border-radius:5px;">⬇️ Descargar {formato.upper()}</a>',
                    unsafe_allow_html=True
                )
                
                st.success("✅ Archivo generado correctamente")
            else:
                st.error("❌ Error al generar el archivo")
if __name__ == "__main__":
    main()