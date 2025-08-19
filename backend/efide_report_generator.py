import argparse
import json
import os
from jinja2 import Environment, FileSystemLoader
import datetime

try:
    from weasyprint import HTML
except ImportError:
    print("Error: WeasyPrint is not installed. Please install it using 'pip install weasyprint'")
    exit(1)

# --- Start of get_emisor_deudor_data function (moved from supabase_queries.py) ---
from dotenv import load_dotenv
from supabase import create_client, Client

def get_emisor_deudor_data(ruc):
    dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'supabase', '.env') # Adjusted path
    load_dotenv(dotenv_path=dotenv_path)

    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print(f"Error: No se pudieron cargar las variables de entorno desde {dotenv_path}")
        return None

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        table_name = "EMISORES.DEUDORES"

        response = supabase.table(table_name).select("*").eq('RUC', ruc).limit(1).execute()

        if response.data:
            return response.data[0]
        else:
            return None

    except Exception as e:
        print(f"Ocurrió un error al conectar o consultar Supabase: {e}")
        return None
# --- End of get_emisor_deudor_data function ---

def generate_efide_pdf(output_filepath, invoices_data_json, print_date_str):
    template_dir = os.path.dirname(os.path.abspath(__file__))
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("plantilla_efide_dinamica.html")

    invoices_data = json.loads(invoices_data_json)

    # --- Calculate Totals for the Footer ---
    total_monto_total_factura = sum(inv.get('monto_total_factura', 0) for inv in invoices_data)
    total_detraccion_monto = sum(inv.get('detraccion_monto', 0) for inv in invoices_data)
    total_monto_neto_factura = sum(inv.get('monto_neto_factura', 0) for inv in invoices_data)
    
    # For percentage, calculate a weighted average based on the invoice net amount
    weighted_sum_tasa_avance = sum(
        inv.get('monto_neto_factura', 0) * inv.get('recalculate_result', {}).get('resultado_busqueda', {}).get('tasa_avance_encontrada', 0)
        for inv in invoices_data
    )
    if total_monto_neto_factura > 0:
        total_tasa_avance_aplicada = weighted_sum_tasa_avance / total_monto_neto_factura
    else:
        total_tasa_avance_aplicada = 0
    
    total_margen_seguridad = sum(inv.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('margen_seguridad', {}).get('monto', 0) for inv in invoices_data)
    total_capital = sum(inv.get('recalculate_result', {}).get('calculo_con_tasa_encontrada', {}).get('capital', 0) for inv in invoices_data)
    total_intereses = sum(inv.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('interes', {}).get('monto', 0) for inv in invoices_data)
    total_comision_estructuracion = sum(inv.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('comision_estructuracion', {}).get('monto', 0) for inv in invoices_data)
    total_comision_afiliacion = sum(inv.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('comision_afiliacion', {}).get('monto', 0) for inv in invoices_data)
    
    # Sum of all IGVs
    total_igv = sum(inv.get('recalculate_result', {}).get('calculo_con_tasa_encontrada', {}).get('igv_interes', 0) +
                    inv.get('recalculate_result', {}).get('calculo_con_tasa_encontrada', {}).get('igv_comision_estructuracion', 0) +
                    inv.get('recalculate_result', {}).get('calculo_con_tasa_encontrada', {}).get('igv_afiliacion', 0)
                    for inv in invoices_data)
    
    total_monto_desembolsar = sum(inv.get('recalculate_result', {}).get('desglose_final_detallado', {}).get('abono', {}).get('monto', 0) for inv in invoices_data)

    # Assuming all invoices have the same main_invoice data for header, pick the first one
    main_invoice_data = invoices_data[0] if invoices_data else {}

    # Fetch signatory data from Supabase
    emisor_ruc = main_invoice_data.get('emisor_ruc')
    signatory_data = {}
    if emisor_ruc:
        signatory_data = get_emisor_deudor_data(emisor_ruc) or {} # Ensure it's a dict even if None

    template_data = {
        'invoices': invoices_data,
        'print_date': datetime.datetime.strptime(print_date_str, "%Y%m%d_%H%M%S"), # Convert back to datetime object
        'main_invoice': main_invoice_data, # Pass the first invoice for header details
        'signatory_data': signatory_data, # NEW: Pass signatory data to template
        'total_monto_total_factura': total_monto_total_factura,
        'total_detraccion_monto': total_detraccion_monto,
        'total_monto_neto_factura': total_monto_neto_factura,
        'total_tasa_avance_aplicada': total_tasa_avance_aplicada,
        'total_margen_seguridad': total_margen_seguridad,
        'total_capital': total_capital,
        'total_intereses': total_intereses,
        'total_comision_estructuracion': total_comision_estructuracion,
        'total_comision_afiliacion': total_comision_afiliacion,
        'total_igv': total_igv,
        'total_monto_desembolsar': total_monto_desembolsar,
    }

    html_output = template.render(template_data)

    base_url = os.path.dirname(os.path.abspath(__file__))
    pdf_bytes = HTML(string=html_output, base_url=base_url).write_pdf()

    output_dir = os.path.dirname(output_filepath)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_filepath, "wb") as f:
        f.write(pdf_bytes)
    
    print(f"EFIDE PDF report successfully generated at: {output_filepath}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an EFIDE-style PDF report from invoice data.")
    parser.add_argument("--output_filepath", required=True, help="The full path to save the output PDF file.")
    parser.add_argument("--data_file", required=True, help="Path to the JSON file containing the list of invoice data.")
    parser.add_argument("--print_date", required=True, help="Date of printing in string format (YYYYMMDD_HHMMSS).")
    args = parser.parse_args()

    try:
        with open(args.data_file, 'r', encoding='utf-8') as f:
            invoices_data_json = f.read()
        generate_efide_pdf(args.output_filepath, invoices_data_json, args.print_date)
    except FileNotFoundError:
        print(f"Error: Data file not found at {args.data_file}")
        exit(1)
    except Exception as e:
        print(f"An error occurred during PDF generation: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
