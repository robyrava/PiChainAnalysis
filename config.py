import os
from dotenv import load_dotenv

# Carica le variabili dal file .env che si trova nella root del progetto
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print("Attenzione: file .env non trovato. Assicurati che esista nella root del progetto.")

# --- Credenziali per il Database Neo4j ---
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")
NEO4J_AUTH = (NEO4J_USER, NEO4J_PASS)

# --- Credenziali per il nodo Bitcoin Core (RPC) ---
RPC_USER = os.getenv("RPC_USER")
RPC_PASS = os.getenv("RPC_PASS")
RPC_HOST = os.getenv("RPC_HOST")
RPC_PORT = os.getenv("RPC_PORT")
RPC_URL = f"http://{RPC_USER}:{RPC_PASS}@{RPC_HOST}:{RPC_PORT}"

# --- Configurazione per Electrs ---
ELECTRS_HOST = os.getenv("ELECTRS_HOST")
ELECTRS_PORT = os.getenv("ELECTRS_PORT", "50002")
ELECTRS_PROTOCOL = "s" # SSL
ELECTRS_TIMEOUT = int(os.getenv("ELECTRS_TIMEOUT", 20))