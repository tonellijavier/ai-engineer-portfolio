# ==============================================================================
# CHATBOT/GRAPH — Construcción del grafo LangGraph
# ==============================================================================
#
# Este archivo define la ESTRUCTURA del grafo:
#   - Qué nodos existen
#   - Cómo se conectan
#   - Cuáles son las decisiones (edges condicionales)
#
# No tiene lógica de negocio — solo el mapa del flujo.
# Si querés entender qué hace cada paso, mirá nodes.py.
# ==============================================================================

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from chatbot.nodes import (
    nodo_conversacion,
    nodo_destinatario,
    nodo_monto,
    nodo_confirmacion,
    nodo_ejecutar,
)


# ── ESTADO ────────────────────────────────────────────────────────────────────
#
# El formulario compartido entre todos los nodos.
# Cada nodo puede leer cualquier campo y actualizar los que necesite.
#
# 'esperando' es la clave del flujo:
#   ""             → conversación libre → nodo_conversacion
#   "destinatario" → esperando a quién → nodo_destinatario
#   "monto"        → esperando cuánto  → nodo_monto
#   "confirmacion" → esperando sí/no   → nodo_confirmacion
#   "ejecutar"     → confirmado        → nodo_ejecutar

class Estado(TypedDict):
    messages: Annotated[list, add_messages]
    # add_messages acumula mensajes en lugar de reemplazarlos.
    # Es lo que le da memoria al chatbot entre turnos.

    datos_cliente: dict    # datos cargados desde PostgreSQL al inicio
    esperando: str         # controla a qué nodo va el grafo
    transferencia: dict    # datos de la transferencia en curso
    operacion_registrar: dict  # señal temporal para el log de auditoría


# ── FUNCIÓN DE DECISIÓN ───────────────────────────────────────────────────────
# LangGraph llama a esta función después de cada nodo para decidir el siguiente.

def decidir_siguiente_nodo(estado: Estado) -> str:
    """
    Lee el campo 'esperando' del estado y decide a qué nodo ir.

    Esta es la diferencia real entre LangGraph y LangChain:
    LangChain va siempre en línea recta.
    LangGraph puede ir a nodos distintos según el estado — incluso volver atrás.
    """
    esperando = estado.get("esperando", "")

    if esperando == "destinatario":
        return "destinatario"
    elif esperando == "monto":
        return "monto"
    elif esperando == "confirmacion":
        return "confirmacion"
    elif esperando == "ejecutar":
        return "ejecutar"
    else:
        return "conversacion"


# ── CONSTRUCCIÓN DEL GRAFO ────────────────────────────────────────────────────

def construir_grafo():
    """
    Arma el grafo completo con todos los nodos y edges.

    El grafo ejecuta UN turno y termina (add_edge → END).
    El loop de conversación lo maneja el while True en main.py.
    """
    grafo = StateGraph(Estado)

    # Registramos cada nodo — nombre → función
    grafo.add_node("conversacion",  nodo_conversacion)
    grafo.add_node("destinatario",  nodo_destinatario)
    grafo.add_node("monto",         nodo_monto)
    grafo.add_node("confirmacion",  nodo_confirmacion)
    grafo.add_node("ejecutar",      nodo_ejecutar)

    # Punto de entrada — siempre empieza por el router
    grafo.set_entry_point("router")

    # Nodo router — decide a qué nodo ir según el estado
    # Es un nodo "transparente" que solo lee el estado y redirige
    grafo.add_node("router", lambda estado: {})
    grafo.add_conditional_edges(
        "router",
        decidir_siguiente_nodo,
        {
            "conversacion":  "conversacion",
            "destinatario":  "destinatario",
            "monto":         "monto",
            "confirmacion":  "confirmacion",
            "ejecutar":      "ejecutar",
        }
    )

    # Todos los nodos terminan en END — el main los vuelve a invocar
    for nodo in ["conversacion", "destinatario", "monto", "confirmacion", "ejecutar"]:
        grafo.add_edge(nodo, END)

    return grafo.compile()