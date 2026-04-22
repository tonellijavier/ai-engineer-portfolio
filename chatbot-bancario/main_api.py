# ==============================================================================
# MAIN_API.PY — Chatbot Bancario expuesto como API REST con FastAPI
# ==============================================================================
#
# Convierte el chatbot bancario en un servicio HTTP.
# Cualquier frontend (web, móvil, WhatsApp) puede consumirlo
# sin saber nada de Python, LangGraph ni Groq.
#
# El frontend solo sabe:
#   POST /sesion/nueva  → crear sesión
#   POST /chat          → enviar mensaje
#   GET  /sesion/{id}   → ver estado actual
#
# PARA CORRERLO:
#   uvicorn main_api:app --reload
#
# DOCUMENTACIÓN AUTOMÁTICA (generada por FastAPI):
#   http://localhost:8000/docs
# ==============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime

from langchain_core.messages import HumanMessage

from database.queries import cargar_datos_banco
from chatbot.graph import construir_grafo

# ── APLICACIÓN ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Chatbot Bancario API",
    description="API REST para el chatbot bancario con LangGraph y Neon PostgreSQL",
    version="1.0.0"
)

# ── ESTADO EN MEMORIA ──────────────────────────────────────────────────────────
#
# En producción esto viviría en Redis — una base de datos en memoria
# diseñada para guardar estado de sesiones con expiración automática.
#
# Para el portfolio usamos un diccionario Python — más simple,
# demuestra el mismo concepto arquitectural.
#
# Cada sesión tiene su propio estado independiente:
# {
#   "abc123": {
#       "messages": [...],
#       "datos_cliente": {...},
#       "esperando": "monto",
#       "transferencia": {...},
#       "creada": "2026-04-22 10:30:00"
#   }
# }

sesiones: dict = {}
agente = construir_grafo()


# ── MODELOS DE REQUEST Y RESPONSE ─────────────────────────────────────────────
#
# Pydantic valida automáticamente que los datos que llegan
# tienen el formato correcto. Si falta un campo o el tipo es incorrecto,
# FastAPI devuelve un error 422 antes de que el código lo procese.

class MensajeRequest(BaseModel):
    sesion_id: str
    mensaje: str

class ChatResponse(BaseModel):
    respuesta: str
    esperando: str
    sesion_id: str

class SesionResponse(BaseModel):
    sesion_id: str
    creada: str
    esperando: str
    total_mensajes: int


# ── ENDPOINTS ──────────────────────────────────────────────────────────────────

@app.get("/")
def raiz():
    """Health check — verifica que la API está corriendo."""
    return {"status": "ok", "servicio": "Chatbot Bancario API"}


@app.post("/sesion/nueva", response_model=SesionResponse)
def nueva_sesion():
    """
    Crea una sesión nueva para un cliente.

    Carga los datos del cliente desde Neon y crea el estado inicial.
    Devuelve un sesion_id que el frontend debe guardar y usar
    en todos los requests siguientes.

    En producción el DNI vendría del sistema de autenticación.
    """
    sesion_id = str(uuid4())
    # uuid4() genera un ID único aleatorio — imposible de adivinar

    datos = cargar_datos_banco()  # en producción: cargar_datos_banco(dni)

    sesiones[sesion_id] = {
        "messages": [],
        "datos_cliente": datos,
        "esperando": "",
        "transferencia": {},
        "operacion_registrar": {},
        "creada": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "operaciones": [],
    }

    return SesionResponse(
        sesion_id=sesion_id,
        creada=sesiones[sesion_id]["creada"],
        esperando="",
        total_mensajes=0
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: MensajeRequest):
    """
    Envía un mensaje al chatbot y recibe la respuesta.

    El frontend manda el sesion_id en cada request para que
    el servidor sepa a qué conversación pertenece el mensaje.

    El estado (historial, transferencia en curso, etc.) persiste
    entre requests gracias al diccionario de sesiones.
    """
    # Verificamos que la sesión existe
    if request.sesion_id not in sesiones:
        raise HTTPException(
            status_code=404,
            detail="Sesión no encontrada. Creá una nueva con POST /sesion/nueva"
        )

    estado = sesiones[request.sesion_id]

    # Agregamos el mensaje del usuario al historial
    estado["messages"].append(HumanMessage(content=request.mensaje))

    # Ejecutamos un turno del grafo — misma lógica que el main.py original
    estado = agente.invoke(estado)

    # Si el nodo ejecutó una operación, la registramos
    if estado.get("operacion_registrar"):
        if "operaciones" not in estado:
            estado["operaciones"] = []
        estado["operaciones"].append(estado["operacion_registrar"])
        estado["operacion_registrar"] = {}

    # Guardamos el estado actualizado
    sesiones[request.sesion_id] = estado

    # Devolvemos la respuesta
    ultima_respuesta = estado["messages"][-1].content

    return ChatResponse(
        respuesta=ultima_respuesta,
        esperando=estado.get("esperando", ""),
        sesion_id=request.sesion_id
    )


@app.get("/sesion/{sesion_id}", response_model=SesionResponse)
def ver_sesion(sesion_id: str):
    """
    Devuelve el estado actual de una sesión.

    Útil para que el frontend sepa en qué paso del flujo está
    sin necesidad de parsear la respuesta del chatbot.
    """
    if sesion_id not in sesiones:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    estado = sesiones[sesion_id]

    return SesionResponse(
        sesion_id=sesion_id,
        creada=estado["creada"],
        esperando=estado.get("esperando", ""),
        total_mensajes=len(estado["messages"])
    )


@app.delete("/sesion/{sesion_id}")
def cerrar_sesion(sesion_id: str):
    """
    Cierra una sesión y libera la memoria.

    En producción esto también guardaría el log de auditoría
    en la base de datos antes de eliminar la sesión.
    """
    if sesion_id not in sesiones:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    estado = sesiones.pop(sesion_id)
    operaciones = estado.get("operaciones", [])

    return {
        "mensaje": "Sesión cerrada",
        "total_operaciones": len(operaciones),
        "operaciones": operaciones
    }