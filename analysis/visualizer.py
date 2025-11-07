import matplotlib.pyplot as plt
import networkx as nx
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
from typing import Dict, Any, List
import webbrowser
import os

def plot_peeling_chain_analysis(results: Dict[str, Any]):
    """
    Genera e salva un grafico a barre dell'analisi della peeling chain.

    Args:
        results: Il dizionario contenente i risultati dell'analisi.
    """
    chain_data = results.get('chain', [])
    if not chain_data:
        print("Nessun dato della catena disponibile per la visualizzazione.")
        return

    # Preparo i dati per il grafico
    steps = [f"Passo {i+1}" for i in range(len(chain_data))]
    percentages = [tx['peeled_percentage'] for tx in chain_data]
    total_peeled = results.get('total_peeled_value', 0.0)
    total_processed = results.get('total_value_processed', 0.0)
    
    # Calcolo i Bitcoin iniziali e finali
    bitcoin_iniziali = chain_data[0]['input_value'] if chain_data else 0.0
    bitcoin_finali = chain_data[-1]['change_value'] if chain_data else 0.0

    # Creo il grafico
    plt.style.use('seaborn-v0_8-darkgrid') # Imposto lo stile del grafico
    fig, ax = plt.subplots(figsize=(12, 7))

    # Disegno le barre
    bars = ax.bar(steps, percentages, color='skyblue', edgecolor='black')

    # Aggiungo etichette e titoli
    ax.set_ylabel('Percentuale Pelata (%)')
    ax.set_title('Analisi della Consistenza della Peeling Chain')
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels(steps, rotation=45, ha="right")
    
    # Aggiungo una legenda con informazioni sui Bitcoin
    legend_text = f'Valore Totale Riciclato: {total_peeled:.8f} BTC\nValore Totale Processato: {total_processed:.8f} BTC\nBitcoin Iniziali: {bitcoin_iniziali:.8f} BTC\nBitcoin Finali: {bitcoin_finali:.8f} BTC'
    ax.text(0.02, 0.98, legend_text, transform=ax.transAxes, fontsize=10, 
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))
    
    # Aggiungo il valore sopra ogni barra
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, yval, f'{yval:.2f}%', va='bottom', ha='center')

    # Ottimizzo il layout e salvo il file
    plt.tight_layout()
    
    try:
        # Creo la cartella plot se non esiste
        plot_dir = 'plot'
        if not os.path.exists(plot_dir):
            os.makedirs(plot_dir)
        
        filename = os.path.join(plot_dir, 'peeling_chain_report.png')
        plt.savefig(filename)
        print(f"\nGrafico salvato con successo come: {filename}")
    except Exception as e:
        print(f"\nErrore durante il salvataggio del grafico: {e}")


def create_peeling_chain_graph(results: Dict[str, Any], save_html: bool = True) -> None:
    """
    Crea una visualizzazione interattiva a grafo della peeling chain.
    
    Args:
        results: Il dizionario contenente i risultati dell'analisi.
        save_html: Se True, salva il grafico come file HTML interattivo.
    """
    chain_data = results.get('chain', [])
    if not chain_data:
        print("Nessun dato della catena disponibile per la visualizzazione del grafo.")
        return

    # Costruisco il grafo diretto con NetworkX
    G = nx.DiGraph()

    # Inserisco i nodi e collego gli archi sequenziali
    for index, tx in enumerate(chain_data):
        node_id = f"TX_{index}"
        G.add_node(
            node_id,
            tx_hash=tx['tx_hash'][:16] + "...",
            value=tx.get('peeled_value', 0.0),
            percentage=tx.get('peeled_percentage', 0.0),
            input_value=tx.get('input_value', 0.0)
        )

        if index < len(chain_data) - 1:
            G.add_edge(
                node_id,
                f"TX_{index+1}",
                value=tx.get('change_value', 0.0)
            )

    # Calcolo le coordinate dei nodi con un layout primaverile
    pos = nx.spring_layout(G, k=3, iterations=50)

    # Raccolgo le coordinate e le etichette per gli archi
    edge_x, edge_y, edge_text = [], [], []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        flow_value = G.edges[edge].get('value', 0.0)
        edge_text.append(f"Flusso: {flow_value:.8f} BTC")

    # Estraggo le informazioni sui nodi da passare a Plotly
    node_x, node_y = [], []
    node_text, node_sizes, node_percentages = [], [], []

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

        info = G.nodes[node]
        node_percentages.append(info.get('percentage', 0.0))
        node_value = info.get('value', 0.0)
        node_sizes.append(max(15, min(65, 20 + node_value * 900)))

        node_text.append(
            f"Hash: {info['tx_hash']}<br>"
            f"Valore Pelato: {node_value:.8f} BTC<br>"
            f"Percentuale: {info.get('percentage', 0.0):.2f}%<br>"
            f"Input Totale: {info.get('input_value', 0.0):.8f} BTC"
        )

    # Genero la figura Plotly
    fig = go.Figure()

    # Disegno gli archi direzionali
    fig.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode='lines',
            line=dict(color='#888', width=2),
            hoverinfo='text',
            text=edge_text,
            name='Flussi'
        )
    )

    # Disegno i nodi dimensionati e colorati
    fig.add_trace(
        go.Scatter(
            x=node_x,
            y=node_y,
            mode='markers',
            hoverinfo='text',
            text=node_text,
            marker=dict(
                size=node_sizes,
                color=node_percentages,
                colorscale='Oranges',
                colorbar=dict(title="Percentuale Pelata (%)"),
                line=dict(width=2, color='darkred'),
                showscale=True
            ),
            name='Transazioni'
        )
    )

    # Imposto il layout complessivo del grafo
    fig.update_layout(
        title=dict(
            text="Grafo Interattivo della Peeling Chain",
            x=0.5,
            font=dict(size=20)
        ),
        showlegend=False,
        hovermode='closest',
        margin=dict(b=20, l=5, r=5, t=40),
        annotations=[
            dict(
                text="Dimensione del nodo = Valore pelato | Colore = Percentuale pelata",
                showarrow=False,
                xref='paper',
                yref='paper',
                x=0.005,
                y=-0.002,
                xanchor='left',
                yanchor='bottom'
            )
        ],
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor='white'
    )

    if save_html:
        filename = 'peeling_chain_graph.html'
        fig.write_html(filename)
        print(f"\nGrafo interattivo salvato come: {filename}")

        try:
            webbrowser.open(f'file://{os.path.abspath(filename)}')
        except Exception:
            pass
    else:
        fig.show()


def create_comprehensive_dashboard(results: Dict[str, Any]) -> None:
    """
    Genera statistiche e grafici di sintesi.
    
    Args:
        results: Il dizionario contenente i risultati dell'analisi.
    """
    chain_data = results.get('chain', [])
    if not chain_data:
        return

    # Estraggo i dati principali della catena
    steps = list(range(1, len(chain_data) + 1))
    percentages = [tx.get('peeled_percentage', 0.0) for tx in chain_data]
    values = [tx.get('peeled_value', 0.0) for tx in chain_data]
    input_values = [tx.get('input_value', 0.0) for tx in chain_data]

    # Imposto la struttura dei subplot
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            'Percentuali Pelate per Transazione',
            'Distribuzione delle Percentuali',
            'Valori delle Transazioni nel Tempo',
            'Efficienza del Peeling'
        ),
        specs=[[{"secondary_y": False}, {"secondary_y": False}],
               [{"secondary_y": True}, {"secondary_y": False}]]
    )

    fig.add_trace(
        go.Scatter(
            x=steps,
            y=percentages,
            mode='lines+markers',
            name='% Pelata',
            line=dict(color='red', width=3)
        ),
        row=1,
        col=1
    )

    # Inserisco la media come riferimento visivo
    avg_percentage = results.get('average_peeled_percentage', 0.0)
    fig.add_hline(
        y=avg_percentage,
        line_dash='dash',
        line_color='blue',
        annotation_text=f"Media: {avg_percentage:.2f}%",
        row=1,
        col=1
    )

    # Mostro la distribuzione delle percentuali pelate
    fig.add_trace(
        go.Histogram(
            x=percentages,
            nbinsx=10,
            name='Distribuzione %',
            marker_color='indianred',
            opacity=0.75
        ),
        row=1,
        col=2
    )

    # Confronto valore pelato e input usando l'asse secondario
    fig.add_trace(
        go.Scatter(
            x=steps,
            y=values,
            mode='lines+markers',
            name='Valore Pelato',
            line=dict(color='green')
        ),
        row=2,
        col=1
    )

    fig.add_trace(
        go.Scatter(
            x=steps,
            y=input_values,
            mode='lines+markers',
            name='Valore Input',
            line=dict(color='blue')
        ),
        row=2,
        col=1,
        secondary_y=True
    )

    # Calcolo l'efficienza come rapporto pelato/input
    efficiency = [v / i if i > 0 else 0 for v, i in zip(values, input_values)]
    fig.add_trace(
        go.Bar(
            x=steps,
            y=efficiency,
            name='Efficienza',
            marker_color='orange',
            opacity=0.8
        ),
        row=2,
        col=2
    )

    # Aggiorno layout e assi per migliore leggibilità
    fig.update_layout(
        title_text="Dashboard Analisi Peeling Chain",
        title_x=0.5,
        height=800,
        showlegend=True,
        bargap=0.2
    )

    fig.update_xaxes(title_text="Passo nella Catena", row=1, col=1)
    fig.update_yaxes(title_text="Percentuale Pelata (%)", row=1, col=1)

    fig.update_xaxes(title_text="Percentuale Pelata (%)", row=1, col=2)
    fig.update_yaxes(title_text="Frequenza", row=1, col=2)

    fig.update_xaxes(title_text="Passo nella Catena", row=2, col=1)
    fig.update_yaxes(title_text="Valore Pelato (BTC)", row=2, col=1)
    fig.update_yaxes(title_text="Valore Input (BTC)", row=2, col=1, secondary_y=True)

    fig.update_xaxes(title_text="Passo nella Catena", row=2, col=2)
    fig.update_yaxes(title_text="Efficienza (Pelato/Input)", row=2, col=2)

    # Salvo la dashboard e provo ad aprirla
    filename = 'peeling_chain_dashboard.html'
    fig.write_html(filename)
    print(f"\nDashboard completa salvata come: {filename}")

    try:
        webbrowser.open(f'file://{os.path.abspath(filename)}')
    except Exception:
        pass


def create_statistics_report(results: Dict[str, Any]) -> None:
    """
    Crea un report testuale dettagliato delle statistiche avanzate.
    
    Args:
        results: Il dizionario contenente i risultati dell'analisi.
    """
    print("\n" + "="*60)
    print("           REPORT STATISTICHE")
    print("="*60)
    
    # Metto in evidenza le statistiche principali
    print(f"\nMETRICHEE:")
    print(f"   • Lunghezza Catena: {results.get('chain_length', 0)} transazioni")
    print(f"   • Valore Totale Pelato: {results.get('total_peeled_value', 0):.8f} BTC")
    print(f"   • Valore Totale Processato: {results.get('total_value_processed', 0):.8f} BTC")
    
    print(f"\nSTATISTICHE PERCENTUALI:")
    print(f"   • Media: {results.get('average_peeled_percentage', 0):.2f}%")
    print(f"   • Min: {results.get('min_peeled_percentage', 0):.2f}%")
    print(f"   • Max: {results.get('max_peeled_percentage', 0):.2f}%")
    
    # Approfondisco le anomalie
    advanced = results.get('advanced_analytics', {})
    if advanced:
        anomalies = advanced.get('anomaly_detection', {})
        if anomalies and anomalies.get('anomaly_count', 0) > 0:
            print(f"\nDEVIAZIONE PEELING CHAIN:")
            print(f"   • Anomalie Rilevate: {anomalies.get('anomaly_count', 0)}")
            
            # Mostro i TXID delle transazioni anomale invece delle posizioni
            anomaly_positions = anomalies.get('anomalies', [])
            chain_data = results.get('chain', [])
            if anomaly_positions and chain_data:
                anomaly_txids = []
                for pos in anomaly_positions:
                    if pos < len(chain_data):
                        tx_hash = chain_data[pos]['tx_hash']
                        anomaly_txids.append(tx_hash)  # Riporto il TXID completo
                
                if anomaly_txids:
                    print(f"   • TXID Anomale:")
                    for i, txid in enumerate(anomaly_txids, 1):
                        print(f"     {i}. {txid}")
    
    print("\n" + "="*60)

import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, Any
import os

def create_fan_in_visualizations(results: Dict[str, Any]) -> None:
    """
    Crea tutte le visualizzazioni per l'analisi Fan-In usando matplotlib.
    
    Args:
        results: Dizionario con i risultati dell'analisi
    """
    if not results:
        print("Nessun dato disponibile per la visualizzazione")
        return
    
    # Creo la cartella plot se non esiste
    plot_dir = 'plot'
    if not os.path.exists(plot_dir):
        os.makedirs(plot_dir)
    
    # Avvio la generazione di tutti i grafici
    create_fund_flow_donut(results)
    create_input_age_histogram(results)
    create_input_hourly_distribution(results)


def create_fund_flow_donut(results: Dict[str, Any]) -> None:
    """
    Crea un grafico completo del flusso di fondi Fan-In con metriche dettagliate.
    Mostra: UTXO in entrata/uscita, valori BTC in entrata/uscita, commissione.
    
    Args:
        results: Dizionario con i risultati dell'analisi
    """
    # Estraggo i dati
    input_count = results.get('input_count', 0)
    output_count = results.get('output_count', 0)
    total_input_value = results.get('total_input_value', 0)
    total_output_value = results.get('total_output_value', 0)
    operation_cost = results.get('operation_cost', 0)
    payment = results.get('payment_output', {})
    change = results.get('change_output', {})
    
    # Verifico la validità dei dati
    if operation_cost < 0:
        print(f"Attenzione: Commissione negativa rilevata ({operation_cost:.8f} BTC)")
        print("I dati potrebbero essere inconsistenti. Verifica i valori di input/output.")
        print("Procedendo comunque con il valore assoluto per la visualizzazione.\n")
        operation_cost_display = abs(operation_cost)
    else:
        operation_cost_display = operation_cost
    
    # Creo una figura con 2 subplot: uno per i valori BTC, uno per gli UTXO
    plt.style.use('seaborn-v0_8-darkgrid')
    fig = plt.figure(figsize=(16, 8))
    
    # === Imposto il GRAFICO 1: Flusso di Valori BTC ===
    ax1 = plt.subplot(1, 2, 1)
    
    # Preparo i dati per il grafico a barre orizzontali
    categories = ['Input\n(Totale)', 'Output\n(Totale)', 'Commissione']
    values = [total_input_value, total_output_value, operation_cost_display]
    colors_bars = ['#3498db', '#2ecc71', '#e74c3c']
    
    # Disegno le barre orizzontali
    bars = ax1.barh(categories, values, color=colors_bars, edgecolor='white', linewidth=2, alpha=0.85)
    
    # Aggiungo i valori sulle barre
    for i, (bar, value) in enumerate(zip(bars, values)):
        width = bar.get_width()
        label_x_pos = width + max(values) * 0.02
        ax1.text(label_x_pos, bar.get_y() + bar.get_height()/2, 
                f'{value:.8f} BTC',
                va='center', ha='left', fontsize=11, weight='bold')
    
    # Applico lo styling
    ax1.set_xlabel('Bitcoin (BTC)', fontsize=12, weight='bold')
    ax1.set_title('Flusso di Valori Bitcoin', fontsize=14, weight='bold', pad=15)
    ax1.grid(axis='x', alpha=0.3, linestyle='--')
    ax1.set_xlim(0, max(values) * 1.2 if max(values) > 0 else 1)
    
    # Aggiungo una nota sulla commissione
    if operation_cost < 0:
        commission_note = f"ATTENZIONE: Commissione negativa - mostrato valore assoluto"
        note_color = 'red'
    else:
        commission_note = f"Commissione: {operation_cost_display:.8f} BTC"
        note_color = 'green'
    
    ax1.text(0.5, -0.15, commission_note, transform=ax1.transAxes,
            ha='center', fontsize=9, style='italic', color=note_color)
    
    # === Imposto il GRAFICO 2: Conteggio UTXO e Breakdown Output ===
    ax2 = plt.subplot(1, 2, 2)
    
    # Preparo i dati per il conteggio degli UTXO
    utxo_labels = ['UTXO\nin Entrata', 'UTXO\nin Uscita']
    utxo_values = [input_count, output_count]
    utxo_colors = ['#3498db', '#2ecc71']
    
    # Disegno le barre
    bars_utxo = ax2.bar(utxo_labels, utxo_values, color=utxo_colors, 
                        edgecolor='white', linewidth=2, alpha=0.85, width=0.6)
    
    # Aggiungo i valori sopra le barre
    for bar, value in zip(bars_utxo, utxo_values):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + max(utxo_values) * 0.02,
                f'{int(value)}',
                ha='center', va='bottom', fontsize=14, weight='bold')
    
    # Applico lo styling
    ax2.set_ylabel('Numero di UTXO', fontsize=12, weight='bold')
    ax2.set_title('Conteggio UTXO', fontsize=14, weight='bold', pad=15)
    ax2.grid(axis='y', alpha=0.3, linestyle='--')
    ax2.set_ylim(0, max(utxo_values) * 1.15 if max(utxo_values) > 0 else 1)
    
    # Inserisco il breakdown degli output come testo
    if payment and change:
        payment_value = payment.get('value', 0)
        change_value = change.get('value', 0)
        
        breakdown_text = (
            f"Breakdown Output:\n"
            f"- Pagamento: {payment_value:.8f} BTC\n"
            f"- Resto: {change_value:.8f} BTC"
        )
        
        ax2.text(0.5, 0.15, breakdown_text, transform=ax2.transAxes,
                fontsize=10, ha='center', va='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5, edgecolor='gray'))
    
    # === Imposto il TITOLO GENERALE ===
    fig.suptitle('Analisi Flusso di Fondi - Transazione Fan-In', 
                 fontsize=16, weight='bold', y=0.98)
    
    # === Inserisco i METADATI IN FONDO ===
    ratio_text = f'Rapporto Consolidamento: {input_count} -> {output_count} UTXO  |  '
    ratio_text += f'Efficienza: {(total_output_value/total_input_value*100):.2f}%' if total_input_value > 0 else 'N/A'
    
    plt.figtext(0.5, 0.02, ratio_text, ha='center', fontsize=10, 
                weight='bold', color='#34495e')
    
    plt.tight_layout(rect=[0, 0.04, 1, 0.96])
    
    # Salvo il file
    try:
        plot_dir = 'plot'
        if not os.path.exists(plot_dir):
            os.makedirs(plot_dir)
        
        filename = os.path.join(plot_dir, 'fan_in_fund_flow.png')
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"\nGrafico flusso fondi salvato come: {filename}")
        plt.close()
    except Exception as e:
        print(f"\nErrore durante il salvataggio del grafico flusso fondi: {e}")
        plt.close()
        raise


def create_input_age_histogram(results: Dict[str, Any]) -> None:
    """
    Crea un istogramma della distribuzione dell'eta degli input usando matplotlib.
    
    Args:
        results: Dizionario con i risultati dell'analisi
    """
    age_distribution = results.get('age_distribution', {})
    
    if not age_distribution or sum(age_distribution.values()) == 0:
        print("Nessun dato sull'eta degli input disponibile")
        return
    
    # Preparo i dati
    categories = list(age_distribution.keys())
    counts = list(age_distribution.values())
    
    # Imposto una scala di colori dal verde (recente) al rosso (vecchio)
    colors = ['#2ecc71', '#f39c12', '#e67e22', '#e74c3c']
    
    # Creo il grafico con matplotlib
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(12, 7))
    
    # Disegno l'istogramma
    bars = ax.bar(categories, counts, color=colors, edgecolor='black', linewidth=1.5)
    
    # Aggiungo i valori sopra le barre
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, height,
                f'{int(height)}',
                ha='center', va='bottom', fontsize=10, weight='bold')
    
    # Imposto etichette e titolo
    ax.set_xlabel('Fascia di Eta', fontsize=12, weight='bold')
    ax.set_ylabel('Numero di Input', fontsize=12, weight='bold')
    ax.set_title('Distribuzione Eta degli Input', fontsize=16, weight='bold', pad=20)
    
    # Imposto l'asse Y per mostrare solo valori interi
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    
    # Aggiungo una griglia per migliorare la leggibilita
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    # Inserisco informazioni su Coin Days Destroyed
    cdd_text = (f'Coin Days Destroyed Totali: {results.get("coin_days_destroyed", 0):.2f}\n'
                f'Media per Input: {results.get("avg_coin_days_per_input", 0):.2f}')
    ax.text(0.98, 0.98, cdd_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8, edgecolor='gray'))
    
    plt.tight_layout()
    
    # Salvo il file
    try:
        # Creo la cartella plot se non esiste
        plot_dir = 'plot'
        if not os.path.exists(plot_dir):
            os.makedirs(plot_dir)
        
        filename = os.path.join(plot_dir, 'fan_in_age_distribution.png')
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"Istogramma distribuzioni eta salvato come: {filename}")
        plt.close()
    except Exception as e:
        print(f"\nErrore durante il salvataggio dell'istogramma: {e}")
        plt.close()
        raise  # Rilancio l'eccezione per vedere l'errore completo


def create_input_hourly_distribution(results: Dict[str, Any]) -> None:
    """
    Crea un istogramma della distribuzione oraria degli input.
    Mostra in quale fascia oraria sono stati creati gli input della transazione Fan-In.
    
    Args:
        results: Dizionario con i risultati dell'analisi
    """
    tx_data = results.get('tx_data', {})
    inputs = tx_data.get('inputs', [])
    
    if not inputs:
        print("Nessun dato sugli input disponibile per la distribuzione oraria")
        return
    
    # Raccolgo le ore di creazione degli input
    hourly_counts = [0] * 24  # Array per 24 ore (0-23)
    inputs_with_time = 0
    
    for inp in inputs:
        # Cerco il timestamp dell'input (quando è stato creato come output)
        creation_time = inp.get('creation_time')
        if creation_time:
            try:
                # Converto il timestamp in ora
                if isinstance(creation_time, str):
                    from datetime import datetime
                    dt = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                elif isinstance(creation_time, int):
                    from datetime import datetime, timezone
                    dt = datetime.fromtimestamp(creation_time, tz=timezone.utc)
                else:
                    continue
                
                hour = dt.hour
                hourly_counts[hour] += 1
                inputs_with_time += 1
            except Exception as e:
                continue
    
    # Se non trovo dati temporali, non creo il grafico
    if inputs_with_time == 0:
        print(f"Nessun dato temporale disponibile per gli input (0/{len(inputs)} input con timestamp)")
        return
    
    # Preparo i dati per il grafico
    hours = [f"{h:02d}:00" for h in range(24)]
    
    # Creo il grafico con matplotlib
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(14, 7))
    
    # Disegno l'istogramma con colori graduati
    colors = plt.cm.viridis(np.linspace(0.3, 0.9, 24))
    bars = ax.bar(range(24), hourly_counts, color=colors, edgecolor='black', linewidth=1)
    
    # Aggiungo i valori sopra le barre (solo se > 0)
    for i, (bar, count) in enumerate(zip(bars, hourly_counts)):
        if count > 0:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2.0, height,
                    f'{int(count)}',
                    ha='center', va='bottom', fontsize=9, weight='bold')
    
    # Imposto etichette e titolo
    ax.set_xlabel('Fascia Oraria (UTC)', fontsize=12, weight='bold')
    ax.set_ylabel('Numero di Input', fontsize=12, weight='bold')
    ax.set_title('Distribuzione Oraria degli Input', fontsize=16, weight='bold', pad=20)
    
    # Imposto le etichette dell'asse X
    ax.set_xticks(range(24))
    ax.set_xticklabels(hours, rotation=45, ha='right', fontsize=9)
    
    # Imposto l'asse Y per mostrare solo valori interi
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    
    # Aggiungo una griglia per migliorare la leggibilità
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    # Identifico l'ora di picco
    max_hour = hourly_counts.index(max(hourly_counts))
    max_count = max(hourly_counts)
    
    # Inserisco informazioni statistiche
    info_text = (f'Input con timestamp: {inputs_with_time}/{len(inputs)}\n'
                 f'Ora di picco: {max_hour:02d}:00-{(max_hour+1)%24:02d}:00 ({max_count} input)\n'
                 f'Media per ora: {inputs_with_time/24:.1f} input')
    
    ax.text(0.98, 0.98, info_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8, edgecolor='blue'))
    
    plt.tight_layout()
    
    # Salvo il file
    try:
        # Creo la cartella plot se non esiste
        plot_dir = 'plot'
        if not os.path.exists(plot_dir):
            os.makedirs(plot_dir)
        
        filename = os.path.join(plot_dir, 'fan_in_hourly_distribution.png')
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"Grafico distribuzione oraria salvato come: {filename}")
        plt.close()
    except Exception as e:
        print(f"\nErrore durante il salvataggio del grafico orario: {e}")
        plt.close()
        raise


def create_fan_in_report(results: Dict[str, Any]) -> None:
    """
    Crea un report testuale dettagliato dell'analisi Fan-In.
    
    Args:
        results: Dizionario con i risultati dell'analisi
    """
    print("\n" + "="*70)
    print("                    REPORT ANALISI FAN-IN")
    print("="*70)

    # Illustro le metriche principali
    print(f"\nMETRICHE PRINCIPALI:")
    print(f"   - Numero Input: {results.get('input_count', 0)}")
    print(f"   - Numero Output: {results.get('output_count', 0)}")
    print(f"   - Valore Bitcoin Raccolto: {results.get('total_input_value', 0):.8f} BTC")
    print(f"   - Valore Bitcoin in Uscita: {results.get('total_output_value', 0):.8f} BTC")
    print(f"   - Costo Operazione (Commissione): {results.get('operation_cost', 0):.8f} BTC")

    # Analizzo i Coin Days Destroyed
    cdd = results.get('coin_days_destroyed', 0)
    avg_cdd = results.get('avg_coin_days_per_input', 0)
    print(f"\nCOIN DAYS DESTROYED:")
    print(f"   - Totale: {cdd:.2f}")
    print(f"   - Media per Input: {avg_cdd:.2f}")

    if avg_cdd > 30:
        print(f"   - Interpretazione: CDD elevato - gli input sono rimasti inattivi per un periodo")
        print(f"     significativo. Possibile utilizzo in tumbler/mixer o conservazione a lungo termine.")
    elif avg_cdd > 7:
        print(f"   - Interpretazione: CDD moderato - comportamento normale di consolidamento fondi.")
    else:
        print(f"   - Interpretazione: CDD basso - rapido movimento di fondi, tipico di exchange")
        print(f"     o operazioni frequenti.")

    # Analizzo gli output
    payment = results.get('payment_output', {})
    change = results.get('change_output', {})

    if payment and change:
        print(f"\nANALISI OUTPUT:")
        print(f"   - Output Pagamento: {payment.get('value', 0):.8f} BTC")
        if payment.get('address'):
            print(f"     Indirizzo: {payment['address']}")

        print(f"   - Output Resto: {change.get('value', 0):.8f} BTC")
        if change.get('address'):
            print(f"     Indirizzo: {change['address']}")

        ratio = payment.get('value', 0) / change.get('value', 1) if change.get('value', 0) > 0 else 0
        print(f"   - Rapporto Pagamento/Resto: {ratio:.4f}")

    # Riporto la distribuzione delle eta
    age_dist = results.get('age_distribution', {})
    if age_dist:
        print(f"\nDISTRIBUZIONE ETA INPUT:")
        for age_range, count in age_dist.items():
            percentage = (count / results.get('input_count', 1)) * 100
            print(f"   - {age_range}: {count} input ({percentage:.1f}%)")

    # Riporto la distribuzione oraria
    hourly_dist = results.get('hourly_distribution', {})
    if hourly_dist:
        print(f"\nDISTRIBUZIONE ORARIA INPUT:")
        # Ordino per numero di input (decrescente)
        sorted_hours = sorted(hourly_dist.items(), key=lambda x: x[1], reverse=True)
        for i, (hour, count) in enumerate(sorted_hours[:5]):
            if count > 0:
                percentage = (count / results.get('input_count', 1)) * 100
                print(f"   {i+1}. {hour}:00-{int(hour)+1:02d}:00: {count} input ({percentage:.1f}%)")

    print("\n" + "="*70)
