"""utils"""
import json
import sys
from common.decos import log
from common.constants import *
sys.path.append('../')


@log
def get_message(client):
    """Утилита приёма и декодирования сообщения
    принимает байты выдаёт словарь, если принято
    что-то другое отдаёт ошибку типа"""
    encoded_response = client.recv(MAX_PACKAGE_LENGTH)
    json_response = encoded_response.decode(ENCODING)
    response = json.loads(json_response)
    if isinstance(response, dict):
        return response
    else:
        raise TypeError


@log
def send_message(sock, message):
    """Утилита кодирования и отправки сообщения
    принимает словарь и отправляет его"""
    js_message = json.dumps(message)
    encoded_message = js_message.encode(ENCODING)
    sock.send(encoded_message)
