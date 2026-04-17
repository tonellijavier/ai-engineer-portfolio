# ==============================================================================
# AGENTE ANALIZADOR DE GASTOS CON LANGGRAPH + GMAIL
# ==============================================================================
#
# ¿QUÉ HACE?
# 1. Cargás un extracto bancario en PDF
# 2. El agente analiza los gastos y busca promedios del sector en Google
# 3. Redacta un informe como borrador de mail
# 4. Te muestra el borrador y espera tu confirmación
# 5. Si confirmás → guarda en Gmail
#    Si pedís cambios → vuelve a redactar incorporando tu feedback
#    Si cancelás → termina sin guardar
#
# ¿POR QUÉ LANGGRAPH Y NO LANGCHAIN?
# LangChain funciona en línea recta: A → B → C → fin.
# Acá el usuario puede pedir cambios N veces antes de confirmar.
# Eso requiere volver atrás — un loop — que LangChain no soporta.
# LangGraph sí, porque permite grafos con bifurcaciones y loops.
#
# PARA CORRERLO:
#   1. Corré test_gmail.py primero para autenticar Gmail
#   2. Necesitás credentials.json y token.json en la carpeta
#   3. python agente_gastos.py
# ==============================================================================

import os
import base64
from pathlib import Path
from typing import TypedDict
from email.mime.text import MIMEText

import pdfplumber
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.utilities import GoogleSerperAPIWrapper

from langgraph.graph import StateGraph, END
# StateGraph → el objeto que construye y ejecuta el grafo
# END → constante especial que marca dónde termina el grafo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()


# ── MODELOS ───────────────────────────────────────────────────────────────────

llm_analista = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.1,   # bajo — el análisis tiene que ser preciso
)

llm_redactor = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.5,   # medio — la redacción necesita ser fluida
)

search = GoogleSerperAPIWrapper()
# Misma lógica que SerperDevTool en CrewAI — distinta sintaxis, mismo concepto.
# Se llama con search.run("consulta") y devuelve resultados de Google.


# ── ESTADO ────────────────────────────────────────────────────────────────────
#
# El Estado es el formulario que comparten todos los nodos.
# Cada nodo puede leer cualquier campo y actualizar los que necesite.
# LangGraph fusiona automáticamente los cambios con el estado existente.
#
# TypedDict define qué campos tiene el formulario y de qué tipo es cada uno.
# str = texto, bool = verdadero/falso.
# Podrías usar un diccionario normal {} y funcionaría igual —
# TypedDict agrega validación de tipos para que VS Code te avise si te equivocás.
#
# Al principio todos los campos están vacíos.
# A medida que el grafo avanza, cada nodo completa los suyos:
#   nodo_analizar         → completa 'analisis'
#   nodo_buscar_promedios → completa 'promedios'
#   nodo_redactar         → completa 'borrador'
#   nodo_pedir_confirmacion → completa 'feedback' y 'confirmado'

class Estado(TypedDict):
    extracto_texto: str   # texto del PDF — entra al inicio, no cambia
    nombre_archivo: str   # nombre del PDF — para el asunto del mail
    analisis: str         # clasificación de gastos del extracto
    promedios: str        # datos de gasto promedio buscados en Google
    borrador: str         # el texto del mail redactado
    feedback: str         # lo que escribió el usuario al ver el borrador
    confirmado: bool      # True si el usuario escribió "sí"


# ── FUNCIONES AUXILIARES ──────────────────────────────────────────────────────

def extraer_texto_pdf(ruta: str) -> str:
    """
    Lee el PDF con pdfplumber y devuelve todo el texto como string.
    Corre ANTES del grafo — el resultado entra al estado inicial.
    """
    texto = ""
    with pdfplumber.open(ruta) as pdf:
        for i, pagina in enumerate(pdf.pages):
            contenido = pagina.extract_text()
            if contenido:
                texto += f"\n--- Página {i+1} ---\n{contenido}"
    return texto


def autenticar_gmail():
    """
    Carga las credenciales de Gmail desde token.json.
    token.json lo generó test_gmail.py la primera vez que autorizaste el acceso.
    """
    SCOPES = ['https://www.googleapis.com/auth/gmail.compose']
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())   # renueva el token si expiró

    return creds


def guardar_borrador_gmail(asunto: str, cuerpo: str) -> str:
    """
    Llama a la API de Gmail y crea un borrador.
    El destinatario queda vacío — el usuario lo completa antes de enviar.
    Devuelve el ID del borrador creado.
    """
    creds = autenticar_gmail()
    service = build('gmail', 'v1', credentials=creds)

    mensaje = MIMEText(cuerpo)
    mensaje['to'] = ''
    mensaje['subject'] = asunto

    # Gmail requiere el mensaje codificado en base64
    raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()

    borrador = service.users().drafts().create(
        userId='me',
        body={'message': {'raw': raw}}
    ).execute()

    return borrador['id']


# ── NODOS ─────────────────────────────────────────────────────────────────────
#
# Un nodo es una función Python con esta firma:
#   def nombre_nodo(estado: Estado) -> dict
#
# Recibe el estado completo, hace su trabajo,
# y devuelve SOLO los campos que modificó.
# LangGraph fusiona esos cambios con el estado existente — no pisás
# los campos que no tocaste.
#
# Comparación con CrewAI:
#   CrewAI → Agent + Task, el framework llama al LLM por vos
#   LangGraph → función Python, vos llamás al LLM con .invoke() cuando querés
#   LangGraph da más control — ves exactamente qué pasa en cada paso

def nodo_analizar(estado: Estado) -> dict:
    """
    NODO 1 — Analiza el extracto bancario.
    Lee estado['extracto_texto'] y devuelve {'analisis': '...'}.
    """
    print("\n🔍 Analizando gastos del extracto...\n")

    # Llamada directa al LLM con .invoke()
    # SystemMessage = system prompt (quién es el modelo)
    # HumanMessage = mensaje del usuario (qué tiene que hacer)
    # En CrewAI esto lo hacía el framework por vos —
    # acá lo escribís explícitamente
    respuesta = llm_analista.invoke([
        SystemMessage(content=(
            "Sos un analista financiero experto en gastos empresariales. "
            "Analizás extractos bancarios y encontrás patrones de gasto. "
            "Respondés siempre en español rioplatense."
        )),
        HumanMessage(content=(
            f"Analizá este extracto bancario y clasificá los gastos:\n\n"
            f"{estado['extracto_texto']}\n\n"
            "Tu análisis debe incluir:\n"
            "1. Categorías de gasto con montos totales\n"
            "2. Los 3 rubros con mayor gasto\n"
            "3. Gastos inusuales o que merecen atención\n"
            "4. Tendencias observadas\n\n"
            "Sé específico con los números del extracto."
        ))
    ])

    print("   ✓ Análisis completado\n")
    return {"analisis": respuesta.content}
    # Solo actualizamos 'analisis' — el resto del estado queda intacto


def nodo_buscar_promedios(estado: Estado) -> dict:
    """
    NODO 2 — Busca promedios del sector en Google.
    No usa el estado de entrada — siempre hace la misma búsqueda.
    Devuelve {'promedios': '...'}.
    """
    print("🌐 Buscando promedios del sector en Google...\n")

    try:
        resultado = search.run(
            "gastos promedio empresas pymes Argentina 2024 2025 "
            "servicios tecnología administración"
        )
        print("   ✓ Promedios encontrados\n")
        return {"promedios": resultado[:2000]}
        # Limitamos a 2000 caracteres para no sobrecargar el prompt del redactor

    except Exception as e:
        print(f"   ⚠ No se pudieron obtener promedios: {e}\n")
        return {"promedios": "No se pudieron obtener promedios del sector."}


def nodo_redactar(estado: Estado) -> dict:
    """
    NODO 3 — Redacta el borrador del mail.

    Lee estado['analisis'] y estado['promedios'] para redactar.
    Si estado['feedback'] tiene instrucciones de cambio, las incorpora.

    Este nodo puede ejecutarse MÁS DE UNA VEZ en el mismo flujo.
    Primera vez: redacta desde cero.
    Siguientes veces: incorpora el feedback del usuario.
    Eso es posible porque el estado PERSISTE entre ejecuciones —
    cuando el grafo vuelve a este nodo, el análisis y los promedios
    ya están en el estado, no hay que buscarlos de nuevo.
    """
    print("✍️  Redactando borrador del mail...\n")

    # Si el usuario pidió cambios, los incorporamos al prompt
    # feedback vacío o "sí"/"no" = primera vez o respuesta de confirmación
    instruccion_feedback = ""
    if estado.get("feedback") and estado["feedback"] not in ["si", "sí", "no", ""]:
        instruccion_feedback = (
            f"\n\nIMPORTANTE — El usuario pidió estos cambios:\n"
            f"'{estado['feedback']}'\n"
            f"Incorporalos en esta nueva versión."
        )

    respuesta = llm_redactor.invoke([
        SystemMessage(content=(
            "Sos un redactor ejecutivo especializado en informes financieros. "
            "Escribís de forma clara, directa y profesional. "
            "Escribís en español rioplatense."
        )),
        HumanMessage(content=(
            f"Redactá un mail ejecutivo con el análisis de gastos.\n\n"
            f"ANÁLISIS DEL EXTRACTO:\n{estado['analisis']}\n\n"
            f"PROMEDIOS DEL SECTOR:\n{estado['promedios']}\n\n"
            f"Requisitos:\n"
            f"- Asunto: 'Análisis de Gastos — {estado['nombre_archivo']}'\n"
            f"- Párrafo inicial: contexto breve\n"
            f"- Hallazgos clave con números concretos\n"
            f"- Comparación con promedios del sector\n"
            f"- 3 recomendaciones accionables al final\n"
            f"- Máximo 400 palabras\n"
            f"- Campo 'Para:' vacío\n"
            f"{instruccion_feedback}"
        ))
    ])

    print("   ✓ Borrador redactado\n")
    return {"borrador": respuesta.content}


def nodo_pedir_confirmacion(estado: Estado) -> dict:
    """
    NODO 4 — Muestra el borrador y espera la decisión del usuario.

    Acá el grafo se PAUSA y espera input humano.
    Lo que escriba el usuario determina a qué nodo va el grafo después.
    En LangChain esto sería imposible — las cadenas no tienen pausa.
    En LangGraph es natural — es simplemente un nodo que hace input().
    """
    print("\n" + "=" * 60)
    print("📧 BORRADOR DEL MAIL")
    print("=" * 60)
    print(estado["borrador"])
    print("=" * 60)
    print("\nOpciones:")
    print("  'sí'    → guardar el borrador en Gmail")
    print("  'no'    → cancelar sin guardar")
    print("  [otro]  → describí los cambios que querés hacer")
    print()

    feedback_nuevo = input("¿Qué hacemos con este borrador? ").strip()

    # Si el usuario pidió cambios, los acumulamos en el mismo campo feedback
    # separados por " | " para que nodo_redactar los vea todos juntos.
    # Ejemplo después de dos pedidos: "cambiá el título | solo 2 recomendaciones"
    feedback_acumulado = feedback_nuevo.lower()
    if feedback_nuevo.lower() not in ["si", "sí", "no"]:
        feedback_anterior = estado.get("feedback", "")
        if feedback_anterior and feedback_anterior not in ["si", "sí", "no", ""]:
            # Ya había cambios anteriores — los sumamos al nuevo
            feedback_acumulado = feedback_anterior + " | " + feedback_nuevo
        else:
            feedback_acumulado = feedback_nuevo

    # Guardamos el feedback acumulado en el estado.
    # La función decidir_despues_de_confirmacion lo va a leer
    # para saber a qué nodo mandar el grafo.
    return {
        "feedback": feedback_acumulado,
        "confirmado": feedback_nuevo.lower() in ["si", "sí"]
    }


def nodo_guardar(estado: Estado) -> dict:
    """
    NODO 5a — Guarda el borrador en Gmail.
    Solo se ejecuta si el usuario escribió 'sí'.
    """
    print("\n💾 Guardando borrador en Gmail...\n")

    asunto = f"Análisis de Gastos — {estado['nombre_archivo']}"
    borrador_id = guardar_borrador_gmail(asunto, estado["borrador"])

    print(f"   ✓ Borrador guardado en Gmail")
    print(f"   ID: {borrador_id}")
    print(f"   Buscalo en 'Borradores' — agregale el destinatario y envialo.\n")

    return {"confirmado": True}


def nodo_cancelado(estado: Estado) -> dict:
    """
    NODO 5b — Informa que el proceso fue cancelado.
    Solo se ejecuta si el usuario escribió 'no'.
    """
    print("\n❌ Proceso cancelado. No se guardó ningún borrador.\n")
    return {}


# ── FUNCIÓN DE DECISIÓN ───────────────────────────────────────────────────────
#
# LangGraph llama a esta función después de nodo_pedir_confirmacion.
# Lee el estado y devuelve un string que indica a qué nodo ir.
# Ese string tiene que coincidir con las claves del diccionario
# en add_conditional_edges().

def decidir_despues_de_confirmacion(estado: Estado) -> str:
    feedback = estado.get("feedback", "").lower()

    if feedback in ["si", "sí"]:
        return "guardar"

    elif feedback == "no":
        return "cancelado"

    else:
        # Cualquier otra cosa = instrucciones de cambio → volvemos a redactar
        print(f"\n   📝 Incorporando cambios: '{feedback}'\n")
        return "redactar"


# ── CONSTRUCCIÓN DEL GRAFO ────────────────────────────────────────────────────
#
# El grafo completo se ve así:
#
#   [analizar] → [buscar_promedios] → [redactar] → [pedir_confirmacion]
#                                          ↑                |
#                                          |          sí → [guardar] → FIN
#                                          |          no → [cancelado] → FIN
#                                          └── cambios ────┘
#
# Los tres primeros edges son lineales — igual que LangChain.
# El edge condicional después de pedir_confirmacion es lo que
# diferencia LangGraph: puede volver atrás y crear el loop.

def construir_grafo():

    # StateGraph(Estado) crea el grafo y le dice qué tipo de formulario usar.
    # En CrewAI le pasabas los agentes al Crew.
    # En LangGraph le pasás el Estado — los nodos los agregás después.
    grafo = StateGraph(Estado)

    # Registramos cada nodo con un nombre y su función
    grafo.add_node("analizar", nodo_analizar)
    grafo.add_node("buscar_promedios", nodo_buscar_promedios)
    grafo.add_node("redactar", nodo_redactar)
    grafo.add_node("pedir_confirmacion", nodo_pedir_confirmacion)
    grafo.add_node("guardar", nodo_guardar)
    grafo.add_node("cancelado", nodo_cancelado)

    # El punto de entrada — por dónde empieza el grafo
    grafo.set_entry_point("analizar")

    # Edges fijos — siempre van al mismo nodo siguiente, sin decisión
    grafo.add_edge("analizar", "buscar_promedios")
    grafo.add_edge("buscar_promedios", "redactar")
    grafo.add_edge("redactar", "pedir_confirmacion")

    # Edge condicional — después de pedir_confirmacion, llama a
    # decidir_despues_de_confirmacion y va al nodo que ella indique.
    # "redactar" en el diccionario crea el loop — es lo que LangChain no puede hacer.
    grafo.add_conditional_edges(
        "pedir_confirmacion",             # desde este nodo
        decidir_despues_de_confirmacion,  # esta función decide
        {
            "guardar":   "guardar",
            "cancelado": "cancelado",
            "redactar":  "redactar",      # ← el loop
        }
    )

    # Los nodos finales van a END — terminan el grafo
    grafo.add_edge("guardar", END)
    grafo.add_edge("cancelado", END)

    # compile() valida el grafo y lo convierte en un objeto ejecutable
    # Equivalente a crew = Crew(...) en CrewAI
    return grafo.compile()


# ── PUNTO DE ENTRADA ──────────────────────────────────────────────────────────

def pedir_pdf():
    """Pide la ruta del PDF y valida que exista."""
    print("\n" + "=" * 60)
    print("AGENTE ANALIZADOR DE GASTOS — LangGraph + Gmail")
    print("=" * 60)
    print("\nArrastrá el extracto bancario (PDF) a la terminal.\n")

    while True:
        ruta = input("📄 Ruta del PDF: ").strip().strip('"').strip("'")
        archivo = Path(ruta)

        if not archivo.exists():
            print(f"   ✗ No se encontró: {ruta}\n")
            continue

        if archivo.suffix.lower() != '.pdf':
            print(f"   ✗ No es un PDF: {archivo.name}\n")
            continue

        print(f"\n   ✓ {archivo.name} ({archivo.stat().st_size / 1024:.1f} KB)\n")
        return str(archivo.resolve()), archivo.name


if __name__ == "__main__":

    # Paso 1: pedimos el PDF
    ruta_pdf, nombre_archivo = pedir_pdf()

    # Paso 2: extraemos el texto ANTES del grafo
    # El texto del PDF entra directamente al estado inicial —
    # no hay un nodo para esto porque no necesita el LLM
    print("Extrayendo texto del PDF...")
    texto = extraer_texto_pdf(ruta_pdf)
    print(f"   ✓ {len(texto)} caracteres extraídos\n")

    # Paso 3: construimos el grafo
    agente = construir_grafo()

    # Paso 4: estado inicial — solo los datos de entrada
    # Los demás campos los van completando los nodos a medida que avanzan
    estado_inicial = {
        "extracto_texto": texto,
        "nombre_archivo": nombre_archivo,
        "analisis": "",        # lo llena nodo_analizar
        "promedios": "",       # lo llena nodo_buscar_promedios
        "borrador": "",        # lo llena nodo_redactar
        "feedback": "",        # lo llena nodo_pedir_confirmacion
        "confirmado": False,   # lo actualiza nodo_guardar
    }

    print("Iniciando el agente...\n")

    # Paso 5: ejecutamos el grafo
    # agente.invoke() es el equivalente a crew.kickoff() en CrewAI.
    # Arranca desde el entry point y corre hasta llegar a un nodo END.
    # Si el usuario pide cambios, el grafo hace el loop internamente
    # hasta que confirme o cancele.
    estado_final = agente.invoke(estado_inicial)

    print("\n" + "=" * 60)
    print("Proceso finalizado.")
    print("=" * 60 + "\n")