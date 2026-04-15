# AI Engineer Portfolio

Proyectos de AI Engineering construidos con CrewAI, sistemas multi-agente y tool use real.

---

## Proyectos

### 1. Crew Investigador de Temas
**Archivo:** `mi_primer_crew.py`

Equipo de 3 agentes que trabajan en cadena para investigar cualquier tema y producir un resumen ejecutivo.

**Agentes:**
- Investigador Senior — recopila información y datos
- Analista Crítico — evalúa la información y detecta gaps
- Redactor Ejecutivo — transforma el análisis en un resumen accionable

**Conceptos aplicados:** multi-agente secuencial, context entre tareas, system prompt dinámico automático, temperature diferenciada por agente.

---

### 2. Analizador de CVs
**Archivo:** `crew-analiza-cvs.py`

Lee un CV en PDF y produce un análisis completo con score, fortalezas, áreas de mejora y coaching de entrevistas.

**Agentes:**
- Evaluador de Perfiles — analiza el CV y produce el informe (temperature 0.5)
- Coach de Entrevistas — genera las preguntas difíciles personalizadas al perfil (temperature 0.9)

**Conceptos aplicados:** procesamiento de PDFs con pdfplumber, dos temperatures distintas según el rol, outputs separados por agente.

---

### 3. Investigador de Empresas
**Archivo:** `crew-analiza-empresas.py`

Le pasás el nombre de una empresa y un rol, y el crew investiga todo lo que necesitás saber antes de una entrevista.

**Agentes:**
- Investigador (SerperDevTool) — busca en Google: cultura, stack, noticias, reviews
- Analista — extrae los insights más relevantes para la entrevista
- Coach — prepara al candidato con estrategias concretas

**Conceptos aplicados:** tool use real con SerperDevTool, búsquedas en Google en tiempo real, tres temperatures distintas (0.1 / 0.3 / 0.9).

---

## Stack

- **Framework:** CrewAI
- **Modelos:** Groq (llama-3.3-70b-versatile) / compatible con Claude (Anthropic)
- **Tools:** SerperDevTool (búsqueda web), pdfplumber (procesamiento PDF)
- **Abstracción de modelos:** LiteLLM

## Setup

```bash
pip install crewai crewai-tools python-dotenv litellm pdfplumber
```

Creá un archivo `.env` en la carpeta del proyecto:

```
GROQ_API_KEY=tu-key        # gratis en console.groq.com
SERPER_API_KEY=tu-key      # gratis en serper.dev (proyecto 3)
```

## Correr los proyectos

```bash
# Proyecto 1
python mi_primer_crew.py

# Proyecto 2
python crew-analiza-cvs.py

# Proyecto 3
python crew-analiza-empresas.py
```
