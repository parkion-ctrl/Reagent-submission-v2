import logging
import sys
import os
from waitress import serve
from config.wsgi import application

LOG_FILE = os.path.join(os.path.dirname(__file__), 'server.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info('서버 시작: http://0.0.0.0:8000')
    serve(application, host='0.0.0.0', port=8000)
