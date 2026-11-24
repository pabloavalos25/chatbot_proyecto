from sqlalchemy import create_engine, inspect, text

from app.database import migrate_reservation_date


def test_legacy_reservation_schema_is_extended_without_losing_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE reservation_drafts (id INTEGER PRIMARY KEY, step INTEGER NOT NULL, name TEXT)")
        conn.exec_driver_sql("INSERT INTO reservation_drafts (id, step, name) VALUES (1, 0, 'Ejemplo')")

    migrate_reservation_date(engine)
    migrate_reservation_date(engine)

    assert 'date' in {column['name'] for column in inspect(engine).get_columns('reservation_drafts')}
    with engine.connect() as conn:
        assert conn.execute(text('SELECT id, step, name, date FROM reservation_drafts')).one() == (1, 0, 'Ejemplo', None)


def test_migration_ignores_missing_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    migrate_reservation_date(engine)
    assert 'reservation_drafts' not in inspect(engine).get_table_names()


def test_chat_works_after_migrating_a_legacy_database(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.database import Base, get_db
    from app.main import app

    monkeypatch.setenv('CHATBOT_AI_ENABLED', 'false')
    engine = create_engine(f"sqlite:///{tmp_path / 'old-chat.db'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE reservation_drafts DROP COLUMN date')
    migrate_reservation_date(engine)
    sessions = sessionmaker(bind=engine)

    def override():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        result = client.post('/api/chat', json={'customer_id': 'prueba', 'message': 'Hola'})
        assert result.status_code == 200
        assert result.json()['response']
        assert client.get('/api/chat/messages').json()['messages'][0]['content'] == 'Hola'
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
