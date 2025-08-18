import os
import argparse
from dotenv import load_dotenv
from supabase import create_client, Client
from jinja2 import Environment, FileSystemLoader

try:
    from weasyprint import HTML
except ImportError:
    print("Error: WeasyPrint is not installed. Please install it using 'pip install weasyprint'")
    exit(1)

def get_emisor_deudor_data(ruc):
    dotenv_path = os.path.join(os.path.dirname(__file__), '..\supabase\.env')
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a PDF report from Supabase EMISORES.DEUDORES table.")
    parser.add_argument("--ruc", required=True, help="RUC to search for in the EMISORES.DEUDORES table.")
    parser.add_argument("--output_filepath", required=True, help="The full path to save the output PDF file.")
    args = parser.parse_args()

    print(f"Consultando datos para RUC: {args.ruc}")
    data = get_emisor_deudor_data(args.ruc)

    template_dir = os.path.dirname(os.path.abspath(__file__))
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("supabase_report_template.html")

    html_output = template.render(data=data)

    base_url = os.path.dirname(os.path.abspath(__file__))
    pdf_bytes = HTML(string=html_output, base_url=base_url).write_pdf()

    output_dir = os.path.dirname(args.output_filepath)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(args.output_filepath, "wb") as f:
        f.write(pdf_bytes)
    
    print(f"PDF report successfully generated at: {args.output_filepath}")