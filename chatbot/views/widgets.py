import streamlit as st
import requests
import os

API_URL = os.getenv("API_URL", "http://api:8000")

def render_widgets():
    st.title("Widget Configuration")
    st.markdown("Configure the external chat widget for your documentation sites.")
    
    headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
    
    # Create new widget form
    with st.form("widget_form"):
        st.subheader("Create New Widget")
        origins_input = st.text_input("Allowed Origins (CORS, comma separated)", placeholder="https://docs.example.com")
        greeting = st.text_input("Greeting Message", placeholder="Hi! How can I help you with our open source project?")
        primary_color = st.color_picker("Theme Primary Color", "#0066cc")
        
        if st.form_submit_button("Create Widget Configuration"):
            origins = [o.strip() for o in origins_input.split(",")] if origins_input else []
            payload = {
                "allowed_origins": origins,
                "theme": {"primary_color": primary_color},
                "greeting": greeting,
                "enabled_tools": ["classify_issue", "extract_entities", "summarize_thread", "search_knowledge_base"]
            }
            resp = requests.post(f"{API_URL}/widgets", json=payload, headers=headers)
            if resp.status_code == 201:
                st.success("Widget configuration saved!")
            else:
                st.error(f"Failed to save: {resp.text}")
    
    st.divider()
    st.subheader("Your Active Widgets")
    # Fetch existing widgets
    resp = requests.get(f"{API_URL}/widgets", headers=headers)
    if resp.status_code == 200:
        widgets = resp.json()
        if not widgets:
            st.info("No widgets created yet.")
        for w in widgets:
            with st.expander(f"Widget: {w['widget_id']}"):
                st.write(f"**Origins:** {', '.join(w['allowed_origins']) if w['allowed_origins'] else 'None'}")
                st.write(f"**Greeting:** {w['greeting']}")
                st.color_picker("Color", w['theme'].get('primary_color', '#000'), key=f"color_{w['widget_id']}", disabled=True)
                
                snippet = f'''
<!-- Add this to your website's <head> -->
<script src="{API_URL.replace('api:8000', 'localhost:8000').replace('http://api', 'http://localhost')}/widget.js" data-widget-id="{w['widget_id']}"></script>
                '''
                st.code(snippet, language="html")
    else:
        st.error("Could not fetch widgets.")
