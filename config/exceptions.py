from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    """Normaliza el cuerpo de todos los errores de la API.

    Contrato con el cliente:
      - errores generales   -> {"detail": "..."}
      - errores de validacion -> {"campo": ["..."]}
    """
    response = drf_exception_handler(exc, context)

    if response is None:
        return None

    data = response.data

    # DRF devuelve una lista plana cuando se lanza ValidationError con un
    # string suelto o con non_field_errors a pelo. La aplanamos a "detail".
    if isinstance(data, list):
        response.data = {'detail': ' '.join(str(item) for item in data)}
        return response

    if not isinstance(data, dict):
        response.data = {'detail': str(data)}
        return response

    # Errores de validacion por campo: se dejan tal cual los da DRF.
    return response
