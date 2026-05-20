import streamlit as st
import requests
import pandas as pd
import os

API_URL = os.getenv("API_URL", "http://api:8000")

def render_memory():
    st.title("Memory Inspector")
    st.markdown("View and manage the long-term semantic memories stored by the copilot for your account.")
    
    # We will need an endpoint in the API to list memories. 
    # Let's see if there is one. If not, we will need to create one in app/api/routers/users.py or memory.py
    
    # Fetch memories from the backend
    
    headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
    
    # Attempt to fetch memories
    try:
        resp = requests.get(f"{API_URL}/memory", headers=headers)
        if resp.status_code == 200:
            memories = resp.json()
            if not memories:
                st.write("No long-term memories stored yet.")
            else:
                for mem in memories:
                    with st.container():
                        st.markdown(f"**Type:** {mem['memory_type']} | **Stored:** {mem['created_at']}")
                        st.markdown(f"> {mem['content']}")
                        if st.button("Delete", key=mem['id']):
                            requests.delete(f"{API_URL}/memory/{mem['id']}", headers=headers)
                            st.rerun()
                        st.divider()
        else:
            st.error(f"Failed to fetch memories: {resp.status_code} - {resp.text}")
    except Exception as e:
        st.error(f"Connection error: {str(e)}")
