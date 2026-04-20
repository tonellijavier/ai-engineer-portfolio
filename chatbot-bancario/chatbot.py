# ==============================================================================
# CHATBOT BANCARIO — LangGraph + Groq + Neon (PostgreSQL)
# ==============================================================================
#
# ¿QUÉ HACE?
# Simula un chatbot bancario con memoria conversacional.
# El cliente puede consultar saldo, movimientos y hacer transferencias.
#
# VERSIÓN 2 — Migrado de JSON a PostgreSQL (Neon)
# Los datos del cliente ahora viven en una base de datos real.
# El saldo y los movimientos se actualizan con SQL en tiempo real.
#
# DISEÑO FUNDAMENTAL — DOS MODOS SEPARADOS:
#
#   MODO CONVERSACIÓN (esperando = ""):
#     El LLM responde libremente con acceso al historial completo.
#
#   MODO TRANSFERENCIA (esperando = "destinatario" | "monto" | "confirmacion"):
#     El CÓDIGO toma el control. El LLM NO habla.
#     Valida datos, detecta duplicados, ejecuta con SQL.
#
# ¿POR QUÉ ESTA SEPARACIÓN?
#   Los bancos reales NO usan LLMs para operaciones financieras.
#   Para operaciones reales se necesita código determinista — predecible,
#   trazable y auditable. El LLM solo maneja la parte conversacional.
#
# PARA CORRERLO:
#   1. Corré setup_db.py una sola vez para crear las tablas
#   2. python chatbot.py
# ==============================================================================

import os
import re
import unicodedata
from datetime import datetime
from typing import TypedDict, Annotated
from dotenv import load_dotenv

import psycopg2
import psycopg2.extras
# psycopg2 es el driver de Python para PostgreSQL.
# psycopg2.extras.RealDictCursor devuelve las filas como diccionarios
# en lugar de tuplas — más fácil de usar en el código.

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

load_dotenv()

# ── MODELO ────────────────────────────────────────────────────────────────────

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
)


# ── ESTADO ────────────────────────────────────────────────────────────────────

class Estado(TypedDict):
    messages: Annotated[list, add_messages]
    datos_cliente: dict
    esperando: str
    transferencia: dict
    operacion_registrar: dict


# ── CONEXIÓN A NEON ───────────────────────────────────────────────────────────

def get_conn():
    """
    Crea una conexión a Neon (PostgreSQL).
    Usamos RealDictCursor para que las filas sean diccionarios,
    así podemos acceder por nombre de columna: fila["saldo"]
    en lugar de por índice: fila[0].
    """
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        cursor_factory=psycopg2.extras.RealDictCursor
    )


# ── FUNCIONES DE BASE DE DATOS ────────────────────────────────────────────────

def cargar_datos_banco(dni: str = "12345678") -> dict:
    """
    Carga los datos del cliente desde PostgreSQL.

    Antes: leía datos_banco.json con open() y json.load()
    Ahora: ejecuta tres consultas SQL y devuelve el mismo formato de diccionario

    El resto del chatbot no sabe la diferencia — recibe el mismo dict
    que antes recibía del JSON. Eso es una buena abstracción.
    """
    conn = get_conn()
    cur = conn.cursor()

    # Consulta 1: datos del cliente
    cur.execute("""
        SELECT nombre, dni, saldo, productos
        FROM clientes
        WHERE dni = %s
    """, (dni,))
    cliente = dict(cur.fetchone())
    # dict() convierte el RealDictRow a un diccionario Python normal

    # Consulta 2: contactos habilitados
    cur.execute("""
        SELECT nombre, cbu, alias
        FROM contactos
        WHERE dni_cliente = %s
        ORDER BY nombre
    """, (dni,))
    contactos = [dict(row) for row in cur.fetchall()]

    # Consulta 3: últimos movimientos (los más recientes primero)
    cur.execute("""
        SELECT fecha::text, descripcion, monto
        FROM movimientos
        WHERE dni_cliente = %s
        ORDER BY fecha DESC, id DESC
        LIMIT 10
    """, (dni,))
    # fecha::text convierte el tipo DATE de PostgreSQL a string
    # para que sea compatible con el resto del código
    movimientos = [dict(row) for row in cur.fetchall()]
    movimientos.reverse()  # los mostramos del más viejo al más nuevo

    cur.close()
    conn.close()

    # Devolvemos el mismo formato que tenía el JSON
    # El resto del chatbot no necesita saber que ahora viene de una DB
    return {
        "cliente": cliente,
        "contactos": contactos,
        "movimientos": movimientos
    }


def actualizar_saldo(dni: str, nuevo_saldo: float):
    """
    Actualiza el saldo del cliente en PostgreSQL.

    Antes: sobreescribía todo el JSON con json.dump()
    Ahora: ejecuta un UPDATE SQL — solo toca el campo que cambió
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clientes
        SET saldo = %s
        WHERE dni = %s
    """, (nuevo_saldo, dni))

    conn.commit()
    cur.close()
    conn.close()


def insertar_movimiento(dni: str, descripcion: str, monto: float):
    """
    Inserta un nuevo movimiento en PostgreSQL.

    Antes: hacía append a la lista de movimientos del JSON
    Ahora: INSERT INTO movimientos — queda guardado permanentemente
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO movimientos (dni_cliente, fecha, descripcion, monto)
        VALUES (%s, CURRENT_DATE, %s, %s)
    """, (dni, descripcion, monto))
    # CURRENT_DATE es una función de PostgreSQL que devuelve la fecha de hoy

    conn.commit()
    cur.close()
    conn.close()


def guardar_log_sesion(messages: list, saldo_inicial: float,
                       datos_finales: dict, operaciones: list):
    """
    Guarda el log de sesión con DOS secciones separadas.

    'operaciones' = log de auditoría — qué se ejecutó y cuándo
    'conversacion' = log de diálogo — todos los mensajes del chat
    """
    import json
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
        "operaciones": operaciones,
        "conversacion": conversacion,
    }

    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2, default=str)

    print(f"   ✓ Log guardado: {nombre_archivo}")
    if operaciones:
        print(f"   ✓ Operaciones registradas: {len(operaciones)}")
    print(f"   ✓ Saldo: ${saldo_inicial:,.2f} → ${float(datos_finales['cliente']['saldo']):,.2f}")


# ── FUNCIONES AUXILIARES ──────────────────────────────────────────────────────

def construir_system_prompt(datos: dict) -> str:
    """
    Construye el system prompt dinámico con los datos del cliente.
    Los datos vienen de PostgreSQL pero el modelo los recibe como texto.
    """
    cliente = datos["cliente"]
    contactos = datos["contactos"]
    movimientos = datos["movimientos"]

    lista_contactos = "\n".join(
        f"  - {c['nombre']} (alias: {c['alias']})"
        for c in contactos
    )

    lista_movimientos = "\n".join(
        f"  - {m['fecha']} | {m['descripcion']} | ${float(m['monto']):,.2f}"
        for m in movimientos[-5:]
    )

    return f"""Sos el asistente virtual del banco para el cliente {cliente['nombre']}.

DATOS DEL CLIENTE (cargados automáticamente al iniciar la sesión):
- Nombre: {cliente['nombre']}
- DNI: {cliente['dni']}
- Saldo disponible: ${float(cliente['saldo']):,.2f}
- Productos: {', '.join(cliente['productos'])}

CONTACTOS HABILITADOS PARA TRANSFERENCIAS:
{lista_contactos}

ÚLTIMOS MOVIMIENTOS:
{lista_movimientos}

INSTRUCCIONES:
- Respondé siempre en español, de forma clara y cordial
- Usá el nombre del cliente cuando sea natural
- Para consultas sobre saldo, movimientos o productos,
  respondé con los datos que tenés arriba
- Si el cliente pregunta algo que no está en sus datos, decilo claramente

IMPORTANTE — TRANSFERENCIAS:
- NUNCA ejecutes, confirmes ni proceses una transferencia vos mismo
- NUNCA digas que una transferencia fue realizada o confirmada
- Si el cliente menciona transferencia, respondé ÚNICAMENTE:
  "Con gusto te ayudo. El sistema va a guiarte paso a paso."
- El sistema de transferencias es manejado por el código, no por vos
- Tu rol es solo conversación — las operaciones las maneja el sistema"""


def normalizar(texto: str) -> str:
    """Normaliza texto para comparación sin importar mayúsculas ni acentos."""
    return unicodedata.normalize('NFD', texto.lower()).encode('ascii', 'ignore').decode()


def detectar_intencion_transferencia(mensaje: str) -> bool:
    """Detecta si el usuario quiere hacer una transferencia."""
    palabras_clave = [
        "transferi", "transferí", "transferir", "transferencia",
        "mandar", "enviar", "pasar plata", "pasar dinero",
        "quiero mandar", "quiero enviar", "hacer una transfer",
        "quiero hacer", "necesito enviar", "necesito mandar"
    ]
    return any(p in mensaje.lower() for p in palabras_clave)


def buscar_contacto(mensaje: str, contactos: list) -> dict | None:
    """Busca si el mensaje menciona algún contacto habilitado."""
    mensaje_norm = normalizar(mensaje)
    for contacto in contactos:
        nombre_completo = normalizar(contacto["nombre"])
        primer_nombre = nombre_completo.split()[0]
        if primer_nombre in mensaje_norm or nombre_completo in mensaje_norm:
            return contacto
    return None


def extraer_monto(mensaje: str) -> float | None:
    """Extrae un número del mensaje del usuario."""
    numeros = re.findall(r'\d+(?:[.,]\d+)*', mensaje)
    if numeros:
        monto_str = numeros[0].replace(".", "").replace(",", "")
        return float(monto_str)
    return None


def detectar_duplicado(movimientos: list, destinatario: str, monto: float) -> bool:
    """Detecta si ya existe una transferencia similar en el historial."""
    dest_norm = normalizar(destinatario.split()[0])
    for mov in movimientos:
        if (dest_norm in normalizar(mov["descripcion"])
                and abs(float(mov["monto"])) == monto):
            return True
    return False


def respuesta_directa(texto: str) -> AIMessage:
    """Crea una respuesta sin pasar por el LLM."""
    return AIMessage(content=texto)


# ── NODO PRINCIPAL ────────────────────────────────────────────────────────────

def nodo_chatbot(estado: Estado) -> dict:
    """
    Maneja DOS modos completamente separados.

    MODO TRANSFERENCIA (esperando != ""):
      El código toma el control. Consulta y actualiza PostgreSQL directamente.
      El LLM no participa en ningún paso de la operación.

    MODO CONVERSACIÓN (esperando = ""):
      El LLM responde libremente con acceso al historial completo.
    """
    datos = estado["datos_cliente"]
    esperando = estado.get("esperando", "")
    transferencia = estado.get("transferencia", {})
    ultimo_mensaje = estado["messages"][-1].content

    # ── MODO TRANSFERENCIA ─────────────────────────────────────────────────────

    if esperando == "destinatario":
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

    elif esperando == "monto":
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

    elif esperando == "confirmacion":
        confirmado = any(p in ultimo_mensaje.lower()
                        for p in ["si", "sí", "confirmo", "dale", "ok", "yes"])
        cancelado  = any(p in ultimo_mensaje.lower()
                        for p in ["no", "cancelar", "cancelá", "nope"])

        if confirmado:
            monto = transferencia["monto"]
            nuevo_saldo = float(datos["cliente"]["saldo"]) - monto
            dni = datos["cliente"]["dni"]

            # ── ACTUALIZACIÓN EN POSTGRESQL ────────────────────────────────
            # Antes: sobreescribíamos el JSON completo
            # Ahora: dos operaciones SQL precisas — solo tocan lo que cambió

            actualizar_saldo(dni, nuevo_saldo)
            # UPDATE clientes SET saldo = nuevo_saldo WHERE dni = dni

            insertar_movimiento(
                dni,
                f"Transferencia a {transferencia['destinatario']}",
                -monto
            )
            # INSERT INTO movimientos (dni_cliente, fecha, descripcion, monto)

            # Actualizamos el estado local para que el sistema prompt
            # refleje el nuevo saldo en el mismo turno
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
                "operacion_registrar": {
                    "tipo": "transferencia",
                    "destinatario": transferencia["destinatario"],
                    "monto": monto,
                    "hora": datetime.now().strftime("%H:%M:%S"),
                    "estado": "ejecutada"
                }
            }

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

    # ── MODO CONVERSACIÓN ──────────────────────────────────────────────────────

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

    system_prompt = construir_system_prompt(datos)
    respuesta = llm.invoke([
        SystemMessage(content=system_prompt),
        *estado["messages"]
    ])

    return {"messages": [respuesta]}


# ── CONSTRUCCIÓN DEL GRAFO ────────────────────────────────────────────────────

def construir_grafo():
    grafo = StateGraph(Estado)
    grafo.add_node("chatbot", nodo_chatbot)
    grafo.set_entry_point("chatbot")
    grafo.add_edge("chatbot", END)
    return grafo.compile()


# ── PUNTO DE ENTRADA ──────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("CHATBOT BANCARIO — Simulador (Neon PostgreSQL)")
    print("=" * 60)

    print("\nConectando a la base de datos...")
    datos = cargar_datos_banco()
    saldo_inicial = float(datos["cliente"]["saldo"])
    print(f"   ✓ Bienvenido, {datos['cliente']['nombre']}")
    print(f"   ✓ Saldo actual: ${saldo_inicial:,.2f}\n")

    print("Escribí tu consulta. Escribí 'salir' para terminar.")
    print("-" * 60 + "\n")

    estado = {
        "messages": [],
        "datos_cliente": datos,
        "esperando": "",
        "transferencia": {},
        "operacion_registrar": {},
    }

    operaciones_sesion = []
    agente = construir_grafo()

    while True:
        entrada = input("Vos: ").strip()

        if not entrada:
            continue

        if entrada.lower() == "salir":
            print("\nHasta luego. ¡Que tengas un buen día!")
            print("\nGuardando sesión...")
            guardar_log_sesion(
                estado["messages"],
                saldo_inicial,
                estado["datos_cliente"],
                operaciones_sesion
            )
            break

        estado["messages"].append(HumanMessage(content=entrada))
        estado = agente.invoke(estado)

        if estado.get("operacion_registrar"):
            operaciones_sesion.append(estado["operacion_registrar"])
            estado["operacion_registrar"] = {}

        ultima_respuesta = estado["messages"][-1].content
        print(f"\nBot: {ultima_respuesta}\n")