# PiChainAnalysis

**PiChainAnalysis** è uno strumento avanzato di analisi per la blockchain di Bitcoin, progettato per connettersi a un nodo Bitcoin Core personale (in esecuzione, ad esempio, su un Raspberry Pi) e archiviare i dati analizzati in un database a grafo Neo4j.

Questo progetto è nato con l'obiettivo di creare uno strumento di chain analysis indipendente, privato e che non faccia affidamento su API di terze parti. Include tuttavia un sistema di fallback intelligente che permette di utilizzare API pubbliche quando necessario, mantenendo sempre la privacy come priorità.

---

## 🌟 Caratteristiche Principali

- **🔒 Privacy-First**: Priorità assoluta al nodo locale per mantenere la privacy
- **🔄 Fallback Intelligente**: Sistema di backup con API pubbliche (mempool.space) con consenso dell'utente
- **📊 Analisi Automatica**: Tracciamento automatico del flusso di denaro attraverso le transazioni
- **� Statistiche Avanzate**: Analisi approfondite con metriche di Gini, entropia, rilevamento anomalie
- **🎨 Visualizzazioni Interattive**: Grafi dinamici, dashboard complete e report dettagliati
- **�🗃️ Archiviazione Strutturata**: Salvataggio dei dati in formato grafo per analisi avanzate
- **⚡ Connessioni Multiple**: Supporto per Bitcoin Core RPC, Electrs e API pubbliche
- **🎯 Ricerca UTXO**: Individuazione automatica di output non spesi
- **🧹 Gestione Dati**: Strumenti completi per eliminare e gestire i dati archiviati

---

## 🎯 Nuove Funzionalità di Analisi

### Analisi Statistiche Avanzate
- **Coefficiente di Gini**: Misura la concentrazione nella distribuzione dei valori
- **Entropia dei Pattern**: Quantifica la diversità nei comportamenti di peeling
- **Rilevamento Anomalie**: Identificazione automatica di transazioni irregolari
- **Analisi Clustering**: Raggruppamento di transazioni con comportamenti simili
- **Score di Consistenza**: Valutazione della regolarità dei pattern

### Visualizzazioni Multiple
- **Grafo Interattivo**: Visualizzazione delle transazioni come rete di nodi connessi
- **Dashboard Completa**: 4 grafici integrati per analisi multi-dimensionale
- **Report Statistiche**: Output formattato con tutte le metriche avanzate
- **Timeline dei Valori**: Andamento temporale dei flussi Bitcoin

---

## 🚀 Architettura del Software

Il software è suddiviso in tre strati logici principali per garantire modularità e manutenibilità:

### 1. **Strato di Accesso ai Dati (`/connectors`)**
Contiene i moduli responsabili della comunicazione con servizi esterni:

- **`bitcoin_connector.py`**: Gestisce tutte le chiamate RPC al nodo Bitcoin Core
- **`neo4j_connector.py`**: Gestisce la connessione e l'esecuzione di query sul database Neo4j
- **`electrs_connector.py`**: Interfaccia con il server Electrs per la ricerca di spending transactions
- **`public_api_connector.py`**: Connettore di fallback per l'API pubblica di mempool.space

### 2. **Strato Logico (`/core`)**
È il cuore dell'applicazione, dove i dati vengono elaborati:

- **`data_parser.py`**: Traduce i dati grezzi ricevuti dal nodo Bitcoin in un formato strutturato
- **`manager.py`**: Orchestra le operazioni, coordinando i connettori e il parser con logica di fallback intelligente
- **`query.py`**: Contiene tutte le query Cypher per Neo4j

### 3. **Strato di Analisi (`/analysis`)**
Moduli specializzati per analisi avanzate e visualizzazioni:

- **`peeling_chain_analyzer.py`**: Analisi statistiche avanzate delle peeling chain
- **`visualizer.py`**: Generazione di grafici interattivi e dashboard

### 4. **Strato di Presentazione (`main.py`)**
L'entry-point dell'applicazione che fornisce un'interfaccia a riga di comando (CLI) intuitiva.

---

## 📋 Prerequisiti

- **Python 3.8 o superiore**
- **Un'istanza di Neo4j Database** in esecuzione
- **Un nodo Bitcoin Core** completamente sincronizzato e accessibile in rete
- **Server Electrs** (opzionale, per funzionalità avanzate di ricerca)
- **Connessione Internet** (per il fallback alle API pubbliche)

---

## ⚙️ Guida all'Installazione

### 1. **Clonare il repository:**
```bash
git clone <URL_DEL_TUO_REPOSITORY>
cd PiChainAnalysis
```

### 2. **Creare un ambiente virtuale:**
```bash
python -m venv venv
source venv/bin/activate  # Su Windows: venv\Scripts\activate
```

### 3. **Installare le dipendenze:**
```bash
pip install -r requirements.txt
```

### 4. **Configurare le credenziali:**
Crea un file `.env` nella root del progetto con le seguenti configurazioni:

```env
# --- Credenziali per il Database Neo4j ---
NEO4J_URI="neo4j://127.0.0.1:7687"
NEO4J_USER="neo4j"
NEO4J_PASS="la_tua_password"

# --- Credenziali per il nodo Bitcoin Core (RPC) ---
RPC_USER="il_tuo_utente_rpc"
RPC_PASS="la_tua_password_rpc"
RPC_HOST="192.168.1.XX"  # IP del tuo nodo
RPC_PORT="8332"

# --- Configurazione Electrs (opzionale) ---
ELECTRS_HOST="192.168.1.XX"  # IP del server Electrs
ELECTRS_PORT="50002"
ELECTRS_PROTOCOL="s"  # SSL
ELECTRS_TIMEOUT="20"
```

---

## ▶️ Avvio dell'Applicazione

Una volta completata l'installazione, avvia l'applicazione eseguendo:

```bash
python main.py
```

---

## 🎮 Funzionalità Disponibili

### 📝 **1. Archivia Transazione Singola**
- Recupera e analizza una specifica transazione Bitcoin
- Supporta input multipli (separati da virgola)
- Parsing automatico di input, output e metadati
- Gestione delle transazioni coinbase
- Archiviazione strutturata in Neo4j

### 🔍 **2. Traccia Percorso Transazione**
- **Tracciamento automatico** del flusso di denaro
- Segue sempre l'**output con valore più alto**
- Supporta **limiti personalizzabili** sul numero di passi
- **Individuazione automatica** di UTXO non spesi
- **Reportistica dettagliata** del percorso seguito

**Esempio di utilizzo:**
```
Hash di partenza: abc123...
Numero massimo di passi: 10 (opzionale)

Risultato:
Passo 1: abc123... → def456...
Passo 2: def456... → ghi789...
...
Raggiunto UTXO non speso: ghi789...:0 (0.5 BTC)
```

### 🗑️ **3. Gestione Dati**
Strumenti completi per la pulizia e manutenzione del database:

- **Elimina transazione singola**: Rimuove solo il nodo transazione
- **Eliminazione completa**: Rimuove transazione e tutti gli UTXO correlati
- **Elimina UTXO specifico**: Rimozione mirata di singoli output

### 🔄 **4. Sistema di Fallback Intelligente**

#### **Strategia Privacy-First:**
1. **Tentativo primario**: Sempre il nodo Bitcoin locale
2. **Richiesta consenso**: L'utente decide se usare API pubbliche
3. **Fallback temporaneo**: Dopo 5 operazioni con API pubblica, ritenta il nodo locale
4. **Feedback continuo**: Notifiche chiare sulla modalità in uso

#### **Vantaggi del Sistema:**
- ✅ **Massima privacy** quando il nodo locale funziona
- ✅ **Continuità operativa** anche con problemi di rete locale
- ✅ **Controllo utente** sulla decisione di usare servizi esterni
- ✅ **Recupero automatico** al nodo locale quando possibile

---

## 🛠️ Gestione degli Errori

Il software gestisce automaticamente diversi scenari problematici:

### **Nodo Bitcoin Non Disponibile:**
- Richiesta di consenso per API pubbliche
- Possibilità di interrompere l'operazione
- Tentativi automatici di riconnessione

### **Server Electrs Offline:**
- Fallback automatico alle API pubbliche (con consenso)
- Continuità nella ricerca di spending transactions

### **Problemi di Rete:**
- Timeout configurabili
- Retry automatici
- Messaggi di errore informativi

### **Transazioni Mancanti:**
- Gestione di nodi in modalità "pruned"
- Suggerimenti per la risoluzione (reindex, etc.)
- Interruzione controllata delle operazioni

---

## 📊 Struttura Dati Neo4j

Il software crea una struttura grafo ottimizzata per l'analisi:

### **Nodi:**
- **Transaction**: Contiene metadati della transazione (TXID, timestamp, block info)
- **UTXO**: Rappresenta output di transazioni (valore, indirizzo, stato)

### **Relazioni:**
- **INPUT**: Collega UTXO spesi alle transazioni che li consumano
- **OUTPUT**: Collega transazioni agli UTXO che creano

### **Proprietà Principali:**
```cypher
// Nodo Transaction
{
  TXID: "abc123...",
  time: "2024-01-01T12:00:00Z",
  block_height: 820000,
  input_value: 1.5,
  output_value: 1.499
}

// Nodo UTXO
{
  TXID: "abc123...:0",
  wallet_address: "bc1q...",
  value: 0.5,
  is_spent: false
}


## 📄 Licenza

[Inserire informazioni sulla licenza]


**Note sulla Privacy**: PiChainAnalysis è progettato per massimizzare la privacy utilizzando principalmente il tuo nodo locale. L'uso di API pubbliche avviene solo con il tuo consenso esplicito e in situazioni di necessità.