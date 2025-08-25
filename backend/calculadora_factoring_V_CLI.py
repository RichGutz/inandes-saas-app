


import datetime
import math
import json

def calcular_desembolso_inicial(
    plazo_operacion: int,
    mfn: float,
    tasa_avance: float,
    interes_mensual: float,
    comision_estructuracion_pct: float,
    comision_minima_aplicable: float,
    igv_pct: float,
    comision_afiliacion_aplicable: float = 0.0,
    aplicar_comision_afiliacion: bool = False
) -> dict:
    """
    Función adaptadora para mantener compatibilidad con interfaces antiguas (como Streamlit)
    que envían una factura a la vez.
    """
    # 1. Empaquetar los argumentos de la factura individual en un diccionario.
    datos_factura = {
        "plazo_operacion": plazo_operacion,
        "mfn": mfn,
        "tasa_avance": tasa_avance,
        "interes_mensual": interes_mensual,
        "comision_estructuracion_pct": comision_estructuracion_pct,
        "comision_minima_aplicable": comision_minima_aplicable,
        "igv_pct": igv_pct,
        "comision_afiliacion_aplicable": comision_afiliacion_aplicable,
        "aplicar_comision_afiliacion": aplicar_comision_afiliacion
    }

    # 2. Convertir la factura individual en un lote de una sola factura.
    lote_de_una_factura = [datos_factura]

    # 3. Llamar a la nueva función de procesamiento de lotes.
    resultado_lote = procesar_lote_desembolso_inicial(lote_de_una_factura)

    # 4. Extraer y devolver el resultado de la única factura del lote.
    if resultado_lote and resultado_lote.get("resultados_por_factura"):
        return resultado_lote["resultados_por_factura"][0]
    else:
        # Devuelve el error que pudo haber generado la función de lote
        return resultado_lote if isinstance(resultado_lote, dict) and "error" in resultado_lote else {
            "error": "El cálculo para el lote no produjo resultados."
        }

def _calcular_desglose_factura(
    plazo_operacion: int,
    mfn: float,
    tasa_avance: float,
    interes_mensual: float,
    comision_estructuracion_fija: float, # Ya no se calcula con MAX, se recibe el valor final
    igv_pct: float,
    comision_afiliacion_aplicable: float = 0.0,
    aplicar_comision_afiliacion: bool = False
) -> dict:
    """
    Calcula los detalles de una operación de factoring para UNA factura.
    Esta es una función auxiliar que asume que la lógica de comisión ya fue resuelta.
    """
    if plazo_operacion < 0:
        return {"error": "El plazo de operación no puede ser negativo."}

    valor_neto_real = mfn
    capital = valor_neto_real * tasa_avance
    tasa_diaria = interes_mensual / 30
    interes = capital * (((1 + tasa_diaria) ** plazo_operacion) - 1)
    igv_interes = interes * igv_pct

    # La comisión de estructuración ahora es un valor fijo que se pasa como argumento
    comision_estructuracion = comision_estructuracion_fija
    igv_comision = comision_estructuracion * igv_pct

    abono_real_teorico = capital - interes - igv_interes - comision_estructuracion - igv_comision

    comision_afiliacion = 0.0
    igv_afiliacion = 0.0
    if aplicar_comision_afiliacion:
        comision_afiliacion = comision_afiliacion_aplicable
        igv_afiliacion = comision_afiliacion * igv_pct
        abono_real_teorico -= (comision_afiliacion + igv_afiliacion)

    monto_desembolsar = math.floor(abono_real_teorico)
    margen_seguridad = valor_neto_real - capital

    return {
        "capital": round(capital, 2),
        "interes": round(interes, 2),
        "igv_interes": round(igv_interes, 2),
        "comision_estructuracion": round(comision_estructuracion, 2),
        "igv_comision": round(igv_comision, 2),
        "comision_afiliacion": round(comision_afiliacion, 2),
        "igv_afiliacion": round(igv_afiliacion, 2),
        "abono_real_teorico": round(abono_real_teorico, 2),
        "monto_desembolsado": round(monto_desembolsar, 2),
        "margen_seguridad": round(margen_seguridad, 2),
        "plazo_operacion": plazo_operacion
    }

def procesar_lote_desembolso_inicial(lote_datos: list) -> dict:
    """
    Orquesta el cálculo del desembolso para un lote de facturas,
    aplicando la lógica de comisión agregada y corrigiendo el total por redondeo.
    """
    if not lote_datos:
        return {"error": "El lote de datos no puede estar vacío."}

    # --- FASE 1: Decisión Agregada sobre la Comisión ---
    capital_total_agregado = 0
    comision_prorrateada_total = 0
    
    parametros_generales = lote_datos[0]
    comision_estructuracion_pct = parametros_generales.get("comision_estructuracion_pct", 0)
    
    for datos_factura in lote_datos:
        capital_individual = datos_factura.get("mfn", 0) * datos_factura.get("tasa_avance", 0)
        capital_total_agregado += capital_individual
        comision_prorrateada_total += datos_factura.get("comision_minima_aplicable", 0)

    comision_porcentual_agregada = capital_total_agregado * comision_estructuracion_pct

    if comision_porcentual_agregada > comision_prorrateada_total:
        metodo_de_comision_elegido = "PORCENTAJE"
    else:
        metodo_de_comision_elegido = "PRORRATEADO"

    # --- FASE 2: Cálculo Individual con la Decisión ya Tomada ---
    resultados_finales = []
    for datos_factura in lote_datos:
        capital_individual = datos_factura.get("mfn", 0) * datos_factura.get("tasa_avance", 0)
        
        if metodo_de_comision_elegido == "PORCENTAJE":
            comision_para_esta_factura = capital_individual * comision_estructuracion_pct
        else: # PRORRATEADO
            comision_para_esta_factura = datos_factura.get("comision_minima_aplicable", 0)
            
        resultado_factura = _calcular_desglose_factura(
            plazo_operacion=datos_factura.get("plazo_operacion"),
            mfn=datos_factura.get("mfn"),
            tasa_avance=datos_factura.get("tasa_avance"),
            interes_mensual=datos_factura.get("interes_mensual"),
            comision_estructuracion_fija=comision_para_esta_factura,
            igv_pct=datos_factura.get("igv_pct"),
            comision_afiliacion_aplicable=datos_factura.get("comision_afiliacion_aplicable", 0),
            aplicar_comision_afiliacion=datos_factura.get("aplicar_comision_afiliacion", False)
        )
        resultados_finales.append(resultado_factura)
        
    # --- FASE 3: Corrección de Totales por Redondeo ---
    if metodo_de_comision_elegido == "PRORRATEADO":
        total_comision_corregido = comision_prorrateada_total
    else:
        total_comision_corregido = sum(c['comision_estructuracion'] for c in resultados_finales)

    return {
        "metodo_comision_elegido": metodo_de_comision_elegido,
        "comision_estructuracion_total_corregida": round(total_comision_corregido, 2),
        "resultados_por_factura": resultados_finales
    }


def encontrar_tasa_de_avance(
    plazo_operacion: int,
    mfn: float,
    interes_mensual: float,
    comision_estructuracion_pct: float,
    igv_pct: float,
    monto_objetivo: float,
    comision_minima_aplicable: float,
    comision_afiliacion_aplicable: float = 0.0,
    aplicar_comision_afiliacion: bool = False,
    # Parámetros no utilizados de la versión anterior, se mantienen por compatibilidad
    tasa_avance_min: float = 0.90,
    tasa_avance_max: float = 1.00,
    tolerancia: float = 0.01,
    max_iteraciones: int = 100
) -> dict:
    """
    (NOTA: Esta función aún contiene la lógica de comisión individual y necesita ser refactorizada
    de manera similar a 'procesar_lote_desembolso_inicial' para funcionar por lotes.)
    Encuentra la tasa de avance necesaria para un monto objetivo, usando la lógica de doble cálculo agnóstica.
    """
    valor_neto_real = mfn
    if valor_neto_real == 0:
        return {"error": "El Monto Neto de Factura (mfn) no puede ser cero."}

    tasa_diaria = interes_mensual / 30
    factor_interes = ((1 + tasa_diaria) ** plazo_operacion) - 1
    
    costo_fijo_afiliacion = 0.0
    if aplicar_comision_afiliacion:
        costo_fijo_afiliacion = comision_afiliacion_aplicable * (1 + igv_pct)

    # --- CÁLCULO A: Asumiendo Comisión de Estructuración como PORCENTAJE ---
    costo_variable_A = (factor_interes + comision_estructuracion_pct) * (1 + igv_pct)
    capital_A = 0
    if (1 - costo_variable_A) > 0:
        capital_A = (monto_objetivo + costo_fijo_afiliacion) / (1 - costo_variable_A)

    # --- CÁLCULO B: Asumiendo Comisión de Estructuración como MÍNIMO FIJO ---
    costo_variable_B = factor_interes * (1 + igv_pct)
    costo_fijo_estructuracion = comision_minima_aplicable * (1 + igv_pct)
    costos_fijos_totales_B = costo_fijo_estructuracion + costo_fijo_afiliacion
    capital_B = 0
    if (1 - costo_variable_B) > 0:
        capital_B = (monto_objetivo + costos_fijos_totales_B) / (1 - costo_variable_B)

    capital_necesario = max(capital_A, capital_B)

    capital = capital_necesario
    interes = capital * factor_interes
    igv_interes = interes * igv_pct
    
    comision_estructuracion = max(capital * comision_estructuracion_pct, comision_minima_aplicable)
    igv_comision_estructuracion = comision_estructuracion * igv_pct
    
    comision_afiliacion = 0.0
    igv_afiliacion = 0.0
    if aplicar_comision_afiliacion:
        comision_afiliacion = comision_afiliacion_aplicable
        igv_afiliacion = comision_afiliacion * igv_pct
    
    abono_real = capital - interes - igv_interes - comision_estructuracion - igv_comision_estructuracion - comision_afiliacion - igv_afiliacion
    margen_seguridad = valor_neto_real - capital
    total_igv = igv_interes + igv_comision_estructuracion + igv_afiliacion
    
    tasa_avance_encontrada = capital / valor_neto_real if valor_neto_real else 0

    desglose_final_detallado = {}
    if valor_neto_real > 0:
        desglose_final_detallado = {
            "abono": { "monto": round(abono_real, 2), "porcentaje": round((abono_real / valor_neto_real) * 100, 3) },
            "interes": { "monto": round(interes, 2), "porcentaje": round((interes / valor_neto_real) * 100, 3) },
            "comision_estructuracion": { "monto": round(comision_estructuracion, 2), "porcentaje": round((comision_estructuracion / valor_neto_real) * 100, 3) },
            "comision_afiliacion": { "monto": round(comision_afiliacion, 2), "porcentaje": round((comision_afiliacion / valor_neto_real) * 100, 3) },
            "igv_total": { "monto": round(total_igv, 2), "porcentaje": round((total_igv / valor_neto_real) * 100, 3) },
            "margen_seguridad": { "monto": round(margen_seguridad, 2), "porcentaje": round((margen_seguridad / valor_neto_real) * 100, 3) }
        }

    return {
        "resultado_busqueda": {
            "tasa_avance_encontrada": round(tasa_avance_encontrada, 6),
            "abono_real_calculado": round(abono_real, 2),
            "monto_objetivo": monto_objetivo
        },
        "calculo_con_tasa_encontrada": {
            "capital": round(capital, 2),
            "interes": round(interes, 2),
            "igv_interes": round(igv_interes, 2),
            "comision_estructuracion": round(comision_estructuracion, 2),
            "igv_comision_estructuracion": round(igv_comision_estructuracion, 2),
            "comision_afiliacion": round(comision_afiliacion, 2),
            "igv_afiliacion": round(igv_afiliacion, 2),
            "margen_seguridad": round(margen_seguridad, 2),
            "plazo_operacion": plazo_operacion
        },
        "desglose_final_detallado": desglose_final_detallado
    }

if __name__ == '__main__':
    # --- CASO 1: Prueba donde gana el método PORCENTAJE ---
    print("--- CASO 1: GANA MÉTODO PORCENTAJE ---")
    lote_caso_1 = [
        {"plazo_operacion": 98, "mfn": 18795.09, "tasa_avance": 0.95, "interes_mensual": 0.02, "comision_estructuracion_pct": 0.015, "comision_minima_aplicable": 66.67, "igv_pct": 0.18},
        {"plazo_operacion": 98, "mfn": 7941.47, "tasa_avance": 0.95, "interes_mensual": 0.02, "comision_estructuracion_pct": 0.015, "comision_minima_aplicable": 66.67, "igv_pct": 0.18},
        {"plazo_operacion": 98, "mfn": 5507.67, "tasa_avance": 0.95, "interes_mensual": 0.02, "comision_estructuracion_pct": 0.015, "comision_minima_aplicable": 66.66, "igv_pct": 0.18}
    ]
    resultado_lote_1 = procesar_lote_desembolso_inicial(lote_caso_1)
    print(f"Método Elegido: {resultado_lote_1['metodo_comision_elegido']}")
    comisiones_1 = [r['comision_estructuracion'] for r in resultado_lote_1['resultados_por_factura']]
    print(f"Comisiones Individuales: {comisiones_1}")
    print(f"Suma de Comisiones Individuales: {round(sum(comisiones_1), 2)}")
    print(f"TOTAL OFICIAL CORREGIDO: {resultado_lote_1['comision_estructuracion_total_corregida']}")

    # --- CASO 2: Prueba donde gana el método PRORRATEADO (para probar el ajuste de redondeo) ---
    print("\n--- CASO 2: GANA MÉTODO PRORRATEADO ---")
    lote_caso_2 = [
        {"plazo_operacion": 98, "mfn": 1000, "tasa_avance": 0.90, "interes_mensual": 0.02, "comision_estructuracion_pct": 0.01, "comision_minima_aplicable": 66.67, "igv_pct": 0.18},
        {"plazo_operacion": 98, "mfn": 1000, "tasa_avance": 0.90, "interes_mensual": 0.02, "comision_estructuracion_pct": 0.01, "comision_minima_aplicable": 66.67, "igv_pct": 0.18},
        {"plazo_operacion": 98, "mfn": 1000, "tasa_avance": 0.90, "interes_mensual": 0.02, "comision_estructuracion_pct": 0.01, "comision_minima_aplicable": 66.66, "igv_pct": 0.18}
    ]
    resultado_lote_2 = procesar_lote_desembolso_inicial(lote_caso_2)
    print(f"Método Elegido: {resultado_lote_2['metodo_comision_elegido']}")
    comisiones_2 = [r['comision_estructuracion'] for r in resultado_lote_2['resultados_por_factura']]
    print(f"Comisiones Individuales: {comisiones_2}")
    print(f"Suma de Comisiones Individuales (potencialmente con error): {round(sum(comisiones_2), 2)}")
    print(f"TOTAL OFICIAL CORREGIDO: {resultado_lote_2['comision_estructuracion_total_corregida']}")



