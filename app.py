import streamlit as st
import requests

# 1. Page Config: Sets the browser tab title and the wider layout
st.set_page_config(page_title="AI Researcher Pro", page_icon="🧪", layout="wide")

# Sidebar for Knowledge Management
with st.sidebar:
    st.title("🗂️ Control Panel")
    
    # File Uploader: Stores the PDF in RAM temporarily
    uploaded_file = st.file_uploader("Upload Knowledge (PDF)", type="pdf")

    # Sync Button: Sends the PDF to FastAPI to be chunked and stored in ChromaDB
    if st.button("🚀 Sync Knowledge Base"):
        if uploaded_file:
            # st.status creates a nice expander that shows progress
            with st.status("Syncing...") as status:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                r = requests.post("http://127.0.0.1:8000/train-on-pdf", files=files)
                
                if r.status_code == 200:
                    data = r.json()
                    if "message" in data:
                        status.update(label="✅ Knowledge Synced!", state="complete")
                    else:
                        status.update(label=f"❌ Error: {data.get('error')}", state="error")
                else:
                    status.update(label="❌ Failed to connect to backend.", state="error")
        else:
            st.warning("Please upload a PDF first.")

    st.divider()

    # Clear Button: Tells FastAPI to delete the 'chroma_db' folder
    if st.button("🗑️ Clear Knowledge Base"):
        r = requests.delete("http://127.0.0.1:8000/clear")
        if r.status_code == 200:
            st.success("Knowledge base cleared!")
        else:
            st.error("Failed to clear knowledge base. Did you add the /clear route?")

# --- Main Chat UI ---
st.title("🕵️‍♂️ AI Document Researcher")

# Hebrew RTL support: This is a hack to make Hebrew look correct in the bubbles
st.markdown("""
    <style>
        .stChatMessage p {
            unicode-bidi: plaintext;
            text-align: start;
        }
    </style>
""", unsafe_allow_html=True)

# Session State: This keeps the chat history on screen when Streamlit reruns
if "messages" not in st.session_state:
    st.session_state.messages = []

# Redraw all previous messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat Input: 'prompt :=' captures the input and checks if it's not empty
if prompt := st.chat_input("Ask about your documents... (supports Hebrew ✓)"):
    # 1. Save and show User message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Ask the Backend
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # 'params' automatically handles spaces and Hebrew characters in the URL
            response = requests.get(
                "http://127.0.0.1:8000/research",
                params={"question": prompt}  
            )
            if response.status_code == 200:
                answer = response.json().get("answer", "No answer returned.")
                st.markdown(answer)
                # 3. Save AI message to history
                st.session_state.messages.append({"role": "assistant", "content": answer})
            else:
                st.error("Could not reach the backend. Make sure FastAPI is running.")
