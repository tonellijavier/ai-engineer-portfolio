# ==============================================================================
# SETUP DE LA BASE DE DATOS — Neon (PostgreSQL)
# ==============================================================================
#
# Corré este script UNA SOLA VEZ para:
#   1. Crear las tablas en Neon
#   2. Cargar los datos iniciales del cliente
#
# Después de correrlo, el chatbot usa la DB en lugar del JSON.
#
# PARA CORRERLO:
#   python setup_db.py
# ==============================================================================

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Nos conectamos a Neon con la connection string del .env
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("Conectado a Neon. Creando tablas...")

# ── CREAR TABLAS ──────────────────────────────────────────────────────────────

cur.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        dni         VARCHAR(20) PRIMARY KEY,
        nombre      VARCHAR(100) NOT NULL,
        saldo       DECIMAL(12,2) NOT NULL DEFAULT 0,
        productos   TEXT[]
        -- TEXT[] es un array de strings en PostgreSQL
        -- Guarda la lista de productos del cliente
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS contactos (
        id          SERIAL PRIMARY KEY,
        -- SERIAL = autoincremento — la DB asigna el ID automáticamente
        dni_cliente VARCHAR(20) REFERENCES clientes(dni),
        -- REFERENCES = clave foránea — este contacto pertenece a ese cliente
        nombre      VARCHAR(100) NOT NULL,
        cbu         VARCHAR(50)  NOT NULL,
        alias       VARCHAR(50)
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS movimientos (
        id          SERIAL PRIMARY KEY,
        dni_cliente VARCHAR(20) REFERENCES clientes(dni),
        fecha       DATE NOT NULL,
        descripcion VARCHAR(200) NOT NULL,
        monto       DECIMAL(12,2) NOT NULL
        -- monto positivo = ingreso, negativo = egreso
    )
""")

print("   ✓ Tablas creadas")

# ── CARGAR DATOS INICIALES ────────────────────────────────────────────────────
# Mismos datos que tenía datos_banco.json — ahora en PostgreSQL

# Cliente
cur.execute("""
    INSERT INTO clientes (dni, nombre, saldo, productos)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (dni) DO NOTHING
    -- ON CONFLICT DO NOTHING = si el cliente ya existe, no falla ni duplica
""", (
    "12345678",
    "Javier",
    150000.00,
    ["Caja de ahorro en pesos", "Tarjeta Visa débito", "Préstamo personal activo"]
))

# Contactos
contactos = [
    ("12345678", "Juan Pérez",   "0000003100025786490015", "juan.perez"),
    ("12345678", "María García", "0000003100025786490022", "maria.garcia"),
    ("12345678", "Carlos López", "0000003100025786490033", "carlos.lopez"),
]

for dni, nombre, cbu, alias in contactos:
    cur.execute("""
        INSERT INTO contactos (dni_cliente, nombre, cbu, alias)
        SELECT %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM contactos WHERE alias = %s
        )
    """, (dni, nombre, cbu, alias, alias))

# Movimientos
movimientos = [
    ("12345678", "2025-03-01", "Netflix",                    -1500.00),
    ("12345678", "2025-03-01", "Supermercado Dia",           -8500.00),
    ("12345678", "2025-03-02", "Netflix",                    -1500.00),
    ("12345678", "2025-03-03", "Sueldo marzo",              120000.00),
    ("12345678", "2025-03-05", "OSDE",                      -12000.00),
    ("12345678", "2025-03-07", "YPF combustible",            -6000.00),
    ("12345678", "2025-03-10", "Transferencia a Juan Pérez", -5000.00),
]

for dni, fecha, desc, monto in movimientos:
    cur.execute("""
        INSERT INTO movimientos (dni_cliente, fecha, descripcion, monto)
        SELECT %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM movimientos
            WHERE dni_cliente = %s AND fecha = %s AND descripcion = %s
        )
    """, (dni, fecha, desc, monto, dni, fecha, desc))

conn.commit()
print("   ✓ Datos iniciales cargados")

# Verificamos que todo quedó bien
cur.execute("SELECT nombre, saldo FROM clientes WHERE dni = '12345678'")
cliente = cur.fetchone()
print(f"   ✓ Cliente: {cliente[0]} — Saldo: ${cliente[1]:,.2f}")

cur.execute("SELECT COUNT(*) FROM contactos WHERE dni_cliente = '12345678'")
print(f"   ✓ Contactos: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM movimientos WHERE dni_cliente = '12345678'")
print(f"   ✓ Movimientos: {cur.fetchone()[0]}")

cur.close()
conn.close()

print("\n¡Listo! La base de datos está configurada.")
print("Ya podés correr chatbot.py con Neon.")