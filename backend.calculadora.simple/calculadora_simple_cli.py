import requests
import datetime

API_BASE_URL = "http://127.0.0.1:8000"

def get_user_input(prompt, type_func=str, default=None):
    while True:
        user_input = input(prompt).strip()
        if user_input == '' and default is not None:
            return default
        try:
            return type_func(user_input)
        except ValueError:
            print(f"Entrada inválida. Por favor, ingrese un valor de tipo {type_func.__name__}.")

def calculate_dates(invoice_data):
    fecha_emision_str = invoice_data.get('fecha_emision_factura')
    plazo_credito_dias = invoice_data.get('plazo_credito_dias')
    fecha_desembolso_str = invoice_data.get('fecha_desembolso_factoring')

    fecha_pago_calculada = ""
    plazo_operacion_calculado = 0

    try:
        if fecha_emision_str:
            fecha_emision_dt = datetime.datetime.strptime(fecha_emision_str, "%d-%m-%Y")

            if plazo_credito_dias is not None:
                fecha_pago_dt = fecha_emision_dt + datetime.timedelta(days=plazo_credito_dias)
                fecha_pago_calculada = fecha_pago_dt.strftime("%d-%m-%Y")
            
            if fecha_pago_calculada and fecha_desembolso_str:
                fecha_pago_dt = datetime.datetime.strptime(fecha_pago_calculada, "%d-%m-%Y")
                fecha_desembolso_dt = datetime.datetime.strptime(fecha_desembolso_str, "%d-%m-%Y")
                if fecha_pago_dt >= fecha_desembolso_dt:
                    plazo_operacion_calculado = (fecha_pago_dt - fecha_desembolso_dt).days
                else:
                    plazo_operacion_calculado = 0

    except ValueError:
        pass # Dates might be invalid, will be handled by API or user input

    invoice_data['fecha_pago_calculada'] = fecha_pago_calculada
    invoice_data['plazo_operacion_calculado'] = plazo_operacion_calculado

def display_profile_report(invoice, recalc_result):
    print("\n--- Perfil de la Operación ---")
    print(f"Emisor: {invoice.get('emisor_nombre', 'N/A')} | Aceptante: {invoice.get('aceptante_nombre', 'N/A')}")
    print(f"Factura: {invoice.get('numero_factura', 'N/A')} | F. Emisión: {invoice.get('fecha_emision_factura', 'N/A')}")
    print(f"F. Pago: {invoice.get('fecha_pago_calculada', 'N/A')} | Monto Total: {invoice.get('moneda_factura', '')} {invoice.get('monto_total_factura', 0):,.2f}")
    print(f"Monto Neto: {invoice.get('moneda_factura', '')} {invoice.get('monto_neto_factura', 0):,.2f}")

    desglose = recalc_result.get('desglose_final_detallado', {{}})
    calculos = recalc_result.get('calculo_con_tasa_encontrada', {{}})
    busqueda = recalc_result.get('resultado_busqueda', {{}})
    moneda = invoice.get('moneda_factura', 'PEN')

    tasa_avance_pct = busqueda.get('tasa_avance_encontrada', 0) * 100
    monto_neto = invoice.get('monto_neto_factura', 0)
    capital = calculos.get('capital', 0)
    
    abono = desglose.get('abono', {{}})
    interes = desglose.get('interes', {{}})
    com_est = desglose.get('comision_estructuracion', {{}})
    com_afi = desglose.get('comision_afiliacion', {{}})
    igv = desglose.get('igv_total', {{}})
    margen = desglose.get('margen_seguridad', {{}})

    costos_totales = interes.get('monto', 0) + com_est.get('monto', 0) + com_afi.get('monto', 0) + igv.get('monto', 0)
    tasa_diaria_pct = (invoice.get('interes_mensual', 0) / 30) 

    print("\n| Item | Monto ({}) | % sobre Neto |")
    print("| :--- | :--- | :--- |")
    
    monto_total = invoice.get('monto_total_factura', 0)
    detraccion_monto = monto_total - monto_neto
    detraccion_pct = invoice.get('detraccion_porcentaje', 0)
    
    print(f"| Monto Total de Factura | {monto_total:,.2f} | |")
    print(f"| Detracción / Retención | {detraccion_monto:,.2f} | {detraccion_pct:.2f}% |")

    print(f"| Monto Neto de Factura | {monto_neto:,.2f} | 100.00% |")
    print(f"| Tasa de Avance Aplicada | N/A | {tasa_avance_pct:.2f}% |")
    print(f"| Margen de Seguridad | {margen.get('monto', 0):,.2f} | {margen.get('porcentaje', 0):.2f}% |")
    print(f"| Capital | {capital:,.2f} | {((capital / monto_neto) * 100) if monto_neto else 0:.2f}% |")
    print(f"| Intereses | {interes.get('monto', 0):,.2f} | {interes.get('porcentaje', 0):.2f}% |")
    print(f"| Comisión de Estructuración | {com_est.get('monto', 0):,.2f} | {com_est.get('porcentaje', 0):.2f}% |")
    if com_afi.get('monto', 0) > 0:
        print(f"| Comisión de Afiliación | {com_afi.get('monto', 0):,.2f} | {com_afi.get('porcentaje', 0):.2f}% |")
    
    igv_interes_monto = calculos.get('igv_interes', 0)
    igv_interes_pct = (igv_interes_monto / monto_neto * 100) if monto_neto else 0
    print(f"| IGV sobre Intereses | {igv_interes_monto:,.2f} | {igv_interes_pct:.2f}% |")

    igv_com_est_monto = calculos.get('igv_comision_estructuracion', 0)
    igv_com_est_pct = (igv_com_est_monto / monto_neto * 100) if monto_neto else 0
    print(f"| IGV sobre Com. de Estruct. | {igv_com_est_monto:,.2f} | {igv_com_est_pct:.2f}% |")

    if com_afi.get('monto', 0) > 0:
        igv_com_afi_monto = calculos.get('igv_afiliacion', 0)
        igv_com_afi_pct = (igv_com_afi_monto / monto_neto * 100) if monto_neto else 0
        print(f"| IGV sobre Com. de Afiliación | {igv_com_afi_monto:,.2f} | {igv_com_afi_pct:.2f}% |")

    print(f"| **Monto a Desembolsar** | **{abono.get('monto', 0):,.2f}** | **{abono.get('porcentaje', 0):.2f}%** |")
    print(f"| **Total (Monto Neto Factura)** | **{monto_neto:,.2f}** | **100.00%** |")
    print("\n")


def main():
    print("--- Calculadora Simple de Factoring ---")
    
    num_invoices = get_user_input("¿Cuántas facturas desea simular? ", int)
    
    invoices_data = []
    for i in range(num_invoices):
        print(f"\n--- Datos para Factura {i + 1} ---")
        invoice = {{}}

        # Involucrados
        invoice['emisor_nombre'] = get_user_input("Nombre del Emisor: ")
        invoice['emisor_ruc'] = get_user_input("RUC del Emisor: ")
        invoice['aceptante_nombre'] = get_user_input("Nombre del Aceptante: ")
        invoice['aceptante_ruc'] = get_user_input("RUC del Aceptante: ")

        # Montos y Moneda
        invoice['numero_factura'] = get_user_input("Número de Factura: ")
        invoice['moneda_factura'] = get_user_input("Moneda (PEN/USD): ").upper()
        invoice['monto_total_factura'] = get_user_input("Monto Factura Total (con IGV): ", float)
        invoice['monto_neto_factura'] = get_user_input("Monto Factura Neto (sin IGV): ", float)
        
        # Calculate detraccion_porcentaje
        detraccion_retencion_pct = 0.0
        if invoice.get('monto_total_factura', 0) > 0:
            detraccion_retencion_pct = ((invoice['monto_total_factura'] - invoice['monto_neto_factura']) / invoice['monto_total_factura']) * 100
        invoice['detraccion_porcentaje'] = detraccion_retencion_pct

        # Fechas y Plazos
        invoice['fecha_emision_factura'] = get_user_input("Fecha de Emisión (DD-MM-YYYY): ")
        invoice['plazo_credito_dias'] = get_user_input("Plazo de Crédito (días): ", int)
        invoice['fecha_desembolso_factoring'] = get_user_input("Fecha de Desembolso (DD-MM-YYYY): ")
        
        # Calculate derived dates and terms
        calculate_dates(invoice)

        # Tasas y Comisiones
        invoice['tasa_de_avance'] = get_user_input("Tasa de Avance (%): ", float)
        invoice['interes_mensual'] = get_user_input("Interés Mensual (%): ", float)
        
        # Default values for commissions (as they are global in the original app)
        # For simplicity in this CLI, we'll use fixed values or prompt if needed.
        # For now, let's hardcode them as per the original app's defaults or global settings.
        invoice['comision_estructuracion_pct'] = 0.5 # Default from original app
        invoice['comision_minima_pen'] = 200.0 # Default from original app
        invoice['comision_minima_usd'] = 50.0 # Default from original app
        invoice['comision_afiliacion_pen'] = 200.0 # Default from original app
        invoice['comision_afiliacion_usd'] = 50.0 # Default from original app
        invoice['aplicar_comision_afiliacion'] = False # Default from original app
        invoice['dias_minimos_interes_individual'] = 15 # Default from original app

        invoices_data.append(invoice)

    print("\n--- Iniciando cálculos para todas las facturas ---")
    for idx, invoice in enumerate(invoices_data):
        print(f"\nCalculando Factura {idx + 1}...")
        
        # Determine applicable minimum commission based on currency
        comision_minima_aplicable = invoice['comision_minima_usd'] if invoice['moneda_factura'] == 'USD' else invoice['comision_minima_pen']
        comision_afiliacion_aplicable = invoice['comision_afiliacion_usd'] if invoice['moneda_factura'] == 'USD' else invoice['comision_afiliacion_pen']

        # Determine plazo_para_api considering minimum interest days
        plazo_real = invoice.get('plazo_operacion_calculado', 0)
        plazo_para_api = max(plazo_real, invoice.get('dias_minimos_interes_individual', 15))

        # Payload for /calcular_desembolso
        api_data_desembolso = {
            "plazo_operacion": plazo_para_api,
            "mfn": invoice['monto_neto_factura'],
            "tasa_avance": invoice['tasa_de_avance'] / 100,
            "interes_mensual": invoice['interes_mensual'] / 100,
            "comision_estructuracion_pct": invoice['comision_estructuracion_pct'] / 100,
            "comision_minima_aplicable": comision_minima_aplicable,
            "igv_pct": 0.18,
            "comision_afiliacion_aplicable": comision_afiliacion_aplicable,
            "aplicar_comision_afiliacion": invoice['aplicar_comision_afiliacion']
        }

        try:
            response_desembolso = requests.post(f"{API_BASE_URL}/calcular_desembolso", json=api_data_desembolso)
            response_desembolso.raise_for_status()
            initial_calc_result = response_desembolso.json()

            if initial_calc_result and 'abono_real_teorico' in initial_calc_result:
                abono_real_teorico = initial_calc_result['abono_real_teorico']
                monto_desembolsar_objetivo = (abono_real_teorico // 10) * 10

                # Payload for /encontrar_tasa
                api_data_encontrar_tasa = {
                    "plazo_operacion": plazo_para_api,
                    "mfn": invoice['monto_neto_factura'],
                    "interes_mensual": invoice['interes_mensual'] / 100,
                    "comision_estructuracion_pct": invoice['comision_estructuracion_pct'] / 100,
                    "igv_pct": 0.18,
                    "monto_objetivo": monto_desembolsar_objetivo,
                    "comision_minima_aplicable": comision_minima_aplicable,
                    "comision_afiliacion_aplicable": comision_afiliacion_aplicable,
                    "aplicar_comision_afiliacion": invoice['aplicar_comision_afiliacion']
                }
                response_encontrar_tasa = requests.post(f"{API_BASE_URL}/encontrar_tasa", json=api_data_encontrar_tasa)
                response_encontrar_tasa.raise_for_status()
                recalculate_result = response_encontrar_tasa.json()
                
                display_profile_report(invoice, recalculate_result)

            else:
                print(f"Error: No se pudo obtener 'abono_real_teorico' de la primera llamada API para Factura {idx + 1}.")
        
        except requests.exceptions.RequestException as e:
            print(f"Error de conexión con la API para Factura {idx + 1}: {e}")
        except Exception as e:
            print(f"Ocurrió un error inesperado para Factura {idx + 1}: {e}")

if __name__ == "__main__":
    main()
