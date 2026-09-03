"""Consistent error responses for the browser and API consumers.

The original validation payload is retained for backwards compatibility.  The
additional fields give clients a stable summary and a predictable place for
field-level errors.
"""

from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return response

    data = response.data
    if isinstance(data, dict):
        field_errors = {
            key: value
            for key, value in data.items()
            if key not in {'detail', 'code', 'message', 'field_errors'}
        }
        detail = data.get('detail')
        if isinstance(detail, str):
            message = detail
        elif field_errors:
            first = next(iter(field_errors.values()))
            message = first[0] if isinstance(first, list) and first else str(first)
        else:
            message = 'The request could not be processed.'
        response.data = {
            **data,
            'message': message,
            'field_errors': field_errors,
        }
    else:
        message = data[0] if isinstance(data, list) and data else 'The request could not be processed.'
        response.data = {
            'detail': data,
            'message': str(message),
            'field_errors': {},
        }
    return response
