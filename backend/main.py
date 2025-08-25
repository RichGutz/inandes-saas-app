
import sys
import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware

# --- Configuración de Path para Módulos ---
# Añadir el directorio raíz del proyecto al path de Python
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Importar las funciones de los módulos usando rutas relativas al proyecto
from backend.calculadora_factoring_V_CLI import calcular_desembolso_inicial, encontrar_tasa_de_avance
from liquidacion.backend.calculadora_liquidacion import calcular_liquidacion
from backend.supabase_handler import get_proposal_details_by_id


app = FastAPI(
    title="API de Calculadora de Factoring INANDES",
    description="Provee endpoints para los cálculos de factoring.",
    version="2.0.0",
)

# --- Middleware de CORS ---
# Permite que el frontend (ej. en Vercel) se comunique con este backend (ej. en Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, deberías restringir esto a tu dominio de frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modelos de Datos (Pydantic) ---

class CalcularDesembolsoRequest(BaseModel):
    plazo_operacion: int
    mfn: float
    tasa_avance: float
    interes_mensual: float
    comision_estructuracion_pct: float
    comision_minima_aplicable: float
    igv_pct: float
    comision_afiliacion_aplicable: float = 0.0
    aplicar_comision_afiliacion: bool = False

class EncontrarTasaRequest(BaseModel):
    plazo_operacion: int
    mfn: float
    interes_mensual: float
    comision_estructuracion_pct: float
    igv_pct: float
    monto_objetivo: float
    comision_minima_aplicable: float
    comision_afiliacion_aplicable: float = 0.0
    aplicar_comision_afiliacion: bool = False

class LiquidarFacturaRequest(BaseModel):
    proposal_id: str
    monto_recibido: float
    fecha_pago_real: str
    tasa_interes_compensatorio_pct: float
    tasa_interes_moratorio_pct: float

# --- Endpoints de la API ---

@app.get("/")
async def read_root():
    return {"message": "Bienvenido a la API de la Calculadora de Factoring v2"}

@app.post("/calcular_desembolso")
async def calcular_desembolso_endpoint(request: CalcularDesembolsoRequest):
    """
    Endpoint para el Modo 1: Cálculo Directo.
    """
    resultado = calcular_desembolso_inicial(**request.dict(exclude_unset=False))
    return resultado

@app.post("/encontrar_tasa")
async def encontrar_tasa_endpoint(request: EncontrarTasaRequest):
    """
    Endpoint para el Modo 2: Búsqueda de Tasa de Avance.
    """
    resultado = encontrar_tasa_de_avance(**request.dict(exclude_unset=False))
    return resultado

@app.post("/liquidar_factura")
async def liquidar_factura_endpoint(request: LiquidarFacturaRequest):
    """
    Endpoint para el Módulo de Liquidación.
    """
    # 1. Obtener los datos de la operación desde Supabase
    datos_operacion = get_proposal_details_by_id(request.proposal_id)

    if not datos_operacion or 'error' in datos_operacion:
        return {"error": f"No se pudieron obtener los datos para la propuesta con ID {request.proposal_id}"}

    # --- INICIO DEL PARCHEO DE DATOS ---
    import json
    recalc_json_str = datos_operacion.get('recalculate_result_json')
    if recalc_json_str:
        try:
            recalc_data = json.loads(recalc_json_str)
            calculos = recalc_data.get('calculo_con_tasa_encontrada', {})
            desglose = recalc_data.get('desglose_final_detallado', {})
            
            datos_operacion['capital_calculado'] = calculos.get('capital')
            datos_operacion['interes_calculado'] = desglose.get('interes', {}).get('monto')
            datos_operacion['margen_seguridad_calculado'] = desglose.get('margen_seguridad', {}).get('monto')
        except json.JSONDecodeError:
            # No hacer nada si el JSON está corrupto, la función de cálculo manejará los errores
            pass
    # --- FIN DEL PARCHEO DE DATOS ---

    # 2. Ejecutar la liquidación
    resultado = calcular_liquidacion(
        datos_operacion=datos_operacion,
        monto_recibido=request.monto_recibido,
        fecha_pago_real_str=request.fecha_pago_real,
        tasa_interes_compensatorio_pct=request.tasa_interes_compensatorio_pct,
        tasa_interes_moratorio_pct=request.tasa_interes_moratorio_pct
    )

    return resultado

# Para ejecutar la aplicación localmente:
# uvicorn main:app --reload
