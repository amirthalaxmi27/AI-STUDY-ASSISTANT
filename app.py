import io
import time
import pypdfium2 as pdfium
import streamlit as st
from google import genai
from pypdf import PdfReader

# If one model is busy, the next one is tried
MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.1-flash-lite"]

st.set_page_config(page_title="AI Study Assistant", page_icon="📚", layout="wide")

try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error('Add GEMINI_API_KEY = "your-key" in .streamlit/secrets.toml')
    st.stop()


def ask_gemini(prompt, images=None):
    contents = [prompt] + (images or [])
    last_error = None
    for attempt in range(2):
        for model in MODELS:
            try:
                response = client.models.generate_content(
                    model=model, contents=contents
                )
                return response.text
            except Exception as error:
                last_error = error
        if attempt == 0:
            time.sleep(10)
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
        for i in scan_indices[:10]:
            bitmap = pdf_doc[i].render(scale=1.5)
            images.append(bitmap.to_pil())

    return "\n".join(text_parts), images


st.title("📚 AI Study Assistant")
st.write("Upload your college notes and study smarter.")

st.sidebar.title("Navigation")
page = st.sidebar.selectbox(
    "Choose a feature", ["Ask Questions", "Summarize Notes", "Generate Quiz"]
)
uploaded_file = st.sidebar.file_uploader("Upload your PDF notes", type=["pdf"])

pdf_text, pdf_images = "", []
if uploaded_file is not None:
    pdf_text, pdf_images = read_pdf(uploaded_file.getvalue())

st.header(page)

if not pdf_text.strip() and not pdf_images:
    st.info("Upload a PDF in the sidebar to get started.")
    st.stop()

if page == "Ask Questions":
    question = st.text_input("Enter your question")

    if st.button("Get Answer"):
        if not question.strip():
            st.warning("Please enter your question.")
        else:
            prompt = f"""You are a helpful study assistant.
Answer using ONLY the provided notes and attached page images. Explain simply.
If the answer is not in the notes, say so.

NOTES:
{pdf_text}

QUESTION: {question}"""
            with st.spinner("Thinking..."):
                answer = ask_gemini(prompt, pdf_images)
            if answer:
                st.subheader("Answer")
                st.write(answer)

elif page == "Summarize Notes":
    style = st.radio("Summary style", ["Short", "Detailed", "Exam revision sheet"])

    if st.button("Summarize"):
        prompt = f"""Summarize these college notes (including any attached page images). Style: {style}.
Use headings and bullet points. Keep definitions and formulas.

NOTES:
{pdf_text}"""
        with st.spinner("Summarizing..."):
            summary = ask_gemini(prompt, pdf_images)
        if summary:
            st.markdown(summary)
            st.download_button("Download summary", summary, file_name="summary.txt")

elif page == "Generate Quiz":
    number = st.slider("Number of questions", 3, 15, 5)
    difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])

    if st.button("Generate Quiz"):
        prompt = f"""Create {number} {difficulty} multiple-choice questions
from these notes (including any attached page images), with options A to D on separate lines.
Write the line ###ANSWERS### and then the answers with short explanations.

NOTES:
{pdf_text}"""
        with st.spinner("Creating quiz..."):
            quiz = ask_gemini(prompt, pdf_images)
        if quiz:
            questions, _, answers = quiz.partition("###ANSWERS###")
            st.markdown(questions)
            if answers:
                with st.expander("Show answers"):
                    st.markdown(answers)
