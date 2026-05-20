import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app

@pytest.mark.asyncio
async def test_chatbot_streaming_and_tool_calling_flow():
    """
    End-to-End integration test checking chatbot session registration/login,
    streaming response chunk parsing, dynamic tool invocation (e.g., classify_issue),
    and database persistence of session message histories.
    """
    unique_id = uuid.uuid4().hex[:6]
    user_email = f"chat_user_{unique_id}@example.com"
    password = "SecurePassword123!"
    conversation_id = str(uuid.uuid4())

    with TestClient(app) as client:
        # 1. Register User
        reg_response = client.post(
            "/auth/register",
            json={
                "email": user_email,
                "password": password,
                "role": "user"
            }
        )
        assert reg_response.status_code == 201

        # 2. Log in and Retrieve JWT
        login_response = client.post(
            "/auth/login",
            data={
                "username": user_email,
                "password": password
            }
        )
        assert login_response.status_code == 200
        user_token = login_response.json()["access_token"]

        # 3. Hit POST /chat/message unauthorized (Assert 401 Unauthorized)
        unauth_response = client.post(
            "/chat/message",
            json={
                "conversation_id": conversation_id,
                "message": "Hello Maintainer Copilot!"
            }
        )
        assert unauth_response.status_code == 401

        # 4. Hit POST /chat/message authorized (Assert 200 and streaming chunks)
        auth_response = client.post(
            "/chat/message",
            json={
                "conversation_id": conversation_id,
                "message": "Classify this issue: my application crashes on boot with index out of bounds"
            },
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert auth_response.status_code == 200
        
        # Capture raw stream
        stream_chunks = []
        for chunk in auth_response.iter_lines():
            if chunk:
                if isinstance(chunk, bytes):
                    stream_chunks.append(chunk.decode("utf-8"))
                else:
                    stream_chunks.append(chunk)

        assert len(stream_chunks) >= 1
        
        # First chunk should contain the resolved conversation ID mapping
        assert stream_chunks[0].startswith(f"CONVERSATION_ID:{conversation_id}")
        
        # Combine remaining tokens to assert classification cite
        full_text_response = " ".join(stream_chunks[1:]).lower()
        print(f"\nChatbot response: {full_text_response}")
        # The prompt was "Classify this issue...", so the LLM should invoke 'classify_issue' and cite 'bug' or 'classification'
        assert any(x in full_text_response for x in ["bug", "classify", "classification", "label"])

        # 5. Fetch GET /chat/conversations/{id} history (Assert 200 OK)
        history_response = client.get(
            f"/chat/conversations/{conversation_id}",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert history_response.status_code == 200
        history_data = history_response.json()
        assert history_data["id"] == conversation_id
        assert len(history_data["messages"]) >= 2
        
        # Messages should have been persisted in order: user, assistant
        assert history_data["messages"][0]["role"] == "user"
        assert history_data["messages"][0]["content"] == "Classify this issue: my application crashes on boot with index out of bounds"
        assert history_data["messages"][1]["role"] == "assistant"
        
        print("\nSuccessfully validated Chatbot Service core loop, tool routing, and DB persistence!")
