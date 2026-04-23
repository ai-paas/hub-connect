"""
Parameter utility functions for model parameter filtering
"""

import re
from typing import Optional, Tuple

from fastapi import HTTPException

# Valid parameter pattern: numbers followed by 'B' (billions)
PARAMETER_PATTERN = r'^(\d+(?:\.\d+)?)[B]$'
PARAMETER_REGEX = re.compile(PARAMETER_PATTERN, re.IGNORECASE)


def validate_parameter_format(param: str) -> bool:
    """
    Validate parameter format (e.g., '3B', '7B', '24.5B')
    
    Args:
        param: Parameter string to validate
        
    Returns:
        bool: True if format is valid, False otherwise
    """
    if not param:
        return False
    
    return bool(PARAMETER_REGEX.match(param))


def parse_parameter_to_number(param: str) -> float:
    """
    Convert parameter notation to numeric value in billions
    
    Args:
        param: Parameter string (e.g., '3B', '7.5B')
        
    Returns:
        float: Parameter value in billions
        
    Raises:
        ValueError: If parameter format is invalid
    """
    if not validate_parameter_format(param):
        raise ValueError(f"Invalid parameter format: {param}")
    
    # Extract numeric value and remove 'B'
    numeric_part = param.upper().rstrip('B')
    return float(numeric_part)


def validate_parameter_range(min_param: Optional[str], max_param: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Validate parameter range (min should be <= max)
    
    Args:
        min_param: Minimum parameter string
        max_param: Maximum parameter string
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not min_param or not max_param:
        return True, None
    
    try:
        min_val = parse_parameter_to_number(min_param)
        max_val = parse_parameter_to_number(max_param)
        
        if min_val > max_val:
            return False, f"Minimum parameter ({min_param}) cannot be greater than maximum parameter ({max_param})"
            
        return True, None
    except ValueError as e:
        return False, str(e)


def build_huggingface_parameter_filter(min_param: Optional[str] = None, max_param: Optional[str] = None) -> str:
    """
    Build HuggingFace API parameter filter string
    
    Args:
        min_param: Minimum parameter (e.g., '3B')
        max_param: Maximum parameter (e.g., '256B')
        
    Returns:
        str: Filter string for HuggingFace API (e.g., 'min:3B,max:256B')
        
    Raises:
        HTTPException: If parameter validation fails
    """
    filters = []
    
    # Validate individual parameter formats
    if min_param and not validate_parameter_format(min_param):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid minimum parameter format. Use format like '3B', '7B', '24B'",
                "error_code": "INVALID_MIN_PARAMETER_FORMAT",
                "provided_value": min_param,
                "valid_examples": ["3B", "7B", "13B", "24B", "70B", "128B", "256B"]
            }
        )
    
    if max_param and not validate_parameter_format(max_param):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid maximum parameter format. Use format like '128B', '256B'",
                "error_code": "INVALID_MAX_PARAMETER_FORMAT", 
                "provided_value": max_param,
                "valid_examples": ["3B", "7B", "13B", "24B", "70B", "128B", "256B"]
            }
        )
    
    # Validate parameter range
    is_valid, error_msg = validate_parameter_range(min_param, max_param)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail={
                "message": error_msg,
                "error_code": "INVALID_PARAMETER_RANGE",
                "provided_min": min_param,
                "provided_max": max_param
            }
        )
    
    # Build filter string
    if min_param:
        filters.append(f"min:{min_param}")
    
    if max_param:
        filters.append(f"max:{max_param}")
    
    return ",".join(filters)


def format_parameter_display(num_parameters: int) -> str:
    """
    Format parameter count for display (e.g., 355000000 -> '355M')
    
    Args:
        num_parameters: Raw parameter count
        
    Returns:
        str: Formatted parameter display
    """
    if num_parameters >= 1_000_000_000:
        value = f"{num_parameters / 1_000_000_000:.1f}".rstrip('0').rstrip('.')
        return f"{value}B"
    elif num_parameters >= 1_000_000:
        value = f"{num_parameters / 1_000_000:.1f}".rstrip('0').rstrip('.')
        return f"{value}M"
    elif num_parameters >= 1_000:
        value = f"{num_parameters / 1_000:.1f}".rstrip('0').rstrip('.')
        return f"{value}K"
    else:
        return str(num_parameters)


def categorize_parameter_range(num_parameters: int) -> str:
    """
    Categorize model by parameter count
    
    Args:
        num_parameters: Raw parameter count
        
    Returns:
        str: Parameter range category
    """
    if num_parameters < 1_000_000:  # < 1M
        return "tiny"
    elif num_parameters < 100_000_000:  # < 100M
        return "small"
    elif num_parameters < 1_000_000_000:  # < 1B
        return "medium"
    elif num_parameters < 10_000_000_000:  # < 10B
        return "large"
    elif num_parameters < 100_000_000_000:  # < 100B
        return "extra_large"
    else:  # >= 100B
        return "massive"