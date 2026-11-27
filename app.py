import html
import io
import os
import time

import streamlit as st
from google import genai
from google.genai import types
from pypdf import PdfReader

# If one model is busy, the next one is tried
MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.1-flash-lite"]

FILE_TYPES = {
    "pdf": {"pdf": "application/pdf"},
    "image": {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "heic": "image/heic",
        "heif": "image/heif",
    },
    "video": {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "webm": "video/webm",
        "avi": "video/x-msvideo",
    },
    "audio": {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "aac": "audio/aac",
    },
}
ICONS = {"pdf": "📄", "image": "🖼️", "video": "🎬", "audio": "🎧"}
ALL_EXTENSIONS = [ext for group in FILE_TYPES.values() for ext in group]
INLINE_LIMIT = 8 * 1024 * 1024  # files up to this size are sent directly (fast)
INLINE_TOTAL_LIMIT = 14 * 1024 * 1024  # Gemini limits one request's size, so cap the total sent directly
PAGES = ["💬 Ask Questions", "📝 Summarize", "🎯 Quiz"]
AVATARS = {"user": "🎓", "assistant": "🤖"}

st.set_page_config(
    page_title="AI Study Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Styling ----------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, .stApp, .stMarkdown p, .stMarkdown li, h1, h2, h3, h4, input, textarea {
    font-family: 'Inter', sans-serif !important;
}
footer, [data-testid="stAppDeployButton"] {display: none;}
.block-container {padding-top: 1.6rem; padding-bottom: 6rem; max-width: 1150px;}

/* Hero */
.hero {
    background: radial-gradient(circle at 85% 20%, rgba(167,139,250,0.35), transparent 45%),
                linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #3730a3 100%);
    border-radius: 20px;
    padding: 2.2rem 2.4rem;
    margin-bottom: 1.4rem;
    box-shadow: 0 18px 40px -18px rgba(30, 27, 75, 0.55);
}
.hero.compact {padding: 1.3rem 1.8rem;}
.hero-badge {
    display: inline-block;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.22);
    color: #e0e7ff;
    font-size: 0.78rem; font-weight: 600; letter-spacing: 0.02em;
    padding: 0.28rem 0.75rem; border-radius: 999px; margin-bottom: 0.8rem;
}
.hero h1 {color: #fff; font-size: 2.3rem; font-weight: 800; margin: 0; padding: 0; letter-spacing: -0.02em;}
.hero.compact h1 {font-size: 1.55rem;}
.hero p {color: #c7d2fe; font-size: 1.05rem; margin: 0.45rem 0 0; max-width: 640px;}
.hero.compact p {font-size: 0.95rem;}

/* Feature cards on the welcome screen */
.feature-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; margin: 0.4rem 0 1.4rem;}
.feature-card {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 1.3rem 1.3rem 1.1rem;
    transition: transform .15s ease, box-shadow .15s ease;
}
.feature-card:hover {transform: translateY(-3px); box-shadow: 0 12px 28px -14px rgba(79,70,229,0.35);}
.feature-icon {
    width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
    background: #eef2ff; font-size: 1.3rem; margin-bottom: 0.8rem;
}
.feature-card h4 {margin: 0 0 0.3rem; font-size: 1.05rem; font-weight: 700; color: #111827;}
.feature-card p {margin: 0; font-size: 0.9rem; color: #6b7280; line-height: 1.5;}

.format-row {display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; color: #6b7280; font-size: 0.88rem;}
.pill {background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 999px; padding: 0.25rem 0.7rem; font-weight: 500; color: #374151;}

/* Metric cards */
[data-testid="stMetric"] {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 0.9rem 1.1rem;
}
[data-testid="stMetricLabel"] p {font-size: 0.82rem; color: #6b7280; font-weight: 600;}
[data-testid="stMetricValue"] {font-size: 1.6rem; font-weight: 700; color: #111827;}

/* Sidebar */
[data-testid="stSidebar"] {background: #f8f9fc; border-right: 1px solid #e5e7eb;}
.brand {display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.3rem;}
.brand-logo {
    width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #4f46e5, #7c3aed); font-size: 1.25rem;
}
.brand-name {font-weight: 800; font-size: 1.1rem; color: #111827; line-height: 1.1;}
.brand-sub {font-size: 0.78rem; color: #6b7280;}
.section-label {font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #9ca3af; margin: 0.6rem 0 0.4rem;}
.file-item {
    display: flex; align-items: center; gap: 0.6rem; background: #fff; border: 1px solid #e5e7eb;
    border-radius: 10px; padding: 0.5rem 0.7rem; margin-bottom: 0.4rem;
}
.file-icon {font-size: 1.1rem;}
.file-name {font-size: 0.85rem; font-weight: 600; color: #111827; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.file-meta {font-size: 0.74rem; color: #6b7280;}
.file-text {min-width: 0;}
.credit {font-size: 0.8rem; color: #6b7280; margin-top: 1rem;}
.credit a {color: #4f46e5; font-weight: 600; text-decoration: none;}

/* Buttons */
.stButton > button, .stDownloadButton > button {border-radius: 10px; font-weight: 600;}

/* Chat */
[data-testid="stChatMessage"] {
    background: #fff; border: 1px solid #eef0f4; border-radius: 16px; padding: 0.9rem 1.1rem; margin-bottom: 0.6rem;
}
.empty-chat {text-align: center; padding: 2rem 1rem 1rem; color: #6b7280;}
.empty-chat h3 {color: #111827; font-weight: 700; margin-bottom: 0.2rem;}
</style>
""",
    unsafe_allow_html=True,
)

try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error('Add GEMINI_API_KEY = "your-key" in .streamlit/secrets.toml')
    st.stop()


# ---------- Gemini helpers ----------
def stream_gemini(prompt, media=None, show=True):
    """Send the prompt plus any media to Gemini. Streams the answer on screen if show=True."""
    contents = [prompt] + (media or [])
    last_error = None
    for attempt in range(2):
        for model in MODELS:
            placeholder = st.empty() if show else None
            full_text = ""
            try:
                for chunk in client.models.generate_content_stream(
                    model=model, contents=contents
                ):
                    if chunk.text:
                        full_text += chunk.text
                        if placeholder:
                            placeholder.markdown(full_text + " ▌")
                if full_text:
                    if placeholder:
                        placeholder.markdown(full_text)
                    return full_text
            except Exception as error:
                last_error = error
            if placeholder:
                placeholder.empty()
        if attempt == 0:
            time.sleep(2)
    st.error(f"Gemini error: {last_error}")
    return None


def upload_to_gemini(data, name, mime):
    """Upload a big file (PDF, video, audio, large image) and wait until Gemini has processed it."""
    gemini_file = client.files.upload(
        file=io.BytesIO(data),
        config=types.UploadFileConfig(mime_type=mime, display_name=name),
    )
    waited = 0
    while getattr(gemini_file.state, "name", "") == "PROCESSING":
        if waited > 300:
            raise TimeoutError("Gemini took too long to process this file.")
        time.sleep(3)
        waited += 3
        gemini_file = client.files.get(name=gemini_file.name)
    if getattr(gemini_file.state, "name", "") == "FAILED":
        raise RuntimeError("Gemini could not process this file.")
    return gemini_file


# ---------- File reading ----------
def file_kind(name):
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    for kind, extensions in FILE_TYPES.items():
        if ext in extensions:
            return kind, extensions[ext]
    return None, None


def format_size(num_bytes):
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


@st.cache_data(show_spinner=False)
def count_pages(pdf_bytes):
    try:
        return len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        return 0


def load_files(uploaded_files):
    """Send every uploaded file to Gemini as a whole, so it can read all of it."""
    docs = []
    cache = st.session_state["media_cache"]
    labels = {"pdf": "PDF", "image": "Image", "video": "Video", "audio": "Audio"}
    inline_total = 0

    for file in uploaded_files:
        kind, mime = file_kind(file.name)
        if kind is None:
            continue
        data = file.getvalue()
        key = f"{file.name}-{file.size}"

        if key not in cache:
            try:
                fits = inline_total + len(data) <= INLINE_TOTAL_LIMIT
                if kind in ("pdf", "image") and len(data) <= INLINE_LIMIT and fits:
                    cache[key] = types.Part.from_bytes(data=data, mime_type=mime)
                else:
                    with st.spinner(f"Uploading {file.name}... (big files and videos can take a minute)"):
                        cache[key] = upload_to_gemini(data, file.name, mime)
            except Exception as error:
                st.error(f"Could not prepare {file.name}: {error}")
                continue

        if isinstance(cache[key], types.Part):
            inline_total += len(data)

        docs.append({
            "name": file.name,
            "kind": kind,
            "size": file.size,
            "pages": count_pages(data) if kind == "pdf" else 0,
            "media": [f"[{labels[kind]} file: {file.name}]", cache[key]],
        })
    return docs


# ---------- Session state ----------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("last_summary", "")
st.session_state.setdefault("last_quiz", "")
st.session_state.setdefault("media_cache", {})
st.session_state.setdefault("page", PAGES[0])


def start_over():
    st.session_state["messages"] = []
    st.session_state["last_summary"] = ""
    st.session_state["last_quiz"] = ""


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown(
        """
<div class="brand">
  <div class="brand-logo">📚</div>
  <div><div class="brand-name">Study Assistant</div><div class="brand-sub">AI-powered learning</div></div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.divider()

    uploaded_files = st.file_uploader(
        "Upload study materials",
        type=ALL_EXTENSIONS,
        accept_multiple_files=True,
        help="PDFs, images, videos and audio. You can select several files at once.",
    )

    docs = load_files(uploaded_files) if uploaded_files else []

    if docs:
        items = ""
        for doc in docs:
            meta = format_size(doc["size"])
            if doc["kind"] == "pdf":
                meta = f"{doc['pages']} pages · {meta}"
            items += f"""
<div class="file-item">
  <div class="file-icon">{ICONS[doc['kind']]}</div>
  <div class="file-text"><div class="file-name">{html.escape(doc['name'])}</div><div class="file-meta">{meta}</div></div>
</div>"""
        st.markdown(f'<div class="section-label">Your files ({len(docs)})</div>{items}', unsafe_allow_html=True)

        st.button("↺ Start over", on_click=start_over, width="stretch")

    st.markdown(
        '<div class="credit">Powered by Google Gemini</div>',
        unsafe_allow_html=True,
    )

# ---------- Welcome screen ----------
if not docs:
    st.markdown(
        """
<div class="hero">
  <div class="hero-badge">✨ Powered by Google Gemini</div>
  <h1>AI Study Assistant</h1>
  <p>Turn your lecture notes, slides, photos and recordings into answers, summaries and practice quizzes in seconds.</p>
</div>
<div class="feature-grid">
  <div class="feature-card"><div class="feature-icon">💬</div><h4>Ask anything</h4>
    <p>Chat with your study materials. Follow-up questions remember the conversation.</p></div>
  <div class="feature-card"><div class="feature-icon">📝</div><h4>Smart summaries</h4>
    <p>Short overviews, detailed notes or exam revision sheets, ready to download.</p></div>
  <div class="feature-card"><div class="feature-icon">🎯</div><h4>Practice quizzes</h4>
    <p>Multiple-choice questions at your chosen difficulty, with explained answers.</p></div>
</div>
<div class="format-row">Supported:
  <span class="pill">📄 PDF</span><span class="pill">🖼️ PNG · JPG · WEBP · HEIC</span>
  <span class="pill">🎬 MP4 · MOV · WEBM</span><span class="pill">🎧 MP3 · WAV</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write("")
    st.info("👈 Upload one or more files in the sidebar to get started.")
    st.stop()

# ---------- Main app ----------
media = [item for doc in docs for item in doc["media"]]

st.markdown(
    """
<div class="hero compact">
  <h1>AI Study Assistant</h1>
  <p>Ask questions, summarize and quiz yourself across all your uploaded files.</p>
</div>
""",
    unsafe_allow_html=True,
)

count = {kind: sum(1 for d in docs if d["kind"] == kind) for kind in ICONS}
col1, col2, col3, col4 = st.columns(4)
col1.metric("Files", len(docs))
col2.metric("PDF pages", sum(d["pages"] for d in docs))
col3.metric("Images", count["image"])
col4.metric("Videos & audio", count["video"] + count["audio"])
st.write("")

choice = st.segmented_control(
    "Feature", PAGES, default=st.session_state["page"], label_visibility="collapsed"
)
if choice:
    st.session_state["page"] = choice
page = st.session_state["page"]

# ---------- Ask Questions ----------
if page == PAGES[0]:
    messages = st.session_state["messages"]
    question = None

    if not messages:
        st.markdown(
            '<div class="empty-chat"><h3>What would you like to learn?</h3>'
            "<p>Ask a question below, or try one of these:</p></div>",
            unsafe_allow_html=True,
        )
        suggestions = [
            "What are the key ideas in these files?",
            "List the important definitions",
            "Explain the hardest topic simply",
        ]
        cols = st.columns(len(suggestions))
        for col, suggestion in zip(cols, suggestions):
            if col.button(suggestion, width="stretch"):
                question = suggestion
    else:
        top_left, top_right1, top_right2 = st.columns([4, 1, 1])
        chat_text = "\n\n".join(
            f"**{'You' if m['role'] == 'user' else 'Assistant'}:** {m['content']}" for m in messages
        )
        top_right1.download_button("⬇️ Save chat", chat_text, file_name="chat.md", width="stretch")
        if top_right2.button("🗑️ Clear", width="stretch"):
            st.session_state["messages"] = []
            st.rerun()

    for message in messages:
        with st.chat_message(message["role"], avatar=AVATARS[message["role"]]):
            st.markdown(message["content"])

    typed = st.chat_input("Ask anything about your files...")
    question = typed or question

    if question:
        with st.chat_message("user", avatar=AVATARS["user"]):
            st.markdown(question)

        history = "\n".join(
            f"{'Student' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in messages[-6:]
        )
        prompt = f"""You are a helpful study assistant.
Answer using ONLY the attached study files. Read every page of each PDF, including text,
tables, diagrams and scanned or handwritten pages, and also use any images, videos and audio.
Explain simply. If the answer is not in the files, say so.
When useful, mention which file (and page) the answer comes from.

CONVERSATION SO FAR:
{history or "(none)"}

QUESTION: {question}"""

        with st.chat_message("assistant", avatar=AVATARS["assistant"]):
            answer = stream_gemini(prompt, media)

        if answer:
            messages.append({"role": "user", "content": question})
            messages.append({"role": "assistant", "content": answer})
            st.rerun()

# ---------- Summarize ----------
elif page == PAGES[1]:
    style = st.radio(
        "Summary style", ["Short", "Detailed", "Exam revision sheet"], horizontal=True
    )
    clicked = st.button("✨ Generate summary", type="primary")

    if clicked:
        prompt = f"""Summarize ALL the attached study files: every page of each PDF, plus any images, videos or audio.
Style: {style}. Use headings and bullet points. Keep definitions and formulas.
If there are several files, cover each of them."""
        with st.container(border=True):
            summary = stream_gemini(prompt, media)
        if summary:
            st.session_state["last_summary"] = summary
    elif st.session_state["last_summary"]:
        with st.container(border=True):
            st.markdown(st.session_state["last_summary"])

    if st.session_state["last_summary"]:
        st.download_button(
            "⬇️ Download summary",
            st.session_state["last_summary"],
            file_name="summary.md",
            mime="text/markdown",
        )

# ---------- Quiz ----------
elif page == PAGES[2]:
    col1, col2 = st.columns(2)
    number = col1.slider("Number of questions", 3, 15, 5)
    difficulty = col2.selectbox("Difficulty", ["Easy", "Medium", "Hard"])

    if st.button("🎯 Generate quiz", type="primary"):
        prompt = f"""Create {number} {difficulty} multiple-choice questions
covering ALL the attached study files: every page of each PDF, plus any images, videos or audio.
Spread the questions across all the files and topics.
Number each question in bold, and put options A to D on separate lines.
Write the line ###ANSWERS### and then the answers with short explanations."""
        with st.spinner("Creating your quiz..."):
            quiz = stream_gemini(prompt, media, show=False)
        if quiz:
            st.session_state["last_quiz"] = quiz

    if st.session_state["last_quiz"]:
        questions, _, answers = st.session_state["last_quiz"].partition("###ANSWERS###")
        with st.container(border=True):
            st.markdown(questions)
        if answers:
            with st.expander("✅ Show answers"):
                st.markdown(answers)
