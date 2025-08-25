import os
import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
import sys
import json

# Añadir el directorio 'backend' al path para importar flatten_dict
sys.path.append(os.path.dirname(__file__))
from variable_data_pdf_generator import flatten_dict

# --- Conexión Segura a Supabase ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'supabase_client', '.env')
load_dotenv(dotenv_path=dotenv_path)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error al inicializar Supabase: {e}")

# --- Mapeo de Claves Aplanadas a Columnas de Supabase ---
# Este mapeo es crucial para traducir las claves generadas por flatten_dict
# a los nombres de columnas de tu tabla 'propuestas' en Supabase.
# Asegúrate de que estos nombres coincidan exactamente con tus columnas de Supabase.
FLATTENED_TO_SUPABASE_MAPPING = {
    # Campos directos del formulario
    'emisor_nombre': 'emisor_nombre',
    'emisor_ruc': 'emisor_ruc',
    'aceptante_nombre': 'aceptante_nombre',
    'aceptante_ruc': 'aceptante_ruc',
    'numero_factura': 'numero_factura',
    'monto_total_factura': 'monto_total_factura',
    'monto_neto_factura': 'monto_neto_factura',
    'moneda_factura': 'moneda_factura',
    'fecha_emision_factura': 'fecha_emision_factura',
    'plazo_credito_dias': 'plazo_credito_dias',
    'fecha_desembolso_factoring': 'fecha_desembolso_factoring',
    'tasa_de_avance': 'tasa_de_avance',
    'interes_mensual': 'interes_mensual',
    'comision_de_estructuracion': 'comision_de_estructuracion',
    'comision_minima_pen': 'comision_minima_pen',
    'comision_minima_usd': 'comision_minima_usd',
    'comision_afiliacion_pen': 'comision_afiliacion_pen',
    'comision_afiliacion_usd': 'comision_afiliacion_usd',
    'aplicar_comision_afiliacion': 'aplicar_comision_afiliacion',
    'detraccion_porcentaje': 'detraccion_porcentaje',
    'anexo_number': 'anexo_number',
    'contract_number': 'contract_number',

    # Campos calculados (de initial_calc_result o recalculate_result)
    'fecha_pago_calculada': 'fecha_pago_calculada',
    'plazo_operacion_calculado': 'plazo_operacion_calculado',

    # Resultados del Paso 1 (initial_calc_result)
    'initial_calc_result.capital': 'capital_calculado',
    'initial_calc_result.interes': 'interes_calculado',
    'initial_calc_result.igv_interes': 'igv_interes_calculado',
    'initial_calc_result.comision_estructuracion': 'comision_estructuracion_monto_calculado',
    'initial_calc_result.igv_comision': 'igv_comision_estructuracion_calculado',
    'initial_calc_result.comision_afiliacion': 'comision_afiliacion_monto_calculado',
    'initial_calc_result.igv_afiliacion': 'igv_afiliacion_calculado',
    'initial_calc_result.abono_real_teorico': 'abono_real_calculado', # Mapeo específico
    'initial_calc_result.margen_seguridad': 'margen_seguridad_calculado',

    # Resultados del Paso 2 (recalculate_result)
    'recalculate_result.resultado_busqueda.tasa_avance_encontrada': 'tasa_avance_encontrada_calculada',
    'recalculate_result.resultado_busqueda.abono_real_calculado': 'abono_real_calculado', # Mapeo específico

    'recalculate_result.calculo_con_tasa_encontrada.capital': 'capital_calculado',
    'recalculate_result.calculo_con_tasa_encontrada.interes': 'interes_calculado',
    'recalculate_result.calculo_con_tasa_encontrada.igv_interes': 'igv_interes_calculado',
    'recalculate_result.calculo_con_tasa_encontrada.comision_estructuracion': 'comision_estructuracion_monto_calculado',
    'recalculate_result.calculo_con_tasa_encontrada.igv_comision_estructuracion': 'igv_comision_estructuracion_calculado',
    'recalculate_result.calculo_con_tasa_encontrada.comision_afiliacion': 'comision_afiliacion_monto_calculado',
    'recalculate_result.calculo_con_tasa_encontrada.igv_afiliacion': 'igv_afiliacion_calculado',
    'recalculate_result.calculo_con_tasa_encontrada.margen_seguridad': 'margen_seguridad_calculado',
    'recalculate_result': 'recalculate_result_json',
    # 'recalculate_result.calculo_con_tasa_encontrada.abono_real': 'abono_real_calculado', # Si existe este campo en tu API
}

# --- Funciones de Ayuda ---

def _format_date(date_str: str) -> str | None:
    """Convierte una fecha de DD-MM-YYYY a YYYY-MM-DD."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return datetime.datetime.strptime(date_str, '%d-%m-%Y').strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return None

def _convert_to_numeric(value):
    """Intenta convertir un valor a float, si es posible."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

# --- Funciones Públicas ---

def get_razon_social_by_ruc(ruc: str) -> str:
    """Busca la razón social de una empresa por su RUC."""
    if not supabase or not ruc:
        return ""
    try:
        response = supabase.table('EMISORES.DEUDORES').select('"Razon Social"').eq('RUC', ruc).single().execute()
        if response.data:
            return response.data.get('Razon Social', '')
    except Exception as e:
        print(f"[ERROR en get_razon_social_by_ruc]: {e}")
    return ""

def save_proposal(session_data: dict) -> tuple[bool, str]:
    """
    Guarda una propuesta completa en la tabla 'propuestas' de Supabase,
    serializando los resultados completos de cálculo como JSON.
    """
    if not supabase:
        return False, "Error crítico: La conexión con Supabase no pudo ser establecida."

    try:
        # Extraer y serializar los resultados completos de cálculo como JSON
        recalculate_result_full = session_data.get('recalculate_result')

        # Crear una copia de session_data para aplanar, excluyendo los objetos JSON completos
        session_data_for_flattening = {k: v for k, v in session_data.items() if k not in ['recalculate_result']}
        flattened_session_data = flatten_dict(session_data_for_flattening)

        # Construir el diccionario para insertar en Supabase
        data_to_insert = {}

        # Añadir los resultados JSON completos como strings
        data_to_insert['recalculate_result_json'] = json.dumps(recalculate_result_full) if recalculate_result_full else None

        # Mapear campos directos y calculados (desde los datos aplanados)
        for flattened_key, supabase_column_name in FLATTENED_TO_SUPABASE_MAPPING.items():
            # Saltar las claves JSON completas ya que se manejan arriba
            if flattened_key in ['recalculate_result']:
                continue

            value = flattened_session_data.get(flattened_key)
            
            # Convertir tipos de datos según sea necesario
            if 'fecha' in supabase_column_name: # Asumiendo que las columnas de fecha contienen 'fecha'
                data_to_insert[supabase_column_name] = _format_date(value)
            elif 'monto' in supabase_column_name or 'comision' in supabase_column_name or \
                 'interes' in supabase_column_name or 'capital' in supabase_column_name or \
                 'margen' in supabase_column_name or 'tasa' in supabase_column_name or \
                 'igv' in supabase_column_name or 'abono' in supabase_column_name:
                data_to_insert[supabase_column_name] = _convert_to_numeric(value)
            elif 'plazo' in supabase_column_name and 'dias' in supabase_column_name:
                try:
                    data_to_insert[supabase_column_name] = int(value) if value is not None else None
                except (ValueError, TypeError):
                    data_to_insert[supabase_column_name] = None
            elif 'aplicar_comision_afiliacion' == supabase_column_name:
                data_to_insert[supabase_column_name] = bool(value) if value is not None else False
            else:
                data_to_insert[supabase_column_name] = value

        # 3. Generar proposal_id y estado (campos especiales)
        emisor_nombre_id = data_to_insert.get('emisor_nombre', 'SIN_NOMBRE').replace(' ', '_').replace('.', '').replace(',', '')
        numero_factura = data_to_insert.get('numero_factura', 'SIN_FACTURA')
        fecha_propuesta = datetime.datetime.now().strftime('%d-%m-%y-%H-%M-%S')
        data_to_insert['proposal_id'] = f"{emisor_nombre_id}-{numero_factura}-{fecha_propuesta}"
        data_to_insert['estado'] = 'ACTIVO'

        # Asegurarse de que los campos que no se mapearon explícitamente pero existen en Supabase
        # y son requeridos, tengan un valor por defecto o null si es apropiado.
        # Esto es una medida de seguridad si el mapeo no es 100% exhaustivo.
        # Por ejemplo, si 'tasa_avance_encontrada_calculada' no se encuentra en flattened_session_data
        # pero es una columna en Supabase, asegúrate de que se añada como None o 0.0
        if 'tasa_avance_encontrada_calculada' not in data_to_insert:
            data_to_insert['tasa_avance_encontrada_calculada'] = None
        if 'abono_real_calculado' not in data_to_insert:
            data_to_insert['abono_real_calculado'] = None
        if 'capital_calculado' not in data_to_insert:
            data_to_insert['capital_calculado'] = None
        # ... y así para otros campos calculados que puedan faltar si no se ejecutó el cálculo completo

        # 4. Ejecutar la inserción
        response = supabase.table('propuestas').insert(data_to_insert).execute()

        if hasattr(response, 'error') and response.error:
            raise Exception(response.error.message)

        return True, f"Propuesta con ID {data_to_insert['proposal_id']} guardada exitosamente."

    except Exception as e:
        print(f"[ERROR en save_proposal]: {e}")
        return False, f"Error al guardar la propuesta: {e}"

def get_proposal_details_by_id(proposal_id: str) -> dict:
    """
    Recupera todos los detalles de una propuesta de factoring desde Supabase usando su proposal_id.
    """
    if not supabase:
        print("Error: La conexión con Supabase no está disponible.")
        return {"error": "No hay conexión con Supabase"}

    try:
        response = supabase.table('propuestas').select('*').eq('proposal_id', proposal_id).single().execute()

        if response.data:
            proposal_data = response.data
            
            # Formatear las fechas de YYYY-MM-DD a DD-MM-YYYY para consistencia
            for key in ['fecha_emision_factura', 'fecha_pago_calculada', 'fecha_desembolso_factoring']:
                if proposal_data.get(key) and isinstance(proposal_data[key], str):
                    try:
                        proposal_data[key] = datetime.datetime.strptime(proposal_data[key], '%Y-%m-%d').strftime('%d-%m-%Y')
                    except ValueError:
                        # Si el formato ya es correcto o es inválido, se deja como está
                        pass
            return proposal_data
        else:
            print(f"No se encontró ninguna propuesta con el ID: {proposal_id}")
            return {"error": f"No se encontró la propuesta con ID {proposal_id}"}

    except Exception as e:
        print(f"[ERROR en get_proposal_details_by_id]: {e}")
        return {"error": f"Error de base de datos al buscar la propuesta: {e}"}

def get_active_proposals_by_emisor_nombre(emisor_nombre: str) -> list[dict]:
    """
    Recupera una lista de propuestas activas desde Supabase para un emisor_nombre dado.
    """
    if not supabase:
        print("Error: La conexión con Supabase no está disponible.")
        return []

    try:
        response = supabase.table('propuestas')\
            .select('proposal_id, aceptante_nombre, abono_real_calculado')\
            .eq('emisor_nombre', emisor_nombre)\
            .eq('estado', 'ACTIVO')\
            .execute()

        if response.data:
            return response.data
        else:
            return []

    except Exception as e:
        print(f"[ERROR en get_active_proposals_by_emisor_nombre]: {e}")
        return []