# ==============================================================================
# CHATBOT/UTILS — Funciones auxiliares sin estado
# ==============================================================================
#
# Estas funciones no saben nada de la DB ni del grafo.
# Solo hacen una cosa y la hacen bien.
# Se pueden testear de forma independiente sin levantar nada más.
# ==============================================================================

import re
import unicodedata


def normalizar(texto: str) -> str:
    """
    Normaliza texto para comparación sin importar mayúsculas ni acentos.
    'María', 'maria', 'MARIA' y 'maría' devuelven el mismo resultado.
    """
    return unicodedata.normalize('NFD', texto.lower()).encode('ascii', 'ignore').decode()


def detectar_intencion_transferencia(mensaje: str) -> bool:
    """
    Detecta si el usuario quiere hacer una transferencia.
    Es el único lugar donde el código interpreta lenguaje natural de forma
    flexible. El resto del flujo de transferencia es determinista.
    """
    palabras_clave = [
        "transferi", "transferí", "transferir", "transferencia",
        "mandar", "enviar", "pasar plata", "pasar dinero",
        "quiero mandar", "quiero enviar", "hacer una transfer",
        "quiero hacer", "necesito enviar", "necesito mandar"
    ]
    return any(p in mensaje.lower() for p in palabras_clave)


def buscar_contacto(mensaje: str, contactos: list) -> dict | None:
    """
    Busca si el mensaje menciona algún contacto habilitado.
    Búsqueda por nombre normalizado — no usa LLM.
    """
    mensaje_norm = normalizar(mensaje)
    for contacto in contactos:
        nombre_completo = normalizar(contacto["nombre"])
        primer_nombre = nombre_completo.split()[0]
        if primer_nombre in mensaje_norm or nombre_completo in mensaje_norm:
            return contacto
    return None


def extraer_monto(mensaje: str) -> float | None:
    """
    Extrae un número del mensaje del usuario con regex.
    No usa LLM — en operaciones financieras el monto tiene que ser exacto.
    """
    numeros = re.findall(r'\d+(?:[.,]\d+)*', mensaje)
    if numeros:
        monto_str = numeros[0].replace(".", "").replace(",", "")
        return float(monto_str)
    return None


def detectar_duplicado(movimientos: list, destinatario: str, monto: float) -> bool:
    """
    Detecta si ya existe una transferencia similar en el historial.
    En producción consultaría la DB con una ventana temporal (últimas 24hs).
    """
    dest_norm = normalizar(destinatario.split()[0])
    for mov in movimientos:
        if (dest_norm in normalizar(mov["descripcion"])
                and abs(float(mov["monto"])) == monto):
            return True
    return False