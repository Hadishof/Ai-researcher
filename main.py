from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import google.generativeai as genai
import shutil

# LangChain components for RAG (Retrieval-Augmented Generation)
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. ENVIRONMENT SETUP
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
os.environ["GOOGLE_API_KEY"] = api_key
genai.configure(api_key=api_key)

app = FastAPI()

# 2. CORS MIDDLEWARE: Crucial for allowing your Streamlit frontend 
# to talk to this API when they are on different "ports" (8501 vs 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows any origin (Fine for local development)
    allow_methods=["*"], # Allows GET, POST, DELETE, etc.
    allow_headers=["*"], 
)

# 3. EMBEDDINGS: The "Math Brain" that turns words into numbers
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")


@app.post("/train-on-pdf")
async def train_on_pdf(file: UploadFile = File(...)):
    try:
        # Save uploaded file locally temporarily
        file_path = f"./{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # PDF Processing: Load -> Split into chunks -> Save to Vector DB
        loader = PyPDFLoader(file_path)
        data = loader.load()
        
        # Chunking: We break text into 1000-char pieces so the AI doesn't get overwhelmed
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(data)

        # Persistence: Chroma saves these chunks into the /chroma_db folder
        Chroma.from_documents(
            documents=docs,
            embedding=embeddings,
            persist_directory="./chroma_db"
        )

        os.remove(file_path) # Clean up the temp PDF file
        return {"message": f"SUCCESS! Learned {file.filename}."}
    except Exception as e:
        return {"error": str(e)}


@app.get("/research")
async def research(question: str):
    try:
        # 4. RETRIEVAL: Search the saved folder for the most relevant 3 chunks (k=3)
        vector_db = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
        search_results = vector_db.similarity_search(question, k=3)
        context = "\n".join([doc.page_content for doc in search_results])

        # 5. GENERATION: Using Gemini 2.5 Flash with Temperature 0 for facts
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            generation_config={"temperature": 0}
        )

        # RTL/Hebrew Prompt: This tells the AI exactly how to behave with Hebrew text
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
    """
    This endpoint wipes the AI's memory by deleting the chroma_db folder.
    Very useful for starting a fresh project or clearing old data.
    """
    try:
        import shutil as sh
        if os.path.exists("./chroma_db"):
            sh.rmtree("./chroma_db") # Deletes the entire directory tree
        return {"message": "Knowledge base cleared successfully."}
    except Exception as e:
        return {"error": str(e)}
