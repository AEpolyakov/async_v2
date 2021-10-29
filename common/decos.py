"""decorators for async chat"""
import sys
import logging

# метод определения модуля, источника запуска.
if sys.argv[0].find('client_src') == -1:
    #если не клиент то сервер!
    logger = logging.getLogger('server')
else:
    # ну, раз не сервер, то клиент
    logger = logging.getLogger('client_src')


def log(func_to_log):
    """log decorator"""
    def log_saver(*args , **kwargs):
        logger.debug(f'Была вызвана функция {func_to_log.__name__} c параметрами {args}, '
                     f'{kwargs}. Вызов из модуля {func_to_log.__module__}')
        ret = func_to_log(*args , **kwargs)
        return ret
    return log_saver