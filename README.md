🕵️‍♂️ AI Document Researcher (Full-Stack RAG)
  A professional Retrieval-Augmented Generation (RAG) platform that allows users to perform high-speed,
  factual research on private PDF documents. This project demonstrates the ability to build a full-stack AI product,
  handling everything from data ingestion and vector embeddings to a modern responsive user interface.
  
🛠️ Technical Stack
  Backend: FastAPI (High-performance Python API)
  Frontend: Streamlit (Modern Interactive Dashboard)
  AI Engine: Google Gemini 2.5 Flash
  Vector Database: ChromaDB (Persistent local storage)
  Orchestration: LangChain (Document loading, splitting, and retrieval)
  Environment: Python 3.10+, Dotenv, CORS Middleware

🧠 Skills Demonstrated
  AI Engineering: Implementation of RAG architecture and prompt engineering for multilingual (Hebrew/English) support.
  Database Management: Managing a persistent vector store and implementing data clearing/management logic.
  API Development: Creating RESTful endpoints with FastAPI to bridge the gap between AI logic and the UI.
  Full-Stack Integration: Connecting a frontend dashboard to a backend server with proper CORS handling and error management.
  Software Security: Implementing .env security protocols and .gitignore safety to protect sensitive API keys and data.

🏗️ System Architecture
  Ingestion: PDFs are processed and split into 1,000-character chunks with overlap to maintain context.
  Embedding: Text is converted into high-dimensional math vectors using gemini-embedding-001.
  Storage: Vectors are saved locally in a chroma_db folder for persistent memory.
  Retrieval: The system performs a similarity search to find the most relevant context for any user query.
  Response: Gemini 2.5 Flash generates a deterministic response (Temp 0) based only on the retrieved data.  

🚀 How to Run Locally
  1. Prerequisites
    Python 3.10 or higher
    A Google Gemini API Key

  2. Setup
     # Clone the repository
      git clone https://github.com/Hadishof/Ai-researcher.git
      cd ai-researcher-project
      # Create and activate virtual environment
      python -m venv .venv
      .\.venv\Scripts\Activate.ps1  # Windows
      # Install libraries
      pip install -r requirements.txt
     
  4. Environment Variables
     Create a .env file in the root directory:
       GOOGLE_API_KEY=your_actual_api_key_here

  5. Launch
     Open two terminals and run:
     Terminal 1 (Backend): fastapi dev main.py
     Terminal 2 (Frontend): python -m streamlit run app.py
