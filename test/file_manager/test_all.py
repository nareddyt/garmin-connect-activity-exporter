#!/usr/bin/env python3
"""
Unit tests for FileManager functionality.

Tests the FileManager's ability to track preexisting files and prevent
re-downloading, as well as all filtering logic.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Set, Optional
from unittest.mock import Mock

from source.activity import Activity
from source.file_manager.all import FileManager, FileManagerConfig
from source.file_manager.per_activity import ActivityFileManager
from source.file_type import FileType
from source.contextual_logger import ContextualLoggerAdapter, setup_contextual_logger


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


@pytest.fixture
def indoor_cardio_activity_data(testdata_dir: Path) -> Dict[str, Any]:
    """Load indoor cardio activity test data (has hasPolyline=false)."""
    with open(testdata_dir / "activity_json" / "indoor_cardio_activity.json", 'r') as f:
        return json.load(f)


@pytest.fixture
def test_logger() -> ContextualLoggerAdapter:
    """Create a real logger for testing."""
    return setup_contextual_logger(__name__, 'DEBUG')


@pytest.fixture
def default_config() -> FileManagerConfig:
    """Create a default FileManagerConfig for testing."""
    return FileManagerConfig(
        excluded_activity_ids=set(),
        excluded_activity_types=set(),
        excluded_file_types=set(),
        start_date=None,
        end_date=None
    )


@pytest.fixture
def download_directory(tmp_path: Path) -> Path:
    """Create a temporary download directory."""
    return tmp_path / "downloads"


class TestFileManager:
    """Test cases for FileManager class."""

    @pytest.mark.parametrize("preexisting_files,activity_fixture,test_cases", [
        # Test case 1: File already exists - should return None
        (
            [
                ("activity_json/2024-01-15-08-30-00_activity_12345678901_running_Morning_Run_in_Central_Park.json", FileType.ACTIVITY_JSON),
                ("gpx/2024-01-15-08-30-00_activity_12345678901_running_Morning_Run_in_Central_Park.gpx", FileType.GPX),
            ],
            "run_activity_data",
            [
                # Should return None - file already exists
                (FileType.ACTIVITY_JSON, None, "File already exists"),
                (FileType.GPX, None, "File already exists"),
                # Should succeed - file doesn't exist yet
                (FileType.TCX, "expected_path", "New file type"),
            ]
        ),
        # Test case 2: No preexisting files - should succeed for all
        (
            [],
            "bike_activity_data", 
            [
                (FileType.ACTIVITY_JSON, "expected_path", "New file"),
                (FileType.GPX, "expected_path", "New file"),
                (FileType.TCX, "expected_path", "New file"),
            ]
        ),
        # Test case 3: Mixed scenario
        (
            [
                ("tcx/2024-03-10-09-45-15_activity_34567890123_hiking_Mountain_Trail_Hike.tcx", FileType.TCX),
            ],
            "hike_activity_data",
            [
                (FileType.ACTIVITY_JSON, "expected_path", "New file type"),
                (FileType.GPX, "expected_path", "New file type"),
                (FileType.TCX, None, "File already exists"),
            ]
        ),
    ])
    def test_preexisting_file_detection(
        self, 
        preexisting_files: list[tuple[str, FileType]], 
        activity_fixture: str,
        test_cases: Any,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        request: pytest.FixtureRequest
    ) -> None:
        """Test that preexisting files are detected and prevent re-downloading."""
        # Phase 1: Initialize FileManager with preexisting files
        file_manager = FileManager(default_config, download_directory)
        
        for file_path_str, file_type in preexisting_files:
            file_path = download_directory / file_path_str
            file_manager.add_preexisting_file(file_path)
        
        # Get the activity data from the fixture
        activity_data = request.getfixturevalue(activity_fixture)
        activity = Activity.from_api_response(activity_data)
        
        # Phase 2: Test record_and_retrieve_download_path
        for file_type, expected_result, description in test_cases:
            result: Optional[Path] = file_manager.record_and_retrieve_download_path(test_logger, activity, file_type)
            
            if expected_result is None:
                assert result is None, f"Expected None for {description}, got {result}"
            else:
                assert result is not None, f"Expected path for {description}, got None"
                assert isinstance(result, Path), f"Expected Path object for {description}"
                # Verify the path contains the expected components
                assert str(activity.id) in str(result)
                assert file_type.value in str(result)

    @pytest.mark.parametrize("config_overrides,activity_fixture,file_type,expected_result,reason", [
        # Test excluded activity IDs
        (
            {"excluded_activity_ids": {12345678901}},
            "run_activity_data",
            FileType.GPX,
            None,
            "Activity ID excluded"
        ),
        # Test excluded activity types  
        (
            {"excluded_activity_types": {"cycling"}},
            "bike_activity_data", 
            FileType.GPX,
            None,
            "Activity type excluded"
        ),
        # Test excluded file types
        (
            {"excluded_file_types": {FileType.TCX}},
            "hike_activity_data",
            FileType.TCX, 
            None,
            "File type excluded"
        ),
        # Test start date filtering (activity too old)
        (
            {"start_date": datetime(2024, 6, 1, tzinfo=timezone.utc)},
            "run_activity_data",  # 2024-01-15
            FileType.GPX,
            None,
            "Activity before start date"
        ),
        # Test end date filtering (activity too new)
        (
            {"end_date": datetime(2024, 1, 1, 23, 59, 59, tzinfo=timezone.utc)},
            "run_activity_data",  # 2024-01-15
            FileType.GPX,
            None,
            "Activity after end date"
        ),
        # Test success case with date range
        (
            {"start_date": datetime(2024, 1, 1, tzinfo=timezone.utc), "end_date": datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)},
            "run_activity_data",  # 2024-01-15
            FileType.GPX,
            "expected_path",
            "Activity within date range"
        ),
        # Test minimum activity age filtering (activity too new relative to huge minimum age)
        (
            {"minimum_activity_age": timedelta(days=36500)},  # ~100 years
            "run_activity_data",  # 2024-01-15
            FileType.GPX,
            None,
            "Activity newer than minimum activity age"
        ),
        # Test minimum activity age filtering (activity is old enough relative to a small minimum age)
        (
            {"minimum_activity_age": timedelta(minutes=1)},
            "run_activity_data",  # 2024-01-15
            FileType.GPX,
            "expected_path",
            "Activity older than minimum activity age"
        ),
    ])
    def test_filtering_logic(
        self,
        config_overrides: Dict[str, Any],
        activity_fixture: str,
        file_type: FileType,
        expected_result: Optional[Path],
        reason: str,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        request: pytest.FixtureRequest
    ):
        """Test all the filtering logic that can cause record_and_retrieve_download_path to return None."""
        # Apply config overrides
        config_dict = {
            "excluded_activity_ids": default_config.excluded_activity_ids,
            "excluded_activity_types": default_config.excluded_activity_types, 
            "excluded_file_types": default_config.excluded_file_types,
            "start_date": default_config.start_date,
            "end_date": default_config.end_date,
        }
        config_dict.update(config_overrides)
        
        config = FileManagerConfig(**config_dict)
        file_manager = FileManager(config, download_directory)
        
        # Get the activity data from the fixture
        activity_data = request.getfixturevalue(activity_fixture)
        activity = Activity.from_api_response(activity_data)
        
        result = file_manager.record_and_retrieve_download_path(test_logger, activity, file_type)
        
        if expected_result is None:
            assert result is None, f"Expected None for {reason}, got {result}"
        else:
            assert result is not None, f"Expected path for {reason}, got None"
            assert isinstance(result, Path), f"Expected Path object for {reason}"

    def test_polyline_requirement_for_gps_files(
        self, 
        default_config: FileManagerConfig, 
        download_directory: Path, 
        test_logger: ContextualLoggerAdapter, 
        indoor_cardio_activity_data: Dict[str, Any]
    ) -> None:
        """Test that GPX/TCX files require hasPolyline=True."""
        file_manager = FileManager(default_config, download_directory)
        
        # Use indoor cardio activity which already has hasPolyline=False
        activity = Activity.from_api_response(indoor_cardio_activity_data)
        
        # GPS file types should return None
        gpx_result = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.GPX)
        tcx_result = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.TCX)
        
        assert gpx_result is None, "Expected None for GPX without polyline"
        assert tcx_result is None, "Expected None for TCX without polyline"
        
        # Activity JSON should still work
        json_result = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        assert json_result is not None, "Expected path for activity JSON without polyline"

    def test_polyline_requirement_with_polyline_data(
        self, 
        default_config: FileManagerConfig, 
        download_directory: Path, 
        test_logger: ContextualLoggerAdapter, 
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that GPX/TCX files work when hasPolyline=True."""
        file_manager = FileManager(default_config, download_directory)
        
        # Use activity with polyline data (default in test data)
        activity = Activity.from_api_response(run_activity_data)
        
        # All file types should work
        gpx_result = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.GPX)
        tcx_result = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.TCX)
        json_result = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        
        assert gpx_result is not None, "Expected path for GPX with polyline"
        assert tcx_result is not None, "Expected path for TCX with polyline"
        assert json_result is not None, "Expected path for activity JSON"

    def test_path_construction(
        self, 
        default_config: FileManagerConfig, 
        download_directory: Path, 
        test_logger: ContextualLoggerAdapter, 
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that returned paths are constructed correctly."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        result = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.GPX)
        
        assert result is not None
        assert result.parent.name == FileType.GPX.value  # Should be in gpx/ subdirectory
        assert str(activity.id) in result.name
        assert result.suffix == f".{FileType.GPX.suffix}"
        assert "activity" in result.name

    def test_multiple_file_types_same_activity(
        self, 
        default_config: FileManagerConfig, 
        download_directory: Path, 
        test_logger: ContextualLoggerAdapter, 
        run_activity_data: Dict[str, Any]
    ):
        """Test that multiple file types for the same activity work correctly."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        # First download should succeed for all types
        json_result1 = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        gpx_result1 = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.GPX)
        tcx_result1 = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.TCX)
        
        assert json_result1 is not None
        assert gpx_result1 is not None
        assert tcx_result1 is not None
        
        # Second download should return None (already recorded)
        json_result2 = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        gpx_result2 = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.GPX)
        tcx_result2 = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.TCX)
        
        assert json_result2 is None, "Expected None for second JSON download"
        assert gpx_result2 is None, "Expected None for second GPX download"
        assert tcx_result2 is None, "Expected None for second TCX download"

    def test_str_representation(self, default_config: FileManagerConfig, download_directory: Path):
        """Test the string representation shows tracked activities correctly."""
        file_manager = FileManager(default_config, download_directory)
        
        # Add some preexisting files
        files = [
            ("activity_json/2024-01-15-08-30-00_activity_12345678901_running_Test.json", FileType.ACTIVITY_JSON),
            ("gpx/2024-01-15-08-30-00_activity_12345678901_running_Test.gpx", FileType.GPX),
            ("tcx/2024-02-20-14-15-30_activity_23456789012_cycling_Test.tcx", FileType.TCX),
        ]
        
        for file_path_str, file_type in files:
            file_path = download_directory / file_path_str
            file_manager.add_preexisting_file(file_path)
        
        str_repr = str(file_manager)
        
        # Should contain the activity IDs
        assert "12345678901" in str_repr
        assert "23456789012" in str_repr
        
        # Should show file types
        assert "activity_json" in str_repr
        assert "gpx" in str_repr
        assert "tcx" in str_repr

    def test_mark_activity_as_redownloadable_selective_behavior(
        self,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        run_activity_data: Dict[str, Any],
        bike_activity_data: Dict[str, Any]
    ) -> None:
        """Test that mark_activity_as_redownloadable only affects the specified activity, not others."""
        file_manager = FileManager(default_config, download_directory)
        
        # Create activities from test data
        activity1 = Activity.from_api_response(run_activity_data)
        activity2 = Activity.from_api_response(bike_activity_data)
        
        # Pre-download all file types for both activities
        preexisting_files: list[tuple[str, FileType]] = [
            # Activity 1 files
            (f"activity_json/2024-01-15-08-30-00_activity_{activity1.id}_running_Morning_Run_in_Central_Park.json", FileType.ACTIVITY_JSON),
            (f"gpx/2024-01-15-08-30-00_activity_{activity1.id}_running_Morning_Run_in_Central_Park.gpx", FileType.GPX),
            (f"tcx/2024-01-15-08-30-00_activity_{activity1.id}_running_Morning_Run_in_Central_Park.tcx", FileType.TCX),
            (f"kml/2024-01-15-08-30-00_activity_{activity1.id}_running_Morning_Run_in_Central_Park.kml", FileType.KML),
            (f"csv/2024-01-15-08-30-00_activity_{activity1.id}_running_Morning_Run_in_Central_Park.csv", FileType.CSV),
            # Activity 2 files  
            (f"activity_json/2024-03-10-09-45-15_activity_{activity2.id}_cycling_Bike_Ride.json", FileType.ACTIVITY_JSON),
            (f"gpx/2024-03-10-09-45-15_activity_{activity2.id}_cycling_Bike_Ride.gpx", FileType.GPX),
            (f"tcx/2024-03-10-09-45-15_activity_{activity2.id}_cycling_Bike_Ride.tcx", FileType.TCX),
            (f"kml/2024-03-10-09-45-15_activity_{activity2.id}_cycling_Bike_Ride.kml", FileType.KML),
            (f"csv/2024-03-10-09-45-15_activity_{activity2.id}_cycling_Bike_Ride.csv", FileType.CSV),
        ]
        
        for file_path_str, file_type in preexisting_files:
            file_path = download_directory / file_path_str
            file_manager.add_preexisting_file(file_path)
        
        # Both activities should initially return None for all file types (already downloaded)
        for file_type in FileType:
            result1 = file_manager.record_and_retrieve_download_path(test_logger, activity1, file_type)
            result2 = file_manager.record_and_retrieve_download_path(test_logger, activity2, file_type)
            assert result1 is None, f"Activity 1 should return None for {file_type.value} (already downloaded)"
            assert result2 is None, f"Activity 2 should return None for {file_type.value} (already downloaded)"
        
        # Mark activity 2 as redownloadable
        file_manager.mark_activity_as_redownloadable(activity2, test_logger)
        
        # Activity 1 should still return None (unaffected)
        for file_type in FileType:
            result1 = file_manager.record_and_retrieve_download_path(test_logger, activity1, file_type)
            assert result1 is None, f"Activity 1 should still return None for {file_type.value} after activity 2 marked redownloadable"
        
        # Activity 2 should now return valid paths (marked as redownloadable)
        for file_type in FileType:
            result2 = file_manager.record_and_retrieve_download_path(test_logger, activity2, file_type)
            assert result2 is not None, f"Activity 2 should return path for {file_type.value} after being marked redownloadable"
            assert isinstance(result2, Path), f"Should return Path object for {file_type.value}"
            assert str(activity2.id) in str(result2), f"Path should contain activity ID for {file_type.value}"
            assert file_type.value in str(result2), f"Path should contain file type for {file_type.value}"

    def test_mark_activity_as_redownloadable_deletes_files(
        self,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that mark_activity_as_redownloadable deletes physical files."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        # Setup activity with multiple file types
        json_path = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        gpx_path = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.GPX)
        
        assert json_path is not None
        assert gpx_path is not None
        
        # Create the files
        json_path.parent.mkdir(parents=True, exist_ok=True)
        gpx_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(json_path, 'wb') as f:
            f.write(activity.dump())
        with open(gpx_path, 'w') as f:
            f.write("dummy gpx content")
        
        # Verify files exist
        assert json_path.exists()
        assert gpx_path.exists()
        
        # Mark as redownloadable
        file_manager.mark_activity_as_redownloadable(activity, test_logger)
        
        # Files should be deleted and activity marked for redownload
        assert not json_path.exists()
        assert not gpx_path.exists()
        assert len(file_manager.downloaded_activities[activity.id].download_file_types) == 0

    def test_check_for_activity_changes_activity_not_tracked(
        self,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that untracked activities are ignored by change detection."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        # Activity is not tracked in file manager
        file_manager.check_for_activity_changes(activity, test_logger)
        
        # Should not be added to downloaded_activities
        assert activity.id not in file_manager.downloaded_activities

    def test_check_for_activity_changes_json_not_downloaded(
        self,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that activities without JSON files are ignored by change detection."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        # Setup activity with only GPX file (no JSON)
        gpx_path = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.GPX)
        assert gpx_path is not None
        
        # Create the GPX file
        gpx_path.parent.mkdir(parents=True, exist_ok=True)
        with open(gpx_path, 'w') as f:
            f.write("dummy gpx content")
        
        initial_file_types = file_manager.downloaded_activities[activity.id].download_file_types.copy()
        
        file_manager.check_for_activity_changes(activity, test_logger)
        
        # File types should be unchanged
        assert file_manager.downloaded_activities[activity.id].download_file_types == initial_file_types

    def test_check_for_activity_changes_unchanged_activity(
        self,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that unchanged activities are not marked for redownload."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        # Setup activity with JSON file
        json_path = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        assert json_path is not None
        
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, 'wb') as f:
            f.write(activity.dump())
        
        initial_file_types = file_manager.downloaded_activities[activity.id].download_file_types.copy()
        
        file_manager.check_for_activity_changes(activity, test_logger)
        
        # File types should be unchanged (not marked for redownload)
        assert file_manager.downloaded_activities[activity.id].download_file_types == initial_file_types

    def test_check_for_activity_changes_data_changed(
        self,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that activities with changed data are marked for redownload."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        # Setup activity with JSON file containing original data
        json_path = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        assert json_path is not None
        
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, 'wb') as f:
            f.write(activity.dump())
        
        # Verify file exists before change detection
        assert json_path.exists()
        
        # Modify the activity object to simulate changed data from API
        activity.raw["averageHR"] = 999  # Modify a field that doesn't affect filename
        
        file_manager.check_for_activity_changes(activity, test_logger)
        
        # Should be marked as redownloadable (empty file types)
        assert len(file_manager.downloaded_activities[activity.id].download_file_types) == 0
        # File should be deleted from filesystem
        assert not json_path.exists()

    def test_check_for_activity_changes_file_content_modified(
        self,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that externally modified files trigger redownload."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        # Setup activity with JSON file
        json_path = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        assert json_path is not None
        
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, 'wb') as f:
            f.write(activity.dump())
        
        # Modify the file content externally
        import json
        with open(json_path, 'r') as f:
            data = json.load(f)
        data["activityName"] = "Externally Modified Activity Name"
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Verify file exists before change detection
        assert json_path.exists()
        
        file_manager.check_for_activity_changes(activity, test_logger)
        
        # Should be marked as redownloadable (empty file types)
        assert len(file_manager.downloaded_activities[activity.id].download_file_types) == 0
        # File should be deleted from filesystem
        assert not json_path.exists()

    def test_check_for_activity_changes_file_missing(
        self,
        default_config: FileManagerConfig,
        download_directory: Path,
        test_logger: ContextualLoggerAdapter,
        run_activity_data: Dict[str, Any]
    ) -> None:
        """Test that missing files trigger redownload."""
        file_manager = FileManager(default_config, download_directory)
        activity = Activity.from_api_response(run_activity_data)
        
        # Setup activity as if JSON was downloaded, but don't create the file
        json_path = file_manager.record_and_retrieve_download_path(test_logger, activity, FileType.ACTIVITY_JSON)
        assert json_path is not None
        # Note: We intentionally don't create the file to simulate it being missing
        
        # Verify file doesn't exist before change detection
        assert not json_path.exists()
        
        file_manager.check_for_activity_changes(activity, test_logger)
        
        # Should be marked as redownloadable (empty file types)
        assert len(file_manager.downloaded_activities[activity.id].download_file_types) == 0
        # File should still not exist (was already missing)
        assert not json_path.exists()

    def test_should_ignore_file_system_files(
        self,
        default_config: FileManagerConfig,
        download_directory: Path
    ) -> None:
        """Test that system files are properly ignored."""
        file_manager = FileManager(default_config, download_directory)
        
        # Test macOS system files
        assert file_manager.should_ignore_file(Path('/some/path/.DS_Store')) is True
        assert file_manager.should_ignore_file(Path('/some/path/subdir/.DS_Store')) is True
        
        # Test Windows system files
        assert file_manager.should_ignore_file(Path('/some/path/Thumbs.db')) is True
        
        # Test Git files
        assert file_manager.should_ignore_file(Path('/some/path/.gitkeep')) is True
        assert file_manager.should_ignore_file(Path('/some/path/.gitignore')) is True

    def test_should_ignore_file_temporary_files(
        self,
        default_config: FileManagerConfig,
        download_directory: Path
    ) -> None:
        """Test that temporary files are properly ignored."""
        file_manager = FileManager(default_config, download_directory)
        
        # Test temporary file extensions
        assert file_manager.should_ignore_file(Path('/some/path/file.tmp')) is True
        assert file_manager.should_ignore_file(Path('/some/path/file.temp')) is True
        assert file_manager.should_ignore_file(Path('/some/path/file.swp')) is True
        assert file_manager.should_ignore_file(Path('/some/path/file.bak')) is True
        
        # Test case insensitive extensions
        assert file_manager.should_ignore_file(Path('/some/path/file.TMP')) is True
        assert file_manager.should_ignore_file(Path('/some/path/file.TEMP')) is True

    def test_should_ignore_file_valid_files(
        self,
        default_config: FileManagerConfig,
        download_directory: Path
    ) -> None:
        """Test that valid activity files are not ignored."""
        file_manager = FileManager(default_config, download_directory)
        
        # Test valid activity files
        assert file_manager.should_ignore_file(Path('/path/activity.json')) is False
        assert file_manager.should_ignore_file(Path('/path/activity.gpx')) is False
        assert file_manager.should_ignore_file(Path('/path/activity.tcx')) is False
        assert file_manager.should_ignore_file(Path('/path/activity.kml')) is False
        assert file_manager.should_ignore_file(Path('/path/activity.csv')) is False
        
        # Test files with similar but valid names
        assert file_manager.should_ignore_file(Path('/path/DS_Store_activity.json')) is False
        assert file_manager.should_ignore_file(Path('/path/temp_activity.gpx')) is False

    def test_add_preexisting_file_ignores_system_files(
        self,
        default_config: FileManagerConfig,
        download_directory: Path
    ) -> None:
        """Test that add_preexisting_file silently ignores system files."""
        file_manager = FileManager(default_config, download_directory)
        
        # Create test file structure
        (download_directory / 'activity_json').mkdir(parents=True, exist_ok=True)
        
        # Valid file
        valid_file = download_directory / 'activity_json' / '2024-01-15-08-30-00_activity_12345678901_running_Test.json'
        valid_file.write_text('{"test": "data"}')
        
        # System file that should be ignored
        ignored_file = download_directory / '.DS_Store'
        ignored_file.write_text('system file')
        
        # Add both files
        file_manager.add_preexisting_file(valid_file)
        file_manager.add_preexisting_file(ignored_file)  # Should be silently ignored
        
        # Only the valid file should be tracked
        assert len(file_manager.downloaded_activities) == 1
        assert 12345678901 in file_manager.downloaded_activities
        assert FileType.ACTIVITY_JSON in file_manager.downloaded_activities[12345678901].download_file_types

    def test_add_preexisting_file_ignores_temporary_files(
        self,
        default_config: FileManagerConfig,
        download_directory: Path
    ) -> None:
        """Test that add_preexisting_file silently ignores temporary files."""
        file_manager = FileManager(default_config, download_directory)
        
        # Create test file structure
        (download_directory / 'gpx').mkdir(parents=True, exist_ok=True)
        
        # Valid file
        valid_file = download_directory / 'gpx' / '2024-01-15-08-30-00_activity_12345678901_running_Test.gpx'
        valid_file.write_text('<gpx>test</gpx>')
        
        # Temporary file that should be ignored
        ignored_file = download_directory / 'gpx' / 'temp_file.tmp'
        ignored_file.write_text('temporary file')
        
        # Add both files
        file_manager.add_preexisting_file(valid_file)
        file_manager.add_preexisting_file(ignored_file)  # Should be silently ignored
        
        # Only the valid file should be tracked
        assert len(file_manager.downloaded_activities) == 1
        assert 12345678901 in file_manager.downloaded_activities
        assert FileType.GPX in file_manager.downloaded_activities[12345678901].download_file_types 