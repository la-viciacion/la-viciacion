import random

forbidden = (
    "No estás autorizado para usar este bot. "
    + "Por favor, ponte en contacto con algún administrador."
)

api_error = (
    "Parece que hay problemas con la API. "
    + "Por favor, ponte en contacto con algún administrador."
)

command_list = (
    "La lista actual de comandos es la siguiente:\n"
    + "/help - Muestra esta lista\n"
    + "/menu - Muestra el menú interactivo\n"
    + "/activate - Activa tu cuenta"
)


def start(name):
    return (
        "Hola *"
        + name
        + "*, soy el bot de 'La Viciación'. "
        + "Para saber la lista de comandos disponibles escribe /help, pero "
        + "si quieres usarlos es necesario tener una cuenta. Habla "
        + "con un administrador para saber cómo hacerlo."
    )
