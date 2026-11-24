import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setenv('CHATBOT_AI_ENABLED', 'false')
    monkeypatch.setenv('OPERATOR_TOKEN', 'operator-test-token-' + 'x' * 32)
    engine = create_engine(f'sqlite:///{tmp_path / "bye.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def override():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.mark.parametrize('farewell', ['chau', 'muchas gracias, nos vemos!', 'hasta luego, gracias', 'adiós', 'chao', 'hasta pronto'])
def test_goodbye_requests_survey(clients, farewell):
    reply = clients.post('/api/chat', json={'customer_id': 'test', 'message': farewell})
    assert reply.status_code == 200
    state = clients.get('/api/chat/messages').json()
    assert state['survey_pending'] is True
    assert state['messages'][-1]['role'] == 'bot'
    assert clients.post('/api/chat/close', json={'rating': 1}).status_code == 200


@pytest.mark.parametrize('text', ['gracias', 'buenas noches', 'chau, ¿a qué hora abren?', 'nos vemos pero quiero reservar'])
def test_ambiguous_messages_do_not_close(clients, text):
    assert clients.post('/api/chat', json={'customer_id': 'test', 'message': text}).status_code == 200
    assert clients.get('/api/chat/messages').json()['survey_pending'] is False


def test_active_reservation_does_not_close(clients):
    clients.post('/api/chat', json={'customer_id': 'test', 'message': 'quiero reservar'})
    response = clients.post('/api/chat', json={'customer_id': 'test', 'message': 'chau'}).json()
    assert 'solicitud' in response['response'].lower()
    assert 'nombre' in response['response'].lower()
    assert clients.get('/api/chat/messages').json()['survey_pending'] is False


def test_human_conversation_does_not_close(clients):
    clients.post('/api/chat', json={'customer_id': 'test', 'message': 'quiero hablar con una persona'})
    response = clients.post('/api/chat', json={'customer_id': 'test', 'message': 'chau'}).json()
    assert response['state'] == 'HUMAN'
    assert clients.get('/api/chat/messages').json()['survey_pending'] is False
