"""
ui/streamlit_app.py
MADIS — Multi-Agent Document Intelligence System
Streamlit frontend: Upload | Chat | Compare | Alerts
"""

import math
import time
import uuid
import json
import requests
import portalocker
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="MADIS — Document Intelligence",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

def render_metadata_footer(msg: dict, i: int):
    """Helper to render message metadata, sources, alerts, and copy button."""
    # ── Metadata line with confidence dot ──
    meta_parts = []
    if msg.get("latency_ms"):
        lv = msg["latency_ms"]
        meta_parts.append(f"{lv / 1000:.1f}s" if lv >= 1000 else f"{lv}ms")
    if msg.get("tokens"):
        meta_parts.append(f"~{msg['tokens']} tokens")

    confidence = msg.get("confidence", "medium") or "medium"
    conf_color = {"high": "#22c55e", "medium": "#eab308", "low": "#ef4444"}.get(confidence, "#eab308")
    conf_dot = (
        f'<span style="color:{conf_color};font-size:0.72rem;vertical-align:middle;">&#9679;</span>'
        f'&thinsp;<span style="color:#9E9D98;font-size:0.75rem;">{confidence} confidence</span>'
    )
    meta_str = ("  ·  ".join(meta_parts) + "  ·  " if meta_parts else "") + conf_dot
    st.markdown(f'<div class="chat-meta">{meta_str}</div>', unsafe_allow_html=True)

    # ── Source chips as clickable buttons ──
    if msg.get("sources"):
        src_list = msg["sources"][:5]
        src_cols = st.columns(len(src_list))
        for si, s in enumerate(src_list):
            with src_cols[si]:
                doc_short = (s.get("document_id") or "")[:8]
                chip_label = f'p.{s.get("page_number") or "?"} · {doc_short}'
                if st.button(
                    chip_label,
                    key=f"src_{i}_{si}",
                    help=f"Score: {s.get('score', 0):.4f}  —  Click to preview chunk",
                ):
                    st.session_state.preview_chunk = s

    # ── Alerts ──
    for alert in msg.get("alerts", []):
        sev = alert.get("severity", "medium")
        border = {"critical": "#C53030", "high": "#B45309",
                  "medium": "#92400E", "low": "#2F8132"}.get(sev, "#92400E")
        bg = {"critical": "#FEE8E7", "high": "#FEF6E7",
              "medium": "#FFFBEB", "low": "#EBF5EB"}.get(sev, "#FFFBEB")
        st.markdown(
            f'<div style="margin-top:10px;border-left:3px solid {border};'
            f'background:{bg};border-radius:0 var(--radius-md) var(--radius-md) 0;'
            f'padding:10px 14px;">'
            f'<span style="font-size:0.7rem;font-weight:600;color:{border};'
            f'text-transform:uppercase;letter-spacing:0.05em;'
            f'font-family:\'JetBrains Mono\',monospace;">'
            f'{alert.get("type","FLAG")}</span>'
            f'<span style="font-size:0.84rem;color:#1C1C1A;margin-left:10px;">'
            f'{alert.get("message","")}</span></div>',
            unsafe_allow_html=True,
        )

    # ── Copy button ──
    content_safe = json.dumps(msg.get("content", ""))
    components.html(
        f"""<button id="cp{i}"
            onclick="navigator.clipboard.writeText({content_safe}).then(
                function(){{document.getElementById('cp{i}').innerText='Copied ✓';
                           setTimeout(function(){{document.getElementById('cp{i}').innerText='Copy';}},2000);}},
                function(){{document.getElementById('cp{i}').innerText='Copy';}});"
            style="background:transparent;border:1px solid #E5E3DD;border-radius:5px;
                   color:#9E9D98;cursor:pointer;font-size:0.72rem;
                   font-family:Inter,sans-serif;padding:3px 10px;margin-top:4px;
                   transition:all 0.12s ease;"
            onmouseover="this.style.borderColor='#9E9D98';this.style.color='#1C1C1A';"
            onmouseout="this.style.borderColor='#E5E3DD';this.style.color='#9E9D98';">
            Copy</button>""",
        height=36,
    )

def inject_chat_scroll():
    """
    Injects auto-scroll + Go-to-bottom button targeting the actual
    st.container(height=520) overflow div — not the page scroll.
    """
    components.html("""
    <script>
    (function() {
        const doc = window.parent.document;
        if (doc.getElementById('madis-chat-scroll-ready')) return;
        doc.getElementById('madis-chat-scroll-ready') && doc.getElementById('madis-chat-scroll-ready').remove();
        const sentinel = doc.createElement('div');
        sentinel.id = 'madis-chat-scroll-ready';
        sentinel.style.display = 'none';
        doc.body.appendChild(sentinel);

        // ── Find the actual chat scrollbox (st.container height=520) ──────────
        // Streamlit renders it as:  <div style="overflow: auto; height: 520px">
        const findChatBox = () => {
            // Try explicit inline-style match first (most reliable)
            let el = doc.querySelector('[style*="height: 520px"][style*="overflow"]');
            if (el) return el;
            // Fallback: any overflow:auto div whose clientHeight is between 400-600px
            return Array.from(doc.querySelectorAll('div')).find(d => {
                const s = window.parent.getComputedStyle(d);
                return (s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                       d.clientHeight > 380 && d.clientHeight < 620;
            }) || null;
        };

        // ── "Go to bottom" button ─────────────────────────────────────────────
        const btn = doc.createElement('button');
        btn.innerHTML = '↓';
        btn.title = 'Scroll to latest message';
        btn.style.cssText = `
            position: fixed;
            bottom: 110px;
            right: 28px;
            width: 42px;
            height: 42px;
            border-radius: 50%;
            background: rgba(28,28,26,0.92);
            backdrop-filter: blur(8px);
            color: #fff;
            border: 1px solid rgba(255,255,255,0.15);
            font-size: 18px;
            line-height: 1;
            box-shadow: 0 4px 14px rgba(0,0,0,0.25);
            cursor: pointer;
            z-index: 999999;
            display: none;
            align-items: center;
            justify-content: center;
            transition: opacity 0.2s, transform 0.15s;
        `;
        btn.onmouseover = () => btn.style.transform = 'scale(1.08)';
        btn.onmouseout  = () => btn.style.transform = 'scale(1)';
        doc.body.appendChild(btn);

        const showBtn = show => { btn.style.display = show ? 'flex' : 'none'; };

        // ── Core scroll helper ────────────────────────────────────────────────
        const scrollToBottom = (chatBox, instant) => {
            chatBox.scrollTo({
                top: chatBox.scrollHeight,
                behavior: instant ? 'instant' : 'smooth'
            });
        };

        // ── State ─────────────────────────────────────────────────────────────
        let userScrolledUp = false;
        let throttle = null;

        const setup = (chatBox) => {
            // Scroll listener — detect if user has scrolled up
            chatBox.addEventListener('scroll', () => {
                const distFromBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight;
                if (distFromBottom > 80) {
                    userScrolledUp = true;
                    showBtn(true);
                } else {
                    userScrolledUp = false;
                    showBtn(false);
                }
            });

            // Button click — jump to bottom and re-engage auto-scroll
            btn.onclick = () => {
                userScrolledUp = false;
                showBtn(false);
                scrollToBottom(chatBox, false);
            };

            // MutationObserver — watch chat content for new elements
            let lastH = chatBox.scrollHeight;
            const observer = new MutationObserver(() => {
                const newH = chatBox.scrollHeight;
                if (newH <= lastH) return;
                lastH = newH;

                if (userScrolledUp) {
                    // Don't steal scroll — just ensure button is visible
                    showBtn(true);
                    return;
                }

                // Throttle to avoid per-token jitter during streaming
                if (!throttle) {
                    throttle = setTimeout(() => {
                        scrollToBottom(chatBox, false);
                        throttle = null;
                    }, 80);
                }
            });

            observer.observe(chatBox, { childList: true, subtree: true, characterData: true });

            // Jump to bottom immediately when page loads
            scrollToBottom(chatBox, true);
        };

        // ── Bootstrap (retry until chatbox is in DOM) ─────────────────────────
        let attempts = 0;
        const trySetup = setInterval(() => {
            const chatBox = findChatBox();
            if (chatBox) {
                clearInterval(trySetup);
                setup(chatBox);
            }
            if (++attempts > 20) clearInterval(trySetup);
        }, 300);

    })();
    </script>
    """, height=0, width=0)

def scroll_question_into_view():
    """Called once when the user submits a question.
    Scrolls the chat box so the latest user bubble is at the TOP of the box,
    then the answer streams in below it — standard chatbot behaviour."""
    components.html("""
    <script>
    (function() {
        const doc = window.parent.document;

        const findChatBox = () => {
            let el = doc.querySelector('[style*="height: 520px"][style*="overflow"]');
            if (el) return el;
            return Array.from(doc.querySelectorAll('div')).find(d => {
                const s = window.parent.getComputedStyle(d);
                return (s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                       d.clientHeight > 380 && d.clientHeight < 620;
            }) || null;
        };

        const run = () => {
            const chatBox = findChatBox();
            if (!chatBox) return;
            // Find the last user bubble inside this specific chatBox
            const userBubbles = chatBox.querySelectorAll('.chat-user');
            if (userBubbles.length === 0) {
                // Fallback: just scroll to bottom
                chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
                return;
            }
            const latest = userBubbles[userBubbles.length - 1];
            // Calculate relative distance between the message and the top of the chat box
            const containerRect = chatBox.getBoundingClientRect();
            const latestRect = latest.getBoundingClientRect();
            
            chatBox.scrollBy({
                top: latestRect.top - containerRect.top - 12,
                behavior: 'smooth'
            });
        };

        // Small delay so the DOM has painted the new user message
        setTimeout(run, 120);
    })();
    </script>
    """, height=0, width=0)




# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; }

:root {
    --bg-primary: #FAFAF8;
    --bg-surface: #FFFFFF;
    --bg-subtle: #F4F3F0;
    --bg-muted: #ECEAE5;
    --border-default: #E5E3DD;
    --border-strong: #D4D1CA;
    --text-primary: #1C1C1A;
    --text-secondary: #6B6A65;
    --text-muted: #9E9D98;
    --text-faint: #B8B7B2;
    --accent: #2D2D2B;
    --accent-hover: #444442;
    --success: #2F8132;
    --success-bg: #EBF5EB;
    --warning: #B45309;
    --warning-bg: #FEF6E7;
    --danger: #C53030;
    --danger-bg: #FEE8E7;
    --info: #1A6DB0;
    --info-bg: #E8F1FA;
    --radius-sm: 5px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 2px 8px rgba(0,0,0,0.06);
    --transition-fast: 0.12s ease;
    --transition-normal: 0.2s ease;
}

html, body, .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border-default) !important;
    padding-top: 0 !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.25rem;
}

/* ── Header ── */
header[data-testid="stHeader"] {
    background: rgba(250, 250, 248, 0.65) !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
    border-bottom: 1px solid rgba(229, 227, 221, 0.5) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--border-default) !important;
    gap: 0 !important;
    padding: 0 !important;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--text-muted) !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.84rem !important;
    padding: 10px 22px !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    transition: color var(--transition-fast), border-color var(--transition-fast) !important;
    letter-spacing: -0.01em !important;
}

.stTabs [aria-selected="true"] {
    color: var(--text-primary) !important;
    border-bottom: 2px solid var(--text-primary) !important;
    background: transparent !important;
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--text-secondary) !important;
    background: transparent !important;
}

.stTabs [data-baseweb="tab-panel"] {
    padding-top: 1.5rem !important;
}

/* ── Cards ── */
.card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow-sm);
    transition: box-shadow var(--transition-normal);
}

.card:hover {
    box-shadow: var(--shadow-md);
}

/* ── Chat bubbles ── */
.chat-user {
    display: flex;
    justify-content: flex-end;
    margin: 14px 0;
}

.chat-user-bubble {
    background: var(--accent);
    color: #FAFAF8;
    padding: 11px 16px;
    border-radius: 16px 16px 4px 16px;
    max-width: 68%;
    font-size: 0.875rem;
    line-height: 1.6;
    font-weight: 400;
    box-shadow: var(--shadow-sm);
}

.chat-system {
    display: flex;
    justify-content: flex-start;
    margin: 14px 0;
}

.chat-system-bubble {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    color: var(--text-primary);
    padding: 14px 18px;
    border-radius: 16px 16px 16px 4px;
    max-width: 78%;
    font-size: 0.875rem;
    line-height: 1.65;
    box-shadow: var(--shadow-sm);
}

.chat-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--text-faint);
    margin-top: 5px;
    margin-left: 4px;
    letter-spacing: 0.01em;
}

/* ── Source chips ── */
.source-chip {
    display: inline-flex;
    align-items: center;
    background: var(--bg-subtle);
    border: 1px solid var(--border-default);
    color: var(--text-secondary);
    border-radius: var(--radius-sm);
    padding: 3px 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    margin: 2px 4px 2px 0;
    font-weight: 500;
    transition: background var(--transition-fast), border-color var(--transition-fast);
}

.source-chip:hover {
    background: var(--bg-muted);
    border-color: var(--border-strong);
}

/* ── Severity badges ── */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 9px;
    border-radius: var(--radius-sm);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
}

.badge-critical { background: var(--danger-bg); color: var(--danger); }
.badge-high     { background: var(--warning-bg); color: var(--warning); }
.badge-medium   { background: #FFFBEB; color: #92400E; }
.badge-low      { background: var(--success-bg); color: var(--success); }

/* ── Buttons ── */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.84rem !important;
    border-radius: var(--radius-md) !important;
    transition: all var(--transition-fast) !important;
    letter-spacing: -0.01em !important;
}

.stButton > button[kind="primary"] {
    background: var(--accent) !important;
    border: 1px solid var(--accent) !important;
    color: #FFFFFF !important;
}

.stButton > button[kind="primary"]:hover {
    background: var(--accent-hover) !important;
    border-color: var(--accent-hover) !important;
    box-shadow: var(--shadow-md) !important;
}

.stButton > button[kind="secondary"],
.stButton > button:not([kind]) {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-strong) !important;
    color: var(--text-primary) !important;
}

.stButton > button[kind="secondary"]:hover,
.stButton > button:not([kind]):hover {
    border-color: var(--accent) !important;
    background: var(--bg-subtle) !important;
}

/* ── Inputs ── */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    font-family: 'Inter', sans-serif !important;
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-size: 0.875rem !important;
    transition: border-color var(--transition-fast) !important;
}

.stTextInput input:focus,
.stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(45,45,43,0.08) !important;
}

.stSelectbox > div > div {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
}

/* ── Chat Input ── */
[data-testid="stChatInput"] {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: 10px !important;
    box-shadow: var(--shadow-sm) !important;
    transition: border-color var(--transition-fast), box-shadow var(--transition-fast) !important;
}

[data-testid="stChatInput"]:focus-within {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(45,45,43,0.08) !important;
}

[data-testid="stChatInput"] textarea {
    font-family: 'Inter', sans-serif !important;
    color: var(--text-primary) !important;
    background: transparent !important;
    font-size: 0.875rem !important;
}

[data-testid="stChatInput"] button {
    color: var(--text-primary) !important;
}

/* ── Slider ── */
.stSlider [data-baseweb="slider"] [role="slider"] {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.84rem !important;
    color: var(--text-primary) !important;
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-md) !important;
}

/* ── Labels & Text ── */
.stMarkdown p, .stMarkdown li,
.stCheckbox label, .stRadio label,
.stSelectbox label, .stSlider label,
.stNumberInput label, label {
    color: var(--text-primary) !important;
    font-family: 'Inter', sans-serif !important;
}

.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.025em !important;
}

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: var(--accent) !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: var(--bg-surface) !important;
    border: 1px dashed var(--border-strong) !important;
    border-radius: var(--radius-md) !important;
    transition: border-color var(--transition-fast) !important;
}

[data-testid="stFileUploader"]:hover {
    border-color: var(--accent) !important;
}

/* ── Progress ── */
.stProgress > div > div > div {
    background: var(--accent) !important;
    border-radius: 4px !important;
}

/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid var(--border-default) !important;
}

/* ── Info / Success / Error ── */
.stAlert {
    border-radius: var(--radius-md) !important;
    border: 1px solid !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.84rem !important;
}

/* ── Code blocks ── */
.stCodeBlock {
    border-radius: var(--radius-md) !important;
}

code {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
}

/* ── Hide Streamlit chrome ── */
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }

/* ── Custom component styling ── */
.section-label {
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 8px;
}

.stat-card {
    background: var(--bg-subtle);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 12px 14px;
}

.stat-label {
    font-size: 0.68rem;
    color: var(--text-muted);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.stat-value {
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-top: 2px;
    font-variant-numeric: tabular-nums;
}

.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 400px;
    color: var(--text-muted);
    font-family: 'Inter', sans-serif;
}

.empty-state-title {
    font-size: 1rem;
    font-weight: 500;
    color: var(--text-secondary);
}

.empty-state-subtitle {
    font-size: 0.82rem;
    margin-top: 6px;
    color: var(--text-muted);
}

.doc-status-dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
}

/* ── Typing Indicator ── */
.typing-indicator {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 8px 12px;
    background: var(--bg-subtle);
    border-radius: var(--radius-md);
    width: fit-content;
    border: 1px solid var(--border-default);
}
.typing-indicator .dot {
    width: 6px;
    height: 6px;
    background: var(--text-muted);
    border-radius: 50%;
    animation: typing 1.4s infinite ease-in-out both;
}
.typing-indicator .dot:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator .dot:nth-child(2) { animation-delay: -0.16s; }
@keyframes typing {
    0%, 80%, 100% { transform: scale(0); opacity: 0; }
    40% { transform: scale(1); opacity: 1; }
}
</style>
""", unsafe_allow_html=True)

# Inject chat scroll (auto-scroll + Go-to-bottom button)
inject_chat_scroll()

# ── State initialization ──────────────────────────────────────────────────────
HISTORY_FILE = Path("logs/chat_history.json")
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_chat_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        with portalocker.Lock(HISTORY_FILE, 'r', timeout=2) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_chat_history(history):
    history = history[-100:]  # Cap at 100 messages
    try:
        with portalocker.Lock(HISTORY_FILE, 'w', timeout=2) as f:
            json.dump(history, f)
    except Exception as e:
        print(f"Failed to save history: {e}")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = load_chat_history()
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "total_tokens" not in st.session_state:
    st.session_state.total_tokens = sum(msg.get("tokens", 0) for msg in st.session_state.chat_history)
if "total_queries" not in st.session_state:
    # only count user messages as queries
    st.session_state.total_queries = sum(1 for msg in st.session_state.chat_history if msg["role"] == "user")
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "preview_chunk" not in st.session_state:
    st.session_state.preview_chunk = None


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # Brand
    st.markdown("""
    <div style="padding: 0.25rem 0 1.25rem 0; border-bottom: 1px solid #E5E3DD; margin-bottom: 1.25rem;">
        <div style="font-family: 'Inter', sans-serif; font-size: 1.3rem; font-weight: 700;
                    color: #1C1C1A; letter-spacing: -0.04em; line-height: 1.2;">
            ◆ MADIS
        </div>
        <div style="font-family: 'Inter', sans-serif; font-size: 0.75rem;
                    color: #9E9D98; margin-top: 4px; font-weight: 400; letter-spacing: -0.01em;">
            Document Intelligence System
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Hardware Telemetry via JS fetch
    monitor_html = f"""
    <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: transparent; }}
    .hw-card {{
        background: #F4F3F0;
        border: 1px solid #E5E3DD;
        border-radius: 8px;
        padding: 10px 13px;
        margin-bottom: 7px;
    }}
    .hw-label {{
        font-size: 0.68rem;
        font-weight: 600;
        color: #9E9D98;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 5px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .hw-value {{
        font-size: 0.82rem;
        font-weight: 600;
        color: #1C1C1A;
        font-variant-numeric: tabular-nums;
    }}
    .hw-bar-track {{
        background: #E5E3DD;
        height: 3px;
        border-radius: 2px;
        margin-top: 5px;
        overflow: hidden;
    }}
    .hw-bar {{
        height: 100%;
        border-radius: 2px;
        transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    .hw-sub {{
        display: flex;
        justify-content: space-between;
        font-size: 0.68rem;
        color: #9E9D98;
        margin-top: 3px;
        font-variant-numeric: tabular-nums;
    }}
    </style>

    <div class="hw-card">
        <div class="hw-label">
            <span>CPU</span>
            <span id="cpu-val" class="hw-value">—</span>
        </div>
        <div class="hw-bar-track">
            <div id="cpu-bar" class="hw-bar" style="width:0%; background:#2D2D2B;"></div>
        </div>
    </div>

    <div class="hw-card">
        <div class="hw-label">
            <span>Memory</span>
            <span id="ram-val" class="hw-value">—</span>
        </div>
        <div class="hw-bar-track">
            <div id="ram-bar" class="hw-bar" style="width:0%; background:#6B6A65;"></div>
        </div>
    </div>

    <div class="hw-card">
        <div class="hw-label">
            <span>GPU</span>
            <span id="gpu-util" class="hw-value">—</span>
        </div>
        <div class="hw-sub">
            <span id="gpu-temp">—</span>
            <span id="gpu-mem">—</span>
        </div>
        <div class="hw-bar-track">
            <div id="gpu-bar" class="hw-bar" style="width:0%; background:#444442;"></div>
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
                bar.style.background = vp > 90 ? '#C53030' : vp > 70 ? '#B45309' : '#444442';
            }} else {{
                document.getElementById('gpu-util').innerText = 'N/A';
            }}
        }} catch(e) {{}}
    }}
    fetchStats();
    setInterval(fetchStats, 3000);
    </script>
    """

    st.markdown('<div class="section-label">System</div>', unsafe_allow_html=True)
    components.html(monitor_html, height=185)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Session</div>', unsafe_allow_html=True)

    col_t, col_q = st.columns(2)
    with col_t:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">Tokens</div>
            <div class="stat-value">{st.session_state.total_tokens:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_q:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">Queries</div>
            <div class="stat-value">{st.session_state.total_queries}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Retrieval</div>', unsafe_allow_html=True)
    top_k = st.slider("Vector depth", 1, 15, 5,
                      help="Number of semantic chunks fetched from Qdrant.",
                      label_visibility="collapsed")
    st.caption(f"Retrieving top {top_k} chunks")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.divider()
    if st.button("Reset session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.chat_history = []
        st.session_state.total_tokens = 0
        st.session_state.total_queries = 0
        st.rerun()
    if st.button("Clear history", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.total_tokens = 0
        st.session_state.total_queries = 0
        try:
            HISTORY_FILE.unlink(missing_ok=True)
        except Exception:
            pass
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
            <div class="empty-state">
                <div class="empty-state-title">
                    Ready when you are
                </div>
                <div class="empty-state-subtitle">
                    Select a document scope above, then ask your question below.
                </div>
            </div>
            """, unsafe_allow_html=True)

        for i, msg in enumerate(st.session_state.chat_history):
            if msg["role"] == "user":
                st.markdown(
                    f'<div class="chat-user"><div class="chat-user-bubble">{msg["content"]}</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="chat-system"><div class="chat-system-bubble">{msg["content"]}</div></div>',
                    unsafe_allow_html=True,
                )

                render_metadata_footer(msg, i)

    user_input = st.chat_input("Ask something about your documents...")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        st.session_state.total_queries += 1   # pre-increment sidebar counter
        st.session_state.stop_requested = False
        st.rerun()

    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
        user_input = st.session_state.chat_history[-1]["content"]
        doc_id = doc_options.get(selected_doc) if selected_doc != "All documents" else None
        payload = {
            "question":   user_input,
            "top_k":      top_k,
            "session_id": st.session_state.session_id,
            "stream":     True,
        }
        if doc_id:
            payload["document_id"] = doc_id

        content_so_far = ""
        got_first_token = False
        final_res: dict = {}
        timed_out = False
        was_stopped = False

        with chat_container:
            # ── JS-Integrated Stop Button (hijacks chat_input) ──
            stop_ph = st.empty()
            with stop_ph:
                st.markdown("<style>div[data-testid='stButton']:has(button p:contains('hidden_stop')) { display: none; }</style>", unsafe_allow_html=True)
                if st.button("hidden_stop", key="stop_generation"):
                    st.session_state.stop_requested = True
                    
                components.html("""
                <script>
                const doc = window.parent.document;
                
                // Transform the chat_input button to stop button
                const chatInputBtn = doc.querySelector('div[data-testid="stChatInput"] button');
                if (chatInputBtn) {
                    if (!chatInputBtn.dataset.origHtml) {
                        chatInputBtn.dataset.origHtml = chatInputBtn.innerHTML;
                    }
                    chatInputBtn.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M6 6h12v12H6z"></path></svg>';
                    chatInputBtn.style.color = '#C53030';
                    chatInputBtn.disabled = false;
                    
                    chatInputBtn.onclick = function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        const hiddenBtns = doc.querySelectorAll('div[data-testid="stButton"] button');
                        for (let btn of hiddenBtns) {
                            if (btn.innerText.includes('hidden_stop')) {
                                btn.click();
                                break;
                            }
                        }
                    };
                }
                </script>
                """, height=0, width=0)

            # Scroll the latest user question to the top of the chat box
            scroll_question_into_view()

            phase_ph   = st.empty()   # phase status line (above content)
            content_ph = st.empty()   # typing indicator → streamed text

            # Typing indicator — shown until first real token arrives
            content_ph.markdown(
                '<div class="typing-indicator">'
                '<span class="dot"></span><span class="dot"></span><span class="dot"></span>'
                '</div>',
                unsafe_allow_html=True,
            )

            try:
                try:
                    r = requests.post(
                        f"{API_BASE}/query/",
                        json=payload,
                        stream=True,
                        timeout=(30, 300),   # 30s connect, 300s read
                    )

                    if r.status_code != 200:
                        content_ph.markdown(f"**Error {r.status_code}:** {r.text[:200]}")
                    else:
                        last_evt = time.monotonic()

                        for raw_line in r.iter_lines():
                            # 1. Check stop flag on every iteration
                            if st.session_state.get("stop_requested"):
                                r.close()
                                content_so_far = (content_so_far or "") + " [stopped]"
                                was_stopped = True
                                break

                            # 2. 30-second silence timeout
                            if time.monotonic() - last_evt > 30:
                                timed_out = True
                                phase_ph.markdown(
                                    '<div style="font-size:0.78rem;color:#B45309;padding:4px 0;">'
                                    '⚠️ Pipeline timeout — please retry.</div>',
                                    unsafe_allow_html=True,
                                )
                                break

                            if not raw_line:
                                continue

                            line_str = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                            if not line_str.startswith("data: "):
                                continue

                            last_evt = time.monotonic()

                            try:
                                data = json.loads(line_str[6:])
                            except Exception:
                                continue

                            ev_type = data.get("type")

                            if ev_type == "token":
                                token_content = data.get("content", "")

                                if token_content.startswith("__PHASE__:"):
                                    # Phase event — render as muted status line above content
                                    phase_ph.markdown(
                                        f'<div style="font-size:0.74rem;color:#9E9D98;'
                                        f'font-family:Inter,sans-serif;padding:2px 0 6px 0;'
                                        f'letter-spacing:-0.01em;">'
                                        f'<span style="display:inline-block;width:5px;height:5px;'
                                        f'border-radius:50%;background:#9E9D98;margin-right:7px;'
                                        f'vertical-align:middle;"></span>{token_content[10:]}</div>',
                                        unsafe_allow_html=True,
                                    )
                                else:
                                    # Real token — clear typing indicator, start streaming text
                                    if not got_first_token:
                                        got_first_token = True
                                        phase_ph.empty()
                                    content_so_far += token_content
                                    content_ph.markdown(content_so_far + " ▌")   # blinking cursor effect

                            elif ev_type == "done":
                                final_res = data.get("result", {})
                                content_ph.markdown(content_so_far)   # remove cursor
                                phase_ph.empty()

                            elif ev_type == "error":
                                content_ph.markdown(f"**Pipeline error:** {data.get('error', 'Unknown error')}")
                                break

                except requests.ConnectionError:
                    # ── Graceful fallback to non-streaming /query/ ──
                    try:
                        phase_ph.markdown(
                            '<div style="font-size:0.74rem;color:#9E9D98;padding:2px 0 6px 0;">'
                            'Streaming unavailable — falling back to standard mode…</div>',
                            unsafe_allow_html=True,
                        )
                        fallback = {k: v for k, v in payload.items() if k != "stream"}
                        r2 = requests.post(f"{API_BASE}/query/", json=fallback, timeout=300)
                        if r2.status_code == 200:
                            fdata = r2.json()
                            content_so_far = fdata.get("answer", "No answer returned.")
                            final_res = fdata
                            content_ph.markdown(content_so_far)
                            phase_ph.empty()
                        else:
                            content_ph.markdown(f"**Error {r2.status_code}:** {r2.text[:200]}")
                    except Exception as fallback_err:
                        content_ph.markdown(
                            f"Connection error — is the backend running? ({fallback_err})"
                        )

                except Exception as ex:
                    content_ph.markdown(f"Unexpected error: {ex}")
            finally:
                # Restore chat_input button
                with stop_ph:
                    components.html("""
                <script>
                const doc = window.parent.document;
                const chatInputBtn = doc.querySelector('div[data-testid="stChatInput"] button');
                if (chatInputBtn && chatInputBtn.dataset.origHtml) {
                    chatInputBtn.innerHTML = chatInputBtn.dataset.origHtml;
                    chatInputBtn.style.color = '';
                    chatInputBtn.onclick = null;
                }
                </script>
                """, height=0, width=0)

                # ── Append completed entry to history (no st.rerun — counters pre-incremented) ──
                # This finally block ensures that if the user clicks the native Stop button 
                # (which raises a StopException), the streamed text so far is still saved.
                if content_so_far or timed_out:
                    if timed_out and not content_so_far:
                        content_so_far = "Pipeline timeout — please retry."
                    est_tokens = max(1, len(content_so_far) // 4)
                    st.session_state.total_tokens += est_tokens
                    confidence = final_res.get("confidence") or "medium"
                    entry = {
                        "role":       "assistant",
                        "content":    content_so_far,
                        "sources":    final_res.get("sources", []),
                        "alerts":     final_res.get("alerts", []),
                        "latency_ms": final_res.get("latency_ms", 0),
                        "tokens":     est_tokens,
                        "confidence": confidence,
                        "timestamp":  time.time(),
                    }
                    st.session_state.chat_history.append(entry)
                    save_chat_history(st.session_state.chat_history)
                    
                    # Explicitly render the metadata for this generation immediately
                    # so the user doesn't have to wait for the next rerun.
                    render_metadata_footer(entry, len(st.session_state.chat_history) - 1)

    # ── Source chunk preview panel (renders below chat when a chip is clicked) ──
    if st.session_state.preview_chunk:
        chunk    = st.session_state.preview_chunk
        filename = (chunk.get("filename") or chunk.get("document_id") or "")[:55]
        page     = chunk.get("page_number") or "?"
        score    = chunk.get("score", 0.0)
        text     = chunk.get("text", "No text available.")

        hdr_col, close_col = st.columns([9, 1])
        with hdr_col:
            st.markdown(
                f'<div style="font-size:0.72rem;font-weight:600;color:#9E9D98;'
                f'text-transform:uppercase;letter-spacing:0.06em;padding:10px 0 4px 0;">'
                f'Source preview · {filename} · p.{page} · score {score:.4f}</div>',
                unsafe_allow_html=True,
            )
        with close_col:
            if st.button("✕", key="close_preview"):
                st.session_state.preview_chunk = None
                st.rerun()
        st.markdown(
            f'<div style="border:1px solid #E5E3DD;border-radius:8px;background:#F4F3F0;'
            f'padding:14px 16px;max-height:200px;overflow-y:auto;'
            f'font-size:0.83rem;color:#1C1C1A;line-height:1.65;white-space:pre-wrap;'
            f'font-family:\'JetBrains Mono\',monospace;">{text}</div>',
            unsafe_allow_html=True,
        )



# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Documents
# ═══════════════════════════════════════════════════════════════════════════════
with tab_upload:
    col_up, col_list = st.columns([1, 1], gap="large")

    with col_up:
        st.markdown("#### Upload document")
        st.markdown(
            "<p style='color:#9E9D98; font-size:0.82rem; margin-top:-8px; letter-spacing:-0.01em;'>"
            "Documents are parsed, chunked, and embedded into the vector store.</p>",
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "Choose file",
            type=["pdf", "docx", "doc", "txt", "md", "html", "png", "jpg", "jpeg", "pptx", "xlsx"],
            label_visibility="collapsed",
        )

        if uploaded:
            file_size_kb = uploaded.size / 1024
            size_display = f"{file_size_kb:.1f} KB" if file_size_kb < 1024 else f"{file_size_kb / 1024:.1f} MB"
            st.markdown(
                f"<div style='font-size:0.82rem; color:#6B6A65; margin-bottom:10px; "
                f"padding:10px 14px; background:#F4F3F0; border:1px solid #E5E3DD; border-radius:8px;'>"
                f"<strong>{uploaded.name}</strong>"
                f"<span style='color:#9E9D98; margin-left:10px;'>{size_display}</span></div>",
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
                                    eta_str = "wrapping up..."

                                if job_status == "completed":
                                    prog.progress(1.0, text="Completed — 100%")
                                    time.sleep(0.5)
                                    st.rerun()
                                    break
                                elif job_status == "failed":
                                    prog.progress(1.0, text="Failed")
                                    st.error(error_msg)
                                    break
                                else:
                                    prog.progress(
                                        progress_val,
                                        text=f"{job_status.capitalize()} — {pct}% · ETA ~{eta_str}"
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
            st.info("No documents indexed yet. Upload one to get started.")
        else:
            STATUS_COLOR = {
                "completed": "#2F8132", "failed": "#C53030",
                "processing": "#B45309", "pending": "#9E9D98",
            }
            for doc in docs[:20]:
                status = doc.get("status", "")
                color = STATUS_COLOR.get(status, "#9E9D98")
                with st.expander(
                    f"{doc['filename']}",
                    expanded=False,
                ):
                    st.markdown(
                        f"<span class='doc-status-dot' style='background:{color};'></span>"
                        f"<span style='color:{color}; font-size:0.75rem; font-weight:600; "
                        f"letter-spacing:0.04em;'>"
                        f"{status.upper()}</span>",
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
    st.markdown(
        "<p style='color:#9E9D98; font-size:0.82rem; margin-top:-8px; letter-spacing:-0.01em;'>"
        "Cross-document differential analysis powered by multi-agent reasoning.</p>",
        unsafe_allow_html=True,
    )

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
                "<div style='text-align:center; padding-top:30px; color:#B8B7B2; "
                "font-size:0.78rem; font-weight:500; letter-spacing:0.04em;'>vs</div>",
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
            with st.spinner("Running differential analysis — this typically takes 30–90 seconds…"):
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
                    f"<div style='font-size:0.72rem; color:#B8B7B2; text-align:right; "
                    f"margin-bottom:12px; font-family:\"JetBrains Mono\",monospace;'>"
                    f"Completed in {cmp['latency_ms'] / 1000:.2f}s</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("**Summary**")
            st.markdown(
                f'<div class="card" style="color:#1C1C1A; font-size:0.875rem; line-height:1.65;">'
                f'{cmp.get("summary", "No summary generated.")}</div>',
                unsafe_allow_html=True,
            )

            col_sim, col_diff = st.columns(2, gap="large")
            with col_sim:
                st.markdown("**Similarities**")
                for s in cmp.get("similarities", []):
                    st.markdown(
                        f'<div style="display:flex; gap:8px; margin-bottom:6px; '
                        f'font-size:0.84rem; color:#1C1C1A; line-height:1.5;">'
                        f'<span style="color:#B8B7B2; flex-shrink:0;">—</span>{s}</div>',
                        unsafe_allow_html=True,
                    )

            with col_diff:
                st.markdown("**Differences**")
                for d in cmp.get("differences", []):
                    aspect = d.get("aspect", "Unknown")
                    st.markdown(
                        f'<div style="margin-bottom:16px;">'
                        f'<div style="font-size:0.72rem; font-weight:600; color:#9E9D98; '
                        f'text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">{aspect}</div>'
                        f'<div style="background:#F4F3F0; border-left:2px solid #D4D1CA; '
                        f'padding:8px 12px; border-radius:0 6px 6px 0; font-size:0.82rem; '
                        f'color:#1C1C1A; margin-bottom:4px; line-height:1.5;">'
                        f'<strong style="color:#6B6A65;">A:</strong> {d.get("doc_a","")}</div>'
                        f'<div style="background:#F4F3F0; border-left:2px solid #2D2D2B; '
                        f'padding:8px 12px; border-radius:0 6px 6px 0; font-size:0.82rem; '
                        f'color:#1C1C1A; line-height:1.5;">'
                        f'<strong style="color:#6B6A65;">B:</strong> {d.get("doc_b","")}</div>'
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
    st.markdown(
        "<p style='color:#9E9D98; font-size:0.82rem; margin-top:-8px; letter-spacing:-0.01em;'>"
        "Flagged anomalies, contradictions, and compliance violations.</p>",
        unsafe_allow_html=True,
    )

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
            border = {"critical": "#C53030", "high": "#B45309",
                      "medium": "#92400E", "low": "#2F8132"}.get(sev, "#92400E")
            badge_bg = {"critical": "#FEE8E7", "high": "#FEF6E7",
                        "medium": "#FFFBEB", "low": "#EBF5EB"}.get(sev, "#FFFBEB")
            created = alert.get("created_at", "")[:16].replace("T", "  ")

            st.markdown(f"""
            <div style="background:#FFFFFF; border:1px solid #E5E3DD;
                        border-left:3px solid {border}; border-radius:8px;
                        padding:14px 18px; margin-bottom:10px; box-shadow:0 1px 2px rgba(0,0,0,0.04);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="background:{badge_bg}; color:{border}; padding:2px 9px;
                                     border-radius:5px; font-size:0.68rem; font-weight:600;
                                     font-family:'JetBrains Mono',monospace; text-transform:uppercase;
                                     letter-spacing:0.04em;">{sev}</span>
                        <span style="font-size:0.8rem; font-weight:600; color:#6B6A65;
                                     letter-spacing:0.02em;">{atype}</span>
                    </div>
                    <span style="font-family:'JetBrains Mono',monospace; font-size:0.7rem;
                                 color:#B8B7B2;">{created}</span>
                </div>
                <div style="font-size:0.84rem; color:#1C1C1A; margin-bottom:10px; line-height:1.55;">
                    {alert.get('message','')}
                </div>
                <div style="font-family:'JetBrains Mono',monospace; font-size:0.72rem; color:#6B6A65;
                            background:#F4F3F0; padding:10px 13px; border-radius:6px;
                            border:1px solid #E5E3DD; white-space:pre-wrap; line-height:1.5;">
{alert.get('context','No trace data available')}</div>
            </div>
            """, unsafe_allow_html=True)