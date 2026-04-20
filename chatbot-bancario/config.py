# ==============================================================================
# CONFIG — Configuración global del sistema
# ==============================================================================
#
# Todo lo que necesita estar disponible en cualquier parte del código:
#   - Conexión a la base de datos
#   - Instancia del modelo LLM
#   - Variables de entorno
#
# ¿Por qué un archivo separado?
# Si mañana cambiás de Groq a Claude, o de Neon a otra DB,
# solo tocás este archivo. El resto del código no sabe nada de estos detalles.
# ==============================================================================

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

# ── MODELO ────────────────────────────────────────────────────────────────────
# Instancia única del LLM — se importa desde acá en cualquier módulo
# Para cambiar a Claude: ChatAnthropic(model="claude-sonnet-4-6")
# El resto del código no cambia nada.

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
)


# ── BASE DE DATOS ─────────────────────────────────────────────────────────────

def get_conn():
    """
    Crea una conexión a Neon (PostgreSQL).
    RealDictCursor devuelve filas como diccionarios — accedemos por nombre
    de columna (fila["saldo"]) en lugar de por índice (fila[0]).
    """
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        cursor_factory=psycopg2.extras.RealDictCursor
    )