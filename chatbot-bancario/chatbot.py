# ==============================================================================
# CHATBOT BANCARIO — LangGraph + Groq
# ==============================================================================
#
# ¿QUÉ HACE?
# Simula un chatbot bancario con memoria conversacional.
# El cliente puede consultar saldo, movimientos y hacer transferencias.
#
# DISEÑO FUNDAMENTAL — DOS MODOS SEPARADOS:
#
#   MODO CONVERSACIÓN (esperando = ""):
#     El LLM responde libremente con acceso al historial completo.
#     Maneja saludos, consultas de saldo, movimientos, preguntas generales.
#
#   MODO TRANSFERENCIA (esperando = "destinatario" | "monto" | "confirmacion"):
#     El CÓDIGO toma el control. El LLM NO habla.
#     El código genera las respuestas directamente y valida cada dato.
#
# ¿POR QUÉ ESTA SEPARACIÓN?
#
#   Los bancos reales NO usan LLMs para manejar operaciones financieras.
#   Un LLM puede alucinar, malinterpretar montos, inventar confirmaciones.
#   Para operaciones reales se necesita código determinista — predecible,
#   trazable y auditable. El LLM solo maneja la parte conversacional.
#
#   Ejemplo: si el usuario escribe "transferí como mil pesos a juan",
#   un LLM podría interpretar "mil" de formas distintas en distintas corridas.
#   El código determinista le pide el número exacto y lo valida.
#
# TÉCNICAS USADAS:
#   - System prompt dinámico — carga los datos del cliente al inicio
#   - Message history — acumula todos los mensajes de la conversación
#   - LangGraph con estados — el campo 'esperando' controla el flujo
#   - Log de auditoría + log de conversación — separados como en producción
#
# PARA CORRERLO:
#   python chatbot.py
# ==============================================================================

import json
import re
import unicodedata
from datetime import datetime
from typing import TypedDict, Annotated
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
# add_messages: reducer especial de LangGraph que ACUMULA mensajes
# en lugar de reemplazarlos. Sin esto, cada nodo pisaría el historial
# y el chatbot perdería la memoria de lo que se dijo antes.

load_dotenv()

# ── MODELO ────────────────────────────────────────────────────────────────────
# Solo se usa en MODO CONVERSACIÓN.
# En MODO TRANSFERENCIA el código genera las respuestas directamente.

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
)


# ── ESTADO ────────────────────────────────────────────────────────────────────
#
# El estado tiene tres partes:
#
# 1. messages — el historial de conversación completo
#    Crece con cada turno. Es lo que le da "memoria" al chatbot.
#    Se le pasa al LLM en cada llamada para que "recuerde" el hilo.
#
# 2. datos_cliente — los datos del banco cargados al inicio
#    Se actualiza cuando se ejecuta una transferencia (saldo, movimientos).
#
# 3. esperando + transferencia — controlan el flujo de transferencia
#    'esperando' es la clave: dice exactamente en qué paso está el sistema.
#    '' = conversación libre, 'destinatario' = esperando a quién,
#    'monto' = esperando cuánto, 'confirmacion' = esperando sí o no.

class Estado(TypedDict):
    messages: Annotated[list, add_messages]
    datos_cliente: dict
    esperando: str
    transferencia: dict
    operacion_registrar: dict
    # Campo temporal — cuando el código ejecuta una transferencia,
    # deja acá los datos para que el main los agregue al log de auditoría.
    # El main lo lee y lo limpia en cada turno.


# ── FUNCIONES AUXILIARES ──────────────────────────────────────────────────────

def cargar_datos_banco() -> dict:
    """Carga datos_banco.json — simula la autenticación del cliente."""
    with open("datos_banco.json", "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_datos_banco(datos: dict):
    """
    Sobreescribe datos_banco.json con los datos actualizados.
    Se llama inmediatamente después de ejecutar una transferencia.
    Así la próxima sesión arranca con el saldo y movimientos correctos.
    """
    with open("datos_banco.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def guardar_log_sesion(messages: list, saldo_inicial: float,
                       datos_finales: dict, operaciones: list):
    """
    Guarda el log de sesión con DOS secciones separadas.

    Por qué dos secciones:

    'operaciones' = log de auditoría
        Solo lo que se ejecutó: qué, cuándo, cuánto, a quién.
        Los bancos están obligados por regulación a guardar esto.
        Es inmutable — no se puede modificar después.
        Sirve para resolver disputas y detectar fraude.

    'conversacion' = log de diálogo
        Todos los mensajes del chat, en orden.
        Sirve para mejorar el bot, analizar patrones de uso,
        y dar soporte al cliente si algo salió mal.

    En producción son dos sistemas separados con distintos niveles
    de acceso y retención. Acá los guardamos juntos por simplicidad.
    """
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
            "saldo_final": datos_finales["cliente"]["saldo"],
            "diferencia": datos_finales["cliente"]["saldo"] - saldo_inicial,
            "total_operaciones": len(operaciones),
            "total_turnos": len([m for m in conversacion if m["rol"] == "usuario"]),
        },
        "operaciones": operaciones,    # log de auditoría — oficial
        "conversacion": conversacion,  # log de diálogo — analítico
    }

    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"   ✓ Log guardado: {nombre_archivo}")
    if operaciones:
        print(f"   ✓ Operaciones registradas: {len(operaciones)}")
    print(f"   ✓ Saldo: ${saldo_inicial:,.2f} → ${datos_finales['cliente']['saldo']:,.2f}")


def construir_system_prompt(datos: dict) -> str:
    """
    Construye el system prompt dinámico con los datos del cliente.

    Esto simula lo que hace un banco real al inicio de cada sesión:
    consulta la base de datos, carga los datos del cliente autenticado,
    y los inyecta en el contexto del modelo.

    El modelo no consultó ninguna base de datos — el código lo hizo por él.
    Eso es system prompt dinámico.
    """
    cliente = datos["cliente"]
    contactos = datos["contactos"]
    movimientos = datos["movimientos"]

    lista_contactos = "\n".join(
        f"  - {c['nombre']} (alias: {c['alias']})"
        for c in contactos
    )

    lista_movimientos = "\n".join(
        f"  - {m['fecha']} | {m['descripcion']} | ${m['monto']:,.2f}"
        for m in movimientos[-5:]
    )

    return f"""Sos el asistente virtual del banco para el cliente {cliente['nombre']}.

DATOS DEL CLIENTE (cargados automáticamente al iniciar la sesión):
- Nombre: {cliente['nombre']}
- DNI: {cliente['dni']}
- Saldo disponible: ${cliente['saldo']:,.2f}
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
    """
    Normaliza un texto para comparación sin importar mayúsculas ni acentos.
    'María', 'maria', 'MARIA' y 'maría' devuelven el mismo resultado.
    Necesario para que la búsqueda de contactos sea flexible.
    """
    return unicodedata.normalize('NFD', texto.lower()).encode('ascii', 'ignore').decode()


def detectar_intencion_transferencia(mensaje: str) -> bool:
    """
    Detecta si el usuario quiere hacer una transferencia.

    Esta detección es el único lugar donde el código "interpreta"
    lenguaje natural de forma flexible. El resto del flujo de
    transferencia es completamente determinista — sin LLM.
    """
    palabras_clave = [
        "transferi", "transferí", "transferir", "transferencia",
        "mandar", "enviar", "pasar plata", "pasar dinero",
        "quiero mandar", "quiero enviar", "hacer una transfer",
        "quiero hacer", "necesito enviar", "necesito mandar"
    ]
    return any(p in mensaje.lower() for p in palabras_clave)


def buscar_contacto(mensaje: str, contactos: list) -> dict | None:
    """
    Busca si el mensaje menciona algún contacto habilitado.
    Búsqueda simple por nombre — no usa LLM.
    """
    for contacto in contactos:
        nombre_completo = contacto["nombre"].lower()
        primer_nombre = nombre_completo.split()[0]
        if primer_nombre in mensaje.lower() or nombre_completo in mensaje.lower():
            return contacto
    return None


def extraer_monto(mensaje: str) -> float | None:
    """
    Extrae un número del mensaje del usuario.
    Búsqueda con regex — no usa LLM.

    Por qué no usar el LLM para esto: si el usuario escribe
    "como unos cincuenta mil" el LLM podría entenderlo, pero también
    podría interpretar "cincuenta" como 50 o 50000 dependiendo del contexto.
    En un banco, el monto tiene que ser exacto. Le pedimos el número directo.
    """
    numeros = re.findall(r'\d+(?:[.,]\d+)*', mensaje)
    if numeros:
        monto_str = numeros[0].replace(".", "").replace(",", "")
        return float(monto_str)
    return None


def detectar_duplicado(movimientos: list, destinatario: str, monto: float) -> bool:
    """
    Detecta si ya existe una transferencia al mismo destinatario
    por el mismo monto en el historial reciente.

    En producción esto consultaría una base de datos con ventana temporal
    (ej: últimas 24 horas). Acá revisamos todos los movimientos del JSON.
    """
    dest_norm = normalizar(destinatario.split()[0])
    for mov in movimientos:
        if (dest_norm in normalizar(mov["descripcion"])
                and abs(mov["monto"]) == monto):
            return True
    return False


def respuesta_directa(texto: str) -> AIMessage:
    """
    Crea un mensaje de respuesta sin pasar por el LLM.

    En MODO TRANSFERENCIA el código genera las respuestas directamente.
    Esto garantiza que lo que el sistema dice es exactamente lo que
    el código decidió decir — sin interpretación del modelo.
    """
    return AIMessage(content=texto)


# ── NODO PRINCIPAL ────────────────────────────────────────────────────────────

def nodo_chatbot(estado: Estado) -> dict:
    """
    El corazón del chatbot. Maneja DOS modos completamente separados.

    ══════════════════════════════════════════════════════════
    MODO TRANSFERENCIA (esperando != "")
    ══════════════════════════════════════════════════════════

    El CÓDIGO toma el control. El LLM NO participa.
    El código procesa la respuesta del usuario, valida los datos,
    y genera la respuesta directamente con respuesta_directa().

    Por qué no usar el LLM acá:
    - Confiabilidad: el código no alucina ni malinterpreta montos
    - Auditoría: cada paso es trazable y determinista
    - Regulación: los bancos necesitan control total sobre operaciones

    ══════════════════════════════════════════════════════════
    MODO CONVERSACIÓN (esperando = "")
    ══════════════════════════════════════════════════════════

    El LLM responde libremente con acceso al historial completo.
    Maneja saludos, consultas, preguntas generales.
    Si detecta intención de transferencia, activa el modo transferencia.
    """
    datos = estado["datos_cliente"]
    esperando = estado.get("esperando", "")
    transferencia = estado.get("transferencia", {})
    ultimo_mensaje = estado["messages"][-1].content

    # ══════════════════════════════════════════════════════════════════════════
    # MODO TRANSFERENCIA — el código maneja todo, sin LLM
    # ══════════════════════════════════════════════════════════════════════════

    if esperando == "destinatario":
        # El sistema preguntó a quién — procesa la respuesta del usuario
        # sin pasar por el LLM. Búsqueda determinista por nombre.
        contacto = buscar_contacto(ultimo_mensaje, datos["contactos"])

        if contacto:
            # Encontramos el contacto — pedimos el monto
            # Nota: generamos la respuesta directamente, sin LLM
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
            # No encontramos el contacto — mostramos los disponibles
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
        # El sistema preguntó el monto — lo extrae con regex, sin LLM
        monto = extraer_monto(ultimo_mensaje)

        if not monto or monto <= 0:
            return {
                "messages": [respuesta_directa(
                    "No entendí el monto. "
                    "Escribí solo el número, por ejemplo: 5000"
                )],
                "esperando": "monto",
            }

        if monto > datos["cliente"]["saldo"]:
            # Validación de saldo — el código chequea, no el LLM
            return {
                "messages": [respuesta_directa(
                    f"Saldo insuficiente. "
                    f"Tu saldo disponible es ${datos['cliente']['saldo']:,.2f}. "
                    f"¿Querés transferir un monto menor?"
                )],
                "esperando": "monto",
            }

        # Detección de duplicado — revisamos el historial de movimientos
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

        # Mostramos el resumen para confirmar — generado por el código, no el LLM
        resumen = (
            f"Confirmame la transferencia:\n"
            f"  • Destinatario: {transferencia['destinatario']}\n"
            f"  • Alias: {transferencia['alias']}\n"
            f"  • Monto: ${monto:,.2f}\n"
            f"  • Saldo después: ${datos['cliente']['saldo'] - monto:,.2f}"
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
        # El sistema mostró el resumen — espera sí o no
        # Solo acepta respuestas explícitas — no interpreta ambigüedades
        confirmado = any(p in ultimo_mensaje.lower()
                        for p in ["si", "sí", "confirmo", "dale", "ok", "yes"])
        cancelado  = any(p in ultimo_mensaje.lower()
                        for p in ["no", "cancelar", "cancelá", "nope"])

        if confirmado:
            # ── EJECUTAMOS LA TRANSFERENCIA ────────────────────────────────
            # Este es el único lugar donde ocurre una acción real.
            # En producción llamaría a la API del banco.
            # El código actualiza el JSON y registra la operación.
            # El LLM no participa en ninguna parte de esta ejecución.

            monto = transferencia["monto"]
            datos["cliente"]["saldo"] -= monto
            datos["movimientos"].append({
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "descripcion": f"Transferencia a {transferencia['destinatario']}",
                "monto": -monto
            })

            # Persistimos los cambios inmediatamente
            # Si el programa se cierra ahora, el JSON ya tiene el saldo correcto
            guardar_datos_banco(datos)

            return {
                "messages": [respuesta_directa(
                    f"✓ Transferencia realizada.\n"
                    f"  • ${monto:,.2f} enviados a {transferencia['destinatario']}\n"
                    f"  • Tu nuevo saldo: ${datos['cliente']['saldo']:,.2f}"
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

        elif cancelado:
            return {
                "messages": [respuesta_directa(
                    "Transferencia cancelada. ¿En qué más puedo ayudarte?"
                )],
                "esperando": "",
                "transferencia": {},
            }
        else:
            # Respuesta ambigua — pedimos claridad
            # En operaciones financieras no hay lugar para ambigüedades
            return {
                "messages": [respuesta_directa(
                    "Por favor respondé 'sí' para confirmar o 'no' para cancelar."
                )],
                "esperando": "confirmacion",
            }

    # ══════════════════════════════════════════════════════════════════════════
    # MODO CONVERSACIÓN — el LLM responde libremente
    # Solo llegamos acá cuando esperando = "" (no hay flujo activo)
    # ══════════════════════════════════════════════════════════════════════════

    # Detectamos si el usuario quiere hacer una transferencia
    # Si es así, activamos el modo transferencia sin llamar al LLM
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

    # Para todo lo demás — el LLM responde con el historial completo
    # Acá sí usamos el modelo porque es conversación libre sin riesgos
    system_prompt = construir_system_prompt(datos)
    respuesta = llm.invoke([
        SystemMessage(content=system_prompt),
        *estado["messages"]
        # Le pasamos TODOS los mensajes anteriores + el actual.
        # El modelo los lee y "recuerda" el hilo de la conversación.
        # Sin este historial, cada pregunta sería independiente.
    ])

    return {"messages": [respuesta]}


# ── CONSTRUCCIÓN DEL GRAFO ────────────────────────────────────────────────────
#
# El grafo es simple — un solo nodo que se ejecuta por turno.
# La complejidad está dentro del nodo, no en la estructura del grafo.
#
# El loop de conversación lo maneja el while True del main,
# no el grafo. El grafo ejecuta un turno y termina.
# El main lo vuelve a llamar con el estado actualizado.

def construir_grafo():
    grafo = StateGraph(Estado)
    grafo.add_node("chatbot", nodo_chatbot)
    grafo.set_entry_point("chatbot")
    grafo.add_edge("chatbot", END)
    return grafo.compile()


# ── PUNTO DE ENTRADA ──────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("CHATBOT BANCARIO — Simulador")
    print("=" * 60)

    print("\nCargando datos del cliente...")
    datos = cargar_datos_banco()
    saldo_inicial = datos["cliente"]["saldo"]
    print(f"   ✓ Bienvenido, {datos['cliente']['nombre']}\n")

    print("Escribí tu consulta. Escribí 'salir' para terminar.")
    print("-" * 60 + "\n")

    # Estado inicial
    estado = {
        "messages": [],
        "datos_cliente": datos,
        "esperando": "",           # sin flujo activo al inicio
        "transferencia": {},
        "operacion_registrar": {},
    }

    operaciones_sesion = []  # log de auditoría — se llena cuando se ejecutan operaciones
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

        # Agregamos el mensaje del usuario al estado
        # add_messages lo suma al historial sin reemplazarlo
        estado["messages"].append(HumanMessage(content=entrada))

        # Ejecutamos un turno del grafo
        estado = agente.invoke(estado)

        # Si el nodo ejecutó una operación, la registramos en el log de auditoría
        # y limpiamos la señal para el próximo turno
        if estado.get("operacion_registrar"):
            operaciones_sesion.append(estado["operacion_registrar"])
            estado["operacion_registrar"] = {}

        # Mostramos la respuesta del turno actual
        ultima_respuesta = estado["messages"][-1].content
        print(f"\nBot: {ultima_respuesta}\n")