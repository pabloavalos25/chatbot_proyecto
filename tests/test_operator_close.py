from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


def test_operator_requests_survey_and_only_owner_can_answer(monkeypatch):
    monkeypatch.setenv('OPERATOR_TOKEN', 'x' * 40)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client, TestClient(app) as other:
            cid = client.post('/api/chat', json={'customer_id': 'a', 'message': 'Hola'}).json()['conversation_id']
            assert client.post('/api/chat/close', json={'rating': 1}).status_code == 409
            assert other.post(f'/api/conversations/{cid}/close').status_code == 401
            assert other.post(f'/api/conversations/{cid}/close', headers={'Authorization': 'Bearer ' + 'x' * 40}).status_code == 200
            assert client.get('/api/chat/messages').json()['survey_pending'] is True
            assert client.get('/api/chat/messages').json()['survey_pending'] is True  # survives reload
            assert other.post(f'/api/conversations/{cid}/close', headers={'Authorization': 'Bearer ' + 'x' * 40}).status_code == 409
            assert client.post('/api/chat', json={'customer_id': 'a', 'message': 'Otro'}).status_code == 409
            assert other.patch(f'/api/conversations/{cid}/state', json={'state': 'BOT'}, headers={'Authorization': 'Bearer ' + 'x' * 40}).status_code == 409
            assert client.post('/api/chat/new-session').status_code == 409
            assert other.post('/api/chat/close', json={'rating': 1}).status_code == 404
            old_cookie = client.cookies.get('chat_session')
            assert client.post('/api/chat/close', json={'rating': 1, 'reason': 'Bien'}).status_code == 200
            client.cookies.set('chat_session', old_cookie, domain='testserver.local', path='/')
            assert client.get('/api/chat/messages').json()['closed'] is True
            assert client.post('/api/chat/new-session').status_code == 200
            assert client.get('/api/chat/messages').json()['messages'] == []
            surveys = other.get(f'/api/conversations/{cid}/surveys', headers={'Authorization': 'Bearer ' + 'x' * 40}).json()
            assert surveys[0]['rating'] == 1 and surveys[0]['reason'] == 'Bien'
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_message_waiting_on_close_cannot_write_after_close(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import text
    monkeypatch.setenv('OPERATOR_TOKEN', 'x' * 40)
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={'check_same_thread': False, 'timeout': 10})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            cid = client.post('/api/chat', json={'customer_id': 'a', 'message': 'Hola'}).json()['conversation_id']
            cookie = client.cookies.get('chat_session')
        with engine.connect() as lock:
            lock.exec_driver_sql('BEGIN IMMEDIATE')
            lock.execute(text('INSERT INTO closure_requests (conversation_id, created_at) VALUES (:cid, CURRENT_TIMESTAMP)'), {'cid': cid})
            def send():
                with TestClient(app, raise_server_exceptions=False) as client:
                    client.cookies.set('chat_session', cookie)
                    return client.post('/api/chat', json={'customer_id': 'a', 'message': 'Demasiado tarde'}).status_code
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(send)
                import time
                time.sleep(0.25)
                lock.commit()
                assert future.result(timeout=10) == 409
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
