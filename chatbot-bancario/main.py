# ==============================================================================
# MAIN — Punto de entrada del chatbot
# ==============================================================================
#
# Este archivo solo hace una cosa: mantener el loop de conversación.
# No tiene lógica de negocio, ni SQL, ni prompts.
# Solo orquesta: lee input → llama al grafo → muestra respuesta.
#
# Si querés agregar un canal nuevo (WhatsApp, Telegram, web),
# solo reemplazás el input() por la API correspondiente.
# El resto del sistema no cambia nada.
#
# PARA CORRERLO:
#   python main.py
# ==============================================================================

from langchain_core.messages import HumanMessage

from database.queries import cargar_datos_banco
from chatbot.graph import construir_grafo
from logs.session_logger import guardar_log_sesion


if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("CHATBOT BANCARIO — Simulador (Neon PostgreSQL)")
    print("=" * 60)

    # Cargamos los datos del cliente desde PostgreSQL
    # En producción el DNI vendría del sistema de autenticación
    print("\nConectando a la base de datos...")
    datos = cargar_datos_banco()
    saldo_inicial = float(datos["cliente"]["saldo"])
    print(f"   ✓ Bienvenido, {datos['cliente']['nombre']}")
    print(f"   ✓ Saldo actual: ${saldo_inicial:,.2f}\n")

    print("Escribí tu consulta. Escribí 'salir' para terminar.")
    print("-" * 60 + "\n")

    # Estado inicial — el historial empieza vacío
    estado = {
        "messages": [],
        "datos_cliente": datos,
        "esperando": "",
        "transferencia": {},
        "operacion_registrar": {},
    }

    operaciones_sesion = []  # log de auditoría
    agente = construir_grafo()

    # Loop de conversación — cada iteración es un turno
    # El grafo ejecuta un turno y termina. Acá lo volvemos a llamar.
    while True:
        entrada = input("Vos: ").strip()

        if not entrada:
            continue

        if entrada.lower() == "salir":
            print("\nHasta luego. ¡Que tengas un buen día!")
            print("\nGuardando sesión...")
            guardar_log_sesion(
                estado["messages"],
                saldo_inicial,
                estado["datos_cliente"],
                operaciones_sesion
            )
            break

        # Agregamos el mensaje del usuario — add_messages lo suma al historial
        estado["messages"].append(HumanMessage(content=entrada))

        # Ejecutamos un turno del grafo
        estado = agente.invoke(estado)

        # Si el nodo ejecutó una operación, la registramos en el log de auditoría
        if estado.get("operacion_registrar"):
            operaciones_sesion.append(estado["operacion_registrar"])
            estado["operacion_registrar"] = {}

        # Mostramos la respuesta
        ultima_respuesta = estado["messages"][-1].content
        print(f"\nBot: {ultima_respuesta}\n")