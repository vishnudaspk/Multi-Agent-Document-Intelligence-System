"""
ui/streamlit_app.py
MADIS — Multi-Agent Document Intelligence System
Streamlit frontend: Upload | Chat | Compare | Alerts
"""

import math
import time
import uuid
import requests
import streamlit as st
import streamlit.components.v1 as components

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="MADIS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
    font-family: 'DM Sans', sans-serif;
    background-color: #F5F4F0;
    color: #1A1A18;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid #E8E6E0 !important;
    padding-top: 0 !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem;
}

/* ── Header ── */
header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #E8E6E0 !important;
    gap: 0 !important;
    padding: 0 !important;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #888880 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    padding: 10px 20px !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    transition: color 0.15s ease !important;
}

.stTabs [aria-selected="true"] {
    color: #1A1A18 !important;
    border-bottom: 2px solid #1A1A18 !important;
    background: transparent !important;
}

.stTabs [data-baseweb="tab"]:hover {
    color: #1A1A18 !important;
    background: transparent !important;
}

.stTabs [data-baseweb="tab-panel"] {
    padding-top: 1.5rem !important;
}

/* ── Cards ── */
.card {
    background: #FFFFFF;
    border: 1px solid #E8E6E0;
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
}

/* ── Chat bubbles ── */
.chat-user {
    display: flex;
    justify-content: flex-end;
    margin: 12px 0;
}

.chat-user-bubble {
    background: #1A1A18;
    color: #F5F4F0;
    padding: 10px 16px;
    border-radius: 14px 14px 3px 14px;
    max-width: 72%;
    font-size: 0.9rem;
    line-height: 1.55;
    font-weight: 400;
}

.chat-ai {
    display: flex;
    justify-content: flex-start;
    margin: 12px 0;
}

.chat-ai-bubble {
    background: #FFFFFF;
    border: 1px solid #E8E6E0;
    color: #1A1A18;
    padding: 12px 16px;
    border-radius: 14px 14px 14px 3px;
    max-width: 80%;
    font-size: 0.9rem;
    line-height: 1.6;
}

.chat-meta {
    font-family: 'DM Mono', monospace;
    font-size: 0.72rem;
    color: #AAAAAA;
    margin-top: 4px;
    margin-left: 4px;
}

/* ── Source chips ── */
.source-chip {
    display: inline-block;
    background: #F5F4F0;
    border: 1px solid #E0DED8;
    color: #555550;
    border-radius: 4px;
    padding: 3px 9px;
    font-family: 'DM Mono', monospace;
    font-size: 0.72rem;
    margin: 2px 3px 2px 0;
    font-weight: 500;
}

/* ── Severity badges ── */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-family: 'DM Mono', monospace;
}

.badge-critical { background: #FEE2E2; color: #991B1B; }
.badge-high     { background: #FFF3E0; color: #A04000; }
.badge-medium   { background: #FFFBEB; color: #854D0E; }
.badge-low      { background: #ECFDF5; color: #065F46; }

/* ── Alert rows ── */
.alert-row {
    background: #FFFFFF;
    border: 1px solid #E8E6E0;
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 10px;
}

.alert-row.critical { border-left: 3px solid #EF4444; }
.alert-row.high     { border-left: 3px solid #F97316; }
.alert-row.medium   { border-left: 3px solid #F59E0B; }
.alert-row.low      { border-left: 3px solid #22C55E; }

/* ── Buttons ── */
.stButton > button {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    border-radius: 6px !important;
    transition: all 0.15s ease !important;
}

.stButton > button[kind="primary"] {
    background: #1A1A18 !important;
    border: 1px solid #1A1A18 !important;
    color: #FFFFFF !important;
}

.stButton > button[kind="primary"]:hover {
    background: #333330 !important;
    border-color: #333330 !important;
}

.stButton > button[kind="secondary"],
.stButton > button:not([kind]) {
    background: #FFFFFF !important;
    border: 1px solid #D8D6D0 !important;
    color: #1A1A18 !important;
}

.stButton > button[kind="secondary"]:hover,
.stButton > button:not([kind]):hover {
    border-color: #1A1A18 !important;
    background: #F5F4F0 !important;
}

/* ── Inputs ── */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    font-family: 'DM Sans', sans-serif !important;
    background: #FFFFFF !important;
    border: 1px solid #D8D6D0 !important;
    border-radius: 6px !important;
    color: #1A1A18 !important;
    font-size: 0.9rem !important;
}

.stTextInput input:focus,
.stTextArea textarea:focus {
    border-color: #1A1A18 !important;
    box-shadow: none !important;
}

.stSelectbox > div > div {
    background: #FFFFFF !important;
    border: 1px solid #D8D6D0 !important;
    border-radius: 6px !important;
    color: #1A1A18 !important;
}

/* ── Chat Input ── */
[data-testid="stChatInput"] {
    background: #FFFFFF !important;
    border: 1px solid #D8D6D0 !important;
    border-radius: 8px !important;
    box-shadow: none !important;
}

[data-testid="stChatInput"] textarea {
    font-family: 'DM Sans', sans-serif !important;
    color: #1A1A18 !important;
    background: transparent !important;
    font-size: 0.9rem !important;
}

[data-testid="stChatInput"] button {
    color: #1A1A18 !important;
}

/* ── Slider ── */
.stSlider [data-baseweb="slider"] [role="slider"] {
    background: #1A1A18 !important;
    border-color: #1A1A18 !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    color: #1A1A18 !important;
    background: #FFFFFF !important;
    border: 1px solid #E8E6E0 !important;
    border-radius: 6px !important;
}

/* ── Labels & Text ── */
.stMarkdown p, .stMarkdown li,
.stCheckbox label, .stRadio label,
.stSelectbox label, .stSlider label,
.stNumberInput label, label {
    color: #1A1A18 !important;
    font-family: 'DM Sans', sans-serif !important;
}

.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    color: #1A1A18 !important;
    letter-spacing: -0.02em !important;
}

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: #1A1A18 !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: #FFFFFF !important;
    border: 1px dashed #D8D6D0 !important;
    border-radius: 8px !important;
}

/* ── Progress ── */
.stProgress > div > div > div {
    background: #1A1A18 !important;
}

/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid #E8E6E0 !important;
}

/* ── Info / Success / Error ── */
.stAlert {
    border-radius: 6px !important;
    border: 1px solid !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.875rem !important;
}

/* ── Code blocks ── */
.stCodeBlock {
    border-radius: 6px !important;
}

code {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.8rem !important;
}

/* ── Hide Streamlit footer ── */
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── State initialization ──────────────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "total_tokens" not in st.session_state:
    st.session_state.total_tokens = 0
if "total_queries" not in st.session_state:
    st.session_state.total_queries = 0


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 0.5rem 0 1.25rem 0; border-bottom: 1px solid #E8E6E0; margin-bottom: 1.25rem;">
        <div style="font-family: 'DM Sans', sans-serif; font-size: 1.35rem; font-weight: 600;
                    color: #1A1A18; letter-spacing: -0.03em; line-height: 1.2;">
            MADIS
        </div>
        <div style="font-family: 'DM Sans', sans-serif; font-size: 0.78rem;
                    color: #888880; margin-top: 3px; font-weight: 400;">
            Document Intelligence System
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Hardware Telemetry via JS fetch
    monitor_html = f"""
    <style>
    .hw-card {{
        background: #F5F4F0;
        border: 1px solid #E8E6E0;
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 8px;
        font-family: 'DM Sans', sans-serif;
    }}
    .hw-label {{
        font-size: 0.7rem;
        font-weight: 600;
        color: #888880;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
        display: flex;
        justify-content: space-between;
    }}
    .hw-value {{
        font-size: 0.85rem;
        font-weight: 600;
        color: #1A1A18;
    }}
    .hw-bar-track {{
        background: #E8E6E0;
        height: 3px;
        border-radius: 2px;
        margin-top: 6px;
        overflow: hidden;
    }}
    .hw-bar {{
        height: 100%;
        border-radius: 2px;
        transition: width 0.4s ease;
    }}
    </style>

    <div class="hw-card">
        <div class="hw-label">
            <span>CPU</span>
            <span id="cpu-val" class="hw-value">—</span>
        </div>
        <div class="hw-bar-track">
            <div id="cpu-bar" class="hw-bar" style="width:0%; background:#1A1A18;"></div>
        </div>
    </div>

    <div class="hw-card">
        <div class="hw-label">
            <span>Memory</span>
            <span id="ram-val" class="hw-value">—</span>
        </div>
        <div class="hw-bar-track">
            <div id="ram-bar" class="hw-bar" style="width:0%; background:#555550;"></div>
        </div>
    </div>

    <div class="hw-card">
        <div class="hw-label">
            <span>GPU</span>
            <span id="gpu-util" class="hw-value">—</span>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:0.72rem; color:#888880; margin-top:1px;">
            <span id="gpu-temp">—</span>
            <span id="gpu-mem">—</span>
        </div>
        <div class="hw-bar-track">
            <div id="gpu-bar" class="hw-bar" style="width:0%; background:#333330;"></div>
        </div>
    </div>

    <script>
    async function fetchStats() {{
        try {{
            const res = await fetch("{API_BASE}/system/stats");
            const d = await res.json();

            document.getElementById('cpu-val').innerText = d.cpu.utilization_percent + '%';
            document.getElementById('cpu-bar').style.width = d.cpu.utilization_percent + '%';

            document.getElementById('ram-val').innerText = d.ram.used_gb + ' GB';
            document.getElementById('ram-bar').style.width = d.ram.utilization_percent + '%';

            if (d.gpu) {{
                const vgb = (d.gpu.vram_used_mb / 1024).toFixed(1);
                const vp = (d.gpu.vram_used_mb / d.gpu.vram_total_mb * 100);
                document.getElementById('gpu-util').innerText = d.gpu.gpu_util_percent + '%';
                document.getElementById('gpu-temp').innerText = d.gpu.gpu_temp_c + '°C';
                document.getElementById('gpu-mem').innerText = vgb + ' GB VRAM';
                const bar = document.getElementById('gpu-bar');
                bar.style.width = vp + '%';
                bar.style.background = vp > 90 ? '#EF4444' : vp > 70 ? '#F59E0B' : '#333330';
            }} else {{
                document.getElementById('gpu-util').innerText = 'N/A';
            }}
        }} catch(e) {{}}
    }}
    fetchStats();
    setInterval(fetchStats, 3000);
    </script>
    """

    st.markdown("""<div style="font-size:0.75rem; font-weight:600; color:#888880;
                text-transform:uppercase; letter-spacing:0.05em;
                margin-bottom:8px;">Hardware</div>""", unsafe_allow_html=True)
    components.html(monitor_html, height=190)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown("""<div style="font-size:0.75rem; font-weight:600; color:#888880;
                text-transform:uppercase; letter-spacing:0.05em;
                margin-bottom:8px;">Session</div>""", unsafe_allow_html=True)

    col_t, col_q = st.columns(2)
    with col_t:
        st.markdown(f"""
        <div style="background:#F5F4F0; border:1px solid #E8E6E0; border-radius:6px;
                    padding:10px 12px;">
            <div style="font-size:0.7rem; color:#888880; font-weight:600;
                        text-transform:uppercase; letter-spacing:0.05em;">Tokens</div>
            <div style="font-size:1.1rem; font-weight:600; color:#1A1A18; margin-top:2px;">
                {st.session_state.total_tokens:,}
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_q:
        st.markdown(f"""
        <div style="background:#F5F4F0; border:1px solid #E8E6E0; border-radius:6px;
                    padding:10px 12px;">
            <div style="font-size:0.7rem; color:#888880; font-weight:600;
                        text-transform:uppercase; letter-spacing:0.05em;">Queries</div>
            <div style="font-size:1.1rem; font-weight:600; color:#1A1A18; margin-top:2px;">
                {st.session_state.total_queries}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown("""<div style="font-size:0.75rem; font-weight:600; color:#888880;
                text-transform:uppercase; letter-spacing:0.05em;
                margin-bottom:8px;">Retrieval</div>""", unsafe_allow_html=True)
    top_k = st.slider("Vector depth", 1, 15, 5,
                      help="Number of semantic chunks fetched from Qdrant.",
                      label_visibility="collapsed")
    st.caption(f"Retrieving top {top_k} chunks")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.divider()
    if st.button("Reset session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.chat_history = []
        st.rerun()


# ── Helpers ───────────────────────────────────────────────────────────────────
def fetch_documents() -> list[dict]:
    try:
        r = requests.get(f"{API_BASE}/documents/", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def poll_job(job_id: str, max_attempts: int = 30) -> dict:
    for _ in range(max_attempts):
        try:
            r = requests.get(f"{API_BASE}/documents/status/{job_id}", timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data["status"] in ("completed", "failed"):
                    return data
        except Exception:
            pass
        time.sleep(2)
    return {"status": "timeout"}


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_chat, tab_upload, tab_compare, tab_alerts = st.tabs([
    "Chat", "Documents", "Compare", "Audit Log"
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Chat
# ═══════════════════════════════════════════════════════════════════════════════
with tab_chat:
    docs = fetch_documents()
    completed_docs = [d for d in docs if d.get("status") == "completed"]
    doc_options = {d["filename"]: d["id"] for d in completed_docs}

    selected_doc = st.selectbox(
        "Knowledge base scope",
        options=["All documents"] + list(doc_options.keys()),
        key="chat_doc_filter",
    )

    chat_container = st.container(height=520)
    with chat_container:
        if not st.session_state.chat_history:
            st.markdown("""
            <div style="display:flex; flex-direction:column; align-items:center;
                        justify-content:center; height:400px; color:#AAAAAA;
                        font-family:'DM Sans',sans-serif;">
                <div style="font-size:1.1rem; font-weight:500; color:#888880;">
                    Ask a question to begin
                </div>
                <div style="font-size:0.825rem; margin-top:6px; color:#AAAAAA;">
                    Select a document scope above or query the full knowledge base
                </div>
            </div>
            """, unsafe_allow_html=True)

        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(
                    f'<div class="chat-user"><div class="chat-user-bubble">{msg["content"]}</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="chat-ai"><div class="chat-ai-bubble">{msg["content"]}</div></div>',
                    unsafe_allow_html=True,
                )
                meta_parts = []
                if msg.get("latency_ms"):
                    meta_parts.append(f"{msg['latency_ms']} ms")
                if msg.get("tokens"):
                    meta_parts.append(f"~{msg['tokens']} tokens")
                if meta_parts:
                    st.markdown(
                        f'<div class="chat-meta">{" · ".join(meta_parts)}</div>',
                        unsafe_allow_html=True,
                    )

                if msg.get("sources"):
                    chips = "".join(
                        f'<span class="source-chip" title="Score: {s.get("score",0):.4f}">'
                        f'p.{s.get("page_number") or "?"} · {s.get("document_id","")[:8]}'
                        f'</span>'
                        for s in msg["sources"][:5]
                    )
                    st.markdown(
                        f'<div style="margin-top:6px; margin-left:2px;">{chips}</div>',
                        unsafe_allow_html=True,
                    )

                for alert in msg.get("alerts", []):
                    sev = alert.get("severity", "medium")
                    border = {"critical": "#EF4444", "high": "#F97316",
                              "medium": "#F59E0B", "low": "#22C55E"}.get(sev, "#F59E0B")
                    st.markdown(
                        f'<div style="margin-top:10px; border-left:3px solid {border}; '
                        f'background:#FFFFFF; border-radius:0 6px 6px 0; padding:10px 14px;">'
                        f'<span style="font-size:0.72rem; font-weight:600; color:{border}; '
                        f'text-transform:uppercase; letter-spacing:0.05em;">'
                        f'{alert.get("type","FLAG")}</span>'
                        f'<span style="font-size:0.875rem; color:#333330; margin-left:10px;">'
                        f'{alert.get("message","")}</span></div>',
                        unsafe_allow_html=True,
                    )

    user_input = st.chat_input("Ask a question about your documents...")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        st.session_state.total_queries += 1
        st.rerun()

    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
        user_input = st.session_state.chat_history[-1]["content"]
        doc_id = doc_options.get(selected_doc) if selected_doc != "All documents" else None
        payload = {
            "question": user_input,
            "top_k": top_k,
            "session_id": st.session_state.session_id,
        }
        if doc_id:
            payload["document_id"] = doc_id

        with chat_container:
            with st.spinner("Processing..."):
                try:
                    r = requests.post(f"{API_BASE}/query/", json=payload, timeout=300)
                    if r.status_code == 200:
                        data = r.json()
                        ans = data.get("answer", "No answer returned.")
                        est_tokens = len(ans) // 4
                        st.session_state.total_tokens += est_tokens
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": ans,
                            "sources": data.get("sources", []),
                            "alerts": data.get("alerts", []),
                            "latency_ms": data.get("latency_ms", 0),
                            "tokens": est_tokens,
                        })
                    else:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": f"Error {r.status_code}: {r.text[:200]}",
                            "sources": [], "alerts": [],
                        })
                except Exception as e:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"Connection error: {e}",
                        "sources": [], "alerts": [],
                    })
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Documents
# ═══════════════════════════════════════════════════════════════════════════════
with tab_upload:
    col_up, col_list = st.columns([1, 1], gap="large")

    with col_up:
        st.markdown("#### Upload document")
        st.markdown("<p style='color:#888880; font-size:0.85rem; margin-top:-8px;'>Parsed and embedded into Qdrant vector store</p>", unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "Choose file",
            type=["pdf", "docx", "doc", "txt", "md", "html", "png", "jpg", "jpeg", "pptx", "xlsx"],
            label_visibility="collapsed",
        )

        if uploaded:
            st.markdown(
                f"<div style='font-size:0.825rem; color:#555550; margin-bottom:10px;'>"
                f"<strong>{uploaded.name}</strong> &nbsp;·&nbsp; {uploaded.size / 1024:.1f} KB</div>",
                unsafe_allow_html=True,
            )
            if st.button("Ingest document", type="primary", use_container_width=True):
                with st.spinner("Uploading..."):
                    try:
                        resp = requests.post(
                            f"{API_BASE}/documents/ingest",
                            files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                            timeout=30,
                        )
                        if resp.status_code == 202:
                            data = resp.json()
                            st.success(f"Queued — Job `{data['job_id'][:18]}…`")
                            prog = st.progress(0, text="Processing…")
                            start_time = time.time()
                            # Rough heuristic: ~1s per 50KB for parsing + embedding
                            expected_time = max(5.0, uploaded.size / 51200.0)
                            
                            for _ in range(600):
                                job_status = "processing"
                                error_msg = "Unknown error"
                                try:
                                    r = requests.get(f"{API_BASE}/documents/status/{data['job_id']}", timeout=5)
                                    if r.status_code == 200:
                                        jd = r.json()
                                        job_status = jd.get("status", "processing")
                                        error_msg = jd.get("error_msg", error_msg)
                                except Exception:
                                    pass
                                
                                elapsed = time.time() - start_time
                                progress_val = min(0.99, 1.0 - math.exp(-elapsed / (expected_time / 2)))
                                pct = int(progress_val * 100)
                                eta = max(0, expected_time - elapsed)
                                eta_str = f"{int(eta)}s" if eta < 60 else f"{int(eta//60)}m {int(eta%60)}s"
                                if pct >= 99:
                                    eta_str = "few seconds..."
                                
                                if job_status == "completed":
                                    prog.progress(1.0, text="Status: COMPLETED • Progress: 100% • ETA: 0s")
                                    time.sleep(0.5)
                                    st.rerun()
                                    break
                                elif job_status == "failed":
                                    prog.progress(1.0, text="Status: FAILED")
                                    st.error(error_msg)
                                    break
                                else:
                                    prog.progress(
                                        progress_val,
                                        text=f"Status: {job_status.upper()} • Progress: {pct}% • ETA: ~{eta_str}"
                                    )
                                
                                time.sleep(1.5)
                        else:
                            st.error(f"Ingestion failed: {resp.text}")
                    except Exception as e:
                        st.error(f"Network error: {e}")

    with col_list:
        st.markdown("#### Knowledge base")
        docs = fetch_documents()
        if not docs:
            st.info("No documents indexed yet.")
        else:
            STATUS_ICON = {
                "completed": "●", "failed": "●", "processing": "○", "pending": "○"
            }
            STATUS_COLOR = {
                "completed": "#22C55E", "failed": "#EF4444",
                "processing": "#F59E0B", "pending": "#AAAAAA"
            }
            for doc in docs[:20]:
                status = doc.get("status", "")
                icon = STATUS_ICON.get(status, "○")
                color = STATUS_COLOR.get(status, "#AAAAAA")
                with st.expander(
                    f"{doc['filename']}",
                    expanded=False,
                ):
                    st.markdown(
                        f"<span style='color:{color}; font-size:0.75rem; font-weight:600;'>"
                        f"{icon} {status.upper()}</span>",
                        unsafe_allow_html=True,
                    )
                    st.code(
                        f"id:   {doc['id']}\ntype: {doc.get('file_type','unknown')}\n"
                        f"size: {(doc.get('file_size') or 0) / 1024:.1f} KB",
                        language="yaml",
                    )
                    if doc.get("error_msg"):
                        st.error(doc["error_msg"])
                    if st.button("Delete", key=f"del_{doc['id']}", use_container_width=True):
                        try:
                            r = requests.delete(f"{API_BASE}/documents/{doc['id']}", timeout=10)
                            if r.status_code == 204:
                                st.success("Deleted.")
                                time.sleep(0.8)
                                st.rerun()
                            else:
                                st.error(f"Delete failed: {r.text}")
                        except Exception as e:
                            st.error(f"Network error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Compare
# ═══════════════════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown("#### Document comparison")
    st.markdown("<p style='color:#888880; font-size:0.85rem; margin-top:-8px;'>Cross-document differential analysis via multi-agent reasoning</p>", unsafe_allow_html=True)

    docs = fetch_documents()
    completed_docs = [d for d in docs if d.get("status") == "completed"]

    if len(completed_docs) < 2:
        st.warning("Two or more indexed documents are required for comparison.")
    else:
        doc_map = {f"{d['filename']} ({d['id'][:8]})": d["id"] for d in completed_docs}
        doc_names = list(doc_map.keys())

        col_a, col_vs, col_b = st.columns([5, 1, 5])
        with col_a:
            sel_a = st.selectbox("Document A", options=doc_names, key="cmp_a")
        with col_vs:
            st.markdown(
                "<div style='text-align:center; padding-top:30px; color:#AAAAAA; font-size:0.8rem;'>vs</div>",
                unsafe_allow_html=True,
            )
        with col_b:
            remaining = [n for n in doc_names if n != sel_a]
            sel_b = st.selectbox("Document B", options=remaining, key="cmp_b")

        cmp_query = st.text_input(
            "Comparison focus",
            value="Map all specific technical and factual differences between these documents.",
            help="Instruct the agent on what to look for.",
        )

        if st.button("Run comparison", type="primary", use_container_width=True):
            with st.spinner("Generating differential analysis — this may take 30–90 seconds…"):
                try:
                    r = requests.post(
                        f"{API_BASE}/query/compare",
                        json={
                            "document_id_a": doc_map[sel_a],
                            "document_id_b": doc_map[sel_b],
                            "query": cmp_query,
                            "session_id": st.session_state.session_id,
                        },
                        timeout=300,
                    )
                    if r.status_code == 200:
                        cmp = r.json()
                        st.session_state["last_comparison"] = cmp
                        st.session_state.total_tokens += len(cmp.get("summary", "")) // 4
                        st.session_state.total_queries += 1
                    else:
                        st.error(f"Error {r.status_code}: {r.text[:300]}")
                except Exception as e:
                    st.error(f"Request failed: {e}")

        cmp = st.session_state.get("last_comparison")
        if cmp:
            if cmp.get("latency_ms"):
                st.markdown(
                    f"<div style='font-size:0.75rem; color:#AAAAAA; text-align:right; margin-bottom:12px;'>"
                    f"Completed in {cmp['latency_ms'] / 1000:.2f}s</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("**Summary**")
            st.markdown(
                f'<div class="card" style="color:#1A1A18; font-size:0.9rem; line-height:1.6;">'
                f'{cmp.get("summary", "No summary generated.")}</div>',
                unsafe_allow_html=True,
            )

            col_sim, col_diff = st.columns(2, gap="large")
            with col_sim:
                st.markdown("**Similarities**")
                for s in cmp.get("similarities", []):
                    st.markdown(
                        f'<div style="display:flex; gap:8px; margin-bottom:6px; font-size:0.875rem; color:#333330;">'
                        f'<span style="color:#AAAAAA; flex-shrink:0;">—</span>{s}</div>',
                        unsafe_allow_html=True,
                    )

            with col_diff:
                st.markdown("**Differences**")
                for d in cmp.get("differences", []):
                    aspect = d.get("aspect", "Unknown")
                    st.markdown(
                        f'<div style="margin-bottom:14px;">'
                        f'<div style="font-size:0.75rem; font-weight:600; color:#888880; '
                        f'text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px;">{aspect}</div>'
                        f'<div style="background:#F5F4F0; border-left:2px solid #D8D6D0; '
                        f'padding:8px 12px; border-radius:0 4px 4px 0; font-size:0.85rem; '
                        f'color:#333330; margin-bottom:4px;"><strong>A:</strong> {d.get("doc_a","")}</div>'
                        f'<div style="background:#F5F4F0; border-left:2px solid #1A1A18; '
                        f'padding:8px 12px; border-radius:0 4px 4px 0; font-size:0.85rem; '
                        f'color:#333330;"><strong>B:</strong> {d.get("doc_b","")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            if cmp.get("recommendation"):
                st.markdown("**Recommendation**")
                st.info(cmp["recommendation"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Alerts
# ═══════════════════════════════════════════════════════════════════════════════
with tab_alerts:
    st.markdown("#### Audit log")
    st.markdown("<p style='color:#888880; font-size:0.85rem; margin-top:-8px;'>Flagged anomalies and compliance violations</p>", unsafe_allow_html=True)

    col_f1, col_f2, col_f3, col_refresh = st.columns([2, 2, 2, 1])
    with col_f1:
        filter_sev = st.selectbox("Severity", ["all", "critical", "high", "medium", "low"])
    with col_f2:
        filter_type = st.selectbox("Type", ["all", "anomaly", "contradiction", "missing_clause"])
    with col_f3:
        filter_limit = st.number_input("Limit", min_value=5, max_value=200, value=50)
    with col_refresh:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.button("Refresh", use_container_width=True)

    params: dict = {"limit": filter_limit}
    if filter_sev != "all":
        params["severity"] = filter_sev
    if filter_type != "all":
        params["alert_type"] = filter_type

    try:
        r = requests.get(f"{API_BASE}/alerts/", params=params, timeout=10)
        alerts = r.json() if r.status_code == 200 else []
    except Exception:
        alerts = []

    if not alerts:
        st.info("No violations recorded.")
    else:
        st.caption(f"{len(alerts)} records")
        for alert in alerts:
            sev = alert.get("severity", "medium")
            atype = alert.get("alert_type", "anomaly").replace("_", " ").title()
            border = {"critical": "#EF4444", "high": "#F97316",
                      "medium": "#F59E0B", "low": "#22C55E"}.get(sev, "#F59E0B")
            badge_bg = {"critical": "#FEE2E2", "high": "#FFF3E0",
                        "medium": "#FFFBEB", "low": "#ECFDF5"}.get(sev, "#FFFBEB")
            created = alert.get("created_at", "")[:16].replace("T", "  ")

            st.markdown(f"""
            <div style="background:#FFFFFF; border:1px solid #E8E6E0;
                        border-left:3px solid {border}; border-radius:6px;
                        padding:14px 16px; margin-bottom:10px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="background:{badge_bg}; color:{border}; padding:2px 8px;
                                     border-radius:3px; font-size:0.7rem; font-weight:700;
                                     font-family:'DM Mono',monospace; text-transform:uppercase;
                                     letter-spacing:0.04em;">{sev}</span>
                        <span style="font-size:0.82rem; font-weight:600; color:#555550;
                                     text-transform:uppercase; letter-spacing:0.04em;">{atype}</span>
                    </div>
                    <span style="font-family:'DM Mono',monospace; font-size:0.72rem;
                                 color:#AAAAAA;">{created}</span>
                </div>
                <div style="font-size:0.875rem; color:#1A1A18; margin-bottom:10px; line-height:1.5;">
                    {alert.get('message','')}
                </div>
                <div style="font-family:'DM Mono',monospace; font-size:0.75rem; color:#555550;
                            background:#F5F4F0; padding:10px 12px; border-radius:4px;
                            border:1px solid #E8E6E0; white-space:pre-wrap;">
{alert.get('context','No trace data available')}</div>
            </div>
            """, unsafe_allow_html=True)