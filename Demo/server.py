import os
import re
import pandas as pd
import pdfplumber
import matplotlib.pyplot as plt
import tempfile
from io import BytesIO
import base64

# === EL CODIGO ORIGINAL EMPIEZA ACA ===

# === Librerías estándar ===
import os
import re

# === Librerías de terceros ===
import pdfplumber
import pandas as pd
import matplotlib.pyplot as plt

# === PyQt6 === (en la sección de imports al principio del archivo)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QLabel, QPushButton, QFileDialog, QScrollArea,
    QLineEdit, QFormLayout, QMessageBox, QTableWidget,
    QTableWidgetItem, QDialog, QDialogButtonBox,
    QHBoxLayout, QGroupBox, QProgressBar,
    QInputDialog  # <-- AÑADIR ESTA IMPORTACIÓN
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

# === ReportLab (para PDF) ===
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm

# === Matplotlib (para gráficos embebidos en PyQt6) ===
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import QThread, pyqtSignal

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QFileDialog, QMessageBox, QHeaderView
from typing import Optional

# ========================================================
# CLASE 0: Clase para diálogo de carga de archivos
# ========================================================
class DialogoCargaArchivos(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cargar hasta 10 archivos PDF")

        layout = QVBoxLayout(self)
        self.campos = []

        for i in range(5):
            fila = QHBoxLayout()
            campo = QLineEdit(self)
            boton = QPushButton("Examinar", self)
            boton.clicked.connect(lambda _, c=campo: self.seleccionar_archivo(c))
            fila.addWidget(campo)
            fila.addWidget(boton)
            layout.addLayout(fila)
            self.campos.append(campo)

        self.boton_aceptar = QPushButton("Aceptar", self)
        self.boton_aceptar.clicked.connect(self.accept)
        layout.addWidget(self.boton_aceptar)

    def seleccionar_archivo(self, campo):
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo PDF", "", "Archivos PDF (*.pdf)")
        if ruta:
            nombres = [os.path.basename(c.text()) for c in self.campos if c.text()]
            if os.path.basename(ruta) in nombres:
                QMessageBox.warning(self, "Duplicado", "⚠️ Ya existe un archivo con ese nombre. Elimínelo antes de continuar.")
                return
            campo.setText(ruta)

    def obtener_rutas(self):
        return [c.text() for c in self.campos if c.text()]
# ========================================================
# CLASE 1: Clase para menejar tareas en hilos secundarios
# ========================================================
class WorkerThread(QThread):
    progreso = pyqtSignal(str)   # Para enviar mensajes de estado a la UI
    terminado = pyqtSignal(object)  # Para devolver un resultado cuando termine
    error = pyqtSignal(str)      # Para manejar errores

    def __init__(self, funcion, *args, **kwargs):
        super().__init__()
        self.funcion = funcion
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.progreso.emit("⏳ Ejecutando tarea en hilo secundario...")
            resultado = self.funcion(*self.args, **self.kwargs)
            self.terminado.emit(resultado)
        except Exception as e:
            self.error.emit(str(e))
# ========================================================
# CLASE 2: Cálculos auxiliares y utilidades de formato
# ========================================================
class CalculosAuxiliares:
    """Contiene métodos utilitarios para conversiones, formateos y cálculos básicos."""

    @staticmethod
    def convertir_a_numero(valor):
        """Convierte strings numéricos con formatos variados a float."""
        if isinstance(valor, (int, float)):
            return float(valor)
        if valor is None:
            return 0.0
        
        texto_limpio = str(valor).strip()
        texto_limpio = texto_limpio.replace("$", "").replace("%", "").replace(" ", "")
        
        if "," in texto_limpio and "." in texto_limpio:
            texto_limpio = texto_limpio.replace(".", "").replace(",", ".")
        elif "," in texto_limpio:
            texto_limpio = texto_limpio.replace(",", ".")
        
        if texto_limpio == "" or texto_limpio == "-":
            return 0.0
          
        try:
            return float(texto_limpio)
        except ValueError:
            return 0.0

    @staticmethod
    def formatear_moneda_pesos(valor):
        """Formatea números al formato monetario argentino."""
        try:
            valor_float = float(valor)
        except (ValueError, TypeError):
            return "0,00"
            
        texto_formateado = f"{valor_float:,.2f}"
        return texto_formateado.replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def formatear_porcentaje(valor):
        """Formatea números al formato porcentual argentino."""
        try:
            valor_float = float(valor)
        except (ValueError, TypeError):
            return "0,00 %"
            
        return f"{valor_float:.2f}".replace(".", ",") + " %"

    @staticmethod
    def extraer_numero_de_plan(texto_plan):
        """Extrae el número de plan de un string."""
        coincidencia = re.search(r"\d+", str(texto_plan))
        return int(coincidencia.group()) if coincidencia else 0

    @staticmethod
    def generar_resumen_operaciones(dataframe_operaciones, diccionario_metadatos):
        """Genera texto HTML con estadísticas resumidas de las operaciones."""
        total_operaciones = len(dataframe_operaciones)
        total_ventas = sum(dataframe_operaciones["tipo_operacion"].str.upper() == "VTA")
        total_devoluciones = sum(dataframe_operaciones["tipo_operacion"].str.upper() == "DEV")

        lista_planes = dataframe_operaciones["plan"].astype(str).dropna().unique().tolist()
        lista_planes_ordenada = sorted(lista_planes, key=CalculosAuxiliares.extraer_numero_de_plan)

        lineas_por_plan = [
            f"• Plan {plan}: {sum(dataframe_operaciones['plan'].astype(str) == plan)} operaciones"
            for plan in lista_planes_ordenada
        ]

        return (
            f"Operaciones encontradas: {total_operaciones}<br>"
            f"Ventas (VTA): {total_ventas}<br>"
            f"Devoluciones (DEV): {total_devoluciones}<br><br>"
            f"Distribución por Plan:<br>{'<br>'.join(lineas_por_plan)}<br><br>"
            f"Fecha Emisión: {diccionario_metadatos.get('fecha_emision', '--')}<br>"
            f"Fecha Pago: {diccionario_metadatos.get('fecha_pago', '--')}<br>"
            f"Forma Pago: {diccionario_metadatos.get('forma_pago', '--')}"
        )    
# ========================================================
# CLASE 3: Procesador lógico (lógica de negocio y cálculos)
# ========================================================
class ProcesadorLogico:
    def __init__(self):
        # Diccionarios para manejar múltiples resúmenes
        self.operaciones_por_resumen = {}                # { "Tipo y Nº": DataFrame }
        self.resultados_por_resumen = {}                 # { "Tipo y Nº": DataFrame }
        self.metadatos_por_resumen = {}                  # { "Tipo y Nº": {fecha_emision, fecha_pago, forma_pago, ...} }
        self.porcentajes_originales_por_resumen = {}     # { "Tipo y Nº": {variante_plan: {arancel, interes, bonificacion}} }
        self.porcentajes_ajustados_por_resumen = {}      # { "Tipo y Nº": {variante_plan: {arancel, interes, bonificacion}} }
        self.resumen_impositivo_por_resumen = {}         # { "Tipo y Nº": {detalles_facturacion, retenciones_impositivas, neto_liquidado} }

        # Atributos temporales para el procesamiento actual
        self.dataframe_operaciones = None
        self.dataframe_resultados = None
        self.diccionario_metadatos = {}
        self.diccionario_porcentajes_originales = {}
        self.diccionario_porcentajes_ajustados = {}
        self.resumen_impositivo = None

    def extraer_operaciones_del_pdf(self, ruta_archivo_pdf):
        """Extrae y normaliza las operaciones de un PDF de resumen."""
        lista_filas_extraidas = []
        
        with pdfplumber.open(ruta_archivo_pdf) as documento_pdf:
            for pagina_actual in documento_pdf.pages:
                tablas_extraidas = pagina_actual.extract_tables() or []
                
                for tabla_actual in tablas_extraidas:
                    for fila_actual in tabla_actual or []:
                        if fila_actual and re.match(r"\d{2}/\d{2}/\d{4}", str(fila_actual[0])):
                            lista_filas_extraidas.append(fila_actual)

        columnas_esperadas = [
            "fecha", "terminal-lote", "presentacion", "cupon", "plan", "importe",
            "arancel_pct", "arancel_valor", "interes_pct", "interes_valor",
            "bonificacion_pct", "bonificacion_valor", "tipo_operacion"
        ]

        if not lista_filas_extraidas:
            self.dataframe_operaciones = pd.DataFrame(columns=columnas_esperadas)
            return self.dataframe_operaciones

        dataframe_crudo = pd.DataFrame(
            lista_filas_extraidas,
            columns=columnas_esperadas[:len(lista_filas_extraidas[0])]
        )

        for columna_numerica in [
            "importe", "arancel_pct", "arancel_valor", "interes_pct",
            "interes_valor", "bonificacion_pct", "bonificacion_valor"
        ]:
            if columna_numerica in dataframe_crudo.columns:
                dataframe_crudo[columna_numerica] = dataframe_crudo[columna_numerica].apply(
                    CalculosAuxiliares.convertir_a_numero
                )

        for columna_requerida in columnas_esperadas:
            if columna_requerida not in dataframe_crudo.columns:
                valor_por_defecto = (
                    0.0 if any(x in columna_requerida for x in ["pct", "valor"]) or columna_requerida == "importe"
                    else ""
                )
                dataframe_crudo[columna_requerida] = valor_por_defecto

        self.dataframe_operaciones = dataframe_crudo[columnas_esperadas]
        if "terminal_lote" in dataframe_crudo.columns:
            dataframe_crudo.rename(columns={"terminal_lote": "terminal-lote"}, inplace=True)

        return self.dataframe_operaciones

    def extraer_metadatos_del_pdf(self, ruta_archivo_pdf):
        """Extrae metadatos clave del documento PDF con patrones específicos para Tarjeta Naranja."""
        metadatos = {
            "tipo_numero": "",   # 🔹 Nuevo campo
            "fecha_emision": "",
            "fecha_pago": "",
            "forma_pago": ""
        }


        # Patrones optimizados para este formato específico de resumen
        patrones = {
            "fecha_emision": [
                r"Fecha\s*de\s*Emisi[oó]n\s*:\s*(\d{2}/\d{2}/\d{4})",
                r"Tipo\s*y\s*N[º°]\s*:\s*.*?\n.*?Fecha\s*de\s*Emisi[oó]n\s*:\s*(\d{2}/\d{2}/\d{4})",
                r"Hoja\s*N[º°]\s*:\s*\d+\nFecha\s*de\s*Emisi[oó]n\s*:\s*(\d{2}/\d{2}/\d{4})"
            ],
            "tipo_numero": [
                r"Tipo\s*y\s*N[º°]\s*:\s*(\S.*?)(?:\n|$)"
            ]
        }


        texto_paginas = ""   # 🔹 Inicialización
        with pdfplumber.open(ruta_archivo_pdf) as pdf:
            # ✅ leer todas las páginas
            texto_paginas = "\n".join((p.extract_text() or "") for p in pdf.pages)

        texto_normalizado = re.sub(r'\s+', ' ', texto_paginas).strip()

        # ---------------------------------------------------
        # 🔹 Fecha de Emisión
        # ---------------------------------------------------
        for patron in patrones["fecha_emision"]:
            match = re.search(patron, texto_normalizado, re.IGNORECASE)
            if match:
                metadatos["fecha_emision"] = next((g for g in match.groups() if g), "")
                break
        # Tipo y Nº
        for patron in patrones["tipo_numero"]:
            match = re.search(patron, texto_paginas, re.IGNORECASE)
            if match:
                metadatos["tipo_numero"] = match.group(1).strip()
                break


        # ---------------------------------------------------
        # 🔹 Forma y Fecha de Pago (con soporte a varios métodos)
        # ---------------------------------------------------
        metodos_pago = ["Echeq", "Transferencia", "Dep[oó]sito", "Nota de Cr[eé]dito"]

        # Construir patrón dinámico
        patron_metodo_pago = (
            r"(" + "|".join(metodos_pago) + r")"
            r"(?:\s*a\s*la\s*Orden)?(?:\s*Pago\s*Diferido)?"
            r"\s*Fecha\s*:\s*(\d{2}/\d{2}/\d{4})"
        )

        match = re.search(patron_metodo_pago, texto_paginas, re.IGNORECASE)
        if match:
            metadatos["forma_pago"] = match.group(1).strip()
            metadatos["fecha_pago"] = match.group(2).strip()

        # ---------------------------------------------------
        # 🔹 Fallback si no se encontró con el patrón dinámico
        # ---------------------------------------------------
        if not metadatos["fecha_pago"]:
            posibles_fechas = [
                r"Fecha\s*de\s*Pago\s*:\s*(\d{2}/\d{2}/\d{4})",
                r"Detalle\s*de\s*Cupones\s*Liquidados.*?Fecha\s*de\s*Pago\s*:\s*(\d{2}/\d{2}/\d{4})",
                r"Echeq\s*a\s*la\s*Orden\s*Pago\s*Diferido\s*Fecha\s*:\s*(\d{2}/\d{2}/\d{4})"
            ]
            for patron in posibles_fechas:
                match = re.search(patron, texto_paginas, re.IGNORECASE)
                if match:
                    metadatos["fecha_pago"] = next((g for g in match.groups() if g), "")
                    break

        if not metadatos["forma_pago"]:
            posibles_formas = [
                r"A\s*Pagar\s*\n.*?\n.*?\n.*?\n(.*?)\n",
                r"Echeq\s*a\s*la\s*Orden\s*(Pago\s*Diferido)",
                r"Forma\s*de\s*Pago\s*:\s*(.*?)(?:\n|$)"
            ]
            for patron in posibles_formas:
                match = re.search(patron, texto_paginas, re.IGNORECASE)
                if match:
                    forma_pago = next((g for g in match.groups() if g), "")
                    forma_pago = forma_pago.strip()
                    forma_pago = re.sub(r'^\W+|\W+$', '', forma_pago)
                    forma_pago = ' '.join(forma_pago.split())
                    if forma_pago:
                        metadatos["forma_pago"] = forma_pago
                        break

        # ---------------------------------------------------
        # 🔹 Validación final de fechas
        # ---------------------------------------------------
        for campo in ["fecha_emision", "fecha_pago"]:
            if metadatos[campo] and not re.match(r"\d{2}/\d{2}/\d{4}", metadatos[campo]):
                metadatos[campo] = ""

        # ---------------------------------------------------
        # 🔹 Guardar resultados
        # ---------------------------------------------------
        self.diccionario_metadatos = metadatos
        self.resumen_impositivo = self.impuestos_retenciones_contribuciones(texto_paginas)
        return metadatos

    def impuestos_retenciones_contribuciones(self, texto_completo: str):

        flags = re.I | re.S
        res = {
            "detalles_facturacion": {},   # {concepto: "$ monto"}
            "retenciones_impositivas": {},# {concepto: "$ monto"}
            "neto_liquidado": None
        }

        # ---------- 1) Bloque "Detalles de facturación" ----------
        pat_detalles = re.compile(
            r"(?:Detalle|Detalles?)\s+de\s+facturaci[oó]n(.*?)"
            r"(?:(?:Detalle\s+(?:de\s+)?)?Retenciones(?:\s+y\s+Percepciones)?\s+Impositivas?|"
            r"Neto\s+(?:Liquidado|a\s+Liquidar|a\s+Pagar))",
            flags
        )
        m = pat_detalles.search(texto_completo)
        if m:
            bloque = m.group(1)
            for linea in bloque.splitlines():
                ln = linea.strip()
                if "$" in ln:
                    partes = ln.split("$")
                    concepto = partes[0].strip(" -")
                    monto = partes[-1].strip()
                    if concepto and monto:
                        res["detalles_facturacion"][concepto] = monto

        # ---------- 2) Bloque "Retenciones / Percepciones Impositivas" ----------
        pat_ret = re.compile(
            r"(?:Detalle\s+(?:de\s+)?)?Retenciones(?:\s+y\s+Percepciones)?\s+Impositivas?(.*?)"
            r"(?:(?:Importe\s*\$\s*[\d\.,]+)|Neto\s+(?:Liquidado|a\s+Liquidar|a\s+Pagar))",
            flags
        )
        m = pat_ret.search(texto_completo)
        if m:
            bloque = m.group(1)
            for linea in bloque.splitlines():
                ln = linea.strip()
                if "$" in ln and "Retenciones Impositivas" not in ln:
                    partes = ln.split("$")
                    concepto = partes[0].strip(" -")
                    monto = partes[-1].strip()
                    if concepto and monto:
                        res["retenciones_impositivas"][concepto] = monto

        # ---------- 3) Neto Liquidado (con fallbacks robustos) ----------
        # Caso habitual: el monto aparece después de "Neto ..."
        m_neto = re.search(r"Neto\s+(?:Liquidado|a\s+Liquidar|a\s+Pagar).*?\$\s*([\d\.\,]+)", texto_completo, flags)
        if not m_neto:
            # Fallback 1: el renglón de pago (Echeq...) trae el mismo monto
            m_neto = re.search(r"Echeq\s*a\s*la\s*Orden.*?\$\s*([\d\.\,]+)", texto_completo, flags)
        if not m_neto:
            # Fallback 2: tomar el último "Importe $ X" antes del bloque Neto
            m_bloque = re.search(r"(Importe\s*\$\s*[\d\.\,]+\s*)+?\s*Neto\s+(?:Liquidado|a\s+Liquidar|a\s+Pagar)", texto_completo, flags)
            if m_bloque:
                import re as _re
                candidatos = _re.findall(r"Importe\s*\$\s*([\d\.\,]+)", m_bloque.group(0))
                if candidatos:
                    res["neto_liquidado"] = candidatos[-1]
        else:
            res["neto_liquidado"] = m_neto.group(1)

        return res

    def detectar_configuraciones_plan(self):
        """Identifica combinaciones únicas de planes y porcentajes aplicados."""
        if self.dataframe_operaciones is None or self.dataframe_operaciones.empty:
            return {}

        dataframe_agrupado = self.dataframe_operaciones.groupby([
            "plan", "arancel_pct", "interes_pct", "bonificacion_pct"
        ]).size().reset_index()

        diccionario_configuraciones = {}
        
        for _, fila_actual in dataframe_agrupado.iterrows():
            plan_actual = str(fila_actual["plan"])
            clave_unica = (
                f"{plan_actual} ("
                f"{fila_actual['arancel_pct']:.2f}/"
                f"{fila_actual['interes_pct']:.2f}/"
                f"{fila_actual['bonificacion_pct']:.2f})"
            )
            
            diccionario_configuraciones[clave_unica] = {
                "arancel": float(fila_actual["arancel_pct"]),
                "interes": float(fila_actual["interes_pct"]),
                "bonificacion": float(fila_actual["bonificacion_pct"])
            }

        self.diccionario_porcentajes_originales = diccionario_configuraciones
        return diccionario_configuraciones

    def recalcular_con_porcentajes_ajustados(self, diccionario_porcentajes_nuevos):
        """Recalcula los valores usando nuevos porcentajes configurados."""
        if self.dataframe_operaciones is None:
            raise ValueError("No hay operaciones cargadas para recalcular")

        self.diccionario_porcentajes_ajustados = diccionario_porcentajes_nuevos
        dataframe_copia = self.dataframe_operaciones.copy()

        # Crear columna identificadora de variante
        dataframe_copia["variante_plan"] = dataframe_copia.apply(
            lambda fila: (
                f"{fila['plan']} ("
                f"{fila['arancel_pct']:.2f}/"
                f"{fila['interes_pct']:.2f}/"
                f"{fila['bonificacion_pct']:.2f})"
            ),
            axis=1
        )

        lista_abonados_pdf = []
        lista_diferencias = []
        lista_estados = []

        for _, fila_actual in dataframe_copia.iterrows():
            variante_actual = fila_actual["variante_plan"]
            porcentajes = diccionario_porcentajes_nuevos.get(variante_actual, {
                "arancel": 0,
                "interes": 0,
                "bonificacion": 0
            })

            importe_operacion = CalculosAuxiliares.convertir_a_numero(fila_actual["importe"])

            # Cálculo de valores según porcentajes
            arancel_calculado = round(importe_operacion * porcentajes["arancel"] / 100, 2)
            interes_calculado = round(importe_operacion * porcentajes["interes"] / 100, 2)
            bonificacion_calculada = round(importe_operacion * porcentajes["bonificacion"] / 100, 2)

            # Valor abonado según PDF
            abonado_pdf = round(
                importe_operacion
                - abs(CalculosAuxiliares.convertir_a_numero(fila_actual.get("arancel_valor", 0)))
                - abs(CalculosAuxiliares.convertir_a_numero(fila_actual.get("interes_valor", 0)))
                + abs(CalculosAuxiliares.convertir_a_numero(fila_actual.get("bonificacion_valor", 0))),
                2
            )

            # Cálculo teórico según tipo de operación
            if str(fila_actual.get("tipo_operacion", "")).upper().startswith("DEV"):
                abonado_teorico = round(
                    importe_operacion
                    - (importe_operacion * porcentajes["arancel"] / 100)  # ← Arancel se resta (te lo devuelven)
                    - (importe_operacion * porcentajes["interes"] / 100)   # ← Interés se resta (te lo devuelven)  
                    + (importe_operacion * porcentajes["bonificacion"] / 100),  # ← Bonificación se suma (te la retienen)
                    2
                )
            else:  # Operación de venta normal (VTA)
                abonado_teorico = round(
                    importe_operacion
                    - (importe_operacion * porcentajes["arancel"] / 100)
                    - (importe_operacion * porcentajes["interes"] / 100)
                    + (importe_operacion * porcentajes["bonificacion"] / 100),
                    2
                )

            diferencia = round(abonado_pdf - abonado_teorico, 2)
            diferencia_absoluta = abs(diferencia)
            estado = "Correcta" if diferencia_absoluta <= 0.01 else "Incorrecta"

            lista_abonados_pdf.append(abonado_pdf)
            lista_diferencias.append(diferencia_absoluta)
            lista_estados.append(estado)

        # Añadir columnas calculadas
        dataframe_copia["importe_abonado"] = lista_abonados_pdf
        dataframe_copia["diferencia"] = lista_diferencias
        dataframe_copia["estado"] = lista_estados

        self.dataframe_resultados = dataframe_copia
        print(f"DEBUG: Recalculo completado. Filas: {len(self.dataframe_resultados)}")
        return dataframe_copia

    def generar_reporte_por_plan(self):
        """Genera un diccionario con resúmenes por cada variante de plan."""
        if self.dataframe_resultados is None:
            raise ValueError("Primero debe ejecutarse el recálculo")

        reporte = {}
        variantes_unicas = sorted(self.dataframe_resultados["variante_plan"].unique())

        for variante_actual in variantes_unicas:
            dataframe_filtrado = self.dataframe_resultados[
                self.dataframe_resultados["variante_plan"] == variante_actual
            ]
            dataframe_errores = dataframe_filtrado[dataframe_filtrado["estado"] == "Incorrecta"]

            if dataframe_errores.empty:
                continue

            total_operaciones = len(dataframe_filtrado)
            operaciones_erroneas = len(dataframe_errores)
            diferencia_total = dataframe_errores["diferencia"].sum()

            porcentajes_originales = self.diccionario_porcentajes_originales.get(variante_actual, {})
            porcentajes_ajustados = self.diccionario_porcentajes_ajustados.get(variante_actual, {})

            reporte[variante_actual] = {
                "total_operaciones": total_operaciones,
                "operaciones_erroneas": operaciones_erroneas,
                "diferencia_total": diferencia_total,
                "porcentajes_originales": porcentajes_originales,
                "porcentajes_ajustados": porcentajes_ajustados,
                "detalle_errores": dataframe_errores
            }

            
        return reporte
        
    def exportacion_de_informes(self, formatos_seleccionados, ruta_base=None):
        """
        Exporta los resultados a los formatos seleccionados por el usuario.
        """
        if self.dataframe_resultados is None:
            raise ValueError("No hay resultados para exportar")
        
        # Esta función NO debe manejar diálogos de archivo
        # Solo debe recibir las rutas ya definidas
        rutas_exportadas = {}
        
        for formato in formatos_seleccionados:
            if formato not in ['csv', 'excel', 'pdf']:
                continue
                
            # Determinar la ruta de destino basada en ruta_base
            if not ruta_base:
                continue  # Si no hay ruta_base, no podemos exportar
                
            if formato == 'csv':
                ruta_destino = f"{ruta_base}.csv"
            elif formato == 'excel':
                ruta_destino = f"{ruta_base}.xlsx"
            elif formato == 'pdf':
                ruta_destino = f"{ruta_base}.pdf"
            
            try:
                if formato == 'pdf':
                    ruta_grafico_temp = ruta_destino.replace('.pdf', '_grafico_temp.png')
                    self.guardar_grafico_planes_temp(ruta_grafico_temp)
                    self._exportar_pdf_interno(ruta_destino, ruta_grafico_temp)
                    
                    try:
                        if os.path.exists(ruta_grafico_temp):
                            os.remove(ruta_grafico_temp)
                    except:
                        pass
                elif formato == 'csv':
                    self._exportar_csv_interno(ruta_destino)
                elif formato == 'excel':
                    self._exportar_excel_interno(ruta_destino)
                
                rutas_exportadas[formato] = ruta_destino
                
            except Exception as e:
                print(f"Error exportando {formato.upper()}: {str(e)}")
    
        return rutas_exportadas

    def _exportar_csv_interno(self, ruta_destino):
        """Exporta los resultados a formato CSV (función interna)"""
        print(f"DEBUG: Exportando CSV a {ruta_destino}")
        
        if self.dataframe_resultados is None:
            raise ValueError("No hay resultados para exportar")
        
        # Crear copia para no modificar el original
        df_export = self.dataframe_resultados.copy()
        print(f"DEBUG: DataFrame a exportar - Filas: {len(df_export)}, Columnas: {len(df_export.columns)}")
        
        # Asegurar nombre de columna correcto
        if 'terminal_lote' in df_export.columns:
            df_export.rename(columns={'terminal_lote': 'terminal-lote'}, inplace=True)
        
        # Columnas a exportar
        columnas_exportacion = [
            'fecha', 'terminal-lote', 'presentacion', 'cupon', 'plan', 'importe',
            'arancel_pct', 'arancel_valor', 'interes_pct', 'interes_valor',
            'bonificacion_pct', 'bonificacion_valor', 'tipo_operacion',
            'importe_abonado', 'diferencia', 'estado'
        ]
        
        # Filtrar columnas existentes
        columnas_existentes = [c for c in columnas_exportacion if c in df_export.columns]
        print(f"DEBUG: Columnas a exportar: {columnas_existentes}")
        
        try:
            # Exportar
            df_export.to_csv(ruta_destino, sep=';', index=False, 
                            columns=columnas_existentes, encoding='utf-8')
            print(f"DEBUG: CSV exportado exitosamente a {ruta_destino}")
            
        except Exception as e:
            print(f"ERROR exportando CSV: {str(e)}")
            raise

    def _exportar_excel_interno(self, ruta_destino):
        """Exporta los resultados a formato Excel (función interna)"""
        if self.dataframe_resultados is None:
            raise ValueError("No hay resultados para exportar")
        
        df_export = self.dataframe_resultados.copy()
        
        if 'terminal_lote' in df_export.columns:
            df_export.rename(columns={'terminal_lote': 'terminal-lote'}, inplace=True)
        
        df_export.to_excel(ruta_destino, index=False, engine='openpyxl')

    def _exportar_pdf_interno(self, ruta_destino, ruta_imagen_grafico=None):
        """Exporta los resultados a formato PDF con formato específico"""
        if self.dataframe_resultados is None:
            raise ValueError("No hay resultados para exportar")
    
        # Configuración del documento
        doc = SimpleDocTemplate(ruta_destino, pagesize=landscape(A4),
                            leftMargin=1*cm, rightMargin=1*cm,
                            topMargin=1*cm, bottomMargin=1*cm)
        
        styles = getSampleStyleSheet()
        elements = []
        
        # Encabezado
        elements.append(Paragraph("ANÁLISIS DE LIQUIDACIÓN - TARJETA NARANJA", styles['Heading1']))
        elements.append(Spacer(1, 12))
        
        # Metadatos incluyendo Tipo y Nº
        fecha_emision = self.diccionario_metadatos.get('fecha_emision', '--')
        fecha_pago = self.diccionario_metadatos.get('fecha_pago', '--')
        forma_pago = self.diccionario_metadatos.get('forma_pago', '--')
        tipo_numero = self.diccionario_metadatos.get('tipo_numero', '--')
        
        elements.append(Paragraph(
            f"<b>Tipo y Nº:</b> {tipo_numero} | "
            f"<b>Fecha Emisión:</b> {fecha_emision} | "
            f"<b>Fecha Pago:</b> {fecha_pago} | "
            f"<b>Forma Pago:</b> {forma_pago}", 
            styles['Normal']
        ))
        elements.append(Spacer(1, 16))
        
        # Resumen impositivo si existe
        if hasattr(self, 'resumen_impositivo') and self.resumen_impositivo:
            elements.append(Paragraph("RESUMEN IMPOSITIVO", styles['Heading2']))
            
            if self.resumen_impositivo.get('detalles_facturacion'):
                for concepto, monto in self.resumen_impositivo['detalles_facturacion'].items():
                    elements.append(Paragraph(f"• {concepto}: ${monto}", styles['Normal']))
            
            if self.resumen_impositivo.get('retenciones_impositivas'):
                for concepto, monto in self.resumen_impositivo['retenciones_impositivas'].items():
                    elements.append(Paragraph(f"• {concepto}: ${monto}", styles['Normal']))
            
            if self.resumen_impositivo.get('neto_liquidado'):
                elements.append(Paragraph(
                    f"<b>NETO LIQUIDADO:</b> ${self.resumen_impositivo['neto_liquidado']}", 
                    styles['Normal']
                ))
            
            elements.append(Spacer(1, 16))
        
        # Gráfico de planes si está disponible
        if ruta_imagen_grafico and os.path.exists(ruta_imagen_grafico):
            try:
                elements.append(Paragraph("DISTRIBUCIÓN DE PLANES", styles['Heading2']))
                img = RLImage(ruta_imagen_grafico, width=14*cm, height=8*cm)
                elements.append(img)
                elements.append(Spacer(1, 16))
            except:
                pass  # Si falla la imagen, continuar sin ella
        
        # Tabla de operaciones con errores - FORMATO COMPLETO
        errores = self.dataframe_resultados[self.dataframe_resultados['estado'] == 'Incorrecta']
        
        if not errores.empty:
            elements.append(Paragraph("OPERACIONES CON ERRORES DE CÁLCULO", styles['Heading2']))
            elements.append(Spacer(1, 10))
            
            # Preparar datos para la tabla con TODAS las columnas
            columnas = [
                'Fecha de Compra', 'Terminal-Lote', 'Presentación', 'Cupones', 'Plan', 
                'Importe', '% Arancel', 'Arancel', '% Interés', 'Interés', 
                '% Bonificación', 'Bonificación', 'Operac.', 'Importe Abonado', 'Diferencia Adeudada'
            ]
            
            datos = [columnas]  # Encabezados
            
            for _, fila in errores.iterrows():
                # Obtener valores, usando "No figura" cuando no hay datos
                fecha = str(fila['fecha']) if pd.notna(fila['fecha']) else 'No figura'
                terminal_lote = str(fila.get('terminal-lote', fila.get('terminal_lote', 'No figura')))
                presentacion = str(fila['presentacion']) if pd.notna(fila['presentacion']) and str(fila['presentacion']).strip() else 'No figura'
                cupon = str(fila['cupon']) if pd.notna(fila['cupon']) and str(fila['cupon']).strip() else 'No figura'
                plan = str(fila['plan']) if pd.notna(fila['plan']) else 'No figura'
                
                # Valores numéricos formateados
                importe_valor = CalculosAuxiliares.formatear_moneda_pesos(fila['importe']) if pd.notna(fila['importe']) else 'No figura'
                arancel_pct = f"{fila['arancel_pct']:.2f}%" if pd.notna(fila['arancel_pct']) and fila['arancel_pct'] != 0 else 'No figura'
                arancel_valor = CalculosAuxiliares.formatear_moneda_pesos(fila['arancel_valor']) if pd.notna(fila['arancel_valor']) and fila['arancel_valor'] != 0 else 'No figura'
                interes_pct = f"{fila['interes_pct']:.2f}%" if pd.notna(fila['interes_pct']) and fila['interes_pct'] != 0 else 'No figura'
                interes_valor = CalculosAuxiliares.formatear_moneda_pesos(fila['interes_valor']) if pd.notna(fila['interes_valor']) and fila['interes_valor'] != 0 else 'No figura'
                bonificacion_pct = f"{fila['bonificacion_pct']:.2f}%" if pd.notna(fila['bonificacion_pct']) and fila['bonificacion_pct'] != 0 else 'No figura'
                bonificacion_valor = CalculosAuxiliares.formatear_moneda_pesos(fila['bonificacion_valor']) if pd.notna(fila['bonificacion_valor']) and fila['bonificacion_valor'] != 0 else 'No figura'
                
                tipo_operacion = str(fila['tipo_operacion']) if pd.notna(fila['tipo_operacion']) else 'No figura'
                importe_abonado = CalculosAuxiliares.formatear_moneda_pesos(fila['importe_abonado']) if pd.notna(fila['importe_abonado']) else 'No figura'
                diferencia = CalculosAuxiliares.formatear_moneda_pesos(fila['diferencia']) if pd.notna(fila['diferencia']) else 'No figura'
                
                datos.append([
                    fecha,
                    terminal_lote,
                    presentacion,
                    cupon,
                    plan,
                    f"${importe_valor}",
                    arancel_pct,
                    f"${arancel_valor}" if arancel_valor != 'No figura' else 'No figura',
                    interes_pct,
                    f"${interes_valor}" if interes_valor != 'No figura' else 'No figura',
                    bonificacion_pct,
                    f"${bonificacion_valor}" if bonificacion_valor != 'No figura' else 'No figura',
                    tipo_operacion,
                    f"${importe_abonado}",
                    f"${diferencia}"
                ])
            
            # Crear tabla con anchos de columna específicos
            ancho_columnas = [
                2.0*cm,  # Fecha
                2.5*cm,  # Terminal-Lote
                2.0*cm,  # Presentación
                1.5*cm,  # Cupones
                1.2*cm,  # Plan
                2.0*cm,  # Importe
                1.5*cm,  # % Arancel
                1.5*cm,  # Arancel
                1.5*cm,  # % Interés
                1.5*cm,  # Interés
                1.5*cm,  # % Bonificación
                1.5*cm,  # Bonificación
                1.2*cm,  # Operac.
                2.0*cm,  # Importe Abonado
                2.0*cm,  # Diferencia Adeudada
            ]
            
            tabla = Table(datos, colWidths=ancho_columnas, repeatRows=1)
            
            # Estilo de la tabla
            estilo_tabla = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FFA500')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('WORDWRAP', (0, 0), (-1, -1), True),  # Permitir wrap de texto
            ])
            
            tabla.setStyle(estilo_tabla)
            
            elements.append(tabla)
            
            # Resumen total de diferencias
            total_diferencia = errores['diferencia'].sum()
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(
                f"<b>TOTAL DIFERENCIA ADEUDADA: ${CalculosAuxiliares.formatear_moneda_pesos(total_diferencia)}</b>", 
                styles['Heading2']
            ))
        else:
            elements.append(Paragraph("✓ No se encontraron operaciones con errores", styles['Normal']))
        
        # Pie de página
        def add_footer(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.drawString(1*cm, 1*cm, f"Página {doc.page}")
            canvas.restoreState()
        
        # Generar PDF
        doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)

    def guardar_grafico_planes_temp(self, ruta_destino):
        """Guarda un gráfico temporal de distribución de planes para usar en PDF"""
        try:
            df = self.dataframe_operaciones
            if df is None or df.empty:
                return
            
            ventas = df[df["tipo_operacion"].astype(str).str.upper() == "VTA"]
            if ventas.empty:
                return
            
            conteo = ventas["plan"].value_counts()
            
            plt.figure(figsize=(8, 6))
            plt.pie(conteo.values.tolist(), labels=conteo.index.tolist(), autopct='%1.1f%%')
            plt.title('Distribución de Planes (Ventas)')
            plt.savefig(ruta_destino, bbox_inches='tight', dpi=100)
            plt.close()
            
        except Exception as e:
            print(f"Error al guardar gráfico temporal: {e}")
# ========================================================
# CLASE 4: Interfaz gráfica (PyQt)
# ========================================================
class InterfazGrafica(QMainWindow): 
    def __init__(self):
        super().__init__()
        self.procesador = ProcesadorLogico()
        
        # Nuevas variables para manejar múltiples archivos
        self.archivos_cargados = {}  # {ruta_archivo: {metadatos, dataframe, etc.}}
        self.archivos_duplicados = {}  # Para manejar archivos con el mismo Tipo y Nº
        self.hilos_activos = []  # <-- NUEVA LISTA para mantener referencia a hilos
        
        # Inicializar variables importantes
        self.dataframe_operaciones = None
        self.dataframe_resultados = None
        self.metadatos = {}
        
        self.configurar_interfaz()
        self.establecer_estilos()
        self.conectar_eventos()

        # --- Inicializaciones importantes ---
        self.df_resultados = None
        self.dataframe_operaciones = self.procesador.dataframe_operaciones
        self.metadatos = self.procesador.diccionario_metadatos

    def manejar_carga_pdf(self):
        dialogo = DialogoCargaArchivos(self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            rutas = dialogo.obtener_rutas()
            if not rutas:
                return
                
            self.etiqueta_estado.setText(f"Procesando {len(rutas)} archivos...")
            self.barra_progreso.setRange(0, len(rutas))
            
            for i, ruta in enumerate(rutas):
                # Verificar si el archivo ya está cargado
                if ruta in self.archivos_cargados:
                    print(f"DEBUG: Archivo ya cargado: {ruta}")
                    continue
                    
                print(f"DEBUG: Procesando archivo {i+1}/{len(rutas)}: {ruta}")
                
                worker = WorkerThread(self.procesar_archivo_en_hilo, ruta)
                self.hilos_activos.append(worker)

                worker.progreso.connect(self.etiqueta_estado.setText)
                worker.terminado.connect(self._finalizar_carga_archivo)
                worker.error.connect(lambda msg, r=ruta: self._manejar_error_carga(r, msg))
                worker.finished.connect(lambda: self._limpiar_hilo(worker))
                
                # Configurar barra de progreso
                worker.progreso.connect(lambda msg, i=i: self.barra_progreso.setValue(i+1))
                
                worker.start()

    def construir_resumen_inicial(self, tipo_numero: str) -> str:
        """Devuelve un resumen en texto para el 'Tipo y Nº' indicado."""
        resumen = [f"📄 Resumen: {tipo_numero}\n"]

        if tipo_numero in self.procesador.metadatos_por_resumen:
            resumen.append("Metadatos:")
            for k, v in self.procesador.metadatos_por_resumen[tipo_numero].items():
                resumen.append(f"   - {k}: {v}")

        if tipo_numero in self.procesador.operaciones_por_resumen:
            resumen.append("\nOperaciones:")
            resumen.append(str(self.procesador.operaciones_por_resumen[tipo_numero].head(10)))

        if tipo_numero in self.procesador.resultados_por_resumen:
            resumen.append("\nResultados:")
            resumen.append(str(self.procesador.resultados_por_resumen[tipo_numero].head(10)))

        if tipo_numero in self.procesador.porcentajes_originales_por_resumen:
            resumen.append("\nPorcentajes originales:")
            resumen.append(str(self.procesador.porcentajes_originales_por_resumen[tipo_numero]))

        if tipo_numero in self.procesador.porcentajes_ajustados_por_resumen:
            resumen.append("\nPorcentajes ajustados:")
            resumen.append(str(self.procesador.porcentajes_ajustados_por_resumen[tipo_numero]))

        if tipo_numero in self.procesador.resumen_impositivo_por_resumen:
            resumen.append("\nResumen impositivo:")
            resumen.append(str(self.procesador.resumen_impositivo_por_resumen[tipo_numero]))

        return "\n".join(resumen)

    def configurar_interfaz(self):
        """Configura los elementos visuales principales de la interfaz."""
        self.setWindowTitle("Analizador de Resúmenes Naranja")
        self.setMinimumSize(1500, 900)

        # Widget central con nombre para CSS
        widget_central = QWidget()
        widget_central.setObjectName("widgetCentral")
        self.layout_principal = QVBoxLayout(widget_central)
        self.setCentralWidget(widget_central)

        # Barra de título
        self.etiqueta_titulo = QLabel("Analizador de Resúmenes Naranja")
        self.etiqueta_titulo.setObjectName("tituloPrincipal")
        self.etiqueta_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_principal.addWidget(self.etiqueta_titulo)

        # Barra de botones - MODIFICADO para múltiples archivos
        self.boton_cargar = QPushButton("1. Cargar Resúmenes PDF")
        self.boton_recalcular = QPushButton("2. Recalcular Operaciones")
        self.boton_exportar = QPushButton("3. Exportar Resultados")
        
        self.boton_recalcular.setEnabled(False)
        self.boton_exportar.setEnabled(False)

        # Nuevo botón para limpiar archivos
        self.boton_limpiar = QPushButton("Limpiar Archivos")
        
        layout_botones = QHBoxLayout()
        layout_botones.addWidget(self.boton_cargar)
        layout_botones.addWidget(self.boton_recalcular)
        layout_botones.addWidget(self.boton_exportar)
        layout_botones.addWidget(self.boton_limpiar)
        self.layout_principal.addLayout(layout_botones)

        # Nuevo: Lista de archivos cargados - CON MEJORAS DE VISUALIZACIÓN
        self.grupo_archivos = QGroupBox("Archivos Cargados")
        self.layout_archivos = QVBoxLayout()
        self.lista_archivos = QTableWidget()
        self.lista_archivos.setColumnCount(4)
        self.lista_archivos.setHorizontalHeaderLabels(["Archivo", "Tipo y Nº", "Estado", "Acciones"])

        # CONFIGURACIONES ADICIONALES PARA MEJOR VISUALIZACIÓN
        self.lista_archivos.setMinimumHeight(200)  # Más alto
        self.lista_archivos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lista_archivos.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.lista_archivos.setAlternatingRowColors(True)  # Filas alternadas
        self.lista_archivos.setSortingEnabled(False)  # Desactivar ordenamiento temporalmente

        # CORRECCIÓN: Verificar que horizontalHeader() no sea None
        header = self.lista_archivos.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Archivo - se expande
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Tipo y Nº - ajusta al contenido
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Estado - ajusta al contenido
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Acciones - ajusta al contenido
        
        self.layout_archivos.addWidget(self.lista_archivos)
        self.grupo_archivos.setLayout(self.layout_archivos)
        self.layout_principal.addWidget(self.grupo_archivos)

        # Área de estado
        self.etiqueta_estado = QLabel("Esperando carga de archivos...")
        self.barra_progreso = QProgressBar()
        self.barra_progreso.setRange(0, 100)
        self.barra_progreso.setValue(0)

        layout_estado = QHBoxLayout()
        layout_estado.addWidget(self.etiqueta_estado)
        layout_estado.addWidget(self.barra_progreso)
        self.layout_principal.addLayout(layout_estado)

        # -----------------------
        # CUERPO PRINCIPAL
        # -----------------------
        self.layout_cuerpo = QHBoxLayout()
        self.layout_principal.addLayout(self.layout_cuerpo)

        # --- Columna izquierda: scroll con contenidos dinámicos ---
        self.contenedor_scroll = QScrollArea()
        self.contenedor_scroll.setObjectName("areaScroll")
        self.contenedor_scroll.setWidgetResizable(True)

        self.widget_contenido = QWidget()
        self.widget_contenido.setObjectName("contenidoPrincipal")
        self.layout_contenido = QVBoxLayout(self.widget_contenido)
        self.contenedor_scroll.setWidget(self.widget_contenido)

        self.layout_cuerpo.addWidget(self.contenedor_scroll, stretch=3)

        # --- Columna derecha: sidebar con gráfico de planes ---
        self.sidebar_grafico = QGroupBox("Distribución de Planes (Ventas)")
        self.layout_sidebar = QVBoxLayout(self.sidebar_grafico)

        # Figura Matplotlib fija en la UI
        self.fig_planes = Figure(figsize=(4, 4), tight_layout=True)
        self.ax_planes = self.fig_planes.add_subplot(111)
        self.canvas_planes = FigureCanvas(self.fig_planes)
        self.layout_sidebar.addWidget(self.canvas_planes)

        # Leyenda / placeholder inicial
        self.label_leyenda_planes = QLabel("Cargá PDFs para ver el gráfico.")
        self.label_leyenda_planes.setWordWrap(True)
        self.layout_sidebar.addWidget(self.label_leyenda_planes)
        self.layout_sidebar.addStretch()

        self.layout_cuerpo.addWidget(self.sidebar_grafico, stretch=1)
        
        # CORRECCIÓN IMPORTANTE: Conectar las señales DESPUÉS de crear todos los widgets
        self.conectar_eventos()

    def conectar_eventos(self):
        """Establece las conexiones de señales y slots."""
        self.boton_cargar.clicked.connect(self.manejar_carga_pdf)
        self.boton_recalcular.clicked.connect(self.manejar_recalculo)
        self.boton_exportar.clicked.connect(self.manejar_exportacion)
        self.boton_limpiar.clicked.connect(self.limpiar_archivos)
        self.lista_archivos.currentCellChanged.connect(self.on_seleccion_archivo_cambiada)

    def on_seleccion_archivo_cambiada(self, current_row, current_column, previous_row, previous_column):
        """Se ejecuta cuando cambia la selección en la lista de archivos."""
        try:
            if current_row >= 0 and current_row < self.lista_archivos.rowCount():
                self.mostrar_resumen_inicial()
        except Exception as e:
            print(f"Error en selección de archivo: {e}")
    
    def establecer_estilos(self):
        """Configura los estilos visuales de toda la aplicación."""
        estilo = """
        /* Fondo base para toda la aplicación */
        QWidget {
            background-color: #F5F5F5;
            color: #333333;
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        
        /* Ventana principal */
        QMainWindow {
            background-color: #F5F5F5;
        }
        
        /* Widget central */
        QWidget#widgetCentral {
            background-color: #F5F5F5;
        }
        
        /* Área de scroll y su contenido */
        QScrollArea#areaScroll {
            background-color: #F5F5F5;
            border: none;
        }
        
        QScrollArea#areaScroll > QWidget > QWidget {
            background-color: #F5F5F5;
        }
        
        QWidget#contenidoPrincipal {
            background-color: #FAFAFA;
            padding: 15px;
        }
        
        /* Título principal */
        QLabel#tituloPrincipal {
            font-size: 24px;
            font-weight: bold;
            color: #FF5F15;
            padding: 15px;
            background: transparent;
        }
        
        /* Botones */
        QPushButton {
            background-color: #FFA500;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            min-width: 120px;
            font-size: 14px;
        }
        
        QPushButton:hover {
            background-color: #FF8C00;
        }
        
        QPushButton:disabled {
            background-color: #CCCCCC;
            color: #666666;
        }
        
        /* Barra de progreso */
        QProgressBar {
            border: 1px solid #E0E0E0;
            border-radius: 4px;
            text-align: center;
            height: 20px;
            background: white;
        }
        
        QProgressBar::chunk {
            background-color: #00CC99;
            border-radius: 3px;
        }
        
        /* Etiquetas */
        QLabel {
            color: #333333;
        }
        
        /* Grupos (para secciones de resultados) */
        QGroupBox {
            background: white;
            border: 1px solid #E0E0E0;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 20px;
        }
        
        QGroupBox::title {
            color: #FF5F15;
            subcontrol-origin: margin;
            left: 10px;
            font-weight: bold;
        }
        
        /* Tablas */
        QTableWidget {
            background: white;
            alternate-background-color: #F9F9F9;
            gridline-color: #E0E0E0;
            border: none;
        }
        
        QHeaderView::section {
            background-color: #FFA500;
            color: white;
            padding: 4px;
            border: none;
        }
        """
        
        self.setStyleSheet(estilo)
    
    def procesar_archivo_en_hilo(self, ruta_archivo):
        """Procesa un archivo PDF en un hilo separado."""
        def tarea_pesada():
            try:
                print(f"DEBUG: Iniciando procesamiento de {ruta_archivo}")
                
                procesador_temp = ProcesadorLogico()

                # Extracción de operaciones
                df_operaciones = procesador_temp.extraer_operaciones_del_pdf(ruta_archivo)
                print(f"DEBUG: Extraídas {len(df_operaciones)} operaciones de {ruta_archivo}")

                # Extracción de metadatos
                metadatos = procesador_temp.extraer_metadatos_del_pdf(ruta_archivo)
                print(f"DEBUG: Metadatos extraídos de {ruta_archivo}")

                # Detección de configuraciones
                configuraciones = procesador_temp.detectar_configuraciones_plan()
                print(f"DEBUG: Configuraciones detectadas en {ruta_archivo}")

                return {
                    "ruta": ruta_archivo,
                    "df_operaciones": df_operaciones,
                    "metadatos": metadatos,
                    "configuraciones": configuraciones,
                    "procesador": procesador_temp,
                    "resumen_impositivo": procesador_temp.resumen_impositivo
                }
            except Exception as e:
                print(f"ERROR en tarea_pesada para {ruta_archivo}: {e}")
                raise e

        return tarea_pesada()
    
    def _limpiar_hilo(self, worker):
        """Elimina un hilo de la lista de hilos activos cuando termina."""
        if worker in self.hilos_activos:
            self.hilos_activos.remove(worker)

    def _finalizar_carga_archivo(self, resultado):
        """Se ejecuta cuando la carga de un archivo PDF terminó en el hilo."""
        if resultado is None:
            self.barra_progreso.setValue(0)
            return
            
        try:
            ruta_archivo = resultado["ruta"]
            tipo_numero = resultado["metadatos"].get("tipo_numero") or os.path.basename(ruta_archivo)

            print(f"DEBUG: Finalizando carga de {ruta_archivo}")

            # Verificar duplicados por Tipo y Nº
            duplicado = False
            archivo_duplicado = None
            for archivo, datos in self.archivos_cargados.items():
                if datos["metadatos"].get("tipo_numero") == tipo_numero and archivo != ruta_archivo:
                    duplicado = True
                    archivo_duplicado = archivo
                    break

            if duplicado:
                print(f"DEBUG: Archivo duplicado detectado: {tipo_numero}")
                # Guardar temporalmente en archivos duplicados
                self.archivos_duplicados[ruta_archivo] = {
                    "df_operaciones": resultado["df_operaciones"],
                    "metadatos": resultado["metadatos"],
                    "configuraciones": resultado["configuraciones"],
                    "procesador": resultado["procesador"],
                    "resumen_impositivo": resultado["procesador"].resumen_impositivo
                }
                # Mostrar diálogo de duplicado
                self.mostrar_dialogo_duplicado(ruta_archivo, tipo_numero, archivo_duplicado)
            else:
                print(f"DEBUG: Agregando archivo a cargados: {ruta_archivo}")
                # Agregar a archivos cargados
                self.archivos_cargados[ruta_archivo] = {
                    "df_operaciones": resultado["df_operaciones"],
                    "metadatos": resultado["metadatos"],
                    "configuraciones": resultado["configuraciones"],
                    "procesador": resultado["procesador"],
                    "resumen_impositivo": resultado["procesador"].resumen_impositivo
                }

                # Guardar datos para resumen
                self.procesador.operaciones_por_resumen[tipo_numero] = resultado["df_operaciones"]
                self.procesador.metadatos_por_resumen[tipo_numero] = resultado["metadatos"]
                self.procesador.porcentajes_originales_por_resumen[tipo_numero] = resultado["configuraciones"]
                self.procesador.resumen_impositivo_por_resumen[tipo_numero] = resultado["procesador"].resumen_impositivo

                # Actualizar interfaz
                print(f"DEBUG: Archivos cargados ahora: {len(self.archivos_cargados)}")
                self.actualizar_lista_archivos()
                self.combinar_datos_archivos()
                self.etiqueta_estado.setText(f"✅ Archivo {os.path.basename(ruta_archivo)} procesado correctamente")
                self.boton_recalcular.setEnabled(len(self.archivos_cargados) > 0)
                
                # FORZAR ACTUALIZACIÓN VISUAL - AÑADIDO
                QApplication.processEvents()  # Procesar eventos pendientes
                viewport = self.lista_archivos.viewport()
                if viewport is not None:
                    viewport.update()  # Actualizar vista
                self.lista_archivos.repaint()  # Repintar tabla

        except Exception as error:
            print(f"ERROR en _finalizar_carga_archivo: {error}")
            self.barra_progreso.setValue(0)
            self.etiqueta_estado.setText(f"Error al procesar el archivo {os.path.basename(ruta_archivo)}")
            QMessageBox.critical(self, "Error", f"No se pudo procesar el archivo:\n{str(error)}")
    
    def _manejar_error_carga(self, ruta_archivo, mensaje_error):
        """Maneja errores durante la carga de archivos."""
        print(f"ERROR cargando {ruta_archivo}: {mensaje_error}")
        QMessageBox.critical(self, "Error", f"No se pudo procesar el archivo {os.path.basename(ruta_archivo)}:\n{mensaje_error}")

    def mostrar_dialogo_duplicado(self, ruta_archivo, tipo_numero, archivo_duplicado):
        """Muestra un diálogo cuando se detecta un archivo duplicado."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Archivo Duplicado")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        
        mensaje = QLabel(
            f"El archivo <b>{os.path.basename(ruta_archivo)}</b> tiene el mismo 'Tipo y Nº' "
            f"({tipo_numero}) que el archivo <b>{os.path.basename(archivo_duplicado)}</b>.<br><br>"
            "¿Qué deseas hacer?"
        )
        mensaje.setTextFormat(Qt.TextFormat.RichText)
        mensaje.setWordWrap(True)
        layout.addWidget(mensaje)
        
        botones = QDialogButtonBox()
        btn_reemplazar = QPushButton("Reemplazar archivo existente")
        btn_conservar = QPushButton("Conservar ambos (cambiar Tipo y Nº)")
        btn_descartar = QPushButton("Descartar archivo nuevo")
        
        botones.addButton(btn_reemplazar, QDialogButtonBox.ButtonRole.AcceptRole)
        botones.addButton(btn_conservar, QDialogButtonBox.ButtonRole.ActionRole)
        botones.addButton(btn_descartar, QDialogButtonBox.ButtonRole.RejectRole)
        
        layout.addWidget(botones)
        
        def on_reemplazar():
            # Eliminar el archivo existente y agregar el nuevo
            del self.archivos_cargados[archivo_duplicado]
            self.archivos_cargados[ruta_archivo] = self.archivos_duplicados.get(ruta_archivo, {})
            if ruta_archivo in self.archivos_duplicados:
                del self.archivos_duplicados[ruta_archivo]
            
            self.actualizar_lista_archivos()
            self.combinar_datos_archivos()
            dialog.accept()
        
        def on_conservar():
            # Permitir al usuario editar el Tipo y Nº
            nuevo_tipo_numero, ok = QInputDialog.getText(
                self, 
                "Cambiar Tipo y Nº", 
                "Ingresa un nuevo valor para Tipo y Nº:",
                text=tipo_numero
            )
            
            if ok and nuevo_tipo_numero:
                # Actualizar el metadato del archivo en duplicados
                if ruta_archivo in self.archivos_duplicados:
                    self.archivos_duplicados[ruta_archivo]["metadatos"]["tipo_numero"] = nuevo_tipo_numero
                    self.archivos_cargados[ruta_archivo] = self.archivos_duplicados[ruta_archivo]
                    del self.archivos_duplicados[ruta_archivo]
                    
                    self.actualizar_lista_archivos()
                    self.combinar_datos_archivos()
            
            dialog.accept()
        
        def on_descartar():
            # Simplemente descartar el archivo nuevo
            if ruta_archivo in self.archivos_duplicados:
                del self.archivos_duplicados[ruta_archivo]
            dialog.accept()
        
        btn_reemplazar.clicked.connect(on_reemplazar)
        btn_conservar.clicked.connect(on_conservar)
        btn_descartar.clicked.connect(on_descartar)
        
        dialog.exec()
    
    def limpiar_archivos(self):
        """Limpia todos los archivos cargados."""
        try:
            # Limpiar la selección de la tabla primero
            self.lista_archivos.clearSelection()
            self.lista_archivos.setCurrentCell(-1, -1)
            
            # Limpiar los datos
            self.archivos_cargados.clear()
            self.archivos_duplicados.clear()
            
            # Actualizar la interfaz
            self.actualizar_lista_archivos()
            
            # Limpiar el área de visualización de manera segura
            try:
                self.limpiar_area_visualizacion()
            except:
                self._recrear_layout_contenido()
                
            self.boton_recalcular.setEnabled(False)
            self.boton_exportar.setEnabled(False)
            self.etiqueta_estado.setText("Todos los archivos han sido eliminados.")
            
            # Limpiar el gráfico
            self._limpiar_grafico()
            
        except Exception as e:
            print(f"Error en limpiar_archivos: {e}")

    def _limpiar_grafico(self):
        """Limpia el gráfico de planes."""
        self.ax_planes.clear()
        self.ax_planes.text(0.5, 0.5, "Cargá PDFs para ver el gráfico", 
                        ha="center", va="center", fontsize=12)
        self.canvas_planes.draw()
        self.label_leyenda_planes.setText("Cargá PDFs para ver el gráfico.")

    def actualizar_lista_archivos(self):
        """Actualiza la tabla de archivos cargados."""
        try:
            # Limpiar selección primero
            self.lista_archivos.clearSelection()
            self.lista_archivos.setCurrentCell(-1, -1)
            
            # Establecer número de filas
            num_archivos = len(self.archivos_cargados)
            self.lista_archivos.setRowCount(num_archivos)
            
            print(f"DEBUG: Actualizando lista con {num_archivos} archivos")
            
            for i, (ruta, datos) in enumerate(self.archivos_cargados.items()):
                # Nombre del archivo
                nombre_archivo = os.path.basename(ruta)
                item_nombre = QTableWidgetItem(nombre_archivo)
                self.lista_archivos.setItem(i, 0, item_nombre)
                
                # Tipo y Nº
                tipo_numero = datos["metadatos"].get("tipo_numero", "Sin identificar")
                item_tipo = QTableWidgetItem(tipo_numero)
                self.lista_archivos.setItem(i, 1, item_tipo)
                
                # Estado
                operaciones = len(datos["df_operaciones"]) if datos["df_operaciones"] is not None else 0
                item_estado = QTableWidgetItem(f"{operaciones} operaciones")
                self.lista_archivos.setItem(i, 2, item_estado)
                
                # Botón para eliminar
                widget_botones = QWidget()
                layout_botones = QHBoxLayout(widget_botones)
                layout_botones.setContentsMargins(0, 0, 0, 0)
                
                btn_eliminar = QPushButton("Eliminar")
                btn_eliminar.clicked.connect(lambda checked, r=ruta: self.eliminar_archivo(r))
                
                layout_botones.addWidget(btn_eliminar)
                layout_botones.addStretch()
                
                self.lista_archivos.setCellWidget(i, 3, widget_botones)
            
            # Ajustar el tamaño de las columnas al contenido
            self.lista_archivos.resizeColumnsToContents()
            
            # Ajustar el tamaño de las filas para que se vean todos los archivos
            for i in range(num_archivos):
                self.lista_archivos.setRowHeight(i, 30)
            
            # FORZAR ACTUALIZACIÓN VISUAL
            viewport = self.lista_archivos.viewport()
            if viewport is not None:
                viewport.update()
            self.lista_archivos.repaint()
            
            print(f"DEBUG: Lista actualizada correctamente con {num_archivos} archivos")
            
            # Seleccionar la primera fila si hay archivos
            if num_archivos > 0:
                self.lista_archivos.setCurrentCell(0, 0)
            
        except Exception as e:
            print(f"ERROR en actualizar_lista_archivos: {e}")
    
    def eliminar_archivo(self, ruta_archivo):
        """Elimina un archivo de la lista de cargados."""
        if ruta_archivo in self.archivos_cargados:
            del self.archivos_cargados[ruta_archivo]
            self.actualizar_lista_archivos()
            self.combinar_datos_archivos()
            
            # Deshabilitar recálculo si no hay archivos
            self.boton_recalcular.setEnabled(len(self.archivos_cargados) > 0)
    
    def combinar_datos_archivos(self):
        """Combina los datos de todos los archivos cargados."""
        if not self.archivos_cargados:
            self.procesador.dataframe_operaciones = None
            self.procesador.diccionario_metadatos = {}
            return
        
        # Combinar dataframes de operaciones
        dataframes = []
        for datos in self.archivos_cargados.values():
            if datos["df_operaciones"] is not None and not datos["df_operaciones"].empty:
                dataframes.append(datos["df_operaciones"])
        
        if dataframes:
            self.procesador.dataframe_operaciones = pd.concat(dataframes, ignore_index=True)
            print(f"DEBUG: DataFrame combinado con {len(self.procesador.dataframe_operaciones)} operaciones")
        else:
            self.procesador.dataframe_operaciones = None
            print("DEBUG: No hay dataframes para combinar")

        # Para múltiples archivos, crear metadatos combinados
        if len(self.archivos_cargados) > 1:
            self.procesador.diccionario_metadatos = {
                "tipo_numero": "Múltiples resúmenes",
                "fecha_emision": "Varias fechas",
                "fecha_pago": "Varias fechas",
                "forma_pago": "Múltiples formas"
            }
        else:
            # Usar metadatos del único archivo
            primer_archivo = next(iter(self.archivos_cargados.values()))
            self.procesador.diccionario_metadatos = primer_archivo["metadatos"].copy()
        
        # Actualizar referencia
        self.dataframe_operaciones = self.procesador.dataframe_operaciones
        
        # Actualizar gráfico
        self._refrescar_grafico_si_hay_datos()
    
    def pedir_porcentajes(self, configuraciones_detectadas):
        dlg = QDialog(self)
        dlg.setWindowTitle("Configurar Porcentajes por Plan")
        layout_principal = QVBoxLayout(dlg)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contenedor = QWidget()
        layout_contenedor = QVBoxLayout(contenedor)

        self.campos_porcentajes = {}

        for clave, valores in configuraciones_detectadas.items():
            grupo = QGroupBox(f"Plan {clave}")
            form = QFormLayout()

            campo_arancel = QLineEdit(f"{valores['arancel']:.2f}")
            campo_interes = QLineEdit(f"{valores['interes']:.2f}")
            campo_bonif = QLineEdit(f"{valores['bonificacion']:.2f}")

            form.addRow("Arancel (%):", campo_arancel)
            form.addRow("Interés (%):", campo_interes)
            form.addRow("Bonificación (%):", campo_bonif)

            grupo.setLayout(form)
            layout_contenedor.addWidget(grupo)

            self.campos_porcentajes[clave] = {
                "arancel": campo_arancel,
                "interes": campo_interes,
                "bonificacion": campo_bonif
            }

        layout_contenedor.addStretch()
        scroll.setWidget(contenedor)
        layout_principal.addWidget(scroll)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout_principal.addWidget(botones)
        botones.accepted.connect(dlg.accept)
        botones.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        # Guardar valores
        resultado = {}
        for clave, campos in self.campos_porcentajes.items():
            try:
                a = CalculosAuxiliares.convertir_a_numero(campos["arancel"].text())
                i = CalculosAuxiliares.convertir_a_numero(campos["interes"].text())
                b = CalculosAuxiliares.convertir_a_numero(campos["bonificacion"].text())
            except Exception:
                a = i = b = 0.0
            resultado[clave] = {"arancel": a, "interes": i, "bonificacion": b}

        return resultado
    
    def construir_vista_previa(self):
        """Construye la vista previa mostrando solo operaciones con errores de liquidación."""
        # Crear copia del dataframe para no modificar el original
        if self.procesador.dataframe_operaciones is not None:
            dataframe_operaciones = self.procesador.dataframe_operaciones.copy()
        else:
            dataframe_operaciones = pd.DataFrame()

        # Agregar columna identificadora de variante de plan
        dataframe_operaciones["variante_plan"] = dataframe_operaciones.apply(
            lambda fila: (
                f"{fila['plan']} ("
                f"{fila['arancel_pct']:.2f}/"
                f"{fila['interes_pct']:.2f}/"
                f"{fila['bonificacion_pct']:.2f})"
            ),
            axis=1
        )

        # Listas para almacenar resultados
        lista_abonados = []
        lista_diferencias = []
        lista_estados = []

        # Recalcular cada operación
        for _, fila_actual in dataframe_operaciones.iterrows():
            variante_actual = fila_actual["variante_plan"]
            porcentajes = self.procesador.diccionario_porcentajes_ajustados.get(variante_actual, {
                "arancel": 0.0, "interes": 0.0, "bonificacion": 0.0
            })

            importe_operacion = CalculosAuxiliares.convertir_a_numero(fila_actual["importe"])

            # Valor abonado según PDF
            abonado_pdf = round(
                importe_operacion
                - abs(CalculosAuxiliares.convertir_a_numero(fila_actual.get("arancel_valor", 0)))
                - abs(CalculosAuxiliares.convertir_a_numero(fila_actual.get("interes_valor", 0)))
                + abs(CalculosAuxiliares.convertir_a_numero(fila_actual.get("bonificacion_valor", 0))),
                2
            )

            # Cálculo teórico según tipo de operación
            if str(fila_actual.get("tipo_operacion", "")).upper().startswith("DEV"):
                abonado_teorico = round(
                    importe_operacion
                    + (importe_operacion * porcentajes["arancel"] / 100)
                    + (importe_operacion * porcentajes["interes"] / 100)
                    - (importe_operacion * porcentajes["bonificacion"] / 100),
                    2
                )
            else:  # Operación de venta normal
                abonado_teorico = round(
                    importe_operacion
                    - (importe_operacion * porcentajes["arancel"] / 100)
                    - (importe_operacion * porcentajes["interes"] / 100)
                    + (importe_operacion * porcentajes["bonificacion"] / 100),
                    2
                )

            diferencia = round(abonado_pdf - abonado_teorico, 2)
            diferencia_absoluta = abs(diferencia)
            estado = "Correcta" if diferencia_absoluta <= 0.01 else "Incorrecta"

            lista_abonados.append(abonado_pdf)
            lista_diferencias.append(diferencia_absoluta)
            lista_estados.append(estado)

        # Añadir columnas calculadas
        dataframe_operaciones["importe_abonado"] = lista_abonados
        dataframe_operaciones["diferencia"] = lista_diferencias
        dataframe_operaciones["estado"] = lista_estados

        # Filtrar solo operaciones incorrectas
        dataframe_errores = dataframe_operaciones[dataframe_operaciones["estado"] == "Incorrecta"]

        # Guardar resultados tanto en la UI como en el procesador
        self.dataframe_resultados = dataframe_operaciones
        self.procesador.dataframe_resultados = dataframe_operaciones

        # Construir la interfaz de visualización
        self.mostrar_resultados_en_interfaz(dataframe_errores)
    
    def actualizar_estado(self, mensaje):
            """Actualiza la etiqueta de estado y la barra de progreso."""
            self.etiqueta_estado.setText(mensaje)
            self.barra_progreso.setValue(100)  # Opcional: ajustar el progreso si es necesario
            QApplication.processEvents()  # Para actualizar la interfaz inmediatamente

    def mostrar_resultados_en_interfaz(self, dataframe_errores):
        """Muestra los resultados en la interfaz gráfica."""
        contenedor = QWidget()
        layout_vertical = QVBoxLayout(contenedor)

        # Resumen global
        total_adeudado = dataframe_errores["diferencia"].sum()
        cantidad_errores = len(dataframe_errores)

        texto_resumen = (
            "<b>Resumen de Diferencias</b><br>"
            f"Resumen emitido: {self.procesador.diccionario_metadatos.get('fecha_emision', '--')}<br>"
            f"Fecha de pago: {self.procesador.diccionario_metadatos.get('fecha_pago', '--')}<br>"
            f"Forma de pago: {self.procesador.diccionario_metadatos.get('forma_pago', '--')}<br><br>"
            f"<b>Total adeudado:</b> {CalculosAuxiliares.formatear_moneda_pesos(total_adeudado)}<br>"
            f"<b>Operaciones con diferencias:</b> {cantidad_errores}"
        )

        etiqueta_resumen = QLabel(texto_resumen)
        etiqueta_resumen.setTextFormat(Qt.TextFormat.RichText)
        etiqueta_resumen.setWordWrap(True)
        layout_vertical.addWidget(etiqueta_resumen)
        layout_vertical.addSpacing(15)

        # Mostrar por variante de plan si hay errores
        if not dataframe_errores.empty:
            variantes_con_error = sorted(dataframe_errores["variante_plan"].unique())

            for variante in variantes_con_error:
                datos_variante = dataframe_errores[dataframe_errores["variante_plan"] == variante]
                self.agregar_seccion_variante(variante, datos_variante, layout_vertical)
        else:
            layout_vertical.addWidget(QLabel("No se encontraron operaciones con diferencias."))

        layout_vertical.addStretch()
        self.contenedor_scroll.setWidget(contenedor)  # corregido, antes estaba self.area_previsualizacion
        self.boton_exportar.setEnabled(True)
        self.actualizar_estado("Vista previa generada. Listo para exportar.")

    def agregar_seccion_variante(self, variante_plan, datos_variante, layout_principal):
        """Agrega una sección a la vista previa para mostrar resultados de una variante de plan específica."""
        grupo = QGroupBox(f"Resultados para {variante_plan}")
        layout_grupo = QVBoxLayout(grupo)

        # Obtener porcentajes desde el procesador (corregido)
        porcentajes_originales = self.procesador.diccionario_porcentajes_originales.get(variante_plan, {})
        porcentajes_ajustados  = self.procesador.diccionario_porcentajes_ajustados.get(variante_plan, {})

        # Resumen de porcentajes
        resumen_porcentajes = QLabel(
            f"<b>Porcentajes originales:</b> "
            f"Arancel {porcentajes_originales.get('arancel', 0):.2f}%, "
            f"Interés {porcentajes_originales.get('interes', 0):.2f}%, "
            f"Bonificación {porcentajes_originales.get('bonificacion', 0):.2f}%<br>"
            f"<b>Porcentajes ajustados:</b> "
            f"Arancel {porcentajes_ajustados.get('arancel', 0):.2f}%, "
            f"Interés {porcentajes_ajustados.get('interes', 0):.2f}%, "
            f"Bonificación {porcentajes_ajustados.get('bonificacion', 0):.2f}%"
        )
        resumen_porcentajes.setTextFormat(Qt.TextFormat.RichText)
        layout_grupo.addWidget(resumen_porcentajes)

        # Crear tabla de resultados
        tabla = QTableWidget()
        tabla.setColumnCount(len(datos_variante.columns))
        tabla.setHorizontalHeaderLabels(datos_variante.columns)

        tabla.setRowCount(len(datos_variante))
        for fila, (_, fila_datos) in enumerate(datos_variante.iterrows()):
            for col, valor in enumerate(fila_datos):
                item = QTableWidgetItem(str(valor))
                if fila_datos["estado"] == "Incorrecta" and datos_variante.columns[col] == "diferencia":
                    item.setBackground(QColor("red"))
                    item.setForeground(QColor("white"))
                tabla.setItem(fila, col, item)

        tabla.resizeColumnsToContents()
        layout_grupo.addWidget(tabla)

        layout_principal.addWidget(grupo)

    def crear_tabla_operaciones(self, dataframe_operaciones):
        """Crea y configura una tabla con las operaciones."""
        columnas = [
            "fecha", "terminal-lote", "presentacion", "plan", 
            "importe", "importe_abonado", "diferencia", "tipo_operacion"
        ]
        nombres_columnas = [
            "Fecha", "Terminal-Lote", "Presentación", "Plan",
            "Importe", "Abonado", "Diferencia", "Tipo Op."
        ]

        tabla = QTableWidget()
        tabla.setColumnCount(len(columnas))
        tabla.setHorizontalHeaderLabels(nombres_columnas)
        tabla.setRowCount(len(dataframe_operaciones))

        for indice_fila, (_, fila) in enumerate(dataframe_operaciones.iterrows()):
            valores_fila = [
                str(fila["fecha"]),
                str(fila["terminal-lote"]),
                str(fila["presentacion"]),
                str(fila["plan"]),
                CalculosAuxiliares.formatear_moneda_pesos(fila["importe"]),
                CalculosAuxiliares.formatear_moneda_pesos(fila["importe_abonado"]),
                CalculosAuxiliares.formatear_moneda_pesos(fila["diferencia"]),
                str(fila["tipo_operacion"])
            ]


            for indice_columna, valor in enumerate(valores_fila):
                item = QTableWidgetItem(valor)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                # Resaltar diferencias importantes
                if indice_columna == nombres_columnas.index("Diferencia"):
                    diferencia = fila["diferencia"]
                    if diferencia > 1000:  # Resaltar diferencias mayores a $1000
                        item.setBackground(QColor(255, 200, 200))  # Rojo claro
                
                tabla.setItem(indice_fila, indice_columna, item)

        tabla.resizeColumnsToContents()
        return tabla

    def _finalizar_carga_pdf(self, tipo_numero: Optional[str] = None):
        self.barra_progreso.setValue(100)
        self.etiqueta_estado.setText("Archivo procesado correctamente")
        self.boton_recalcular.setEnabled(True)
        self._refrescar_grafico_si_hay_datos()
        if tipo_numero:
            self.construir_resumen_inicial(tipo_numero)

    def mostrar_resumen_inicial(self):
        """Muestra un resumen inicial extendido con metadatos, totales, detalle por plan e impuestos/retenciones/percepciones."""
        try:
            # Verificar si hay archivos cargados
            if not self.archivos_cargados:
                try:
                    self.limpiar_area_visualizacion()
                    etiqueta = QLabel("No hay archivos cargados. Use el botón 'Cargar Resúmenes PDF' para agregar archivos.")
                    etiqueta.setWordWrap(True)
                    self.layout_contenido.addWidget(etiqueta)
                    self.layout_contenido.addStretch()
                except RuntimeError:
                    self._recrear_layout_contenido()
                    etiqueta = QLabel("No hay archivos cargados. Use el botón 'Cargar Resúmenes PDF' para agregar archivos.")
                    etiqueta.setWordWrap(True)
                    self.layout_contenido.addWidget(etiqueta)
                    self.layout_contenido.addStretch()
                return
            
            # Obtener el archivo seleccionado en la lista
            current_row = self.lista_archivos.currentRow()
            if current_row < 0 or current_row >= len(self.archivos_cargados):
                # Si no hay selección, mostrar el primer archivo
                current_row = 0
                if self.lista_archivos.rowCount() > 0:
                    self.lista_archivos.setCurrentCell(0, 0)
            
            # Obtener la ruta del archivo seleccionado
            try:
                ruta_archivo = list(self.archivos_cargados.keys())[current_row]
                datos_archivo = self.archivos_cargados[ruta_archivo]
                
                df = datos_archivo["df_operaciones"]
                metadatos = datos_archivo["metadatos"]
                resumen_impositivo = datos_archivo.get("resumen_impositivo", {})

                if df is None or df.empty:
                    self.limpiar_area_visualizacion()
                    etiqueta = QLabel("No se encontraron operaciones en el PDF cargado.")
                    etiqueta.setWordWrap(True)
                    self.layout_contenido.addWidget(etiqueta)
                    self.layout_contenido.addStretch()
                    return

                # Totales globales
                ventas = df[df["tipo_operacion"].str.upper() == "VTA"]
                devoluciones = df[df["tipo_operacion"].str.upper() == "DEV"]

                total_operaciones = len(df)
                total_vta = len(ventas)
                total_dev = len(devoluciones)

                facturacion_total = df["importe"].sum()
                arancel_total = df["arancel_valor"].sum()
                interes_total = df["interes_valor"].sum()
                bonificacion_total = df["bonificacion_valor"].sum()
                importe_bruto_cobrar = facturacion_total - arancel_total - interes_total + bonificacion_total

                # Detalle por plan (solo ventas)
                detalle_planes = []
                if not ventas.empty:
                    df_planes = ventas.groupby("plan")["importe"].agg(["count", "sum"]).reset_index()
                    for _, fila in df_planes.iterrows():
                        detalle_planes.append(
                            f"Plan {fila['plan']} → {int(fila['count'])} operaciones – $ {CalculosAuxiliares.formatear_moneda_pesos(fila['sum'])}"
                        )
                else:
                    detalle_planes.append("No hay ventas en este resumen")

                # --- BLOQUE: Impuestos, retenciones, percepciones ---
                texto_impuestos = ""
                if resumen_impositivo:
                    # 1. Detalles de Facturación (IVA, percepciones, etc.)
                    if resumen_impositivo.get("detalles_facturacion"):
                        texto_impuestos += "<h3>📑 Detalles de Facturación</h3><ul>"
                        for concepto, monto in resumen_impositivo["detalles_facturacion"].items():
                            texto_impuestos += f"<li>{concepto}: $ {monto}</li>"
                        texto_impuestos += "</ul>"

                    # 2. Retenciones Impositivas
                    if resumen_impositivo.get("retenciones_impositivas"):
                        texto_impuestos += "<h3>📑 Retenciones / Percepciones Impositivas</h3><ul>"
                        for concepto, monto in resumen_impositivo["retenciones_impositivas"].items():
                            texto_impuestos += f"<li>{concepto}: $ {monto}</li>"
                        texto_impuestos += "</ul>"

                    # 3. Neto Liquidado
                    if resumen_impositivo.get("neto_liquidado"):
                        texto_impuestos += (
                            "<h3>💰 Neto Liquidado</h3>"
                            f"<b>Total Neto a Cobrar:</b> $ {resumen_impositivo['neto_liquidado']}"
                        )
                else:
                    texto_impuestos = "<p>No se encontró información impositiva</p>"

                # Construcción del texto
                nombre_archivo = os.path.basename(ruta_archivo)
                texto_resumen = (
                    f"<h2>🖥️ Resumen inicial - {nombre_archivo}</h2>"
                    "<h3>📋 Resumen Global del Resumen PDF</h3>"
                    f"📝 Tipo y Nº: {metadatos.get('tipo_numero', '--')}<br>"
                    f"📅 Fecha de emisión: {metadatos.get('fecha_emision', '--')}<br>"
                    f"📅 Fecha de pago: {metadatos.get('fecha_pago', '--')}<br>"
                    f"💳 Forma de pago: {metadatos.get('forma_pago', '--')}<br><br>"
                    f"<b>Importe bruto a Cobrar:</b> $ {CalculosAuxiliares.formatear_moneda_pesos(importe_bruto_cobrar)}<br><br>"

                    "<h3>📊 Detalle por Plan (Ventas)</h3>"
                    + "<br>".join(detalle_planes) +
                    "<br><br>" +

                    texto_impuestos +

                    "<h3>📊 Totales del Resumen</h3>"
                    f"Operaciones totales: {total_operaciones}<br>"
                    f"Ventas (VTA): {total_vta}<br>"
                    f"Devoluciones (DEV): {total_dev}<br>"
                    f"Facturación total: $ {CalculosAuxiliares.formatear_moneda_pesos(facturacion_total)}<br>"
                    f"Total Aranceles: $ {CalculosAuxiliares.formatear_moneda_pesos(arancel_total)}<br>"
                    f"Total Intereses: $ {CalculosAuxiliares.formatear_moneda_pesos(interes_total)}<br>"
                    f"Total Bonificación: $ {CalculosAuxiliares.formatear_moneda_pesos(bonificacion_total)}<br><br>"
                )

                # Mostrar en la interfaz
                self.limpiar_area_visualizacion()
                etiqueta_resumen = QLabel(texto_resumen)
                etiqueta_resumen.setTextFormat(Qt.TextFormat.RichText)
                etiqueta_resumen.setWordWrap(True)
                self.layout_contenido.addWidget(etiqueta_resumen)
                self.layout_contenido.addStretch()

            except (IndexError, KeyError) as e:
                print(f"Error al mostrar resumen: {e}")
                self.limpiar_area_visualizacion()
                etiqueta = QLabel("Error al cargar el resumen del archivo seleccionado.")
                etiqueta.setWordWrap(True)
                self.layout_contenido.addWidget(etiqueta)
                self.layout_contenido.addStretch()

        except RuntimeError as e:
            print(f"RuntimeError en mostrar_resumen_inicial: {e}")
            self._recrear_layout_contenido()
            # Intentar mostrar el mensaje de nuevo después de recrear el layout
            etiqueta = QLabel("Error en la interfaz. Recargando...")
            etiqueta.setWordWrap(True)
            self.layout_contenido.addWidget(etiqueta)
            self.layout_contenido.addStretch()
            
        except Exception as e:
            print(f"Error inesperado en mostrar_resumen_inicial: {e}")
            try:
                self.limpiar_area_visualizacion()
                etiqueta = QLabel(f"Error inesperado: {str(e)}")
                etiqueta.setWordWrap(True)
                self.layout_contenido.addWidget(etiqueta)
                self.layout_contenido.addStretch()
            except:
                self._recrear_layout_contenido()
                etiqueta = QLabel(f"Error inesperado: {str(e)}")
                etiqueta.setWordWrap(True)
                self.layout_contenido.addWidget(etiqueta)
                self.layout_contenido.addStretch()

    def manejar_exportacion(self):
        """Maneja el proceso de exportación de resultados"""
        print(f"DEBUG: Iniciando exportación. dataframe_resultados es None? {self.procesador.dataframe_resultados is None}")
        
        if self.procesador.dataframe_resultados is None:
            QMessageBox.warning(self, "Advertencia", "No hay resultados para exportar. Ejecute primero el recálculo.")
            return
        
        # Diálogo para seleccionar formatos
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox
        
        dlg = QDialog(self)
        dlg.setWindowTitle("Seleccionar formatos de exportación")
        layout = QVBoxLayout(dlg)
        
        # Checkboxes para formatos
        chk_csv = QCheckBox("CSV (.csv)")
        chk_excel = QCheckBox("Excel (.xlsx)")
        chk_pdf = QCheckBox("PDF (.pdf)")
        
        # Seleccionar todos por defecto
        chk_csv.setChecked(True)
        chk_excel.setChecked(True)
        chk_pdf.setChecked(True)
        
        layout.addWidget(chk_csv)
        layout.addWidget(chk_excel)
        layout.addWidget(chk_pdf)
        
        # Botones
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(botones)
        
        botones.accepted.connect(dlg.accept)
        botones.rejected.connect(dlg.reject)
        
        if dlg.exec() != QDialog.DialogCode.Accepted:
            print("DEBUG: Usuario canceló diálogo de formatos")
            return
        
        # Obtener formatos seleccionados
        formatos_seleccionados = []
        if chk_csv.isChecked():
            formatos_seleccionados.append('csv')
        if chk_excel.isChecked():
            formatos_seleccionados.append('excel')
        if chk_pdf.isChecked():
            formatos_seleccionados.append('pdf')
        
        print(f"DEBUG: Formatos seleccionados: {formatos_seleccionados}")
        
        if not formatos_seleccionados:
            QMessageBox.information(self, "Información", "No se seleccionó ningún formato para exportar.")
            return
        
        # Pedir ruta base si se seleccionó más de un formato
        rutas_destino = {}
        if len(formatos_seleccionados) > 1:
            ruta_base, _ = QFileDialog.getSaveFileName(
                self, 
                "Guardar archivos (se crearán múltiples archivos)",
                "analisis_resumen",  # 🔹 Nombre por defecto
                "Todos los archivos (*)"
            )
            print(f"DEBUG: Ruta base seleccionada: {ruta_base}")
            
            if not ruta_base:  # 🔹 Verificar si el usuario canceló
                print("DEBUG: Usuario canceló diálogo de ruta base")
                return
            
            # Construir rutas para cada formato
            for formato in formatos_seleccionados:
                if formato == 'csv':
                    rutas_destino[formato] = f"{ruta_base}.csv"
                elif formato == 'excel':
                    rutas_destino[formato] = f"{ruta_base}.xlsx"
                elif formato == 'pdf':
                    rutas_destino[formato] = f"{ruta_base}.pdf"
        else:
            # Pedir ruta individual para un solo formato
            formato = formatos_seleccionados[0]
            extension = ".csv" if formato == 'csv' else ".xlsx" if formato == 'excel' else ".pdf"
            
            ruta_destino, _ = QFileDialog.getSaveFileName(
                self, 
                f"Guardar archivo {formato.upper()}", 
                f"analisis_resumen{extension}",  # 🔹 Nombre por defecto
                f"{formato.upper()} (*{extension})"
            )
            
            print(f"DEBUG: Ruta individual seleccionada: {ruta_destino}")
            
            # 🔹 VERIFICACIÓN CRÍTICA: Si el usuario cancela, salir
            if not ruta_destino:
                print("DEBUG: Usuario canceló diálogo de guardar archivo")
                return
            
            # 🔹 Asegurar que la ruta tenga la extensión correcta
            if not ruta_destino.endswith(extension):
                ruta_destino += extension
            
            rutas_destino[formato] = ruta_destino
        
        print(f"DEBUG: Rutas destino finales: {rutas_destino}")
        
        if not rutas_destino:
            print("DEBUG: No se seleccionaron rutas válidas")
            return
        
        try:
            # Exportar cada formato
            rutas_exportadas = {}
            for formato, ruta_destino in rutas_destino.items():
                try:
                    print(f"DEBUG: Exportando {formato} a {ruta_destino}")
                    
                    if formato == 'pdf':
                        # Para PDF necesitamos generar el gráfico temporal
                        ruta_grafico_temp = ruta_destino.replace('.pdf', '_grafico_temp.png')
                        print(f"DEBUG: Generando gráfico temporal: {ruta_grafico_temp}")
                        
                        self.procesador.guardar_grafico_planes_temp(ruta_grafico_temp)
                        self.procesador._exportar_pdf_interno(ruta_destino, ruta_grafico_temp)
                        
                        # Limpiar archivo temporal
                        try:
                            if os.path.exists(ruta_grafico_temp):
                                os.remove(ruta_grafico_temp)
                                print(f"DEBUG: Archivo temporal eliminado: {ruta_grafico_temp}")
                        except Exception as e:
                            print(f"DEBUG: Error eliminando archivo temporal: {e}")
                            
                    elif formato == 'csv':
                        self.procesador._exportar_csv_interno(ruta_destino)
                    elif formato == 'excel':
                        self.procesador._exportar_excel_interno(ruta_destino)
                    
                    rutas_exportadas[formato] = ruta_destino
                    print(f"DEBUG: {formato} exportado exitosamente")
                    
                except Exception as e:
                    print(f"ERROR exportando {formato.upper()}: {str(e)}")
            
            if rutas_exportadas:
                mensaje = "Archivos exportados correctamente:\n"
                for formato, ruta in rutas_exportadas.items():
                    mensaje += f"• {formato.upper()}: {ruta}\n"
                
                print(f"DEBUG: Exportación completada: {mensaje}")
                QMessageBox.information(self, "Éxito", mensaje)
            else:
                print("DEBUG: No se exportó ningún archivo")
                QMessageBox.warning(self, "Advertencia", "No se exportó ningún archivo.")
                
        except Exception as error:
            print(f"DEBUG: Error general en exportación: {str(error)}")
            QMessageBox.critical(self, "Error", f"No se pudieron exportar los archivos:\n{str(error)}")

    def manejar_recalculo(self):
        """Maneja el recálculo de operaciones con porcentajes ajustados por el usuario."""
        # --- Validación inicial ---
        if self.procesador.dataframe_operaciones is None or self.procesador.dataframe_operaciones.empty:
            QMessageBox.warning(self, "Advertencia", "No hay operaciones para procesar")
            return

        # --- Detectar configuraciones ---
        configuraciones_detectadas = self.procesador.detectar_configuraciones_plan()

        if not configuraciones_detectadas:
            QMessageBox.information(self, "Información", "No se detectaron configuraciones de planes.")
            return

        # --- Abrir diálogo de porcentajes ---
        nuevos_porcentajes = self.pedir_porcentajes(configuraciones_detectadas)

        if not nuevos_porcentajes:
            self.actualizar_estado("Recalculo cancelado por el usuario.")
            return

        try:
            # --- Ejecutar recálculo en el PROCESADOR ---
            self.procesador.recalcular_con_porcentajes_ajustados(nuevos_porcentajes)
            
            # --- Actualizar la referencia en la interfaz ---
            self.dataframe_resultados = self.procesador.dataframe_resultados

            # --- Construir vista previa con los resultados ---
            self.construir_vista_previa()

            # --- Habilitar exportación ---
            self.boton_exportar.setEnabled(True)

            # --- Actualizar estado ---
            self.actualizar_estado("Recalculo completado correctamente.")

        except Exception as error:
            QMessageBox.critical(
                self,
                "Error en recálculo",
                f"Ocurrió un problema durante el recálculo:\n{str(error)}"
            )
            self.actualizar_estado("Error en el recálculo.")

    def limpiar_area_visualizacion(self):
        """Elimina todo el contenido del área de visualización."""
        try:
            # Verificar si el layout todavía existe
            if self.layout_contenido is not None:
                while self.layout_contenido.count():
                    item = self.layout_contenido.takeAt(0)
                    if item is not None:
                        widget = item.widget()
                        if widget is not None:
                            widget.setParent(None)
                            widget.deleteLater()
        except RuntimeError as e:
            print(f"Error al limpiar área de visualización: {e}")
            # Recrear el layout si fue eliminado
            self._recrear_layout_contenido()

    def _recrear_layout_contenido(self):
        """Recrea el layout de contenido si fue eliminado."""
        try:
            # Crear nuevo widget de contenido
            self.widget_contenido = QWidget()
            self.widget_contenido.setObjectName("contenidoPrincipal")
            self.layout_contenido = QVBoxLayout(self.widget_contenido)
            self.contenedor_scroll.setWidget(self.widget_contenido)
            print("DEBUG: Layout de contenido recreado")
        except Exception as e:
            print(f"Error recreando layout: {e}")

    def mostrar_resultados_recalculo(self):
        """Muestra los resultados del recálculo en la interfaz."""
        reporte = self.procesador.generar_reporte_por_plan()
        total_adeudado = sum(
            datos_plan["diferencia_total"]
            for datos_plan in reporte.values()
        )

        # Limpiar área de visualización
        self.limpiar_area_visualizacion()

        # Resumen global
        texto_resumen = (
            f"<b>Resumen de diferencias encontradas</b><br><br>"
            f"<b>Total adeudado:</b> {CalculosAuxiliares.formatear_moneda_pesos(total_adeudado)}<br>"
            f"<b>Fecha emisión:</b> {self.procesador.diccionario_metadatos.get('fecha_emision', '--')}<br>"
            f"<b>Fecha pago:</b> {self.procesador.diccionario_metadatos.get('fecha_pago', '--')}<br>"
            f"<b>Forma pago:</b> {self.procesador.diccionario_metadatos.get('forma_pago', '--')}"
        )

        etiqueta_resumen = QLabel(texto_resumen)
        etiqueta_resumen.setTextFormat(Qt.TextFormat.RichText)
        etiqueta_resumen.setWordWrap(True)
        self.layout_contenido.addWidget(etiqueta_resumen)
        self.layout_contenido.addSpacing(20)

        # Detalle por plan
        for variante_plan, datos_plan in reporte.items():
            grupo_plan = QGroupBox(f"Plan: {variante_plan}")
            layout_grupo = QVBoxLayout()

            texto_plan = (
                f"<b>Operaciones analizadas:</b> {datos_plan['total_operaciones']}<br>"
                f"<b>Operaciones con diferencias:</b> {datos_plan['operaciones_erroneas']}<br>"
                f"<b>Total adeudado:</b> {CalculosAuxiliares.formatear_moneda_pesos(datos_plan['diferencia_total'])}<br><br>"
                "<b>Porcentajes aplicados:</b><br>"
                f"- Arancel: {CalculosAuxiliares.formatear_porcentaje(datos_plan['porcentajes_originales'].get('arancel', 0))} "
                f"(Ajustado: {CalculosAuxiliares.formatear_porcentaje(datos_plan['porcentajes_ajustados'].get('arancel', 0))})<br>"
                f"- Interés: {CalculosAuxiliares.formatear_porcentaje(datos_plan['porcentajes_originales'].get('interes', 0))} "
                f"(Ajustado: {CalculosAuxiliares.formatear_porcentaje(datos_plan['porcentajes_ajustados'].get('interes', 0))})<br>"
                f"- Bonificación: {CalculosAuxiliares.formatear_porcentaje(datos_plan['porcentajes_originales'].get('bonificacion', 0))} "
                f"(Ajustado: {CalculosAuxiliares.formatear_porcentaje(datos_plan['porcentajes_ajustados'].get('bonificacion', 0))})"
            )

            etiqueta_plan = QLabel(texto_plan)
            etiqueta_plan.setTextFormat(Qt.TextFormat.RichText)
            etiqueta_plan.setWordWrap(True)
            layout_grupo.addWidget(etiqueta_plan)

            # Tabla de operaciones con errores
            tabla = QTableWidget()
            tabla.setColumnCount(7)
            tabla.setHorizontalHeaderLabels([
                "Fecha", "Terminal", "Plan", "Importe", 
                "Abonado", "Diferencia", "Tipo Op."
            ])
            tabla.setRowCount(len(datos_plan["detalle_errores"]))

            for indice_fila, (_, fila_error) in enumerate(datos_plan["detalle_errores"].iterrows()):
                tabla.setItem(indice_fila, 0, QTableWidgetItem(str(fila_error["fecha"])))
                tabla.setItem(indice_fila, 1, QTableWidgetItem(str(fila_error["terminal-lote"])))
                tabla.setItem(indice_fila, 2, QTableWidgetItem(str(fila_error["plan"])))
                tabla.setItem(indice_fila, 3, QTableWidgetItem(
                    CalculosAuxiliares.formatear_moneda_pesos(fila_error["importe"])
                ))
                tabla.setItem(indice_fila, 4, QTableWidgetItem(
                    CalculosAuxiliares.formatear_moneda_pesos(fila_error["importe_abonado"])
                ))
                tabla.setItem(indice_fila, 5, QTableWidgetItem(
                    CalculosAuxiliares.formatear_moneda_pesos(fila_error["diferencia"])
                ))
                tabla.setItem(indice_fila, 6, QTableWidgetItem(str(fila_error["tipo_operacion"])))

            tabla.resizeColumnsToContents()
            layout_grupo.addWidget(tabla)
            grupo_plan.setLayout(layout_grupo)
            self.layout_contenido.addWidget(grupo_plan)

        self.layout_contenido.addStretch()

    def actualizar_grafico_planes(self):
        """Actualiza el gráfico de torta con % por plan (solo VTA)"""
        import numpy as np
        
        df = self.procesador.dataframe_operaciones
        self.ax_planes.clear()

        if df is None or df.empty:
            self.ax_planes.text(0.5, 0.5, "Sin datos", ha="center", va="center")
            self.canvas_planes.draw()
            return

        ventas = df[df["tipo_operacion"].astype(str).str.upper() == "VTA"]
        conteo = (
            ventas["plan"]
            .fillna("—")
            .astype(str)
            .value_counts()
            .sort_index()
        )

        total = int(conteo.sum())
        if total == 0:
            self.ax_planes.text(0.5, 0.5, "Sin ventas (VTA)", ha="center", va="center")
            self.canvas_planes.draw()
            self.label_leyenda_planes.setText("No se registraron ventas en el archivo.")
            return

        etiquetas = list(conteo.index)
        cantidades = conteo.values.tolist()
        porcentajes = (conteo / total * 100).values.tolist()

        # Paleta de colores
        palette = ["#4285F4", "#F59E0B", "#9333EA", "#A3E635", "#10B981",
                "#EF4444", "#3B82F6", "#14B8A6", "#8B5CF6", "#FB923C"]
        colors = [palette[i % len(palette)] for i in range(len(etiquetas))]

        # Usar autopct pero manejar el retorno correctamente
        pie_result = self.ax_planes.pie(
            porcentajes,
            startangle=90,
            counterclock=False,
            colors=colors,
            autopct=lambda p: f'{p:.1f}%' if p > 5 else '',  # Solo mostrar > 5%
            pctdistance=0.7,
            wedgeprops={"linewidth": 1, "edgecolor": "white"}
        )
        
        # El retorno puede ser 2 o 3 elementos dependiendo de autopct
        if len(pie_result) == 3:
            wedges, texts, autotexts = pie_result
        else:
            wedges, texts = pie_result
            autotexts = []

        self.ax_planes.axis("equal")
        self.ax_planes.set_title("Planes sobre el total de VENTAS")

        # Leyenda con cantidades
        lbls = [
            f"{etiquetas[i]} — {cantidades[i]} venta{'s' if cantidades[i]!=1 else ''}"
            for i in range(len(etiquetas))
        ]
        self.ax_planes.legend(
            wedges, lbls, loc="upper center", bbox_to_anchor=(0.5, -0.05),
            ncol=1, frameon=False
        )

        # Limpiar placeholder
        self.label_leyenda_planes.setText("")
        self.canvas_planes.draw()

    def _refrescar_grafico_si_hay_datos(self):
        """Actualiza el gráfico de planes si hay datos disponibles"""
        try:
            # Verificar si tenemos datos y si el gráfico está inicializado
            if (hasattr(self, 'procesador') and 
                self.procesador.dataframe_operaciones is not None and 
                not self.procesador.dataframe_operaciones.empty and
                hasattr(self, 'ax_planes') and
                hasattr(self, 'canvas_planes')):
                
                self.actualizar_grafico_planes()
                
        except Exception as e:
            print(f"Error al refrescar gráfico: {e}")
            # Continuar sin gráfico si hay error

    def guardar_grafico_planes_temp(self, ruta_destino):
        """Guarda un gráfico temporal de distribución de planes para usar en PDF"""
        try:
            df = self.procesador.dataframe_operaciones
            if df is None or df.empty:
                return
            
            ventas = df[df["tipo_operacion"].astype(str).str.upper() == "VTA"]
            if ventas.empty:
                return
            
            conteo = ventas["plan"].value_counts()
            
            plt.figure(figsize=(8, 6))
            plt.pie(
                conteo.values.tolist(), 
                labels=conteo.index.tolist(), 
                autopct='%1.1f%%'
            )
            plt.title('Distribución de Planes (Ventas)')
            plt.savefig(ruta_destino, bbox_inches='tight', dpi=100)
            plt.close()
            
        except Exception as e:
            print(f"Error al guardar gráfico temporal: {e}")
# ========================================================
# Lanzador principal
# ========================================================
if __name__ == "__main__":
    aplicacion = QApplication([])
    
    # Establecer estilo visual consistente
    aplicacion.setStyle("Fusion")
    
    ventana_principal = InterfazGrafica()
    ventana_principal.show()
    
    aplicacion.exec()

# === EL CODIGO ORIGINAL TERMINA ACA ===

class DemoBackend:
    def __init__(self):
        self.procesador = ProcesadorLogico()
        self.archivos_procesados = {}
        
    def procesar_pdf(self, archivo_bytes, nombre_archivo):
        """Procesa un archivo PDF y devuelve resultados"""
        # Guardar archivo temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(archivo_bytes)
            tmp_path = tmp.name
        
        try:
            # Procesar con tu lógica existente
            operaciones = self.procesador.extraer_operaciones_del_pdf(tmp_path)
            metadatos = self.procesador.extraer_metadatos_del_pdf(tmp_path)
            configuraciones = self.procesador.detectar_configuraciones_plan()
            
            # Guardar resultados
            self.archivos_procesados[nombre_archivo] = {
                'operaciones': operaciones,
                'metadatos': metadatos,
                'configuraciones': configuraciones
            }
            
            return {
                'success': True,
                'operaciones': len(operaciones),
                'metadatos': metadatos,
                'configuraciones': configuraciones
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            # Limpiar archivo temporal
            os.unlink(tmp_path)
    
    def recalcular_operaciones(self, porcentajes_ajustados):
        """Recalcula operaciones con nuevos porcentajes"""
        try:
            self.procesador.recalcular_con_porcentajes_ajustados(porcentajes_ajustados)
            reporte = self.procesador.generar_reporte_por_plan()
            
            return {
                'success': True,
                'reporte': reporte,
                'dataframe': self.procesador.dataframe_resultados
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def generar_grafico(self):
        """Genera gráfico de distribución de planes"""
        if self.procesador.dataframe_operaciones is None:
            return None
            
        ventas = self.procesador.dataframe_operaciones[
            self.procesador.dataframe_operaciones["tipo_operacion"].astype(str).str.upper() == "VTA"
        ]
        
        if ventas.empty:
            return None
            
        conteo = ventas["plan"].value_counts()
        
        plt.figure(figsize=(10, 8))
        plt.pie(conteo.values.tolist(), labels=conteo.index.tolist(), autopct='%1.1f%%')
        plt.title('Distribución de Planes (Ventas)')
        
        # Convertir a base64 para mostrar en web
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        plt.close()
        
        return base64.b64encode(buf.read()).decode('utf-8')
    
    def exportar_resultados(self, formato):
        """Exporta resultados en formato solicitado - VERSIÓN CORREGIDA"""
        if self.procesador.dataframe_resultados is None:
            return None
        
        # Crear archivo temporal con manejo seguro para Windows
        try:
            # Crear archivo temporal con nombre único
            import tempfile
            import uuid
            
            # Generar nombre único
            nombre_temp = f"temp_{uuid.uuid4().hex}.{formato}"
            temp_path = os.path.join(tempfile.gettempdir(), nombre_temp)
            
            if formato == 'csv':
                self.procesador._exportar_csv_interno(temp_path)
            elif formato == 'xlsx':
                self.procesador._exportar_excel_interno(temp_path)
            elif formato == 'pdf':
                # Para PDF necesitamos generar el gráfico primero
                ruta_grafico = temp_path.replace('.pdf', '_chart.png')
                self.procesador.guardar_grafico_planes_temp(ruta_grafico)
                self.procesador._exportar_pdf_interno(temp_path, ruta_grafico)
                # Limpiar archivo temporal del gráfico
                try:
                    if os.path.exists(ruta_grafico):
                        os.unlink(ruta_grafico)
                except:
                    pass
            
            # Leer y devolver contenido
            with open(temp_path, 'rb') as f:
                contenido = f.read()
            
            return contenido
            
        except Exception as e:
            print(f"Error en exportación: {e}")
            return None
        finally:
            # Limpieza segura para Windows
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass  # Ignorar errores de limpieza