import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.engine import RuleEngine, Reply, contains, normalize
from app.models import ClosureRequest, CommercialRequest, Conversation, ConversationState, Customer, Message, ReservationDraft
from app.schemas import ChatResponse


RESERVATION_FIELDS = ('name', 'vehicle', 'color', 'plate', 'date', 'arrival', 'departure')
RESERVATION_QUESTIONS = (
    '¿Cuál es tu nombre?',
    '¿Qué vehículo querés estacionar?',
    '¿De qué color es el vehículo?',
    '¿Cuál es la patente?',
    '¿Para qué fecha necesitás la reserva? Indicá DD/MM/AAAA.',
    '¿Cuál sería la hora aproximada de entrada?',
    '¿Cuál sería la hora aproximada de salida?',
)


def is_clear_farewell(text: str) -> bool:
    if '?' in text or '¿' in text:
        return False
    normalized = normalize(text)
    return bool(re.fullmatch(
        r'(?:(?:muchas )?gracias )?(?:chau|chao|adios|hasta luego|hasta pronto|nos vemos)(?: (?:muchas )?gracias)?',
        normalized,
    ))


def reservation_reply(db: Session, conversation: Conversation, text: str, reply: Reply) -> Reply:
    draft = db.scalar(select(ReservationDraft).where(ReservationDraft.conversation_id == conversation.id))
    normalized = normalize(text)
    if reply.handoff:
        return reply
    if draft is not None:
        if is_clear_farewell(text):
            question = RESERVATION_QUESTIONS[draft.step] if draft.step < len(RESERVATION_FIELDS) else '¿La salida es al día siguiente? Respondé sí o no.'
            return Reply('commercial', 'Tenés una solicitud de reserva en curso. Podés cancelarla o continuar: ' + question)
        if contains(normalized, 'cancelar', 'cancela', 'cancelar reserva', 'cancelar solicitud'):
            db.delete(draft)
            return Reply('commercial', 'Cancelé la carga de esta solicitud. ¿Puedo ayudarte con otra consulta?')
        if draft.step == len(RESERVATION_FIELDS):
            if normalized in ('si', 'sí', 'correcto'):
                draft.departure += ' (día siguiente)'
                return finish_reservation(db, conversation, draft)
            if normalized in ('no', 'no es', 'no gracias'):
                draft.step -= 1
                return Reply('commercial', 'Indicá nuevamente la hora aproximada de salida en formato 24 horas.')
            return Reply('commercial', '¿La salida es al día siguiente? Respondé sí o no.')
        question = ('?' in text or '¿' in text or contains(normalized, 'cuanto cuesta', 'cuanto sale', 'que horario', 'como pago', 'hay lugar'))
        if question and reply.intent in ('prices', 'hours', 'payment', 'availability', 'security', 'location', 'services'):
            return Reply('commercial', reply.text + ' Para seguir con la solicitud: ' + RESERVATION_QUESTIONS[draft.step])
        if RESERVATION_FIELDS[draft.step] == 'vehicle' and not contains(normalized, 'auto', 'autos', 'coche', 'camioneta', 'camion', 'camiones'):
            return Reply('commercial', 'Por ahora figuran autos, camionetas y camiones. Indicá uno de esos vehículos o pedí hablar con una persona.')
        if RESERVATION_FIELDS[draft.step] == 'plate' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 -]{3,14}', text.strip()):
            return Reply('commercial', 'Indicá la patente con letras o números, sin caracteres especiales.')
        if RESERVATION_FIELDS[draft.step] == 'date':
            try:
                requested_date = datetime.strptime(text.strip(), '%d/%m/%Y').date()
            except ValueError:
                return Reply('commercial', 'Indicá una fecha válida en formato DD/MM/AAAA.')
            if requested_date < datetime.now().astimezone().date():
                return Reply('commercial', 'La fecha ya pasó. Indicá una fecha de hoy o posterior en formato DD/MM/AAAA.')
        if RESERVATION_FIELDS[draft.step] in ('arrival', 'departure') and not re.fullmatch(r'(?:[01]?\d|2[0-3])(?::[0-5]\d)?(?:\s*(?:hs|h))?', text.strip().lower()):
            return Reply('commercial', 'Indicá la hora aproximada en formato 24 horas, por ejemplo 14:30.')
        setattr(draft, RESERVATION_FIELDS[draft.step], text.strip())
        draft.step += 1
        if draft.step < len(RESERVATION_FIELDS):
            return Reply('commercial', RESERVATION_QUESTIONS[draft.step])
        def minutes(value):
            digits = re.match(r'(\d{1,2})(?::(\d{2}))?', value)
            return int(digits.group(1)) * 60 + int(digits.group(2) or 0)
        if minutes(draft.departure) <= minutes(draft.arrival):
            return Reply('commercial', 'La salida indicada es igual o anterior a la entrada. ¿Es al día siguiente? Respondé sí o no.')
        return finish_reservation(db, conversation, draft)
    if reply.commercial and contains(normalized, 'reservar', 'reserva', 'apartarme un lugar'):
        db.add(ReservationDraft(conversation_id=conversation.id, step=0))
        return Reply('commercial', 'Puedo tomar los datos de tu solicitud. La reserva requiere confirmación. ' + RESERVATION_QUESTIONS[0], commercial=True)
    return reply


def finish_reservation(db: Session, conversation: Conversation, draft: ReservationDraft) -> Reply:
    summary = (f'Solicitud de reserva: nombre {draft.name}; vehículo {draft.vehicle}; color {draft.color}; '
               f'patente {draft.plate}; fecha {draft.date}; entrada aproximada {draft.arrival}; salida aproximada {draft.departure}.')
    db.add(CommercialRequest(conversation_id=conversation.id, message=summary))
    db.delete(draft)
    return Reply('commercial', 'Guardé tu solicitud y la dejé para revisión de una persona. La reserva no está confirmada; disponibilidad y precio deben consultarse con el equipo.', handoff=True)


def process_message(db: Session, customer_id: str, text: str, engine: RuleEngine) -> ChatResponse:
    customer = db.scalar(select(Customer).where(Customer.external_id == customer_id))
    if customer is None:
        customer = Customer(external_id=customer_id)
        db.add(customer)
        db.flush()
    conversation = db.scalar(select(Conversation).where(Conversation.customer_id == customer.id))
    if conversation is None:
        conversation = Conversation(customer_id=customer.id, state=ConversationState.BOT)
        db.add(conversation)
        db.flush()
    db.add(Message(conversation_id=conversation.id, role="customer", content=text))
    response = intent = None
    if conversation.state == ConversationState.BOT:
        draft = db.scalar(select(ReservationDraft.id).where(ReservationDraft.conversation_id == conversation.id))
        if draft is None and is_clear_farewell(text):
            reply = Reply('goodbye', '¡Hasta luego! Gracias por contactarnos. Antes de irte, contanos cómo fue tu atención.')
            db.add(ClosureRequest(conversation_id=conversation.id))
        else:
            reply = reservation_reply(db, conversation, text, engine.respond(text))
        response, intent = reply.text, reply.intent
        if reply.handoff:
            conversation.state = ConversationState.HUMAN
        if reply.commercial:
            db.add(CommercialRequest(conversation_id=conversation.id, message=text))
        db.add(Message(conversation_id=conversation.id, role="bot", content=response))
    db.commit()
    return ChatResponse(conversation_id=conversation.id, state=conversation.state, response=response, intent=intent)
