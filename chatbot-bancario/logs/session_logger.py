# ==============================================================================
# LOGS/SESSION_LOGGER — Guardado de logs de sesión
# ==============================================================================
#
# Guarda DOS tipos de log separados en un mismo archivo JSON:
#
#   'operaciones' = log de auditoría
#       Solo lo que se ejecutó: qué, cuándo, cuánto, a quién.
#       Los bancos están obligados por regulación a guardar esto.
#       Inmutable — no se modifica después.
#
#   'conversacion' = log de diálogo
#       Todos los mensajes del chat en orden.
#       Para mejorar el bot, analizar patrones y dar soporte.
#
# ¿Por qué separado?
# Si mañana querés guardar los logs en una DB en lugar de archivos,
# solo tocás este archivo.
# ==============================================================================

import json
from datetime import datetime


def guardar_log_sesion(messages: list, saldo_inicial: float,
                       datos_finales: dict, operaciones: list):
    """Guarda el log completo de la sesión en un archivo JSON."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"sesion_{timestamp}.json"

    conversacion = [
        {
            "rol": "usuario" if msg.__class__.__name__ == "HumanMessage" else "bot",
            "contenido": msg.content,
        }
        for msg in messages
    ]

    log = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cliente": datos_finales["cliente"]["nombre"],
        "dni": datos_finales["cliente"]["dni"],
        "resumen": {
            "saldo_inicial": saldo_inicial,
            "saldo_final": float(datos_finales["cliente"]["saldo"]),
            "diferencia": float(datos_finales["cliente"]["saldo"]) - saldo_inicial,
            "total_operaciones": len(operaciones),
            "total_turnos": len([m for m in conversacion if m["rol"] == "usuario"]),
        },
        "operaciones": operaciones,    # log de auditoría — oficial
        "conversacion": conversacion,  # log de diálogo — analítico
    }

    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2, default=str)

    print(f"   ✓ Log guardado: {nombre_archivo}")
    if operaciones:
        print(f"   ✓ Operaciones registradas: {len(operaciones)}")
    print(f"   ✓ Saldo: ${saldo_inicial:,.2f} → ${float(datos_finales['cliente']['saldo']):,.2f}")