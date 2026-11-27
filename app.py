import html
import io
import json
import os
import re
import time

import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel
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
KIND_LABELS = {"pdf": "PDF", "image": "Image", "video": "Video", "audio": "Audio"}
ALL_EXTENSIONS = [ext for group in FILE_TYPES.values() for ext in group]
INLINE_LIMIT = 8 * 1024 * 1024  # files up to this size are sent directly (fast)
INLINE_TOTAL_LIMIT = 14 * 1024 * 1024  # Gemini limits one request's size, so cap the total sent directly
PAGES = ["Ask", "Summarize", "Quiz"]
LETTERS = ["A", "B", "C", "D"]

st.set_page_config(page_title="Study Assistant", page_icon="📘", layout="centered")

# ---------- Styling ----------
# Ballpoint blue on white paper, with highlighter yellow used only where
# a student would actually highlight: the page title and correct answers.
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&display=swap');

:root {
    --ink: #1F2328;
    --muted: #5B6472;
    --pen: #2747A8;
    --highlight: #FFE66D;
    --rule: #DDE1E7;
    --side: #F3F5F8;
    --wrong: #B42318;
}

.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea,
.stApp h1, .stApp h2, .stApp h3, .stApp button p {
    font-family: 'Atkinson Hyperlegible', sans-serif !important;
}
.stApp p, .stApp li {font-size: 1.02rem; line-height: 1.6; color: var(--ink);}
footer, [data-testid="stAppDeployButton"] {display: none;}
.block-container {padding-top: 2.5rem; padding-bottom: 7rem; max-width: 780px;}

/* Highlighter stroke, like a marker pen pulled across the line */
.marked {
    background: linear-gradient(100deg, transparent 0.4%, var(--highlight) 1.2%, var(--highlight) 98.6%, transparent 99.4%);
    background-size: 100% 52%;
    background-position: 0 78%;
    background-repeat: no-repeat;
    -webkit-box-decoration-break: clone;
    box-decoration-break: clone;
    padding: 0 0.15em;
}

/* Welcome screen */
.intro-title {font-size: 2.6rem; font-weight: 700; line-height: 1.15; color: var(--ink); margin: 0 0 1rem; letter-spacing: -0.01em;}
.lede {font-size: 1.15rem !important; color: var(--muted) !important; max-width: 36em; margin-bottom: 2rem;}
.steps {padding-left: 1.3rem; margin: 0 0 1.8rem;}
.steps li {margin-bottom: 0.6rem; padding-left: 0.3rem;}
.steps li::marker {color: var(--pen); font-weight: 700;}
.formats {font-size: 0.92rem !important; color: var(--muted) !important; border-top: 1px solid var(--rule); padding-top: 1rem;}

/* Page header once files are added */
.masthead {border-bottom: 2px solid var(--ink); padding-bottom: 0.8rem; margin-bottom: 1.4rem;}
.masthead h1 {font-size: 1.9rem; font-weight: 700; margin: 0; padding: 0; color: var(--ink);}
.masthead p {margin: 0.3rem 0 0; color: var(--muted) !important; font-size: 0.98rem !important;}

/* Sidebar */
[data-testid="stSidebar"] {background: var(--side); border-right: 1px solid var(--rule);}
.wordmark {font-size: 1.35rem; font-weight: 700; color: var(--pen); margin-bottom: 0.1rem;}
.side-note {font-size: 0.9rem !important; color: var(--muted) !important; margin-bottom: 1rem;}
.file-row {padding: 0.55rem 0; border-bottom: 1px solid var(--rule);}
.file-row:last-child {border-bottom: none;}
.file-name {font-weight: 700; font-size: 0.92rem; color: var(--ink); overflow-wrap: anywhere;}
.file-meta {font-size: 0.82rem; color: var(--muted);}
.tag {display: inline-block; font-size: 0.72rem; font-weight: 700; color: var(--pen); border: 1px solid var(--pen); border-radius: 3px; padding: 0 0.3rem; margin-right: 0.35rem;}
.disclaimer {font-size: 0.8rem !important; color: var(--muted) !important; margin-top: 1.5rem;}

/* Navigation */
button[kind="segmented_controlActive"] {background: var(--pen) !important; border-color: var(--pen) !important;}
button[kind="segmented_controlActive"] p {color: #fff !important;}

/* Buttons */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {border-radius: 6px; font-weight: 700;}

/* Chat: your questions sit on a grey slip, answers on the page */
[data-testid="stChatMessage"] {background: transparent; padding: 0.9rem 0; border-radius: 0;}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: var(--side); border-radius: 8px; padding: 0.8rem 1rem;
}
.meta {font-size: 0.8rem; color: var(--muted);}

/* Quiz results */
.score {font-size: 1.5rem !important; margin-bottom: 0.2rem;}
.option {padding: 0.25rem 0; color: var(--ink);}
.option .letter {display: inline-block; width: 1.6rem; font-weight: 700; color: var(--muted);}
.option.correct .letter {color: var(--ink);}
.option.correct .text {font-weight: 700;}
.option.wrong .text {color: var(--wrong); text-decoration: line-through;}
.option .note {font-size: 0.8rem; color: var(--muted); margin-left: 0.4rem;}
.option.wrong .note {color: var(--wrong);}
.why {color: var(--muted) !important; font-size: 0.95rem !important; margin-top: 0.5rem;}

@media (max-width: 640px) {
    .intro-title {font-size: 2rem;}
    .block-container {padding-top: 1.5rem;}
}
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
def model_config(model, **settings):
    """Gemini 2.5 models 'think' before answering by default, which is slow. Turn it off."""
    if model.startswith("gemini-2.5"):
        settings["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    return types.GenerateContentConfig(**settings)


def gemini_error(error):
    st.error(
        "Gemini didn't respond. Wait a few seconds and try again. "
        f"If it keeps happening, check your API key and usage limits.\n\nDetails: {error}"
    )


def stream_gemini(prompt, media=None, show=True):
    """Send the prompt plus any media to Gemini. Streams the answer on screen if show=True."""
    contents = [prompt] + (media or [])
    last_error = None
    for attempt in range(2):
        for model in MODELS:
            placeholder = st.empty() if show else None
            full_text = ""
            started = time.time()
            try:
                for chunk in client.models.generate_content_stream(
                    model=model, contents=contents, config=model_config(model)
                ):
                    if chunk.text:
                        full_text += chunk.text
                        if placeholder:
                            placeholder.markdown(full_text + " ▌")
                if full_text:
                    if placeholder:
                        placeholder.markdown(full_text)
                    st.session_state["last_meta"] = (
                        f"Answered by {model} in {time.time() - started:.1f}s"
                    )
                    return full_text
            except Exception as error:
                last_error = error
            if placeholder:
                placeholder.empty()
        if attempt == 0:
            time.sleep(2)
    gemini_error(last_error)
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


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_option: int  # 0 = A, 1 = B, 2 = C, 3 = D
    explanation: str


def generate_quiz(prompt, media, number):
    """Ask Gemini for quiz questions as structured data, showing live progress."""
    status = st.status("Creating your quiz", expanded=True)
    with status:
        bar = st.progress(0.0, text="Sending your files to Gemini")

    started = time.time()
    last_error = None
    for attempt in range(2):
        for model in MODELS:
            config = model_config(
                model,
                response_mime_type="application/json",
                response_schema=list[QuizQuestion],
            )
            try:
                bar.progress(0.0, text=f"Reading your files with {model}")
                text = ""
                for chunk in client.models.generate_content_stream(
                    model=model, contents=[prompt] + media, config=config
                ):
                    if chunk.text:
                        text += chunk.text
                        written = min(text.count('"question"'), number)
                        if written:
                            bar.progress(
                                written / number,
                                text=f"Writing question {written} of {number}",
                            )

                quiz = []
                for item in json.loads(text):
                    q = QuizQuestion(**item)
                    options = [re.sub(r"^\s*[A-Da-d][\.\):]\s+", "", o).strip() for o in q.options]
                    if len(options) == 4 and 0 <= q.correct_option <= 3:
                        quiz.append({
                            "question": q.question,
                            "options": options,
                            "correct": q.correct_option,
                            "explanation": q.explanation,
                        })
                if quiz:
                    seconds = time.time() - started
                    bar.progress(1.0, text="Done")
                    st.session_state["last_meta"] = f"Written by {model} in {seconds:.1f}s"
                    status.update(label=f"Quiz ready in {seconds:.1f}s", state="complete", expanded=False)
                    return quiz
            except Exception as error:
                last_error = error
                with status:
                    st.caption(f"{model} didn't respond properly. Trying the next model.")
        if attempt == 0:
            time.sleep(2)

    status.update(label="Couldn't create the quiz", state="error", expanded=True)
    gemini_error(last_error)
    return None


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


def join_words(items):
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


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
                    with st.spinner(f"Uploading {file.name}. Large files and videos can take a minute."):
                        cache[key] = upload_to_gemini(data, file.name, mime)
            except Exception as error:
                st.error(f"Couldn't read {file.name}. Try uploading it again. Details: {error}")
                continue

        if isinstance(cache[key], types.Part):
            inline_total += len(data)

        docs.append({
            "name": file.name,
            "kind": kind,
            "size": file.size,
            "pages": count_pages(data) if kind == "pdf" else 0,
            "media": [f"[{KIND_LABELS[kind]} file: {file.name}]", cache[key]],
        })
    return docs


def describe_files(docs):
    """'2 PDFs (48 pages) and 1 video' style summary."""
    parts = []
    for kind, word in [("pdf", "PDF"), ("image", "image"), ("video", "video"), ("audio", "audio file")]:
        group = [d for d in docs if d["kind"] == kind]
        if not group:
            continue
        text = f"{len(group)} {word}{'s' if len(group) > 1 else ''}"
        if kind == "pdf":
            pages = sum(d["pages"] for d in group)
            text += f" ({pages} page{'s' if pages != 1 else ''})"
        parts.append(text)
    return join_words(parts)


# ---------- Session state ----------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("last_summary", "")
st.session_state.setdefault("quiz", [])
st.session_state.setdefault("quiz_id", 0)
st.session_state.setdefault("quiz_answers", None)
st.session_state.setdefault("media_cache", {})
st.session_state.setdefault("page", PAGES[0])


def clear_results():
    st.session_state["messages"] = []
    st.session_state["last_summary"] = ""
    st.session_state["quiz"] = []
    st.session_state["quiz_answers"] = None


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown(
        '<div class="wordmark">Study Assistant</div>'
        '<p class="side-note">Add lecture notes, photos of your notebook or class recordings.</p>',
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Your files",
        type=ALL_EXTENSIONS,
        accept_multiple_files=True,
        help="You can select several files at once.",
    )

    docs = load_files(uploaded_files) if uploaded_files else []

    if docs:
        rows = ""
        for doc in docs:
            meta = format_size(doc["size"])
            if doc["kind"] == "pdf":
                meta = f"{doc['pages']} pages, {meta}"
            rows += (
                f'<div class="file-row"><div class="file-name">'
                f'<span class="tag">{KIND_LABELS[doc["kind"]]}</span>{html.escape(doc["name"])}</div>'
                f'<div class="file-meta">{meta}</div></div>'
            )
        st.markdown(rows, unsafe_allow_html=True)
        st.write("")
        st.button("Clear all results", on_click=clear_results, width="stretch")

    st.markdown(
        '<p class="disclaimer">Answers are written by Google Gemini and can be wrong. '
        "Check anything important against your notes.</p>",
        unsafe_allow_html=True,
    )

# ---------- Welcome screen ----------
if not docs:
    st.markdown(
        """
<h1 class="intro-title"><span class="marked">Study from your own notes.</span></h1>
<p class="lede">Upload lecture PDFs, photos of your notebook or a recorded class.
Ask questions about them, get a summary for revision, or test yourself with a quiz.</p>
<ol class="steps">
  <li><strong>Add your files</strong> in the sidebar. You can add several at once.</li>
  <li><strong>Choose Ask, Summarize or Quiz</strong> at the top of the page.</li>
  <li><strong>Check answers against your notes.</strong> Each answer says which file it came from.</li>
</ol>
<p class="formats">Works with PDFs, images (PNG, JPG, WEBP, HEIC), video (MP4, MOV, WEBM)
and audio (MP3, WAV). Files up to 200 MB each.</p>
""",
        unsafe_allow_html=True,
    )
    st.stop()

# ---------- Main app ----------
media = [item for doc in docs for item in doc["media"]]

st.markdown(
    f'<div class="masthead"><h1>Study Assistant</h1>'
    f"<p>Working from {describe_files(docs)}.</p></div>",
    unsafe_allow_html=True,
)

choice = st.segmented_control(
    "Feature", PAGES, default=st.session_state["page"], label_visibility="collapsed"
)
if choice:
    st.session_state["page"] = choice
page = st.session_state["page"]

# ---------- Ask ----------
if page == "Ask":
    messages = st.session_state["messages"]
    question = None

    if not messages:
        st.subheader("Ask about your files")
        st.write("Type a question at the bottom of the page. Follow-up questions remember the conversation.")
        suggestions = [
            "Explain the main topics",
            "List the key definitions",
            "What might come up in the exam?",
        ]
        cols = st.columns(len(suggestions))
        for col, suggestion in zip(cols, suggestions):
            if col.button(suggestion, width="stretch"):
                question = suggestion
    else:
        _, save_col, clear_col = st.columns([3, 1, 1])
        chat_text = "\n\n".join(
            f"**{'You' if m['role'] == 'user' else 'Assistant'}:** {m['content']}" for m in messages
        )
        save_col.download_button("Save chat", chat_text, file_name="chat.md", width="stretch")
        if clear_col.button("Clear chat", width="stretch"):
            st.session_state["messages"] = []
            st.rerun()

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("meta"):
                st.markdown(f'<span class="meta">{message["meta"]}</span>', unsafe_allow_html=True)

    typed = st.chat_input("Ask a question about your files")
    question = typed or question

    if question:
        with st.chat_message("user"):
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

        with st.chat_message("assistant"):
            answer = stream_gemini(prompt, media)

        if answer:
            messages.append({"role": "user", "content": question})
            messages.append(
                {"role": "assistant", "content": answer, "meta": st.session_state.get("last_meta", "")}
            )
            st.rerun()

# ---------- Summarize ----------
elif page == "Summarize":
    st.subheader("Summarize your files")
    style = st.radio(
        "Summary style",
        ["Short", "Detailed", "Exam revision sheet"],
        horizontal=True,
        captions=["Key points only", "Section by section", "Definitions, formulas, likely questions"],
    )
    clicked = st.button("Write summary", type="primary")

    if clicked:
        prompt = f"""Summarize ALL the attached study files: every page of each PDF, plus any images, videos or audio.
Style: {style}. Use headings and bullet points. Keep definitions and formulas.
If there are several files, cover each of them."""
        summary = stream_gemini(prompt, media)
        if summary:
            st.session_state["last_summary"] = summary
            st.session_state["summary_meta"] = st.session_state.get("last_meta", "")
    elif st.session_state["last_summary"]:
        st.markdown(st.session_state["last_summary"])
        st.markdown(f'<span class="meta">{st.session_state.get("summary_meta", "")}</span>', unsafe_allow_html=True)

    if st.session_state["last_summary"]:
        st.write("")
        st.download_button(
            "Download summary",
            st.session_state["last_summary"],
            file_name="summary.md",
            mime="text/markdown",
        )

# ---------- Quiz ----------
elif page == "Quiz":
    st.subheader("Test yourself")
    col1, col2 = st.columns(2)
    number = col1.slider("Number of questions", 3, 15, 5)
    difficulty = col2.selectbox("Difficulty", ["Easy", "Medium", "Hard"])

    if st.button("Create quiz", type="primary"):
        prompt = f"""Create {number} {difficulty} multiple-choice questions
covering ALL the attached study files: every page of each PDF, plus any images, videos or audio.
Spread the questions across all the files and topics.
Each question has exactly 4 options (write the options without A/B/C/D letters),
correct_option is the index of the right option (0 to 3), and explanation briefly says why it is right.
Mix up which position the correct option is in."""
        quiz = generate_quiz(prompt, media, number)
        if quiz:
            st.session_state["quiz"] = quiz
            st.session_state["quiz_answers"] = None
            st.session_state["quiz_id"] += 1
            st.session_state["quiz_meta"] = st.session_state.get("last_meta", "")
            st.rerun()

    quiz = st.session_state["quiz"]
    quiz_id = st.session_state["quiz_id"]
    answers = st.session_state["quiz_answers"]

    if quiz and answers is None:
        # Taking the quiz
        st.markdown(f'<span class="meta">{st.session_state.get("quiz_meta", "")}</span>', unsafe_allow_html=True)
        with st.form(f"quiz_form_{quiz_id}", border=False):
            for i, q in enumerate(quiz):
                with st.container(border=True):
                    st.markdown(f"**Question {i + 1} of {len(quiz)}**")
                    st.markdown(q["question"])
                    st.radio(
                        f"Answer for question {i + 1}",
                        range(4),
                        format_func=lambda j, q=q: f"{LETTERS[j]}.  {q['options'][j]}",
                        index=None,
                        key=f"quiz_{quiz_id}_{i}",
                        label_visibility="collapsed",
                    )
            if st.form_submit_button("Submit answers", type="primary"):
                st.session_state["quiz_answers"] = [
                    st.session_state.get(f"quiz_{quiz_id}_{i}") for i in range(len(quiz))
                ]
                st.rerun()

    elif quiz:
        # Showing results
        score = sum(1 for q, a in zip(quiz, answers) if a == q["correct"])
        percent = score / len(quiz) * 100
        if percent >= 80:
            message = "Strong result. Read the explanations for any you guessed."
        elif percent >= 50:
            message = "Halfway there. Go through the ones you missed below."
        else:
            message = "Worth another read of your notes before you retake it."

        st.markdown(
            f'<p class="score">You got <strong>{score} of {len(quiz)}</strong> right.</p><p>{message}</p>',
            unsafe_allow_html=True,
        )

        for i, (q, chosen) in enumerate(zip(quiz, answers)):
            with st.container(border=True):
                result = "Correct" if chosen == q["correct"] else ("Not answered" if chosen is None else "Incorrect")
                st.markdown(f"**Question {i + 1}: {result}**")
                st.markdown(q["question"])
                rows = ""
                for j, option in enumerate(q["options"]):
                    text = html.escape(option)
                    if j == q["correct"]:
                        note = "Your answer" if j == chosen else "Correct answer"
                        rows += (
                            f'<div class="option correct"><span class="letter">{LETTERS[j]}</span>'
                            f'<span class="text marked">{text}</span><span class="note">{note}</span></div>'
                        )
                    elif j == chosen:
                        rows += (
                            f'<div class="option wrong"><span class="letter">{LETTERS[j]}</span>'
                            f'<span class="text">{text}</span><span class="note">Your answer</span></div>'
                        )
                    else:
                        rows += (
                            f'<div class="option"><span class="letter">{LETTERS[j]}</span>'
                            f'<span class="text">{text}</span></div>'
                        )
                st.markdown(rows, unsafe_allow_html=True)
                st.markdown(f'<p class="why">{html.escape(q["explanation"])}</p>', unsafe_allow_html=True)

        if st.button("Retake this quiz"):
            st.session_state["quiz_answers"] = None
            st.session_state["quiz_id"] += 1
            st.rerun()
