# ==============================================================================
# MI PRIMER CREW — Sistema multi-agente con CrewAI + Groq
# ==============================================================================
#
# ¿QUÉ HACE ESTE SCRIPT?
# Crea un equipo de 3 agentes de IA que trabajan en cadena:
#   1. Un investigador recopila información sobre un tema
#   2. Un analista evalúa críticamente esa información
#   3. Un redactor transforma todo en un resumen ejecutivo
#
# Cada agente recibe el trabajo del anterior automáticamente.
# Esto es lo que se llama un sistema multi-agente secuencial.
#
# ANTES DE CORRERLO (una sola vez):
#   pip install crewai python-dotenv litellm
#
# Creá un archivo .env en esta carpeta con:
#   GROQ_API_KEY=gsk_tu-key-acá
#
# Key gratuita en: console.groq.com → API Keys → Create Key
#
# PARA CORRERLO:
#   python mi_primer_crew.py
# ==============================================================================


# ── IMPORTS ───────────────────────────────────────────────────────────────────

import os
from dotenv import load_dotenv       # lee el archivo .env con la API key
from crewai import Agent, Task, Crew, Process
#                  ↑       ↑     ↑      ↑
#               agentes  tareas equipo  modo de trabajo


# ── CONFIGURACIÓN INICIAL ─────────────────────────────────────────────────────

# load_dotenv() busca el archivo .env en la carpeta y carga las variables.
# Así la API key queda en un archivo separado y nunca se sube a GitHub.
load_dotenv()

# El modelo que van a usar todos los agentes.
# Formato de LiteLLM: "proveedor/nombre-del-modelo"
# Groq es gratis. Para cambiar a Claude: "anthropic/claude-sonnet-4-6"
MODEL = "groq/llama-3.3-70b-versatile"

# El tema que va a investigar el crew.
# Podés cambiar esto por cualquier tema que te interese.
TEMA = "El impacto de la inteligencia artificial en el mercado laboral argentino"


# ==============================================================================
# AGENTES — los especialistas del equipo
# ==============================================================================
#
# Un Agent en CrewAI tiene 4 ingredientes clave:
#
#   role      → la identidad del agente (quién es)
#   goal      → su objetivo principal (qué tiene que lograr)
#   backstory → su experiencia y filosofía (cómo piensa y qué prioriza)
#   llm       → el modelo de IA que lo "corre"
#
# CrewAI toma estos 4 ingredientes y construye el system prompt
# automáticamente. Es exactamente role prompting, pero en forma de objeto.
#
# verbose=True hace que el agente muestre su proceso en la terminal.
# Cambialo a False en producción para un output más limpio.

investigador = Agent(
    role="Investigador Senior",
    goal=(
        "Recopilar información actualizada, datos concretos y perspectivas "
        "diversas sobre el tema asignado."
    ),
    backstory=(
        "Sos un periodista de investigación con 15 años de experiencia. "
        "Sabés encontrar información relevante y distinguir datos concretos "
        "de opiniones. Siempre buscás múltiples perspectivas antes de "
        "llegar a conclusiones. Sos especialmente bueno contextualizando "
        "tendencias globales en el contexto argentino."
    ),
    verbose=True,
    llm=MODEL,
)

analista = Agent(
    role="Analista Crítico",
    goal=(
        "Analizar la información recibida, identificar los insights más "
        "relevantes y señalar contradicciones o puntos débiles."
    ),
    backstory=(
        "Sos economista con especialización en análisis de tendencias. "
        "Tenés un ojo entrenado para encontrar lo que realmente importa. "
        "Sos escéptico de las generalizaciones y priorizás los datos concretos. "
        "Antes de concluir siempre preguntás: '¿qué evidencia respalda esto?'"
    ),
    verbose=True,
    llm=MODEL,
)

redactor = Agent(
    role="Redactor Ejecutivo",
    goal=(
        "Transformar el análisis en un resumen claro, estructurado "
        "y útil para alguien que necesita entender el tema rápidamente."
    ),
    backstory=(
        "Escribís para personas que tienen poco tiempo. "
        "Tu fortaleza es convertir información compleja en narrativas claras. "
        "Nunca usás jerga innecesaria. Terminás siempre con conclusiones "
        "concretas y accionables. Escribís en español rioplatense."
    ),
    verbose=True,
    llm=MODEL,
)


# ==============================================================================
# TAREAS — el trabajo que hace cada agente
# ==============================================================================
#
# Una Task tiene 4 partes:
#
#   description     → las instrucciones detalladas (qué tiene que hacer)
#   expected_output → el formato exacto de lo que tiene que entregar
#   agent           → qué agente ejecuta esta tarea
#   context         → resultados de tareas anteriores que puede leer
#
# El parámetro "context" es la clave del sistema multi-agente:
# cuando lo definís, CrewAI inyecta automáticamente el output
# de esas tareas en el prompt de esta tarea. El agente "ve"
# el trabajo de los anteriores sin que vos hagas nada.

# TAREA 1: investigación
# No tiene "context" porque es la primera — arranca de cero.
# Usamos f-string para insertar la variable TEMA en la descripción.
tarea_investigacion = Task(
    description=(
        f"Investigá en profundidad el siguiente tema:\n'{TEMA}'\n\n"
        "Tu entrega debe incluir:\n"
        "- Los 5 datos o estadísticas más relevantes\n"
        "- Las principales tendencias identificadas\n"
        "- Perspectivas a favor y en contra\n"
        "- Contexto específico para Argentina\n"
        "- Qué sectores son los más impactados"
    ),
    expected_output=(
        "Un informe de investigación estructurado con datos concretos, "
        "múltiples perspectivas y contexto argentino. Entre 300 y 400 palabras."
    ),
    agent=investigador,   # el investigador ejecuta esta tarea
)

# TAREA 2: análisis
# context=[tarea_investigacion] significa que el analista va a recibir
# el output del investigador antes de empezar su trabajo.
# No tiene que "pedirlo" — CrewAI lo pasa automáticamente.
tarea_analisis = Task(
    description=(
        "Analizá la investigación que recibís y producí un análisis crítico.\n\n"
        "Tu análisis debe:\n"
        "- Identificar los 3 insights más importantes\n"
        "- Señalar qué datos merecen escepticismo y por qué\n"
        "- Evaluar impacto real vs impacto percibido\n"
        "- Identificar qué grupos son más vulnerables\n"
        "- Señalar oportunidades no obvias"
    ),
    expected_output=(
        "Un análisis crítico con insights priorizados y evaluación "
        "de la solidez de la evidencia. Entre 200 y 300 palabras."
    ),
    agent=analista,
    context=[tarea_investigacion],   # lee el trabajo del investigador
)

# TAREA 3: redacción
# Esta tarea recibe el output de LAS DOS anteriores.
# El redactor ve tanto la investigación como el análisis
# antes de escribir el resumen final.
tarea_redaccion = Task(
    description=(
        "Redactá un resumen ejecutivo basado en la investigación y el análisis.\n\n"
        "Requisitos:\n"
        "- Máximo 400 palabras en total\n"
        "- Español rioplatense, tono profesional pero accesible\n"
        "- Estructura: contexto breve → hallazgos clave → implicancias\n"
        "- Cerrá con exactamente 3 recomendaciones concretas\n"
        "- Principalmente prosa fluida, no listas excesivas\n"
        "- No uses frases de relleno como 'en conclusión' o 'en resumen'"
    ),
    expected_output=(
        "Un resumen ejecutivo de máximo 400 palabras en prosa fluida, "
        "con sección final de 3 recomendaciones concretas."
    ),
    agent=redactor,
    context=[tarea_investigacion, tarea_analisis],   # lee los dos anteriores
)


# ==============================================================================
# CREW — el equipo completo
# ==============================================================================
#
# El Crew agrupa los agentes y las tareas, y define cómo trabajan juntos.
#
# Process.sequential = trabajan en orden, uno tras otro.
# La tarea 1 termina → empieza la 2 → termina → empieza la 3.
#
# Existe también Process.hierarchical, donde hay un agente "manager"
# que delega y coordina — más avanzado, para el próximo proyecto.

crew = Crew(
    agents=[investigador, analista, redactor],
    tasks=[tarea_investigacion, tarea_analisis, tarea_redaccion],
    process=Process.sequential,
    verbose=True,   # muestra el progreso del crew en la terminal
)


# ==============================================================================
# EJECUCIÓN
# ==============================================================================
#
# El bloque "if __name__ == '__main__'" es una convención de Python:
# garantiza que este código solo corre cuando ejecutás el archivo
# directamente, no cuando lo importás desde otro módulo.
#
# crew.kickoff() es el "botón de play" — arranca todo el proceso.
# Sin esta línea, los agentes y tareas están definidos pero no hacen nada.
# Cuando termina, devuelve el resultado final de la última tarea.

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("ARRANCANDO EL CREW")
    print(f"Tema: {TEMA}")
    print(f"Modelo: {MODEL}")
    print("=" * 60 + "\n")

    # Acá empieza toda la magia — los 3 agentes trabajan en cadena
    resultado = crew.kickoff()

    print("\n" + "=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60 + "\n")
    print(resultado)


# ==============================================================================
# PRÓXIMOS PASOS — cómo extender este proyecto
# ==============================================================================
#
# 1. INPUTS DINÁMICOS — cambiar el tema sin tocar el código:
#
#    En las tareas, reemplazás la f-string por una variable con llaves:
#      description="Investigá: '{tema}'"   ← así CrewAI la reemplaza
#
#    Y al llamar al crew:
#      resultado = crew.kickoff(inputs={"tema": "Crypto en Argentina"})
#
# 2. CAMBIAR A CLAUDE — cuando tengas la API key de Anthropic:
#
#    MODEL = "anthropic/claude-sonnet-4-6"
#    En el .env: ANTHROPIC_API_KEY=sk-ant-...
#    Todo lo demás queda igual — esa es la gracia de CrewAI.
#
# 3. AGREGAR TOOLS — darle herramientas a los agentes:
#
#    from crewai_tools import SerperDevTool
#    search_tool = SerperDevTool()
#    investigador = Agent(..., tools=[search_tool])
#    Ahora el investigador puede buscar en internet de verdad.
#
# 4. PROCESS HIERARCHICAL — sumar un manager que coordine:
#
#    crew = Crew(..., process=Process.hierarchical, manager_llm=MODEL)
#    El manager decide qué agente hace qué, en qué orden.