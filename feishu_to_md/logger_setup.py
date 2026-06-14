# -*- coding: utf-8 -*-
import logging
import sys
import io


def setup_logger(level="INFO", log_to_file=False, log_file=None):
    """Configure structured logging for feishu_to_md.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_to_file: Whether to also log to a file.
        log_file: Path to the log file. Defaults to _feishu_to_md.log in script dir.
    """
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    logger = logging.getLogger("feishu_to_md")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    
    # Console handler with color via stream wrapper
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    if log_to_file:
        fpath = log_file or os.path.join(script_dir, "_feishu_to_md.log")
        file_handler = logging.FileHandler(fpath, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
