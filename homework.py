import logging
import os
import requests
import sys
import telegram
import time
from typing import Dict

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

logging.basicConfig(
    level=logging.DEBUG,
    filename='program.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s - %(name)s',
)
logger = logging.getLogger(__name__)
logger.addHandler(
    logging.StreamHandler(),
)


class RequestExceptionError(Exception):
    """Ошибка запроса."""


class TheAnswerIsNot200Error(Exception):
    """Ответ сервера не 200."""


def check_tokens() -> bool:
    """Проверка наличия токена."""
    return all(
        [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID],
    )


def send_message(bot: telegram.bot.Bot, message: str) -> None:
    """Отправка сообщения в Телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(
            f'Сообщение в Telegram отправлено: {message}')
    except Exception as telegram_error:
        logger.error(
            f'Сообщение в Telegram не отправлено: {telegram_error}')


def get_api_answer(timestamp: int) -> Dict[str, list]:
    """Получение данных с API Яндекс Практикума."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=timestamp,
        )
        if response.status_code != 200:
            api_answer = (
                f'Эндпоинт {ENDPOINT} недоступен.'
                f' Код ответа API: {response.status_code}'
            )
            logger.error(api_answer)
            raise TheAnswerIsNot200Error(api_answer)
        return response.json()
    except requests.exceptions.RequestException as request_error:
        api_answer = f'Код ответа API : {request_error}'
        logger.error(api_answer)
        raise RequestExceptionError(api_answer) from request_error


def check_response(response: Dict[str, list]) -> list:
    """Проверяем данные в response."""
    if isinstance(response, dict):
        if 'homeworks' in response:
            if isinstance(response.get('homeworks'), list):
                return response.get('homeworks')
            raise TypeError('API возвращает не список.')
        raise KeyError('Не найден ключ homeworks.')
    raise TypeError('API возвращает не словарь.')


def parse_status(homework: Dict[str, str]) -> str:
    """Анализируем статус если изменился."""
    if isinstance(homework, dict):
        if 'status' in homework:
            if 'homework_name' in homework:
                if isinstance(homework.get('status'), str):
                    homework_name = homework.get('homework_name')
                    homework_status = homework.get('status')
                    if homework_status in HOMEWORK_VERDICTS:
                        verdict = HOMEWORK_VERDICTS.get(homework_status)
                        return ('Изменился статус проверки работы '
                                f'"{homework_name}". {verdict}')
                    else:
                        raise Exception("Неизвестный статус работы")
                raise TypeError('status не str.')
            raise KeyError('В ответе нет ключа homework_name.')
        raise KeyError('В ответе нет ключа status.')
    raise KeyError('API возвращает не словарь.')


def main() -> None:
    """Основная логика работы бота."""
    logging.info('Бот запущен.')
    if not check_tokens():
        api_answer = 'Отстутствует одна или несколько переменных окружения'
        logger.critical(api_answer)
        sys.exit(api_answer)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            logging.info('Cписок работ получен.')
            if len(homeworks) > 0:
                send_message(bot, parse_status(homeworks[0]))
                timestamp = response['current_date']
            else:
                logging.info('Новых заданий нет.')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logger.critical(message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
