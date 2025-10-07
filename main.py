# main.py
from core.manager import Manager

def display_main_menu():
    """Stampa il menu principale delle operazioni."""
    print("\n╔═════════════════════════════════╗")
    print("║          PiChainAnalysis        ║")
    print("╚═════════════════════════════════╝")
    print("Cosa vuoi fare?")
    print("  1. Archivia transazione singola")
    print("  2. Esci")

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

def main():
    print("Avvio di PiChainAnalysis...")
    app_manager = Manager()

    while True:
        display_main_menu()
        try:
            choice = int(input("Scegli un'azione -> "))
            if choice == 1:
                handle_storage(app_manager)
            elif choice == 2:
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