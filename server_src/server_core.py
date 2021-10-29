"""module docstring"""

import binascii
import hmac
import socket
import os
import select
import threading
from common.utils import *
from common.descryptors import Port
from common.metaclasses import ServerMaker


class Server(threading.Thread, metaclass=ServerMaker):
    """Инициализация_Сокета"""

    port = Port()

    def __init__(self, listen_address, listen_port, database):
        # Параментры подключения
        self.addr = listen_address
        self.port = listen_port

        # База данных сервера
        self.database = database

        # Список подключённых клиентов.
        self.clients = []

        # Список сообщений на отправку.
        self.messages = []

        # Словарь содержащий сопоставленные имена и соответствующие им сокеты.
        self.names = dict()

        # Инициализация логирования сервера.
        self.logger = logging.getLogger('server')

        # Флаг что был подключён новый пользователь,
        # нужен чтобы не мучать BD постоянными запросами на обновление
        self.new_connection = False
        self.conflag_lock = threading.Lock()

        # Конструктор предка
        super().__init__()

    def init_socket(self):
        self.logger.info(f'Запущен сервер, порт для подключений: {self.port}, '
                         f'адрес с которого принимаются подключения: {self.addr}. '
                         f'Если адрес не указан, принимаются соединения с любых адресов.')
        # Готовим сокет
        transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        transport.bind((self.addr, self.port))
        transport.settimeout(0.5)

        # Начинаем слушать сокет.
        self.sock = transport
        self.sock.listen()

    def run(self):
        """Инициализация Сокета"""
        self.init_socket()

        # Основной цикл программы сервера
        while True:
            # Ждём подключения, если таймаут вышел, ловим исключение.
            try:
                client, client_address = self.sock.accept()
            except OSError:
                pass
            else:
                self.logger.info(f'Установлено соедение с ПК {client_address}')
                self.clients.append(client)

            recv_data_lst = []
            send_data_lst = []
            err_lst = []
            # Проверяем на наличие ждущих клиентов
            try:
                if self.clients:
                    recv_data_lst, send_data_lst, err_lst = select.select(self.clients, self.clients, [], 0)
            except OSError as err:
                self.logger.error(f'Ошибка работы с сокетами: {err}')

            # принимаем сообщения и если ошибка, исключаем клиента.
            if recv_data_lst:
                for client_with_message in recv_data_lst:
                    try:
                        self.process_client_message(get_message(client_with_message), client_with_message)
                    except OSError:
                        # Ищем клиента в словаре клиентов и удаляем его из него и  базы подключённых
                        self.logger.info(f'Клиент {client_with_message.getpeername()} отключился от сервера.')
                        for name in self.names:
                            if self.names[name] == client_with_message:
                                self.database.user_logout(name)
                                del self.names[name]
                                break
                        self.clients.remove(client_with_message)
                        with self.conflag_lock:
                            self.new_connection = True

            # Если есть сообщения, обрабатываем каждое.
            for message in self.messages:
                try:
                    self.process_message(message, send_data_lst)
                except (ConnectionAbortedError, ConnectionError, ConnectionResetError, ConnectionRefusedError):
                    self.logger.info(f'Связь с клиентом с именем {message[DESTINATION]} была потеряна')
                    self.clients.remove(self.names[message[DESTINATION]])
                    self.database.user_logout(message[DESTINATION])
                    del self.names[message[DESTINATION]]
                    with self.conflag_lock:
                        self.new_connection = True
            self.messages.clear()

    def process_message(self, message, listen_socks):
        """Функция адресной отправки сообщения определённому клиенту.
        Принимает словарь сообщение, список зарегистрированых
        пользователей и слушающие сокеты. Ничего не возвращает."""
        if message[DESTINATION] in self.names and self.names[message[DESTINATION]] in listen_socks:
            send_message(self.names[message[DESTINATION]], message)
            self.logger.info(f'Отправлено сообщение пользователю {message[DESTINATION]} от пользователя {message[SENDER]}.')
        elif message[DESTINATION] in self.names and self.names[message[DESTINATION]] not in listen_socks:
            raise ConnectionError
        else:
            self.logger.error(
                f'Пользователь {message[DESTINATION]} не зарегистрирован на сервере, отправка сообщения невозможна.')

    def response_400(self, client, text):
        response = RESPONSE_400
        response[ERROR] = text
        send_message(client, response)
        self.clients.remove(client)
        client.close()

    def authorize_user(self, message, client):
        """метод авторизации пользователя"""
        if message[USER][ACCOUNT_NAME] in self.names.keys():
            self.response_400(client, 'Имя пользователя уже занято.')
        elif not self.database.check_user(message[USER][ACCOUNT_NAME]):
            self.response_400(client, 'Пользователь не зарегистрарован')
        else:
            random_string = binascii.hexlify(os.urandom(64))
            message_auth = RESPONSE_511
            message_auth[DATA] = random_string.decode('ascii')
            hash_object = hmac.new(self.database.get_hash(message[USER][ACCOUNT_NAME]), random_string, 'MD5')
            server_digest = hash_object.digest()
            self.logger.debug(f'auth message = {message_auth}')
            try:
                send_message(client, message_auth)
                answer = get_message(client)
            except OSError as err:
                self.logger.debug(f'authenticate error in data, {err}')
                client.close()
                return
            client_digest = binascii.a2b_base64(answer[DATA])
            if RESPONSE in answer and answer[RESPONSE] == 511 and hmac.compare_digest(server_digest, client_digest):
                self.logger.debug(f'authenticate {message[USER][ACCOUNT_NAME]} successful')
                self.names[message[USER][ACCOUNT_NAME]] = client
                client_ip, client_port = client.getpeername()
                self.database.user_login(message[USER][ACCOUNT_NAME], client_ip, client_port, message[USER][PUBLIC_KEY])
                send_message(client, RESPONSE_200)
                with self.conflag_lock:
                    self.new_connection = True

    def process_client_message(self, message, client):
        """Обработчик сообщений от клиентов, принимает словарь - сообщение от клиента,
        проверяет корректность, отправляет словарь-ответ в случае необходимости."""
        self.logger.debug(f'Разбор сообщения от клиента : {message}')

        # Если это сообщение о присутствии, принимаем и отвечаем
        if ACTION in message and \
                message[ACTION] == PRESENCE and \
                TIME in message and \
                USER in message:
            # Если такой пользователь ещё не зарегистрирован, регистрируем,
            # иначе отправляем ответ и завершаем соединение.
            self.authorize_user(message, client)
            return

        # Если это сообщение, то добавляем его в очередь сообщений. проверяем наличие в сети. и отвечаем.
        elif ACTION in message and \
                message[ACTION] == MESSAGE and \
                DESTINATION in message and \
                TIME in message and \
                SENDER in message and \
                MESSAGE_TEXT in message and \
                self.names[message[SENDER]] == client:
            if message[DESTINATION] in self.names:
                self.messages.append(message)
                self.database.process_message(message[SENDER], message[DESTINATION])
                send_message(client, RESPONSE_200)
            else:
                response = RESPONSE_400
                response[ERROR] = 'Пользователь не зарегистрирован на сервере.'
                send_message(client, response)
            return

        # Если клиент выходит
        elif ACTION in message and message[ACTION] == EXIT and ACCOUNT_NAME in message \
                and self.names[message[ACCOUNT_NAME]] == client:
            self.database.user_logout(message[ACCOUNT_NAME])
            self.logger.info(f'Клиент {message[ACCOUNT_NAME]} корректно отключился от сервера.')
            self.clients.remove(self.names[message[ACCOUNT_NAME]])
            self.names[message[ACCOUNT_NAME]].close()
            del self.names[message[ACCOUNT_NAME]]
            with self.conflag_lock:
                self.new_connection = True
            return

        # Если это запрос контакт-листа
        elif ACTION in message and message[ACTION] == GET_CONTACTS and USER in message and \
                self.names[message[USER]] == client:
            response = RESPONSE_202
            response[LIST_INFO] = self.database.get_contacts(message[USER])
            send_message(client, response)

        # Если это добавление контакта
        elif ACTION in message and message[ACTION] == ADD_CONTACT and ACCOUNT_NAME in message and USER in message \
                and self.names[message[USER]] == client:
            self.database.add_contact(message[USER], message[ACCOUNT_NAME])
            send_message(client, RESPONSE_200)

        # Если это удаление контакта
        elif ACTION in message and message[ACTION] == REMOVE_CONTACT and ACCOUNT_NAME in message and USER in message \
                and self.names[message[USER]] == client:
            self.database.remove_contact(message[USER], message[ACCOUNT_NAME])
            send_message(client, RESPONSE_200)

        # Если это запрос известных пользователей
        elif ACTION in message and message[ACTION] == USERS_REQUEST and ACCOUNT_NAME in message \
                and self.names[message[ACCOUNT_NAME]] == client:
            response = RESPONSE_202
            response[LIST_INFO] = [user[0] for user in self.database.users_list()]
            send_message(client, response)

        # Иначе отдаём Bad request
        else:
            response = RESPONSE_400
            response[ERROR] = 'Запрос некорректен.'
            send_message(client, response)
            return

    def service_update_lists(self):
        """Метод реализующий отправки сервисного сообщения 205 клиентам."""
        for client in self.names:
            try:
                send_message(self.names[client], RESPONSE_205)
            except OSError:
                self.remove_client(self.names[client])

    def remove_client(self, client):
        """
        Метод обработчик клиента с которым прервана связь.
        Ищет клиента и удаляет его из списков и базы:
        """
        self.logger.info(f'Клиент {client.getpeername()} отключился от сервера.')
        for name in self.names:
            if self.names[name] == client:
                self.database.user_logout(name)
                del self.names[name]
                break
        self.clients.remove(client)
        client.close()
