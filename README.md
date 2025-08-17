# Garmin Connect Activity Exporter

Automatically download your Garmin Connect activities as JSON files, along with associated GPS tracks (GPX, TCX, KML) and workout data (CSV).

- [What You Get](#what-you-get)
- [Quick Start](#quick-start)
  - [1. Set Your Credentials](#1-set-your-credentials)
  - [2. Create Directories](#2-create-directories)
  - [3. Run the Exporter](#3-run-the-exporter)
- [Running Long-Term](#running-long-term)
- [How It Works](#how-it-works)
  - [When Downloads Happen](#when-downloads-happen)
  - [Download Speed \& Safety](#download-speed--safety)
  - [What Gets Downloaded](#what-gets-downloaded)
  - [File Naming](#file-naming)
  - [Filtering Activities](#filtering-activities)
  - [Automatic Re-downloads](#automatic-re-downloads)
  - [Smart Activity Processing](#smart-activity-processing)
- [Configuration](#configuration)
  - [Required Settings](#required-settings)
  - [Optional Settings](#optional-settings)

## What You Get

The exporter downloads your activities and organizes them into folders:

```txt
garmin_downloads/
├── activity_json/          ← Activity details (JSON, every activity)
│   ├── 2024-03-15-14-32-10_activity_1001_running_Downtown_Running.json
│   ├── 2024-03-16-09-45-23_activity_1002_hiking_Mountain_View_Hiking.json
│   ├── 2024-03-18-08-15-42_activity_1004_strength_training_Gym_Workout.json
│   └── ...
├── gpx/                     ← GPS tracks (XML, outdoor activities only)
│   ├── 2024-03-15-14-32-10_activity_1001_running_Downtown_Running.gpx
│   ├── 2024-03-16-09-45-23_activity_1002_hiking_Mountain_View_Hiking.gpx
│   └── ...
├── tcx/                     ← GPS tracks with heart rate (XML, outdoor activities only)
│   ├── 2024-03-15-14-32-10_activity_1001_running_Downtown_Running.tcx
│   ├── 2024-03-16-09-45-23_activity_1002_hiking_Mountain_View_Hiking.tcx
│   └── ...
├── kml/                     ← GPS tracks (XML, all activities)
│   ├── 2024-03-15-14-32-10_activity_1001_running_Downtown_Running.kml
│   ├── 2024-03-16-09-45-23_activity_1002_hiking_Mountain_View_Hiking.kml
│   ├── 2024-03-18-08-15-42_activity_1004_strength_training_Gym_Workout.kml
│   └── ...
└── csv/                     ← Workout data (CSV, all activities)
    ├── 2024-03-15-14-32-10_activity_1001_running_Downtown_Running.csv
    ├── 2024-03-16-09-45-23_activity_1002_hiking_Mountain_View_Hiking.csv
    ├── 2024-03-18-08-15-42_activity_1004_strength_training_Gym_Workout.csv
    └── ...
```

**Note:** Indoor activities (gym workouts, treadmill runs) don't have GPS coordinates, so they get minimal KML files and only activity JSON, KML, and CSV files are created for them (no GPX/TCX).

See [testdata/](./testdata/) for example file contents.

## Quick Start

### 1. Set Your Credentials

```bash
export GARMIN_USERNAME=<your-garmin-email>
export GARMIN_PASSWORD=<your-garmin-password>
```

🔒 **NOTE:** Two-factor authentication (MFA) is not supported yet.
Please file a Github issue if you require MFA.

### 2. Create Directories

```bash
mkdir -p garmin_downloads garmin_session
```

### 3. Run the Exporter

```bash
docker run \
  --name garmin-connect-activity-exporter \
  --restart unless-stopped \
  -e GARMIN_USERNAME="${GARMIN_USERNAME}" \
  -e GARMIN_PASSWORD="${GARMIN_PASSWORD}" \
  -v $(pwd)/garmin_downloads:/app/garmin_downloads \
  -v $(pwd)/garmin_session:/app/garmin_session \
  ghcr.io/nareddyt/garmin-connect-activity-exporter:v1
```

The exporter starts downloading immediately and continues running in the background to fetch new activities automatically.

🔒 **Security Note:** Your login session is saved to `garmin_session/`. Don't share this folder or upload it to GitHub - anyone with access can login to your Garmin account.

## Running Long-Term

The basic Docker command stops when your computer restarts. For continuous operation:

**Docker Compose** (recommended):

Create a `.env` file under the `examples/` directory with the following content:

```bash
GARMIN_USERNAME='your-username'
GARMIN_PASSWORD='your-password'
TZ='https://en.wikipedia.org/wiki/List_of_tz_database_time_zones'
```

Then run:

```bash
docker compose --file examples/docker-compose.yaml up -d
```

**Kubernetes** (for clusters):

A sample kubernetes deployment manifest is provided in `examples/kubernets.yaml`.

## How It Works

This section explains how the exporter behaves by default and what to expect when running it.

### When Downloads Happen

**On Startup:** The exporter immediately starts downloading your activities from Garmin Connect.
You can disable this with `RUN_IMMEDIATELY_ON_STARTUP=false`.

**Ongoing:** The exporter runs on a schedule to check for new activities.
By default, it checks every 12 hours. Change this with `CRON_SCHEDULE`.

### Download Speed & Safety

**The exporter is intentionally slow.** If you have many activities, expect the first download to take hours.

The exporter includes built-in delays between API requests to prevent your Garmin account from being flagged or banned:

- 30-second delays between requests (`REQUEST_DELAY_SECONDS`)  
- Downloads 30 activities per batch (`BATCH_SIZE`)

⚠️ **WARNING:** Making the exporter faster increases the risk of account suspension.
**DO NOT** reduce delays or increase batch sizes unless you understand the risks, especially if you have hundreds of activities.

### What Gets Downloaded

For every activity, the exporter downloads:

- **Activity data** (timestamps, stats, etc.) → `garmin_downloads/activity_json/`
- **Workout data** (splits, summary) → `garmin_downloads/csv/`
- **GPS tracks** (KML format) → `garmin_downloads/kml/`
- **GPS tracks** (GPX/TCX formats, outdoor activities only) → `garmin_downloads/gpx/` and `garmin_downloads/tcx/`

Indoor activities get JSON, CSV, and minimal KML files. Outdoor activities get all file types.

### File Naming

Files are saved with descriptive names so you can easily identify them:

```text
{DATE-TIME}_activity_{ACTIVITY-ID}_{ACTIVITY-TYPE}_{ACTIVITY-NAME}.{FILE-TYPE}
```

For example: `2024-03-15-14-32-10_activity_1001_running_Downtown_Running.gpx`

- `{DATE-TIME}`: When the activity started (YYYY-MM-DD-HH-MM-SS)
- `{ACTIVITY-ID}`: Unique ID from Garmin Connect  
- `{ACTIVITY-TYPE}`: Type of activity (running, cycling, etc.)
- `{ACTIVITY-NAME}`: Activity name (cleaned up for file systems)
- `{FILE-TYPE}`: File format (`json`, `csv`, `kml`, `gpx`, or `tcx`)

### Filtering Activities

You can configure this exporter to:

- Only download activities after a certain date via `START_DATE`.
- Only download activities before a certain date via `END_DATE`.
- Not download activities of specific types via `EXCLUDED_ACTIVITY_TYPES`.
- Not download specific activities via `EXCLUDED_ACTIVITY_IDS`.
- Not download GPX or TCX file types via `EXCLUDED_FILE_TYPES`.
- Skip downloading very new activities via `MIN_ACTIVITY_AGE` (giving you time to edit/trim the activities in Garmin Connect before they are downloaded).

### Automatic Re-downloads

**Missing Files:** If you delete any downloaded files, the exporter will re-download them on the next run.

**Changed Activities:** If an activity is modified (either in Garmin Connect or you edit the downloaded files), the exporter will detect this and re-download all files for that activity.
Disable this with `CHECK_FOR_ACTIVITY_CHANGES=false`.

### Smart Activity Processing

The exporter is designed to be efficient and avoid unnecessary work:

**First Run:** Downloads all your activities from Garmin Connect.

**Subsequent Runs:** Only checks for new activities since the last run, ignoring older activities that have already been processed.

This means after the initial download, the exporter runs much faster because it doesn't re-examine your entire activity history every time.
More importantly, this reduces the amount of calls to the Garmin API, further helping prevent bot detection and rate limiting.

To force the exporter to re-examine all activities, restart the container. After restart, if activities were previously downloaded, [activity change detection](#automatic-re-downloads) also runs.

Disable this optimization and always check all activities via configuration option `ALWAYS_RECHECK_ALL_ACTIVITIES`.

## Configuration

Customize the exporter's behavior with environment variables.

### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `GARMIN_USERNAME` | Your Garmin Connect username | `john.doe@example.com` |
| `GARMIN_PASSWORD` | Your Garmin Connect password | `your_password` |

### Optional Settings

**Scheduling:**

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `CRON_SCHEDULE` | How often to check for new activities ([help](https://crontab.guru/)) | `0 */12 * * *` (every 12 hours) | `0 */8 * * *` |
| `TZ` | Timezone for cron scheduling ([list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)) | `UTC` | `America/Chicago` |
| `RUN_IMMEDIATELY_ON_STARTUP` | Start downloading on container start | `true` | `false` |

**Performance & Safety:**

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `REQUEST_DELAY_SECONDS` | Delay between API requests (⚠️ see warnings above) | `10` | `2` |
| `BATCH_SIZE` | Activities to fetch per API call (⚠️ see warnings above) | `30` | `50` |
| `LOG_LEVEL` | Logging detail level | `INFO` | `DEBUG` |

**Activity Processing:**

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `CHECK_FOR_ACTIVITY_CHANGES` | Re-download modified activities | `true` | `false` |
| `ALWAYS_RECHECK_ALL_ACTIVITIES` | Check all activities every run (slow) | `false` | `true` |

**Filtering:**

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `START_DATE` | Only download activities after this date | `None` | `2023-01-01` |
| `END_DATE` | Only download activities before this date | `None` | `2024-12-31` |
| `EXCLUDED_ACTIVITY_TYPES` | Skip these activity types | `None` | `indoor_cycling,treadmill_running` |
| `EXCLUDED_ACTIVITY_IDS` | Skip these specific activities | `None` | `12345,67890` |
| `EXCLUDED_FILE_TYPES` | Skip these file types (activity_json cannot be excluded) | `None` | `tcx,gpx` |
| `MIN_ACTIVITY_AGE` | Only download activities older than this duration (relative to now). Supports `s`, `m`, `h`, `d`. | `None` | `50m`, `6h`, `2d` |
