#!/usr/bin/env python3
"""
Garmin Connect GPX Exporter

A script to automatically download all GPX files from Garmin Connect.
Runs as a background service with configurable cron scheduling.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import signal
import random
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.job import Job
from garminconnect import (
    Garmin,
    GarminConnectTooManyRequestsError,
)

from source.config import Config
from source.activity import Activity, ActivityId
from source.file_manager.all import FileManager
from source.file_type import FileType
from source.contextual_logger import ContextualLoggerAdapter, setup_contextual_logger
from source.auth import GarminAuthenticator

class Exporter:
    """Main class for exporting GPX files from Garmin Connect."""

    config: Config
    logger: ContextualLoggerAdapter
    authenticator: GarminAuthenticator
    file_manager: FileManager
    cron_iteration: int
    oldest_downloaded_activity_id: Optional[ActivityId]
    trigger: Optional[CronTrigger]
    
    def __init__(self, config: Config) -> None:
        self.config = config
        self.logger = setup_contextual_logger(__name__, self.config.log_level)
        self.authenticator = GarminAuthenticator(self.config)
        self.file_manager = FileManager(self.config.file_manager_config, self.config.download_directory)
        self.cron_iteration = 0
        self.oldest_downloaded_activity_id = None
        self.trigger = None

        self._ensure_download_directory_exists()
        self._precompute_downloaded_activities()

    def _log_next_scheduled_run(self) -> None:
        """Log the next scheduled run time in both local and UTC timezones."""
        if self.trigger:
            next_fire_time: Optional[datetime] = self.trigger.get_next_fire_time(None, datetime.now().astimezone())
            if next_fire_time:
                next_fire_time_utc: datetime = next_fire_time.astimezone(timezone.utc)
                self.logger.info(f"Next scheduled run: {next_fire_time} (local) / {next_fire_time_utc} (UTC)")
            else:
                self.logger.info("Next scheduled run: Not scheduled")
        else:
            self.logger.debug("No trigger configured for next run logging")

    def _ensure_download_directory_exists(self) -> None:
        if not self.config.download_directory.exists():
            raise FileNotFoundError(f"Download directory does not exist: {self.config.download_directory}")
        
        for file_type in FileType:
            dir_path: Path = self.config.download_directory / file_type.value
            dir_path.mkdir(parents=True, exist_ok=True)

    def _precompute_downloaded_activities(self) -> None:
        for file_path in self.config.download_directory.glob('*/*'):
            if file_path.is_file():
                self.file_manager.add_preexisting_file(file_path)
                
        self.logger.info(f"Processed all preexisting files: {self.file_manager}")

    def _sleep_for_request_delay(self) -> None:
        if self.config.request_delay_seconds == 0:
            return
            
        # Add ±25% jitter to the base delay
        jitter_factor: float = random.uniform(0.75, 1.25)
        actual_delay: float = self.config.request_delay_seconds * jitter_factor
        
        self.logger.debug(f"Waiting {actual_delay:.2f} seconds (base: {self.config.request_delay_seconds}s) before next Garmin API call...")
        time.sleep(actual_delay)

    def _write_activity_json(self, activity: Activity, path: Path, logger: ContextualLoggerAdapter) -> None:
        with open(path, 'wb') as f:
            f.write(activity.dump())
        logger.info(f"Saved activity JSON file: {path}")

    def _write_gps_file(self, activity: Activity, path: Path, file_type: FileType, logger: ContextualLoggerAdapter, api: Garmin) -> None:
        gps_data: bytes = api.download_activity(
            activity.id,
            dl_fmt=file_type.garmin_download_format
        )
        if not gps_data:
            logger.warning(f"No {file_type.value} data returned for activity, even though it has polyline data, skipping")
            return
        
        with open(path, 'wb') as f:
            f.write(gps_data)
        logger.info(f"Saved {file_type.value} file: {path}")

    def _maybe_download_activity(self, activity: Activity, logger: ContextualLoggerAdapter, api: Garmin) -> Tuple[int, int]:
        downloaded_count = 0
        skipped_count = 0

        # Activity JSON first
        activity_json_path: Optional[Path] = self.file_manager.record_and_retrieve_download_path(logger, activity, FileType.ACTIVITY_JSON)
        if activity_json_path:
            self._write_activity_json(activity, activity_json_path, logger)
            downloaded_count += 1
            self._sleep_for_request_delay()
        else:
            skipped_count += 1

        # GPS data next
        for file_type in FileType.gps_file_types():
            gps_path: Optional[Path] = self.file_manager.record_and_retrieve_download_path(logger, activity, file_type)
            if gps_path:
                self._write_gps_file(activity, gps_path, file_type, logger, api)
                downloaded_count += 1
                self._sleep_for_request_delay()
            else:
                skipped_count += 1

        return downloaded_count, skipped_count

    def _get_activities_batch(self, start: int, limit: int, api: Garmin) -> List[Activity]:
        """Get a batch of activities from Garmin Connect."""
        activities: Any = api.get_activities(start, limit)
        return [Activity.from_api_response(activity) for activity in activities]

    def download_all_activities_iteration(self) -> None:
        """Download GPX files for all activities matching criteria."""
        iteration_logger: ContextualLoggerAdapter = self.logger.with_context(cron_iteration=self.cron_iteration)
        self.cron_iteration += 1

        iteration_logger.info("Starting GPX download process...")
        iteration_logger.debug(f"Already downloaded activities: {self.file_manager}")
        
        downloaded_count = 0
        skipped_count = 0
        start = 0
        current_run_oldest_downloaded_activity_id: Optional[ActivityId] = None
        
        while True:
            batch_logger: ContextualLoggerAdapter = iteration_logger.with_context(
                batch_start=start,
                batch_size=self.config.batch_size
            )
            api : Garmin = self.authenticator.ensure_authenticated(batch_logger)
            
            batch_logger.debug("Fetching activities batch")
            activities: List[Activity] = self._get_activities_batch(start, self.config.batch_size, api)
            
            if not activities:
                iteration_logger.info("No more activities found")
                break
                
            batch_logger.info(f"Processing {len(activities)} activities in batch")
            
            reached_boundary = False
            for activity in activities:
                if not current_run_oldest_downloaded_activity_id:
                    current_run_oldest_downloaded_activity_id = activity.id

                if self.oldest_downloaded_activity_id and activity.id == self.oldest_downloaded_activity_id:
                    reached_boundary = True
                    batch_logger.info(f"Reached previously processed boundary activity {self.oldest_downloaded_activity_id}")
                    
                activity_logger: ContextualLoggerAdapter = activity.add_logger_context(batch_logger)
                if self.config.check_for_activity_changes:
                    self.file_manager.check_for_activity_changes(activity, activity_logger)
                d, s = self._maybe_download_activity(activity, activity_logger, api)
                downloaded_count += d
                skipped_count += s
                
                if d > 0:
                    current_run_oldest_downloaded_activity_id = activity.id
                    reached_boundary = False
            
            if reached_boundary:
                if self.config.always_recheck_all_activities:
                    batch_logger.info("ALWAYS_RECHECK_ALL_ACTIVITIES is enabled, continuing to process all activities despite boundary")
                else:
                    batch_logger.info("Stopping early due to boundary (set ALWAYS_RECHECK_ALL_ACTIVITIES=true to disable this behavior)")
                    break
                
            start += self.config.batch_size
            batch_logger.debug(f"Waiting 1 second before next batch...")
            time.sleep(1)
                
        if current_run_oldest_downloaded_activity_id:
            batch_logger.info(f"Marking oldest downloaded activity for next run: {current_run_oldest_downloaded_activity_id}")
            self.oldest_downloaded_activity_id = current_run_oldest_downloaded_activity_id
        
        self.logger.info(f"Download complete. Downloaded files: {downloaded_count}, "
                        f"Skipped files: {skipped_count}")
        self.logger.debug(f"All downloaded activities: {self.file_manager}")
        
        # Show next scheduled run time
        self._log_next_scheduled_run()

    def _download_all_activities(self) -> None:
        try:
            self.download_all_activities_iteration()
        except GarminConnectTooManyRequestsError as e:
            self.logger.warning(f"Rate limited by Garmin: {e}. Next run will retry, no action is needed.")
        except Exception as e:
            self.logger.error(f"Unexpected error during download: {e}", exc_info=True)
            sys.exit(1)

    def run_scheduled(self) -> None:
        """Run the download process using APScheduler with callback-based scheduling."""
        cron_schedule: str = self.config.cron_schedule
        run_immediately: bool = self.config.run_immediately_on_startup
        if run_immediately:
            self.logger.info("Running initial download on startup...")
            self._download_all_activities()
        
        self.logger.info(f"Starting APScheduler-based GPX exporter with cron: {cron_schedule}")
        
        executors: Dict[str, ThreadPoolExecutor] = {
            'default': ThreadPoolExecutor(max_workers=1)  # Single worker to avoid conflicts
        }
        
        local_timezone = datetime.now().astimezone().tzinfo
        scheduler = BlockingScheduler(executors=executors, timezone=local_timezone)
        
        # Parse cron expression (e.g., "0 */8 * * *" -> minute=0, hour="*/8")
        cron_parts: List[str] = cron_schedule.split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid cron schedule: {cron_schedule}")
        
        minute, hour, day, month, day_of_week = cron_parts
        
        self.trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
        scheduler.add_job(
            func=self._download_all_activities,
            trigger=self.trigger,
            id='download_all_activities',
            name='Garmin Connect Activity Exporter Job',
            max_instances=1,  # Prevent overlapping executions
            coalesce=True     # If multiple triggers fire while job is running, only execute once
        )
        
        def signal_handler(signum: int, frame: Any) -> None:
            signal_name = signal.Signals(signum).name
            self.logger.info(f"Received {signal_name} signal, stopping scheduler...")
            scheduler.shutdown(wait=True)
            self.logger.info("Scheduler stopped gracefully")
            sys.exit(0)
        
        # Handle termination signals for graceful shutdown
        signal.signal(signal.SIGTERM, signal_handler)  # K8s/Docker graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGHUP, signal_handler)   # Terminal disconnection
        
        scheduler.print_jobs()
        self._log_next_scheduled_run()
        
        # Start the scheduler (this blocks until shutdown)
        try:
            self.logger.info("Starting scheduler...")
            scheduler.start()
        except (SystemExit, KeyboardInterrupt):
            # SystemExit is raised by signal handlers, KeyboardInterrupt shouldn't occur 
            # due to signal handling but kept as failsafe
            pass
        except Exception as e:
            self.logger.error(f"Scheduler failed with unexpected error: {e}")
            raise
        finally:
            self.logger.info("Ensuring scheduler is shut down...")
            if scheduler.running:
                scheduler.shutdown(wait=False)
