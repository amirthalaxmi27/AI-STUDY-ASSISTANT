import io
import time
import streamlit as st
from google import genai
from pypdf import PdfReader

# If one model is busy, the next one is tried
MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash","gemini-3.1-flash-lite"]

st.set_page_config(page_title="AI Study Assistant", page_icon="📚", layout="wide")

try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error('Add GEMINI_API_KEY = "your-key" in .streamlit/secrets.toml')
    st.stop()


def ask_gemini(prompt):
    last_error = None
    for attempt in range(2):
        for model in MODELS:
            try:
                response = client.models.generate_content(
                    model=model, contents=prompt
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
    return "\n".join(page.extract_text() or "" for page in reader.pages)


st.title("📚 AI Study Assistant")
st.write("Upload your college notes and study smarter.")

st.sidebar.title("Navigation")
page = st.sidebar.selectbox(
    "Choose a feature", ["Ask Questions", "Summarize Notes", "Generate Quiz"]
)
uploaded_file = st.sidebar.file_uploader("Upload your PDF notes", type=["pdf"])

pdf_text = ""
if uploaded_file is not None:
    pdf_text = read_pdf(uploaded_file.getvalue())

st.header(page)

if not pdf_text.strip():
    st.info("Upload a text-based PDF in the sidebar (scanned PDFs won't work).")
    st.stop()

if page == "Ask Questions":
    question = st.text_input("Enter your question")

    if st.button("Get Answer"):
        if not question.strip():
            st.warning("Please enter your question.")
        else:
            prompt = f"""You are a helpful study assistant.
Answer using ONLY the notes below. Explain simply.
If the answer is not in the notes, say so.

NOTES:
{pdf_text}

QUESTION: {question}"""
            with st.spinner("Thinking..."):
                answer = ask_gemini(prompt)
            if answer:
                st.subheader("Answer")
                st.write(answer)

elif page == "Summarize Notes":
    style = st.radio("Summary style", ["Short", "Detailed", "Exam revision sheet"])

    if st.button("Summarize"):
        prompt = f"""Summarize these college notes. Style: {style}.
Use headings and bullet points. Keep definitions and formulas.

NOTES:
{pdf_text}"""
        with st.spinner("Summarizing..."):
            summary = ask_gemini(prompt)
        if summary:
            st.markdown(summary)
            st.download_button("Download summary", summary, file_name="summary.txt")

elif page == "Generate Quiz":
    number = st.slider("Number of questions", 3, 15, 5)
    difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])

    if st.button("Generate Quiz"):
        prompt = f"""Create {number} {difficulty} multiple-choice questions
from these notes, with options A to D on separate lines.
Write the line ###ANSWERS### and then the answers with short explanations.

NOTES:
{pdf_text}"""
        with st.spinner("Creating quiz..."):
            quiz = ask_gemini(prompt)
        if quiz:
            questions, _, answers = quiz.partition("###ANSWERS###")
            st.markdown(questions)
            if answers:
                with st.expander("Show answers"):
                    st.markdown(answers)