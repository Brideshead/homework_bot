import logging
import os
import time
from http import HTTPStatus
from pathlib import Path
from typing import Dict, List

import requests
import telegram
from dotenv import load_dotenv
from exceptions import (RequestExceptionError, SendmessageError,
                        TheAnswerIsNot200Error, TokenError)

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')


RETRY_PERIOD = 600  # 10 минут * 60 секунд
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

logging.basicConfig(
    level=logging.DEBUG,
    filename=Path('../program.log').resolve(),
    filemode='w',
    format='%(asctime)s - %(funcName)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def check_tokens() -> bool:
    """Проверяем наличия токена.

    Доступны ли токены, которые необходимы для работы программы.
    Если хотя бы один токен не доступен , тогда программа прекрашает
    свою работу.

    Возвращает:
        True если проверка пройдена или TokenError, если что-то отсутсвует.
    """
    list_tokens = []
    for name in ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']:
        if globals().get(name) is None:
            list_tokens.append(name)
    if not list_tokens:
        return True
    else:
        api_answer = 'Отстутствует одна или несколько переменных окружения'
        logging.critical(api_answer)
        raise TokenError


def send_message(bot: telegram.bot.Bot, message: str) -> None:
    """Отправляем сообщение в Телеграм.

    В случае успеха пользователь получает сообщение в чат Телеграма.
    В случае неудачи логируем в журнал запись об ошибке.

    Параметры:
        bot: экземпляр класса Bot.
        message: строка сообщения с текстом.
    """
    logger.info(
        f'Вызываем функцию send_message c аргументами {bot} и {message}',
    )
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError as telegram_error:
        logging.exception(
            f'Сообщение в Telegram не отправлено: {telegram_error}',
        )
        raise SendmessageError
    logger.debug(f'Сообщение в Telegram отправлено: {message}')


def get_api_answer(timestamp: int) -> Dict[str, List[str]]:
    """Получение данных с API Яндекс Практикума.

    Делает запрос к единственному эндпойнту на предмет доступности.

    Параметры:
        timestamp: временная метка запроса.

    Возвращает:
        В случае успешного запроса возвращает ответ API в формате JSON.
        В случае неудачи выводится ошибка и осуществляется запись в лог.
    """
    logger.info(f'Вызываем функцию get_api_answer c аргументами {timestamp}')
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp},
        )
    except requests.exceptions.RequestException as request_error:
        logger.error(f'Код ответа API : {request_error}')
        raise RequestExceptionError
    if response.status_code != HTTPStatus.OK:
        logger.error(
            f'Эндпоинт {ENDPOINT} недоступен.'
            f' Код ответа API: {response.status_code}',
        )
        raise TheAnswerIsNot200Error
    return response.json()


def check_response(response: Dict[str, List[str]]) -> List[str]:
    """Проверяем данные в response.

    Соответствует ли ответ API документации.

    Параметры:
        response: ответ API, приведенный к типам данных Python.

    Возвращает:
        В случае успеха список с информацией о всех выполненных домашних
        работах и той , которая находятся в работе.
        В случае неудачи обработки запроса выводится ошибка с просьбой
        проверить переменные окружения.
    """
    logger.info(f'Вызываем функцию check_response c аргументами {response}')
    if isinstance(response, dict) and all(
        key for key in ('current_date', 'homeworks')
    ) and isinstance(response.get('homeworks'), list):
        return response.get('homeworks')

    raise TypeError(
        'Ошибка API при проверке response, проверьте данные.',
    )


def parse_status(homework: Dict[str, str]) -> str:
    """Анализируем статус если изменился.

    Извлекает статус о конкретной домашней работе.

    Параметры:
        homework: список с информацией о всех выполненных домашних работах
        и той , которая находятся в работе.

    Возвращает:
        В случае если статус работы изменился , выводит сообщение об
        изменении статуса работы.
        В случае неудачи есть несколько сценариев выводимых ошибок в
        зависимости от причины сбоя - соответствие значений
        по указываему ключу или если статуса нет в словаре вердиктов.
    """
    logger.info(f'Вызываем функцию parse_status c аргументами {homework}')
    try:
        name, status = homework['homework_name'], homework['status']
    except KeyError:
        raise KeyError(
            'Ошибка ключа при запросе названия и статуса домашней работы',
        )
    try:
        verdict = HOMEWORK_VERDICTS[status]
    except KeyError:
        raise KeyError(
            f'Ошибка ключа при запросе статуса работы: {verdict}',
        )
    return f'Изменился статус проверки работы "{name}": {verdict}'


def main() -> None:
    """Основная логика работы бота.

    Делаем проверку токенов функцией check_tokens().
    Запускаем бота.
    Делаем запрос к API функцией get_api_answer().
    Проверяем ответ функцией check_response().
    Если есть обновления получаем статус обновления
    функцией parse_status() и отправляем сообщение с уведомлением
    в Telegram функцией send_message().
    Далее уходим в режим ожидания на время RETRY_PERIOD и
    возвращаемся к началу работы.

    В случае сбоя в работе выводим в Telegram уведомление
    с названием ошибки и логируем это в журнал.
    """
    logging.info('Бот запущен.')
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            logger.info('Cписок работ получен.')
            if homeworks:
                send_message(bot, parse_status(homeworks[0]))
                timestamp = response['current_date']
            else:
                logger.info('Новых заданий нет.')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logger.critical(message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
