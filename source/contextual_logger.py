#!/usr/bin/env python3
"""
Contextual Logger Module

Provides enhanced logging capabilities with contextual information support,
similar to structured logging in other languages like Go's zap logger.
"""

import logging
import sys
from typing import Dict, Any, Optional


class ContextualLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that supports adding context like zap logger in Go."""
    
    def __init__(self, logger: logging.Logger, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(logger, context or {})
    
    def with_context(self, **kwargs) -> 'ContextualLoggerAdapter':
        """Create a new logger adapter with additional context."""
        new_context = {**self.extra, **kwargs}
        return ContextualLoggerAdapter(self.logger, new_context)
    
    def process(self, msg, kwargs):
        """Process the log record to include context."""
        # Store our context in a dedicated field
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        kwargs['extra']['_context'] = self.extra
        return msg, kwargs


class ContextualFormatter(logging.Formatter):
    """Custom formatter that includes context fields in log output."""
    
    def format(self, record) -> str:
        # Get the base formatted message
        msg = super().format(record)
        
        # Add context fields if they exist
        context = getattr(record, '_context', {})
        if context:
            context_pairs = [f"{key}={value}" for key, value in context.items()]
            msg += f" [{', '.join(context_pairs)}]"
        
        return msg


def setup_contextual_logger(name: str, log_level: str) -> ContextualLoggerAdapter:
    """
    Setup a contextual logger with the specified name and log level.
    
    Args:
        name: Logger name (typically __name__)
        log_level: Log level string (e.g., 'INFO', 'DEBUG')
    
    Returns:
        ContextualLoggerAdapter instance ready for use
    """
    # Create custom formatter
    formatter = ContextualFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # Setup logger
    base_logger = logging.getLogger(name)
    base_logger.setLevel(getattr(logging, log_level.upper()))
    base_logger.handlers.clear()
    base_logger.addHandler(handler)
    
    return ContextualLoggerAdapter(base_logger) 