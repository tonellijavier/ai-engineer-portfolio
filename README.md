# AI Engineer Portfolio

Proyectos de AI Engineering construidos con CrewAI, LangChain y LangGraph. Cubren sistemas multi-agente, RAG, tool use y flujos conversacionales con estados.

---

## Proyectos

### 1. Crew Investigador de Temas
**Archivo:** `mi_primer_crew.py`

Equipo de 3 agentes que trabajan en cadena para investigar cualquier tema y producir un resumen ejecutivo.

**Agentes:** Investigador Senior → Analista Crítico → Redactor Ejecutivo

**Conceptos aplicados:** multi-agente secuencial, context entre tareas, system prompt dinámico, temperature diferenciada por agente.

---

### 2. Analizador de CVs
**Archivo:** `crew-analiza-cvs.py`

Lee un CV en PDF y produce un análisis completo con score, fortalezas, áreas de mejora y las preguntas difíciles que te van a hacer en la entrevista.

**Agentes:** Evaluador de Perfiles (temperature 0.5) → Coach de Entrevistas (temperature 0.9)

**Conceptos aplicados:** procesamiento de PDFs con pdfplumber, temperatures distintas según el rol, outputs separados por agente.

---

### 3. Investigador de Empresas
**Archivo:** `crew-analiza-empresas.py`

Le pasás el nombre de una empresa y un rol, y el crew investiga todo lo que necesitás saber antes de una entrevista — buscando en Google en tiempo real.

**Agentes:** Investigador con SerperDevTool → Analista → Coach

**Conceptos aplicados:** tool use real con SerperDevTool, búsquedas en Google en tiempo real, tres temperatures distintas (0.1 / 0.3 / 0.9).

---

### 4. Chatbot RAG Dinámico
**Carpeta:** `rag-langchain/`

Chatbot que responde preguntas sobre tus documentos en lenguaje natural. Podés agregar PDFs en cualquier momento — el sistema empieza a buscar en todos los documentos cargados. Muestra de qué documento y qué página viene cada respuesta.

**Conceptos aplicados:** RAG completo, base de datos vectorial con Chroma, embeddings semánticos con HuggingFace, búsqueda por significado (no por palabras exactas).

---

### 5. Agente Analizador de Gastos
**Carpeta:** `agente-gastos-gmail/`

Agente que lee un extracto bancario en PDF, analiza los gastos, los compara con promedios del sector buscados en Google, y redacta un borrador de mail. El usuario puede pedir cambios antes de confirmar — el agente incorpora todo el feedback y guarda el borrador final en Gmail.

**Conceptos aplicados:** LangGraph con estados persistentes y edges condicionales, loop de confirmación, integración con Gmail API, feedback acumulativo entre iteraciones.

---

### 6. Chatbot Bancario
**Carpeta:** `chatbot-bancario/`

Simulador de chatbot bancario con memoria conversacional y base de datos real. El cliente puede consultar saldo, ver movimientos y realizar transferencias.

**Decisión de diseño clave:** el chatbot tiene dos modos completamente separados. El LLM maneja la conversación libre. Para transferencias, el código toma el control — sin LLM. En operaciones financieras se necesita código determinista, no probabilístico. Las llamadas al LLM se monitorean con LangSmith — las transferencias no generan trazas porque el modelo no participa.

**Conceptos aplicados:** system prompt dinámico, message history con LangGraph, código determinista para operaciones sensibles, PostgreSQL real con Neon, detección de duplicados, logs de auditoría separados del log de conversación, observabilidad con LangSmith.

---

## Stack

| Framework | Proyectos |
|---|---|
| CrewAI + LiteLLM | Proyectos 1, 2 y 3 |
| LangChain + Chroma | Proyecto 4 |
| LangGraph | Proyectos 5 y 6 |
| Neon (PostgreSQL) | Proyecto 6 |
| LangSmith | Proyecto 6 |

**Modelos:** Groq (`llama-3.3-70b-versatile`) — compatible con Claude (Anthropic) y otros via LiteLLM

**Tools:** SerperDevTool (búsqueda web), pdfplumber (PDFs), HuggingFace Embeddings, Gmail API, psycopg2 (PostgreSQL)

---

## Setup

**Proyectos 1, 2 y 3 (CrewAI):**
```bash
pip install crewai crewai-tools python-dotenv litellm pdfplumber
```

**Proyecto 4 (RAG LangChain):**
```bash
pip install langchain langchain-community langchain-groq langchain-classic chromadb pypdf sentence-transformers python-dotenv
```

**Proyecto 5 (LangGraph + Gmail):**
```bash
python -m venv venv
venv\Scripts\activate
pip install langgraph langchain-groq langchain-community langchain-core pdfplumber python-dotenv google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

**Proyecto 6 (Chatbot Bancario):**
```bash
pip install langgraph langchain-groq langchain-core python-dotenv psycopg2-binary
```

Variables de entorno necesarias en `.env`:
```
GROQ_API_KEY=tu-key              # gratis en console.groq.com
SERPER_API_KEY=tu-key            # gratis en serper.dev (proyectos 3 y 5)
DATABASE_URL=postgresql://...    # gratis en console.neon.tech (proyecto 6)
LANGCHAIN_API_KEY=tu-key         # gratis en smith.langchain.com (proyecto 6)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=chatbot-bancario
```

---

## Correr los proyectos

**Proyecto 1**
```bash
python mi_primer_crew.py
```

**Proyecto 2**
```bash
python crew-analiza-cvs.py
```

**Proyecto 3**
```bash
python crew-analiza-empresas.py
```

**Proyecto 4**
```bash
cd rag-langchain
python rag_chatbot.py
```

**Proyecto 5**
```bash
cd agente-gastos-gmail
venv\Scripts\activate
python test_gmail.py    # solo la primera vez — autentica Gmail
python agente_gastos.py
```

**Proyecto 6**
```bash
cd chatbot-bancario
python setup_db.py     # solo la primera vez — crea las tablas en Neon
python main.py
```