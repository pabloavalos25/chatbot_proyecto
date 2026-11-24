from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import ClosureRequest, CommercialRequest, Conversation, Customer, Message, ReservationDraft, Survey


def test_operator_deletes_only_closed_conversation_and_related_data(tmp_path, monkeypatch):
    monkeypatch.setenv('CHATBOT_AI_ENABLED', 'false')
    token = 'test-operator-token-' + 'x' * 40
    monkeypatch.setenv('OPERATOR_TOKEN', token)
    engine = create_engine(f'sqlite:///{tmp_path / "delete.db"}', connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override
    customer, other, operator = TestClient(app), TestClient(app), TestClient(app)
    headers = {'Authorization': f'Bearer {token}'}
    try:
        cid = customer.post('/api/chat', json={'customer_id': 'test', 'message': 'Quiero reservar un lugar'}).json()['conversation_id']
        other_id = other.post('/api/chat', json={'customer_id': 'other', 'message': 'Hola'}).json()['conversation_id']
        assert operator.delete(f'/api/conversations/{cid}').status_code == 401
        assert operator.delete(f'/api/conversations/{cid}', headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert operator.delete(f'/api/conversations/{cid}', headers=headers).status_code == 409
        assert operator.post(f'/api/conversations/{cid}/close', headers=headers).status_code == 200
        assert operator.delete(f'/api/conversations/{cid}', headers=headers).status_code == 409
        assert customer.post('/api/chat/close', json={'rating': 1, 'reason': 'bien'}).status_code == 200
        with sessions() as db:
            customer_id = db.get(Conversation, cid).customer_id
            assert db.scalar(select(CommercialRequest.id).where(CommercialRequest.conversation_id == cid))
        assert operator.delete(f'/api/conversations/{cid}', headers=headers).status_code == 200
        assert operator.delete(f'/api/conversations/{cid}', headers=headers).status_code == 404
        with sessions() as db:
            assert db.get(Conversation, cid) is None
            assert db.get(Customer, customer_id) is None
            for cls in (Message, CommercialRequest, ReservationDraft, ClosureRequest, Survey):
                assert db.scalar(select(cls.id).where(cls.conversation_id == cid)) is None
            assert db.get(Conversation, other_id) is not None
            assert db.scalar(select(Message.id).where(Message.conversation_id == other_id))
    finally:
        customer.close()
        other.close()
        operator.close()
        app.dependency_overrides.clear()
        engine.dispose()


def test_deletion_failure_rolls_back_all_records(tmp_path, monkeypatch):
    monkeypatch.setenv('CHATBOT_AI_ENABLED', 'false')
    token = 'test-operator-token-' + 'x' * 40
    monkeypatch.setenv('OPERATOR_TOKEN', token)
    engine = create_engine(f'sqlite:///{tmp_path / "rollback.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override
    customer = TestClient(app)
    operator = TestClient(app, raise_server_exceptions=False)
    headers = {'Authorization': f'Bearer {token}'}
    try:
        cid = customer.post('/api/chat', json={'customer_id': 'test', 'message': 'Hola'}).json()['conversation_id']
        assert operator.post(f'/api/conversations/{cid}/close', headers=headers).status_code == 200
        assert customer.post('/api/chat/close', json={'rating': 2}).status_code == 200
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TRIGGER block_survey_delete BEFORE DELETE ON surveys BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        assert operator.delete(f'/api/conversations/{cid}', headers=headers).status_code == 500
        with sessions() as db:
            assert db.get(Conversation, cid) is not None
            for cls in (Message, ClosureRequest, Survey):
                assert db.scalar(select(cls.id).where(cls.conversation_id == cid)) is not None
    finally:
        customer.close()
        operator.close()
        app.dependency_overrides.clear()
        engine.dispose()
