
import sys
import os
import json
from datetime import datetime, timedelta

# --- Configuración del Path ---
# Añadir el directorio raíz del proyecto al path de Python para permitir importaciones relativas
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

# --- Importaciones de Módulos Propios ---
from backend.supabase_handler import get_proposal_details_by_id
from liquidacion.backend.calculadora_liquidacion import calcular_liquidacion

def test_liquidar_factura(proposal_id: str):
    """
    Orquesta el proceso de liquidación para una factura específica:
    1. Obtiene los datos de la factura desde Supabase.
    2. Define parámetros de prueba para la liquidación.
    3. Ejecuta la calculadora de liquidación.
    4. Imprime los resultados de forma clara.
    """
    print(f"--- INICIANDO TEST DE LIQUIDACIÓN PARA LA FACTURA ID: {proposal_id} ---")

    # 1. Obtener los datos de la factura desde Supabase
    print("\n1. Obteniendo datos de la operación desde Supabase...")
    datos_operacion = get_proposal_details_by_id(proposal_id)

    if not datos_operacion or datos_operacion.get('error'):
        print(f"   ERROR: No se pudieron obtener los datos para la propuesta.")
        if datos_operacion.get('error'):
            print(f"   Detalle del error: {datos_operacion['error']}")
        return

    print("   ...Datos de la operación obtenidos exitosamente.")
    print(json.dumps(datos_operacion, indent=4, default=str))

    # 2. Definir parámetros para la liquidación (simulando inputs del usuario)
    print("\n2. Definiendo parámetros de prueba para la liquidación...")
    try:
        monto_recibido = float(datos_operacion.get('monto_neto_factura', 0.0))
        
        # Simular un pago 15 días tarde
        fecha_pago_esperada = datetime.strptime(datos_operacion.get('fecha_pago_calculada'), '%d-%m-%Y')
        fecha_pago_real = fecha_pago_esperada + timedelta(days=15)
        fecha_pago_real_str = fecha_pago_real.strftime('%d-%m-%Y')
        
        tasa_interes_compensatorio_pct = 3.5  # Tasa de ejemplo: 3.5%
        tasa_interes_moratorio_pct = 1.0      # Tasa de ejemplo: 1.0%

        print(f"   - Monto Recibido (simulado): {monto_recibido}")
        print(f"   - Fecha de Pago Real (simulada): {fecha_pago_real_str}")
        print(f"   - Tasa Interés Compensatorio: {tasa_interes_compensatorio_pct}%")
        print(f"   - Tasa Interés Moratorio: {tasa_interes_moratorio_pct}%")

    except (ValueError, TypeError) as e:
        print(f"   ERROR: Datos inválidos en la operación original. {e}")
        return

    # 3. Ejecutar la liquidación
    print("\n3. Ejecutando la calculadora de liquidación...")
    resultado = calcular_liquidacion(
        datos_operacion=datos_operacion,
        monto_recibido=monto_recibido,
        fecha_pago_real_str=fecha_pago_real_str,
        tasa_interes_compensatorio_pct=tasa_interes_compensatorio_pct,
        tasa_interes_moratorio_pct=tasa_interes_moratorio_pct
    )
    print("   ...Cálculo de liquidación completado.")

    # 4. Imprimir los resultados
    print("\n--- RESULTADO DE LA LIQUIDACIÓN ---")
    if 'error' in resultado:
        print(f"   ERROR al calcular la liquidación: {resultado['error']}")
    else:
        print(json.dumps(resultado, indent=4, default=str))
        print("--- FIN DEL TEST DE LIQUIDACIÓN ---")

if __name__ == '__main__':
    # Usar el proposal_id proporcionado por el usuario
    id_factura_a_liquidar = "SERVICIOS_MOBILES_INTERNACIONALES-E001-3707-24-08-25-11-21-48"
    test_liquidar_factura(id_factura_a_liquidar)
