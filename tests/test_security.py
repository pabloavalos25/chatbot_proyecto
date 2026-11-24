import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def secure_clients(monkeypatch):
    monkeypatch.setenv('OPERATOR_TOKEN', 'x' * 40)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = override
    with TestClient(app) as first, TestClient(app) as second:
        yield first, second
    app.dependency_overrides.clear()
    engine.dispose()


def test_operator_endpoints_deny_missing_or_invalid_token(secure_clients):
    client, _ = secure_clients
    for headers in ({}, {'Authorization': 'Bearer wrong'}):
        assert client.get('/api/conversations', headers=headers).status_code == 401
        assert client.get('/api/conversations/1/messages', headers=headers).status_code == 401
        assert client.post('/api/conversations/1/messages', headers=headers, json={'message': 'hola'}).status_code == 401
        assert client.patch('/api/conversations/1/state', headers=headers, json={'state': 'BOT'}).status_code == 401
    assert client.get('/api/conversations', headers={'Authorization': 'Bearer ' + 'x' * 40}).status_code == 200


def test_clients_cannot_impersonate_by_selecting_customer_id(secure_clients):
    first, second = secure_clients
    a = first.post('/api/chat', json={'customer_id': 'victim', 'message': 'Hola'}).json()
    b = second.post('/api/chat', json={'customer_id': 'victim', 'message': 'Buenas tardes'}).json()
    assert a['conversation_id'] != b['conversation_id']
    again = first.post('/api/chat', json={'customer_id': 'different', 'message': 'Hola'}).json()
    assert again['conversation_id'] == a['conversation_id']
    assert first.get('/api/chat/messages').json()['messages'][0]['content'] == 'Hola'
    assert second.get('/api/chat/messages').json()['messages'][0]['content'] == 'Buenas tardes'
    assert 'Buenas tardes' not in [m['content'] for m in first.get('/api/chat/messages').json()['messages']]
    assert 'Hola' not in [m['content'] for m in second.get('/api/chat/messages').json()['messages']]
    assert len(second.get('/api/chat/messages').json()['messages']) == 2


def test_cookie_is_http_only_and_old_ids_are_not_reused(secure_clients):
    first, second = secure_clients
    initial = first.get('/api/chat/messages')
    assert initial.json() == {'state': 'BOT', 'messages': [], 'survey_pending': False, 'closed': False}
    assert 'httponly' in initial.headers['set-cookie'].lower()
    assert 'samesite=strict' in initial.headers['set-cookie'].lower()
    second.cookies.set('chat_session', 'client-controlled-invalid')
    replacement = second.get('/api/chat/messages')
    assert replacement.json()['messages'] == []
    assert 'set-cookie' in replacement.headers


def test_unconfigured_or_short_operator_token_denies_access(secure_clients, monkeypatch):
    client, _ = secure_clients
    for token in ('', 'weak'):
        monkeypatch.setenv('OPERATOR_TOKEN', token)
        assert client.get('/api/conversations', headers={'Authorization': 'Bearer ' + token}).status_code == 401
