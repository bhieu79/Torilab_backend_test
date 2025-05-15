import logging
import logging.handlers
import os
from logging.handlers import RotatingFileHandler

def logging_setup():
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Reset any existing loggers to avoid duplicate handlers
    logging.getLogger('app').handlers = []
    class CustomFormatter(logging.Formatter):
        grey = "\x1b[38;21m" # ANSI escape for grey
        blue = "\x1b[34;21m" # ANSI escape for blue
        yellow = "\x1b[33;21m" # ANSI escape for yellow
        red = "\x1b[31;21m" # ANSI escape for red
        bold_red = "\x1b[31;1m" # ANSI escape for bold red
        reset = "\x1b[0m" # ANSI escape for reset
        # Note: Corrected reset to \x1b[0m from \x1b[m for broader compatibility

        format_info_template = "[%(levelname)s - %(asctime)s - %(name)s]: "
        format_message = "%(message)s %(extra)s"

        FORMATS = {
            logging.DEBUG: grey + format_info_template + reset + format_message,
            logging.INFO: blue + format_info_template + reset + format_message,
            logging.WARNING: yellow + format_info_template + reset + format_message,
            logging.ERROR: red + format_info_template + reset + format_message,
            logging.CRITICAL: bold_red + format_info_template + reset + format_message
        }

        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno)
            # Add extra fields if available
            if hasattr(record, 'extra'):
                if isinstance(record.extra, dict):
                    record.extra = ' '.join(f'{k}={v}' for k, v in record.extra.items())
            else:
                record.extra = ''
            
            # Create a new formatter for each record to apply the specific format
            formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
            return formatter.format(record)

    custom_formatter = CustomFormatter()

    # Configure the logger named 'app'
    custom_logger = logging.getLogger('app')
    custom_logger.setLevel(logging.DEBUG)  # Set root level to DEBUG
    custom_logger.propagate = False  # Prevent double logging

    # Set up the console handler with more verbose output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(custom_formatter)

    # Set up rotating file handler
    log_file = os.path.join('logs', 'server.log')
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,  # 1MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(custom_formatter)

    # Add handlers
    custom_logger.addHandler(console_handler)
    custom_logger.addHandler(file_handler)

    # Debug logging setup
    custom_logger.debug("Logging setup completed")
    custom_logger.debug(f"Logger level: {custom_logger.level}")
    custom_logger.debug(f"Console handler level: {console_handler.level}")
    custom_logger.debug(f"File handler level: {file_handler.level}")

    return custom_logger