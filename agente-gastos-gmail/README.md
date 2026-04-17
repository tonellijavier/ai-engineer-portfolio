# Agente Analizador de Gastos — LangGraph + Gmail

Agente que lee un extracto bancario en PDF, analiza los gastos, los compara con promedios del sector y redacta un informe como borrador de mail en Gmail.

---

## ¿Qué hace?

1. Cargás un extracto bancario en PDF
2. El agente analiza y clasifica los gastos por categoría
3. Busca promedios del sector en Google en tiempo real
4. Redacta un borrador de mail con el análisis y recomendaciones
5. Muestra el borrador y espera tu confirmación
6. Si confirmás → guarda en Gmail como borrador listo para enviar
7. Si pedís cambios → vuelve a redactar incorporando tu feedback
8. Si cancelás → termina sin guardar nada

---

## Por qué LangGraph

El flujo depende de lo que decide el usuario en cada momento — puede confirmar, cancelar o pedir cambios N veces antes de guardar. Eso requiere un loop con estados, que LangChain no soporta. LangGraph permite definir bifurcaciones y loops donde el grafo vuelve a nodos anteriores según la decisión del usuario.

---

## Stack

- **LangGraph** — flujo con estados y edges condicionales
- **LangChain + Groq** — modelo llama-3.3-70b-versatile para análisis y redacción
- **SerperDevTool** — búsqueda de promedios del sector en Google en tiempo real
- **pdfplumber** — extracción de texto del extracto bancario
- **Gmail API** — guardado del borrador en Gmail

---

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install langgraph langchain-groq langchain-community langchain-core pdfplumber python-dotenv google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

Creá un archivo `.env`:

```
GROQ_API_KEY=tu-key        # gratis en console.groq.com
SERPER_API_KEY=tu-key      # gratis en serper.dev
```

Para conectar Gmail, necesitás un archivo `credentials.json` de Google Cloud Console con la Gmail API habilitada. Corrés `test_gmail.py` primero para autenticar y generar `token.json`.

---

## Correr el proyecto

```bash
# Primero — autenticá Gmail (solo la primera vez)
python test_gmail.py

# Después — corrés el agente
python agente_gastos.py
```