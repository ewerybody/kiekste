import os
import json
import logging

NAME = 'kiekste'
TMP_NAME = f'_{NAME}_tmp'
TMP_PATH = os.path.join(os.getenv('TEMP', ''), TMP_NAME)
PATH = os.path.abspath(os.path.dirname(__file__))
LOG_LEVEL = logging.DEBUG
ENCODING = 'utf8'
# logging.basicConfig()
LOG_FMT = '%(levelname)s: [%(name)s] %(message)s'

_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(logging.Formatter(LOG_FMT, None))
logging.root.handlers = [_stream_handler]


def get_logger(name):
    new_logger = logging.getLogger(name)
    new_logger.setLevel(LOG_LEVEL)
    return new_logger

log = get_logger(f'{NAME}.common')


class _Settings:
    def __init__(self):
        self.last_save_path = ''
        self.last_rectangles = []
        self.max_rectangles = 12
        self.draw_pointer = True
        self.video_fps = 10
        self.video_quality = 5000

        self._settings_file = NAME.lower() + '.json'
        self._settings_path = os.path.join(PATH, self._settings_file)
        self._load()

    def _load(self):
        for key, value in self._get_json().items():
            if key not in self.__dict__:
                log.warning('Key "%s" not yet listed in Settings obj!1', key)
            self.__dict__[key] = value

    def _get_json(self):
        if os.path.isfile(self._settings_path):
            with open(self._settings_path, encoding=ENCODING) as file_obj:
                return json.load(file_obj)
        return {}

    def _save(self):
        current = self._get_json()
        do_write = False
        for name, value in self.__dict__.items():
            if name.startswith('_'):
                continue
            if not isinstance(value, (str, int, list, bool)):
                continue
            if name not in current:
                do_write = True
                current[name] = value
            if current[name] == value:
                continue
            do_write = True
            current[name] = value

        if not do_write:
            return

        with open(self._settings_path, 'w', encoding=ENCODING) as file_obj:
            json.dump(current, file_obj, indent=2, sort_keys=True)


SETTINGS = _Settings()


def setup_logger():
    import a2output

    if not os.path.isdir(TMP_PATH):
        os.makedirs(TMP_PATH)
    logger = a2output.get_logwriter(NAME, reuse=False)
    logger.set_data_path(TMP_PATH)
    return logger
