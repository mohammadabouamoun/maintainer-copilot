import pytest
import uuid
import json
from fastapi.testclient import TestClient
from app.main import app

@pytest.mark.asyncio
async def test_rag_pipeline_flow():
    """
    End-to-End Integration test verifying authorization, RAG endpoint orchestration,
    OpenTelemetry trace ID returns, and document snapshot writes to MinIO.
    """
    unique_id = uuid.uuid4().hex[:6]
    user_email = f"rag_user_{unique_id}@example.com"
    password = "SecurePassword123!"
    conversation_id = f"conv_{unique_id}"

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

        # 3. Hit /rag/query unauthorized (Assert 401 Unauthorized)
        unauth_response = client.post(
            "/rag/query",
            json={
                "question": "how do I align Series?",
                "conversation_id": conversation_id
            }
        )
        assert unauth_response.status_code == 401

        # 4. Hit /rag/query authorized (Assert 200 OK)
        auth_response = client.post(
            "/rag/query",
            json={
                "question": "how do I align Series?",
                "conversation_id": conversation_id
            },
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert auth_response.status_code == 200
        res_data = auth_response.json()
        assert "answer" in res_data
        assert "chunks" in res_data
        assert "trace_id" in res_data
        assert len(res_data["chunks"]) > 0

        # 5. Verify MinIO snapshot upload
        minio_client = app.state.minio_client
        objects = list(minio_client.list_objects("chunks", prefix=f"{conversation_id}/", recursive=True))
        assert len(objects) >= 1
        
        # Read snapshot content from MinIO
        obj_name = objects[0].object_name
        data_stream = minio_client.get_object("chunks", obj_name)
        chunks_snapshot = json.loads(data_stream.read().decode("utf-8"))
        assert len(chunks_snapshot) > 0
        assert "id" in chunks_snapshot[0]
        assert "content" in chunks_snapshot[0]
        print("\nSuccessfully validated RAG pipeline e2e with MinIO auditing snapshot storage!")
