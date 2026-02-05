#!/usr/bin/env python3
"""
Zoom API Client - Shared utility for Zoom API operations.

Provides:
- Server-to-Server OAuth authentication
- Meeting recording search
- Participant matching
- Coach email mapping

Usage:
    from utilities.zoom_client import ZoomClient

    client = ZoomClient()
    client.authenticate()
    meetings = client.get_recordings_for_date('2025-01-15')
"""

import boto3
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict


class ZoomClient:
    """Zoom API client with Server-to-Server OAuth authentication."""

    DEFAULT_REGION = 'eu-west-2'
    SSM_PREFIX = '/zoom/s2s'

    def __init__(self, region: str = None):
        """Initialize Zoom client with SSM credentials."""
        self.region = region or self.DEFAULT_REGION
        ssm = boto3.client('ssm', region_name=self.region)

        self.account_id = self._get_ssm_param(ssm, f'{self.SSM_PREFIX}/account_id')
        self.client_id = self._get_ssm_param(ssm, f'{self.SSM_PREFIX}/client_id')
        self.client_secret = self._get_ssm_param(ssm, f'{self.SSM_PREFIX}/client_secret')

        self.access_token = None
        self.base_url = 'https://api.zoom.us/v2'

        # Caches
        self._recordings_cache: Dict[str, List[Dict]] = {}
        self._coach_emails: Dict[str, str] = {}
        self._meeting_cache: Dict[str, Any] = {}

    def _get_ssm_param(self, ssm, name: str) -> str:
        """Get parameter from SSM Parameter Store."""
        response = ssm.get_parameter(Name=name, WithDecryption=True)
        return response['Parameter']['Value'].strip()

    def authenticate(self) -> bool:
        """Get OAuth access token using Server-to-Server credentials."""
        response = requests.post(
            'https://zoom.us/oauth/token',
            params={'grant_type': 'account_credentials', 'account_id': self.account_id},
            auth=(self.client_id, self.client_secret)
        )
        if response.status_code == 200:
            self.access_token = response.json()['access_token']
            return True
        return False

    def _ensure_authenticated(self):
        """Ensure we have a valid access token."""
        if not self.access_token:
            if not self.authenticate():
                raise RuntimeError("Failed to authenticate with Zoom API")

    def _headers(self) -> Dict[str, str]:
        """Get authorization headers."""
        return {'Authorization': f'Bearer {self.access_token}'}

    def load_coach_emails(self) -> Dict[str, str]:
        """
        Load all Zoom users and create name->email mapping.
        Returns dict mapping lowercase names to email addresses.
        """
        self._ensure_authenticated()

        if self._coach_emails:
            return self._coach_emails

        response = requests.get(
            f'{self.base_url}/users',
            headers=self._headers(),
            params={'status': 'active', 'page_size': 300}
        )

        if response.status_code == 200:
            for user in response.json().get('users', []):
                first = user.get('first_name', '')
                last = user.get('last_name', '')
                display = user.get('display_name', '')
                email = user.get('email', '').lower()

                # Map multiple name formats to email
                full_name = f"{first} {last}".strip().lower()
                if full_name:
                    self._coach_emails[full_name] = email
                if display:
                    self._coach_emails[display.lower()] = email

        return self._coach_emails

    def get_coach_email(self, coach_name: str) -> Optional[str]:
        """Get coach email by name (case-insensitive)."""
        if not self._coach_emails:
            self.load_coach_emails()
        return self._coach_emails.get(coach_name.lower())

    def get_recordings_for_date(self, date_str: str) -> List[Dict]:
        """
        Get all recordings for a specific date.
        date_str should be in YYYY-MM-DD format.
        Results are cached.
        """
        self._ensure_authenticated()

        if date_str in self._recordings_cache:
            return self._recordings_cache[date_str]

        try:
            response = requests.get(
                f'{self.base_url}/accounts/me/recordings',
                headers=self._headers(),
                params={'from': date_str, 'to': date_str, 'page_size': 300}
            )
            if response.status_code == 200:
                recordings = response.json().get('meetings', [])
                self._recordings_cache[date_str] = recordings
                return recordings
        except Exception as e:
            print(f"Error fetching recordings for {date_str}: {e}")

        self._recordings_cache[date_str] = []
        return []

    def get_recordings_for_range(self, from_date: str, to_date: str) -> List[Dict]:
        """Get all recordings for a date range."""
        self._ensure_authenticated()

        all_recordings = []
        try:
            response = requests.get(
                f'{self.base_url}/accounts/me/recordings',
                headers=self._headers(),
                params={'from': from_date, 'to': to_date, 'page_size': 300}
            )
            if response.status_code == 200:
                all_recordings = response.json().get('meetings', [])
        except Exception as e:
            print(f"Error fetching recordings: {e}")

        return all_recordings

    def find_meeting(
        self,
        client_identifier: str,
        call_datetime: str,
        coach_name: str = None,
        time_window_hours: float = 2.0
    ) -> tuple:
        """
        Find Zoom meeting matching client and time.

        Args:
            client_identifier: Client email or name to search for in meeting topic
            call_datetime: ISO format datetime string
            coach_name: Optional coach name to match by host
            time_window_hours: How close the meeting time should be (default 2 hours)

        Returns:
            tuple: (meeting_id, match_type) where match_type is one of:
                - 'adviser+client': Matched by coach host AND client in topic
                - 'adviser+time': Matched by coach host within time window
                - 'client_topic': Matched by client name in topic
                - 'adviser_not_found': Coach not found in Zoom users
                - 'no_recording': No matching recording found
                - 'invalid_date': Could not parse call_datetime
        """
        self._ensure_authenticated()
        self.load_coach_emails()

        # Parse datetime
        try:
            dt = datetime.fromisoformat(call_datetime.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None, 'invalid_date'

        # Check cache
        cache_key = f"{client_identifier}_{dt.strftime('%Y-%m-%d')}_{coach_name or ''}"
        if cache_key in self._meeting_cache:
            return self._meeting_cache[cache_key]

        # Get coach email
        coach_email = None
        if coach_name:
            coach_email = self.get_coach_email(coach_name)

        # Extract searchable client name from email
        name_parts = client_identifier.split('@')[0].replace('.', ' ').replace('_', ' ')

        # Get recordings for the date
        date_str = dt.strftime('%Y-%m-%d')
        recordings = self.get_recordings_for_date(date_str)

        time_window_sec = time_window_hours * 3600

        # Strategy 1: Match by coach (host) + time window
        if coach_email:
            for meeting in recordings:
                host_email = meeting.get('host_email', '').lower()
                if host_email != coach_email:
                    continue

                try:
                    meeting_dt = datetime.fromisoformat(meeting['start_time'].replace('Z', '+00:00'))
                    time_diff = abs((meeting_dt - dt).total_seconds())
                    if time_diff <= time_window_sec:
                        meeting_id = str(meeting.get('id'))
                        topic = meeting.get('topic', '').lower()

                        # Check if client name also in topic (stronger match)
                        if name_parts.lower() in topic or client_identifier.lower() in topic:
                            result = (meeting_id, 'adviser+client')
                        else:
                            result = (meeting_id, 'adviser+time')

                        self._meeting_cache[cache_key] = result
                        return result
                except (ValueError, KeyError):
                    pass

        # Strategy 2: Match by client name in topic
        for meeting in recordings:
            topic = meeting.get('topic', '').lower()
            if client_identifier.lower() in topic or name_parts.lower() in topic:
                try:
                    meeting_dt = datetime.fromisoformat(meeting['start_time'].replace('Z', '+00:00'))
                    time_diff = abs((meeting_dt - dt).total_seconds())
                    if time_diff <= time_window_sec:
                        meeting_id = str(meeting.get('id'))
                        result = (meeting_id, 'client_topic')
                        self._meeting_cache[cache_key] = result
                        return result
                except (ValueError, KeyError):
                    pass

        # No match found
        if coach_name and not coach_email:
            result = (None, 'adviser_not_found')
        else:
            result = (None, 'no_recording')

        self._meeting_cache[cache_key] = result
        return result

    def search_by_email(
        self,
        email: str,
        from_date: str,
        to_date: str
    ) -> List[Dict]:
        """
        Search for meetings where a specific email participated.

        Args:
            email: Email address to search for
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of matching meetings with details
        """
        self._ensure_authenticated()

        recordings = self.get_recordings_for_range(from_date, to_date)
        email_lower = email.lower()
        name_parts = email.split('@')[0].replace('.', ' ').replace('_', ' ').lower()

        matches = []
        for meeting in recordings:
            topic = meeting.get('topic', '').lower()

            # Check if email or name appears in topic
            if email_lower in topic or name_parts in topic:
                matches.append({
                    'meeting_id': meeting.get('id'),
                    'topic': meeting.get('topic'),
                    'start_time': meeting.get('start_time'),
                    'duration': meeting.get('duration'),
                    'host_email': meeting.get('host_email'),
                    'total_size': meeting.get('total_size')
                })

        return matches

    def clear_cache(self):
        """Clear all caches."""
        self._recordings_cache.clear()
        self._meeting_cache.clear()
        # Don't clear coach_emails as that rarely changes


# Convenience function for simple usage
def create_zoom_client(region: str = None) -> ZoomClient:
    """Create and authenticate a ZoomClient."""
    client = ZoomClient(region=region)
    client.authenticate()
    return client
