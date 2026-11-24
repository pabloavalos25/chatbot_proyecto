from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    pass


url = Settings().database_url
engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session


def migrate_reservation_date(target_engine):
    """Add the optional date field to legacy local databases, if required."""
    if target_engine.dialect.name != 'sqlite':
        raise ValueError('La migración solo admite SQLite')
    with target_engine.begin() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        columns = connection.exec_driver_sql('PRAGMA table_info(reservation_drafts)').fetchall()
        if columns and 'date' not in {column[1] for column in columns}:
            connection.exec_driver_sql('ALTER TABLE reservation_drafts ADD COLUMN date TEXT')
