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
    # Tabella Libri con campo Copertina
    c.execute('''CREATE TABLE IF NOT EXISTS libri (
                    isbn TEXT PRIMARY KEY,
                    titolo TEXT,
                    autore TEXT,
                    copie_totali INTEGER,
                    copie_disponibili INTEGER,
                    copertina_url TEXT)''')

    # Migrazione automatica se la tabella esisteva già senza copertina_url
    try:
        c.execute("ALTER TABLE libri ADD COLUMN copertina_url TEXT")
    except sqlite3.OperationalError:
        pass  # La colonna esiste già

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

# --- MOTORE DI RICERCA ISBN POTENZIATO + COPERTINE ---
def get_book_by_isbn(isbn):
    isbn_clean = isbn.strip().replace("-", "").replace(" ", "").upper()
    if not isbn_clean:
        return None, None, None

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    # 1. Tentativo: Google Books (Ricerca mirata ISBN)
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_clean}"
        res = requests.get(url, headers=headers, timeout=5).json()
        if "items" in res and len(res["items"]) > 0:
            info = res["items"][0]["volumeInfo"]
            titolo = info.get("title", "")
            autori = ", ".join(info.get("authors", ["Sconosciuto"]))
            copertina = info.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://")
            return titolo, autori, copertina
    except Exception:
        pass

    # 2. Tentativo: Google Books (Ricerca generica - trova molti più libri italiani)
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={isbn_clean}"
        res = requests.get(url, headers=headers, timeout=5).json()
        if "items" in res and len(res["items"]) > 0:
            info = res["items"][0]["volumeInfo"]
            titolo = info.get("title", "")
            autori = ", ".join(info.get("authors", ["Sconosciuto"]))
            copertina = info.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://")
            return titolo, autori, copertina
    except Exception:
        pass

    # 3. Tentativo: Open Library Search API
    try:
        url = f"https://openlibrary.org/search.json?isbn={isbn_clean}"
        res = requests.get(url, headers=headers, timeout=5).json()
        if "docs" in res and len(res["docs"]) > 0:
            doc = res["docs"][0]
            titolo = doc.get("title", "")
            autori = ", ".join(doc.get("author_name", ["Sconosciuto"]))
            cover_id = doc.get("cover_i")
            copertina = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else f"https://covers.openlibrary.org/b/isbn/{isbn_clean}-M.jpg"
            return titolo, autori, copertina
    except Exception:
        pass

    # Fallback immagine predefinita OpenLibrary anche se i metadati mancano
    fallback_cover = f"https://covers.openlibrary.org/b/isbn/{isbn_clean}-M.jpg"
    return None, None, fallback_cover

def get_connection():
    return sqlite3.connect('biblioteca.db')

# --- MENU PRINCIPALE ---
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
# 1. CATALOGO LIBRI (CON COPERTINE E RICERCA POTENZIATA)
# -------------------------------------------------------------
if menu == "📖 Catalogo Libri (ISBN)":
    st.subheader("Aggiungi o Aggiorna Libro")

    # Gestione dello stato dei campi
    if "titolo_temp" not in st.session_state:
        st.session_state.titolo_temp = ""
    if "autore_temp" not in st.session_state:
        st.session_state.autore_temp = ""
    if "cover_temp" not in st.session_state:
        st.session_state.cover_temp = ""

    col_isbn, col_btn = st.columns([3, 1])
    isbn_inserito = col_isbn.text_input("Codice ISBN (es. 9788804668237):").strip().replace("-", "")

    if col_btn.button("🔍 Cerca Dati e Copertina"):
        if isbn_inserito:
            t, a, cov = get_book_by_isbn(isbn_inserito)
            if t:
                st.session_state.titolo_temp = t
                st.session_state.autore_temp = a
                st.session_state.cover_temp = cov or ""
                st.success(f"Trovato: {t} di {a}")
            else:
                st.session_state.cover_temp = cov or ""
                st.warning("Metadati non trovati automaticamente. Puoi inserire titolo e autore a mano.")
        else:
            st.error("Inserisci prima un codice ISBN.")

    # Sezione input con anteprima copertina
    col_dati, col_anteprima = st.columns([3, 1])

    with col_dati:
        titolo_finale = st.text_input("Titolo del libro:", value=st.session_state.titolo_temp)
        autore_finale = st.text_input("Autore:", value=st.session_state.autore_temp)
        copertina_url = st.text_input("URL Copertina (opzionale):", value=st.session_state.cover_temp)
        copie = st.number_input("Quantità copie:", min_value=1, value=1, step=1)

    with col_anteprima:
        if st.session_state.cover_temp:
            st.image(st.session_state.cover_temp, caption="Anteprima Copertina", width=140)
        else:
            st.info("Nessuna copertina caricata")

    if st.button("💾 Salva nel Catalogo", type="primary"):
        if not isbn_inserito:
            st.error("L'ISBN è obbligatorio.")
        elif not titolo_finale.strip():
            st.error("Il Titolo è obbligatorio.")
        else:
            try:
                c.execute("SELECT copie_totali, copie_disponibili FROM libri WHERE isbn = ?", (isbn_inserito,))
                libro_esistente = c.fetchone()

                if libro_esistente:
                    nuove_totali = libro_esistente[0] + copie
                    nuove_disp = libro_esistente[1] + copie
                    c.execute("""UPDATE libri 
                                 SET copie_totali = ?, copie_disponibili = ?, titolo = ?, autore = ?, copertina_url = ? 
                                 WHERE isbn = ?""",
                              (nuove_totali, nuove_disp, titolo_finale.strip(), autore_finale.strip(), copertina_url, isbn_inserito))
                    st.success(f"Aggiornate copie per: '{titolo_finale}'.")
                else:
                    c.execute("""INSERT INTO libri (isbn, titolo, autore, copie_totali, copie_disponibili, copertina_url) 
                                 VALUES (?, ?, ?, ?, ?, ?)""",
                              (isbn_inserito, titolo_finale.strip(), autore_finale.strip(), copie, copie, copertina_url))
                    st.success(f"Libro '{titolo_finale}' inserito a catalogo!")

                conn.commit()
                st.session_state.titolo_temp = ""
                st.session_state.autore_temp = ""
                st.session_state.cover_temp = ""
                st.rerun()
            except Exception as e:
                st.error(f"Errore nel salvataggio: {e}")

    st.divider()
    st.subheader("Catalogo Libri Disponibili")
    catalogo = c.execute("SELECT copertina_url, isbn, titolo, autore, copie_disponibili, copie_totali FROM libri").fetchall()
    if catalogo:
        df = pd.DataFrame(catalogo, columns=["Copertina", "ISBN", "Titolo", "Autore", "Copie Disp.", "Copie Totali"])
        st.dataframe(
            df,
            column_config={
                "Copertina": st.column_config.ImageColumn("Copertina", width="small")
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nessun libro a catalogo.")

# -------------------------------------------------------------
# 2. REGISTRA PRESTITO
# -------------------------------------------------------------
elif menu == "📋 Registra Prestito":
    st.subheader("Registra Uscita Libro")

    utenti = c.execute("SELECT id, nome, cognome FROM utenti").fetchall()
    libri_disp = c.execute("SELECT isbn, titolo, autore, copie_disponibili, copertina_url FROM libri WHERE copie_disponibili > 0").fetchall()

    if not utenti:
        st.warning("Nessun utente registrato. Vai in 'Anagrafica Utenti'.")
    elif not libri_disp:
        st.warning("Nessun libro disponibile per il prestito.")
    else:
        diz_utenti = {f"{u[1]} {u[2]} (ID: {u[0]})": u[0] for u in utenti}
        diz_libri = {f"{b[1]} - {b[2]} (Copie: {b[3]})": (b[0], b[4]) for b in libri_disp}

        col1, col2 = st.columns([3, 1])
        with col1:
            utente_sel = st.selectbox("Seleziona Utente:", list(diz_utenti.keys()))
            libro_sel = st.selectbox("Seleziona Libro:", list(diz_libri.keys()))
            data_inizio = st.date_input("Data Prestito:", date.today())

        with col2:
            copertina_sel = diz_libri[libro_sel][1]
            if copertina_sel:
                st.image(copertina_sel, width=130, caption="Libro selezionato")

        if st.button("Conferma Prestito", type="primary"):
            id_utente = diz_utenti[utente_sel]
            isbn_libro = diz_libri[libro_sel][0]

            c.execute("INSERT INTO prestiti (isbn, utente_id, data_prestito, stato) VALUES (?, ?, ?, 'IN CORSO')",
                      (isbn_libro, id_utente, str(data_inizio)))
            c.execute("UPDATE libri SET copie_disponibili = copie_disponibili - 1 WHERE isbn = ?", (isbn_libro,))
            conn.commit()

            st.success("Prestito registrato!")
            st.rerun()

# -------------------------------------------------------------
# 3. RIENTRO PRESTITO
# -------------------------------------------------------------
elif menu == "🔄 Rientro Prestito":
    st.subheader("Registra Rientro Libro")

    query = '''SELECT p.id, l.titolo, u.nome, u.cognome, p.data_prestito, p.isbn, l.copertina_url
               FROM prestiti p
               JOIN libri l ON p.isbn = l.isbn
               JOIN utenti u ON p.utente_id = u.id
               WHERE p.stato = 'IN CORSO' '''
    in_corso = c.execute(query).fetchall()

    if not in_corso:
        st.info("Non ci sono prestiti attivi al momento.")
    else:
        prestiti_attivi = {f"'{p[1]}' preso da {p[2]} {p[3]} (il {p[4]})": (p[0], p[5], p[6]) for p in in_corso}
        selezione = st.selectbox("Seleziona il prestito da chiudere:", list(prestiti_attivi.keys()))

        id_prestito, isbn_libro, cover = prestiti_attivi[selezione]
        if cover:
            st.image(cover, width=120)

        if st.button("Segna come Restituito", type="primary"):
            oggi = str(date.today())
            c.execute("UPDATE prestiti SET stato = 'RESTITUITO', data_restituzione = ? WHERE id = ?", (oggi, id_prestito))
            c.execute("UPDATE libri SET copie_disponibili = copie_disponibili + 1 WHERE isbn = ?", (isbn_libro,))
            conn.commit()

            st.success("Libro restituito!")
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
            st.error("Nome e Cognome sono obbligatori.")

    st.divider()
    st.subheader("Utenti Registrati")
    lista_utenti = c.execute("SELECT id, nome, cognome, email, telefono FROM utenti").fetchall()
    if lista_utenti:
        df_u = pd.DataFrame(lista_utenti, columns=["ID", "Nome", "Cognome", "Email", "Telefono"])
        st.dataframe(df_u, use_container_width=True, hide_index=True)
    else:
        st.info("Nessun utente registrato.")

# -------------------------------------------------------------
# 5. STORICO PRESTITI
# -------------------------------------------------------------
elif menu == "📊 Storico Prestiti":
    st.subheader("Riepilogo Totale Movimenti")
    query = '''SELECT l.copertina_url, l.titolo, p.isbn, u.nome || ' ' || u.cognome as utente, 
                      p.data_prestito, p.data_restituzione, p.stato 
               FROM prestiti p
               JOIN libri l ON p.isbn = l.isbn
               JOIN utenti u ON p.utente_id = u.id
               ORDER BY p.id DESC'''
    storico = c.execute(query).fetchall()
    if storico:
        df_s = pd.DataFrame(storico, columns=["Copertina", "Titolo", "ISBN", "Utente", "Data Prestito", "Data Reso", "Stato"])
        st.dataframe(
            df_s,
            column_config={
                "Copertina": st.column_config.ImageColumn("Copertina", width="small")
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nessuna movimentazione registrata.")

conn.close()
