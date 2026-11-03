import re
import io
import base64
import requests
import sqlite3
import pandas as pd
import streamlit as st
from datetime import date

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Gestionale Biblioteca", layout="wide", page_icon="📚")

# --- MOTORE DI RICERCA ISBN (OTTIMIZZATO) ---
def pulisci_isbn(s):
    return re.sub(r"[^0-9Xx]", "", s or "").upper()

def isbn10_a_13(i):
    if len(i) != 10: 
        return i
    base = "978" + i[:9]
    ctrl = (10 - sum(int(c) * (1 if n % 2 == 0 else 3) for n, c in enumerate(base)) % 10) % 10
    return base + str(ctrl)

HEADERS = {"User-Agent": "GestionaleBiblioteca/1.0 (streamlit)"}

def _get(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=12)
    r.raise_for_status()
    return r.json()

def cover_valida(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        return r.ok and "image" in r.headers.get("content-type", "")
    except Exception:
        return False

def _google(q, isbn):
    p = {"q": q, "maxResults": 5, "country": "IT"}
    if "GOOGLE_BOOKS_KEY" in st.secrets:
        p["key"] = st.secrets["GOOGLE_BOOKS_KEY"]
         GOOGLE_BOOKS_KEY = "AIzaSyAXp61M1AGtnFnEByUKAzl87lAWgXZTjdQ"
    items = _get("https://www.googleapis.com/books/v1/volumes", p).get("items") or []
    for it in items:
        ids = [x.get("identifier", "") for x in it["volumeInfo"].get("industryIdentifiers", [])]
        if isbn in ids:
            scelto = it
            break
    if not scelto and items and q.startswith("isbn:"):
        scelto = items[0]
    if not scelto:
        return None
    v = scelto["volumeInfo"]
    cover = (v.get("imageLinks") or {}).get("thumbnail", "").replace("http://", "https://").replace("&edge=curl", "")
    return {"titolo": v.get("title", ""), "autore": ", ".join(v.get("authors", [])),
            "editore": v.get("publisher", ""), "copertina": cover}

def google_isbn(isbn):
    return _google(f"isbn:{isbn}", isbn)

def google_testo(isbn):
    return _google(isbn, isbn)

def openlibrary(isbn):
    d = _get("https://openlibrary.org/api/books",
             {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"}).get(f"ISBN:{isbn}")
    if not d:
        return None
    return {"titolo": d.get("title", ""),
            "autore": ", ".join(a["name"] for a in d.get("authors", [])),
            "editore": ", ".join(p["name"] for p in d.get("publishers", [])),
            "copertina": (d.get("cover") or {}).get("medium", "")}

FONTI = (google_isbn, google_testo, openlibrary)

@st.cache_data(ttl=86400, show_spinner=False)
def _cerca_online(isbn):
    # Se non trova nulla solleva un errore: cosi' l'esito negativo NON viene messo in cache.
    errori = []
    for fonte in FONTI:
        try:
            ris = fonte(isbn)
            if ris and ris["titolo"]:
                if not ris["copertina"]:
                    alt = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"
                    ris["copertina"] = alt if cover_valida(alt) else ""
                return ris
            errori.append(f"{fonte.__name__}: nessun risultato")
        except Exception as e:
            errori.append(f"{fonte.__name__}: {e}")
    raise LookupError(" | ".join(errori))

def cerca_libro(isbn_grezzo):
    """Ritorna (dati, motivo_errore)."""
    isbn = pulisci_isbn(isbn_grezzo)
    if not isbn:
        return None, "ISBN vuoto"
    motivo = ""
    for codice in dict.fromkeys([isbn, isbn10_a_13(isbn)]):
        try:
            ris = dict(_cerca_online(codice))
            ris["isbn"] = codice
            return ris, ""
        except LookupError as e:
            motivo = str(e)
    return None, motivo

# --- COPERTINE ---
def immagine_a_data_uri(file):
    from PIL import Image
    img = Image.open(file).convert("RGB")
    img.thumbnail((400, 600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

def mostra_cover(src, **kw):
    try:
        if src.startswith("data:image"):
            st.image(base64.b64decode(src.split(",", 1)[1]), **kw)
        else:
            st.image(src, **kw)
    except Exception:
        st.caption("Copertina non disponibile")

# --- INIZIALIZZAZIONE DATABASE ---
def init_db():
    conn = sqlite3.connect('biblioteca.db')
    c = conn.cursor()
    # Tabella Libri
    c.execute('''CREATE TABLE IF NOT EXISTS libri (
                    isbn TEXT PRIMARY KEY,
                    titolo TEXT,
                    autore TEXT,
                    editore TEXT,
                    copie_totali INTEGER,
                    copie_disponibili INTEGER,
                    copertina_url TEXT)''')

    # Migrazioni automatiche per colonne aggiuntive
    try:
        c.execute("ALTER TABLE libri ADD COLUMN copertina_url TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE libri ADD COLUMN editore TEXT")
    except sqlite3.OperationalError:
        pass

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

def get_connection():
    return sqlite3.connect('biblioteca.db')

# --- INTERFACCIA ---
st.title("📚 Banco Biblioteca - Gestione Prestiti")

menu = st.sidebar.radio("Sezioni:", [
    "📖 Catalogo Libri (ISBN)", 
    "📋 Registra Prestito", 
    "🔄 Rientro Prestito", 
    "👥 Anagrafica Utenti", 
    "📊 Storico Prestiti"
])

try:
    with open("biblioteca.db", "rb") as f:
        st.sidebar.download_button("💾 Scarica backup database", f.read(), "biblioteca.db")
except Exception:
    pass

conn = get_connection()
c = conn.cursor()

# -------------------------------------------------------------
# 1. CATALOGO LIBRI (CON LOGICA OTTIMIZZATA)
# -------------------------------------------------------------
if menu == "📖 Catalogo Libri (ISBN)":
    st.subheader("Aggiungi o Aggiorna Libro")

    # Inizializza session_state per i campi
    for k in ["titolo_temp", "autore_temp", "editore_temp", "cover_temp", "isbn_temp"]:
        if k not in st.session_state:
            st.session_state[k] = ""

    col_isbn, col_btn = st.columns([3, 1])
    isbn_inserito = col_isbn.text_input("Codice ISBN (10 o 13 cifre):", value=st.session_state.isbn_temp)

    if col_btn.button("🔍 Cerca Dati"):
        if isbn_inserito:
            with st.spinner("Ricerca nei database in corso..."):
                dati, motivo = cerca_libro(isbn_inserito)
                if dati:
                    st.session_state.titolo_temp = dati["titolo"]
                    st.session_state.autore_temp = dati["autore"]
                    st.session_state.editore_temp = dati["editore"]
                    st.session_state.cover_temp = dati["copertina"]
                    st.session_state.isbn_temp = dati["isbn"]
                    st.success(f"Trovato: {dati['titolo']}")
                    st.rerun()
                else:
                    st.session_state.isbn_temp = pulisci_isbn(isbn_inserito)
                    st.warning("Nessun dato trovato online. Puoi compilare i campi a mano.")
                    with st.expander("Dettagli tecnici"):
                        st.write(motivo)
        else:
            st.error("Inserisci prima un codice ISBN.")

    # Form dati e anteprima copertina
    col_dati, col_anteprima = st.columns([3, 1])

    with col_dati:
        titolo_finale = st.text_input("Titolo:", value=st.session_state.titolo_temp)
        autore_finale = st.text_input("Autore:", value=st.session_state.autore_temp)
        editore_finale = st.text_input("Editore:", value=st.session_state.editore_temp)
        copertina_url = st.text_input("URL Copertina:", value=st.session_state.cover_temp)
        file_cover = st.file_uploader("...oppure carica la copertina (foto o immagine)", type=["jpg", "jpeg", "png", "webp"])
        if file_cover:
            copertina_url = immagine_a_data_uri(file_cover)
        copie = st.number_input("Quantità copie:", min_value=1, value=1, step=1)

    with col_anteprima:
        if copertina_url:
            mostra_cover(copertina_url, caption="Anteprima Copertina", width=140)
        else:
            st.info("Nessuna copertina")

    if st.button("💾 Salva nel Catalogo", type="primary"):
        isbn_finale = pulisci_isbn(isbn_inserito)
        if not isbn_finale:
            st.error("L'ISBN è obbligatorio.")
        elif not titolo_finale.strip():
            st.error("Il Titolo è obbligatorio.")
        else:
            try:
                c.execute("SELECT copie_totali, copie_disponibili FROM libri WHERE isbn = ?", (isbn_finale,))
                esiste = c.fetchone()

                if esiste:
                    c.execute("""UPDATE libri 
                                 SET copie_totali = copie_totali + ?, 
                                     copie_disponibili = copie_disponibili + ?, 
                                     titolo = ?, autore = ?, editore = ?, copertina_url = ? 
                                 WHERE isbn = ?""",
                              (copie, copie, titolo_finale.strip(), autore_finale.strip(), editore_finale.strip(), copertina_url, isbn_finale))
                    st.success(f"Aggiunte {copie} copie al libro '{titolo_finale}'.")
                else:
                    c.execute("""INSERT INTO libri (isbn, titolo, autore, editore, copie_totali, copie_disponibili, copertina_url) 
                                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
                              (isbn_finale, titolo_finale.strip(), autore_finale.strip(), editore_finale.strip(), copie, copie, copertina_url))
                    st.success(f"Libro '{titolo_finale}' inserito a catalogo!")

                conn.commit()
                # Reset campi
                for k in ["titolo_temp", "autore_temp", "editore_temp", "cover_temp", "isbn_temp"]:
                    st.session_state[k] = ""
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante il salvataggio: {e}")

    st.divider()
    st.subheader("Catalogo Attuale")
    catalogo = c.execute("SELECT copertina_url, isbn, titolo, autore, editore, copie_disponibili, copie_totali FROM libri").fetchall()
    if catalogo:
        df = pd.DataFrame(catalogo, columns=["Copertina", "ISBN", "Titolo", "Autore", "Editore", "Disp.", "Totali"])
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
                mostra_cover(copertina_sel, width=130, caption="Libro selezionato")

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
        st.info("Nessun prestito attivo al momento.")
    else:
        prestiti_attivi = {f"'{p[1]}' preso da {p[2]} {p[3]} (il {p[4]})": (p[0], p[5], p[6]) for p in in_corso}
        selezione = st.selectbox("Seleziona prestito da chiudere:", list(prestiti_attivi.keys()))

        id_prestito, isbn_libro, cover = prestiti_attivi[selezione]
        if cover:
            mostra_cover(cover, width=120)

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
