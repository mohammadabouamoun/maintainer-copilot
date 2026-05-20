import streamlit as st
import requests
import os

API_URL = os.getenv("API_URL", "http://api:8000")

st.set_page_config(page_title="Maintainer's Copilot", layout="wide")

def login(email, password):
    try:
        resp = requests.post(
            f"{API_URL}/auth/login",
            data={"username": email, "password": password}
        )
        if resp.status_code == 200:
            st.session_state.access_token = resp.json()["access_token"]
            st.session_state.user_email = email
            st.success("Logged in successfully!")
            st.rerun()
        else:
            st.error(f"Login failed: {resp.text}")
    except Exception as e:
        st.error(f"Connection error: {str(e)}")

def main():
    if "access_token" not in st.session_state:
        st.title("Login - Maintainer's Copilot")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit:
                login(email, password)
    else:
        st.sidebar.title("Navigation")
        st.sidebar.write(f"Logged in as: {st.session_state.user_email}")
        
        page = st.sidebar.radio("Go to", ["Chat", "Memory Inspector", "Widget Config"])
        
        if st.sidebar.button("Logout"):
            del st.session_state.access_token
            del st.session_state.user_email
            st.rerun()
            
        if page == "Chat":
            from views.chat import render_chat
            render_chat()
        elif page == "Memory Inspector":
            from views.memory import render_memory
            render_memory()
        elif page == "Widget Config":
            from views.widgets import render_widgets
            render_widgets()

if __name__ == "__main__":
    main()
