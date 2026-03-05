from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import google.generativeai as genai
import shutil

from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
os.environ["GOOGLE_API_KEY"] = api_key
genai.configure(api_key=api_key)

app = FastAPI()

# Allow Streamlit frontend to talk to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")


@app.post("/train-on-pdf")
async def train_on_pdf(file: UploadFile = File(...)):
    try:
        file_path = f"./{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        loader = PyPDFLoader(file_path)
        data = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(data)

        Chroma.from_documents(
            documents=docs,
            embedding=embeddings,
            persist_directory="./chroma_db"
        )

        os.remove(file_path)
        return {"message": f"SUCCESS! Learned {file.filename}."}
    except Exception as e:
        return {"error": str(e)}


@app.get("/research")
async def research(question: str):
    try:
        vector_db = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
        search_results = vector_db.similarity_search(question, k=3)
        context = "\n".join([doc.page_content for doc in search_results])

        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            generation_config={"temperature": 0}
        )

        # Fix Hebrew RTL: explicitly tell the model to preserve RTL text direction
        prompt = f"""You are a helpful document assistant. 
Answer the user's question using ONLY the document info below.
IMPORTANT: If the user writes in Hebrew, you MUST respond in Hebrew.
When responding in Hebrew, write naturally from right to left — do NOT reverse or flip words.

Document info:
{context}

Question: {question}

Answer:"""

        response = model.generate_content(prompt)
        return {"answer": response.text}
    except Exception as e:
        return {"error": str(e)}


@app.delete("/clear")
async def clear_knowledge_base():
    try:
        import shutil as sh
        if os.path.exists("./chroma_db"):
            sh.rmtree("./chroma_db")
        return {"message": "Knowledge base cleared successfully."}
    except Exception as e:
        return {"error": str(e)}