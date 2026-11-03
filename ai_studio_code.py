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

# --- FUNZIONE RECUPERO INFO DA ISBN (OpenLibrary + Google Books) ---
def get_book_by_isbn(isbn):
    # Pulisce l'ISBN da trattini, spazi o caratteri strani
    isbn_clean = isbn.strip().replace("-", "").replace(" ", "").upper()
    if not isbn_clean:
        return None, None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    # TENTATIVO 1: Open Library (eccellente per server cloud, nessun blocco)
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

    # TENTATIVO 2: Google Books API (con User-Agent per non essere bloccati)
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
# -------------------------------------------------------------
# 3. CATALOGO LIBRI (CORRETTO E MIGLIORATO)
# -------------------------------------------------------------
elif menu == "📖 Catalogo Libri (ISBN)":
    st.subheader("Aggiungi Libro al Catalogo")

    # Inizializza variabili di stato per i campi se non esistono
    if "titolo_val" not in st.session_state:
        st.session_state.titolo_val = ""
    if "autore_val" not in st.session_state:
        st.session_state.autore_val = ""

    col_isbn, col_btn = st.columns([3, 1])
    isbn_input = col_isbn.text_input("Codice ISBN (es. 9788804668237)", key="isbn_field").strip().replace("-", "")

    # Tasto per cercare tramite ISBN
    if col_btn.button("🔍 Cerca Dati"):
        if isbn_input:
            t, a = get_book_by_isbn(isbn_input)
            if t:
                st.session_state.titolo_val = t
                st.session_state.autore_val = a
                st.success(f"Trovato: {t}")
            else:
                st.warning("ISBN non trovato online. Puoi compilare a mano qui sotto.")
        else:
            st.error("Inserisci prima un codice ISBN.")

    # Campi compilabili (sia da ricerca ISBN che manualmente)
    titolo = st.text_input("Titolo del libro", value=st.session_state.titolo_val)
    autore = st.text_input("Autore", value=st.session_state.autore_val)
    copie = st.number_input("Quantità copie", min_value=1, value=1, step=1)

    # Tasto definitivo di Salvataggio
    if st.button("💾 Salva nel Catalogo", type="primary"):
        if not isbn_input:
            st.error("Attenzione: il campo ISBN è obbligatorio (se il libro non ce l'ha, inventa un codice univoco, es. LIB001).")
        elif not titolo:
            st.error("Attenzione: il Titolo è obbligatorio.")
        else:
            try:
                # Controlla se il libro esiste già
                esistente = c.execute("SELECT copie_totali, copie_disponibili FROM libri WHERE isbn = ?", (isbn_input,)).fetchone()
                
                if esistente:
                    nuove_tot = esistente[0] + copie
                    nuove_disp = esistente[1] + copie
                    c.execute("UPDATE libri SET copie_totali = ?, copie_disponibili = ?, titolo = ?, autore = ? WHERE isbn = ?",
                              (nuove_tot, nuove_disp, titolo, autore, isbn_input))
                else:
                    c.execute("INSERT INTO libri (isbn, titolo, autore, copie_totali, copie_disponibili) VALUES (?, ?, ?, ?, ?)",
                              (isbn_input, titolo, autore, copie, copie))
                
                conn.commit()
                st.success(f"Libro '{titolo}' salvato con successo!")
                
                # Reset campi
                st.session_state.titolo_val = ""
                st.session_state.autore_val = ""
                st.rerun()
            except Exception as e:
                st.error(f"Errore nel salvataggio: {e}")

    st.divider()
    st.subheader("Catalogo Attuale")
    
    # Mostra catalogo aggiornato
    libri_raw = c.execute("SELECT isbn, titolo, autore, copie_disponibili, copie_totali FROM libri").fetchall()
    if libri_raw:
        import pandas as pd
        df = pd.DataFrame(libri_raw, columns=["ISBN", "Titolo", "Autore", "Copie Disp.", "Copie Totali"])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nessun libro presente nel catalogo.")
