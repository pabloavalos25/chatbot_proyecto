"""Exercise the complete local chat journey using an isolated database."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


def test_full_local_journey(tmp_path, monkeypatch):
    monkeypatch.setenv('CHATBOT_AI_ENABLED', 'false')
    token = 'integration-test-operator-token-' + 'x' * 32
    monkeypatch.setenv('OPERATOR_TOKEN', token)
    engine = create_engine(f'sqlite:///{tmp_path / "journey.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def session_override():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = session_override
    customer = TestClient(app)
    other = TestClient(app)
    operator = TestClient(app)
    headers = {'Authorization': f'Bearer {token}'}
    try:
        first = customer.post('/api/chat', json={'customer_id': 'test', 'message': '¿Cuál es el horario y qué medios de pago aceptan?'}).json()
        assert all(value in first['response'].lower() for value in ('07:00', '23:00', 'efectivo', 'qr'))
        cid = first['conversation_id']
        other.post('/api/chat', json={'customer_id': 'test', 'message': 'Mensaje privado de otro cliente'})
        assert 'Mensaje privado de otro cliente' not in [m['content'] for m in customer.get('/api/chat/messages').json()['messages']]

        assert operator.get('/api/conversations').status_code == 401
        handoff = customer.post('/api/chat', json={'customer_id': 'test', 'message': 'Quiero hablar con una persona'}).json()
        assert handoff['state'] == 'HUMAN'
        waiting = customer.post('/api/chat', json={'customer_id': 'test', 'message': 'Tengo una consulta'}).json()
        assert waiting['response'] is None
        assert cid in [c['id'] for c in operator.get('/api/conversations', headers=headers, params={'state': 'HUMAN'}).json()]
        reply = operator.post(f'/api/conversations/{cid}/messages', headers=headers, json={'message': 'Hola, te atiendo'} )
        assert reply.status_code == 201
        assert 'Hola, te atiendo' in [m['content'] for m in customer.get('/api/chat/messages').json()['messages']]
        assert operator.patch(f'/api/conversations/{cid}/state', headers=headers, json={'state': 'BOT'}).status_code == 200
        assert customer.post('/api/chat', json={'customer_id': 'test', 'message': 'Hola'}).json()['response']

        assert operator.post(f'/api/conversations/{cid}/close', headers=headers).status_code == 200
        assert customer.post('/api/chat/close', json={'rating': 1, 'reason': 'Fue sencillo'}).status_code == 200
        assert operator.get(f'/api/conversations/{cid}/surveys').status_code == 401
        survey = operator.get(f'/api/conversations/{cid}/surveys', headers=headers).json()
        assert len(survey) == 1 and survey[0]['rating'] == 1 and survey[0]['reason'] == 'Fue sencillo'
        new = customer.get('/api/chat/messages').json()
        assert new['state'] == 'BOT' and new['messages'] == []
        assert operator.post(f'/api/conversations/{cid}/messages', headers=headers, json={'message': 'Tarde'}).status_code == 409
    finally:
        customer.close()
        other.close()
        operator.close()
        app.dependency_overrides.clear()
        engine.dispose()
