import requests
import streamlit as st
import os

API_URL = os.environ.get("API_URL")
if not API_URL:
    try:
        API_URL = st.secrets["API_URL"]
    except (KeyError, FileNotFoundError):
        API_URL="http://127.0.0.1:8000"

st.set_page_config(page_title="PaperLens", page_icon="📄", layout="wide")


# ---------------------------------------------------------------------------
# CSS -- font, fixed header, centered empty-state, and dark mode
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* ---- Font: applied broadly, THEN restored for icons ---- */
    html, body, [class*="st-"], [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    [data-testid="stIconMaterial"],
    span[class*="material-symbols"],
    span[class*="material-icons"] {
        font-family: 'Material Symbols Outlined', 'Material Symbols Rounded', 'Material Icons' !important;
    }

    /* ---- Hide Streamlit's own menu/deploy/status controls -- but NOT the
       whole toolbar. The toolbar also contains the sidebar's "re-expand"
       button (data-testid="stExpandSidebarButton") when the sidebar is
       collapsed. display:none on the whole [data-testid="stToolbar"]
       deletes that button from the DOM entirely -- no child !important
       rule can bring back an element whose ancestor is display:none.
       That was the actual bug: collapse the sidebar once and there is
       nothing left to click to bring it back. ---- */
    #MainMenu,
    [data-testid="stMainMenu"],
    [data-testid="stToolbarActions"],
    [data-testid="stStatusWidget"] {
        display: none !important;
    }
    header[data-testid="stHeader"] {
        background: transparent;
    }
    /* Keep the toolbar container itself intact/visible -- it's the parent
       of the expand button, so it must never be display:none. */
    [data-testid="stToolbar"] {
        visibility: visible !important;
    }

    /* ---- The actual "open sidebar" arrow (current Streamlit testid).
       Kept a couple of legacy testids too as a harmless fallback in case
       this runs on an older Streamlit version. ---- */
    [data-testid="stExpandSidebarButton"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 999999 !important;
    }
    [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"],
    [data-testid="collapsedControl"] [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Outlined', 'Material Symbols Rounded', 'Material Icons' !important;
        color: #FAFAFA !important;
    }

    /* ---- Dark mode, done directly in CSS instead of a .toml file ---- */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    [data-testid="stSidebar"] {
        background-color: #1B1F27;
    }
    [data-testid="stSidebar"] * {
        color: #FAFAFA;
    }
    .stTextInput input, [data-testid="stFileUploaderDropzone"] {
        background-color: #1B1F27 !important;
        color: #FAFAFA !important;
        border-color: #2A2F3A !important;
    }
    /* The chip that appears after a file is selected (before "Add to
       knowledge base" is clicked) -- this is the one part of tonight's
       changes I can't fully verify, since Streamlit doesn't publicly
       document this exact internal name and it's the kind of thing
       that can shift between versions. If this doesn't visibly change
       anything, it's safe to just delete this one rule -- nothing else
       depends on it. */
    [data-testid="stFileUploaderFile"] {
        background-color: #DCE9FC !important;
        border-radius: 8px;
    }
    [data-testid="stFileUploaderFile"] * {
        color: #1B1F27 !important;
    }
    [data-testid="stChatInput"], [data-testid="stChatInput"] textarea {
        background-color: #262B36 !important;
        color: #FAFAFA !important;
        border: 1px solid #2A2F3A !important;
    }
    .stButton button {
        background-color: #1B1F27;
        color: #FAFAFA;
        border-color: #2A2F3A;
    }
    .stButton button[kind="primary"] {
        background-color: #4F8EF7;
        color: #FFFFFF;
    }
    [data-testid="stFileUploaderDropzone"] button {
        background-color: #4F8EF7 !important;
        color: #FFFFFF !important;
        border: none !important;
    }
    [data-testid="stChatMessage"] {
        background-color: #1B1F27;
    }
    [data-testid="stChatMessage"] * {
        color: #FAFAFA !important;
    }
    [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid="stCode"] code,
    [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid="stCode"] code span {
        color: #0C0C0C !important;
    }

    [data-testid="stBottom"],
    [data-testid="stBottomBlockContainer"] {
        background-color: #0E1117 !important;
    }

    /* ---- Fixed header, top-right ---- */
    .app-title-fixed {
        position: fixed;
        top: 1.3rem;
        right: 2rem;
        z-index: 999999;
        font-size: 1.4rem;
        font-weight: 700;
        color: #4F8EF7;
        letter-spacing: 0.02em;
    }
    .block-container {
        padding-top: 3rem;
    }

    /* ---- Centered empty-state text ---- */
    .empty-state {
        text-align: center;
        color: #9CA3AF;
        margin-top: 5rem;
    }
    .empty-state-main {
        font-size: 1.6rem;
        font-weight: 600;
    }
    .empty-state-sub {
        font-size: 1rem;
        margin-top: 0.4rem;
    }
    </style>

    <div class="app-title-fixed">PaperLens</div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# SIDEBAR -- "Manage Documents"
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("📁 Manage Documents")

    uploaded_files = st.file_uploader(
        "Upload PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if st.button("Add to knowledge base", disabled=not uploaded_files, type="primary"):
        for uploaded_file in uploaded_files:
            with st.spinner(f"Processing {uploaded_file.name}..."):
                try:
                    response = requests.post(
                        f"{API_URL}/ingest",
                        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")},
                    )
                    if response.status_code == 200:
                        st.success(f"{uploaded_file.name} added.")
                    else:
                        st.error(f"{uploaded_file.name} failed: {response.text}")
                except requests.exceptions.ConnectionError:
                    st.error("Can't reach the backend. Is 'uvicorn api:app --reload' running?")
                    break

    st.divider()
    st.subheader("Stored papers")

    try:
        documents_response = requests.get(f"{API_URL}/documents")
        documents = documents_response.json().get("documents", [])
    except requests.exceptions.ConnectionError:
        st.error("Backend not reachable.")
        documents = []

    if not documents:
        st.caption("Nothing uploaded yet.")

    for doc in documents:
        col1, col2 = st.columns([4, 1])
        col1.write(f"📄 {doc}")
        if col2.button("🗑️", key=f"delete_{doc}"):
            requests.delete(f"{API_URL}/documents/{doc}")
            st.rerun()


# ---------------------------------------------------------------------------
# MAIN AREA -- "Ask a Question", chat-style
# ---------------------------------------------------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if not st.session_state.chat_history:
    st.markdown(
        """
        <div class="empty-state" style="text-align: left;">
            <div class="empty-state-main">Welcome to PaperLens</div>
            <div class="empty-state-sub">
                <p style="margin-top: 0.8rem; margin-bottom: 0.4rem;">Let's get started in a few steps:</p>
                <ul style="margin: 0;">
                    <li>Click the arrow (>>) in the top-left to open the sidebar</li>
                    <li>Upload a PDF using the file picker</li>
                    <li>Click "Add to knowledge base"</li>
                    <li>Ask anything about the paper in the box below</li>
                    <li>To remove a paper, click the delete button next to it under "Stored papers"</li>
                </ul>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    for question, answer, sources in st.session_state.chat_history:
        with st.chat_message("user"):
            st.code(question, language=None)
        with st.chat_message("assistant"):
            st.markdown(answer)
            if sources:
                st.caption("Sources: " + ", ".join(sources))

question = st.chat_input("Ask anything about your papers...")

if question:
    with st.chat_message("user"):
        st.code(question, language=None)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                ask_response = requests.post(f"{API_URL}/ask", json={"question": question})
                result = ask_response.json()
                answer = result["answer"]
                sources = result.get("sources", [])

                st.markdown(answer)
                if sources:
                    st.caption("Sources: " + ", ".join(sources))

                st.session_state.chat_history.append((question, answer, sources))
            except (requests.exceptions.ConnectionError, requests.exceptions.JSONDecodeError):
                st.error("Can't reach the backend. Is 'uvicorn api:app --reload' running?")