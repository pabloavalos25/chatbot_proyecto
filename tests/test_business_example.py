import pytest

from app.domain.engine import RuleEngine


@pytest.mark.parametrize(('question', 'expected'), [
    ('¿Cuál es el horario?', ('07:00', '23:00', 'días')),
    ('¿Aceptan camionetas?', ('autos', 'camionetas', 'camiones')),
    ('¿Qué medios de pago aceptan?', ('efectivo', 'mercado pago', 'crédito', 'débito', 'qr')),
])
def test_consultas_con_datos_de_ejemplo(question, expected):
    answer = RuleEngine().respond(question).text.lower()
    for item in expected:
        assert item in answer


def test_consulta_combinada_incluye_datos_y_aclara_precio_desconocido():
    answer = RuleEngine().respond('¿Qué horario tienen, cuánto cuesta y aceptan tarjeta?').text.lower()
    for item in ('07:00', '23:00', 'efectivo', 'precios', 'confirm'):
        assert item in answer


def test_confirma_apertura_de_domingo():
    answer = RuleEngine().respond('¿Abren los domingos?').text.lower()
    assert '07:00' in answer
    assert 'todos los días' in answer


def test_horarios_y_medios_de_pago_en_la_misma_consulta():
    answer = RuleEngine().respond('¿Abren los sábados y se puede pagar con QR?').text.lower()
    for item in ('07:00', '23:00', 'días', 'qr'):
        assert item in answer


@pytest.mark.parametrize('question', ['¿Qué tarjetas aceptan?', '¿Puedo pagar con American Express?'])
def test_tarjetas_se_limitan_a_visa_y_mastercard(question):
    answer = RuleEngine().respond(question).text.lower()
    assert 'solo' in answer and 'visa' in answer and 'mastercard' in answer


def test_qr_se_genera_al_confirmar_sin_prometer_pago_automatico():
    answer = RuleEngine().respond('¿Cómo funciona el QR?').text.lower()
    assert 'qr' in answer and 'confirm' in answer and 'reserva' in answer and 'abono' in answer


def test_pregunta_por_qr_de_reserva_no_inicia_solicitud():
    reply = RuleEngine().respond('¿Cómo se paga con QR una reserva?')
    assert reply.intent == 'payment'
    assert 'qr' in reply.text.lower()


def test_vehiculos_no_listados_no_son_inventados():
    answer = RuleEngine().respond('¿Puedo guardar una moto?').text.lower()
    assert 'otros tipos de vehículo no están confirmados' in answer


def test_direccion_sigue_sin_confirmar():
    answer = RuleEngine().respond('¿Dónde están?').text.lower()
    assert 'dirección' in answer and 'confirm' in answer
