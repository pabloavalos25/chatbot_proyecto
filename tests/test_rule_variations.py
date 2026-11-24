import pytest

from app.domain.engine import RuleEngine


@pytest.mark.parametrize(('question', 'topic'), [
    ('¿Abren los domingos?', 'hours'),
    ('¿Puedo pagar con débito?', 'payment'),
    ('¿Aceptan autos?', 'vehicles'),
])
def test_consultas_habituales_reconocidas_sin_inventar(question, topic):
    reply = RuleEngine().respond(question)
    assert reply.intent == topic
    assert {'hours': '07:00', 'payment': 'débito', 'vehicles': 'autos'}[topic] in reply.text.lower()


def test_horarios_y_vehiculos_en_la_misma_consulta():
    reply = RuleEngine().respond('¿Abren los sábados y admiten coches?')
    assert 'horarios' in reply.text.lower()
    assert 'vehículos' in reply.text.lower()


def test_consulta_de_precio_de_auto_no_confunde_tipo_de_vehiculo():
    reply = RuleEngine().respond('¿Cuánto sale dejar el auto?')
    assert reply.intent == 'prices'
    assert 'vehículos admitidos' not in reply.text.lower()


def test_debito_sin_la_palabra_pagar():
    reply = RuleEngine().respond('¿Aceptan débito?')
    assert reply.intent == 'payment'
    assert 'débito' in reply.text.lower()
