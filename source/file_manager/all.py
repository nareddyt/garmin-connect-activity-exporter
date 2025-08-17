#!/usr/bin/env python3
"""
Filename format utilities for Garmin Connect files.

This module centralizes the filename format logic to avoid duplication
throughout the codebase and provides a single source of truth for the
naming convention.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import difflib
from pathlib import Path
from typing import Any, Dict, Optional, Set
import json
from source.activity import Activity, ActivityId
from source.contextual_logger import ContextualLoggerAdapter
from source.file_manager.per_activity import ActivityFileManager
from source.file_type import FileType

@dataclass
class FileManagerConfig:
    excluded_activity_ids: Set[ActivityId]
    excluded_activity_types: Set[str]
    excluded_file_types: Set[FileType]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    minimum_activity_age: Optional[timedelta] = None

class FileManager:
    config: FileManagerConfig
    download_directory: Path
    downloaded_activities: Dict[ActivityId, ActivityFileManager]

    def __init__(self, config: FileManagerConfig, download_directory: Path) -> None:
        self.config = config
        self.download_directory = download_directory
        self.downloaded_activities = {}

    def should_ignore_file(self, file_path: Path) -> bool:
        """Check if a file should be ignored during processing."""
        ignored_filenames: Set[str] = {'.DS_Store', 'Thumbs.db', '.gitkeep', '.gitignore'}
        ignored_extensions: Set[str] = {'.tmp', '.temp', '.swp', '.bak'}
        
        # Ignore system files and temporary files
        if file_path.name in ignored_filenames:
            return True
        if file_path.suffix.lower() in ignored_extensions:
            return True
        
        return False

    def add_preexisting_file(self, file_path: Path) -> None:
        if self.should_ignore_file(file_path):
            return
            
        try:
            file_type = FileType(file_path.parent.name)
        except ValueError:
            raise ValueError(f"Invalid file type {file_path.parent.name} in {file_path}")
        
        activity_file_manager: ActivityFileManager = ActivityFileManager.create_from_file_path(file_path, file_type)

        if activity_file_manager.activity_id not in self.downloaded_activities:
            self.downloaded_activities[activity_file_manager.activity_id] = activity_file_manager
            return
        
        self.downloaded_activities[activity_file_manager.activity_id].download_file_types.add(file_type)

    def _retrieve_download_path(self, activity: Activity, file_type: FileType) -> Path:
        file_name: str = self.downloaded_activities[activity.id].format_into_filename(activity, file_type)
        return self.download_directory / file_type.value / file_name

    def record_and_retrieve_download_path(self, logger: ContextualLoggerAdapter, activity: Activity, file_type: FileType) -> Optional[Path]:
        if activity.id in self.downloaded_activities and file_type in self.downloaded_activities[activity.id].download_file_types:
            logger.debug(f"Skipping already downloaded activity")
            return None
        
        if activity.id in self.config.excluded_activity_ids:
            logger.debug(f"Skipping excluded activity by ID")
            return None
        
        if activity.type in self.config.excluded_activity_types:
            logger.debug(f"Skipping excluded activity by type")
            return None
        
        if file_type in self.config.excluded_file_types:
            logger.debug(f"Skipping excluded file type")
            return None

        if self.config.start_date and activity.start_time_gmt < self.config.start_date:
            logger.debug(f"Skipping activity before start date")
            return None
        
        if self.config.end_date and activity.start_time_gmt > self.config.end_date:
            logger.debug(f"Skipping activity after end date")
            return None
        
        if self.config.minimum_activity_age is not None:
            now_utc: datetime = datetime.now(timezone.utc)
            cutoff_time: datetime = now_utc - self.config.minimum_activity_age
            if activity.start_time_gmt > cutoff_time:
                logger.debug(f"Skipping activity newer than minimum age")
                return None

        if (file_type == FileType.GPX or file_type == FileType.TCX) and not activity.hasPolyline:
            logger.debug(f"Skipping activity GPS data without polyline data")
            return None

        self._record_download_path(activity.id, file_type)
        return self._retrieve_download_path(activity, file_type)
    
    def mark_activity_as_redownloadable(self, activity: Activity, logger: ContextualLoggerAdapter) -> None:
        """Mark activity for redownload and delete existing files from filesystem."""
        if activity.id not in self.downloaded_activities:
            raise ValueError(f"Cannot mark activity {activity.id} as redownloadable: activity not tracked in file manager")
            
        # Delete physical files for all recorded file types
        for file_type in self.downloaded_activities[activity.id].download_file_types:
            file_path: Path = self._retrieve_download_path(activity, file_type)
            if file_path.exists():
                logger.debug(f"Deleted existing file {file_path}")
                file_path.unlink()
        
        # Clear the downloaded file types to mark for redownload
        self.downloaded_activities[activity.id].download_file_types = set()

    def check_for_activity_changes(self, activity: Activity, activity_logger: ContextualLoggerAdapter) -> None:
        """Check if activity data has changed compared to existing file and mark for redownload if different."""
        if activity.id not in self.downloaded_activities:
            return
            
        if FileType.ACTIVITY_JSON not in self.downloaded_activities[activity.id].download_file_types:
            return
            
        existing_file_path: Path = self._retrieve_download_path(activity, FileType.ACTIVITY_JSON)
        
        if not existing_file_path.exists():
            activity_logger.warning("Existing activity JSON file not found, marking for redownload")
            self.mark_activity_as_redownloadable(activity, activity_logger)
            return
            
        with open(existing_file_path, 'rb') as f:
            existing_data: bytes = f.read()
        
        current_data: bytes = activity.dump()
        
        if current_data == existing_data:
            return
        
        # Generate and log the diff
        current_lines: list[str] = current_data.decode('utf-8').splitlines(keepends=True)
        existing_lines: list[str] = existing_data.decode('utf-8').splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            existing_lines, 
            current_lines, 
            fromfile=f"existing_{activity.id}.json",
            tofile=f"current_{activity.id}.json",
            lineterm=""
        ))
        
        if diff:
            diff_text: str = ''.join(diff)
            activity_logger.warning(f"Activity data has changed, marking for redownload. Diff:\n{diff_text}")
        else:
            activity_logger.warning("Activity data has changed (binary difference), marking for redownload")
        
        self.mark_activity_as_redownloadable(activity, activity_logger)

    def __str__(self) -> str:
        return f"{sorted(self.downloaded_activities.values(), reverse=True)}"
    
    def _record_download_path(self, activity_id: ActivityId, file_type: FileType) -> None:
        if activity_id not in self.downloaded_activities:
            self.downloaded_activities[activity_id] = ActivityFileManager(activity_id=activity_id, download_file_types=set())
        self.downloaded_activities[activity_id].download_file_types.add(file_type)