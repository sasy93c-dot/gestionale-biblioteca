import streamlit as st
import sqlite3
import requests
from datetime import datetime, date

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

# --- FUNZIONE RECUPERO INFO DA ISBN (Google Books API) ---
def get_book_by_isbn(isbn):
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        res = requests.get(url).json()
        if "items" in res:
            info = res["items"][0]["volumeInfo"]
            titolo = info.get("title", "")
            autori = ", ".join(info.get("authors", ["Sconosciuto"]))
            return titolo, autori
    except Exception:
        pass
    return None, None

# --- CONNESSIONE DB ---
def get_connection():
    return sqlite3.connect('biblioteca.db')

# --- INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="Gestionale Biblioteca", layout="wide")
st.title("📚 Banco Biblioteca - Gestione Prestiti")

menu = st.sidebar.radio("Navigazione", [
    "📋 Registra Prestito", 
    "🔄 Rientro Prestito", 
    "📖 Catalogo Libri (ISBN)", 
    "👥 Anagrafica Utenti", 
    "📊 Storico Prestiti"
])

conn = get_connection()
c = conn.cursor()

# -------------------------------------------------------------
# 1. REGISTRA PRESTITO
# -------------------------------------------------------------
if menu == "📋 Registra Prestito":
    st.subheader("Nuovo Prestito")
    
    # Preleva utenti e libri disponibili
    utenti = c.execute("SELECT id, nome, cognome FROM utenti").fetchall()
    libri = c.execute("SELECT isbn, titolo FROM libri WHERE copie_disponibili > 0").fetchall()
    
    if not utenti or not libri:
        st.warning("Assicurati di avere almeno un utente registrato e almeno un libro disponibile a catalogo.")
    else:
        user_dict = {f"{u[1]} {u[2]} (ID: {u[0]})": u[0] for u in utenti}
        book_dict = {f"{b[1]} (ISBN: {b[0]})": b[0] for b in libri}
        
        with st.form("prestito_form"):
            selected_user = st.selectbox("Seleziona Utente", list(user_dict.keys()))
            selected_book = st.selectbox("Seleziona Libro", list(book_dict.keys()))
            data_prestito = st.date_input("Data Inizio", date.today())
            
            submitted = st.form_submit_button("Conferma Prestito")
            if submitted:
                u_id = user_dict[selected_user]
                b_isbn = book_dict[selected_book]
                
                # Registra prestito
                c.execute("INSERT INTO prestiti (isbn, utente_id, data_prestito, stato) VALUES (?, ?, ?, 'IN CORSO')",
                          (b_isbn, u_id, str(data_prestito)))
                # Scala disponibilità libro
                c.execute("UPDATE libri SET copie_disponibili = copie_disponibili - 1 WHERE isbn = ?", (b_isbn,))
                conn.commit()
                st.success("Prestito registrato con successo!")
                st.rerun()

# -------------------------------------------------------------
# 2. RIENTRO PRESTITO
# -------------------------------------------------------------
elif menu == "🔄 Rientro Prestito":
    st.subheader("Restituzione Libro")
    query = '''SELECT p.id, l.titolo, u.nome, u.cognome, p.data_prestito, p.isbn 
               FROM prestiti p
               JOIN libri l ON p.isbn = l.isbn
               JOIN utenti u ON p.utente_id = u.id
               WHERE p.stato = 'IN CORSO' '''
    attivi = c.execute(query).fetchall()
    
    if not attivi:
        st.info("Nessun prestito attualmente in corso.")
    else:
        prestito_dict = {f"{p[1]} preso da {p[2]} {p[3]} in data {p[4]}": (p[0], p[5]) for p in attivi}
        selected = st.selectbox("Seleziona prestito da chiudere:", list(prestito_dict.keys()))
        
        if st.button("Segna come Restituito"):
            prestito_id, isbn = prestito_dict[selected]
            oggi = str(date.today())
            c.execute("UPDATE prestiti SET stato = 'RESTITUITO', data_restituzione = ? WHERE id = ?", (oggi, prestito_id))
            c.execute("UPDATE libri SET copie_disponibili = copie_disponibili + 1 WHERE isbn = ?", (isbn,))
            conn.commit()
            st.success("Libro restituito e inventario aggiornato!")
            st.rerun()

# -------------------------------------------------------------
# 3. CATALOGO LIBRI (CON ISBN LOOKUP)
# -------------------------------------------------------------
elif menu == "📖 Catalogo Libri (ISBN)":
    st.subheader("Aggiungi Nuovo Libro")
    
    isbn_input = st.text_input("Inserisci o scansiona ISBN:")
    
    titolo_default, autore_default = "", ""
    if isbn_input:
        t, a = get_book_by_isbn(isbn_input.replace("-", "").strip())
        if t:
            titolo_default, autore_default = t, a
            st.success(f"Dati trovati: {t} di {a}")
        else:
            st.info("ISBN non trovato automaticamente. Inserisci i dati manualmente.")
            
    with st.form("libro_form"):
        titolo = st.text_input("Titolo", value=titolo_default)
        autore = st.text_input("Autore", value=autore_default)
        copie = st.number_input("Quantità copie", min_value=1, value=1)
        
        btn_libro = st.form_submit_button("Salva nel Catalogo")
        if btn_libro and isbn_input:
            c.execute("""INSERT INTO libri (isbn, titolo, autore, copie_totali, copie_disponibili)
                         VALUES (?, ?, ?, ?, ?)
                         ON CONFLICT(isbn) DO UPDATE SET 
                         copie_totali = copie_totali + excluded.copie_totali,
                         copie_disponibili = copie_disponibili + excluded.copie_disponibili""",
                      (isbn_input.strip(), titolo, autore, copie, copie))
            conn.commit()
            st.success(f"Libro '{titolo}' aggiunto!")
            st.rerun()
            
    st.divider()
    st.subheader("Catalogo Attuale")
    libri_df = c.execute("SELECT isbn, titolo, autore, copie_disponibili, copie_totali FROM libri").fetchall()
    st.dataframe(libri_df, use_container_width=True)

# -------------------------------------------------------------
# 4. ANAGRAFICA UTENTI
# -------------------------------------------------------------
elif menu == "👥 Anagrafica Utenti":
    st.subheader("Aggiungi Nuovo Utente")
    with st.form("utente_form"):
        col1, col2 = st.columns(2)
        nome = col1.text_input("Nome")
        cognome = col2.text_input("Cognome")
        email = col1.text_input("Email")
        tel = col2.text_input("Telefono")
        
        btn_user = st.form_submit_button("Registra Utente")
        if btn_user and nome and cognome:
            c.execute("INSERT INTO utenti (nome, cognome, email, telefono) VALUES (?, ?, ?, ?)",
                      (nome, cognome, email, tel))
            conn.commit()
            st.success(f"Utente {nome} {cognome} registrato!")
            st.rerun()

    st.divider()
    st.subheader("Lista Utenti")
    utenti_df = c.execute("SELECT id, nome, cognome, email, telefono FROM utenti").fetchall()
    st.dataframe(utenti_df, use_container_width=True)

# -------------------------------------------------------------
# 5. STORICO PRESTITI
# -------------------------------------------------------------
elif menu == "📊 Storico Prestiti":
    st.subheader("Monitoraggio Prestiti Totali")
    query = '''SELECT p.id, l.titolo, p.isbn, u.nome || ' ' || u.cognome as utente, 
                      p.data_prestito, p.data_restituzione, p.stato 
               FROM prestiti p
               JOIN libri l ON p.isbn = l.isbn
               JOIN utenti u ON p.utente_id = u.id
               ORDER BY p.id DESC'''
    prestiti_df = c.execute(query).fetchall()
    st.dataframe(prestiti_df, use_container_width=True)

conn.close()