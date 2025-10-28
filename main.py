from core.manager import Manager
import json

def display_main_menu():
    """Stampa il menu principale delle operazioni."""
    print("\n╔═════════════════════════════════╗")
    print("║          PiChainAnalysis        ║")
    print("╚═════════════════════════════════╝")
    print("Cosa vuoi fare?")
    print("  1. Archivia transazione singola")
    print("  2. Traccia percorso Transazione")
    print("  3. Elimina dati dal database")
    print("  4. Sezione Analisi") # Nuova Opzione
    print("  5. Esci") # Scalato a 5

def display_delete_menu():
    """Stampa il sottomenu per le operazioni di cancellazione."""
    print("\n--- Menu Eliminazione ---")
    print("  1. Elimina solo una transazione")
    print("  2. Elimina una transazione e i suoi UTXO")
    print("  3. Elimina un singolo UTXO")
    print("  4. Torna al menu principale")

def display_analysis_menu():
    """Stampa il sottomenu per le operazioni di analisi."""
    print("\n--- Menu Analisi ---")
    print("  1. Analisi Peeling Chain")
    print("  2. Torna al menu principale") 

def handle_analysis_menu(manager: Manager):
    """Gestisce la logica per le varie operazioni di analisi."""
    while True:
        display_analysis_menu()
        try:
            choice = int(input("Scegli un'azione -> "))
            if choice == 1:
                start_hash = input("Inserisci l'hash della transazione da cui iniziare l'analisi Peeling Chain:\n--> ").strip()
                if start_hash:
                    results = manager.start_peeling_chain_analysis(start_hash)
                    # Stampa risultati grezzi 
                    print("\n--- Risultati Analisi Peeling Chain ---")
                    print(json.dumps(results, indent=2))
                    print("--------------------------------------")
                else:
                    print("Errore: L'hash non può essere vuoto.")
            elif choice == 2: # Torna indietro
                break
            else:
                print("Scelta non valida. Riprova.")
        except ValueError:
            print("Input non valido. Per favore, inserisci un numero.")
        except Exception as e:
            print(f"Si è verificato un errore inaspettato durante l'analisi: {e}")
            import traceback
            traceback.print_exc()


def handle_storage(manager: Manager):
    """Gestisce la logica per archiviare una o più transazioni."""
    try:
        hashes_input = input("Inserisci l'hash della transazione (o più hash separati da virgola):\n--> ")
        hash_list = [h.strip() for h in hashes_input.split(',')]
        for tx_hash in hash_list:
            if tx_hash:
                manager.store_transaction_by_hash(tx_hash)
    except Exception as e:
        print(f"Si è verificato un errore inaspettato: {e}")

def handle_tracing(manager: Manager):
    """Gestisce la logica per il tracciamento automatico di un percorso."""
    try:
        start_hash = input("Inserisci l'hash della transazione di partenza:\n--> ").strip()
        if not start_hash:
            print("Errore: L'hash non può essere vuoto.")
            return
        
        max_steps_str = input("Inserisci il numero massimo di passi (lascia vuoto per tracciare fino alla fine):\n--> ").strip()
        
        max_steps = None
        if max_steps_str:
            max_steps = int(max_steps_str)
            if max_steps <= 0:
                print("Errore: Il numero di passi deve essere un numero positivo.")
                return
        
        manager.trace_transaction_path(start_hash, max_steps)

    except Exception as e:
        print(f"Si è verificato un errore inaspettato: {e}")

def handle_deletion(manager: Manager):
    """Gestisce la logica per le varie operazioni di cancellazione."""
    while True:
        display_delete_menu()
        try:
            choice = int(input("Scegli un'azione -> "))
            if choice == 1:
                tx_hash = input("Inserisci l'hash della transazione da eliminare: ")
                manager.delete_transaction(tx_hash.strip())
            elif choice == 2:
                tx_hash = input("Inserisci l'hash della transazione da eliminare completamente: ")
                manager.delete_transaction_and_utxos(tx_hash.strip())
            elif choice == 3:
                utxo_id = input("Inserisci l'ID dell'UTXO da eliminare (formato: hash:index): ")
                manager.delete_utxo(utxo_id.strip())
            elif choice == 4:
                break
            else:
                print("Scelta non valida. Riprova.")
        except ValueError:
            print("Input non valido. Per favore, inserisci un numero.")
        except Exception as e:
            print(f"Si è verificato un errore inaspettato: {e}")

def main():
    """Punto di ingresso principale dell'applicazione."""
    print("Avvio di PiChainAnalysis...")
    app_manager = Manager()

    while True:
        display_main_menu()
        try:
            choice = int(input("Scegli un'azione -> "))
            if choice == 1:
                handle_storage(app_manager)
            elif choice == 2:
                handle_tracing(app_manager)
            elif choice == 3:
                handle_deletion(app_manager)
            elif choice == 4:
                handle_analysis_menu(app_manager)
            elif choice == 5:
                break
            else:
                print("Scelta non valida. Riprova.")
        except ValueError:
            print("Input non valido. Per favore, inserisci un numero.")
        except KeyboardInterrupt:
            print("\nUscita richiesta dall'utente.")
            break

    app_manager.shutdown()

if __name__ == "__main__":
    main()