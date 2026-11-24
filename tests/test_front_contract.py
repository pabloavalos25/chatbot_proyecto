"""Smoke test for the browser's local client/operator API contract."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


def test_local_chat_and_operator_flow(tmp_path, monkeypatch):
    monkeypatch.setenv('CHATBOT_AI_ENABLED', 'false')
    token = 'test-operator-credential-' + ('a' * 32)
    monkeypatch.setenv('OPERATOR_TOKEN', token)
    engine = create_engine(f'sqlite:///{tmp_path / "chat.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def session_override():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = session_override
    # Avoid running the application's lifespan against the real default database.
    client = TestClient(app)
    try:
        html = client.get('/').text
        assert 'class="phone"' in html
        assert '/api/chat/messages' in html
        assert 'operator-token' in html
        initial = client.get('/api/chat/messages')
        assert initial.json() == {'state': 'BOT', 'messages': [], 'survey_pending': False, 'closed': False}
        assert 'httponly' in initial.headers['set-cookie'].lower()
        result = client.post('/api/chat', json={'customer_id': 'cliente', 'message': '¿Qué condiciones tiene el abono mensual?'})
        assert result.status_code == 200
        assert result.json()['response']
        history = client.get('/api/chat/messages').json()
        assert history['messages'][0]['content'] == '¿Qué condiciones tiene el abono mensual?'
        assert history['messages'][1]['content'] == result.json()['response']
        assert client.get('/api/conversations').status_code == 401
        listing = client.get('/api/conversations', headers={'Authorization': f'Bearer {token}'})
        assert listing.status_code == 200
        assert len(listing.json()) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
