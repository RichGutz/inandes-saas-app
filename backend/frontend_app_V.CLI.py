import streamlit as st
import requests
import os
import pdf_parser
import datetime
import supabase_handler
import json
import subprocess

# --- Configuración Inicial ---
API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    layout="wide",
    initial_sidebar_state="expanded",
    page_title="Calculadora de Factoring INANDES",
    page_icon="📊",
)

# --- Funciones de Ayuda y Callbacks ---
def update_date_calculations(invoice, changed_field=None):
    try:
        fecha_emision_str = invoice.get('fecha_emision_factura')
        if not fecha_emision_str:
            # If there's no emission date, we can't calculate anything.
            invoice['fecha_pago_calculada'] = ""
            invoice['plazo_credito_dias'] = 0
            invoice['plazo_operacion_calculado'] = 0
            return

        fecha_emision_dt = datetime.datetime.strptime(fecha_emision_str, "%d-%m-%Y")

        # --- Bidirectional Calculation ---
        # If the credit term was the last thing changed by the user
        if changed_field == 'plazo' and invoice.get('plazo_credito_dias', 0) > 0:
            plazo = int(invoice['plazo_credito_dias'])
            fecha_pago_dt = fecha_emision_dt + datetime.timedelta(days=plazo)
            invoice['fecha_pago_calculada'] = fecha_pago_dt.strftime("%d-%m-%Y")
        # If the payment date was the last thing changed by the user
        elif changed_field == 'fecha' and invoice.get('fecha_pago_calculada'):
            fecha_pago_dt = datetime.datetime.strptime(invoice['fecha_pago_calculada'], "%d-%m-%Y")
            if fecha_pago_dt > fecha_emision_dt:
                invoice['plazo_credito_dias'] = (fecha_pago_dt - fecha_emision_dt).days
            else:
                # Avoid negative or zero credit terms if date is before emission
                invoice['plazo_credito_dias'] = 0
        # Default calculation if no specific field was changed (e.g., on initial load)
        elif invoice.get('plazo_credito_dias', 0) > 0:
             plazo = int(invoice['plazo_credito_dias'])
             fecha_pago_dt = fecha_emision_dt + datetime.timedelta(days=plazo)
             invoice['fecha_pago_calculada'] = fecha_pago_dt.strftime("%d-%m-%Y")
        else:
            invoice['fecha_pago_calculada'] = ""
            # invoice['plazo_credito_dias'] is likely already 0 or None

        # --- Plazo de Operación Calculation (remains the same) ---
        if invoice.get('fecha_pago_calculada') and invoice.get('fecha_desembolso_factoring'):
            fecha_pago_dt = datetime.datetime.strptime(invoice['fecha_pago_calculada'], "%d-%m-%Y")
            fecha_desembolso_dt = datetime.datetime.strptime(invoice['fecha_desembolso_factoring'], "%d-%m-%Y")
            invoice['plazo_operacion_calculado'] = (fecha_pago_dt - fecha_desembolso_dt).days if fecha_pago_dt >= fecha_desembolso_dt else 0
        else:
            invoice['plazo_operacion_calculado'] = 0

    except (ValueError, TypeError, AttributeError):
        # Reset fields on any error to ensure a consistent state
        invoice['fecha_pago_calculada'] = ""
        # Keep plazo_credito_dias as is, to avoid overwriting user input on a temporary error
        # invoice['plazo_credito_dias'] = 0
        invoice['plazo_operacion_calculado'] = 0

def validate_inputs(invoice):
    required_fields = {
        "emisor_nombre": "Nombre del Emisor", "emisor_ruc": "RUC del Emisor",
        "aceptante_nombre": "Nombre del Aceptante", "aceptante_ruc": "RUC del Aceptante",
        "numero_factura": "Número de Factura", "moneda_factura": "Moneda de Factura",
        "fecha_emision_factura": "Fecha de Emisión",
        "tasa_de_avance": "Tasa de Avance",
        "interes_mensual": "Interés Mensual",
        "plazo_credito_dias": "Plazo de Crédito (días)", "fecha_desembolso_factoring": "Fecha de Desembolso",
    }
    is_valid = True
    for key, name in required_fields.items():
        if not invoice.get(key):
            is_valid = False
    
    numeric_fields = {
        "monto_total_factura": "Monto Factura Total", "monto_neto_factura": "Monto Factura Neto",
        "tasa_de_avance": "Tasa de Avance", "interes_mensual": "Interés Mensual"
    }
    for key, name in numeric_fields.items():
        if invoice.get(key, 0) <= 0:
            is_valid = False
    return is_valid

def flatten_db_proposal(proposal):
    """
    Flattens the nested JSON from a database proposal to match the structure
    of a session-calculated proposal for PDF generation.
    """
    print(f"--- [DEBUG] flatten_db_proposal: Initial proposal keys: {proposal.keys()} ---")
    print(f"--- [DEBUG] flatten_db_proposal: Initial invoice_net_amount: {proposal.get('invoice_net_amount')} ---")
    print(f"--- [DEBUG] flatten_db_proposal: Initial advance_rate: {proposal.get('advance_rate')} ---")

    recalc_result = proposal.get('recalculate_result', {})

    # --- ROBUSTNESS FIX: Ensure recalc_result is a dictionary ---
    if isinstance(recalc_result, str):
        try:
            recalc_result = json.loads(recalc_result)
            print(f"--- [DEBUG] flatten_db_proposal: Parsed recalc_result from string. ---")
        except json.JSONDecodeError:
            recalc_result = {}
            print(f"--- [DEBUG] flatten_db_proposal: Failed to parse recalc_result string. ---")
    # --- END FIX ---

    desglose = recalc_result.get('desglose_final_detallado', {})
    calculos = recalc_result.get('calculo_con_tasa_encontrada', {})
    busqueda = recalc_result.get('resultado_busqueda', {})
    
    # Add top-level keys that the PDF generator expects
    proposal['advance_amount'] = calculos.get('capital', 0)
    proposal['commission_amount'] = desglose.get('comision_estructuracion', {}).get('monto', 0)
    proposal['interes_calculado'] = desglose.get('interes', {}).get('monto', 0)
    proposal['igv_interes_calculado'] = calculos.get('igv_interes', 0)
    proposal['initial_disbursement'] = desglose.get('abono', {}).get('monto', 0)
    proposal['security_margin'] = desglose.get('margen_seguridad', {}).get('monto', 0)
    
    # Ensure other necessary keys are present, providing defaults if they are missing
    proposal['invoice_issuer_name'] = proposal.get('invoice_issuer_name', 'N/A')
    proposal['invoice_issuer_ruc'] = proposal.get('invoice_issuer_ruc', 'N/A')
    proposal['invoice_acceptor_name'] = proposal.get('invoice_acceptor_name', 'N/A')
    proposal['invoice_payer_name'] = proposal.get('invoice_payer_name', 'N/A')
    proposal['invoice_acceptor_ruc'] = proposal.get('invoice_acceptor_ruc', 'N/A')
    proposal['invoice_number'] = proposal.get('invoice_number', 'N/A')
    proposal['invoice_series_and_number'] = proposal.get('invoice_series_and_number', 'N/A')
    proposal['invoice_total_amount'] = proposal.get('invoice_total_amount', 0)
    # Correctly extract invoice_net_amount from nested structure if not present at top level
    if 'invoice_net_amount' not in proposal or proposal['invoice_net_amount'] == 0:
        proposal['invoice_net_amount'] = recalc_result.get('calculo_con_tasa_encontrada', {}).get('mfn', 0.0)
        print(f"--- [DEBUG] flatten_db_proposal: Updated invoice_net_amount to {proposal['invoice_net_amount']} ---")
    
    # Ensure advance_rate is correctly extracted and scaled
    if 'advance_rate' not in proposal or proposal['advance_rate'] == 0:
        proposal['advance_rate'] = recalc_result.get('resultado_busqueda', {}).get('tasa_avance_encontrada', 0) * 100
        print(f"--- [DEBUG] flatten_db_proposal: Updated advance_rate to {proposal['advance_rate']} ---")

    proposal['invoice_currency'] = proposal.get('invoice_currency', 'PEN')
    proposal['invoice_issue_date'] = proposal.get('invoice_issue_date', 'N/A')
    proposal['credit_term_days'] = proposal.get('credit_term_days', 0)
    proposal['disbursement_date'] = proposal.get('disbursement_date', 'N/A')
    proposal['calculated_payment_date'] = proposal.get('calculated_payment_date', 'N/A')
    proposal['invoice_due_date'] = proposal.get('invoice_due_date', 'N/A')
    proposal['calculated_operation_days'] = proposal.get('calculated_operation_days', 0)
    proposal['financing_term_days'] = proposal.get('financing_term_days', 0)
    proposal['detraccion_percentage'] = proposal.get('detraccion_percentage', 0)
    
    print(f"--- [DEBUG] flatten_db_proposal: Final invoice_net_amount: {proposal.get('invoice_net_amount')} ---")
    print(f"--- [DEBUG] flatten_db_proposal: Final advance_rate: {proposal.get('advance_rate')} ---")
    return proposal

def propagate_commission_changes():
    # This function is called on_change. It will trigger a rerun.
    # On the next run, the UI will be updated based on the new state.
    if st.session_state.get('fijar_condiciones', False) and st.session_state.invoices_data and len(st.session_state.invoices_data) > 1:
        # Get the most recent values directly from the session state of the first invoice's widgets
        # This ensures we are using the value that just changed, before the full rerun.
        first_invoice = st.session_state.invoices_data[0]
        first_invoice['tasa_de_avance'] = st.session_state.get(f"tasa_de_avance_0", first_invoice['tasa_de_avance'])
        first_invoice['interes_mensual'] = st.session_state.get(f"interes_mensual_0", first_invoice['interes_mensual'])
        first_invoice['comision_afiliacion_pen'] = st.session_state.get(f"comision_afiliacion_pen_0", first_invoice['comision_afiliacion_pen'])
        first_invoice['comision_afiliacion_usd'] = st.session_state.get(f"comision_afiliacion_usd_0", first_invoice['comision_afiliacion_usd'])

        # Now that the first invoice's dictionary is up-to-date, propagate its values
        for i in range(1, len(st.session_state.invoices_data)):
            invoice = st.session_state.invoices_data[i]
            invoice['tasa_de_avance'] = first_invoice['tasa_de_avance']
            invoice['interes_mensual'] = first_invoice['interes_mensual']
            invoice['comision_afiliacion_pen'] = first_invoice['comision_afiliacion_pen']
            invoice['comision_afiliacion_usd'] = first_invoice['comision_afiliacion_usd']

def handle_global_payment_date_change():
    if st.session_state.get('aplicar_fecha_vencimiento_global') and st.session_state.get('fecha_vencimiento_global'):
        global_due_date_str = st.session_state.fecha_vencimiento_global.strftime('%d-%m-%Y')
        for invoice in st.session_state.invoices_data:
            invoice['fecha_pago_calculada'] = global_due_date_str
            update_date_calculations(invoice, changed_field='fecha')
        st.toast("Fecha de pago global aplicada a todas las facturas.")

def handle_global_disbursement_date_change():
    if st.session_state.get('aplicar_fecha_desembolso_global') and st.session_state.get('fecha_desembolso_global'):
        global_disbursement_date_str = st.session_state.fecha_desembolso_global.strftime('%d-%m-%Y')
        for invoice in st.session_state.invoices_data:
            invoice['fecha_desembolso_factoring'] = global_disbursement_date_str
            update_date_calculations(invoice)
        st.toast("Fecha de desembolso global aplicada a todas las facturas.")

def handle_global_tasa_avance_change():
    if st.session_state.get('aplicar_tasa_avance_global') and st.session_state.get('tasa_avance_global') is not None:
        global_tasa = st.session_state.tasa_avance_global
        for invoice in st.session_state.invoices_data:
            invoice['tasa_de_avance'] = global_tasa
        st.toast("Tasa de avance global aplicada a todas las facturas.")

def handle_global_interes_mensual_change():
    if st.session_state.get('aplicar_interes_mensual_global') and st.session_state.get('interes_mensual_global') is not None:
        global_interes = st.session_state.interes_mensual_global
        for invoice in st.session_state.invoices_data:
            invoice['interes_mensual'] = global_interes
        st.toast("Interés mensual global aplicado a todas las facturas.")

def handle_global_min_interest_days_change():
    if st.session_state.get('aplicar_dias_interes_minimo_global'):
        global_min_days = st.session_state.dias_interes_minimo_global
        for invoice in st.session_state.invoices_data:
            invoice['dias_minimos_interes_individual'] = global_min_days
        st.toast("Días de interés mínimo global aplicado a todas las facturas.")

# --- Inicialización del Session State ---

# --- Inicialización del Session State ---
if 'invoices_data' not in st.session_state: st.session_state.invoices_data = []
if 'pdf_datos_cargados' not in st.session_state: st.session_state.pdf_datos_cargados = False
if 'last_uploaded_pdf_files_ids' not in st.session_state: st.session_state.last_uploaded_pdf_files_ids = []
if 'last_saved_proposal_id' not in st.session_state: st.session_state.last_saved_proposal_id = ''
if 'anexo_number' not in st.session_state: st.session_state.anexo_number = ''
if 'contract_number' not in st.session_state: st.session_state.contract_number = ''
if 'fijar_condiciones' not in st.session_state: st.session_state.fijar_condiciones = False

# Global settings for affiliation commission
if 'aplicar_comision_afiliacion_global' not in st.session_state: st.session_state.aplicar_comision_afiliacion_global = False
if 'comision_afiliacion_pen_global' not in st.session_state: st.session_state.comision_afiliacion_pen_global = 200.0
if 'comision_afiliacion_usd_global' not in st.session_state: st.session_state.comision_afiliacion_usd_global = 50.0

# Global settings for structuring commission
if 'aplicar_comision_estructuracion_global' not in st.session_state: st.session_state.aplicar_comision_estructuracion_global = False
if 'comision_estructuracion_pct_global' not in st.session_state: st.session_state.comision_estructuracion_pct_global = 0.5
if 'comision_estructuracion_min_pen_global' not in st.session_state: st.session_state.comision_estructuracion_min_pen_global = 200.0
if 'comision_estructuracion_min_usd_global' not in st.session_state: st.session_state.comision_estructuracion_min_usd_global = 50.0


# Global settings for due date
if 'aplicar_fecha_vencimiento_global' not in st.session_state: st.session_state.aplicar_fecha_vencimiento_global = False
if 'fecha_vencimiento_global' not in st.session_state: st.session_state.fecha_vencimiento_global = datetime.date.today()

# Global settings for disbursement date
if 'aplicar_fecha_desembolso_global' not in st.session_state: st.session_state.aplicar_fecha_desembolso_global = False
if 'fecha_desembolso_global' not in st.session_state: st.session_state.fecha_desembolso_global = datetime.date.today()

# Global settings for minimum interest days
if 'aplicar_dias_interes_minimo_global' not in st.session_state: st.session_state.aplicar_dias_interes_minimo_global = False
if 'dias_interes_minimo_global' not in st.session_state: st.session_state.dias_interes_minimo_global = 15


# Default values for new invoices (these will be copied into each invoice's dict)
if 'default_comision_afiliacion_pen' not in st.session_state: st.session_state.default_comision_afiliacion_pen = 200.0
if 'default_comision_afiliacion_usd' not in st.session_state: st.session_state.default_comision_afiliacion_usd = 50.0
if 'default_tasa_de_avance' not in st.session_state: st.session_state.default_tasa_de_avance = 98.0
if 'default_interes_mensual' not in st.session_state: st.session_state.default_interes_mensual = 1.25

# Global settings for rates
if 'aplicar_tasa_avance_global' not in st.session_state: st.session_state.aplicar_tasa_avance_global = False
if 'tasa_avance_global' not in st.session_state: st.session_state.tasa_avance_global = st.session_state.default_tasa_de_avance
if 'aplicar_interes_mensual_global' not in st.session_state: st.session_state.aplicar_interes_mensual_global = False
if 'interes_mensual_global' not in st.session_state: st.session_state.interes_mensual_global = st.session_state.default_interes_mensual

# --- UI: Título y CSS ---
try:
    with open("C:/Users/rguti/Inandes.TECH/.streamlit/style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

# Inject CSS for vertical alignment and right alignment for the last column
st.markdown("""<style>
[data-testid="stHorizontalBlock"] {
    align-items: flex-start; /* Aligns items to the top */
}
/* Target the image within the third column specifically for right alignment */
[data-testid="stHorizontalBlock"] > div:nth-child(3) img {
    margin-left: auto; /* Pushes the image to the right */
}
</style>""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([0.25, 0.5, 0.25])
with col1:
    st.image("C:/Users/rguti/Inandes.TECH/inputs_para_generated_pdfs/logo.geek.png", width=200)
with col2:
    st.markdown("<h2 style='text-align: center; font-size: 2.4em;'>Modulo Operaciones de Factoring</h2>", unsafe_allow_html=True)
with col3:
    st.image("C:/Users/rguti/Inandes.TECH/inputs_para_generated_pdfs/LOGO.png", width=150)

# --- UI: Carga de Archivos ---
with st.expander("", expanded=True):
    col1, col2 = st.columns([1, 0.00001])
    with col1:
        uploaded_pdf_files = st.file_uploader("Seleccionar archivos", type=["pdf"], key="pdf_uploader_main", accept_multiple_files=True)
    with col2:
        pass # Button removed

    if uploaded_pdf_files:
        # Clear previous data if new files are uploaded or file IDs change
        current_file_ids = [f.file_id for f in uploaded_pdf_files]
        if "last_uploaded_pdf_files_ids" not in st.session_state or \
           current_file_ids != st.session_state.last_uploaded_pdf_files_ids:
            st.session_state.invoices_data = []
            st.session_state.last_uploaded_pdf_files_ids = current_file_ids
            st.session_state.pdf_datos_cargados = False # Reset this flag

        if not st.session_state.pdf_datos_cargados: # Process only if not already processed for current files
            for uploaded_file in uploaded_pdf_files:
                temp_file_path = os.path.join("C:/Users/rguti/Inandes.TECH/backend", f"temp_uploaded_pdf_{uploaded_file.file_id}.pdf")
                with open(temp_file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                with st.spinner(f"Procesando {uploaded_file.name} y consultando base de datos..."):
                    try:
                        parsed_data = pdf_parser.extract_fields_from_pdf(temp_file_path)
                        if parsed_data.get("error"):
                            st.error(f"Error al procesar el PDF {uploaded_file.name}: {parsed_data['error']}")
                        else:
                            invoice_entry = {
                                'emisor_ruc': parsed_data.get('emisor_ruc', ''),
                                'aceptante_ruc': parsed_data.get('aceptante_ruc', ''),
                                'fecha_emision_factura': parsed_data.get('fecha_emision', ''),
                                'monto_total_factura': parsed_data.get('monto_total', 0.0),
                                'monto_neto_factura': parsed_data.get('monto_neto', 0.0),
                                'moneda_factura': parsed_data.get('moneda', 'PEN'),
                                'numero_factura': parsed_data.get('invoice_id', ''),
                                'parsed_pdf_name': uploaded_file.name,
                                'file_id': uploaded_file.file_id,
                                'emisor_nombre': '',
                                'aceptante_nombre': '',
                                'plazo_credito_dias': None,
                                'fecha_desembolso_factoring': '',
                                'tasa_de_avance': st.session_state.default_tasa_de_avance,
                                'interes_mensual': st.session_state.default_interes_mensual,
                                'comision_afiliacion_pen': st.session_state.default_comision_afiliacion_pen,
                                'comision_afiliacion_usd': st.session_state.default_comision_afiliacion_usd,
                                'aplicar_comision_afiliacion': False,
                                'detraccion_porcentaje': 0.0, # Will be calculated later
                                'fecha_pago_calculada': '', # Will be calculated later
                                'plazo_operacion_calculado': 0, # Will be calculated later
                                'initial_calc_result': None,
                                'recalculate_result': None,
                                'dias_minimos_interes_individual': 15,
                            }

                            if invoice_entry['emisor_ruc']:
                                invoice_entry['emisor_nombre'] = supabase_handler.get_razon_social_by_ruc(invoice_entry['emisor_ruc'])
                            if invoice_entry['aceptante_ruc']:
                                invoice_entry['aceptante_nombre'] = supabase_handler.get_razon_social_by_ruc(invoice_entry['aceptante_ruc'])
                            
                            st.session_state.invoices_data.append(invoice_entry)
                            st.success(f"Datos de {uploaded_file.name} cargados y enriquecidos. Revisa el formulario.")

                    except Exception as e:
                        st.error(f"Error al parsear el PDF {uploaded_file.name}: {e}")
                    finally:
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
            st.session_state.pdf_datos_cargados = True

    elif "invoices_data" not in st.session_state:
        st.session_state.invoices_data = []
        st.session_state.pdf_datos_cargados = False
        st.session_state.last_uploaded_pdf_files_ids = []

# --- UI: Configuración Global ---
if st.session_state.invoices_data:
    st.markdown("---")
    st.subheader("Configuración Global")

    col1, col2, col3 = st.columns(3)

    # --- COLUMNA 1: COMISIONES ---
    with col1:
        st.write("##### Comisiones Globales")
        st.write("---")
        st.write("**Com. de Estructuración**")
        st.checkbox(
            "Aplicar Comisión de Estructuración", 
            key='aplicar_comision_estructuracion_global',
            help="Si se marca, la comisión de estructuración se calculará sobre el capital total y se dividirá entre todas las facturas cargadas."
        )
        st.number_input(
            "Comisión de Estructuración (%)",
            min_value=0.0,
            value=st.session_state.comision_estructuracion_pct_global,
            key='comision_estructuracion_pct_global',
            format="%.2f",
            disabled=not st.session_state.get('aplicar_comision_estructuracion_global', False)
        )
        st.number_input(
            "Comisión Mínima (PEN)",
            min_value=0.0,
            value=st.session_state.comision_estructuracion_min_pen_global,
            key='comision_estructuracion_min_pen_global',
            format="%.2f",
            disabled=not st.session_state.get('aplicar_comision_estructuracion_global', False)
        )
        st.number_input(
            "Comisión Mínima (USD)",
            min_value=0.0,
            value=st.session_state.comision_estructuracion_min_usd_global,
            key='comision_estructuracion_min_usd_global',
            format="%.2f",
            disabled=not st.session_state.get('aplicar_comision_estructuracion_global', False)
        )
        
        st.write("**Com. de Afiliación**")
        st.checkbox(
            "Aplicar Comisión de Afiliación", 
            key='aplicar_comision_afiliacion_global',
            help="Si se marca, la comisión de afiliación se dividirá entre todas las facturas cargadas."
        )
        st.number_input(
            "Monto Comisión Afiliación (PEN)",
            min_value=0.0,
            value=st.session_state.comision_afiliacion_pen_global,
            key='comision_afiliacion_pen_global',
            format="%.2f",
            disabled=not st.session_state.get('aplicar_comision_afiliacion_global', False)
        )
        st.number_input(
            "Monto Comisión Afiliación (USD)",
            min_value=0.0,
            value=st.session_state.comision_afiliacion_usd_global,
            key='comision_afiliacion_usd_global',
            format="%.2f",
            disabled=not st.session_state.get('aplicar_comision_afiliacion_global', False)
        )

    # --- COLUMNA 2: TASAS ---
    with col2:
        st.write("##### Tasas Globales")
        st.write("---")
        st.checkbox(
            "Aplicar Tasa de Avance Global",
            key='aplicar_tasa_avance_global',
            help="Si se marca, la tasa de avance se aplicará a todas las facturas.",
            on_change=handle_global_tasa_avance_change
        )
        st.number_input(
            "Tasa de Avance Global (%)",
            key='tasa_avance_global',
            min_value=0.0,
            format="%.2f",
            disabled=not st.session_state.get('aplicar_tasa_avance_global', False),
            on_change=handle_global_tasa_avance_change
        )
        st.checkbox(
            "Aplicar Interés Mensual Global",
            key='aplicar_interes_mensual_global',
            help="Si se marca, el interés mensual se aplicará a todas las facturas.",
            on_change=handle_global_interes_mensual_change
        )
        st.number_input(
            "Interés Mensual Global (%)",
            key='interes_mensual_global',
            min_value=0.0,
            format="%.2f",
            disabled=not st.session_state.get('aplicar_interes_mensual_global', False),
            on_change=handle_global_interes_mensual_change
        )

    # --- COLUMNA 3: FECHAS GLOBALES ---
    with col3:
        st.write("##### Fechas Globales")
        st.write("---")
        st.checkbox(
            "Aplicar Fecha de Pago Global",
            key='aplicar_fecha_vencimiento_global',
            help="Si se marca, la fecha de pago seleccionada se aplicará a todas las facturas.",
            on_change=handle_global_payment_date_change
        )
        st.date_input(
            "Fecha de Pago Global",
            key='fecha_vencimiento_global',
            format="DD-MM-YYYY",
            disabled=not st.session_state.get('aplicar_fecha_vencimiento_global', False),
            on_change=handle_global_payment_date_change
        )
        st.checkbox(
            "Aplicar Fecha de Desembolso Global",
            key='aplicar_fecha_desembolso_global',
            help="Si se marca, la fecha de desembolso seleccionada se aplicará a todas las facturas.",
            on_change=handle_global_disbursement_date_change
        )
        st.date_input(
            "Fecha de Desembolso Global",
            key='fecha_desembolso_global',
            format="DD-MM-YYYY",
            disabled=not st.session_state.get('aplicar_fecha_desembolso_global', False),
            on_change=handle_global_disbursement_date_change
        )

        st.write("**Días Mínimos de Interés**")
        st.checkbox("Aplicar Días Mínimos", key='aplicar_dias_interes_minimo_global', on_change=handle_global_min_interest_days_change)
        st.number_input("Valor Días Mínimos", key='dias_interes_minimo_global', min_value=0, step=1, on_change=handle_global_min_interest_days_change)


    # --- Cálculo Global ---
    st.write("##### Cálculo Global de Todas las Facturas")
    if st.button("Calcular Todas las Facturas", key="calculate_all_invoices"):
        # 1. Validate all invoices first
        all_valid = True
        for idx, invoice in enumerate(st.session_state.invoices_data):
            if not validate_inputs(invoice):
                st.error(f"La Factura {idx + 1} ({invoice.get('parsed_pdf_name', 'N/A')}) tiene campos incompletos o inválidos.")
                all_valid = False
        
        if not all_valid:
            st.warning("No se pueden calcular todas las facturas. Por favor, revisa los errores mencionados arriba.")
        else:
            # 2. If all are valid, proceed with calculation for each
            st.success("Todas las facturas son válidas. Iniciando cálculos...")
            for idx, invoice in enumerate(st.session_state.invoices_data):
                with st.spinner(f"Calculando Factura {idx + 1}/{len(st.session_state.invoices_data)}..."):
                    num_invoices = len(st.session_state.invoices_data)
                    
                    # --- Lógica de Prorrateo ---
                    comision_pen_apportioned = st.session_state.get('comision_afiliacion_pen_global', 0.0) / num_invoices if num_invoices > 0 else 0
                    comision_usd_apportioned = st.session_state.get('comision_afiliacion_usd_global', 0.0) / num_invoices if num_invoices > 0 else 0
                    comision_estructuracion_pct = st.session_state.comision_estructuracion_pct_global
                    comision_min_pen_apportioned_struct = st.session_state.comision_estructuracion_min_pen_global / num_invoices if num_invoices > 0 else 0
                    comision_min_usd_apportioned_struct = st.session_state.comision_estructuracion_min_usd_global / num_invoices if num_invoices > 0 else 0

                    # --- Lógica de Selección de Moneda (NUEVO) ---
                    if invoice['moneda_factura'] == 'USD':
                        comision_minima_aplicable = comision_min_usd_apportioned_struct
                        comision_afiliacion_aplicable = comision_usd_apportioned
                    else: # Default to PEN
                        comision_minima_aplicable = comision_min_pen_apportioned_struct
                        comision_afiliacion_aplicable = comision_pen_apportioned

                    # --- Determinación del Plazo para la API (Lógica Actualizada) ---
                    plazo_real = invoice.get('plazo_operacion_calculado', 0)
                    plazo_para_api = plazo_real
                    if st.session_state.get('aplicar_dias_interes_minimo_global', False):
                        dias_minimos_a_usar = invoice.get('dias_minimos_interes_individual', 15)
                        plazo_para_api = max(plazo_real, dias_minimos_a_usar)

                    # --- Payload para /calcular_desembolso (ACTUALIZADO) ---
                    api_data = {
                        "plazo_operacion": plazo_para_api,
                        "mfn": invoice['monto_neto_factura'],
                        "tasa_avance": invoice['tasa_de_avance'] / 100,
                        "interes_mensual": invoice['interes_mensual'] / 100,
                        "comision_estructuracion_pct": comision_estructuracion_pct / 100,
                        "comision_minima_aplicable": comision_minima_aplicable,
                        "igv_pct": 0.18,
                        "comision_afiliacion_aplicable": comision_afiliacion_aplicable,
                        "aplicar_comision_afiliacion": st.session_state.get('aplicar_comision_afiliacion_global', False)
                    }
                    try:
                        response = requests.post(f"{API_BASE_URL}/calcular_desembolso", json=api_data)
                        response.raise_for_status()
                        invoice['initial_calc_result'] = response.json()

                        if invoice['initial_calc_result'] and 'abono_real_teorico' in invoice['initial_calc_result']:
                            abono_real_teorico = invoice['initial_calc_result']['abono_real_teorico']
                            monto_desembolsar_objetivo = (abono_real_teorico // 10) * 10

                            # --- Payload para /encontrar_tasa (ACTUALIZADO) ---
                            api_data_recalculate = {
                                "plazo_operacion": plazo_para_api,
                                "mfn": invoice['monto_neto_factura'],
                                "interes_mensual": invoice['interes_mensual'] / 100,
                                "comision_estructuracion_pct": comision_estructuracion_pct / 100,
                                "igv_pct": 0.18,
                                "monto_objetivo": monto_desembolsar_objetivo,
                                "comision_minima_aplicable": comision_minima_aplicable,
                                "comision_afiliacion_aplicable": comision_afiliacion_aplicable,
                                "aplicar_comision_afiliacion": st.session_state.get('aplicar_comision_afiliacion_global', False)
                            }
                            response_recalculate = requests.post(f"{API_BASE_URL}/encontrar_tasa", json=api_data_recalculate)
                            response_recalculate.raise_for_status()
                            invoice['recalculate_result'] = response_recalculate.json()
                        else:
                            invoice['recalculate_result'] = None
                    except requests.exceptions.RequestException as e:
                        st.error(f"Error de conexión con la API para Factura {idx + 1}: {e}")
                        break 
            st.success("¡Cálculo de todas las facturas completado!")


# --- UI: Formulario Principal ---
if st.session_state.invoices_data:
    for idx, invoice in enumerate(st.session_state.invoices_data):
        st.markdown("--- ")
        st.write(f"### Factura {idx + 1}: {invoice.get('parsed_pdf_name', 'N/A')}")

        # --- UI: Formulario Principal (adaptado para múltiples facturas) ---
        # Involucrados
        with st.container():
            st.write("##### Involucrados")
            col_emisor_nombre, col_emisor_ruc, col_aceptante_nombre, col_aceptante_ruc = st.columns(4)
            with col_emisor_nombre:
                invoice['emisor_nombre'] = st.text_input(" NOMBRE DEL EMISOR", value=invoice.get('emisor_nombre', ''), key=f"emisor_nombre_{idx}", label_visibility="visible")
            with col_emisor_ruc:
                invoice['emisor_ruc'] = st.text_input("RUC DEL EMISOR", value=invoice.get('emisor_ruc', ''), key=f"emisor_ruc_{idx}", label_visibility="visible")
            with col_aceptante_nombre:
                invoice['aceptante_nombre'] = st.text_input("NOMBRE DEL ACEPTANTE", value=invoice.get('aceptante_nombre', ''), key=f"aceptante_nombre_{idx}", label_visibility="visible")
            with col_aceptante_ruc:
                invoice['aceptante_ruc'] = st.text_input("RUC DEL ACEPTANTE", value=invoice.get('aceptante_ruc', ''), key=f"aceptante_ruc_{idx}", label_visibility="visible")

        # Montos y Moneda
        with st.container():
            st.write("##### Montos y Moneda")
            col_num_factura, col_monto_total, col_monto_neto, col_moneda, col_detraccion = st.columns(5)
            with col_num_factura:
                invoice['numero_factura'] = st.text_input("NÚMERO DE FACTURA", value=invoice.get('numero_factura', ''), key=f"numero_factura_{idx}", label_visibility="visible")
            with col_monto_total:
                invoice['monto_total_factura'] = st.number_input("MONTO FACTURA TOTAL (CON IGV)", min_value=0.0, value=invoice.get('monto_total_factura', 0.0), format="%.2f", key=f"monto_total_factura_{idx}", label_visibility="visible")
            with col_monto_neto:
                invoice['monto_neto_factura'] = st.number_input("MONTO FACTURA NETO", min_value=0.0, value=invoice.get('monto_neto_factura', 0.0), format="%.2f", key=f"monto_neto_factura_{idx}", label_visibility="visible")
            with col_moneda:
                invoice['moneda_factura'] = st.selectbox("MONEDA DE FACTURA", ["PEN", "USD"], index=["PEN", "USD"].index(invoice.get('moneda_factura', 'PEN')), key=f"moneda_factura_{idx}", label_visibility="visible")
            with col_detraccion:
                detraccion_retencion_pct = 0.0
                if invoice.get('monto_total_factura', 0) > 0:
                    detraccion_retencion_pct = ((invoice['monto_total_factura'] - invoice['monto_neto_factura']) / invoice['monto_total_factura']) * 100
                invoice['detraccion_porcentaje'] = detraccion_retencion_pct
                st.text_input("Detracción / Retención (%)", value=f"{detraccion_retencion_pct:.2f}%", disabled=True, key=f"detraccion_porcentaje_{idx}", label_visibility="visible")

        # Fechas y Plazos
        with st.container():
            st.write("##### Fechas y Plazos")

            # Helper to parse date string to date object, returns None on failure
            def to_date_obj(date_str):
                if not date_str or not isinstance(date_str, str): return None
                try:
                    return datetime.datetime.strptime(date_str, '%d-%m-%Y').date()
                except (ValueError, TypeError):
                    return None

            col_fecha_emision, col_plazo_credito, col_fecha_pago, col_fecha_desembolso, col_plazo_operacion, col_dias_minimos = st.columns(6)

            with col_fecha_emision:
                fecha_emision_obj = to_date_obj(invoice.get('fecha_emision_factura'))
                
                # Disable the input if a date was successfully parsed from the PDF
                is_disabled = bool(fecha_emision_obj)

                nueva_fecha_emision_obj = st.date_input(
                    "Fecha de Emisión",
                    value=fecha_emision_obj,
                    key=f"fecha_emision_factura_{idx}",
                    format="DD-MM-YYYY",
                    disabled=is_disabled
                )

                # If the field is enabled (i.e., not parsed from PDF), update the session state with the user's input
                if not is_disabled:
                    if nueva_fecha_emision_obj:
                        invoice['fecha_emision_factura'] = nueva_fecha_emision_obj.strftime('%d-%m-%Y')
                    else:
                        # If the user clears the date, set it to an empty string
                        invoice['fecha_emision_factura'] = ''

            # --- Callbacks for bidirectional updates ---
            def plazo_changed(idx):
                new_plazo = st.session_state.get(f"plazo_credito_dias_{idx}")
                st.session_state.invoices_data[idx]['plazo_credito_dias'] = new_plazo
                update_date_calculations(st.session_state.invoices_data[idx], changed_field='plazo')

            def fecha_pago_changed(idx):
                new_date_obj = st.session_state.get(f"fecha_pago_calculada_{idx}")
                if new_date_obj:
                    st.session_state.invoices_data[idx]['fecha_pago_calculada'] = new_date_obj.strftime('%d-%m-%Y')
                else:
                    st.session_state.invoices_data[idx]['fecha_pago_calculada'] = ''
                update_date_calculations(st.session_state.invoices_data[idx], changed_field='fecha')

            def fecha_desembolso_changed(idx):
                new_date_obj = st.session_state.get(f"fecha_desembolso_factoring_{idx}")
                if new_date_obj:
                    st.session_state.invoices_data[idx]['fecha_desembolso_factoring'] = new_date_obj.strftime('%d-%m-%Y')
                else:
                    st.session_state.invoices_data[idx]['fecha_desembolso_factoring'] = ''
                update_date_calculations(st.session_state.invoices_data[idx])

            with col_plazo_credito:
                plazo_value = invoice.get('plazo_credito_dias')
                display_value = int(plazo_value) if plazo_value is not None else 0
                st.number_input(
                    "Plazo de Crédito (días)",
                    min_value=0,
                    step=1,
                    value=display_value,
                    key=f"plazo_credito_dias_{idx}",
                    on_change=plazo_changed,
                    args=(idx,)
                )

            with col_fecha_pago:
                fecha_pago_obj = to_date_obj(invoice.get('fecha_pago_calculada'))
                st.date_input(
                    "Fecha de Pago",
                    value=fecha_pago_obj,
                    key=f"fecha_pago_calculada_{idx}",
                    format="DD-MM-YYYY",
                    on_change=fecha_pago_changed,
                    args=(idx,)
                )

            with col_fecha_desembolso:
                fecha_desembolso_obj = to_date_obj(invoice.get('fecha_desembolso_factoring'))
                st.date_input(
                    "Fecha de Desembolso",
                    value=fecha_desembolso_obj,
                    key=f"fecha_desembolso_factoring_{idx}",
                    format="DD-MM-YYYY",
                    on_change=fecha_desembolso_changed,
                    args=(idx,)
                )

            with col_plazo_operacion:
                st.number_input("Plazo de Operación (días)", value=invoice.get('plazo_operacion_calculado', 0), disabled=True, key=f"plazo_operacion_calculado_{idx}", label_visibility="visible")
            
            with col_dias_minimos:
                invoice['dias_minimos_interes_individual'] = st.number_input("Días Mín. Interés", value=invoice.get('dias_minimos_interes_individual', 15), min_value=0, step=1, key=f"dias_minimos_interes_individual_{idx}")

        # Tasas y Comisiones
        with st.container():
            st.write("##### Tasas y Comisiones")
            st.write("") # Empty row for spacing

            # Determine if fields should be disabled (i.e., if it's not the first invoice and conditions are fixed)
            is_disabled = idx > 0 and st.session_state.fijar_condiciones

            col_tasa_avance, col_interes_mensual = st.columns(2)
            with col_tasa_avance:
                invoice['tasa_de_avance'] = st.number_input("Tasa de Avance (%)", min_value=0.0, value=invoice.get('tasa_de_avance', st.session_state.default_tasa_de_avance), format="%.2f", key=f"tasa_de_avance_{idx}", label_visibility="visible", on_change=propagate_commission_changes, disabled=is_disabled)
            with col_interes_mensual:
                invoice['interes_mensual'] = st.number_input("Interés Mensual (%)", min_value=0.0, value=invoice.get('interes_mensual', st.session_state.default_interes_mensual), format="%.2f", key=f"interes_mensual_{idx}", label_visibility="visible", on_change=propagate_commission_changes, disabled=is_disabled)
            

        

        st.markdown("--- ")

        # --- Pasos de Cálculo y Acción (adaptado para múltiples facturas) ---
        col_resultados, = st.columns(1)

        with col_resultados:
            # CSS para reducir el tamaño de la fuente de los labels en los resultados iterativos
            st.markdown("""
            <style>
            /* Reduce font size for the 'Calcular' button */
            .stButton>button {
                font-size: 0.8em; /* Adjust as needed */
                padding: 0.25em 0.5em; /* Adjust padding to fit text */
            }
            label {
                font-size: 0.1em !important; /* Reducido al mínimo para prueba */
            }
            </style>
            """, unsafe_allow_html=True)

            if invoice.get('recalculate_result'):
                st.write("##### Perfil de la Operación")
                st.markdown(
                    f"**Emisor:** {invoice.get('emisor_nombre', 'N/A')} | "
                    f"**Aceptante:** {invoice.get('aceptante_nombre', 'N/A')} | "
                    f"**Factura:** {invoice.get('numero_factura', 'N/A')} | "
                    f"**F. Emisión:** {invoice.get('fecha_emision_factura', 'N/A')} | "
                    f"**F. Pago:** {invoice.get('fecha_pago_calculada', 'N/A')} | "
                    f"**Monto Total:** {invoice.get('moneda_factura', '')} {invoice.get('monto_total_factura', 0):,.2f} | "
                    f"**Monto Neto:** {invoice.get('moneda_factura', '')} {invoice.get('monto_neto_factura', 0):,.2f}"
                )
                recalc_result = invoice['recalculate_result']
                desglose = recalc_result.get('desglose_final_detallado', {})
                calculos = recalc_result.get('calculo_con_tasa_encontrada', {})
                busqueda = recalc_result.get('resultado_busqueda', {})
                moneda = invoice.get('moneda_factura', 'PEN')

                # --- Preparar todos los datos necesarios ---
                tasa_avance_pct = busqueda.get('tasa_avance_encontrada', 0) * 100
                monto_neto = invoice.get('monto_neto_factura', 0)
                capital = calculos.get('capital', 0)
                
                abono = desglose.get('abono', {})
                interes = desglose.get('interes', {})
                com_est = desglose.get('comision_estructuracion', {})
                com_afi = desglose.get('comision_afiliacion', {})
                igv = desglose.get('igv_total', {})
                margen = desglose.get('margen_seguridad', {})

                costos_totales = interes.get('monto', 0) + com_est.get('monto', 0) + com_afi.get('monto', 0) + igv.get('monto', 0)
                tasa_diaria_pct = (invoice.get('interes_mensual', 0) / 30) 

                # --- Construir la tabla en Markdown línea por línea para evitar errores de formato ---
                lines = []
                lines.append(f"| Item | Monto ({moneda}) | % sobre Neto | Fórmula de Cálculo | Detalle del Cálculo |")
                lines.append("| :--- | :--- | :--- | :--- | :--- |")
                
                # --- Nuevas Filas ---
                monto_total = invoice.get('monto_total_factura', 0)
                detraccion_monto = monto_total - monto_neto
                detraccion_pct = invoice.get('detraccion_porcentaje', 0)
                
                lines.append(f"| Monto Total de Factura | {monto_total:,.2f} | | `Dato de entrada` | Monto original de la factura con IGV |")
                lines.append(f"| Detracción / Retención | {detraccion_monto:,.2f} | {detraccion_pct:.2f}% | `Monto Total - Monto Neto` | `{monto_total:,.2f} - {monto_neto:,.2f} = {detraccion_monto:,.2f}` |")
                # --- Fin Nuevas Filas ---

                lines.append(f"| Monto Neto de Factura | {monto_neto:,.2f} | 100.00% | `Dato de entrada` | Monto a financiar (después de detracciones/retenciones) |")
                lines.append(f"| Tasa de Avance Aplicada | N/A | {tasa_avance_pct:.2f}% | `Tasa final de la operación` | N/A |")
                lines.append(f"| Margen de Seguridad | {margen.get('monto', 0):,.2f} | {margen.get('porcentaje', 0):.2f}% | `Monto Neto - Capital` | `{monto_neto:,.2f} - {capital:,.2f} = {margen.get('monto', 0):,.2f}` |")
                lines.append(f"| Capital | {capital:,.2f} | {((capital / monto_neto) * 100) if monto_neto else 0:.2f}% | `Monto Neto * (Tasa de Avance / 100)` | `{monto_neto:,.2f} * ({tasa_avance_pct:.2f} / 100) = {capital:,.2f}` |")
                lines.append(f"| Intereses | {interes.get('monto', 0):,.2f} | {interes.get('porcentaje', 0):.2f}% | `Capital * ((1 + Tasa Diaria)^Plazo - 1)` | Tasa Diaria: `{invoice.get('interes_mensual', 0):.2f}% / 30 = {tasa_diaria_pct:.4f}%`, Plazo: `{calculos.get('plazo_operacion', 0)} días`. Cálculo: `{capital:,.2f} * ((1 + {tasa_diaria_pct/100:.6f})^{calculos.get('plazo_operacion', 0)} - 1) = {interes.get('monto', 0):,.2f}` |")
                lines.append(f"| Comisión de Estructuración | {com_est.get('monto', 0):,.2f} | {com_est.get('porcentaje', 0):.2f}% | `MAX(Capital * %Comisión, Mínima Prorrateada)` | Base: `{capital:,.2f} * ({st.session_state.comision_estructuracion_pct_global:.2f} / 100) = {capital * (st.session_state.comision_estructuracion_pct_global/100):.2f}`, Mín Prorrateado: `{(st.session_state.comision_estructuracion_min_pen_global / len(st.session_state.invoices_data)) if moneda == 'PEN' else (st.session_state.comision_estructuracion_min_usd_global / len(st.session_state.invoices_data)):.2f}`. Resultado: `{com_est.get('monto', 0):,.2f}` |")
                if com_afi.get('monto', 0) > 0:
                    lines.append(f"| Comisión de Afiliación | {com_afi.get('monto', 0):,.2f} | {com_afi.get('porcentaje', 0):.2f}% | `Valor Fijo (si aplica)` | Monto fijo para la moneda {moneda}. |")
                
                igv_interes_monto = calculos.get('igv_interes', 0)
                igv_interes_pct = (igv_interes_monto / monto_neto * 100) if monto_neto else 0
                lines.append(f"| IGV sobre Intereses | {igv_interes_monto:,.2f} | {igv_interes_pct:.2f}% | `Intereses * 18%` | `{interes.get('monto', 0):,.2f} * 18% = {igv_interes_monto:,.2f}` |")

                igv_com_est_monto = calculos.get('igv_comision_estructuracion', 0)
                igv_com_est_pct = (igv_com_est_monto / monto_neto * 100) if monto_neto else 0
                lines.append(f"| IGV sobre Com. de Estruct. | {igv_com_est_monto:,.2f} | {igv_com_est_pct:.2f}% | `Comisión * 18%` | `{com_est.get('monto', 0):,.2f} * 18% = {igv_com_est_monto:,.2f}` |")

                if com_afi.get('monto', 0) > 0:
                    igv_com_afi_monto = calculos.get('igv_afiliacion', 0)
                    igv_com_afi_pct = (igv_com_afi_monto / monto_neto * 100) if monto_neto else 0
                    lines.append(f"| IGV sobre Com. de Afiliación | {igv_com_afi_monto:,.2f} | {igv_com_afi_pct:.2f}% | `Comisión * 18%` | `{com_afi.get('monto', 0):,.2f} * 18% = {igv_com_afi_monto:,.2f}` |")

                lines.append("| | | | | |")
                lines.append(f"| **Monto a Desembolsar** | **{abono.get('monto', 0):,.2f}** | **{abono.get('porcentaje', 0):.2f}%** | `Capital - Costos Totales` | `{capital:,.2f} - {costos_totales:,.2f} = {abono.get('monto', 0):,.2f}` |")
                lines.append("| | | | | |")
                lines.append(f"| **Total (Monto Neto Factura)** | **{monto_neto:,.2f}** | **100.00%** | `Abono + Costos + Margen` | `{abono.get('monto', 0):,.2f} + {costos_totales:,.2f} + {margen.get('monto', 0):,.2f} = {monto_neto:,.2f}` |")
                
                tabla_md = "\n".join(lines)
                st.markdown(tabla_md, unsafe_allow_html=True)

        st.markdown("--- ") # Separador después del botón


# --- Pasos 3 y 4: Grabar e Imprimir ---


# Creación de la estructura de dos columnas
col_paso3, col_consulta = st.columns(2)

with col_paso3:
    st.write("#### Grabar Propuesta")
    st.write("##### 1. Ingresar Datos de Contrato")

    # Inputs apilados verticalmente como se solicitó
    st.session_state.anexo_number = st.text_input("Número de Anexo", value=st.session_state.anexo_number, key="anexo_number_global")
    st.session_state.contract_number = st.text_input("Número de Contrato", value=st.session_state.contract_number, key="contract_number_global")

    # --- Lógica de habilitación del botón ---
    # 1. Debe haber al menos un resultado de recálculo en cualquiera de las facturas.
    has_recalc_result = any(invoice.get('recalculate_result') for invoice in st.session_state.invoices_data)
    
    # 2. Los campos de anexo y contrato no deben estar vacíos.
    contract_fields_filled = bool(st.session_state.anexo_number) and bool(st.session_state.contract_number)

    # El botón está habilitado solo si ambas condiciones son verdaderas.
    can_save_proposal = has_recalc_result and contract_fields_filled

    if st.button("GRABAR Propuesta en Base de Datos", disabled=not can_save_proposal):
        if can_save_proposal:
            for idx, invoice in enumerate(st.session_state.invoices_data):
                if invoice.get('recalculate_result'):
                    with st.spinner(f"Guardando propuesta para Factura {idx + 1}..."):
                        # Obtener los valores de los inputs
                        anexo_number_str = st.session_state.anexo_number
                        contract_number_str = st.session_state.contract_number

                        # Convertir a entero o None si está vacío
                        anexo_number_int = int(anexo_number_str) if anexo_number_str else None
                        contract_number_int = int(contract_number_str) if contract_number_str else None
                        
                        temp_session_data = {
                            'emisor_nombre': invoice.get('emisor_nombre'),
                            'emisor_ruc': invoice.get('emisor_ruc'),
                            'aceptante_nombre': invoice.get('aceptante_nombre'),
                            'aceptante_ruc': invoice.get('aceptante_ruc'),
                            'numero_factura': invoice.get('numero_factura'),
                            'monto_total_factura': invoice.get('monto_total_factura'),
                            'monto_neto_factura': invoice.get('monto_neto_factura'),
                            'moneda_factura': invoice.get('moneda_factura'),
                            'fecha_emision_factura': invoice.get('fecha_emision_factura'),
                            'plazo_credito_dias': invoice.get('plazo_credito_dias'),
                            'fecha_desembolso_factoring': invoice.get('fecha_desembolso_factoring'),
                            'tasa_de_avance': invoice.get('tasa_de_avance'),
                            'interes_mensual': invoice.get('interes_mensual'),
                            'comision_de_estructuracion': invoice.get('comision_de_estructuracion'),
                            'comision_minima_pen': invoice.get('comision_minima_pen'),
                            'comision_minima_usd': invoice.get('comision_minima_usd'),
                            'comision_afiliacion_pen': invoice.get('comision_afiliacion_pen'),
                            'comision_afiliacion_usd': invoice.get('comision_afiliacion_usd'),
                            'aplicar_comision_afiliacion': invoice.get('aplicar_comision_afiliacion'),
                            'detraccion_porcentaje': invoice.get('detraccion_porcentaje'),
                            'fecha_pago_calculada': invoice.get('fecha_pago_calculada'),
                            'plazo_operacion_calculado': invoice.get('plazo_operacion_calculado'),
                            'initial_calc_result': invoice.get('initial_calc_result'),
                            'recalculate_result': invoice.get('recalculate_result'),
                            'anexo_number': anexo_number_int,
                            'contract_number': contract_number_int,
                        }
                        success, message = supabase_handler.save_proposal(temp_session_data)
                        if success:
                            st.success(message)
                            if "Propuesta con ID" in message:
                                start_index = message.find("ID ") + 3
                                end_index = message.find(" guardada")
                                newly_saved_id = message[start_index:end_index]
                                st.session_state.last_saved_proposal_id = newly_saved_id

                                # --- MEJORA: Añadir automáticamente a la lista de impresión ---
                                if 'accumulated_proposals' not in st.session_state:
                                    st.session_state.accumulated_proposals = []
                                
                                full_proposal_details = supabase_handler.get_proposal_details_by_id(newly_saved_id)
                                if full_proposal_details and 'proposal_id' in full_proposal_details:
                                    if not any(p.get('proposal_id') == newly_saved_id for p in st.session_state.accumulated_proposals):
                                        st.session_state.accumulated_proposals.append(full_proposal_details)
                                        st.success(f"Propuesta {newly_saved_id} añadida a la lista de impresión.")
                                # --- FIN MEJORA ---
                        else:
                            st.error(message)
        else:
            st.warning("No hay resultados de cálculo para guardar.")

    # Container for the print buttons
    can_print_profiles = any(invoice.get('recalculate_result') for invoice in st.session_state.invoices_data)
    
    if st.button("Imprimir Perfiles (PDF con Jinja2)", disabled=not can_print_profiles):
            if can_print_profiles:
                st.write("Generando PDF consolidado de perfiles con Jinja2...")
                
                invoices_to_print = []
                num_invoices_for_pdf = len([inv for inv in st.session_state.invoices_data if inv.get('recalculate_result')])
                for invoice in st.session_state.invoices_data:
                    if invoice.get('recalculate_result'):
                        # Add the new data point for the template
                        invoice['detraccion_monto'] = invoice.get('monto_total_factura', 0) - invoice.get('monto_neto_factura', 0)
                        # Add global commission data to each invoice for the template
                        invoice['comision_de_estructuracion_global'] = st.session_state.comision_estructuracion_pct_global
                        invoice['comision_minima_pen_global'] = st.session_state.comision_estructuracion_min_pen_global
                        invoice['comision_minima_usd_global'] = st.session_state.comision_estructuracion_min_usd_global
                        invoice['num_invoices'] = num_invoices_for_pdf
                        invoices_to_print.append(invoice)

                if invoices_to_print:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_filename = f"perfiles_consolidados_{timestamp}.pdf"
                    output_filepath = os.path.join("C:/Users/rguti/Inandes.TECH/generated_pdfs", output_filename)

                    temp_dir = "C:/Users/rguti/Inandes.TECH/backend/temp_files"
                    if not os.path.exists(temp_dir):
                        os.makedirs(temp_dir)
                    
                    temp_json_path = os.path.join(temp_dir, f"perfiles_data_{timestamp}.json")
                    with open(temp_json_path, 'w', encoding='utf-8') as f:
                        json.dump(invoices_to_print, f, ensure_ascii=False, indent=4)

                    print_date = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")

                    command = [
                        "python", "C:/Users/rguti/Inandes.TECH/backend/html_generator_for_perfil.py",
                        f"--output_filepath={output_filepath}",
                        f"--data_file={temp_json_path}",
                        f"--print_date={print_date}"
                    ]
                    try:
                        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
                        if result.stderr:
                            st.warning(f"Advertencias/Errores del generador de PDF: {result.stderr}")
                        
                        if os.path.exists(output_filepath):
                            st.success(f"PDF consolidado generado: {output_filename}")
                            with open(output_filepath, "rb") as file:
                                st.download_button(
                                    label=f"Descargar {output_filename}",
                                    data=file.read(),
                                    file_name=output_filename,
                                    mime="application/pdf",
                                    key=f"download_{output_filename}"
                                )
                            os.remove(output_filepath)
                        else:
                            st.error(f"Error: El PDF consolidado no se generó correctamente. Salida: {result.stdout}")

                    except subprocess.CalledProcessError as e:
                        st.error(f"Error al generar el PDF consolidado: {e}\nSalida del error: {e.stderr}")
                    except FileNotFoundError:
                        st.error("Error: El script html_generator_for_perfil.py no fue encontrado.")
                    finally:
                        if os.path.exists(temp_json_path):
                            os.remove(temp_json_path)
                else:
                    st.warning("No hay perfiles calculados para imprimir.")
            else:
                st.warning("No hay resultados de cálculo para generar perfiles.")

    # New button for EFIDE report
    if st.button("Generar Reporte EFIDE (PDF)", disabled=not can_print_profiles):
        if can_print_profiles:
            st.write("Generando Reporte EFIDE...")
            
            invoices_to_print = []
            num_invoices_for_pdf = len([inv for inv in st.session_state.invoices_data if inv.get('recalculate_result')])
            for invoice in st.session_state.invoices_data:
                if invoice.get('recalculate_result'):
                    # Ensure detraccion_monto is present for the template
                    invoice['detraccion_monto'] = invoice.get('monto_total_factura', 0) - invoice.get('monto_neto_factura', 0)
                    # --- FIX: Add contract and anexo numbers to each invoice ---
                    invoice['contract_number'] = st.session_state.get('contract_number', '')
                    invoice['anexo_number'] = st.session_state.get('anexo_number', '')
                    # Add global commission data to each invoice for the template
                    invoice['comision_de_estructuracion_global'] = st.session_state.comision_estructuracion_pct_global
                    invoice['comision_minima_pen_global'] = st.session_state.comision_estructuracion_min_pen_global
                    invoice['comision_minima_usd_global'] = st.session_state.comision_estructuracion_min_usd_global
                    invoice['num_invoices'] = num_invoices_for_pdf
                    invoices_to_print.append(invoice)

            if invoices_to_print:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"reporte_efide_{timestamp}.pdf"
                output_filepath = os.path.join("C:/Users/rguti/Inandes.TECH/generated_pdfs", output_filename)

                temp_dir = "C:/Users/rguti/Inandes.TECH/backend/temp_files"
                if not os.path.exists(temp_dir):
                    os.makedirs(temp_dir)

                temp_json_path = os.path.join(temp_dir, f"efide_data_{timestamp}.json")
                with open(temp_json_path, 'w', encoding='utf-8') as f:
                    json.dump(invoices_to_print, f, ensure_ascii=False, indent=4)

                print_date = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") # Format for the generator script

                command = [
                    "python", "C:/Users/rguti/Inandes.TECH/backend/efide_report_generator.py",
                    f"--output_filepath={output_filepath}",
                    f"--data_file={temp_json_path}",
                    f"--print_date={print_date}"
                ]
                try:
                    result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
                    if result.stderr:
                        st.warning(f"Advertencias/Errores del generador de Reporte EFIDE: {result.stderr}")
                    
                    if os.path.exists(output_filepath):
                        st.success(f"Reporte EFIDE generado: {output_filename}")
                        with open(output_filepath, "rb") as file:
                            st.download_button(
                                label=f"Descargar {output_filename}",
                                data=file.read(),
                                file_name=output_filename,
                                mime="application/pdf",
                                key=f"download_{output_filename}"
                            )
                        os.remove(output_filepath)
                    else:
                        st.error(f"Error: El Reporte EFIDE no se generó correctamente. Salida: {result.stdout}")

                except subprocess.CalledProcessError as e:
                    st.error(f"Error al generar el Reporte EFIDE: {e}\nSalida del error: {e.stderr}")
                except FileNotFoundError:
                    st.error("Error: El script efide_report_generator.py no fue encontrado.")
                finally:
                    if os.path.exists(temp_json_path):
                        os.remove(temp_json_path)
            else:
                st.warning("No hay perfiles calculados para generar el Reporte EFIDE.")
        else:
            st.warning("No hay resultados de cálculo para generar el Reporte EFIDE.")

with col_consulta:
    st.write("#### Consulta y Generación de PDF")

    # --- Funcionalidad 1: Añadir propuesta actual ---
    st.write("##### 1. Añadir Propuesta(s) en Pantalla")
    if st.button("Añadir a la Lista de Impresión", help="Agrega las propuestas calculadas en esta sesión a la lista de abajo para generar el PDF."):
        if 'accumulated_proposals' not in st.session_state:
            st.session_state.accumulated_proposals = []

        proposals_added = 0
        for idx, invoice in enumerate(st.session_state.invoices_data):
            if invoice.get('recalculate_result'):
                # Crear un ID único para la propuesta de la sesión
                session_proposal_id = f"session_{invoice.get('file_id', idx)}"

                # Evitar añadir duplicados de la misma sesión
                if not any(p.get('proposal_id') == session_proposal_id for p in st.session_state.accumulated_proposals):
                    # Mapear los datos de la factura de la sesión al formato de propuesta
                    # Este formato debe ser compatible con el generador de PDF
                    proposal_data = {
                        'proposal_id': session_proposal_id,
                        'invoice_issuer_name': invoice.get('emisor_nombre'),
                        'invoice_issuer_ruc': invoice.get('emisor_ruc'),
                        'invoice_acceptor_name': invoice.get('aceptante_nombre'),
                        'invoice_payer_name': invoice.get('aceptante_nombre'), # Align key for PDF generator
                        'invoice_acceptor_ruc': invoice.get('aceptante_ruc'),
                        'invoice_number': invoice.get('numero_factura'),
                        'invoice_series_and_number': invoice.get('numero_factura'), # Align key for PDF generator
                        'invoice_total_amount': invoice.get('monto_total_factura'),
                        'invoice_net_amount': invoice.get('monto_neto_factura'),
                        'invoice_currency': invoice.get('moneda_factura'),
                        'invoice_issue_date': invoice.get('fecha_emision_factura'),
                        'credit_term_days': invoice.get('plazo_credito_dias'),
                        'disbursement_date': invoice.get('fecha_desembolso_factoring'),
                        'calculated_payment_date': invoice.get('fecha_pago_calculada'),
                        'invoice_due_date': invoice.get('fecha_pago_calculada'), # Align key for PDF generator
                        'calculated_operation_days': invoice.get('plazo_operacion_calculado'),
                        'financing_term_days': invoice.get('plazo_operacion_calculado'), # Align key for PDF generator
                        'detraccion_percentage': invoice.get('detraccion_porcentaje'),
                        'advance_rate': invoice.get('recalculate_result', {}).get('resultado_busqueda', {}).get('tasa_avance_encontrada', 0) * 100,
                        'monthly_interest_rate': invoice.get('interes_mensual'),
                        'structuring_commission_rate': invoice.get('comision_de_estructuracion'),
                        'min_commission_pen': invoice.get('comision_minima_pen'),
                        'min_commission_usd': invoice.get('comision_minima_usd'),
                        'affiliation_commission_pen': invoice.get('comision_afiliacion_pen'),
                        'affiliation_commission_usd': invoice.get('comision_afiliacion_usd'),
                        'apply_affiliation_commission': invoice.get('aplicar_comision_afiliacion'),
                        'initial_disbursement': invoice.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('abono', {}).get('monto', 0),
                        'total_costs': invoice.get('recalculate_result', {}).get('calculo_con_tasa_encontrada', {}).get('costos_totales', 0),
                        'security_margin': invoice.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('margen_seguridad', {}).get('monto', 0),
                        'margen_seguridad_calculado': invoice.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('margen_seguridad', {}).get('monto', 0),
                        'anexo_number': st.session_state.anexo_number,
                        'contract_number': st.session_state.contract_number,
                        'calculation_details': invoice.get('recalculate_result'),
                        'is_session_proposal': True,
                        # --- Flattened keys for pdf_generator_v_cli ---
                        'advance_amount': invoice.get('recalculate_result', {}).get('calculo_con_tasa_encontrada', {}).get('capital', 0),
                        'commission_amount': invoice.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('comision_estructuracion', {}).get('monto', 0),
                        'interes_calculado': invoice.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('interes', {}).get('monto', 0),
                        'igv_interes_calculado': invoice.get('recalculate_result', {}).get('calculo_con_tasa_encontrada', {}).get('igv_interes', 0),
                    }
                    st.session_state.accumulated_proposals.append(proposal_data)
                    proposals_added += 1
        
        if proposals_added > 0:
            st.success(f"{proposals_added} propuesta(s) de la sesión actual han sido añadidas a la lista de impresión.")
        else:
            st.warning("No se encontraron propuestas calculadas en la sesión actual para añadir. Por favor, haz clic en 'Calcular' primero.")

    st.markdown("---")

    # --- UI: Consulta y Selección de Propuestas (Funcionalidad 2 y 3) ---
    st.write("###### 2. Buscar y Seleccionar Propuestas Guardadas")
    with st.expander("Buscar en Base de Datos", expanded=False):
        col_id_propuesta, col_razon_social = st.columns(2)
        with col_id_propuesta:
            st.text_input("ID Propuesta (Opcional)", key="search_proposal_id", value=st.session_state.last_saved_proposal_id)
        with col_razon_social:
            st.text_input("Razón Social del Emisor", key="search_emisor_nombre")

        if st.button("Buscar y Añadir a la Lista"):
            if 'accumulated_proposals' not in st.session_state:
                st.session_state.accumulated_proposals = []

            search_found = False
            if st.session_state.search_proposal_id:
                proposal = supabase_handler.get_proposal_details_by_id(st.session_state.search_proposal_id)
                if proposal and 'proposal_id' in proposal:
                    if not any(p['proposal_id'] == proposal['proposal_id'] for p in st.session_state.accumulated_proposals):
                        # Flatten the proposal before adding it to the list
                        st.session_state.accumulated_proposals.append(flatten_db_proposal(proposal))
                        search_found = True
                else:
                    st.info(f"No se encontró ninguna propuesta con el ID: {st.session_state.search_proposal_id}")
            
            elif st.session_state.search_emisor_nombre:
                found_proposals_partial = supabase_handler.get_active_proposals_by_emisor_nombre(st.session_state.search_emisor_nombre)
                if found_proposals_partial:
                    for proposal_partial in found_proposals_partial:
                        full_proposal_details = supabase_handler.get_proposal_details_by_id(proposal_partial['proposal_id'])
                        if full_proposal_details and 'proposal_id' in full_proposal_details:
                            if not any(p['proposal_id'] == full_proposal_details['proposal_id'] for p in st.session_state.accumulated_proposals):
                                # Flatten the proposal before adding it to the list
                                st.session_state.accumulated_proposals.append(flatten_db_proposal(full_proposal_details))
                                search_found = True
                else:
                    st.info(f"No se encontraron propuestas activas para: {st.session_state.search_emisor_nombre}")
            else:
                st.warning("Por favor, ingresa un ID de Propuesta o una Razón Social para buscar.")
            
            if search_found:
                st.success("Propuesta(s) encontradas y añadidas a la lista de impresión.")

    st.markdown("---")
    st.write("###### 3. Lista de Propuestas para Imprimir")
    
    # Display the accumulated proposals (laundry list)
    if 'accumulated_proposals' in st.session_state and st.session_state.accumulated_proposals:
        if 'selected_proposals_checkboxes' not in st.session_state:
            st.session_state.selected_proposals_checkboxes = {}

        for i, proposal in enumerate(st.session_state.accumulated_proposals):
            if 'proposal_id' not in proposal: continue
            
            checkbox_key = f"accum_prop_checkbox_{proposal['proposal_id']}"
            if checkbox_key not in st.session_state.selected_proposals_checkboxes:
                st.session_state.selected_proposals_checkboxes[checkbox_key] = True

            col_check, col_id, col_emisor, col_monto = st.columns([0.1, 0.3, 0.3, 0.3])
            with col_check:
                st.session_state.selected_proposals_checkboxes[checkbox_key] = st.checkbox(" ", value=st.session_state.selected_proposals_checkboxes[checkbox_key], key=checkbox_key, label_visibility="collapsed")
            with col_id:
                origen = "(Sesión Actual)" if proposal.get('is_session_proposal') else ""
                st.write(f"**ID:** {proposal.get('proposal_id', 'N/A')} {origen}")
            with col_emisor:
                st.write(f"**Emisor:** {proposal.get('invoice_issuer_name', 'N/A')}")
            with col_monto:
                st.write(f"**Monto:** {proposal.get('invoice_currency', 'PEN')} {proposal.get('initial_disbursement', 0.0):,.2f}")

    # Botón para generar PDF consolidado
    if 'accumulated_proposals' in st.session_state and st.session_state.accumulated_proposals:
        if st.button("Generar PDF Consolidado"):
            selected_invoices_data = []
            for proposal in st.session_state.accumulated_proposals:
                checkbox_key = f"accum_prop_checkbox_{proposal.get('proposal_id', 'MISSING_ID')}"
                if st.session_state.selected_proposals_checkboxes.get(checkbox_key, False):
                    # Si es una propuesta de sesión, ya tenemos todos los datos.
                    # Si es de Supabase, necesitamos obtener los detalles completos (ya se hace en la búsqueda).
                    selected_invoices_data.append(proposal)
            
            if selected_invoices_data:
                # Construir el objeto de datos final con la estructura que espera el generador de PDF
                final_data_for_pdf = {
                    'tipo_documento': 'LIQUIDACIÓN DE FACTORING',
                    'contract_name': selected_invoices_data[0].get('contract_number', 'N/A'),
                    'emisor_nombre': selected_invoices_data[0].get('invoice_issuer_name', 'N/A'),
                    'emisor_ruc': selected_invoices_data[0].get('invoice_issuer_ruc', 'N/A'),
                    'relation_type': 'FACTURA(S)',
                    'anexo_number': selected_invoices_data[0].get('anexo_number', 'N/A'),
                    'document_date': datetime.datetime.now().strftime("%A %d, %B, %Y").upper(),
                    'facturas': selected_invoices_data,
                    'total_monto_neto': sum(inv.get('invoice_net_amount', 0) for inv in selected_invoices_data),
                    'total_invoice_total_amount': sum(inv.get('invoice_total_amount', 0) for inv in selected_invoices_data),
                    'detracciones_total': sum(inv.get('invoice_total_amount', 0) - inv.get('invoice_net_amount', 0) for inv in selected_invoices_data),
                    'total_neto': sum(inv.get('invoice_net_amount', 0) for inv in selected_invoices_data),
                    'total_capital_calculado': sum(inv.get('advance_amount', 0) for inv in selected_invoices_data),
                    'total_interes_calculado': sum(inv.get('interes_calculado', 0) for inv in selected_invoices_data),
                    'total_igv_interes_calculado': sum(inv.get('igv_interes_calculado', 0) for inv in selected_invoices_data),
                    'total_abono_real_calculado': sum(inv.get('initial_disbursement', 0) for inv in selected_invoices_data),
                    'total_margen_seguridad_calculado': sum(inv.get('margen_seguridad_calculado', 0) for inv in selected_invoices_data),
                    'total_comision_estructuracion_monto_calculado': sum(inv.get('commission_amount', 0) for inv in selected_invoices_data),
                    'total_igv_comision_estructuracion_calculado': sum(inv.get('commission_amount', 0) for inv in selected_invoices_data) * 0.18,
                    'total_comision_estructuracion': sum(inv.get('commission_amount', 0) for inv in selected_invoices_data) * 1.18,
                    'total_a_depositar': sum(inv.get('initial_disbursement', 0) for inv in selected_invoices_data),
                    'imprimir_comision_afiliacion': any(inv.get('apply_affiliation_commission', False) for inv in selected_invoices_data),
                    'total_comision_afiliacion_monto_calculado': selected_invoices_data[0].get('affiliation_commission_pen', 0) if selected_invoices_data else 0,
                    'total_igv_afiliacion_calculado': (selected_invoices_data[0].get('affiliation_commission_pen', 0) * 0.18) if any(inv.get('apply_affiliation_commission', False) for inv in selected_invoices_data) else 0,
                    'total_comision_afiliacion': (selected_invoices_data[0].get('affiliation_commission_pen', 0) * 1.18) if any(inv.get('apply_affiliation_commission', False) for inv in selected_invoices_data) else 0,
                    'total_commissions_and_igv': (sum(inv.get('commission_amount', 0) for inv in selected_invoices_data) * 1.18) + ((selected_invoices_data[0].get('affiliation_commission_pen', 0) * 1.18) if any(inv.get('apply_affiliation_commission', False) for inv in selected_invoices_data) else 0),
                    'total_intereses_adicionales_int': 0.0,
                    'total_intereses_adicionales_igv': 0.0,
                    'total_intereses_adicionales': 0.0,
                    'total_abono_for_pdf_display': sum((inv.get('invoice_net_amount', 0.0) * (inv.get('advance_rate', 0.0) / 100)) - inv.get('interes_calculado', 0.0) - inv.get('igv_interes_calculado', 0.0) for inv in selected_invoices_data),
                    'signatures': []
                }

                import subprocess, json, tempfile
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filepath = f"C:/Users/rguti/Inandes.TECH/generated_pdfs/consolidated_invoice_{timestamp}.pdf"

                temp_dir = "C:/Users/rguti/Inandes.TECH/backend/temp_files"
                if not os.path.exists(temp_dir):
                    os.makedirs(temp_dir)
                
                temp_json_path = os.path.join(temp_dir, f"consolidated_data_{timestamp}.json")
                with open(temp_json_path, 'w', encoding='utf-8') as f:
                    json.dump(final_data_for_pdf, f, ensure_ascii=False, indent=4)

                command = [
                    "python", "C:/Users/rguti/Adicionales.Inandes.HTML/html_generator_V6.py",
                    f"--output_file={output_filepath}",
                    f"--data_file={temp_json_path}",
                    "--template=plantilla_factura_V6.html"
                ]
                # ... (resto del código de generación de PDF sin cambios)
                st.write("Generando PDF consolidado...")
                try:
                    # Ejecutar el script y capturar la salida para depuración
                    result = subprocess.run(command, capture_output=True, text=True, encoding='cp1252')

                    # Imprimir siempre la salida estándar y el error estándar para depuración
                    if result.stdout:
                        st.warning(f"Salida del generador de PDF: {result.stdout}")
                    if result.stderr:
                        st.error(f"Errores del generador de PDF: {result.stderr}")

                    if result.returncode != 0 or not os.path.exists(output_filepath):
                        st.error("Error: El archivo PDF consolidado no se generó correctamente. Revisa la consola para ver los detalles.")
                        st.error(f"Detalle del error: {result.stderr}")
                    else:
                        with open(output_filepath, "rb") as file:
                            st.download_button(
                                label="Descargar PDF Consolidado", data=file.read(),
                                file_name=os.path.basename(output_filepath), mime="application/pdf"
                            )
                        st.success("PDF consolidado generado. Haz clic en el botón para descargarlo.")
                        os.remove(output_filepath)

                except FileNotFoundError:
                    st.error("Error: El script html_generator_V6.py no fue encontrado.")
                except Exception as e:
                    st.error(f"Ocurrió un error inesperado: {e}")
            else:
                st.warning("No hay propuestas seleccionadas para generar el PDF.")
