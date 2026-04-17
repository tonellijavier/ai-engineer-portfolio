# ==============================================================================
# TEST DE CONEXIÓN CON GMAIL
# ==============================================================================
#
# Corre este archivo PRIMERO para verificar que la conexión con Gmail funciona.
# La primera vez abre el navegador para que autorices el acceso.
# Después guarda un archivo token.json que usa el agente principal.
#
# PARA CORRERLO:
#   python test_gmail.py
# ==============================================================================

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText

# Los permisos que necesitamos sobre Gmail
# gmail.compose = crear borradores y enviar mails
SCOPES = ['https://www.googleapis.com/auth/gmail.compose']

def autenticar_gmail():
    """
    Maneja la autenticación con Gmail.
    
    Primera vez: abre el navegador para que autorices el acceso.
    La autorización queda guardada en token.json.
    
    Próximas veces: usa token.json directamente sin abrir el navegador.
    """
    creds = None

    # Si ya existe token.json de una autenticación anterior, lo usamos
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # Si no hay credenciales válidas, iniciamos el flujo de autorización
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Token expirado — lo renovamos automáticamente
            creds.refresh(Request())
        else:
            # Primera vez — abre el navegador para autorizar
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json',  # el archivo que descargaste de Google Cloud
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Guardamos el token para no tener que autorizar de nuevo
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds

def crear_borrador_prueba(service):
    """
    Crea un borrador de prueba en Gmail para verificar que todo funciona.
    """
    # Creamos el mensaje
    mensaje = MIMEText(
        "Este es un borrador de prueba creado por el agente de gastos.\n\n"
        "Si ves este mensaje en tu carpeta de Borradores, "
        "la conexión con Gmail está funcionando correctamente."
    )
    mensaje['to'] = ''           # destinatario vacío — el usuario lo completa
    mensaje['subject'] = 'Prueba — Agente de Gastos'

    # Codificamos el mensaje en base64 (formato que requiere la API de Gmail)
    raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()

    # Creamos el borrador via la API
    borrador = service.users().drafts().create(
        userId='me',
        body={'message': {'raw': raw}}
    ).execute()

    return borrador['id']

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("TEST DE CONEXIÓN CON GMAIL")
    print("=" * 50)

    print("\n1. Autenticando con Gmail...")
    print("   (se va a abrir el navegador para autorizar el acceso)\n")

    creds = autenticar_gmail()
    service = build('gmail', 'v1', credentials=creds)

    print("   ✓ Autenticación exitosa\n")

    print("2. Creando borrador de prueba...")
    borrador_id = crear_borrador_prueba(service)
    print(f"   ✓ Borrador creado (ID: {borrador_id})")
    print("   Buscalo en la carpeta 'Borradores' de tu Gmail\n")

    print("=" * 50)
    print("¡Todo funciona! Podés correr el agente principal.")
    print("=" * 50 + "\n")