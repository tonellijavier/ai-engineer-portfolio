# ==============================================================================
# DATABASE/QUERIES — Todas las consultas SQL en un solo lugar
# ==============================================================================
#
# ¿Por qué separado?
# Si mañana migrás de Neon a otra base de datos, solo tocás este archivo.
# El resto del código no sabe de dónde vienen los datos — solo llama
# a estas funciones y recibe diccionarios Python.
#
# Cada función tiene una responsabilidad única:
#   cargar_datos_banco()   → SELECT de cliente, contactos y movimientos
#   actualizar_saldo()     → UPDATE del saldo
#   insertar_movimiento()  → INSERT de un movimiento nuevo
# ==============================================================================

from config import get_conn


def cargar_datos_banco(dni: str = "12345678") -> dict:
    """
    Carga todos los datos del cliente desde PostgreSQL.

    Ejecuta tres consultas y devuelve un diccionario con el mismo
    formato que tenía el JSON original. El resto del código no sabe
    si los datos vienen de un JSON, una DB o una API.
    """
    conn = get_conn()
    cur = conn.cursor()

    # Consulta 1 — datos del cliente
    cur.execute("""
        SELECT nombre, dni, saldo, productos
        FROM clientes
        WHERE dni = %s
    """, (dni,))
    cliente = dict(cur.fetchone())

    # Consulta 2 — contactos habilitados para transferencias
    cur.execute("""
        SELECT nombre, cbu, alias
        FROM contactos
        WHERE dni_cliente = %s
        ORDER BY nombre
    """, (dni,))
    contactos = [dict(row) for row in cur.fetchall()]

    # Consulta 3 — últimos movimientos (más recientes primero, luego invertimos)
    cur.execute("""
        SELECT fecha::text, descripcion, monto
        FROM movimientos
        WHERE dni_cliente = %s
        ORDER BY fecha DESC, id DESC
        LIMIT 10
    """, (dni,))
    movimientos = [dict(row) for row in cur.fetchall()]
    movimientos.reverse()

    cur.close()
    conn.close()

    return {
        "cliente": cliente,
        "contactos": contactos,
        "movimientos": movimientos
    }


def actualizar_saldo(dni: str, nuevo_saldo: float):
    """
    Actualiza el saldo del cliente en PostgreSQL.
    Solo toca el campo que cambió — no reescribe nada más.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clientes
        SET saldo = %s
        WHERE dni = %s
    """, (nuevo_saldo, dni))

    conn.commit()
    cur.close()
    conn.close()


def insertar_movimiento(dni: str, descripcion: str, monto: float):
    """
    Inserta un nuevo movimiento en PostgreSQL.
    CURRENT_DATE es una función de PostgreSQL que devuelve la fecha de hoy.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO movimientos (dni_cliente, fecha, descripcion, monto)
        VALUES (%s, CURRENT_DATE, %s, %s)
    """, (dni, descripcion, monto))

    conn.commit()
    cur.close()
    conn.close()