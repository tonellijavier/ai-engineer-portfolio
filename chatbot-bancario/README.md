# Chatbot Bancario — LangGraph + Groq

Simulador de chatbot bancario con memoria conversacional. El cliente puede consultar saldo, ver movimientos y realizar transferencias. El sistema recuerda el hilo de la conversación entre mensajes.

---

## Decisión de diseño central

El chatbot tiene **dos modos completamente separados**:

**Modo conversación** — el LLM responde libremente con acceso al historial completo. Maneja saludos, consultas de saldo, preguntas sobre productos y movimientos.

**Modo transferencia** — el código toma el control. El LLM no participa. El código valida cada dato, detecta duplicados y ejecuta la operación.

Esta separación es intencional y refleja cómo funcionan los sistemas bancarios reales: un LLM puede alucinar o malinterpretar montos. Para operaciones financieras se necesita código determinista — predecible, trazable y auditable.

---

## ¿Qué puede hacer el cliente?

- Consultar saldo, productos y últimos movimientos
- Realizar transferencias a contactos habilitados
- El sistema detecta transferencias duplicadas y avisa antes de confirmar
- Todo se guarda al cerrar la sesión

---

## Flujo de transferencia

```
Cliente dice "transferir"
        ↓
Código activa el modo transferencia
        ↓
¿A quién? → búsqueda determinista en contactos habilitados
        ↓
¿Cuánto? → extracción con regex + validación de saldo
        ↓
¿Duplicado? → revisión del historial de movimientos
        ↓
Resumen → espera confirmación explícita (sí / no)
        ↓
Ejecuta → actualiza JSON + registra en log de auditoría
```

En ningún paso de este flujo interviene el LLM.

---

## Logs de sesión

Al cerrar la sesión se genera un archivo `sesion_FECHA.json` con dos secciones separadas:

**`operaciones`** — log de auditoría. Solo lo que se ejecutó: qué, cuándo, cuánto, a quién. Los bancos están obligados por regulación a guardar esto. Es inmutable.

**`conversacion`** — log de diálogo. Todos los mensajes del chat en orden. Sirve para mejorar el bot y dar soporte al cliente.

---

## Técnicas aplicadas

- **System prompt dinámico** — los datos del cliente se cargan desde el JSON al inicio e inyectan en el contexto del modelo
- **Message history** — `add_messages` de LangGraph acumula todos los mensajes sin reemplazarlos, dándole memoria al chatbot
- **Código determinista** — el flujo de transferencia no usa LLM en ningún paso
- **Detección de duplicados** — compara la operación solicitada con el historial de movimientos
- **Persistencia** — el JSON se actualiza inmediatamente al ejecutar cada transferencia

---

## Pendientes documentados

- [ ] Refactorizar el flujo de transferencia con nodos separados en LangGraph — cada paso sería un nodo distinto con edges condicionales
- [ ] Migrar de JSON a PostgreSQL (Neon) — los datos operativos deberían vivir en una base de datos real

---

## Stack

- **LangGraph** — manejo del estado entre turnos con `add_messages`
- **LangChain + Groq** — modelo `llama-3.3-70b-versatile` para el modo conversación
- **Python puro** — flujo de transferencia, logs, persistencia

---

## Setup

```bash
pip install langgraph langchain-groq langchain-core python-dotenv
```

Creá un archivo `.env`:

```
GROQ_API_KEY=tu-key        # gratis en console.groq.com
```

---

## Correr el proyecto

```bash
python chatbot.py
```

Escribí `salir` para terminar la sesión y guardar el log.