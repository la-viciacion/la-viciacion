forbidden = (
    "No estás autorizado para usar este bot. "
    + "Por favor, ponte en contacto con algún administrador."
)

inactive = (
    "Tu cuenta todavía no está activa. "
    + "Por favor, ponte en contacto con algún administrador."
)

api_error = (
    "Parece que hay problemas con la API. "
    + "Por favor, ponte en contacto con algún administrador."
)

activated = "¡Listo, {name}! Tu cuenta de Telegram ya está vinculada. Usa /menu para empezar."
already_activated = "Tu cuenta de Telegram ya está vinculada. Usa /menu para empezar."
activate_no_username = (
    "Para activarte necesitas tener un nombre de usuario de Telegram (@usuario) "
    + "igual al que tienes en la app. Ponlo en los ajustes de Telegram y vuelve a probar."
)
activate_no_account = (
    "No hay ninguna cuenta en la app con tu nombre de usuario de Telegram. "
    + "Habla con un administrador."
)
activate_taken = (
    "Tu cuenta de la app ya está vinculada a otro usuario de Telegram. "
    + "Habla con un administrador."
)
forbidden_in_group = "No estás activado. Escribe /activate para vincular tu cuenta de la app."


def start(name, in_group):
    text = f"Hola {name}, soy el bot de 'La Viciación'. Escribe /menu para consultar tus estadísticas y los rankings."
    if in_group:
        text += " Si todavía no puedes usarlo, escribe /activate para vincular tu cuenta de la app."
    return text
