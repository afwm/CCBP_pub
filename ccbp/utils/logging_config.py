import logging
import logging.handlers
import os
import sys
from pathlib import Path
# Assuming you need platformdirs 
try:
    from platformdirs import user_log_dir
    PLATFORMDIRS_AVAILABLE = True
except ImportError:
    PLATFORMDIRS_AVAILABLE = False

_ROOT_LOGGER_NAME = 'ccbp'  # Root logger name for the application

# Format strings
_CONSOLE_FORMAT = '%(levelname)s: %(message)s'
_FILE_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'

def setup_logging(level=logging.INFO):
    """
    Sets up logging for the application with console and file handlers.
    
    Args:
        level: The logging level to use (default: logging.INFO)
    """
    # Main application logger (root of our namespace)
    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    root_logger.setLevel(level)  # Use the provided level
    
    # Determine the log directory
    log_dir = None
    if PLATFORMDIRS_AVAILABLE:
        try:
            log_dir = Path(user_log_dir('CCBP', ensure_exists=True))
            print(f"INFO: Using platformdirs log directory: {log_dir}")
        except Exception as e:
            print(f"WARNING: platformdirs failed to get/create log directory: {e}. Will use fallback.")
    
    if log_dir is None:  # Fallback logic
        if sys.platform == 'win32':
            log_dir = Path(os.environ.get('APPDATA', '~')) / 'CCBP' / 'logs'
        elif sys.platform == 'darwin':
            log_dir = Path.home() / 'Library' / 'Logs' / 'CCBP'
        else:  # Linux/Unix
            log_dir = Path.home() / '.cache' / 'CCBP' / 'logs'
        
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            print(f"INFO: Using fallback log directory: {log_dir}")
        except Exception as e:
            print(f"WARNING: Failed to create log directory {log_dir}: {e}. Logs will only go to console.")
            log_dir = None
    
    # Configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)  # Use the provided level
    console_formatter = logging.Formatter(_CONSOLE_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # If we have a log directory, set up file logging
    if log_dir:
        log_file = log_dir / 'app.log'
        print(f"INFO: Setting up logging. Log file path: {log_file}")
        
        # File handler with rotation
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_file,
            when='midnight',
            backupCount=7,  # Keep logs for 7 days
            encoding='utf-8'
        )
        file_handler.setLevel(level)  # Use the provided level
        file_formatter = logging.Formatter(_FILE_FORMAT)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Always log setup completion through the logger we just configured
    root_logger.info(f"Logging setup complete. Logging to console and potentially {log_file} (daily rotation, keep 7 days)")
    
    return root_logger

def get_logger(name):
    """
    Get a logger for a specific module.
    
    Args:
        name: Usually __name__ of the module requesting the logger
        
    Returns:
        A configured logger
    """
    # If it's a __main__ or similar top-level module, return the root logger
    if name == '__main__' or name == 'builtins' or '.' not in name:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    
    # Otherwise, return a child logger that inherits settings from the root
    return logging.getLogger(name)

# Testing if run directly
if __name__ == '__main__':
    setup_logging(level=logging.DEBUG)
    logger = get_logger(__name__)
    
    # Test logging at different levels
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
    
    # Test child logger
    child_logger = get_logger('test.child')
    child_logger.info("This is from the child logger") 