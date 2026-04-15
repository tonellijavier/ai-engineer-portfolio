# ==============================================================================
# ANALIZADOR DE CV + COACH DE ENTREVISTAS — CrewAI + Groq
# ==============================================================================
#
# ¿QUÉ HACE?
# Lee un CV en PDF y lo procesa con 2 agentes en cadena:
#
#   Agente 1 — Evaluador (temp 0.5)
#              Analiza el CV: score, fortalezas, áreas de mejora,
#              sugerencias concretas y roles sugeridos.
#
#   Agente 2 — Coach de entrevistas (temp 0.9)
#              Recibe el análisis y genera las preguntas difíciles
#              que le harían en una entrevista, con tips para responderlas.
#              Temperature alta → preguntas variadas e inesperadas.
#
# ANTES DE CORRERLO:
#   pip install crewai python-dotenv litellm pdfplumber
#
# En el archivo .env:
#   GROQ_API_KEY=gsk_tu-key-acá
#
# PARA CORRERLO:
#   python analizador_cv.py
# ==============================================================================

import sys
from pathlib import Path
import pdfplumber
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM

load_dotenv()

# ── PEDIR EL PDF ──────────────────────────────────────────────────────────────

def pedir_pdf():
    print("\n" + "=" * 60)
    print("ANALIZADOR DE CV + COACH DE ENTREVISTAS")
    print("=" * 60)
    print("\nArrastrá el PDF a la terminal o escribí la ruta completa.\n")

    while True:
        ruta = input("📄 Ruta del PDF: ").strip().strip('"').strip("'")
        archivo = Path(ruta)

        if not archivo.exists():
            print(f"   ✗ No se encontró: {ruta}\n")
            continue

        if archivo.suffix.lower() != '.pdf':
            print(f"   ✗ No es un PDF: {archivo.name}\n")
            continue

        print(f"\n   ✓ Encontrado: {archivo.name} ({archivo.stat().st_size / 1024:.1f} KB)\n")
        return str(archivo.resolve())


# ── EXTRAER TEXTO DEL PDF ─────────────────────────────────────────────────────

def extraer_texto_pdf(ruta_pdf: str) -> str:
    """
    Extrae el texto del PDF con pdfplumber.
    Más confiable que FileReadTool para PDFs con formato complejo.
    """
    texto = ""
    with pdfplumber.open(ruta_pdf) as pdf:
        for i, pagina in enumerate(pdf.pages):
            contenido = pagina.extract_text()
            if contenido:
                texto += f"\n--- Página {i+1} ---\n{contenido}"

    if not texto.strip():
        print("   ⚠ No se pudo extraer texto. El PDF puede ser una imagen escaneada.")
        sys.exit(1)

    print(f"   ✓ Texto extraído: {len(texto)} caracteres\n")
    return texto


# ── MODELOS ───────────────────────────────────────────────────────────────────

# El evaluador necesita ser preciso y consistente → temperature media
llm_evaluador = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0.5,
)

# El coach necesita ser creativo e impredecible → temperature alta
# Con temperature 0.9 las preguntas van a ser variadas y menos genéricas.
# Si lo corrés dos veces con el mismo CV, las preguntas van a ser distintas.
llm_coach = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0.9,
)


# ── FUNCIÓN PRINCIPAL ─────────────────────────────────────────────────────────

def analizar_cv(ruta_pdf: str):

    print("Extrayendo texto del PDF...")
    texto_cv = extraer_texto_pdf(ruta_pdf)
    nombre_archivo = Path(ruta_pdf).name

    # ── AGENTE 1: EVALUADOR ───────────────────────────────────────────────────
    # Analiza el CV y produce un informe estructurado.
    # Su output va a ser el input del coach vía context.

    evaluador = Agent(
        role="Evaluador de Perfiles Profesionales",
        goal=(
            "Leer el CV y producir un análisis honesto, "
            "constructivo y accionable del perfil."
        ),
        backstory=(
            "Sos un recruiter senior con más de 5.000 CVs revisados "
            "en empresas de tecnología de Latinoamérica. "
            "Sos directo pero constructivo — nombrás los problemas "
            "con sugerencias concretas para resolverlos. "
            "Sabés exactamente qué buscan las empresas tech hoy en día."
        ),
        verbose=True,
        llm=llm_evaluador,      # temperature 0.5 — análisis equilibrado
    )

    # ── AGENTE 2: COACH DE ENTREVISTAS ────────────────────────────────────────
    # Recibe el análisis del evaluador y genera preguntas difíciles.
    # Temperature alta → preguntas variadas, inesperadas, más realistas.
    # No tiene tools — trabaja solo con lo que le pasó el evaluador.

    coach = Agent(
        role="Coach de Entrevistas Técnicas",
        goal=(
            "Preparar al candidato para su entrevista generando las preguntas "
            "más difíciles que le van a hacer, basadas en su perfil real."
        ),
        backstory=(
            "Sos un coach de entrevistas con 10 años preparando candidatos "
            "para empresas tech como Mercado Libre, Globant y startups. "
            "Conocés exactamente qué preguntas hacen los interviewers "
            "cuando ven gaps, cambios de carrera o logros poco claros en un CV. "
            "No hacés preguntas genéricas — las personalizás al perfil. "
            "Sos honesto sobre las partes del CV que van a generar preguntas incómodas."
        ),
        verbose=True,
        llm=llm_coach,          # temperature 0.9 — preguntas creativas e inesperadas
    )

    # ── TAREA 1: EVALUACIÓN ───────────────────────────────────────────────────
    # El texto del CV se inserta directamente en la descripción.
    # El agente lo recibe como parte del prompt — sin tools.

    tarea_evaluacion = Task(
        description=(
            f"Analizá el siguiente CV del archivo '{nombre_archivo}'.\n\n"
            "═══════════════════ CONTENIDO DEL CV ═══════════════════\n"
            f"{texto_cv}\n"
            "════════════════════════════════════════════════════════\n\n"
            "Producí un análisis completo con esta estructura exacta:\n\n"
            "SCORE GENERAL (0-100):\n"
            "Un número con una oración que justifique el puntaje.\n\n"
            "FORTALEZAS (exactamente 3):\n"
            "Lo que más destaca y por qué llama la atención de un recruiter.\n\n"
            "ÁREAS DE MEJORA (exactamente 3):\n"
            "Lo que falta o podría presentarse mejor. Sé específico.\n\n"
            "SUGERENCIAS CONCRETAS (exactamente 3):\n"
            "Acciones específicas que puede hacer esta semana.\n\n"
            "ROLES SUGERIDOS (exactamente 3):\n"
            "Roles para los que aplicaría, con una oración de justificación.\n\n"
            "Escribí en español rioplatense. Tono directo y profesional."
        ),
        expected_output=(
            "Análisis completo con score, fortalezas, áreas de mejora, "
            "sugerencias y roles sugeridos. En español."
        ),
        agent=evaluador,
    )

    # TAREA 2: COACHING DE ENTREVISTAS ─────────────────────────────────────────
    # Recibe el análisis completo del evaluador vía context.
    # El coach ve el score, las debilidades y las fortalezas
    # antes de generar las preguntas — así las personaliza al perfil real.

    tarea_coaching = Task(
        description=(
            "Recibiste el análisis completo del CV. "
            "Usá esa información para preparar al candidato para su entrevista.\n\n"
            "Tu entrega debe tener esta estructura:\n\n"
            "PREGUNTAS DIFÍCILES (exactamente 5):\n"
            "Las preguntas más incómodas que le van a hacer, basadas en "
            "los gaps y áreas débiles identificadas en el análisis. "
            "No preguntas genéricas — preguntas específicas al perfil.\n"
            "Para cada pregunta incluí:\n"
            "  - La pregunta exacta como la haría el interviewer\n"
            "  - Por qué la van a hacer (qué están evaluando)\n"
            "  - Cómo responderla bien (tip concreto de 2-3 oraciones)\n\n"
            "PREGUNTA TRAMPA (1):\n"
            "La pregunta más inesperada que podría aparecer, "
            "que el candidato probablemente no anticipa.\n"
            "Con explicación de cómo desarmarla.\n\n"
            "CONSEJO FINAL (1 párrafo):\n"
            "Lo más importante que tiene que tener en mente este candidato "
            "específico al entrar a la entrevista.\n\n"
            "Escribí en español rioplatense. Sé directo y honesto — "
            "mejor que se prepare para lo peor que llegar sin estar listo."
        ),
        expected_output=(
            "5 preguntas difíciles personalizadas con tips de respuesta, "
            "1 pregunta trampa y 1 consejo final. En español."
        ),
        agent=coach,
        context=[tarea_evaluacion],     # recibe el análisis completo del evaluador
    )

    # ── CREW ──────────────────────────────────────────────────────────────────

    crew = Crew(
        agents=[evaluador, coach],
        tasks=[tarea_evaluacion, tarea_coaching],
        process=Process.sequential,
        verbose=True,
    )

    # kickoff() devuelve el output de la ÚLTIMA tarea.
    # Para obtener los outputs de TODAS las tareas, usamos tasks_output
    # que CrewAI llena automáticamente después de kickoff().
    crew.kickoff()

    # Cada tarea guarda su resultado en .output.raw después de ejecutarse
    analisis    = tarea_evaluacion.output.raw
    preguntas   = tarea_coaching.output.raw

    return analisis, preguntas


# ── PUNTO DE ENTRADA ──────────────────────────────────────────────────────────

if __name__ == "__main__":

    ruta_pdf = pedir_pdf()

    print("Iniciando análisis... esto puede tardar 60-90 segundos.\n")

    analisis, preguntas = analizar_cv(ruta_pdf)

    # ── BLOQUE 1: análisis del CV ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📋 ANÁLISIS DEL CV")
    print("=" * 60 + "\n")
    print(analisis)

    # ── BLOQUE 2: coaching de entrevistas ──────────────────────────────────
    print("\n" + "=" * 60)
    print("🎯 COACHING DE ENTREVISTAS")
    print("=" * 60 + "\n")
    print(preguntas)

    print("\n" + "=" * 60 + "\n")