"""
Garmin Connect Authentication Helper

Handles authentication with Garmin Connect using session management.
"""

from datetime import datetime
from typing import Optional

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
)
from garth.exc import GarthHTTPError

from source.config import Config
from source.contextual_logger import ContextualLoggerAdapter


class GarminAuthenticator:
    """Helper class for managing Garmin Connect authentication."""
    
    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self._api: Optional[Garmin] = None
    
    @property
    def api(self) -> Optional[Garmin]:
        return self._api
    
    def ensure_authenticated(self, logger: ContextualLoggerAdapter) -> Garmin:
        """Ensure we have a valid authentication, re-authenticate if needed."""
        if self._api is None:
            logger.debug("Very first run, we need to authenticate")
            self._api = self._authenticate(logger)
            return self._api
        
        logger.debug("Potentially authenticated by last run. Dummy call to check if session is valid.")
        try:    
            self._api.get_user_summary(cdate=datetime.now().strftime("%Y-%m-%d"))
            return self._api
            
        except (GarthHTTPError, GarminConnectAuthenticationError):
            logger.warning("Session expired during operation, re-authenticating...")
            self._api = self._authenticate(logger)
            return self._api

    def _authenticate(self, logger: ContextualLoggerAdapter) -> Garmin:
        """Authenticate with Garmin Connect using Garth session management."""
        try:
            garmin = Garmin()
            garmin.login(tokenstore=str(self.config.session_directory))
            logger.info(f"Successfully authenticated with saved session tokens in directory: {self.config.session_directory}")
            return garmin
                    
        except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
            logger.info("Session file not found or invalid, logging in with credentials...")
            
        username = self.config.garmin_username
        password = self.config.garmin_password
        
        if not username or not password:
            raise ValueError("Garmin credentials are required for authentication")
            
        garmin = Garmin(username, password, return_on_mfa=True)
        result1, result2 = garmin.login()
        if result1 == "needs_mfa":
            raise ValueError("MFA is not supported, please raise an issue on Github.")
        
        # Save Oauth1 and Oauth2 token files to directory for next login
        garmin.garth.dump(str(self.config.session_directory))
        logger.info(f"Successfully authenticated with username/password and saved session tokens to directory: {self.config.session_directory}")
        return garmin
