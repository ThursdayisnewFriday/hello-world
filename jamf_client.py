#!/usr/bin/env python3
"""
Jamf Pro API Client for License Reclamation
This module provides functionality to interact with Jamf Pro API for license management.
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import base64
import urllib.parse

class JamfAPIClient:
    """Jamf Pro API Client for license management operations"""
    
    def __init__(self, server_url: str, username: str = None, password: str = None, api_token: str = None):
        """
        Initialize Jamf API client
        
        Args:
            server_url: Jamf Pro server URL
            username: API username (if using basic auth)
            password: API password (if using basic auth)
            api_token: API token (if using token auth)
        """
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.password = password
        self.api_token = api_token
        self.session = requests.Session()
        self.auth_token = None
        self.logger = logging.getLogger(__name__)
        
        # Set up authentication
        self._setup_authentication()
    
    def _setup_authentication(self):
        """Setup authentication for Jamf API"""
        if self.api_token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            })
        elif self.username and self.password:
            # Use basic auth to get bearer token
            self._get_bearer_token()
        else:
            raise ValueError("Either api_token or username/password must be provided")
    
    def _get_bearer_token(self):
        """Get bearer token using basic authentication"""
        try:
            auth_url = f"{self.server_url}/api/v1/auth/token"
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            
            headers = {
                'Authorization': f'Basic {credentials}',
                'Accept': 'application/json'
            }
            
            response = requests.post(auth_url, headers=headers)
            response.raise_for_status()
            
            token_data = response.json()
            self.auth_token = token_data.get('token')
            
            self.session.headers.update({
                'Authorization': f'Bearer {self.auth_token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            })
            
            self.logger.info("Successfully authenticated with Jamf Pro API")
            
        except Exception as e:
            self.logger.error(f"Failed to authenticate with Jamf Pro API: {str(e)}")
            raise
    
    def get_all_computers(self) -> List[Dict]:
        """
        Get all computers from Jamf Pro
        
        Returns:
            List of computer objects
        """
        try:
            url = f"{self.server_url}/JSSResource/computers"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            computers = data.get('computers', {}).get('computer', [])
            
            self.logger.info(f"Retrieved {len(computers)} computers from Jamf Pro")
            return computers
            
        except Exception as e:
            self.logger.error(f"Failed to get computers: {str(e)}")
            return []
    
    def get_computer_details(self, computer_id: int) -> Dict:
        """
        Get detailed information for a specific computer
        
        Args:
            computer_id: Computer ID in Jamf Pro
            
        Returns:
            Computer details dictionary
        """
        try:
            url = f"{self.server_url}/JSSResource/computers/id/{computer_id}"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            return data.get('computer', {})
            
        except Exception as e:
            self.logger.error(f"Failed to get computer details for ID {computer_id}: {str(e)}")
            return {}
    
    def get_computer_last_contact(self, computer_id: int) -> Optional[datetime]:
        """
        Get the last contact time for a computer
        
        Args:
            computer_id: Computer ID in Jamf Pro
            
        Returns:
            Last contact datetime or None if not available
        """
        try:
            computer_details = self.get_computer_details(computer_id)
            general_info = computer_details.get('general', {})
            
            # Try different date fields that might indicate last activity
            last_contact_time = general_info.get('last_contact_time_epoch')
            if last_contact_time:
                return datetime.fromtimestamp(int(last_contact_time) / 1000)
            
            # Fallback to last_contact_time (string format)
            last_contact_str = general_info.get('last_contact_time')
            if last_contact_str and last_contact_str != '':
                try:
                    return datetime.strptime(last_contact_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        return datetime.strptime(last_contact_str, '%Y-%m-%dT%H:%M:%S.%fZ')
                    except ValueError:
                        pass
            
            # Try last_report_date_epoch
            last_report_epoch = general_info.get('last_report_date_epoch')
            if last_report_epoch:
                return datetime.fromtimestamp(int(last_report_epoch) / 1000)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get last contact for computer {computer_id}: {str(e)}")
            return None
    
    def get_inactive_computers(self, inactive_days: int) -> List[Dict]:
        """
        Get computers that have been inactive for specified number of days
        
        Args:
            inactive_days: Number of days to consider as inactive
            
        Returns:
            List of inactive computers with their details
        """
        inactive_computers = []
        cutoff_date = datetime.now() - timedelta(days=inactive_days)
        
        try:
            computers = self.get_all_computers()
            
            for computer in computers:
                computer_id = computer.get('id')
                if not computer_id:
                    continue
                
                last_contact = self.get_computer_last_contact(computer_id)
                
                if last_contact is None:
                    # If no last contact info, consider it inactive
                    inactive_computers.append({
                        'id': computer_id,
                        'name': computer.get('name', 'Unknown'),
                        'serial_number': computer.get('serial_number', ''),
                        'last_contact': None,
                        'days_inactive': 'Unknown'
                    })
                elif last_contact < cutoff_date:
                    days_inactive = (datetime.now() - last_contact).days
                    inactive_computers.append({
                        'id': computer_id,
                        'name': computer.get('name', 'Unknown'),
                        'serial_number': computer.get('serial_number', ''),
                        'last_contact': last_contact,
                        'days_inactive': days_inactive
                    })
            
            self.logger.info(f"Found {len(inactive_computers)} inactive computers (>{inactive_days} days)")
            return inactive_computers
            
        except Exception as e:
            self.logger.error(f"Failed to get inactive computers: {str(e)}")
            return []
    
    def get_computer_user_info(self, computer_id: int) -> Dict:
        """
        Get user information for a computer
        
        Args:
            computer_id: Computer ID in Jamf Pro
            
        Returns:
            User information dictionary
        """
        try:
            computer_details = self.get_computer_details(computer_id)
            location = computer_details.get('location', {})
            
            return {
                'username': location.get('username', ''),
                'real_name': location.get('real_name', ''),
                'email_address': location.get('email_address', ''),
                'department': location.get('department', ''),
                'building': location.get('building', ''),
                'room': location.get('room', '')
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get user info for computer {computer_id}: {str(e)}")
            return {}
    
    def remove_computer_from_jamf(self, computer_id: int) -> bool:
        """
        Remove a computer from Jamf Pro (license reclamation)
        
        Args:
            computer_id: Computer ID to remove
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.server_url}/JSSResource/computers/id/{computer_id}"
            response = self.session.delete(url)
            response.raise_for_status()
            
            self.logger.info(f"Successfully removed computer ID {computer_id} from Jamf Pro")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove computer {computer_id}: {str(e)}")
            return False
    
    def create_computer_group(self, group_name: str, computer_ids: List[int]) -> bool:
        """
        Create a computer group for tracking reclaimed devices
        
        Args:
            group_name: Name for the computer group
            computer_ids: List of computer IDs to add to group
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # First check if group already exists
            existing_groups_url = f"{self.server_url}/JSSResource/computergroups"
            response = self.session.get(existing_groups_url)
            response.raise_for_status()
            
            existing_groups = response.json().get('computer_groups', {}).get('computer_group', [])
            existing_group_names = [group.get('name') for group in existing_groups]
            
            if group_name in existing_group_names:
                self.logger.info(f"Computer group '{group_name}' already exists")
                return True
            
            # Create new group
            group_data = {
                "computer_group": {
                    "name": group_name,
                    "is_smart": False,
                    "computers": [{"id": comp_id} for comp_id in computer_ids]
                }
            }
            
            url = f"{self.server_url}/JSSResource/computergroups/id/0"
            response = self.session.post(url, json=group_data)
            response.raise_for_status()
            
            self.logger.info(f"Successfully created computer group '{group_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create computer group '{group_name}': {str(e)}")
            return False
    
    def invalidate_token(self):
        """Invalidate the current authentication token"""
        if self.auth_token:
            try:
                url = f"{self.server_url}/api/v1/auth/invalidate-token"
                self.session.post(url)
                self.logger.info("Successfully invalidated authentication token")
            except Exception as e:
                self.logger.warning(f"Failed to invalidate token: {str(e)}")
        
        self.session.close()