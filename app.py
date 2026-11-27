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
MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.1-flash-lite","gemini-3.5-flash-lite","gemini-3.8-flash"]

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
LETTERS = ["A", "B", "C", "D"]

st.set_page_config(page_title="Study Lamp", page_icon="💡", layout="wide")

# ---------- Styling ----------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Source+Serif+4:ital,wght@0,400;0,700;1,400&display=swap');
:root {--bg: #14120F; --panel: #1E1B17; --line: #332E26; --ink: #F5EFE3; --muted: #A89F8E; --amber: #FFB547; --mint: #B9E4C9; --coral: #F2A38F;}
.stApp {background: var(--bg);}
.stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea {font-family: 'Inter', sans-serif; color: var(--ink);}
.stApp h1, .stApp h2, .stApp h3, .serif {font-family: 'Source Serif 4', Georgia, serif !important; color: var(--ink);}
footer, [data-testid="stAppDeployButton"], [data-testid="stSidebar"] {display: none;}
[data-testid="stHeader"] {background: transparent;}
.block-container {max-width: 1180px; padding-top: 3rem; padding-bottom: 7rem;}
.logo {font-size: 1.7rem;}
.logo b {color: var(--amber);}
.muted {color: var(--muted) !important; font-size: 0.9rem !important;}
.right {text-align: right; padding-top: 0.5rem;}
.kicker {font-size: 0.72rem !important; letter-spacing: 0.18em; color: var(--amber) !important; font-weight: 700;}

/* Buttons: pills, amber when active */
.stButton button, .stDownloadButton button {border-radius: 30px; background: var(--panel); border: 1px solid var(--line); font-weight: 700;}
.stButton button:hover, .stDownloadButton button:hover {border-color: var(--amber);}
.stButton button[kind="primary"] {background: var(--amber); border-color: var(--amber);}
.stButton button[kind="primary"] p {color: var(--bg);}

/* Panels */
.st-key-hero, .st-key-files, .st-key-progress, .st-key-question {background: var(--panel); border: 1px solid var(--line); border-radius: 22px; padding: 1.5rem;}
.st-key-hero {background: radial-gradient(500px 360px at 50% 0, #4A351466, transparent), var(--panel); padding: 3.5rem 2rem; text-align: center;}
.headline {font-size: 3.1rem; line-height: 1.2; margin-bottom: 0.8rem;}
.headline i {color: var(--amber);}
[data-testid="stFileUploaderDropzone"] {background: transparent; border: 2px dashed #FFB54780; border-radius: 20px; padding: 2rem;}

/* Desk tiles */
.st-key-tile_ask button, .st-key-tile_sum button, .st-key-tile_quiz button {border: none; border-radius: 22px; min-height: 8.5rem; justify-content: flex-start; align-items: flex-start; text-align: left; padding: 1.4rem 1.5rem;}
.st-key-tile_ask button > div, .st-key-tile_sum button > div, .st-key-tile_quiz button > div {justify-content: flex-start; text-align: left;}
.st-key-tile_ask button {background: var(--amber);}
.st-key-tile_sum button {background: var(--mint);}
.st-key-tile_quiz button {background: var(--coral);}
.st-key-tile_ask button p, .st-key-tile_sum button p, .st-key-tile_quiz button p {color: var(--bg); font-weight: 400;}
.st-key-tile_ask button strong, .st-key-tile_sum button strong, .st-key-tile_quiz button strong {font-family: 'Source Serif 4', Georgia, serif; font-size: 1.6rem;}

/* Chat */
[data-testid="stChatMessage"] {background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 1rem;}
[data-testid="stBottom"] > div {background: var(--bg);}

/* Quiz */
.count {font-size: 3.6rem; line-height: 1.1;}
.count span {font-size: 1.4rem; color: var(--muted);}
.bars {display: flex; gap: 6px; margin: 1rem 0 1.5rem;}
.bars i {flex: 1; height: 8px; border-radius: 5px; background: var(--line);}
.bars i.done {background: var(--mint);}
.bars i.now {background: var(--amber);}
.qtext {font-size: 2rem; line-height: 1.35; margin-bottom: 1rem;}
.st-key-opts button {border-radius: 18px; min-height: 4.5rem; justify-content: flex-start; text-align: left; padding: 0.9rem 1.2rem;}
.st-key-opts button > div {justify-content: flex-start; text-align: left;}
.st-key-opts button p {font-weight: 400;}
.st-key-opts button[kind="primary"] {background: #33270F; border: 2px solid var(--amber);}
.st-key-opts button[kind="primary"] p {color: var(--ink);}
.option {background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 0.7rem 1rem; margin-bottom: 0.45rem; color: var(--ink);}
.option b {color: var(--amber); margin-right: 0.8rem;}
.option.correct {border-color: var(--mint); background: #17271E;}
.option.wrong {border-color: var(--coral); background: #2D1B17;}
.option small {color: var(--muted); margin-left: 0.6rem;}

@media (max-width: 640px) {.headline {font-size: 2.2rem;} .qtext {font-size: 1.5rem;} .right {text-align: left;}}
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
    source: str  # file name (and page) the question comes from


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
                            "source": q.source,
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
    inline_total = sum(
        d["size"] for d in st.session_state["docs"].values() if isinstance(d["media"][1], types.Part)
    )

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
PAGES = ["Desk", "Ask", "Summarize", "Quiz"]
DEFAULTS = {
    "page": "Desk", "docs": {}, "media_cache": {}, "upload_id": 0,
    "messages": [], "last_summary": "",
    "quiz": [], "quiz_picks": [], "quiz_index": 0, "quiz_done": False,
}
for name, value in DEFAULTS.items():
    st.session_state.setdefault(name, value)
state = st.session_state


def go(page):
    state["page"] = page


def clear_results():
    state.update(messages=[], last_summary="", quiz=[], quiz_picks=[], quiz_index=0, quiz_done=False)


def remove_file(key):
    state["docs"].pop(key, None)
    state["media_cache"].pop(key, None)
    clear_results()


def pick(option):
    state["quiz_picks"][state["quiz_index"]] = option


def move(step):
    state["quiz_index"] += step


def finish_quiz():
    state["quiz_done"] = True


def retry_quiz():
    state.update(quiz_picks=[None] * len(state["quiz"]), quiz_index=0, quiz_done=False)


def new_quiz():
    state.update(quiz=[], quiz_picks=[], quiz_index=0, quiz_done=False)


def kicker(text):
    st.markdown(f'<p class="kicker">{text}</p>', unsafe_allow_html=True)


# ---------- Top bar ----------
logo_col, *nav_cols, count_col = st.columns([2.2, 1, 1, 1.3, 1, 2.2])
logo_col.markdown('<div class="logo serif">study<b>lamp</b></div>', unsafe_allow_html=True)
for col, name in zip(nav_cols, PAGES):
    col.button(
        name, key=f"nav_{name}", on_click=go, args=(name,), width="stretch",
        type="primary" if state["page"] == name else "secondary",
    )
total = len(state["docs"])
count_col.markdown(
    f'<p class="muted right">{total} file{"s" if total != 1 else ""} on desk</p>', unsafe_allow_html=True
)
st.write("")

page = state["page"]
docs = list(state["docs"].values())
media = [item for doc in docs for item in doc["media"]]

# ---------- Desk ----------
if page == "Desk":
    left, right = st.columns([1.5, 1], gap="medium")

    with left, st.container(key="hero"):
        st.markdown(
            '<div class="headline serif">What are we<br>studying <i>tonight?</i></div>'
            '<p class="muted">Put your notes on the desk and pick how you want to learn.</p>',
            unsafe_allow_html=True,
        )
        uploads = st.file_uploader(
            "Drop files here", type=ALL_EXTENSIONS, accept_multiple_files=True,
            key=f"uploader_{state['upload_id']}", label_visibility="collapsed",
        )
        if uploads:
            fresh = [f for f in uploads if f"{f.name}-{f.size}" not in state["docs"]]
            loaded = load_files(fresh)
            for doc in loaded:
                state["docs"][f"{doc['name']}-{doc['size']}"] = doc
            # Reset the uploader once everything is on the desk. If a file failed, keep its error visible.
            if len(loaded) == len(fresh):
                if loaded:
                    clear_results()
                state["upload_id"] += 1
                st.rerun()

    with right:
        with st.container(key="files"):
            kicker("ON YOUR DESK")
            if not state["docs"]:
                st.markdown('<p class="muted">Nothing yet. Add a file to begin.</p>', unsafe_allow_html=True)
            for key, doc in state["docs"].items():
                info, remove = st.columns([6, 1])
                detail = f"{doc['pages']} pages" if doc["kind"] == "pdf" else format_size(doc["size"])
                info.markdown(
                    f'<p>{html.escape(doc["name"])} <span class="muted">{detail}</span></p>',
                    unsafe_allow_html=True,
                )
                remove.button("✕", key=f"remove_{key}", on_click=remove_file, args=(key,), help="Remove file")
        st.button("**Ask →**  \nClear a doubt from your own notes.", key="tile_ask",
                  on_click=go, args=("Ask",), width="stretch")
        st.button("**Summarize →**  \nShort, detailed or exam sheet.", key="tile_sum",
                  on_click=go, args=("Summarize",), width="stretch")
        st.button("**Quiz →**  \nCheck what actually stuck.", key="tile_quiz",
                  on_click=go, args=("Quiz",), width="stretch")

    st.markdown(
        '<p class="muted">Answers are written by Google Gemini and can be wrong. '
        "Check anything important against your notes.</p>",
        unsafe_allow_html=True,
    )

# ---------- No files yet ----------
elif not docs:
    st.subheader("Your desk is empty")
    st.write("Add at least one file first.")
    st.button("Go to Desk", type="primary", on_click=go, args=("Desk",))

# ---------- Ask ----------
elif page == "Ask":
    messages = state["messages"]
    question = None

    if not messages:
        st.subheader("Ask about your files")
        st.write(f"Working from {describe_files(docs)}.")
        suggestions = ["Explain the main topics", "List the key definitions", "What might come up in the exam?"]
        for col, suggestion in zip(st.columns(len(suggestions)), suggestions):
            if col.button(suggestion, width="stretch"):
                question = suggestion
    else:
        _, save_col, clear_col = st.columns([4, 1, 1])
        chat_text = "\n\n".join(
            f"**{'You' if m['role'] == 'user' else 'Assistant'}:** {m['content']}" for m in messages
        )
        save_col.download_button("Save chat", chat_text, file_name="chat.md", width="stretch")
        if clear_col.button("Clear chat", width="stretch"):
            state["messages"] = []
            st.rerun()

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("meta"):
                st.markdown(f'<span class="muted">{message["meta"]}</span>', unsafe_allow_html=True)

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
            messages.append({"role": "assistant", "content": answer, "meta": state.get("last_meta", "")})
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

    if st.button("Write summary", type="primary"):
        instructions = {
            "Short": "Write a short summary with only the key points as bullets.",
            "Detailed": "Write a detailed summary, section by section, with headings.",
            "Exam revision sheet": "Write an exam revision sheet: key definitions, formulas and likely exam questions.",
        }
        prompt = f"""You are a helpful study assistant. Use ONLY the attached study files.
{instructions[style]} Use simple language."""
        answer = stream_gemini(prompt, media)
        if answer:
            state["last_summary"] = answer
            st.rerun()

    if state["last_summary"]:
        st.markdown(state["last_summary"])
        st.download_button("Save summary", state["last_summary"], file_name="summary.md")

# ---------- Quiz ----------
elif page == "Quiz":
    quiz = state["quiz"]

    if not quiz:
        st.subheader("Test yourself")
        number = st.slider("Number of questions", 3, 15, 5)
        difficulty = st.radio("Difficulty", ["Easy", "Medium", "Hard"], index=1, horizontal=True)
        if st.button("Start quiz", type="primary"):
            prompt = f"""Create {number} multiple-choice questions of {difficulty.lower()} difficulty
using ONLY the attached study files. Each question needs exactly 4 options, one correct answer,
a short explanation, and the source (file name and page if there is one)."""
            result = generate_quiz(prompt, media, number)
            if result:
                state.update(quiz=result, quiz_picks=[None] * len(result), quiz_index=0, quiz_done=False)
                st.rerun()

    elif not state["quiz_done"]:
        index = state["quiz_index"]
        item = quiz[index]
        chosen = state["quiz_picks"][index]
        side, main = st.columns([1, 3.4], gap="medium")

        with side, st.container(key="progress"):
            kicker("PROGRESS")
            bars = "".join(
                f'<i class="{"now" if i == index else "done" if p is not None else ""}"></i>'
                for i, p in enumerate(state["quiz_picks"])
            )
            st.markdown(
                f'<div class="count serif">{index + 1} <span>/ {len(quiz)}</span></div>'
                f'<div class="bars">{bars}</div>'
                f'<p class="muted">Source<br>{html.escape(item["source"])}</p>',
                unsafe_allow_html=True,
            )

        with main, st.container(key="question"):
            kicker(f"QUESTION {index + 1}")
            st.markdown(f'<div class="qtext serif">{html.escape(item["question"])}</div>', unsafe_allow_html=True)
            with st.container(key="opts"):
                for row in (0, 2):
                    for col, i in zip(st.columns(2), (row, row + 1)):
                        col.button(
                            f"{LETTERS[i]} {item['options'][i]}", key=f"opt_{index}_{i}",
                            on_click=pick, args=(i,), width="stretch",
                            type="primary" if chosen == i else "secondary",
                        )
            st.write("")
            back_col, _, next_col = st.columns([1, 2, 1.3])
            if index > 0:
                back_col.button("← Back", on_click=move, args=(-1,), width="stretch")
            if index < len(quiz) - 1:
                next_col.button("Next question →", type="primary", on_click=move, args=(1,),
                                disabled=chosen is None, width="stretch")
            else:
                next_col.button("See my score", type="primary", on_click=finish_quiz,
                                disabled=chosen is None, width="stretch")

    else:
        picks = state["quiz_picks"]
        score = sum(p == q["correct"] for p, q in zip(picks, quiz))
        kicker("RESULT")
        st.markdown(f'<div class="count serif">{score} <span>/ {len(quiz)} correct</span></div>', unsafe_allow_html=True)
        retry_col, new_col, _ = st.columns([1, 1, 3])
        retry_col.button("Retry quiz", type="primary", on_click=retry_quiz, width="stretch")
        new_col.button("New quiz", on_click=new_quiz, width="stretch")

        for number, (item, chosen) in enumerate(zip(quiz, picks), start=1):
            st.markdown(f"### {number}. {item['question']}")
            rows = ""
            for i, option in enumerate(item["options"]):
                css, note = "", ""
                if i == item["correct"]:
                    css, note = "correct", "Correct answer"
                elif i == chosen:
                    css, note = "wrong", "Your answer"
                rows += f'<div class="option {css}"><b>{LETTERS[i]}</b>{html.escape(option)}<small>{note}</small></div>'
            st.markdown(rows, unsafe_allow_html=True)
            st.caption(f"{item['explanation']} (Source: {item['source']})")
