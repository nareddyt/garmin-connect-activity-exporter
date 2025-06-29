#!/usr/bin/env python3
"""
Unit tests for ActivityFileManager roundtrip functionality.

Tests the create_from_file_path -> format_into_filename roundtrip
to ensure filename preservation across different file types and activities.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from source.activity import Activity
from source.file_manager.per_activity import ActivityFileManager
from source.file_type import FileType


@pytest.fixture
def testdata_dir() -> Path:
    """Return the path to the test data directory."""
    return Path(__file__).parent.parent.parent / "testdata"


@pytest.fixture
def run_activity_data(testdata_dir: Path) -> Dict[str, Any]:
    """Load run activity test data."""
    with open(testdata_dir / "activity_json" / "run_activity.json", 'r') as f:
        return json.load(f)


@pytest.fixture
def bike_activity_data(testdata_dir: Path) -> Dict[str, Any]:
    """Load bike activity test data."""
    with open(testdata_dir / "activity_json" / "bike_activity.json", 'r') as f:
        return json.load(f)


@pytest.fixture
def hike_activity_data(testdata_dir: Path) -> Dict[str, Any]:
    """Load hike activity test data.""" 
    with open(testdata_dir / "activity_json" / "hike_activity.json", 'r') as f:
        return json.load(f)


@pytest.mark.parametrize("file_path_str,file_type,activity_fixture", [
    # GPX files
    ("2024-01-15-08-30-00_activity_12345678901_running_Morning_Run_in_Central_Park.gpx", 
     FileType.GPX, "run_activity_data"),
    ("2024-02-20-14-15-30_activity_23456789012_cycling_Weekend_Bike_Ride___Hill_Training.gpx", 
     FileType.GPX, "bike_activity_data"),
        ("2024-03-10-12-00-00_activity_34567890123_hiking_Mountain_Trail_Hike.gpx",
     FileType.GPX, "hike_activity_data"),
    
    # TCX files
    ("2024-01-15-08-30-00_activity_12345678901_running_Morning_Run_in_Central_Park.tcx", 
     FileType.TCX, "run_activity_data"),
    ("2024-02-20-14-15-30_activity_23456789012_cycling_Weekend_Bike_Ride___Hill_Training.tcx", 
     FileType.TCX, "bike_activity_data"),
        ("2024-03-10-12-00-00_activity_34567890123_hiking_Mountain_Trail_Hike.tcx",
     FileType.TCX, "hike_activity_data"),
    
    # Activity JSON files
    ("2024-01-15-08-30-00_activity_12345678901_running_Morning_Run_in_Central_Park.json", 
     FileType.ACTIVITY_JSON, "run_activity_data"),
    ("2024-02-20-14-15-30_activity_23456789012_cycling_Weekend_Bike_Ride___Hill_Training.json", 
     FileType.ACTIVITY_JSON, "bike_activity_data"),
        ("2024-03-10-12-00-00_activity_34567890123_hiking_Mountain_Trail_Hike.json",
     FileType.ACTIVITY_JSON, "hike_activity_data"),
])
def test_roundtrip_filename_preservation(file_path_str: str, file_type: FileType, activity_fixture: str, request: pytest.FixtureRequest):
    """Test that create_from_file_path -> format_into_filename preserves the original filename."""
    # Get the activity data from the fixture
    activity_data = request.getfixturevalue(activity_fixture)
    
    # Create Activity object from test data
    activity = Activity.from_api_response(activity_data)
    
    # Create file path
    file_path = Path(file_path_str)
    
    # Step 1: Create ActivityFileManager from file path
    manager = ActivityFileManager.create_from_file_path(file_path, file_type)
    
    # Verify the activity ID matches
    assert manager.activity_id == activity.id
    assert file_type in manager.download_file_types
    
    # Step 2: Format back into filename
    formatted_filename = manager.format_into_filename(activity, file_type)
    
    # Step 3: Verify roundtrip preservation
    assert formatted_filename == file_path.name, (
        f"Roundtrip failed for {file_type.value}: "
        f"expected '{file_path.name}', got '{formatted_filename}'"
    )


def test_create_from_file_path_invalid_suffix():
    """Test that create_from_file_path raises ValueError for mismatched file suffixes."""
    file_path = Path("2024-01-15-08-30-00_activity_12345678901_running_Test.gpx")
    
    with pytest.raises(ValueError, match="Invalid filename, no matching file type"):
        ActivityFileManager.create_from_file_path(file_path, FileType.TCX)


def test_create_from_file_path_invalid_format():
    """Test that create_from_file_path raises ValueError for invalid filename format."""
    file_path = Path("invalid_filename_format.gpx")
    
    with pytest.raises(ValueError, match="Invalid filename, no activity marker"):
        ActivityFileManager.create_from_file_path(file_path, FileType.GPX)


def test_format_into_filename_activity_id_mismatch(run_activity_data):
    """Test that format_into_filename raises ValueError when activity IDs don't match."""
    # Create manager with different activity ID
    manager = ActivityFileManager(
        activity_id=1919,
        download_file_types={FileType.GPX}
    )
    
    activity = Activity.from_api_response(run_activity_data)
    
    with pytest.raises(ValueError, match="Activity ID mismatch"):
        manager.format_into_filename(activity, FileType.GPX)


def test_format_into_filename_file_type_not_downloaded(run_activity_data):
    """Test that format_into_filename raises ValueError when file type not downloaded."""
    activity = Activity.from_api_response(run_activity_data)
    
    manager = ActivityFileManager(
        activity_id=activity.id,
        download_file_types={FileType.GPX}  # Only GPX downloaded
    )
    
    with pytest.raises(ValueError, match="File type 'tcx' not downloaded yet"):
        manager.format_into_filename(activity, FileType.TCX)


@pytest.mark.parametrize("input_name,expected_sanitized", [
    ("Normal Activity Name", "Normal_Activity_Name"),
    ("Activity/With\\Slashes", "Activity_With_Slashes"),
    ("Activity with special chars !@#$%", "Activity_with_special_chars"),
    ("", "unnamed"),
    ("A" * 100, "A" * 50),  # Test length truncation
    ("   Spaces   ", "Spaces"),  # Test trimming
])
def test_sanitize_filename_component(input_name: str, expected_sanitized: str):
    """Test filename sanitization with various inputs."""
    result = ActivityFileManager._sanitize_filename_component(input_name)
    assert result == expected_sanitized


def test_format_start_time():
    """Test start time formatting."""
    test_time = datetime(2024, 1, 15, 8, 30, 0, tzinfo=timezone.utc)
    formatted = ActivityFileManager._format_start_time(test_time)
    assert formatted == "2024-01-15-08-30-00" 