import pdfplumber
import pandas as pd
import matplotlib.pyplot as plt
import re
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet

# 🔹 Clase auxiliar para conversiones y formatos
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

class ProcesadorLogico:
    def __init__(self):
        self.operaciones_por_resumen = {}
        self.resultados_por_resumen = {}
        self.metadatos_por_resumen = {}
        self.porcentajes_originales_por_resumen = {}
        self.porcentajes_ajustados_por_resumen = {}
        self.resumen_impositivo_por_resumen = {}

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

    def exportar_csv_bytes(self):
        if self.dataframe_resultados is None:
            raise ValueError("No hay resultados para exportar")
        buffer = io.BytesIO()
        self.dataframe_resultados.to_csv(buffer, sep=";", index=False, encoding="utf-8")
        buffer.seek(0)
        return buffer

    def exportar_excel_bytes(self):
        if self.dataframe_resultados is None:
            raise ValueError("No hay resultados para exportar")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            self.dataframe_resultados.to_excel(writer, index=False)
        buffer.seek(0)
        return buffer

    def exportar_pdf_bytes(self):
        if self.dataframe_resultados is None:
            raise ValueError("No hay resultados para exportar")
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        elements = []
        elements.append(Paragraph("ANÁLISIS DE LIQUIDACIÓN - TARJETA NARANJA", styles['Heading1']))
        elements.append(Spacer(1, 12))
        # (acá podés armar el mismo contenido que en tu _exportar_pdf_interno)
        doc.build(elements)
        buffer.seek(0)
        return buffer
