from contextlib import asynccontextmanager
from pathlib import Path
import hashlib
import re
import secrets

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db, migrate_reservation_date
from app.config import Settings
from app.domain.ai_engine import AIEngine
from app.domain.engine import RuleEngine
from app.integrations.openai_provider import OpenAIProvider
from app.integrations.ollama_provider import OllamaProvider
from app.schemas import ChatRequest, ChatResponse, CloseChatRequest, OperatorMessage, StateUpdate
from app.models import ClosureRequest, Conversation, ConversationState, Customer, Message, Survey
from app.service import process_message


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine.dialect.name == 'sqlite':
        migrate_reservation_date(engine)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Chatbot de servicios", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


def require_operator(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    expected = Settings().operator_token
    if len(expected) < 32 or credentials is None or not secrets.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Acceso de operador no autorizado", headers={"WWW-Authenticate": "Bearer"})


def client_id(response: Response, chat_session: str | None = Cookie(default=None)) -> str:
    if chat_session is None or re.fullmatch(r'[A-Za-z0-9_-]{43}', chat_session) is None:
        chat_session = secrets.token_urlsafe(32)
        response.set_cookie('chat_session', chat_session, httponly=True, samesite='strict', path='/', max_age=60 * 60 * 24 * 365)
    return 'session:' + hashlib.sha256(chat_session.encode()).hexdigest()


def lock_sqlite_writes(db: Session):
    # Serialize checking closure and writing for the supported local SQLite database.
    if db.get_bind().dialect.name == 'sqlite':
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')


@app.get("/", include_in_schema=False)
def local_interface():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get('/static/assets/negocio.png', include_in_schema=False)
def business_image():
    return FileResponse(Path(__file__).parent / 'static' / 'assets' / 'negocio.png', media_type='image/png')


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, identity: str = Depends(client_id), db: Session = Depends(get_db)):
    lock_sqlite_writes(db)
    conversation = db.scalar(select(Conversation).join(Customer).where(Customer.external_id == identity))
    if conversation is not None and db.scalar(select(Survey).where(Survey.conversation_id == conversation.id)):
        raise HTTPException(status_code=409, detail='La conversación está cerrada')
    if conversation is not None and db.scalar(select(ClosureRequest).where(ClosureRequest.conversation_id == conversation.id)):
        raise HTTPException(status_code=409, detail='La encuesta está pendiente')
    return process_message(db, identity, payload.message, make_chat_engine())


@app.post('/api/chat/close')
def close_chat(payload: CloseChatRequest, response: Response, identity: str = Depends(client_id), db: Session = Depends(get_db)):
    lock_sqlite_writes(db)
    conversation = db.scalar(select(Conversation).join(Customer).where(Customer.external_id == identity))
    if conversation is None:
        raise HTTPException(status_code=404, detail='Conversación no encontrada')
    if db.scalar(select(Survey).where(Survey.conversation_id == conversation.id)):
        raise HTTPException(status_code=409, detail='La conversación ya está cerrada')
    if not db.scalar(select(ClosureRequest).where(ClosureRequest.conversation_id == conversation.id)):
        raise HTTPException(status_code=409, detail='El operador aún no solicitó el cierre')
    reason = payload.reason.strip() if payload.reason else None
    db.add(Survey(conversation_id=conversation.id, rating=payload.rating, reason=reason or None))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(Survey).where(Survey.conversation_id == conversation.id)):
            raise HTTPException(status_code=409, detail='La conversación ya está cerrada')
        raise
    response.delete_cookie('chat_session', path='/')
    return {'status': 'closed'}


@app.post('/api/chat/new-session')
def new_session(response: Response, identity: str = Depends(client_id), db: Session = Depends(get_db)):
    conversation = db.scalar(select(Conversation).join(Customer).where(Customer.external_id == identity))
    if conversation is None:
        raise HTTPException(status_code=404, detail='Conversación no encontrada')
    if not db.scalar(select(Survey.id).where(Survey.conversation_id == conversation.id)):
        raise HTTPException(status_code=409, detail='La conversación aún no está cerrada')
    response.delete_cookie('chat_session', path='/')
    return {'status': 'new_session'}


@app.get('/api/chat/messages')
def client_messages(identity: str = Depends(client_id), db: Session = Depends(get_db)):
    conversation = db.scalar(select(Conversation).join(Customer).where(Customer.external_id == identity))
    if conversation is None:
        return {'state': 'BOT', 'messages': [], 'survey_pending': False, 'closed': False}
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id))
    closed = bool(db.scalar(select(Survey.id).where(Survey.conversation_id == conversation.id)))
    requested = bool(db.scalar(select(ClosureRequest.id).where(ClosureRequest.conversation_id == conversation.id)))
    return {'state': conversation.state, 'survey_pending': requested and not closed, 'closed': closed, 'messages': [
        {'id': m.id, 'role': m.role, 'content': m.content, 'created_at': m.created_at} for m in messages
    ]}


def make_chat_engine():
    fallback = RuleEngine()
    settings = Settings()
    if settings.chatbot_ai_enabled and settings.chatbot_ai_provider == "ollama":
        return AIEngine(fallback, OllamaProvider(settings.ollama_model))
    if settings.chatbot_ai_enabled and settings.chatbot_ai_provider == "openai" and settings.openai_api_key.strip():
        return AIEngine(fallback, OpenAIProvider(settings.openai_api_key, settings.openai_model))
    return fallback


def find_conversation(db: Session, conversation_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return conversation


@app.get("/api/conversations", dependencies=[Depends(require_operator)])
def list_conversations(state: ConversationState | None = None, db: Session = Depends(get_db)):
    closed = select(Survey.id).where(Survey.conversation_id == Conversation.id).exists()
    requested = select(ClosureRequest.id).where(ClosureRequest.conversation_id == Conversation.id).exists()
    query = select(Conversation, Customer.external_id, closed, requested).join(Customer, Customer.id == Conversation.customer_id)
    if state is not None:
        query = query.where(Conversation.state == state, ~select(Survey.id).where(Survey.conversation_id == Conversation.id).exists())
    return [{"id": c.id, "customer_id": customer_id, "state": c.state, "closed": is_closed, "survey_pending": is_requested and not is_closed, "created_at": c.created_at}
            for c, customer_id, is_closed, is_requested in db.execute(query.order_by(Conversation.id.desc()))]


@app.post('/api/conversations/{conversation_id}/close', dependencies=[Depends(require_operator)])
def request_close(conversation_id: int, db: Session = Depends(get_db)):
    lock_sqlite_writes(db)
    find_conversation(db, conversation_id)
    if db.scalar(select(Survey.id).where(Survey.conversation_id == conversation_id)) or db.scalar(select(ClosureRequest.id).where(ClosureRequest.conversation_id == conversation_id)):
        raise HTTPException(status_code=409, detail='El cierre ya fue solicitado')
    db.add(ClosureRequest(conversation_id=conversation_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(ClosureRequest.id).where(ClosureRequest.conversation_id == conversation_id)):
            raise HTTPException(status_code=409, detail='El cierre ya fue solicitado')
        raise
    return {'status': 'survey_pending'}


@app.get("/api/conversations/{conversation_id}/messages", dependencies=[Depends(require_operator)])
def conversation_messages(conversation_id: int, db: Session = Depends(get_db)):
    find_conversation(db, conversation_id)
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id))
    return [{"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in messages]


@app.get('/api/conversations/{conversation_id}/surveys', dependencies=[Depends(require_operator)])
def conversation_surveys(conversation_id: int, db: Session = Depends(get_db)):
    find_conversation(db, conversation_id)
    surveys = db.scalars(select(Survey).where(Survey.conversation_id == conversation_id))
    return [{'id': s.id, 'rating': s.rating, 'reason': s.reason, 'created_at': s.created_at} for s in surveys]


@app.post("/api/conversations/{conversation_id}/messages", status_code=201, dependencies=[Depends(require_operator)])
def operator_message(conversation_id: int, payload: OperatorMessage, db: Session = Depends(get_db)):
    lock_sqlite_writes(db)
    conversation = find_conversation(db, conversation_id)
    if db.scalar(select(Survey).where(Survey.conversation_id == conversation.id)) or db.scalar(select(ClosureRequest).where(ClosureRequest.conversation_id == conversation.id)):
        raise HTTPException(status_code=409, detail='La conversación está cerrada')
    if conversation.state != ConversationState.HUMAN:
        raise HTTPException(status_code=409, detail="La conversación no está en atención humana")
    message = Message(conversation_id=conversation.id, role="operator", content=payload.message)
    db.add(message)
    db.commit()
    db.refresh(message)
    return {"id": message.id, "role": message.role, "content": message.content, "created_at": message.created_at}


@app.patch("/api/conversations/{conversation_id}/state", dependencies=[Depends(require_operator)])
def update_state(conversation_id: int, payload: StateUpdate, db: Session = Depends(get_db)):
    lock_sqlite_writes(db)
    conversation = find_conversation(db, conversation_id)
    if db.scalar(select(Survey).where(Survey.conversation_id == conversation.id)) or db.scalar(select(ClosureRequest).where(ClosureRequest.conversation_id == conversation.id)):
        raise HTTPException(status_code=409, detail='La conversación está cerrada')
    conversation.state = payload.state
    db.commit()
    return {"id": conversation.id, "state": conversation.state}


@app.delete('/api/conversations/{conversation_id}', dependencies=[Depends(require_operator)])
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import delete
    from app.models import CommercialRequest, ReservationDraft

    lock_sqlite_writes(db)
    conversation = find_conversation(db, conversation_id)
    if not db.scalar(select(Survey.id).where(Survey.conversation_id == conversation_id)):
        raise HTTPException(status_code=409, detail='Solo se pueden eliminar conversaciones cerradas')
    customer_id = conversation.customer_id
    for model in (Message, CommercialRequest, ReservationDraft, ClosureRequest, Survey):
        db.execute(delete(model).where(model.conversation_id == conversation_id))
    db.delete(conversation)
    db.flush()
    db.execute(delete(Customer).where(Customer.id == customer_id))
    db.commit()
    return {'status': 'deleted'}
