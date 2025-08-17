#!/usr/bin/env python3
"""
Unit tests for configuration management.

Tests the Config class's ability to parse environment variables correctly
and provide meaningful error messages for invalid values.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Set
from unittest.mock import patch

from source.config import Config
from source.file_type import FileType
from source.activity import ActivityId


class TestConfigValidParsing:
    """Test cases for valid configuration parsing."""
    
    @pytest.mark.parametrize("env_vars,expected_values,description", [
        # Default values
        (
            {"GARMIN_USERNAME": "test", "GARMIN_PASSWORD": "test"},
            {
                "log_level": "INFO",
                "cron_schedule": "0 */8 * * *",
                "run_immediately_on_startup": True,
                "request_delay_seconds": 10.0,
                "batch_size": 30,
                "check_for_activity_changes": True,
                "always_recheck_all_activities": False,
            },
            "Default configuration values"
        ),
        # Custom values
        (
            {
                "GARMIN_USERNAME": "user@example.com",
                "GARMIN_PASSWORD": "secret123",
                "LOG_LEVEL": "DEBUG",
                "CRON_SCHEDULE": "0 */12 * * *",
                "RUN_IMMEDIATELY_ON_STARTUP": "false",
                "REQUEST_DELAY_SECONDS": "45.5",
                "BATCH_SIZE": "50",
                "CHECK_FOR_ACTIVITY_CHANGES": "false",
                "ALWAYS_RECHECK_ALL_ACTIVITIES": "true",
            },
            {
                "garmin_username": "user@example.com",
                "garmin_password": "secret123",
                "log_level": "DEBUG",
                "cron_schedule": "0 */12 * * *",
                "run_immediately_on_startup": False,
                "request_delay_seconds": 45.5,
                "batch_size": 50,
                "check_for_activity_changes": False,
                "always_recheck_all_activities": True,
            },
            "Custom configuration values"
        ),
        # Boolean variations
        (
            {
                "GARMIN_USERNAME": "test", 
                "GARMIN_PASSWORD": "test",
                "RUN_IMMEDIATELY_ON_STARTUP": "1",
                "CHECK_FOR_ACTIVITY_CHANGES": "yes",
                "ALWAYS_RECHECK_ALL_ACTIVITIES": "on",
            },
            {
                "run_immediately_on_startup": True,
                "check_for_activity_changes": True,
                "always_recheck_all_activities": True,
            },
            "Boolean variations (1, yes, on)"
        ),
        # Numeric edge cases
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test", 
                "REQUEST_DELAY_SECONDS": "0.1",
                "BATCH_SIZE": "1",
            },
            {
                "request_delay_seconds": 0.1,
                "batch_size": 1,
            },
            "Minimum numeric values"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "REQUEST_DELAY_SECONDS": "999.99",
                "BATCH_SIZE": "1000",
            },
            {
                "request_delay_seconds": 999.99,
                "batch_size": 1000,
            },
            "Large numeric values"
        ),
    ])
    def test_valid_config_parsing(
        self, 
        env_vars: Dict[str, str], 
        expected_values: Dict[str, Any], 
        description: str
    ) -> None:
        """Test that valid environment variables are parsed correctly."""
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            for key, expected_value in expected_values.items():
                actual_value = getattr(config, key)
                assert actual_value == expected_value, (
                    f"{description}: Expected {key}={expected_value}, got {actual_value}"
                )

    @pytest.mark.parametrize("env_vars,expected_filtering,description", [
        # Date filtering
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "START_DATE": "2024-01-01",
                "END_DATE": "2024-12-31",
            },
            {
                "start_date": datetime(2024, 1, 1, 0, 0, 0),
                "end_date": datetime(2024, 12, 31, 23, 59, 59),
            },
            "Date range filtering (YYYY-MM-DD format)"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "START_DATE": "2024-01-01 10:30:00",
                "END_DATE": "2024-12-31 15:45:30",
            },
            {
                "start_date": datetime(2024, 1, 1, 10, 30, 0),
                "end_date": datetime(2024, 12, 31, 15, 45, 30),
            },
            "Date range filtering (YYYY-MM-DD HH:MM:SS format)"
        ),
        # Activity type filtering
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_TYPES": "running,cycling,swimming",
            },
            {
                "excluded_activity_types": {"running", "cycling", "swimming"},
            },
            "Activity type filtering"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_TYPES": " running , cycling , swimming ",
            },
            {
                "excluded_activity_types": {"running", "cycling", "swimming"},
            },
            "Activity type filtering with spaces"
        ),
        # Activity ID filtering
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_IDS": "123,456,789",
            },
            {
                "excluded_activity_ids": {ActivityId(123), ActivityId(456), ActivityId(789)},
            },
            "Activity ID filtering"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_IDS": " 123 , 456 , 789 ",
            },
            {
                "excluded_activity_ids": {ActivityId(123), ActivityId(456), ActivityId(789)},
            },
            "Activity ID filtering with spaces"
        ),
        # File type filtering
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_FILE_TYPES": "gpx,tcx",
            },
            {
                "excluded_file_types": {FileType.GPX, FileType.TCX},
            },
            "File type filtering"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_FILE_TYPES": "gpx",
            },
            {
                "excluded_file_types": {FileType.GPX},
            },
            "Single file type filtering"
        ),
    ])
    def test_valid_filtering_config(
        self, 
        env_vars: Dict[str, str], 
        expected_filtering: Dict[str, Any], 
        description: str
    ) -> None:
        """Test that filtering configuration is parsed correctly."""
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            for key, expected_value in expected_filtering.items():
                if key.startswith("excluded_"):
                    actual_value = getattr(config.file_manager_config, key)
                else:
                    actual_value = getattr(config.file_manager_config, key)
                
                assert actual_value == expected_value, (
                    f"{description}: Expected {key}={expected_value}, got {actual_value}"
                )

    @pytest.mark.parametrize("duration_str,expected_td", [
        ("90s", timedelta(seconds=90)),
        ("50m", timedelta(minutes=50)),
        ("1.5h", timedelta(hours=1.5)),
        ("2d", timedelta(days=2)),
    ])
    def test_min_activity_age_parsing(self, duration_str: str, expected_td: timedelta) -> None:
        """Test that MIN_ACTIVITY_AGE is parsed into a timedelta correctly."""
        with patch.dict(os.environ, {
            "GARMIN_USERNAME": "test",
            "GARMIN_PASSWORD": "test",
            "MIN_ACTIVITY_AGE": duration_str,
        }, clear=True):
            config = Config.from_environment()
            assert config.file_manager_config.minimum_activity_age == expected_td


class TestConfigErrorHandling:
    """Test cases for configuration error handling."""
    
    @pytest.mark.parametrize("env_vars,expected_error,description", [
        # Missing required credentials
        (
            {},
            "GARMIN_USERNAME and GARMIN_PASSWORD environment variables are required",
            "Missing both credentials"
        ),
        (
            {"GARMIN_USERNAME": "test"},
            "GARMIN_USERNAME and GARMIN_PASSWORD environment variables are required",
            "Missing password"
        ),
        (
            {"GARMIN_PASSWORD": "test"},
            "GARMIN_USERNAME and GARMIN_PASSWORD environment variables are required",
            "Missing username"
        ),
        # Invalid cron schedule
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "CRON_SCHEDULE": "invalid cron",
            },
            "Invalid cron schedule:",
            "Invalid cron expression"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "CRON_SCHEDULE": '"0 * * * *"',
            },
            "CRON_SCHEDULE cannot contain quotes",
            "Cron with quotes"
        ),
        # Invalid numeric values
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "BATCH_SIZE": "invalid",
            },
            "Invalid BATCH_SIZE value 'invalid': must be a valid integer",
            "Invalid batch size"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "BATCH_SIZE": "50.5",
            },
            "Invalid BATCH_SIZE value '50.5': must be a valid integer",
            "Float for integer field"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "REQUEST_DELAY_SECONDS": "invalid",
            },
            "Invalid REQUEST_DELAY_SECONDS value 'invalid': must be a valid number",
            "Invalid request delay"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "REQUEST_DELAY_SECONDS": "1.2.3",
            },
            "Invalid REQUEST_DELAY_SECONDS value '1.2.3': must be a valid number",
            "Malformed float"
        ),
        # Invalid activity IDs
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_IDS": "123,invalid,456",
            },
            "Invalid EXCLUDED_ACTIVITY_IDS value 'invalid': must be a valid integer",
            "Invalid activity ID in list"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_IDS": "123,456.5,789",
            },
            "Invalid EXCLUDED_ACTIVITY_IDS value '456.5': must be a valid integer",
            "Float activity ID in list"
        ),
        # Invalid file types
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_FILE_TYPES": "gpx,invalid,tcx",
            },
            "Invalid file type 'invalid'",
            "Invalid file type in list"
        ),
        # Cannot exclude activity_json
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_FILE_TYPES": "activity_json",
            },
            "Cannot exclude 'activity_json' file type",
            "Cannot exclude activity_json file type"
        ),
    ])
    def test_config_error_handling(
        self, 
        env_vars: Dict[str, str], 
        expected_error: str, 
        description: str
    ) -> None:
        """Test that invalid configuration raises appropriate errors."""
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError, match=expected_error):
                Config.from_environment()

    @pytest.mark.parametrize("env_vars,expected_error", [
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "MIN_ACTIVITY_AGE": "-5m",
            },
            "Invalid MIN_ACTIVITY_AGE value",
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "MIN_ACTIVITY_AGE": "garbage",
            },
            "Invalid MIN_ACTIVITY_AGE value",
        ),
    ])
    def test_min_activity_age_errors(self, env_vars: Dict[str, str], expected_error: str) -> None:
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError, match=expected_error):
                Config.from_environment()

    @pytest.mark.parametrize("env_vars,description", [
        # Edge cases that should be handled gracefully
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_IDS": "",
            },
            "Empty excluded activity IDs"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_TYPES": "",
            },
            "Empty excluded activity types"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_FILE_TYPES": "",
            },
            "Empty excluded file types"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "EXCLUDED_ACTIVITY_IDS": "123,,456",
            },
            "Empty values in activity ID list"
        ),
        (
            {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "START_DATE": "invalid-date",
            },
            "Invalid date format (should be silently ignored)"
        ),
    ])
    def test_graceful_edge_cases(
        self, 
        env_vars: Dict[str, str], 
        description: str
    ) -> None:
        """Test that edge cases are handled gracefully without errors."""
        with patch.dict(os.environ, env_vars, clear=True):
            # These should not raise exceptions
            config = Config.from_environment()
            assert config is not None, f"{description}: Config creation failed"


class TestConfigSpecialCases:
    """Test cases for special configuration scenarios."""
    
    def test_empty_environment(self) -> None:
        """Test behavior with completely empty environment."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="GARMIN_USERNAME and GARMIN_PASSWORD"):
                Config.from_environment()
    
    def test_boolean_variations(self) -> None:
        """Test various boolean value interpretations."""
        true_values = ["true", "True", "TRUE", "1", "yes", "Yes", "YES", "on", "On", "ON"]
        false_values = ["false", "False", "FALSE", "0", "no", "No", "NO", "off", "Off", "OFF", ""]
        
        for true_val in true_values:
            with patch.dict(os.environ, {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "RUN_IMMEDIATELY_ON_STARTUP": true_val,
            }, clear=True):
                config = Config.from_environment()
                assert config.run_immediately_on_startup is True, f"'{true_val}' should be True"
        
        for false_val in false_values:
            with patch.dict(os.environ, {
                "GARMIN_USERNAME": "test",
                "GARMIN_PASSWORD": "test",
                "RUN_IMMEDIATELY_ON_STARTUP": false_val,
            }, clear=True):
                config = Config.from_environment()
                assert config.run_immediately_on_startup is False, f"'{false_val}' should be False"
    
    def test_numeric_boundary_values(self) -> None:
        """Test numeric values at boundaries."""
        with patch.dict(os.environ, {
            "GARMIN_USERNAME": "test",
            "GARMIN_PASSWORD": "test",
            "REQUEST_DELAY_SECONDS": "0",
            "BATCH_SIZE": "1",
        }, clear=True):
            config = Config.from_environment()
            assert config.request_delay_seconds == 0.0
            assert config.batch_size == 1
    
    def test_whitespace_handling(self) -> None:
        """Test that whitespace in comma-separated values is handled correctly."""
        with patch.dict(os.environ, {
            "GARMIN_USERNAME": "test",
            "GARMIN_PASSWORD": "test",
            "EXCLUDED_ACTIVITY_IDS": " 123 , 456 , 789 ",
            "EXCLUDED_ACTIVITY_TYPES": " running , cycling ",
            "EXCLUDED_FILE_TYPES": " gpx , tcx ",
        }, clear=True):
            config = Config.from_environment()
            assert config.file_manager_config.excluded_activity_ids == {ActivityId(123), ActivityId(456), ActivityId(789)}
            assert config.file_manager_config.excluded_activity_types == {"running", "cycling"}
            assert config.file_manager_config.excluded_file_types == {FileType.GPX, FileType.TCX} 