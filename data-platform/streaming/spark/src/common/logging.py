import logging
import sys

def get_logger(name: str = None) -> logging.Logger:
    """
    Get a configured logger instance
    
    Args:
        name: Name of the logger (default is root logger)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    
    if name is None:
        name = __name__
    
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger
