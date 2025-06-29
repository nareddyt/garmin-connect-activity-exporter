#!/usr/bin/env python3
"""
Activity utilities for Garmin Connect data.

This module provides shared utility functions for working with Garmin Connect
activity data to avoid code duplication across the codebase.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Dict, Any, Optional

from source.contextual_logger import ContextualLoggerAdapter

ActivityId = int

@dataclass
class Activity:
    raw: Dict[str, Any]
    
    id: ActivityId
    name: str
    type: str
    start_time_gmt: datetime
    hasPolyline: bool

    def __str__(self) -> str:
        return f"Activity {self.id}"

    def __lt__(self, other: 'Activity') -> bool:
        """Enable sorting by activity ID."""
        return self.id < other.id
    
    def __eq__(self, other: object) -> bool:
        """Enable equality comparison by activity ID."""
        if not isinstance(other, Activity):
            return NotImplemented
        return self.id == other.id

    def dump(self) -> bytes:
        return json.dumps(self.raw, indent=2, sort_keys=True).encode('utf-8')
    
    def add_logger_context(self, logger: ContextualLoggerAdapter) -> ContextualLoggerAdapter:
        return logger.with_context(
            activity_id=self.id,
            activity_type=self.type,
            activity_name=self.name,
            activity_start_time_gmt=self.start_time_gmt,
            activity_has_polyline=self.hasPolyline,
        )

    @classmethod
    def from_api_response(cls, response: Dict[str, Any]) -> 'Activity':
        activity_id: int = response['activityId']
        return cls(
            raw=response,
            id=activity_id,
            name=response['activityName'],
            type=response['activityType']['typeKey'],
            start_time_gmt=Activity._get_activity_date(response),
            hasPolyline=response['hasPolyline'],
        )

    @staticmethod
    def _get_activity_date(response: Dict[str, Any]) -> datetime:
        date_str: Optional[str] = response.get('startTimeGMT')
        if not date_str:
            raise ValueError(f"No start time found in response: {response}")
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)