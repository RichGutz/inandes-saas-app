
import datetime

def _safe_get(data: dict, key: str, default_value=0, target_type=float):
    """
    Safely gets a value from a dictionary, handles None, and converts its type.
    """
    value = data.get(key)
    if value is None:
        return default_value
    try:
        return target_type(value)
    except (ValueError, TypeError):
        return default_value

def calcular_liquidacion(
    datos_operacion: dict,
    monto_recibido: float,
    fecha_pago_real_str: str,
    tasa_interes_compensatorio_pct: float,
    tasa_interes_moratorio_pct: float
) -> dict:
    """
    Calcula la liquidación de una operación de factoring.
    """
    try:
        # 1. Extraer y validar datos clave
        fecha_pago_esperada_str = datos_operacion.get('fecha_pago_calculada')
        if not fecha_pago_esperada_str:
            raise ValueError("La 'fecha_pago_calculada' es inválida o no fue encontrada.")

        monto_pago_esperado = _safe_get(datos_operacion, 'monto_neto_factura')
        capital_desembolsado = _safe_get(datos_operacion, 'capital_calculado')
        margen_seguridad_inicial = _safe_get(datos_operacion, 'margen_seguridad_calculado')
        interes_original = _safe_get(datos_operacion, 'interes_calculado')
        plazo_operacion_original = _safe_get(datos_operacion, 'plazo_operacion_calculado', target_type=int)
        interes_mensual_pct = _safe_get(datos_operacion, 'interes_mensual')
        igv_pct = 0.18

        fecha_pago_esperada = datetime.datetime.strptime(fecha_pago_esperada_str, '%d-%m-%Y')
        fecha_pago_real = datetime.datetime.strptime(fecha_pago_real_str, '%d-%m-%Y')

    except (ValueError, TypeError, AttributeError) as e:
        return {"error": f"Error en los datos de entrada: {e}"}

    # 2. Calcular diferencias y tasas
    dias_diferencia = (fecha_pago_real - fecha_pago_esperada).days
    diferencia_monto_pago = monto_pago_esperado - monto_recibido
    tasa_diaria_compensatoria = (tasa_interes_compensatorio_pct / 100) / 30
    tasa_diaria_moratoria = (tasa_interes_moratorio_pct / 100) / 30

    # 3. Inicializar variables
    interes_compensatorio, igv_interes_compensatorio = 0, 0
    interes_moratorio, igv_interes_moratorio = 0, 0
    interes_a_devolver, igv_interes_a_devolver = 0, 0

    # 4. Lógica de cálculo principal
    if dias_diferencia > 0:  # Pago Tardío
        interes_compensatorio = capital_desembolsado * (pow(1 + tasa_diaria_compensatoria, dias_diferencia) - 1)
        igv_interes_compensatorio = interes_compensatorio * igv_pct
        base_moratorio = capital_desembolsado + interes_compensatorio
        interes_moratorio = base_moratorio * (pow(1 + tasa_diaria_moratoria, dias_diferencia) - 1)
        igv_interes_moratorio = interes_moratorio * igv_pct

    elif dias_diferencia < 0:  # Pago Anticipado
        dias_anticipacion = abs(dias_diferencia)
        tasa_diaria_original = (interes_mensual_pct / 100) / 30
        plazo_real = plazo_operacion_original - dias_anticipacion
        if plazo_real < 0: plazo_real = 0
        interes_real_calculado = capital_desembolsado * (((1 + tasa_diaria_original) ** plazo_real) - 1)
        interes_a_devolver = interes_original - interes_real_calculado
        igv_interes_a_devolver = interes_a_devolver * igv_pct

    # 5. Calcular saldo final
    total_cargos = (interes_compensatorio + igv_interes_compensatorio) + (interes_moratorio + igv_interes_moratorio) + diferencia_monto_pago
    total_creditos = interes_a_devolver + igv_interes_a_devolver
    saldo_final = margen_seguridad_inicial - total_cargos + total_creditos

    # 6. Generar Proyección Futura si hay deuda remanente
    proyeccion_futura = []
    if dias_diferencia > 0 and diferencia_monto_pago > 0 and saldo_final < 0:
        nuevo_capital = abs(saldo_final)
        fecha_proyeccion = fecha_pago_real
        for dia in range(1, 31):
            fecha_proyeccion += datetime.timedelta(days=1)
            
            # Calcular intereses diarios sobre el nuevo capital
            int_comp_diario = nuevo_capital * tasa_diaria_compensatoria
            igv_int_comp_diario = int_comp_diario * igv_pct

            base_mora_diario = nuevo_capital + int_comp_diario + igv_int_comp_diario
            int_mora_diario = base_mora_diario * tasa_diaria_moratoria
            igv_int_mora_diario = int_mora_diario * igv_pct
            
            # Acumular el capital (incluyendo IGV)
            nuevo_capital += int_comp_diario + igv_int_comp_diario + int_mora_diario + igv_int_mora_diario
            
            proyeccion_futura.append({
                "dia": dia,
                "fecha": fecha_proyeccion.strftime('%d-%m-%Y'),
                "capital_proyectado": round(nuevo_capital, 2),
                "interes_compensatorio_diario": round(int_comp_diario, 2),
                "igv_interes_compensatorio_diario": round(igv_int_comp_diario, 2),
                "interes_moratorio_diario": round(int_mora_diario, 2),
                "igv_interes_moratorio_diario": round(igv_int_mora_diario, 2)
            })

    # 7. Preparar el resultado final
    resultado_liquidacion = {
        "dias_diferencia": dias_diferencia,
        "tipo_pago": "Tardío" if dias_diferencia > 0 else ("Anticipado" if dias_diferencia < 0 else "A Tiempo"),
        "diferencia_por_monto_recibido": round(diferencia_monto_pago, 2),
        "desglose_cargos": {
            "interes_compensatorio": round(interes_compensatorio, 2),
            "igv_interes_compensatorio": round(igv_interes_compensatorio, 2),
            "interes_moratorio": round(interes_moratorio, 2),
            "igv_interes_moratorio": round(igv_interes_moratorio, 2),
            "total_cargos": round(total_cargos, 2)
        },
        "desglose_creditos": {
            "interes_a_devolver": round(interes_a_devolver, 2),
            "igv_interes_a_devolver": round(igv_interes_a_devolver, 2),
            "total_creditos": round(total_creditos, 2)
        },
        "liquidacion_final": {
            "margen_seguridad_inicial": round(margen_seguridad_inicial, 2),
            "saldo_final_a_liquidar": round(saldo_final, 2)
        },
        "proyeccion_futura": proyeccion_futura
    }

    return resultado_liquidacion
