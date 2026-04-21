# ==============================================================================
# CHATBOT/NODES — Los nodos del grafo LangGraph
# ==============================================================================
#
# Cada función es un nodo distinto del grafo.
# Cada nodo tiene UNA responsabilidad — un paso del flujo.
#
# Antes: todo en un if/elif gigante dentro de nodo_chatbot()
# Ahora: cada paso es una función separada, fácil de leer y modificar
#
# El grafo (graph.py) conecta estos nodos con edges.
# Los nodos no saben cómo están conectados — solo hacen su trabajo.
# ==============================================================================

from datetime import datetime
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from config import llm
from database.queries import actualizar_saldo, insertar_movimiento
from chatbot.prompts import construir_system_prompt
from chatbot.utils import (
    buscar_contacto, extraer_monto,
    detectar_duplicado, detectar_intencion_transferencia
)


def respuesta_directa(texto: str) -> AIMessage:
    """
    Crea una respuesta sin pasar por el LLM.
    En modo transferencia el código genera las respuestas directamente.
    Garantiza que lo que el sistema dice es exactamente lo que el código decidió.
    """
    return AIMessage(content=texto)


# ── NODO 1: CONVERSACIÓN LIBRE ─────────────────────────────────────────────
# El LLM responde con acceso al historial completo.
# Si detecta intención de transferencia, activa el flujo controlado.

def nodo_conversacion(estado: dict) -> dict:
    """
    Modo conversación — el LLM responde libremente.

    Es el único nodo donde el modelo habla.
    Para todo lo demás (transferencias), el código toma el control.
    """
    datos = estado["datos_cliente"]
    ultimo_mensaje = estado["messages"][-1].content

    # Si el usuario quiere transferir, activamos el flujo controlado
    # sin llamar al LLM — el código maneja todo
    if detectar_intencion_transferencia(ultimo_mensaje):
        nombres = [c["nombre"] for c in datos["contactos"]]
        return {
            "messages": [respuesta_directa(
                f"Con gusto te ayudo con la transferencia. "
                f"¿A quién querés transferirle? "
                f"Tus contactos habilitados son: {', '.join(nombres)}."
            )],
            "esperando": "destinatario",
            "transferencia": {},
        }

    # Conversación normal — el LLM responde con el historial completo
    # El historial crece con cada turno — más tokens, más latencia.
    # Se puede limitar con estado["messages"][-10:] si es necesario.
    system_prompt = construir_system_prompt(datos)
    respuesta = llm.invoke([
        SystemMessage(content=system_prompt),
        *estado["messages"]
        # Pasamos TODOS los mensajes anteriores + el actual.
        # El modelo los lee y "recuerda" el hilo de la conversación.
    ])

    return {"messages": [respuesta]}


# ── NODO 2: PEDIR DESTINATARIO ─────────────────────────────────────────────
# El código busca el contacto — sin LLM.

def nodo_destinatario(estado: dict) -> dict:
    """
    Procesa la respuesta del usuario cuando se le preguntó a quién transferir.
    Búsqueda determinista — no usa LLM.
    """
    datos = estado["datos_cliente"]
    ultimo_mensaje = estado["messages"][-1].content

    contacto = buscar_contacto(ultimo_mensaje, datos["contactos"])

    if contacto:
        return {
            "messages": [respuesta_directa(
                f"Perfecto. ¿Cuánto querés transferirle a {contacto['nombre']}?"
            )],
            "esperando": "monto",
            "transferencia": {
                "destinatario": contacto["nombre"],
                "cbu": contacto["cbu"],
                "alias": contacto["alias"],
                "monto": None
            }
        }
    else:
        nombres = [c["nombre"] for c in datos["contactos"]]
        return {
            "messages": [respuesta_directa(
                f"No encontré ese contacto. "
                f"Tus contactos habilitados son: {', '.join(nombres)}. "
                f"¿A cuál querés transferirle?"
            )],
            "esperando": "destinatario",
        }


# ── NODO 3: PEDIR MONTO ────────────────────────────────────────────────────
# El código extrae y valida el monto — sin LLM.

def nodo_monto(estado: dict) -> dict:
    """
    Procesa la respuesta del usuario cuando se le preguntó el monto.
    Validación con regex y chequeo de saldo — no usa LLM.
    """
    datos = estado["datos_cliente"]
    transferencia = estado.get("transferencia", {})
    ultimo_mensaje = estado["messages"][-1].content

    monto = extraer_monto(ultimo_mensaje)

    if not monto or monto <= 0:
        return {
            "messages": [respuesta_directa(
                "No entendí el monto. Escribí solo el número, por ejemplo: 5000"
            )],
            "esperando": "monto",
        }

    if monto > float(datos["cliente"]["saldo"]):
        return {
            "messages": [respuesta_directa(
                f"Saldo insuficiente. "
                f"Tu saldo disponible es ${float(datos['cliente']['saldo']):,.2f}. "
                f"¿Querés transferir un monto menor?"
            )],
            "esperando": "monto",
        }

    # Detección de duplicado
    es_duplicado = detectar_duplicado(
        datos["movimientos"], transferencia["destinatario"], monto
    )

    aviso = ""
    if es_duplicado:
        aviso = (
            f"\n\n⚠️  Ya hay una transferencia previa a "
            f"{transferencia['destinatario']} por ${monto:,.2f} "
            f"en tu historial. ¿Estás seguro de que querés hacer otra?"
        )

    resumen = (
        f"Confirmame la transferencia:\n"
        f"  • Destinatario: {transferencia['destinatario']}\n"
        f"  • Alias: {transferencia['alias']}\n"
        f"  • Monto: ${monto:,.2f}\n"
        f"  • Saldo después: ${float(datos['cliente']['saldo']) - monto:,.2f}"
        f"{aviso}\n\n"
        f"¿Confirmás? (sí / no)"
    )

    transferencia_actualizada = dict(transferencia)
    transferencia_actualizada["monto"] = monto

    return {
        "messages": [respuesta_directa(resumen)],
        "esperando": "confirmacion",
        "transferencia": transferencia_actualizada,
    }


# ── NODO 4: PEDIR CONFIRMACIÓN ─────────────────────────────────────────────
# El código espera sí o no — sin LLM.

def nodo_confirmacion(estado: dict) -> dict:
    """
    Procesa la respuesta del usuario cuando se le mostró el resumen.
    Solo acepta sí o no — en operaciones financieras no hay ambigüedades.
    """
    ultimo_mensaje = estado["messages"][-1].content

    confirmado = any(p in ultimo_mensaje.lower()
                    for p in ["si", "sí", "confirmo", "dale", "ok", "yes"])
    cancelado  = any(p in ultimo_mensaje.lower()
                    for p in ["no", "cancelar", "cancelá", "nope"])

    if confirmado:
        # Llamamos directamente a nodo_ejecutar en lugar de cambiar el estado
        # y esperar otro turno. Así evitamos el turno extra que causaba el doble "si".
        # nodo_confirmacion decide, nodo_ejecutar actúa — en el mismo turno.
        return nodo_ejecutar(estado)

    elif cancelado:
        return {
            "messages": [respuesta_directa(
                "Transferencia cancelada. ¿En qué más puedo ayudarte?"
            )],
            "esperando": "",
            "transferencia": {},
        }
    else:
        return {
            "messages": [respuesta_directa(
                "Por favor respondé 'sí' para confirmar o 'no' para cancelar."
            )],
            "esperando": "confirmacion",
        }


# ── NODO 5: EJECUTAR TRANSFERENCIA ─────────────────────────────────────────
# El único nodo que escribe en la DB. Completamente determinista.

def nodo_ejecutar(estado: dict) -> dict:
    """
    Ejecuta la transferencia confirmada.

    Este es el único nodo que modifica datos reales.
    En producción llamaría a la API del banco.
    Acá ejecuta dos operaciones SQL en Neon.

    Por qué es un nodo separado:
    Separar la confirmación de la ejecución es una práctica de seguridad.
    El nodo de confirmación solo decide. El nodo de ejecución solo actúa.
    Si algo falla en la ejecución, es fácil identificar dónde.
    """
    datos = estado["datos_cliente"]
    transferencia = estado.get("transferencia", {})
    monto = transferencia["monto"]
    nuevo_saldo = float(datos["cliente"]["saldo"]) - monto
    dni = datos["cliente"]["dni"]

    # Dos operaciones SQL — atómicas y precisas
    actualizar_saldo(dni, nuevo_saldo)
    insertar_movimiento(
        dni,
        f"Transferencia a {transferencia['destinatario']}",
        -monto
    )

    # Actualizamos el estado local para reflejar el nuevo saldo
    datos["cliente"]["saldo"] = nuevo_saldo
    datos["movimientos"].append({
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "descripcion": f"Transferencia a {transferencia['destinatario']}",
        "monto": -monto
    })

    return {
        "messages": [respuesta_directa(
            f"✓ Transferencia realizada.\n"
            f"  • ${monto:,.2f} enviados a {transferencia['destinatario']}\n"
            f"  • Tu nuevo saldo: ${nuevo_saldo:,.2f}"
        )],
        "datos_cliente": datos,
        "esperando": "",
        "transferencia": {},
        # Señal para el main — registrar en el log de auditoría
        "operacion_registrar": {
            "tipo": "transferencia",
            "destinatario": transferencia["destinatario"],
            "monto": monto,
            "hora": datetime.now().strftime("%H:%M:%S"),
            "estado": "ejecutada"
        }
    }