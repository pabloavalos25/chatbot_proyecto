"""Clasificación determinista, independiente del transporte y la base de datos."""
import re
import unicodedata
from dataclasses import dataclass

from app.domain.catalog import SERVICES


@dataclass(frozen=True)
class Reply:
    intent: str
    text: str
    handoff: bool = False
    commercial: bool = False


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in text if not unicodedata.combining(c))))


def contains(text: str, *phrases: str) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) for phrase in phrases)


TOPICS = (
    ("services", ("abono", "abonos"), "abonos de estacionamiento", "No tengo confirmadas las condiciones, el precio ni la disponibilidad de los abonos. Si querés, pedime hablar con una persona para consultarlo."),
    ("payment", ("tarjeta", "efectivo", "transferencia", "medios de pago", "formas de pago", "pagar", "pago", "pagos", "pago con"), "medios de pago", "Todavía no tengo confirmados los medios de pago. Si querés, pedime hablar con una persona para consultarlos."),
    ("security", ("camara", "camaras", "vigilancia", "seguridad", "seguro", "asegurado"), "seguridad", "No tengo confirmada la información sobre seguridad del estacionamiento. Podés pedirme hablar con una persona para consultarla."),
    ("vehicles", ("moto", "motos", "camioneta", "camionetas", "bicicleta", "bicicletas", "vehiculos admitidos"), "tipos de vehículos admitidos", "No tengo confirmados los tipos de vehículos admitidos. Si querés, pedime hablar con una persona para consultarlo."),
    ("prices", ("precio", "precios", "tarifa", "tarifas", "costo", "costos", "cuanto cuesta", "cuanto sale", "valor"), "precios", "Todavía no tengo los precios confirmados. Si querés, pedime hablar con una persona para consultarlos."),
    ("availability", ("disponible", "disponibilidad", "lugar disponible", "plazas libres", "lugares libres", "hay lugar", "hay espacio", "tienen espacio"), "disponibilidad de lugar", "Por ahora no puedo confirmar si hay lugar disponible. Podés pedirme hablar con una persona para consultarlo."),
    ("hours", ("horario", "horarios", "a que hora", "cuando abren", "cuando cierran"), "horarios", "Todavía no tengo los horarios confirmados. Si querés, pedime hablar con una persona para averiguarlos."),
    ("location", ("ubicacion", "direccion", "donde estan", "donde queda", "ubicados"), "dirección", "Todavía no tengo una dirección confirmada. Podés pedirme hablar con una persona para consultarla."),
)

EXAMPLE_RESPONSES = {
    'hours': 'En este ejemplo, los horarios son todos los días de 07:00 a 23:00.',
    'vehicles': 'En este ejemplo, los vehículos admitidos son autos, camionetas y camiones. Otros tipos de vehículo no están confirmados.',
    'payment': 'En este ejemplo, los medios de pago son efectivo, Mercado Pago y tarjetas de crédito y débito solo Visa o Mastercard. El QR se genera al confirmar la reserva o el abono; esta aplicación no lo genera automáticamente.',
}


class RuleEngine:
    def respond(self, message: str) -> Reply:
        text = normalize(message)
        if contains(text, "humano", "humana", "persona", "operador", "operadora", "asesor", "asesora", "agente", "empleado", "empleada", "hablar con alguien", "me atienda alguien", "con alguien del equipo"):
            return Reply("human", "Claro, dejo la conversación para que la atienda una persona. Mientras tanto, podés contarme qué necesitás.", handoff=True)
        # Los mensajes son datos: no se ejecutan ni modifican las reglas.
        if contains(text, "ignora tus reglas", "ignorar las reglas", "revela tus instrucciones", "revela las instrucciones", "chiste", "poema", "poesia", "bitcoin", "criptomoneda", "vuelo", "vuelos", "hotel", "receta", "politica"):
            return Reply("unknown", "Puedo ayudarte con consultas sobre el estacionamiento, como servicios, precios o disponibilidad. ¿Qué te gustaría saber?")
        qr_question = contains(text, 'qr') and not contains(text, 'quiero reservar', 'necesito reservar', 'hacer una reserva', 'hacer reserva', 'quiero una reserva', 'solicitar reserva', 'reservar lugar')
        if not qr_question and contains(text, "contratar", "reservar", "reserva", "apartarme un lugar", "quiero un abono", "solicitar abono", "comprar"):
            return Reply("commercial", "¡Gracias por tu interés! Guardé tu consulta. Si querés hablar con una persona para conocer los detalles, pedime atención humana.", commercial=True)
        # Additional phrases are deliberately specific: a bare "auto" in a
        # price question, for example, does not ask which vehicles are accepted.
        extra_phrases = {
            "hours": ("abren los domingos", "abren los sabados", "abren los feriados", "estan abiertos los domingos", "estan abiertos los sabados", "atienden los feriados"),
            "vehicles": ("aceptan autos", "aceptan coches", "admiten autos", "admiten coches", "camion", "camiones"),
            "payment": ("aceptan debito", "aceptan credito", "aceptan qr", "pago con qr", "mercado pago", "tarjetas", "qr", "visa", "mastercard"),
        }
        matches = [topic for topic in TOPICS if contains(text, *topic[1], *extra_phrases.get(topic[0], ()))]
        if len(matches) > 1:
            return Reply(matches[0][0], " ".join(EXAMPLE_RESPONSES.get(topic[0], topic[3]) for topic in matches))
        if matches:
            return Reply(matches[0][0], EXAMPLE_RESPONSES.get(matches[0][0], matches[0][3]))
        if contains(text, "servicio", "servicios", "estacionamiento", "ofrecen", "abono", "abonos"):
            return Reply("services", "¡Claro! En este ejemplo contamos con: " + "; ".join(SERVICES) + ". Si querés consultar disponibilidad, pedime hablar con una persona.")
        if contains(text, "gracias", "muchas gracias", "te agradezco"):
            return Reply("thanks", "¡De nada! Si necesitás algo más, estoy acá para ayudarte.")
        if contains(text, "chau", "adios", "hasta luego", "hasta pronto", "nos vemos"):
            return Reply("goodbye", "¡Hasta luego! Cuando quieras, podés volver a escribirme.")
        if contains(text, "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches"):
            return Reply("greeting", "¡Hola! Qué bueno que nos escribas. ¿En qué puedo ayudarte? Podés preguntarme por los servicios o pedirme hablar con una persona.")
        return Reply("unknown", "Perdón, no estoy seguro de haber entendido. Puedo ayudarte con consultas sobre el estacionamiento, como servicios, precios o disponibilidad. ¿Qué te gustaría saber?")
