from enum import Enum
from typing import Dict, List
from garminconnect import Garmin

class FileType(Enum):
    """Supported file types for activity downloads."""
    ACTIVITY_JSON = 'activity_json'
    GPX = 'gpx'
    TCX = 'tcx'
    KML = 'kml'
    CSV = 'csv'
    # NOT supported yet. Please file a Github issue if you require it.
    # FIT = 'fit'  # Downloaded as zip file, needs to be extracted
    
    @property
    def suffix(self) -> str:
        """Return the file suffix for this file type."""
        mapping: Dict[str, str] = {
            'activity_json': 'json',
            'gpx': 'gpx',
            'tcx': 'tcx',
            'kml': 'kml',
            'csv': 'csv',
            'fit': 'fit'
        }
        return mapping[self.value]
    
    @property
    def garmin_download_format(self) -> Garmin.ActivityDownloadFormat:
        mapping: Dict[str, Garmin.ActivityDownloadFormat] = {
            'gpx': Garmin.ActivityDownloadFormat.GPX,
            'tcx': Garmin.ActivityDownloadFormat.TCX,
            'kml': Garmin.ActivityDownloadFormat.KML,
            'csv': Garmin.ActivityDownloadFormat.CSV,
            'fit': Garmin.ActivityDownloadFormat.ORIGINAL
        }
        return mapping[self.value]
    
    @classmethod
    def gps_file_types(cls) -> List['FileType']:
        """Return all file types that contain GPS data."""
        return [file_type for file_type in cls if file_type != cls.ACTIVITY_JSON]