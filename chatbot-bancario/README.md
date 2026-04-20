# Chatbot Bancario — LangGraph + Groq + Neon (PostgreSQL)

Simulador de chatbot bancario con memoria conversacional y base de datos real. El cliente puede consultar saldo, ver movimientos y realizar transferencias. Los datos persisten en PostgreSQL (Neon) entre sesiones.

---

## Decisión de diseño central

El chatbot tiene **dos modos completamente separados**:

**Modo conversación** — el LLM responde libremente con acceso al historial completo. Maneja saludos, consultas de saldo, preguntas sobre productos y movimientos.

**Modo transferencia** — el código toma el control. El LLM no participa. El código valida cada dato, detecta duplicados, ejecuta con SQL y persiste en PostgreSQL.

Esta separación es intencional y refleja cómo funcionan los sistemas bancarios reales: un LLM puede alucinar o malinterpretar montos. Para operaciones financieras se necesita código determinista — predecible, trazable y auditable.

---

## ¿Qué puede hacer el cliente?

- Consultar saldo, productos y últimos movimientos
- Realizar transferencias a contactos habilitados
- El sistema detecta transferencias duplicadas y avisa antes de confirmar
- Los cambios persisten en PostgreSQL — el saldo es correcto en la próxima sesión

---

## Flujo de transferencia

```
Cliente dice "transferir"
        ↓
Código activa el modo transferencia
        ↓
¿A quién? → búsqueda determinista en contactos (PostgreSQL)
        ↓
¿Cuánto? → extracción con regex + validación de saldo
        ↓
¿Duplicado? → revisión del historial de movimientos
        ↓
Resumen → espera confirmación explícita (sí / no)
        ↓
Ejecuta → UPDATE saldo + INSERT movimiento en PostgreSQL
```

En ningún paso de este flujo interviene el LLM.

---

## Base de datos — Neon (PostgreSQL)

Tres tablas:

```sql
clientes     → dni, nombre, saldo, productos
contactos    → id, dni_cliente, nombre, cbu, alias
movimientos  → id, dni_cliente, fecha, descripcion, monto
```

Las operaciones SQL que ejecuta el código:

```sql
-- Al iniciar sesión
SELECT nombre, dni, saldo, productos FROM clientes WHERE dni = %s
SELECT nombre, cbu, alias FROM contactos WHERE dni_cliente = %s
SELECT fecha, descripcion, monto FROM movimientos WHERE dni_cliente = %s

-- Al ejecutar una transferencia
UPDATE clientes SET saldo = %s WHERE dni = %s
INSERT INTO movimientos (dni_cliente, fecha, descripcion, monto) VALUES (...)
```

---

## Logs de sesión

Al cerrar la sesión se genera un archivo `sesion_FECHA.json` con dos secciones separadas:

**`operaciones`** — log de auditoría. Solo lo que se ejecutó: qué, cuándo, cuánto, a quién. Los bancos están obligados por regulación a guardar esto.

**`conversacion`** — log de diálogo. Todos los mensajes del chat en orden. Sirve para mejorar el bot y dar soporte al cliente.

---

## Técnicas aplicadas

- **System prompt dinámico** — los datos del cliente se consultan desde PostgreSQL al inicio e inyectan en el contexto del modelo
- **Message history** — `add_messages` de LangGraph acumula todos los mensajes sin reemplazarlos, dándole memoria al chatbot
- **Código determinista** — el flujo de transferencia no usa LLM en ningún paso
- **PostgreSQL real** — saldo y movimientos persisten en Neon entre sesiones
- **Detección de duplicados** — compara la operación con el historial de movimientos
- **Logs de auditoría separados** del log de conversación, como en producción real

---

## Pendientes documentados

- [ ] Refactorizar el flujo de transferencia con nodos separados en LangGraph — cada paso sería un nodo distinto con edges condicionales
- [ ] Agregar autenticación — ahora el DNI está hardcodeado, en producción vendría del login

---

## Stack

- **LangGraph** — manejo del estado entre turnos con `add_messages`
- **LangChain + Groq** — modelo `llama-3.3-70b-versatile` para el modo conversación
- **Neon (PostgreSQL)** — base de datos serverless para persistencia real
- **psycopg2** — driver de Python para PostgreSQL
- **Python puro** — flujo de transferencia, logs, validaciones

---

## Setup

```bash
pip install langgraph langchain-groq langchain-core python-dotenv psycopg2-binary
```

Creá un archivo `.env`:

```
GROQ_API_KEY=tu-key        # gratis en console.groq.com
DATABASE_URL=postgresql://usuario:password@host/neondb?sslmode=require
```

Para obtener el `DATABASE_URL`: console.neon.tech → tu proyecto → Connect → Connection string.

---

## Correr el proyecto

```bash
# Solo la primera vez — crea las tablas y carga los datos iniciales
python setup_db.py

# Después — corré el chatbot
python chatbot.py
```

Escribí `salir` para terminar la sesión y guardar el log.