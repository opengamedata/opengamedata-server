# import standard libraries
import sys, os
from logging.config import dictConfig
# import 3rd-party libraries
from flask import Flask

# By default we'll log to WSGI errors stream which ends up in the Apache error log
logHandlers = {
        'wsgi': { 
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream', 
            'formatter': 'default'
            }
    }

logRootHandlers = ['wsgi']

# If a dedicated log file is defined for this Flask app, we'll also log there
# Ensure this is a writable directory
if "OGD_FLASK_APP_LOG_FILE" in os.environ:
    logHandlers['wsgi_app_file'] = {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.environ["OGD_FLASK_APP_LOG_FILE"],
            'maxBytes': 100000000, # 100 MB
            'backupCount': 10, # Up to 10 rotated files
            'formatter': 'default'
    }

    logRootHandlers.append('wsgi_app_file')

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '%(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': logHandlers,
    'root': {
        'level': 'INFO',
        'handlers': logRootHandlers
    }
})

application = Flask(__name__)

# import locals
from config.config import settings
_ogd_core = settings['OGD_CORE_PATH']
if not _ogd_core in sys.path:
    sys.path.append(settings['OGD_CORE_PATH'])
    application.logger.info(f"Added {_ogd_core} to path.")

application.logger.setLevel(settings['DEBUG_LEVEL'])
application.secret_key = b'thisisafakesecretkey'

def _logImportErr(msg:str, err:Exception):
    application.logger.warning(msg)
    application.logger.exception(err)

try:
    from apis.data.ClassroomAPI import ClassroomAPI
except ImportError as err:
    _logImportErr(msg="Could not import Classroom API:", err=err)
except Exception as err:
    _logImportErr(msg="Could not import Classroom API, general error:", err=err)
else:
    ClassroomAPI.register(application)

try:
    from apis.data.PopulationAPI import PopulationAPI
except ImportError as err:
    _logImportErr(msg="Could not import Population API:", err=err)
except Exception as err:
    _logImportErr(msg="Could not import Population API, general error:", err=err)
else:
    PopulationAPI.register(application)

try:
    from apis.data.PlayerAPI import PlayerAPI
except ImportError as err:
    _logImportErr(msg="Could not import Player API:", err=err)
except Exception as err:
    _logImportErr(msg="Could not import Player API, general error:", err=err)
else:
    PlayerAPI.register(application)

try:
    from apis.data.SessionAPI import SessionAPI
except ImportError as err:
    _logImportErr(msg="Could not import Session API:", err=err)
except Exception as err:
    _logImportErr(msg="Could not import Session API, general error:", err=err)
else:
    SessionAPI.register(application)

try:
    from apis.HelloAPI import HelloAPI
except ImportError as err:
    _logImportErr(msg="Could not import Hello API:", err=err)
except Exception as err:
    _logImportErr(msg="Could not import Hello API, general error:", err=err)
else:
    HelloAPI.register(application)
    
# if __name__ == '__main__':
# 	application.run(debug=True)