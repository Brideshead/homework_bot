class RequestExceptionError(Exception):
    """Ошибка запроса."""


class SendmessageError(Exception):
    """Сообщение не отправлено."""


class TheAnswerIsNot200Error(Exception):
    """Ответ сервера не 200."""


class TokenError(Exception):
    """Отсутсвует один или более токен."""
