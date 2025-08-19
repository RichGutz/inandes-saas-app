import argparse
import json
import os
from jinja2 import Environment, FileSystemLoader

try:
    from weasyprint import HTML
except ImportError:
    print("Error: WeasyPrint is not installed. Please install it using 'pip install weasyprint'")
    exit(1)

def generate_pdf_from_invoices_data(output_filepath, invoices_data, print_date_str):
    template_dir = os.path.dirname(os.path.abspath(__file__))
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("perfil_template.html")

    template_data = {
        'invoices': invoices_data,
        'print_date': print_date_str
    }

    html_output = template.render(template_data)

    base_url = os.path.dirname(os.path.abspath(__file__))
    pdf_bytes = HTML(string=html_output, base_url=base_url).write_pdf()

    output_dir = os.path.dirname(output_filepath)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_filepath, "wb") as f:
        f.write(pdf_bytes)
    
    print(f"PDF profile successfully generated at: {output_filepath}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a consolidated PDF profile from a list of invoices.")
    parser.add_argument("--output_filepath", required=True, help="The full path to save the output PDF file.")
    parser.add_argument("--data_file", required=True, help="Path to the JSON file containing the list of invoice data.")
    parser.add_argument("--print_date", required=True, help="Date of printing in string format.")
    args = parser.parse_args()

    try:
        with open(args.data_file, 'r', encoding='utf-8') as f:
            invoices_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from file {args.data_file}: {e}")
        exit(1)
    except FileNotFoundError:
        print(f"Error: Data file not found at {args.data_file}")
        exit(1)

    try:
        generate_pdf_from_invoices_data(args.output_filepath, invoices_data, args.print_date)
    except Exception as e:
        print(f"An error occurred during PDF generation: {e}")
        import traceback
        traceback.print_exc()
        exit(1)