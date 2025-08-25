import streamlit as st
import sys
import os
import json
import requests
from datetime import datetime

# --- Configuración del Path ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

# --- Constantes ---
API_BASE_URL = "http://127.0.0.1:8000"

# --- Configuración de la Página ---
st.set_page_config(
    page_title="Calculadora de Liquidación - Inandes",
    layout="wide"
)

# --- Header con Logos y Título ---
col1, col2, col3 = st.columns([0.25, 0.5, 0.25])
with col1:
    st.image("C:/Users/rguti/Inandes.TECH/inputs_para_generated_pdfs/logo.geek.png", width=200)
with col2:
    st.markdown("<h2 style='text-align: center; font-size: 2.4em;'>Módulo de Liquidación de Factoring</h2>", unsafe_allow_html=True)
with col3:
    st.image("C:/Users/rguti/Inandes.TECH/inputs_para_generated_pdfs/LOGO.png", width=150)

st.markdown("<hr>", unsafe_allow_html=True)

# --- Funciones de Ayuda para la UI ---

def display_operation_profile(data):
    """
    Muestra el perfil de la operación original en un formato de tabla detallado,
    similar al de frontend_app_V.CLI.py.
    """
    st.subheader("Perfil de la Operación Original")

    recalc_result_json = data.get('recalculate_result_json')
    if not recalc_result_json:
        st.warning("No se encontraron datos del perfil de operación original para mostrar.")
        return

    try:
        recalc_result = json.loads(recalc_result_json)
    except json.JSONDecodeError:
        st.error("Error al leer los datos del perfil de operación original.")
        with st.expander("Ver JSON con error"):
            st.json(recalc_result_json)
        return

    # Extraer datos para la cabecera y la tabla
    desglose = recalc_result.get('desglose_final_detallado', {})
    calculos = recalc_result.get('calculo_con_tasa_encontrada', {})
    busqueda = recalc_result.get('resultado_busqueda', {})
    moneda = data.get('moneda_factura', 'PEN')

    # Cabecera
    st.markdown(
        f"**Emisor:** {data.get('emisor_nombre', 'N/A')} | "
        f"**Aceptante:** {data.get('aceptante_nombre', 'N/A')} | "
        f"**Factura:** {data.get('numero_factura', 'N/A')} | "
        f"**F. Emisión:** {data.get('fecha_emision_factura', 'N/A')} | "
        f"**F. Pago:** {data.get('fecha_pago_calculada', 'N/A')} | "
        f"**Monto Neto:** {moneda} {data.get('monto_neto_factura', 0):,.2f}"
    )

    # --- Preparar todos los datos necesarios para la tabla ---
    tasa_avance_pct = busqueda.get('tasa_avance_encontrada', 0) * 100
    monto_neto = data.get('monto_neto_factura', 0)
    capital = calculos.get('capital', 0)
    
    abono = desglose.get('abono', {})
    interes = desglose.get('interes', {})
    com_est = desglose.get('comision_estructuracion', {})
    com_afi = desglose.get('comision_afiliacion', {})
    igv = desglose.get('igv_total', {})
    margen = desglose.get('margen_seguridad', {})

    costos_totales = interes.get('monto', 0) + com_est.get('monto', 0) + com_afi.get('monto', 0) + igv.get('monto', 0)
    tasa_diaria_pct = (data.get('interes_mensual', 0) / 30)

    # --- Construir la tabla en Markdown ---
    lines = []
    lines.append(f"| Item | Monto ({moneda}) | % sobre Neto | Detalle del Cálculo |")
    lines.append("| :--- | :--- | :--- | :--- |")
    
    monto_total = data.get('monto_total_factura', 0)
    detraccion_monto = monto_total - monto_neto
    
    lines.append(f"| Monto Neto de Factura | **{monto_neto:,.2f}** | **100.00%** | Monto a financiar (después de detracciones/retenciones) |")
    lines.append(f"| Tasa de Avance Aplicada | N/A | {tasa_avance_pct:.2f}% | Tasa final encontrada para redondear desembolso |")
    lines.append(f"| Margen de Seguridad | {margen.get('monto', 0):,.2f} | {margen.get('porcentaje', 0):.2f}% | `Monto Neto - Capital` |")
    lines.append(f"| Capital | {capital:,.2f} | {((capital / monto_neto) * 100) if monto_neto else 0:.2f}% | `Monto Neto * Tasa de Avance` |")
    lines.append(f"| Intereses | {interes.get('monto', 0):,.2f} | {interes.get('porcentaje', 0):.2f}% | `Capital * ((1 + Tasa Diaria)^Plazo - 1)` |")
    lines.append(f"| Comisión de Estructuración | {com_est.get('monto', 0):,.2f} | {com_est.get('porcentaje', 0):.2f}% | `Valor calculado en la operación` |")
    if com_afi.get('monto', 0) > 0:
        lines.append(f"| Comisión de Afiliación | {com_afi.get('monto', 0):,.2f} | {com_afi.get('porcentaje', 0):.2f}% | `Valor calculado en la operación` |")
    
    igv_interes_monto = calculos.get('igv_interes', 0)
    lines.append(f"| IGV sobre Intereses | {igv_interes_monto:,.2f} | {((igv_interes_monto / monto_neto) * 100) if monto_neto else 0:.2f}% | `Intereses * 18%` |")

    igv_com_est_monto = calculos.get('igv_comision_estructuracion', 0)
    lines.append(f"| IGV sobre Com. de Estruct. | {igv_com_est_monto:,.2f} | {((igv_com_est_monto / monto_neto) * 100) if monto_neto else 0:.2f}% | `Comisión * 18%` |")

    if com_afi.get('monto', 0) > 0:
        igv_com_afi_monto = calculos.get('igv_afiliacion', 0)
        lines.append(f"| IGV sobre Com. de Afiliación | {igv_com_afi_monto:,.2f} | {((igv_com_afi_monto / monto_neto) * 100) if monto_neto else 0:.2f}% | `Comisión * 18%` |")

    lines.append("| | | | |")
    lines.append(f"| **Monto a Desembolsar** | **{abono.get('monto', 0):,.2f}** | **{abono.get('porcentaje', 0):.2f}%** | `Capital - Costos Totales` |")
    
    tabla_md = "\n".join(lines)
    st.markdown(tabla_md, unsafe_allow_html=True)


def display_liquidation_details(result: dict, original_data: dict, params: dict):
    """
    Muestra los resultados de la liquidación en un formato de tabla detallado,
    similar al del perfil de la operación.
    """
    st.subheader("Desglose Detallado del Cálculo de Liquidación")

    # Extraer datos clave
    capital_value = original_data.get('capital_calculado')
    capital = float(capital_value) if capital_value is not None else 0.0
    moneda = original_data.get('moneda_factura', 'PEN')
    dias_diferencia = result.get('dias_diferencia', 0)
    
    margen_inicial = result.get('liquidacion_final', {}).get('margen_seguridad_inicial', 0)
    diff_monto = result.get('diferencia_por_monto_recibido', 0)
    cargos = result.get('desglose_cargos', {})
    creditos = result.get('desglose_creditos', {})
    saldo_final = result.get('liquidacion_final', {}).get('saldo_final_a_liquidar', 0)

    tasa_compensatoria_pct = params.get('tasa_compensatoria', 0.0) or 0.0
    tasa_moratoria_pct = params.get('tasa_moratoria', 0.0) or 0.0

    # --- Construir la tabla en Markdown ---
    lines = []
    lines.append(f"| Concepto | Monto ({moneda}) | Detalle del Cálculo |")
    lines.append("| :--- | ---: | :--- |")

    # 1. Saldo Inicial
    lines.append(f"| **Saldo Inicial (Margen de Seguridad)** | **{margen_inicial:,.2f}** | `Dato de la operación original` |")
    lines.append("| | | |")

    # 2. Ajustes y Cargos/Créditos
    lines.append(f"| **Ajustes y Cargos/Créditos** | | |")
    if diff_monto != 0:
        signo_txt = "Diferencia en contra (menor pago)" if diff_monto > 0 else "Diferencia a favor (mayor pago)"
        signo_op = "-" if diff_monto > 0 else "+"
        detalle = f"Monto Esperado: `{original_data.get('monto_neto_factura', 0):,.2f}`<br>Monto Recibido: `{params['monto_recibido']:,.2f}`"
        lines.append(f"| ({signo_op}) {signo_txt} | {abs(diff_monto):,.2f} | {detalle} |")

    # 3. Cargos (Pago Tardío)
    if result.get('tipo_pago') == 'Tardío':
        int_comp = cargos.get('interes_compensatorio', 0)
        igv_int_comp = cargos.get('igv_interes_compensatorio', 0)
        int_mora = cargos.get('interes_moratorio', 0)
        igv_int_mora = cargos.get('igv_interes_moratorio', 0)
        
        detalle_comp = f"Fórmula: `Capital * ((1 + TasaDiaria)^Días - 1)`<br>Capital: `{capital:,.2f}`, Tasa: `{tasa_compensatoria_pct:.2f}%` mensual, Días: `{dias_diferencia}`"
        lines.append(f"| (-) Interés Compensatorio | {int_comp:,.2f} | {detalle_comp} |")
        lines.append(f"| (-) IGV s/ Int. Compensatorio | {igv_int_comp:,.2f} | `Interés Compensatorio * 18%` |")

        if int_mora > 0:
            base_moratorio = capital + int_comp
            detalle_mora = f"Fórmula: `(Capital+Int.Comp) * ((1 + TasaDiaria)^Días - 1)`<br>Base: `{base_moratorio:,.2f}`, Tasa: `{tasa_moratoria_pct:.2f}%` mensual, Días: `{dias_diferencia}`"
            lines.append(f"| (-) Interés Moratorio | {int_mora:,.2f} | {detalle_mora} |")
            lines.append(f"| (-) IGV s/ Int. Moratorio | {igv_int_mora:,.2f} | `Interés Moratorio * 18%` |")

    # 4. Créditos (Pago Anticipado)
    if result.get('tipo_pago') == 'Anticipado':
        int_dev = creditos.get('interes_a_devolver', 0)
        igv_int_dev = creditos.get('igv_interes_a_devolver', 0)
        
        detalle_dev = f"Intereses cobrados en exceso por pago `{abs(dias_diferencia)}` días antes."
        lines.append(f"| (+) Nota de Credito por intereses en exceso | {int_dev:,.2f} | {detalle_dev} |")
        lines.append(f"| (+) Nota de Credito por IGV en exceso | {igv_int_dev:,.2f} | `Intereses en exceso * 18%` |")

    # 5. Saldo Final
    lines.append("| | | |")
    detalle_final = "`Saldo Inicial - Ajustes/Cargos + Créditos`"
    lines.append(f"| **Saldo Final a Liquidar** | **{saldo_final:,.2f}** | {detalle_final} |")

    st.markdown('\n'.join(lines), unsafe_allow_html=True)
    
    with st.expander("Ver JSON completo del resultado (para Debugging)"):
        st.json(result)

# --- Estado de la Sesión ---
if 'proposal_data' not in st.session_state:
    st.session_state.proposal_data = None
if 'liquidation_result' not in st.session_state:
    st.session_state.liquidation_result = None

# --- 1. Búsqueda del Perfil de la Propuesta ---
with st.expander("1. Buscar Operación a Liquidar", expanded=True):
    proposal_id_input = st.text_input(
        "Ingrese el ID de la Propuesta (proposal_id)",
        help="Copie y pegue el ID de la propuesta que desea liquidar desde Supabase.",
        key="proposal_id_input"
    )

    if st.button("Buscar Operación"):
        if proposal_id_input:
            with st.spinner("Buscando operación en Supabase..."):
                from backend.supabase_handler import get_proposal_details_by_id
                data = get_proposal_details_by_id(proposal_id_input)
                if data and not data.get('error'):
                    st.session_state.proposal_data = data
                    st.session_state.liquidation_result = None # Resetear resultado anterior
                    st.success(f"Operación para la factura **{data.get('numero_factura')}** encontrada.")
                else:
                    st.session_state.proposal_data = None
                    st.error(f"No se pudo encontrar la operación. Error: {data.get('error', 'Desconocido')}")
        else:
            st.warning("Por favor, ingrese un ID de propuesta.")

# --- 2. Visualización de Datos y Entradas para Liquidación ---
if st.session_state.proposal_data:
    st.header("2. Datos de la Operación y Parámetros de Liquidación")
    data = st.session_state.proposal_data

    col_perfil, col_inputs = st.columns([0.6, 0.4])

    with col_perfil:
        display_operation_profile(data)

    with col_inputs:
        st.subheader("Inputs para la Liquidación")
        fecha_pago_real = st.date_input("Fecha de Pago Real", value=datetime.now(), format="DD-MM-YYYY")
        monto_neto_factura = data.get('monto_neto_factura')
        monto_recibido_value = float(monto_neto_factura) if monto_neto_factura is not None else 0.0
        monto_recibido = st.number_input("Monto Total Recibido", value=monto_recibido_value)

        interes_mensual = data.get('interes_mensual')
        default_compensatory_rate = float(interes_mensual) if interes_mensual is not None else 0.0
        tasa_compensatoria = st.number_input(
            "Tasa de Interés Compensatorio (% Mensual)", 
            value=default_compensatory_rate,
            help="Por defecto, es la misma tasa de interés de la operación."
        )
        tasa_moratoria = st.number_input("Tasa de Interés Moratorio (% Mensual)", value=1.0)

    # --- 3. Cálculo y Visualización de la Liquidación ---
    if st.button("Calcular Liquidación"):
        st.session_state.last_liquidation_params = {
            "tasa_compensatoria": tasa_compensatoria,
            "tasa_moratoria": tasa_moratoria,
            "monto_recibido": monto_recibido
        }

        payload = {
            "proposal_id": st.session_state.proposal_id_input,
            "monto_recibido": monto_recibido,
            "fecha_pago_real": fecha_pago_real.strftime('%d-%m-%Y'),
            "tasa_interes_compensatorio_pct": tasa_compensatoria,
            "tasa_interes_moratorio_pct": tasa_moratoria
        }
        
        with st.spinner("Contactando al backend para calcular la liquidación..."):
            try:
                response = requests.post(f"{API_BASE_URL}/liquidar_factura", json=payload)
                response.raise_for_status()
                result = response.json()
                st.session_state.liquidation_result = result
            except requests.exceptions.RequestException as e:
                st.error(f"Error de conexión con el backend: {e}")
                st.session_state.liquidation_result = None

if st.session_state.liquidation_result:
    st.header("3. Resultado de la Liquidación")
    result = st.session_state.liquidation_result

    if result.get('error'):
        st.error(f"Error en el cálculo: {result['error']}")
    else:
        st.subheader("Resumen de Liquidación")
        col1, col2, col3 = st.columns(3)
        col1.metric("Estado del Pago", result.get('tipo_pago'))
        col2.metric("Días de Diferencia", result.get('dias_diferencia'))
        col3.metric("Diferencia en Monto Recibido", f"S/ {result.get('diferencia_por_monto_recibido', 0):,.2f}")

        display_liquidation_details(result, st.session_state.proposal_data, st.session_state.last_liquidation_params)
        
        # --- Mostrar Proyección Futura (si existe) ---
        proyeccion_futura = result.get('proyeccion_futura')
        if proyeccion_futura:
            st.subheader("Proyección de Deuda Futura (30 Días)")
            lines = []
            lines.append("| Día | Fecha | Capital Proyectado | Interés Comp. Diario | IGV Comp. Diario | Interés Mora Diario | IGV Mora Diario |")
            lines.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
            for entry in proyeccion_futura:
                lines.append(
                    f"| {entry['dia']} | {entry['fecha']} | {entry['capital_proyectado']:,.2f} | "
                    f"{entry['interes_compensatorio_diario']:,.2f} | {entry['igv_interes_compensatorio_diario']:,.2f} | "
                    f"{entry['interes_moratorio_diario']:,.2f} | {entry['igv_interes_moratorio_diario']:,.2f} |"
                )
            st.markdown("\n".join(lines), unsafe_allow_html=True)
            st.info("Esta proyección muestra el crecimiento diario del 'Nuevo Capital' si no se realiza ningún pago adicional.")

        final = result.get('liquidacion_final', {})
        st.success(f"Saldo Final a Liquidar: S/ {final.get('saldo_final_a_liquidar', 0):,.2f}")
        st.info("Un saldo positivo es a favor del cliente (emisor). Un saldo negativo es a favor de Inandes.")