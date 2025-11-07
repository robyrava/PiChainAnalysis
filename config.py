import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print("Attenzione: file .env non trovato. Assicurati che esista nella root del progetto.")

# Esponi le variabili di configurazione
RPC_USER = os.getenv("RPC_USER")
RPC_PASS = os.getenv("RPC_PASS")
RPC_HOST = os.getenv("RPC_HOST")
RPC_PORT = os.getenv("RPC_PORT")
RPC_URL = f"http://{RPC_USER}:{RPC_PASS}@{RPC_HOST}:{RPC_PORT}"

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")
NEO4J_AUTH = (NEO4J_USER, NEO4J_PASS)

# Configurazione per Electrs
ELECTRS_HOST = os.getenv("ELECTRS_HOST")
ELECTRS_PORT = os.getenv("ELECTRS_PORT", "50002")
ELECTRS_PROTOCOL = "s"
ELECTRS_PORT_STRING = f"{ELECTRS_PROTOCOL}{ELECTRS_PORT}"
ELECTRS_TIMEOUT = int(os.getenv("ELECTRS_TIMEOUT", 30))