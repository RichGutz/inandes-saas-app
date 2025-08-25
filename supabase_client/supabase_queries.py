import os
from dotenv import load_dotenv
from supabase import create_client, Client

def get_emisor_deudor_data(ruc):
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
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
