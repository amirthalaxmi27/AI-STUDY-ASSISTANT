import io
import time

import pypdfium2 as pdfium
import streamlit as st
from google import genai
from PIL import Image
from pypdf import PdfReader

# If one model is busy, the next one is tried
MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.1-flash-lite"]

st.set_page_config(
    page_title="AI Study Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Custom styling ----------
st.markdown(
    """
<style>
/* Hide Streamlit branding */
footer, [data-testid="stAppDeployButton"] {display: none;}
.block-container {padding-top: 2rem; max-width: 1100px;}

/* Header banner */
.hero {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
    padding: 1.8rem 2.2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    box-shadow: 0 8px 24px rgba(79, 70, 229, 0.25);
}
.hero h1 {color: #ffffff; margin: 0; font-size: 2rem; font-weight: 700;}
.hero p {color: rgba(255,255,255,0.88); margin: 0.4rem 0 0; font-size: 1.05rem;}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {gap: 6px;}
.stTabs [data-baseweb="tab"] {
    height: 46px; padding: 0 20px; font-weight: 600;
    border-radius: 10px 10px 0 0;
}

/* Buttons */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 10px; font-weight: 600; padding: 0.5rem 1.2rem;
}

/* Sidebar */
[data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,0.15);}
[data-testid="stMetricValue"] {font-size: 1.4rem;}
</style>
""",
    unsafe_allow_html=True,
)

try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error('Add GEMINI_API_KEY = "your-key" in .streamlit/secrets.toml')
    st.stop()


def stream_gemini(prompt, images=None):
    contents = [prompt] + (images or [])
    last_error = None
    for attempt in range(2):
        for model in MODELS:
            try:
                placeholder = st.empty()
                full_text = ""
                for chunk in client.models.generate_content_stream(
                    model=model, contents=contents
                ):
                    if chunk.text:
                        full_text += chunk.text
                        placeholder.markdown(full_text)
                if full_text:
                    placeholder.empty()
                    return full_text
            except Exception as error:
                last_error = error
        if attempt == 0:
            time.sleep(2)
    st.error(f"Gemini error: {last_error}")
    return None


@st.cache_data(show_spinner="Reading your PDF...")
def read_pdf(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text_parts = []
    scan_indices = []

    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if len(text) >= 30:
            text_parts.append(text)
        else:
            scan_indices.append(i)

    images = []
    if scan_indices:
        pdf_doc = pdfium.PdfDocument(pdf_bytes)
        for i in scan_indices[:5]:
            bitmap = pdf_doc[i].render(scale=1.0)
            pil_img: Image.Image = bitmap.to_pil()
            images.append(pil_img)

    return "\n".join(text_parts), images, len(reader.pages), len(scan_indices)


def reset_results():
    st.session_state["chat"] = []
    st.session_state["last_summary"] = ""
    st.session_state["last_quiz"] = ""


st.session_state.setdefault("chat", [])
st.session_state.setdefault("last_summary", "")
st.session_state.setdefault("last_quiz", "")
st.session_state.setdefault("current_file", None)

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("## 📚 Study Assistant")
    st.caption("Your AI-powered study companion")
    st.divider()

    uploaded_file = st.file_uploader("Upload your notes", type=["pdf"])

    pdf_text, pdf_images = "", []
    if uploaded_file is not None:
        # Start fresh when a different PDF is uploaded
        file_key = f"{uploaded_file.name}-{uploaded_file.size}"
        if st.session_state["current_file"] != file_key:
            reset_results()
            st.session_state["current_file"] = file_key

        pdf_text, pdf_images, page_count, scanned_count = read_pdf(
            uploaded_file.getvalue()
        )

        st.divider()
        st.markdown("**📄 Current document**")
        st.caption(uploaded_file.name)
        col1, col2 = st.columns(2)
        col1.metric("Pages", page_count)
        col2.metric("Words", f"{len(pdf_text.split()):,}")
        if scanned_count:
            st.info(
                f"{scanned_count} scanned page(s) found. "
                f"The first {min(scanned_count, 5)} are read as images."
            )

        st.divider()
        if st.button("🗑️ Clear all results", width="stretch"):
            reset_results()
            st.rerun()

    st.caption("Powered by Google Gemini")

# ---------- Header ----------
st.markdown(
    """
<div class="hero">
  <h1>📚 AI Study Assistant</h1>
  <p>Upload your college notes, ask questions, get summaries and test yourself.</p>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- Welcome screen ----------
if not pdf_text.strip() and not pdf_images:
    col1, col2, col3 = st.columns(3)
    with col1:
        with st.container(border=True):
            st.markdown("### 💬 Ask")
            st.caption("Ask anything about your notes and get simple, clear answers.")
    with col2:
        with st.container(border=True):
            st.markdown("### 📝 Summarize")
            st.caption("Turn long notes into short summaries or exam revision sheets.")
    with col3:
        with st.container(border=True):
            st.markdown("### 🎯 Quiz")
            st.caption("Generate multiple-choice questions to test what you've learned.")
    st.info("👈 Upload a PDF in the sidebar to get started.")
    st.stop()

tab_ask, tab_summary, tab_quiz = st.tabs(
    ["💬 Ask Questions", "📝 Summarize Notes", "🎯 Generate Quiz"]
)

# ---------- Ask Questions ----------
with tab_ask:
    if not st.session_state["chat"]:
        st.caption("Ask a question about your notes to start the conversation.")

    for message in st.session_state["chat"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    with st.form("ask_form", clear_on_submit=True, border=False):
        col_input, col_button = st.columns([5, 1])
        question = col_input.text_input(
            "Your question",
            placeholder="e.g. Explain the main idea of chapter 2",
            label_visibility="collapsed",
        )
        submitted = col_button.form_submit_button("Ask", type="primary", width="stretch")

    if submitted:
        if not question.strip():
            st.warning("Please enter your question.")
        else:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                prompt = f"""You are a helpful study assistant.
Answer using ONLY the provided notes and attached page images. Explain simply.
If the answer is not in the notes, say so.

NOTES:
{pdf_text}

QUESTION: {question}"""
                answer = stream_gemini(prompt, pdf_images)
            if answer:
                st.session_state["chat"].append({"role": "user", "content": question})
                st.session_state["chat"].append({"role": "assistant", "content": answer})
                st.rerun()

# ---------- Summarize Notes ----------
with tab_summary:
    style = st.radio(
        "Summary style",
        ["Short", "Detailed", "Exam revision sheet"],
        horizontal=True,
    )

    if st.button("✨ Generate summary", type="primary"):
        prompt = f"""Summarize these college notes (including any attached page images). Style: {style}.
Use headings and bullet points. Keep definitions and formulas.

NOTES:
{pdf_text}"""
        summary = stream_gemini(prompt, pdf_images)
        if summary:
            st.session_state["last_summary"] = summary

    if st.session_state["last_summary"]:
        with st.container(border=True):
            st.markdown(st.session_state["last_summary"])
        st.download_button(
            "⬇️ Download summary",
            st.session_state["last_summary"],
            file_name="summary.md",
            mime="text/markdown",
        )

# ---------- Generate Quiz ----------
with tab_quiz:
    col1, col2 = st.columns(2)
    number = col1.slider("Number of questions", 3, 15, 5)
    difficulty = col2.selectbox("Difficulty", ["Easy", "Medium", "Hard"])

    if st.button("🎯 Generate quiz", type="primary"):
        prompt = f"""Create {number} {difficulty} multiple-choice questions
from these notes (including any attached page images), with options A to D on separate lines.
Write the line ###ANSWERS### and then the answers with short explanations.

NOTES:
{pdf_text}"""
        quiz = stream_gemini(prompt, pdf_images)
        if quiz:
            st.session_state["last_quiz"] = quiz

    if st.session_state["last_quiz"]:
        questions, _, answers = st.session_state["last_quiz"].partition("###ANSWERS###")
        with st.container(border=True):
            st.markdown(questions)
        if answers:
            with st.expander("✅ Show answers"):
                st.markdown(answers)
