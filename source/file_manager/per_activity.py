#!/usr/bin/env python3
"""
Filename format utilities for Garmin Connect files.

This module centralizes the filename format logic to avoid duplication
throughout the codebase and provides a single source of truth for the
naming convention.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import LiteralString, Set
from source.activity import Activity, ActivityId
from source.file_type import FileType

ACTIVITY_MARKER = "activity"

@dataclass
class ActivityFileManager:

    activity_id: ActivityId
    download_file_types: Set[FileType]
        
    def __str__(self) -> str:
        file_types_str: str = ", ".join(sorted([ft.value for ft in self.download_file_types]))
        if not file_types_str:
            file_types_str = "none"
        return f"{self.activity_id} [{file_types_str}]"
    
    def __repr__(self) -> str:
        return self.__str__()
        
    def __lt__(self, other: 'ActivityFileManager') -> bool:
        """Enable sorting by activity ID."""
        return self.activity_id < other.activity_id
    
    def __eq__(self, other: object) -> bool:
        """Enable equality comparison by activity ID."""
        if not isinstance(other, ActivityFileManager):
            return NotImplemented
        return self.activity_id == other.activity_id
        
    def format_into_filename(self, activity: Activity, file_type: FileType) -> str:
        # Verify activity_id matches the activity dictionary
        if activity.id != self.activity_id:
            raise ValueError(f"Activity ID mismatch: instance has '{self.activity_id}' but activity dict has '{activity.id}'")
        
        # Verify we already have this file type
        if file_type not in self.download_file_types:
            raise ValueError(f"File type '{file_type.value}' not downloaded yet for this activity")

        date_prefix = ActivityFileManager._format_start_time(activity.start_time_gmt)
        activity_name_clean = ActivityFileManager._sanitize_filename_component(activity.name)

        return f"{date_prefix}_{ACTIVITY_MARKER}_{activity.id}_{activity.type}_{activity_name_clean}.{file_type.suffix}"
    
    @staticmethod
    def create_from_file_path(file_path: Path, file_type: FileType) -> 'ActivityFileManager':
        if not file_path.suffix == f".{file_type.suffix}":
            raise ValueError(f"Invalid filename, no matching file type: {file_path.suffix} != {file_type.suffix}")
        
        parts: list[str] = file_path.name.split('_')
        if len(parts) < 3 or parts[1] != ACTIVITY_MARKER:
            raise ValueError(f"Invalid filename, no activity marker: {file_path.name}")
        
        try:
            activity_id = int(parts[2])
        except ValueError:
            raise ValueError(f"Invalid filename, activity ID is not numeric: '{parts[2]}' in {file_path.name}")
        
        return ActivityFileManager(
            activity_id=activity_id,
            download_file_types={file_type}
        )
    
    @staticmethod
    def _sanitize_filename_component(name: str) -> str:
        # Replace filesystem-unsafe characters
        sanitized = name.replace('/', '_').replace('\\', '_')
        
        # Keep only alphanumeric, spaces, hyphens, and underscores
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c in (' ', '-', '_')).strip()
        
        # Replace spaces with underscores and limit length
        sanitized = sanitized.replace(' ', '_')[:50]
        
        return sanitized if sanitized else 'unnamed'
    
    @staticmethod
    def _format_start_time(start_time: datetime) -> str:
        return start_time.strftime('%Y-%m-%d-%H-%M-%S')
        
