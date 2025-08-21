
import datetime
import math

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
    Calcula los detalles de una operación de factoring basándose en una tasa de avance fija.
    Es agnóstico a la moneda; requiere que las comisiones correctas ya vengan en el payload.
    """
    if plazo_operacion < 0:
        return {"error": "El plazo de operación no puede ser negativo."}

    valor_neto_real = mfn
    capital = valor_neto_real * tasa_avance
    tasa_diaria = interes_mensual / 30
    interes = capital * (((1 + tasa_diaria) ** plazo_operacion) - 1)
    igv_interes = interes * igv_pct

    comision_estructuracion_base = capital * comision_estructuracion_pct
    comision_estructuracion = max(comision_estructuracion_base, comision_minima_aplicable)
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
    # --- Prueba en PEN ---
    print("---" + " PRUEBA EN SOLES (PEN) " + "---")
    datos_prueba_pen = {
        "plazo_operacion": 53,
        "mfn": 8178.82,
        "tasa_avance": 0.98,
        "interes_mensual": 0.0125,
        "comision_estructuracion_pct": 0.005,
        "comision_minima_aplicable": 10.0, # Valor PEN
        "igv_pct": 0.18,
        "comision_afiliacion_aplicable": 200.0, # Valor PEN
        "aplicar_comision_afiliacion": True
    }
    resultado_inicial_pen = calcular_desembolso_inicial(**datos_prueba_pen)
    print(f"[PEN] Abono Teórico Inicial: {resultado_inicial_pen.get('abono_real_teorico')}")
    
    monto_objetivo_pen = math.floor(resultado_inicial_pen.get('abono_real_teorico', 0) / 10) * 10
    print(f"[PEN] Monto Objetivo Redondeado: {monto_objetivo_pen}")

    datos_busqueda_pen = {
        k: v for k, v in datos_prueba_pen.items() if k != 'tasa_avance'
    }
    datos_busqueda_pen["monto_objetivo"] = monto_objetivo_pen
    
    resultado_final_pen = encontrar_tasa_de_avance(**datos_busqueda_pen)
    import json
    print("[PEN] Resultado Final:")
    print(json.dumps(resultado_final_pen, indent=4))

    # --- Prueba en USD ---
    print("\n" + "---" + " PRUEBA EN DÓLARES (USD) " + "---")
    datos_prueba_usd = {
        "plazo_operacion": 10, # Menos de 15 para probar la regla
        "mfn": 5000.00,
        "tasa_avance": 0.97,
        "interes_mensual": 0.0125,
        "comision_estructuracion_pct": 0.005,
        "comision_minima_aplicable": 3.0, # Valor USD
        "igv_pct": 0.18,
        "comision_afiliacion_aplicable": 50.0, # Valor USD
        "aplicar_comision_afiliacion": True
    }
    resultado_inicial_usd = calcular_desembolso_inicial(**datos_prueba_usd)
    print(f"[USD] Abono Teórico Inicial: {resultado_inicial_usd.get('abono_real_teorico')}")
    
    monto_objetivo_usd = math.floor(resultado_inicial_usd.get('abono_real_teorico', 0) / 10) * 10
    print(f"[USD] Monto Objetivo Redondeado: {monto_objetivo_usd}")

    datos_busqueda_usd = {
        k: v for k, v in datos_prueba_usd.items() if k != 'tasa_avance'
    }
    datos_busqueda_usd["monto_objetivo"] = monto_objetivo_usd
    
    resultado_final_usd = encontrar_tasa_de_avance(**datos_busqueda_usd)
    print("[USD] Resultado Final:")
    print(json.dumps(resultado_final_usd, indent=4))

