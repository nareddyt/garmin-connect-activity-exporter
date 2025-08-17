#!/usr/bin/env python3
"""
Configuration management for Garmin GPX Exporter.
"""

import os
import sys
from datetime import datetime, timedelta
from humanfriendly import parse_timespan
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Set
from croniter import croniter
from source.activity import ActivityId
from source.file_manager.all import FileManagerConfig
from source.file_type import FileType

@dataclass
class Config:
    """Strongly typed configuration for Garmin GPX Exporter."""
    
    # Required Garmin credentials
    garmin_username: str
    garmin_password: str
    
    # Logging
    log_level: str
    
    # Scheduling
    cron_schedule: str
    run_immediately_on_startup: bool
    
    # Rate limiting
    request_delay_seconds: float
    batch_size: int
    
    # Activity change detection
    check_for_activity_changes: bool
    
    # Activity processing behavior
    always_recheck_all_activities: bool
    
    # Activity filtering
    file_manager_config: FileManagerConfig
    
    # File paths - hardcoded, change docker volume mount instead
    download_directory: Path = Path('/app/garmin_downloads')
    session_directory: Path = Path('/app/garmin_session')
    
    @classmethod
    def from_environment(cls) -> 'Config':
        """Load configuration from environment variables with defaults."""
        
        # Required environment variables
        garmin_username: Optional[str] = os.getenv('GARMIN_USERNAME')
        garmin_password: Optional[str] = os.getenv('GARMIN_PASSWORD')
        
        if not garmin_username or not garmin_password:
            raise ValueError("GARMIN_USERNAME and GARMIN_PASSWORD environment variables are required")
        
        # Logging
        log_level: str = os.getenv('LOG_LEVEL', 'INFO')
        
        # Scheduling
        cron_schedule: str = os.getenv('CRON_SCHEDULE', '0 */8 * * *')
        if '"' in cron_schedule or "'" in cron_schedule:
            raise ValueError("CRON_SCHEDULE cannot contain quotes")

        try:
            croniter(cron_schedule)
        except ValueError as e:
            raise ValueError(f"Invalid cron schedule: {e}")
        
        run_immediately_on_startup: bool = os.getenv('RUN_IMMEDIATELY_ON_STARTUP', 'true').lower() in ('true', '1', 'yes', 'on')
        
        def _parse_int_env(env_name: str, default_value: str) -> int:
            """Parse integer from environment variable with error handling."""
            env_value = os.getenv(env_name, default_value)
            try:
                return int(env_value)
            except ValueError:
                raise ValueError(f"Invalid {env_name} value '{env_value}': must be a valid integer")
        
        def _parse_float_env(env_name: str, default_value: str) -> float:
            """Parse float from environment variable with error handling."""
            env_value = os.getenv(env_name, default_value)
            try:
                return float(env_value)
            except ValueError:
                raise ValueError(f"Invalid {env_name} value '{env_value}': must be a valid number")
        
        # Rate limiting
        request_delay_seconds: float = _parse_float_env('REQUEST_DELAY_SECONDS', '10')
        batch_size: int = _parse_int_env('BATCH_SIZE', '30')
        
        # Activity change detection
        check_for_activity_changes: bool = os.getenv('CHECK_FOR_ACTIVITY_CHANGES', 'true').lower() in ('true', '1', 'yes', 'on')
        
        # Activity processing behavior
        always_recheck_all_activities: bool = os.getenv('ALWAYS_RECHECK_ALL_ACTIVITIES', 'false').lower() in ('true', '1', 'yes', 'on')
        
        def _parse_date_env(env_value: Optional[str], env_name: str, is_end_date: bool = False) -> Optional[datetime]:
            """Parse date from environment variable, supporting both date and datetime formats."""
            if not env_value:
                return None
            
            try:
                # Try parsing as datetime first (YYYY-MM-DD HH:MM:SS)
                return datetime.strptime(env_value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    # Fall back to date only (YYYY-MM-DD)
                    parsed_date = datetime.strptime(env_value, '%Y-%m-%d')
                    if is_end_date:
                        # Set time to end of day for end dates
                        return parsed_date.replace(hour=23, minute=59, second=59)
                    return parsed_date  # Midnight for start dates
                except ValueError:
                    print(f"Warning: Invalid {env_name} format: {env_value}", file=sys.stderr)
                    return None

        # Activity filtering - date range
        start_date: Optional[datetime] = _parse_date_env(os.getenv('START_DATE'), 'START_DATE')
        end_date: Optional[datetime] = _parse_date_env(os.getenv('END_DATE'), 'END_DATE', is_end_date=True)
        
        def _parse_duration_env(env_name: str) -> Optional[timedelta]:
            env_value: Optional[str] = os.getenv(env_name)
            if not env_value:
                return None
            try:
                seconds: float = parse_timespan(env_value)
            except Exception:
                raise ValueError(
                    f"Invalid {env_name} value '{env_value}': must be a valid duration like '5m', '6h', '2d'"
                )
            if seconds < 0:
                raise ValueError(f"Invalid {env_name} value '{env_value}': must be non-negative")
            return timedelta(seconds=seconds)

        # Activity filtering - minimum activity age (relative to now)
        minimum_activity_age: Optional[timedelta] = _parse_duration_env('MIN_ACTIVITY_AGE')

        # Activity filtering - excluded types
        excluded_activity_types: Set[str] = set()
        excluded_types_env: Optional[str] = os.getenv('EXCLUDED_ACTIVITY_TYPES')
        if excluded_types_env:
            excluded_activity_types = {t.strip() for t in excluded_types_env.split(',') if t.strip()}
        
        # Activity filtering - excluded IDs
        excluded_activity_ids: Set[ActivityId] = set()
        excluded_ids_env: Optional[str] = os.getenv('EXCLUDED_ACTIVITY_IDS')
        if excluded_ids_env:
            for activity_id_str in excluded_ids_env.split(','):
                activity_id_str = activity_id_str.strip()
                if activity_id_str:
                    try:
                        excluded_activity_ids.add(ActivityId(int(activity_id_str)))
                    except ValueError:
                        raise ValueError(f"Invalid EXCLUDED_ACTIVITY_IDS value '{activity_id_str}': must be a valid integer")
        
        # Activity filtering - excluded file types
        excluded_file_types: Set[FileType] = set()
        excluded_file_types_env: Optional[str] = os.getenv('EXCLUDED_FILE_TYPES')
        if excluded_file_types_env:
            file_type_strings: list[str] = [t.strip() for t in excluded_file_types_env.split(',') if t.strip()]
            valid_file_type_values: Set[str] = {ft.value for ft in FileType}
            
            for file_type_str in file_type_strings:
                if file_type_str not in valid_file_type_values:
                    raise ValueError(f"Invalid file type '{file_type_str}'. Valid values: {', '.join(valid_file_type_values)}")
                if file_type_str == FileType.ACTIVITY_JSON.value:
                    raise ValueError(f"Cannot exclude '{FileType.ACTIVITY_JSON.value}' file type. Activity JSON files are required for the tool to function properly.")
                excluded_file_types.add(FileType(file_type_str))
        
        return cls(
            garmin_username=garmin_username,
            garmin_password=garmin_password,
            log_level=log_level,
            cron_schedule=cron_schedule,
            run_immediately_on_startup=run_immediately_on_startup,
            request_delay_seconds=request_delay_seconds,
            batch_size=batch_size,
            check_for_activity_changes=check_for_activity_changes,
            always_recheck_all_activities=always_recheck_all_activities,
            file_manager_config=FileManagerConfig(
                excluded_activity_ids=excluded_activity_ids,
                excluded_activity_types=excluded_activity_types,
                excluded_file_types=excluded_file_types,
                start_date=start_date,
                end_date=end_date,
                minimum_activity_age=minimum_activity_age,
            )
        ) 