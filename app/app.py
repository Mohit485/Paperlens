import os
import uuid
import time
import requests
import streamlit as st
import streamlit.components.v1 as components  # Required for browser JS execution

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="PaperLens", page_icon="📄", layout="wide")

# ---------------------------------------------------------------------------
# API WAKE-UP LOGIC (Browser-native JS ping)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# API WAKE-UP LOGIC (Using st.html to replace deprecated components.html)
# ---------------------------------------------------------------------------
def ensure_api_awake_js(api_url):
    """
    Triggers an HTTP ping directly from the client's browser using st.html.
    Avoids st.components.v1.html deprecation warnings and iframe sandboxing issues.
    """
    if "api_is_awake" not in st.session_state:
        st.session_state.api_is_awake = False

    if not st.session_state.api_is_awake:
        # Fast Python backend check first in case it's already awake
        try:
            r = requests.get(f"{api_url}/health", timeout=2)
            if r.status_code == 200:
                st.session_state.api_is_awake = True
                return True
        except Exception:
            pass

        # Native JS injection via st.html (no iframe deprecation warnings)
        js_code = f"""
        <div id="status-container" style="font-family: sans-serif; color: #FAFAFA; padding: 12px; background: #1B1F27; border: 1px solid #2A2F3A; border-radius: 8px; margin-bottom: 20px;">
            ⏳ Waking up API backend service on Render... Please wait up to 50 seconds.
        </div>
        <script>
        (function wakeUpBackend() {{
            const healthUrl = "{api_url}/health";
            let interval = setInterval(async () => {{
                try {{
                    let res = await fetch(healthUrl, {{ method: 'GET', mode: 'cors' }});
                    if (res.ok) {{
                        clearInterval(interval);
                        const statusDiv = document.getElementById("status-container");
                        if (statusDiv) statusDiv.innerText = "✅ Backend API is online! Reloading...";
                        window.location.reload();
                    }}
                }} catch (e) {{
                    console.log("Waiting for backend cold-start...");
                }}
            }}, 4000);
        }})();
        </script>
        """
        st.html(js_code)
        st.stop()

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="st-"], [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    [data-testid="stIconMaterial"],
    span[class*="material-symbols"],
    span[class*="material-icons"] {
        font-family: 'Material Symbols Outlined', 'Material Symbols Rounded', 'Material Icons' !important;
    }

    #MainMenu,
    [data-testid="stMainMenu"],
    [data-testid="stToolbarActions"],
    [data-testid="stStatusWidget"] {
        display: none !important;
    }
    header[data-testid="stHeader"] {
        background: transparent;
    }
    [data-testid="stToolbar"] {
        visibility: visible !important;
    }

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
# WAKE UP API BEFORE DOING ANYTHING ELSE
# ---------------------------------------------------------------------------
ensure_api_awake_js(API_URL)

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
                        timeout=60
                    )
                    if response.status_code == 200:
                        st.success(f"{uploaded_file.name} added.")
                    else:
                        st.error(f"{uploaded_file.name} failed: {response.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Can't reach the backend: {e}")
                    break

    st.divider()
    st.subheader("Stored papers")

    try:
        documents_response = requests.get(f"{API_URL}/documents", timeout=30)
        documents = documents_response.json().get("documents", [])
    except requests.exceptions.RequestException:
        st.info("Backend is not responding. Please refresh the page.")
        documents = []

    if not documents:
        st.caption("Nothing uploaded yet.")

    for doc in documents:
        col1, col2 = st.columns([4, 1])
        col1.write(f"📄 {doc}")
        if col2.button("🗑️", key=f"delete_{doc}"):
            try:
                requests.delete(f"{API_URL}/documents/{doc}", timeout=30)
                st.rerun()
            except requests.exceptions.RequestException:
                st.error("Failed to delete document. Please try again.")

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

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if question:
    with st.chat_message("user"):
        st.code(question, language=None)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    f"{API_URL}/ask",
                    json={"question": question, "thread_id": st.session_state.thread_id},
                    timeout=60
                )
                if response.status_code == 200:
                    result = response.json()
                    answer = result["answer"]
                    sources = result.get("sources", [])
                    st.markdown(answer)
                    if sources:
                        st.caption("Sources: " + ", ".join(sources))
                    st.session_state.chat_history.append((question, answer, sources))
                else:
                    st.error(f"Backend error: {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"Can't reach the backend: {e}")