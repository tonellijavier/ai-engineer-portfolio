# Chatbot RAG Dinámico — LangChain + Chroma + Groq

Chatbot que responde preguntas sobre tus documentos en lenguaje natural. Podés agregar PDFs en cualquier momento durante la conversación y el sistema empieza a buscar en todos los documentos cargados.

---

## ¿Qué hace?

1. Cargás un PDF y el sistema lo indexa en una base de datos vectorial
2. Hacés preguntas en lenguaje natural sobre el contenido
3. El sistema busca los fragmentos más relevantes y responde con información real del documento
4. Podés agregar más PDFs en cualquier momento — sin reiniciar
5. Cada respuesta muestra de qué documento y qué página viene la información

---

## Comandos durante el chat

| Comando | Acción |
|---|---|
| `agregar` | Carga un PDF nuevo a la base de conocimiento |
| `docs` | Muestra los documentos cargados |
| `salir` | Cierra el programa |

---

## Por qué RAG

El modelo no fue entrenado con tus documentos — no los conoce. RAG (Retrieval Augmented Generation) soluciona esto: antes de responder, el sistema busca los fragmentos más relevantes del documento y se los pasa al modelo como contexto. El modelo responde basándose en esa información real, no en su entrenamiento.

---

## Stack

- **LangChain** — pipeline RAG completo
- **Chroma** — base de datos vectorial local
- **HuggingFace Embeddings** — modelo `all-MiniLM-L6-v2` para búsqueda semántica
- **Groq** — modelo `llama-3.3-70b-versatile` para generación de respuestas
- **pypdf** — extracción de texto de PDFs

---

## Setup

```bash
pip install langchain langchain-community langchain-groq langchain-classic chromadb pypdf sentence-transformers python-dotenv
```

Creá un archivo `.env`:

```
GROQ_API_KEY=tu-key        # gratis en console.groq.com
```

---

## Correr el proyecto

```bash
python rag_chatbot.py
```

La primera vez descarga el modelo de embeddings (~90MB) — después queda en caché local.