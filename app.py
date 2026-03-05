import streamlit as st
import requests

st.set_page_config(page_title="AI Researcher Pro", page_icon="🧪", layout="wide")

# Sidebar for Knowledge Management
with st.sidebar:
    st.title("🗂️ Control Panel")
    uploaded_file = st.file_uploader("Upload Knowledge (PDF)", type="pdf")

    if st.button("🚀 Sync Knowledge Base"):
        if uploaded_file:
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

    if st.button("🗑️ Clear Knowledge Base"):
        r = requests.delete("http://127.0.0.1:8000/clear")
        if r.status_code == 200:
            st.success("Knowledge base cleared!")
        else:
            st.error("Failed to clear knowledge base.")

# Main Chat UI
st.title("🕵️‍♂️ AI Document Researcher")

# Hebrew RTL support styling
st.markdown("""
    <style>
        /* Make chat bubbles support RTL text naturally */
        .stChatMessage p {
            unicode-bidi: plaintext;
            text-align: start;
        }
    </style>
""", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about your documents... (supports Hebrew ✓)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = requests.get(
                "http://127.0.0.1:8000/research",
                params={"question": prompt}  # Fix: use params dict to handle special characters
            )
            if response.status_code == 200:
                answer = response.json().get("answer", "No answer returned.")
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            else:
                st.error("Could not reach the backend. Make sure FastAPI is running.")