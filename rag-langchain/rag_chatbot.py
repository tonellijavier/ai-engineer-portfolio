# ==============================================================================
# CHATBOT CON RAG DINÁMICO — LangChain + Chroma + Groq
# ==============================================================================
#
# ¿QUÉ HACE?
# Chatbot que responde preguntas sobre tus documentos.
# Podés agregar PDFs en cualquier momento durante la conversación
# y el sistema empieza a buscar en todos los documentos cargados.
#
# Comandos durante el chat:
#   "agregar"  → carga un PDF nuevo a la base de conocimiento
#   "docs"     → muestra los documentos cargados hasta ahora
#   "salir"    → cierra el programa
#
# ANTES DE CORRERLO:
#   pip install langchain langchain-community langchain-groq langchain-classic
#               chromadb pypdf sentence-transformers python-dotenv
#
# En el archivo .env:
#   GROQ_API_KEY=gsk_tu-key-acá
# ==============================================================================

import os
from pathlib import Path
from dotenv import load_dotenv

# ── IMPORTS DE LANGCHAIN ──────────────────────────────────────────────────────

from langchain_groq import ChatGroq
# ChatGroq es el conector entre LangChain y la API de Groq.
# Le dice a LangChain "usá este modelo para generar respuestas".

from langchain_community.document_loaders import PyPDFLoader
# PyPDFLoader lee un archivo PDF y devuelve su texto página por página.
# Cada página queda como un objeto "Document" con texto + metadata (número de página).

from langchain_text_splitters import RecursiveCharacterTextSplitter
# Divide el texto en fragmentos más pequeños.
# "Recursive" significa que primero intenta cortar por párrafos,
# después por oraciones, después por palabras — respeta la estructura del texto.

from langchain_community.vectorstores import Chroma
# Chroma es la base de datos vectorial.
# Guarda los fragmentos como vectores y permite buscar por similitud semántica.
# Corre localmente en tu computadora — no necesita ningún servidor externo.

from langchain_community.embeddings import HuggingFaceEmbeddings
# HuggingFaceEmbeddings carga un modelo de machine learning que convierte
# texto en vectores (listas de números que representan el significado).
# Corre localmente — no llama a ninguna API.

from langchain_classic.chains import RetrievalQA
# RetrievalQA es la "cadena" que une todo el flujo RAG:
# recibe la pregunta → busca fragmentos → arma el prompt → llama al modelo → devuelve respuesta.
# "Chain" en LangChain = una secuencia de pasos conectados.

from langchain_classic.prompts import PromptTemplate
# PromptTemplate es un molde para el prompt.
# Tiene variables ({context}, {question}) que se rellenan en tiempo real
# antes de mandarle el prompt al modelo.

load_dotenv()  # lee el archivo .env y carga GROQ_API_KEY como variable de entorno


# ── MODELO ────────────────────────────────────────────────────────────────────

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.1,
    # Temperature baja — queremos respuestas precisas basadas en el documento,
    # no respuestas creativas que se inventen cosas que no están ahí.
)


# ── EMBEDDINGS ────────────────────────────────────────────────────────────────

print("\nCargando modelo de embeddings...")
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
# "all-MiniLM-L6-v2" es el nombre del modelo que convierte texto en vectores.
# Se descarga la primera vez (~90MB) y queda guardado en tu computadora.
# La próxima vez que corrás el programa, carga desde el caché local — más rápido.
#
# ¿Por qué necesitamos esto?
# Para buscar por SIGNIFICADO, no por palabras exactas.
# Si el PDF habla de "remuneración" y el usuario pregunta por "sueldo",
# los embeddings los reconocen como conceptos similares y encuentran el fragmento.
print("   ✓ Listo\n")


# ── TEXT SPLITTER ─────────────────────────────────────────────────────────────

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    # Cada fragmento tiene máximo 1000 caracteres (~150 palabras).
    # ¿Por qué no meter el PDF entero? Porque el prompt tiene un límite de tokens
    # y queremos pasar solo los fragmentos relevantes, no todo el documento.

    chunk_overlap=200,
    # Los últimos 200 caracteres de un fragmento se repiten al inicio del siguiente.
    # Esto evita que una idea quede cortada entre dos fragmentos.
    # Sin overlap: "El sueldo es de $X | mensuales brutos" → dos fragmentos incompletos.
    # Con overlap: el "$X" aparece en ambos fragmentos → ninguno queda incompleto.
)
# Lo definimos una sola vez y lo reutilizamos para todos los PDFs que se agreguen.


# ── PROMPT TEMPLATE ───────────────────────────────────────────────────────────

template = """Sos un asistente que responde preguntas basándote
exclusivamente en los documentos proporcionados.

Contexto de los documentos:
{context}

Pregunta: {question}

Instrucciones:
- Respondé solo con información del contexto proporcionado
- Si la información no está en los documentos, decilo claramente
- Respondé en español, de forma clara y concisa
- Si es relevante, mencioná de qué documento viene la información

Respuesta:"""
# {context} → se reemplaza con los fragmentos encontrados por Chroma
# {question} → se reemplaza con la pregunta del usuario
# Esto es lo que realmente le llega al modelo antes de generar la respuesta.

prompt = PromptTemplate(
    template=template,
    input_variables=["context", "question"]
    # Le decimos a LangChain cuáles son las variables del template
    # para que sepa qué reemplazar antes de llamar al modelo.
)


# ==============================================================================
# FUNCIONES
# ==============================================================================

def pedir_pdf(mensaje="📄 Ruta del PDF: "):
    """
    Pide una ruta de PDF al usuario en un loop hasta que sea válida.
    Acepta rutas con o sin comillas (Windows agrega comillas al arrastrar archivos).
    """
    while True:
        ruta = input(mensaje).strip().strip('"').strip("'")
        # .strip() saca espacios al inicio y al final
        # .strip('"') saca las comillas que Windows agrega al arrastrar un archivo
        archivo = Path(ruta)

        if not archivo.exists():
            print(f"   ✗ No se encontró: {ruta}\n")
            continue  # vuelve al inicio del loop y pide de nuevo

        if archivo.suffix.lower() != '.pdf':
            print(f"   ✗ No es un PDF: {archivo.name}\n")
            continue

        print(f"   ✓ {archivo.name} ({archivo.stat().st_size / 1024:.1f} KB)\n")
        return str(archivo.resolve())
        # .resolve() convierte la ruta relativa en ruta absoluta completa
        # Ej: "documento.pdf" → "C:\Users\tonel\...\documento.pdf"


def procesar_pdf(ruta_pdf: str):
    """
    Carga un PDF y lo divide en fragmentos listos para indexar.

    El resultado es una lista de objetos Document, donde cada uno tiene:
      - page_content: el texto del fragmento
      - metadata: diccionario con "source" (ruta del archivo) y "page" (número de página)

    Ese metadata es lo que usamos después para mostrar "basado en página X".
    """
    loader = PyPDFLoader(ruta_pdf)
    paginas = loader.load()
    # paginas es una lista de Documents, uno por página del PDF

    fragmentos = splitter.split_documents(paginas)
    # split_documents divide cada página en fragmentos más pequeños
    # y preserva el metadata original (número de página, fuente)

    return fragmentos


def agregar_documento(vector_store, documentos_cargados: list):
    """
    Agrega un PDF nuevo a la vector store que ya existe.

    Lo clave: add_documents() suma sin borrar.
    La vector store ya tiene los fragmentos del documento anterior
    y ahora agrega los del nuevo. Desde este momento, las búsquedas
    devuelven fragmentos de TODOS los documentos cargados.
    """
    print("\nAgregá un documento nuevo a la base de conocimiento.")
    ruta = pedir_pdf()
    nombre = Path(ruta).name

    if nombre in documentos_cargados:
        print(f"   ⚠ '{nombre}' ya está cargado.\n")
        return  # evitamos indexar el mismo documento dos veces

    print(f"Procesando '{nombre}'...")
    fragmentos = procesar_pdf(ruta)

    vector_store.add_documents(fragmentos)
    # add_documents agrega los nuevos fragmentos a la vector store existente.
    # No reinicia nada — simplemente suma más vectores a la base.

    documentos_cargados.append(nombre)
    print(f"   ✓ '{nombre}' agregado — {len(fragmentos)} fragmentos indexados")
    print(f"   📚 Documentos en la base: {', '.join(documentos_cargados)}\n")


def crear_cadena(vector_store):
    """
    Crea la cadena RAG completa — el objeto que une todos los pasos.

    ¿Por qué es una función separada y no se crea una sola vez?
    Porque cuando agregamos un documento nuevo, necesitamos recrear
    la cadena para que use el retriever actualizado con los nuevos fragmentos.
    """
    return RetrievalQA.from_chain_type(
        # RetrievalQA coordina las otras piezas — no busca ni genera él solo.
        # Es como el director de orquesta: Chroma busca, PromptTemplate arma,
        # ChatGroq genera. RetrievalQA decide el orden y les pasa el resultado.
        llm=llm,
        # El modelo que genera la respuesta final.

        chain_type="stuff",
        # "stuff" = mete todos los fragmentos encontrados en un solo prompt.
        # Alternativas: "map_reduce" (resume cada fragmento por separado y combina)
        # o "refine" (procesa fragmento por fragmento refinando la respuesta).
        # Para la mayoría de los casos "stuff" es suficiente y más simple.

        retriever=vector_store.as_retriever(search_kwargs={"k": 4}),
        # as_retriever() convierte la vector store en un "buscador".
        # k=4 → busca los 4 fragmentos más similares a la pregunta.
        # Podés subir k para más contexto, pero más fragmentos = más tokens = más costo.

        chain_type_kwargs={"prompt": prompt},
        # Le pasamos nuestro PromptTemplate personalizado.
        # Sin esto, LangChain usaría su prompt por default en inglés.
        # El prompt que usa es 'sos un asistente...', no es el input del usuario

        return_source_documents=True,
        # Que devuelva también los fragmentos que usó para responder.
        # Esto es lo que nos permite mostrar "basado en página X del documento Y".
    )


def chat_loop(vector_store, documentos_cargados: list):
    """
    Loop principal de conversación.

    Un loop infinito que espera input del usuario.
    Según lo que escriba, hace una de tres cosas:
      - Ejecuta un comando ("agregar", "docs", "salir")
      - Responde una pregunta usando RAG
    """
    print("=" * 60)
    print("✓ Sistema listo. Podés hacer preguntas.")
    print("Comandos: 'agregar' | 'docs' | 'salir'")
    print("=" * 60 + "\n")

    cadena = crear_cadena(vector_store)
    # Creamos la cadena una vez al inicio.
    # Se recrea solo cuando el usuario agrega un documento nuevo.

    while True:
        entrada = input("❓ Pregunta o comando: ").strip()

        if not entrada:
            continue  # si el usuario presionó Enter sin escribir nada, ignoramos

        # ── COMANDOS ──────────────────────────────────────────────────────────

        if entrada.lower() == 'salir':
            print("\nHasta luego.")
            break  # sale del loop y termina el programa

        if entrada.lower() == 'docs':
            # Muestra qué documentos están indexados en este momento
            print(f"\n📚 Documentos cargados ({len(documentos_cargados)}):")
            for i, doc in enumerate(documentos_cargados, 1):
                print(f"   {i}. {doc}")
            print()
            continue

        if entrada.lower() == 'agregar':
            agregar_documento(vector_store, documentos_cargados)
            cadena = crear_cadena(vector_store)
            # Recreamos la cadena para que el retriever incluya los nuevos fragmentos
            continue

        # ── PREGUNTA ──────────────────────────────────────────────────────────
        # Si no era un comando, es una pregunta — ejecutamos el RAG completo

        print("\n🔍 Buscando en los documentos...\n")

        resultado = cadena.invoke({"query": entrada})
        # cadena.invoke() ejecuta todo el flujo RAG:
        # 1. Convierte la pregunta en vector
        # 2. Busca los 4 fragmentos más similares en Chroma
        # 3. Rellena el PromptTemplate con esos fragmentos + la pregunta
        # 4. Llama a Groq con ese prompt
        # 5. Devuelve la respuesta + los fragmentos usados
        # Extra: en LangChain le pasás {"query": "..."}.
        # El nombre de la clave query es el que espera RetrievalQA internamente para saber -
        # cuál es la pregunta del usuario
        # invoke() no crea nada nuevo — ejecuta la cadena que ya fue configurada.
        # Es el equivalente a crew.kickoff() en CrewAI.

        respuesta = resultado["result"]
        # El texto de la respuesta generada por el modelo

        fuentes = resultado["source_documents"]
        # Lista de los fragmentos que usó — cada uno tiene metadata con página y fuente

        print("💬 Respuesta:")
        print("-" * 40)
        print(respuesta)

        # Construimos el resumen de fuentes agrupando por documento y página
        origen = {}
        for doc in fuentes:
            nombre_doc = Path(doc.metadata.get("source", "?")).name
            pagina = doc.metadata.get("page", 0) + 1
            # +1 porque las páginas en el metadata empiezan desde 0
            if nombre_doc not in origen:
                origen[nombre_doc] = set()
            origen[nombre_doc].add(pagina)

        if origen:
            print("\n📄 Fuentes:")
            for doc_name, paginas in origen.items():
                print(f"   {doc_name} — página(s) {sorted(paginas)}")

        print("\n")


# ==============================================================================
# PUNTO DE ENTRADA
# ==============================================================================

if __name__ == "__main__":

    print("=" * 60)
    print("CHATBOT CON RAG DINÁMICO")
    print("=" * 60)
    print("\nArrastrá el PDF a la terminal o escribí la ruta completa.\n")

    # Paso 1: pedimos el primer PDF — obligatorio para arrancar
    ruta_inicial = pedir_pdf()
    nombre_inicial = Path(ruta_inicial).name

    # Paso 2: procesamos el PDF (carga + división en fragmentos)
    print(f"Procesando '{nombre_inicial}'...")
    fragmentos_iniciales = procesar_pdf(ruta_inicial)
    print(f"   ✓ {len(fragmentos_iniciales)} fragmentos generados")

    # Paso 3: creamos la vector store con esos fragmentos
    # Chroma.from_documents hace dos cosas:
    #   1. Convierte cada fragmento en vector usando los embeddings
    #   2. Guarda todos esos vectores en memoria
    print("Indexando en base de datos vectorial...")
    vector_store = Chroma.from_documents(
        documents=fragmentos_iniciales,
        embedding=embeddings,
    )
    print(f"   ✓ Base vectorial lista\n")

    # Lista que vamos actualizando cada vez que se agrega un documento
    documentos_cargados = [nombre_inicial]

    # Paso 4: arrancamos el chat
    chat_loop(vector_store, documentos_cargados)