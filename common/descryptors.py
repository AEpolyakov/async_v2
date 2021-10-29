"""descriptors"""
import logging
import sys

# Инициализиция логера
# метод определения модуля, источника запуска.
if sys.argv[0].find('client_src') == -1:
    # если не клиент то сервер!
    logger = logging.getLogger('server')
else:
    # ну, раз не сервер, то клиент
    logger = logging.getLogger('client_src')


# Дескриптор для описания порта:
class Port:
    """port descriptor"""
    def __set__(self, instance, value):
        if not 1023 < value < 65536:
            logger.critical(
                f'Попытка запуска с указанием неподходящего порта {value}. Допустимы адреса с 1024 до 65535.')
            exit(1)
        instance.__dict__[self.name] = value

    def __set_name__(self, owner, name):
        self.name = name
