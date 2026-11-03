import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Gestionale Biblioteca", layout="wide", page_icon="📚")

# --- INIZIALIZZAZIONE DATABASE ---
def init_db():
    conn = sqlite3.connect('biblioteca.db')
    c = conn.cursor()
    # Tabella Libri
    c.execute('''CREATE TABLE IF NOT EXISTS libri (
                    isbn TEXT PRIMARY KEY,
                    titolo TEXT,
                    autore TEXT,
                    copie_totali INTEGER,
                    copie_disponibili INTEGER)''')
    # Tabella Utenti
    c.execute('''CREATE TABLE IF NOT EXISTS utenti (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT,
                    cognome TEXT,
                    email TEXT,
                    telefono TEXT)''')
    # Tabella Prestiti
    c.execute('''CREATE TABLE IF NOT EXISTS prestiti (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    isbn TEXT,
                    utente_id INTEGER,
                    data_prestito TEXT,
                    data_restituzione TEXT,
                    stato TEXT,
                    FOREIGN KEY(isbn) REFERENCES libri(isbn),
                    FOREIGN KEY(utente_id) REFERENCES utenti(id))''')
    conn.commit()
    conn.close()

init_db()

# --- FUNZIONE RICERCA ISBN ONLINE (OPEN LIBRARY + GOOGLE BOOKS) ---
def get_book_by_isbn(isbn):
    isbn_clean = isbn.strip().replace("-", "").replace(" ", "").upper()
    if not isbn_clean:
        return None, None

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # 1. Prova Open Library
    try:
        url_ol = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_clean}&format=json&jscmd=data"
        res_ol = requests.get(url_ol, headers=headers, timeout=6)
        if res_ol.status_code == 200:
            data = res_ol.json()
            key = f"ISBN:{isbn_clean}"
            if key in data:
                titolo = data[key].get("title", "")
                autori = ", ".join([a.get("name") for a in data[key].get("authors", [])]) or "Sconosciuto"
                return titolo, autori
    except Exception:
        pass

    # 2. Prova Google Books
    try:
        url_gb = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_clean}"
        res_gb = requests.get(url_gb, headers=headers, timeout=6)
        if res_gb.status_code == 200:
            data = res_gb.json()
            if "items" in data and len(data["items"]) > 0:
                info = data["items"][0]["volumeInfo"]
                titolo = info.get("title", "")
                autori = ", ".join(info.get("authors", ["Sconosciuto"]))
                return titolo, autori
    except Exception:
        pass

    return None, None

def get_connection():
    return sqlite3.connect('biblioteca.db')

# --- INTERFACCIA PRINCIPALE ---
st.title("📚 Banco Biblioteca - Gestione Prestiti")

menu = st.sidebar.radio("Sezioni:", [
    "📖 Catalogo Libri (ISBN)", 
    "📋 Registra Prestito", 
    "🔄 Rientro Prestito", 
    "👥 Anagrafica Utenti", 
    "📊 Storico Prestiti"
])

conn = get_connection()
c = conn.cursor()

# -------------------------------------------------------------
# 1. CATALOGO LIBRI (CON RICERCA ISBN + INSERIMENTO MANUALE)
# -------------------------------------------------------------
if menu == "📖 Catalogo Libri (ISBN)":
    st.subheader("Aggiungi o Modifica un Libro")

    # Inizializzazione session_state per i valori del form
    if "titolo_temp" not in st.session_state:
        st.session_state.titolo_temp = ""
    if "autore_temp" not in st.session_state:
        st.session_state.autore_temp = ""

    col_isbn, col_btn = st.columns([3, 1])
    isbn_inserito = col_isbn.text_input("Codice ISBN (es. 9788804668237):").strip().replace("-", "")

    if col_btn.button("🔍 Cerca Online"):
        if isbn_inserito:
            t, a = get_book_by_isbn(isbn_inserito)
            if t:
                st.session_state.titolo_temp = t
                st.session_state.autore_temp = a
                st.success(f"Trovato: {t} di {a}")
            else:
                st.warning("Nessun risultato online trovato. Inserisci i dati manualmente nei campi sotto.")
        else:
            st.error("Inserisci prima un codice ISBN.")

    # Campi compilabili (modificabili sempre dall'utente)
    titolo_finale = st.text_input("Titolo del libro:", value=st.session_state.titolo_temp)
    autore_finale = st.text_input("Autore:", value=st.session_state.autore_temp)
    copie = st.number_input("Quantità copie:", min_value=1, value=1, step=1)

    if st.button("💾 Salva nel Catalogo", type="primary"):
        if not isbn_inserito:
            st.error("Il codice ISBN è obbligatorio (se assente sul libro, usa un codice inventato univoco, es. LIB-001).")
        elif not titolo_finale.strip():
            st.error("Il Titolo è obbligatorio.")
        else:
            try:
                # Verifica se il libro esiste già
                c.execute("SELECT copie_totali, copie_disponibili FROM libri WHERE isbn = ?", (isbn_inserito,))
                libro_esistente = c.fetchone()

                if libro_esistente:
                    nuove_totali = libro_esistente[0] + copie
                    nuove_disp = libro_esistente[1] + copie
                    c.execute("""UPDATE libri 
                                 SET copie_totali = ?, copie_disponibili = ?, titolo = ?, autore = ? 
                                 WHERE isbn = ?""",
                              (nuove_totali, nuove_disp, titolo_finale.strip(), autore_finale.strip(), isbn_inserito))
                    st.success(f"Aggiunte {copie} copie al libro già presente: '{titolo_finale}'.")
                else:
                    c.execute("""INSERT INTO libri (isbn, titolo, autore, copie_totali, copie_disponibili) 
                                 VALUES (?, ?, ?, ?, ?)""",
                              (isbn_inserito, titolo_finale.strip(), autore_finale.strip(), copie, copie))
                    st.success(f"Libro '{titolo_finale}' registrato con successo nel catalogo!")

                conn.commit()
                st.session_state.titolo_temp = ""
                st.session_state.autore_temp = ""
                st.rerun()
            except Exception as e:
                st.error(f"Errore nel database: {e}")

    st.divider()
    st.subheader("Libri Attualmente a Catalogo")
    catalogo = c.execute("SELECT isbn, titolo, autore, copie_disponibili, copie_totali FROM libri").fetchall()
    if catalogo:
        df = pd.DataFrame(catalogo, columns=["ISBN", "Titolo", "Autore", "Copie Disponibili", "Copie Totali"])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nessun libro inserito finora.")

# -------------------------------------------------------------
# 2. REGISTRA PRESTITO
# -------------------------------------------------------------
elif menu == "📋 Registra Prestito":
    st.subheader("Registra Uscita Libro")

    utenti = c.execute("SELECT id, nome, cognome FROM utenti").fetchall()
    libri_disp = c.execute("SELECT isbn, titolo, autore, copie_disponibili FROM libri WHERE copie_disponibili > 0").fetchall()

    if not utenti:
        st.warning("Nessun utente registrato. Vai prima nella sezione 'Anagrafica Utenti'.")
    elif not libri_disp:
        st.warning("Nessun libro disponibile per il prestito al momento.")
    else:
        diz_utenti = {f"{u[1]} {u[2]} (ID: {u[0]})": u[0] for u in utenti}
        diz_libri = {f"{b[1]} - {b[2]} (Copie disp: {b[3]})": b[0] for b in libri_disp}

        utente_selezionato = st.selectbox("Seleziona Utente:", list(diz_utenti.keys()))
        libro_selezionato = st.selectbox("Seleziona Libro:", list(diz_libri.keys()))
        data_inizio = st.date_input("Data Prestito:", date.today())

        if st.button("Conferma e Registra Prestito", type="primary"):
            id_utente = diz_utenti[utente_selezionato]
            isbn_libro = diz_libri[libro_selezionato]

            # Inserisce prestito
            c.execute("INSERT INTO prestiti (isbn, utente_id, data_prestito, stato) VALUES (?, ?, ?, 'IN CORSO')",
                      (isbn_libro, id_utente, str(data_inizio)))
            # Scala copia
            c.execute("UPDATE libri SET copie_disponibili = copie_disponibili - 1 WHERE isbn = ?", (isbn_libro,))
            conn.commit()

            st.success("Prestito registrato correttamente!")
            st.rerun()

# -------------------------------------------------------------
# 3. RIENTRO PRESTITO
# -------------------------------------------------------------
elif menu == "🔄 Rientro Prestito":
    st.subheader("Registra Rientro Libro")

    query = '''SELECT p.id, l.titolo, u.nome, u.cognome, p.data_prestito, p.isbn 
               FROM prestiti p
               JOIN libri l ON p.isbn = l.isbn
               JOIN utenti u ON p.utente_id = u.id
               WHERE p.stato = 'IN CORSO' '''
    in_corso = c.execute(query).fetchall()

    if not in_corso:
        st.info("Non ci sono prestiti attivi al momento.")
    else:
        prestiti_attivi = {f"'{p[1]}' preso da {p[2]} {p[3]} in data {p[4]}": (p[0], p[5]) for p in in_corso}
        selezione = st.selectbox("Seleziona il prestito da chiudere:", list(prestiti_attivi.keys()))

        if st.button("Segna come Rientrato / Restituito", type="primary"):
            id_prestito, isbn_libro = prestiti_attivi[selezione]
            oggi = str(date.today())

            # Chiude prestito e ripristina la disponibilità
            c.execute("UPDATE prestiti SET stato = 'RESTITUITO', data_restituzione = ? WHERE id = ?", (oggi, id_prestito))
            c.execute("UPDATE libri SET copie_disponibili = copie_disponibili + 1 WHERE isbn = ?", (isbn_libro,))
            conn.commit()

            st.success("Libro restituito e disponibilità aggiornata!")
            st.rerun()

# -------------------------------------------------------------
# 4. ANAGRAFICA UTENTI
# -------------------------------------------------------------
elif menu == "👥 Anagrafica Utenti":
    st.subheader("Aggiungi Nuovo Utente")
    col_n, col_c = st.columns(2)
    nome = col_n.text_input("Nome:")
    cognome = col_c.text_input("Cognome:")
    col_e, col_t = st.columns(2)
    email = col_e.text_input("Email (opzionale):")
    telefono = col_t.text_input("Telefono (opzionale):")

    if st.button("Registra Utente", type="primary"):
        if nome.strip() and cognome.strip():
            c.execute("INSERT INTO utenti (nome, cognome, email, telefono) VALUES (?, ?, ?, ?)",
                      (nome.strip(), cognome.strip(), email.strip(), telefono.strip()))
            conn.commit()
            st.success(f"Utente '{nome} {cognome}' registrato!")
            st.rerun()
        else:
            st.error("Nome e Cognome sono campi obbligatori.")

    st.divider()
    st.subheader("Utenti Registrati")
    lista_utenti = c.execute("SELECT id, nome, cognome, email, telefono FROM utenti").fetchall()
    if lista_utenti:
        df_u = pd.DataFrame(lista_utenti, columns=["ID", "Nome", "Cognome", "Email", "Telefono"])
        st.dataframe(df_u, use_container_width=True)
    else:
        st.info("Nessun utente registrato.")

# -------------------------------------------------------------
# 5. STORICO PRESTITI
# -------------------------------------------------------------
elif menu == "📊 Storico Prestiti":
    st.subheader("Riepilogo Totale Prestiti")
    query = '''SELECT p.id, l.titolo, p.isbn, u.nome || ' ' || u.cognome as utente, 
                      p.data_prestito, p.data_restituzione, p.stato 
               FROM prestiti p
               JOIN libri l ON p.isbn = l.isbn
               JOIN utenti u ON p.utente_id = u.id
               ORDER BY p.id DESC'''
    storico = c.execute(query).fetchall()
    if storico:
        df_s = pd.DataFrame(storico, columns=["ID", "Titolo", "ISBN", "Utente", "Data Prestito", "Data Reso", "Stato"])
        st.dataframe(df_s, use_container_width=True)
    else:
        st.info("Nessuna movimentazione registrata.")

conn.close()
