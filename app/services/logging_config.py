import logging.config
import os

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'level': 'INFO',
            'stream': 'ext://sys.stdout'
        },
        'file': {
            'class': 'logging.FileHandler',
            'formatter': 'standard',
            'level': 'DEBUG',
            'filename': os.path.join('logs', 'app.log'),  # Creates a logs/ directory
            'mode': 'a'  # Append mode
        }
    },
    'loggers': {
        '': {  # Root logger (captures all loggers)
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True
        },
        'uvicorn': {
            'level': 'INFO',
            'propagate': False
        },
        'uvicorn.error': {
            'level': 'INFO',
            'propagate': False
        }
    }
}

def setup_logging():
    """Initialize logging configuration globally."""
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Apply the configuration
    logging.config.dictConfig(LOGGING_CONFIG)

# For JSON logging, replace the formatter with:
# 'formatters': {
#     'json': {
#         '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
#         'format': '''
#             %(asctime)s %(name)s %(levelname)s 
#             %(message)s %(pathname)s %(lineno)d
#         '''
#     }
# }


# To exclude noisy libraries, add them to loggers with a higher level:
# 'loggers': {
#     'urllib3': {  # Example: Silence requests/urllib3 logs
#         'level': 'WARNING',
#         'propagate': False
#     }
# }