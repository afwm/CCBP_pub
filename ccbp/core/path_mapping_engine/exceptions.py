# -*- coding: utf-8 -*-
"""Custom exceptions for the Path Mapping Engine."""

class PathMappingError(Exception):
    """Base exception for the path mapping engine."""
    pass

class ConfigError(PathMappingError):
    """Exception raised for errors in the configuration file."""
    pass

class RuleError(PathMappingError):
    """Exception raised for errors during rule processing."""
    pass 