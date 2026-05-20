import streamlit as st
import requests
import json
import uuid
import os

API_URL = os.getenv("API_URL", "http://api:8000")

def render_chat():
    st.title("Copilot Chat")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = str(uuid.uuid4())
        
    # Display chat messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # Chat input
    if prompt := st.chat_input("How can I help you?"):
        # Add user message to state
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
            data = {
                "conversation_id": st.session_state.conversation_id,
                "message": prompt
            }
            
            try:
                # Use SSE streaming
                with requests.post(f"{API_URL}/chat/message", json=data, headers=headers, stream=True) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
                        if chunk:
                            # The API streams raw tokens, but the first token might be CONVERSATION_ID
                            if chunk.startswith("CONVERSATION_ID:"):
                                st.session_state.conversation_id = chunk.split(":")[1].strip()
                                continue
                                
                            full_response += chunk
                            message_placeholder.markdown(full_response + "▌")
                            
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            except Exception as e:
                st.error(f"Error communicating with Copilot: {str(e)}")
