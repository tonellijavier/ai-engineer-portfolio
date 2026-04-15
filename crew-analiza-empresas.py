# ==============================================================================
# INVESTIGADOR DE EMPRESAS — CrewAI + SerperDevTool + Groq
# ==============================================================================
#
# ¿QUÉ HACE?
# Le pasás el nombre de una empresa y un rol, y un crew de 3 agentes
# investiga todo lo que necesitás saber antes de una entrevista:
#
#   Agente 1 — Investigador (SerperDevTool, temp 0.1)
#              Busca en Google: cultura, stack, noticias, reviews de empleados.
#              TOOL USE REAL — el agente decide qué buscar y cuándo.
#
#   Agente 2 — Analista (sin tools, temp 0.3)
#              Recibe la investigación y extrae los insights más relevantes
#              para prepararse para una entrevista en esa empresa.
#
#   Agente 3 — Coach de entrevistas (sin tools, temp 0.9)
#              Recibe el análisis y prepara al candidato:
#              qué preguntar, qué destacar, qué evitar.
#
# ANTES DE CORRERLO:
#   pip install crewai crewai-tools python-dotenv litellm
#
# En el archivo .env:
#   GROQ_API_KEY=gsk_tu-key-acá
#   SERPER_API_KEY=tu-key-acá   ← gratis en serper.dev (2500 búsquedas/mes)
#
# PARA CORRERLO:
#   python crew-analiza-empresas.py
# ==============================================================================

from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import SerperDevTool

load_dotenv()

# ── HERRAMIENTA DE BÚSQUEDA ───────────────────────────────────────────────────
# SerperDevTool usa la API de Serper para buscar en Google.
# El agente decide cuándo usarla y con qué query — eso es tool use real.
# Sin esta tool, el investigador respondería desde su entrenamiento
# y los datos podrían estar desactualizados.
search_tool = SerperDevTool()

# ── PEDIR DATOS AL USUARIO ────────────────────────────────────────────────────

def pedir_datos():
    print("\n" + "=" * 60)
    print("INVESTIGADOR DE EMPRESAS — Preparación para entrevistas")
    print("=" * 60 + "\n")

    empresa = input("🏢 Nombre de la empresa: ").strip()
    rol     = input("💼 Rol al que aplicás: ").strip()

    print(f"\n   ✓ Empresa: {empresa}")
    print(f"   ✓ Rol: {rol}\n")

    return empresa, rol


# ── MODELOS ───────────────────────────────────────────────────────────────────

llm_investigador = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0.1,    # preciso — necesita buscar y reportar con exactitud
)

llm_analista = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0.3,    # consistente — análisis que no varía mucho entre ejecuciones
)

llm_coach = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0.9,    # creativo — consejos variados e inesperados
)


# ── FUNCIÓN PRINCIPAL ─────────────────────────────────────────────────────────

def investigar_empresa(empresa: str, rol: str):

    # ── AGENTE 1: INVESTIGADOR ────────────────────────────────────────────────
    # Este es el único agente con tools.
    # Tiene SerperDevTool — puede buscar en Google cuando lo necesite.
    # El modelo decide cuántas búsquedas hacer y con qué términos.
    # Podés ver en el verbose cómo elige los queries de búsqueda.

    investigador = Agent(
        role="Investigador de Empresas",
        goal=(
            f"Investigar todo lo relevante sobre {empresa} "
            f"para alguien que va a entrevistar para el rol de {rol}."
        ),
        backstory=(
            "Sos un investigador especializado en due diligence de empresas. "
            "Antes de cada entrevista investigás a fondo: cultura, stack tecnológico, "
            "noticias recientes, reviews de empleados en Glassdoor y LinkedIn, "
            "y cualquier dato que ayude a prepararse mejor. "
            "Hacés múltiples búsquedas desde distintos ángulos antes de concluir. "
            "Nunca inventás datos — si no encontrás algo, lo decís."
        ),
        tools=[search_tool],    # ← TOOL USE REAL — busca en Google
        verbose=True,
        llm=llm_investigador,
    )

    # ── AGENTE 2: ANALISTA ────────────────────────────────────────────────────
    # No tiene tools — trabaja con la investigación del agente anterior.
    # Su trabajo es filtrar lo que realmente importa para una entrevista
    # y descartar lo que es ruido o irrelevante.

    analista = Agent(
        role="Analista de Cultura y Fit Empresarial",
        goal=(
            "Analizar la información investigada y extraer los insights "
            "más relevantes para prepararse para una entrevista."
        ),
        backstory=(
            "Sos especialista en cultura organizacional con 8 años "
            "ayudando a candidatos a entender qué buscan realmente las empresas. "
            "Sabés distinguir el marketing corporativo de la realidad del día a día. "
            "Leés entre líneas en las job descriptions y en las reviews de empleados. "
            "Tu análisis siempre termina con conclusiones accionables."
        ),
        verbose=True,
        llm=llm_analista,       # sin tools — solo procesa lo que recibe
    )

    # ── AGENTE 3: COACH ───────────────────────────────────────────────────────
    # Temperature alta — consejos creativos y personalizados.
    # Recibe tanto la investigación como el análisis vía context.
    # Su trabajo es convertir todo eso en prep concreta para la entrevista.

    coach = Agent(
        role="Coach de Entrevistas",
        goal=(
            "Usar la investigación y el análisis para preparar al candidato "
            "con estrategias concretas para la entrevista."
        ),
        backstory=(
            "Sos coach de entrevistas con un track record impresionante: "
            "el 80% de tus candidatos consiguen el trabajo. "
            "Tu secreto es la preparación específica — nunca consejos genéricos. "
            "Sabés exactamente qué preguntar, qué decir y qué evitar "
            "según la cultura de cada empresa. "
            "Sos directo y honesto — preferís preparar para lo peor "
            "que dar falsas esperanzas."
        ),
        verbose=True,
        llm=llm_coach,          # temperature alta — consejos creativos
    )

    # ── TAREA 1: INVESTIGACIÓN ────────────────────────────────────────────────
    # El investigador tiene libertad para hacer las búsquedas que necesite.
    # Le damos una guía de qué buscar pero él decide los queries exactos.
    # Esto es tool use real — el modelo razona y decide cuándo y cómo buscar.

    tarea_investigacion = Task(
        description=(
            f"Investigá en profundidad la empresa '{empresa}' "
            f"para alguien que va a entrevistar para '{rol}'.\n\n"
            "Buscá información sobre:\n"
            "- Qué hace la empresa, su producto o servicio principal\n"
            "- Cultura y valores — cómo es trabajar ahí realmente\n"
            "- Stack tecnológico (si es empresa tech)\n"
            "- Noticias recientes — crecimiento, despidos, funding, cambios\n"
            "- Reviews de empleados (Glassdoor, LinkedIn, etc.)\n"
            "- Competidores principales\n"
            "- Tamaño, etapa (startup, scale-up, enterprise) y presencia en LATAM\n\n"
            "Hacé al menos 4 búsquedas con distintos ángulos.\n"
            "Si no encontrás algo, decilo explícitamente."
        ),
        expected_output=(
            "Un informe completo con información verificada sobre la empresa. "
            "Organizado por secciones. Entre 400 y 500 palabras."
        ),
        agent=investigador,     # único agente con tools
    )

    # ── TAREA 2: ANÁLISIS ─────────────────────────────────────────────────────
    # El analista recibe la investigación completa vía context.
    # Filtra lo importante y descarta el ruido.

    tarea_analisis = Task(
        description=(
            f"Analizá la investigación sobre '{empresa}' para el rol '{rol}'.\n\n"
            "Tu análisis debe incluir:\n\n"
            "QUÉ BUSCA ESTA EMPRESA EN UN CANDIDATO:\n"
            "Más allá del job description — qué valores y comportamientos realmente valoran.\n\n"
            "RED FLAGS A TENER EN CUENTA:\n"
            "Cosas de la investigación que el candidato debería considerar antes de aceptar.\n\n"
            "OPORTUNIDADES PARA DESTACAR:\n"
            "Qué aspectos del contexto de la empresa podés usar a tu favor en la entrevista.\n\n"
            "PREGUNTAS QUE VAN A HACER:\n"
            "Basado en la cultura y el rol, qué tipo de preguntas son probables.\n\n"
            "Sé específico — nada genérico que aplique a cualquier empresa."
        ),
        expected_output=(
            "Análisis con 4 secciones: qué buscan, red flags, "
            "oportunidades y preguntas probables. Entre 300 y 400 palabras."
        ),
        agent=analista,
        context=[tarea_investigacion],  # lee la investigación completa
    )

    # ── TAREA 3: COACHING ─────────────────────────────────────────────────────
    # El coach recibe TANTO la investigación como el análisis.
    # Con toda esa información genera prep concreta y personalizada.

    tarea_coaching = Task(
        description=(
            f"Preparé al candidato para su entrevista en '{empresa}' "
            f"para el rol de '{rol}'.\n\n"
            "Tu entrega debe tener:\n\n"
            "CÓMO ARRANCAR LA ENTREVISTA (primeros 5 minutos):\n"
            "Qué decir cuando te pregunten '¿quién sos?' — específico para esta empresa.\n\n"
            "3 PREGUNTAS QUE VOS TENÉS QUE HACER:\n"
            "Preguntas que demuestren que investigaste y que son relevantes para este rol.\n"
            "Con explicación de por qué cada una impacta positivamente.\n\n"
            "3 COSAS QUE NO DECIR:\n"
            "Errores específicos para esta empresa/cultura que arruinan la entrevista.\n\n"
            "EL MOMENTO CLAVE:\n"
            "El punto de la entrevista donde más se decide si quedás o no, "
            "y cómo manejarlo.\n\n"
            "Escribí en español rioplatense. Directo y concreto — "
            "nada que aplique a cualquier empresa."
        ),
        expected_output=(
            "Guía de preparación con 4 secciones: cómo arrancar, "
            "preguntas para hacer, cosas a evitar y el momento clave."
        ),
        agent=coach,
        context=[tarea_investigacion, tarea_analisis],  # lee los dos anteriores
    )

    # ── CREW ──────────────────────────────────────────────────────────────────

    crew = Crew(
        agents=[investigador, analista, coach],
        tasks=[tarea_investigacion, tarea_analisis, tarea_coaching],
        process=Process.sequential,
        verbose=True,
    )

    crew.kickoff()

    # Guardamos el output de cada tarea por separado
    investigacion = tarea_investigacion.output.raw
    analisis      = tarea_analisis.output.raw
    coaching      = tarea_coaching.output.raw

    return investigacion, analisis, coaching


# ── PUNTO DE ENTRADA ──────────────────────────────────────────────────────────

if __name__ == "__main__":

    empresa, rol = pedir_datos()

    print("Investigando... esto puede tardar 90-120 segundos.\n")

    investigacion, analisis, coaching = investigar_empresa(empresa, rol)

    print("\n" + "=" * 60)
    print("🔍 INVESTIGACIÓN DE LA EMPRESA")
    print("=" * 60 + "\n")
    print(investigacion)

    print("\n" + "=" * 60)
    print("📊 ANÁLISIS — QUÉ IMPORTA PARA TU ENTREVISTA")
    print("=" * 60 + "\n")
    print(analisis)

    print("\n" + "=" * 60)
    print("🎯 COACHING — CÓMO PREPARARTE")
    print("=" * 60 + "\n")
    print(coaching)

    print("\n" + "=" * 60 + "\n")