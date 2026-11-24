from tests.test_chat import setup_client
from datetime import date, timedelta


def test_reservation_collects_fields_without_promising_confirmation(setup_client):
    client, factory = setup_client
    def send(text):
        return client.post('/api/chat', json={'customer_id': 'x', 'message': text}).json()
    date_text = (date.today() + timedelta(days=30)).strftime('%d/%m/%Y')
    first = send('Quiero reservar')
    assert 'nombre' in first['response'].lower()
    for value, expected in [('Ana Pérez', 'vehículo'), ('camioneta', 'color'), ('azul', 'patente'), ('AB123CD', 'fecha'), (date_text, 'entrada'), ('10:00', 'salida')]:
        assert expected in send(value)['response'].lower()
    final = send('12:30')
    assert 'solicitud' in final['response'].lower()
    assert 'no está confirmada' in final['response'].lower()
    assert final['state'] == 'HUMAN'
    from app.models import CommercialRequest
    from sqlalchemy import select
    with factory() as db:
        records = db.scalars(select(CommercialRequest)).all()
        assert any(all(x in row.message for x in ('Ana Pérez', 'camioneta', 'azul', 'AB123CD', date_text, '10:00', '12:30')) for row in records)


def test_reservation_human_handoff_takes_precedence(setup_client):
    client, _ = setup_client
    client.post('/api/chat', json={'customer_id': 'x', 'message': 'quiero reservar'})
    response = client.post('/api/chat', json={'customer_id': 'x', 'message': 'quiero hablar con una persona'}).json()
    assert response['state'] == 'HUMAN'


def test_rejects_unsupported_vehicle_and_invalid_hour_without_advancing(setup_client):
    client, _ = setup_client
    def send(message):
        return client.post('/api/chat', json={'customer_id': 'x', 'message': message}).json()['response'].lower()
    send('Quiero reservar')
    send('Laura')
    assert 'auto' in send('moto')
    assert 'color' in send('auto')
    send('blanco')
    send('ABC123')
    send((date.today() + timedelta(days=30)).strftime('%d/%m/%Y'))
    assert 'hora' in send('cualquier hora')
    assert 'salida' in send('14:00')


def test_reservation_can_be_cancelled_without_creating_completed_request(setup_client):
    client, _ = setup_client
    def send(message):
        return client.post('/api/chat', json={'customer_id': 'x', 'message': message}).json()['response'].lower()
    send('Reservar')
    assert 'cancel' in send('cancelar')
    assert 'horarios' in send('¿Qué horario tienen?')


def test_reservation_questions_do_not_become_personal_data(setup_client):
    client, _ = setup_client
    def send(message):
        return client.post('/api/chat', json={'customer_id': 'x', 'message': message}).json()['response'].lower()
    send('Quiero reservar')
    answer = send('¿Cuánto cuesta?')
    assert 'precio' in answer and 'nombre' in answer
    assert 'vehículo' in send('Ana')


def test_reservation_reprompts_invalid_date_plate_and_asks_about_next_day(setup_client):
    client, _ = setup_client
    def send(message):
        return client.post('/api/chat', json={'customer_id': 'x', 'message': message}).json()['response'].lower()
    for message in ['Quiero reservar', 'Ana', 'auto', 'rojo']:
        send(message)
    assert 'patente' in send('???')
    assert 'fecha' in send('ABC123')
    assert 'fecha' in send('31/02/2027')
    assert 'fecha' in send((date.today() - timedelta(days=1)).strftime('%d/%m/%Y'))
    assert 'entrada' in send((date.today() + timedelta(days=30)).strftime('%d/%m/%Y'))
    assert 'salida' in send('22:00')
    assert 'día siguiente' in send('08:00')
    assert 'solicitud' in send('sí')
