"""
Tests for parameter utility functions
"""

import pytest
from fastapi import HTTPException

from app.utils.parameter_utils import (
    validate_parameter_format,
    parse_parameter_to_number,
    validate_parameter_range,
    build_huggingface_parameter_filter,
    format_parameter_display,
    categorize_parameter_range
)


class TestParameterValidation:
    """Test parameter validation functions"""
    
    def test_validate_parameter_format_valid(self):
        """Test valid parameter formats"""
        assert validate_parameter_format("3B") == True
        assert validate_parameter_format("7B") == True
        assert validate_parameter_format("24B") == True
        assert validate_parameter_format("128B") == True
        assert validate_parameter_format("256B") == True
        assert validate_parameter_format("7.5B") == True
        assert validate_parameter_format("13.2B") == True
    
    def test_validate_parameter_format_invalid(self):
        """Test invalid parameter formats"""
        assert validate_parameter_format("") == False
        assert validate_parameter_format("3") == False
        assert validate_parameter_format("B") == False
        assert validate_parameter_format("3M") == False
        assert validate_parameter_format("3K") == False
        assert validate_parameter_format("3GB") == False
        assert validate_parameter_format("abc") == False
        assert validate_parameter_format("3.B") == False
    
    def test_parse_parameter_to_number(self):
        """Test parameter parsing to numeric values"""
        assert parse_parameter_to_number("3B") == 3.0
        assert parse_parameter_to_number("7B") == 7.0
        assert parse_parameter_to_number("24B") == 24.0
        assert parse_parameter_to_number("7.5B") == 7.5
        assert parse_parameter_to_number("128B") == 128.0
    
    def test_parse_parameter_to_number_invalid(self):
        """Test parameter parsing with invalid formats"""
        with pytest.raises(ValueError):
            parse_parameter_to_number("3M")
        
        with pytest.raises(ValueError):
            parse_parameter_to_number("invalid")
    
    def test_validate_parameter_range_valid(self):
        """Test valid parameter ranges"""
        is_valid, error = validate_parameter_range("3B", "256B")
        assert is_valid == True
        assert error is None
        
        is_valid, error = validate_parameter_range("7B", "128B")
        assert is_valid == True
        assert error is None
        
        is_valid, error = validate_parameter_range("3B", "3B")
        assert is_valid == True
        assert error is None
    
    def test_validate_parameter_range_invalid(self):
        """Test invalid parameter ranges"""
        is_valid, error = validate_parameter_range("256B", "3B")
        assert is_valid == False
        assert "cannot be greater than" in error
        
        is_valid, error = validate_parameter_range("128B", "24B")
        assert is_valid == False
        assert "cannot be greater than" in error
    
    def test_validate_parameter_range_none_values(self):
        """Test parameter range validation with None values"""
        assert validate_parameter_range(None, "256B") == (True, None)
        assert validate_parameter_range("3B", None) == (True, None)
        assert validate_parameter_range(None, None) == (True, None)


class TestHuggingFaceFilterBuilder:
    """Test HuggingFace parameter filter builder"""
    
    def test_build_filter_both_params(self):
        """Test building filter with both min and max"""
        result = build_huggingface_parameter_filter("3B", "256B")
        assert result == "min:3B,max:256B"
    
    def test_build_filter_min_only(self):
        """Test building filter with min only"""
        result = build_huggingface_parameter_filter("7B", None)
        assert result == "min:7B"
    
    def test_build_filter_max_only(self):
        """Test building filter with max only"""
        result = build_huggingface_parameter_filter(None, "128B")
        assert result == "max:128B"
    
    def test_build_filter_no_params(self):
        """Test building filter with no parameters"""
        result = build_huggingface_parameter_filter(None, None)
        assert result == ""
    
    def test_build_filter_invalid_min(self):
        """Test building filter with invalid min parameter"""
        with pytest.raises(HTTPException) as exc_info:
            build_huggingface_parameter_filter("3M", "256B")
        
        assert exc_info.value.status_code == 400
        assert "INVALID_MIN_PARAMETER_FORMAT" in str(exc_info.value.detail)
    
    def test_build_filter_invalid_max(self):
        """Test building filter with invalid max parameter"""
        with pytest.raises(HTTPException) as exc_info:
            build_huggingface_parameter_filter("3B", "256M")
        
        assert exc_info.value.status_code == 400
        assert "INVALID_MAX_PARAMETER_FORMAT" in str(exc_info.value.detail)
    
    def test_build_filter_invalid_range(self):
        """Test building filter with invalid range"""
        with pytest.raises(HTTPException) as exc_info:
            build_huggingface_parameter_filter("256B", "3B")
        
        assert exc_info.value.status_code == 400
        assert "INVALID_PARAMETER_RANGE" in str(exc_info.value.detail)


class TestParameterDisplay:
    """Test parameter display formatting"""
    
    def test_format_parameter_display_billions(self):
        """Test formatting for billion-scale parameters"""
        assert format_parameter_display(3_000_000_000) == "3B"
        assert format_parameter_display(7_500_000_000) == "7.5B"
        assert format_parameter_display(24_000_000_000) == "24B"
        assert format_parameter_display(128_000_000_000) == "128B"
    
    def test_format_parameter_display_millions(self):
        """Test formatting for million-scale parameters"""
        assert format_parameter_display(355_000_000) == "355M"
        assert format_parameter_display(1_500_000) == "1.5M"
        assert format_parameter_display(500_000_000) == "500M"
    
    def test_format_parameter_display_thousands(self):
        """Test formatting for thousand-scale parameters"""
        assert format_parameter_display(1_500) == "1.5K"
        assert format_parameter_display(500_000) == "500K"
    
    def test_format_parameter_display_small(self):
        """Test formatting for small parameters"""
        assert format_parameter_display(100) == "100"
        assert format_parameter_display(500) == "500"
    
    def test_categorize_parameter_range(self):
        """Test parameter range categorization"""
        assert categorize_parameter_range(500_000) == "tiny"  # 500K (< 1M = tiny)
        assert categorize_parameter_range(50_000_000) == "small"  # 50M
        assert categorize_parameter_range(500_000_000) == "medium"  # 500M
        assert categorize_parameter_range(3_000_000_000) == "large"  # 3B
        assert categorize_parameter_range(50_000_000_000) == "extra_large"  # 50B
        assert categorize_parameter_range(200_000_000_000) == "massive"  # 200B


if __name__ == "__main__":
    pytest.main([__file__])