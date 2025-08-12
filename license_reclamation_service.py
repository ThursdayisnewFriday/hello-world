#!/usr/bin/env python3
"""
Jamf License Reclamation Service
Main service that orchestrates the license reclamation process including grace periods,
database tracking, and automatic reclamation.
"""

import sqlite3
import logging
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from jamf_client import JamfAPIClient
from notification_service import NotificationService

@dataclass
class GracePeriodEntry:
    """Represents a device in grace period"""
    computer_id: int
    computer_name: str
    serial_number: str
    last_contact: Optional[datetime]
    days_inactive: int
    grace_start_date: datetime
    grace_end_date: datetime
    user_info: Dict
    notified: bool = False

class LicenseReclamationService:
    """Main service for managing Jamf license reclamation"""
    
    def __init__(self, jamf_client: JamfAPIClient, notification_service: NotificationService,
                 database_path: str = "license_reclamation.db"):
        """
        Initialize license reclamation service
        
        Args:
            jamf_client: Jamf API client instance
            notification_service: Notification service instance
            database_path: Path to SQLite database file
        """
        self.jamf_client = jamf_client
        self.notification_service = notification_service
        self.database_path = database_path
        self.logger = logging.getLogger(__name__)
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for tracking grace periods and reclamations"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Grace period tracking table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS grace_periods (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        computer_id INTEGER UNIQUE,
                        computer_name TEXT,
                        serial_number TEXT,
                        last_contact TEXT,
                        days_inactive INTEGER,
                        grace_start_date TEXT,
                        grace_end_date TEXT,
                        user_info TEXT,
                        notified BOOLEAN DEFAULT FALSE,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Reclamation history table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reclamation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        computer_id INTEGER,
                        computer_name TEXT,
                        serial_number TEXT,
                        last_contact TEXT,
                        days_inactive INTEGER,
                        user_info TEXT,
                        reclamation_date TEXT,
                        success BOOLEAN,
                        error_message TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                conn.commit()
                self.logger.info("Database initialized successfully")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {str(e)}")
            raise
    
    def run_license_reclamation_cycle(self, inactive_days_threshold: int, 
                                    grace_period_days: int = 7,
                                    max_reclaims_per_run: int = 10,
                                    dry_run: bool = False) -> Dict:
        """
        Run complete license reclamation cycle
        
        Args:
            inactive_days_threshold: Days of inactivity before entering grace period
            grace_period_days: Grace period duration in days
            max_reclaims_per_run: Maximum number of licenses to reclaim per run
            dry_run: If True, don't actually reclaim licenses (for testing)
            
        Returns:
            Dictionary with cycle results
        """
        cycle_results = {
            'start_time': datetime.now(),
            'inactive_computers_found': 0,
            'new_grace_periods': 0,
            'licenses_reclaimed': 0,
            'failed_reclamations': 0,
            'notifications_sent': 0,
            'errors': []
        }
        
        try:
            self.logger.info("Starting license reclamation cycle")
            
            # Step 1: Find inactive computers
            inactive_computers = self.jamf_client.get_inactive_computers(inactive_days_threshold)
            cycle_results['inactive_computers_found'] = len(inactive_computers)
            
            if not inactive_computers:
                self.logger.info("No inactive computers found")
                return cycle_results
            
            # Step 2: Process new inactive computers (add to grace period)
            new_grace_entries = self._process_new_inactive_computers(
                inactive_computers, grace_period_days
            )
            cycle_results['new_grace_periods'] = len(new_grace_entries)
            
            # Step 3: Send grace period notifications for new entries
            if new_grace_entries:
                notification_sent = self._send_grace_period_notifications(new_grace_entries)
                if notification_sent:
                    cycle_results['notifications_sent'] += 1
            
            # Step 4: Process computers whose grace period has expired
            expired_computers = self._get_expired_grace_periods()
            
            if expired_computers:
                reclaimed, failed = self._reclaim_licenses(
                    expired_computers, max_reclaims_per_run, dry_run
                )
                cycle_results['licenses_reclaimed'] = len(reclaimed)
                cycle_results['failed_reclamations'] = len(failed)
                
                # Send reclamation notifications
                if reclaimed or failed:
                    notification_sent = self.notification_service.send_reclamation_notification(
                        reclaimed, failed
                    )
                    if notification_sent:
                        cycle_results['notifications_sent'] += 1
            
            cycle_results['end_time'] = datetime.now()
            cycle_results['duration'] = (cycle_results['end_time'] - cycle_results['start_time']).total_seconds()
            
            self.logger.info(f"License reclamation cycle completed: {cycle_results}")
            
        except Exception as e:
            error_msg = f"Error during license reclamation cycle: {str(e)}"
            self.logger.error(error_msg)
            cycle_results['errors'].append(error_msg)
            
            # Send error notification
            self.notification_service.send_error_notification(
                "License reclamation cycle failed", str(e)
            )
        
        return cycle_results
    
    def _process_new_inactive_computers(self, inactive_computers: List[Dict], 
                                      grace_period_days: int) -> List[GracePeriodEntry]:
        """
        Process newly inactive computers and add them to grace period
        
        Args:
            inactive_computers: List of inactive computers
            grace_period_days: Grace period duration in days
            
        Returns:
            List of new grace period entries
        """
        new_grace_entries = []
        
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                for computer in inactive_computers:
                    computer_id = computer.get('id')
                    
                    # Check if computer is already in grace period
                    cursor.execute(
                        'SELECT id FROM grace_periods WHERE computer_id = ?',
                        (computer_id,)
                    )
                    
                    if cursor.fetchone():
                        continue  # Already in grace period
                    
                    # Get user information
                    user_info = self.jamf_client.get_computer_user_info(computer_id)
                    
                    # Create grace period entry
                    grace_start_date = datetime.now()
                    grace_end_date = grace_start_date + timedelta(days=grace_period_days)
                    
                    grace_entry = GracePeriodEntry(
                        computer_id=computer_id,
                        computer_name=computer.get('name', 'Unknown'),
                        serial_number=computer.get('serial_number', ''),
                        last_contact=computer.get('last_contact'),
                        days_inactive=computer.get('days_inactive', 0),
                        grace_start_date=grace_start_date,
                        grace_end_date=grace_end_date,
                        user_info=user_info
                    )
                    
                    # Insert into database
                    cursor.execute('''
                        INSERT INTO grace_periods 
                        (computer_id, computer_name, serial_number, last_contact, 
                         days_inactive, grace_start_date, grace_end_date, user_info)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        computer_id,
                        grace_entry.computer_name,
                        grace_entry.serial_number,
                        grace_entry.last_contact.isoformat() if grace_entry.last_contact else None,
                        grace_entry.days_inactive,
                        grace_entry.grace_start_date.isoformat(),
                        grace_entry.grace_end_date.isoformat(),
                        json.dumps(user_info)
                    ))
                    
                    new_grace_entries.append(grace_entry)
                    self.logger.info(f"Added computer {computer_id} to grace period")
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to process new inactive computers: {str(e)}")
        
        return new_grace_entries
    
    def _send_grace_period_notifications(self, grace_entries: List[GracePeriodEntry]) -> bool:
        """
        Send notifications for computers entering grace period
        
        Args:
            grace_entries: List of grace period entries
            
        Returns:
            True if notification sent successfully
        """
        try:
            # Convert grace entries to notification format
            inactive_computers = []
            for entry in grace_entries:
                inactive_computers.append({
                    'id': entry.computer_id,
                    'name': entry.computer_name,
                    'serial_number': entry.serial_number,
                    'last_contact': entry.last_contact,
                    'days_inactive': entry.days_inactive,
                    'user_info': entry.user_info
                })
            
            # Send notification
            notification_sent = self.notification_service.send_grace_period_notification(
                inactive_computers
            )
            
            if notification_sent:
                # Mark as notified in database
                with sqlite3.connect(self.database_path) as conn:
                    cursor = conn.cursor()
                    for entry in grace_entries:
                        cursor.execute(
                            'UPDATE grace_periods SET notified = TRUE WHERE computer_id = ?',
                            (entry.computer_id,)
                        )
                    conn.commit()
                
                self.logger.info(f"Grace period notification sent for {len(grace_entries)} computers")
            
            return notification_sent
            
        except Exception as e:
            self.logger.error(f"Failed to send grace period notifications: {str(e)}")
            return False
    
    def _get_expired_grace_periods(self) -> List[Dict]:
        """
        Get computers whose grace period has expired
        
        Returns:
            List of computers ready for license reclamation
        """
        expired_computers = []
        
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Find expired grace periods
                now = datetime.now().isoformat()
                cursor.execute('''
                    SELECT computer_id, computer_name, serial_number, last_contact,
                           days_inactive, user_info, grace_start_date, grace_end_date
                    FROM grace_periods 
                    WHERE grace_end_date <= ?
                ''', (now,))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    computer_id, computer_name, serial_number, last_contact, \
                    days_inactive, user_info_json, grace_start_date, grace_end_date = row
                    
                    last_contact_dt = None
                    if last_contact:
                        try:
                            last_contact_dt = datetime.fromisoformat(last_contact)
                        except ValueError:
                            pass
                    
                    user_info = json.loads(user_info_json) if user_info_json else {}
                    
                    expired_computers.append({
                        'id': computer_id,
                        'name': computer_name,
                        'serial_number': serial_number,
                        'last_contact': last_contact_dt,
                        'days_inactive': days_inactive,
                        'user_info': user_info,
                        'grace_start_date': datetime.fromisoformat(grace_start_date),
                        'grace_end_date': datetime.fromisoformat(grace_end_date)
                    })
                
                self.logger.info(f"Found {len(expired_computers)} computers with expired grace periods")
                
        except Exception as e:
            self.logger.error(f"Failed to get expired grace periods: {str(e)}")
        
        return expired_computers
    
    def _reclaim_licenses(self, computers: List[Dict], max_reclaims: int, 
                         dry_run: bool = False) -> Tuple[List[Dict], List[Dict]]:
        """
        Reclaim licenses for expired computers
        
        Args:
            computers: List of computers to reclaim licenses from
            max_reclaims: Maximum number of reclamations per run
            dry_run: If True, don't actually reclaim licenses
            
        Returns:
            Tuple of (successful_reclamations, failed_reclamations)
        """
        reclaimed = []
        failed = []
        
        # Limit the number of reclamations per run
        computers_to_process = computers[:max_reclaims]
        
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                for computer in computers_to_process:
                    computer_id = computer['id']
                    
                    try:
                        if not dry_run:
                            # Actually remove from Jamf
                            success = self.jamf_client.remove_computer_from_jamf(computer_id)
                        else:
                            # Dry run - simulate success
                            success = True
                            self.logger.info(f"DRY RUN: Would reclaim license for computer {computer_id}")
                        
                        if success:
                            reclaimed.append({
                                **computer,
                                'status': 'reclaimed',
                                'reclamation_date': datetime.now()
                            })
                            
                            # Remove from grace periods table
                            cursor.execute(
                                'DELETE FROM grace_periods WHERE computer_id = ?',
                                (computer_id,)
                            )
                            
                            # Add to reclamation history
                            cursor.execute('''
                                INSERT INTO reclamation_history 
                                (computer_id, computer_name, serial_number, last_contact,
                                 days_inactive, user_info, reclamation_date, success)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                computer_id,
                                computer['name'],
                                computer['serial_number'],
                                computer['last_contact'].isoformat() if computer['last_contact'] else None,
                                computer['days_inactive'],
                                json.dumps(computer['user_info']),
                                datetime.now().isoformat(),
                                True
                            ))
                            
                            self.logger.info(f"Successfully reclaimed license for computer {computer_id}")
                        else:
                            failed.append({
                                **computer,
                                'status': 'failed',
                                'error': 'Failed to remove from Jamf'
                            })
                            
                            # Add to reclamation history as failed
                            cursor.execute('''
                                INSERT INTO reclamation_history 
                                (computer_id, computer_name, serial_number, last_contact,
                                 days_inactive, user_info, reclamation_date, success, error_message)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                computer_id,
                                computer['name'],
                                computer['serial_number'],
                                computer['last_contact'].isoformat() if computer['last_contact'] else None,
                                computer['days_inactive'],
                                json.dumps(computer['user_info']),
                                datetime.now().isoformat(),
                                False,
                                'Failed to remove from Jamf'
                            ))
                            
                    except Exception as e:
                        error_msg = f"Error reclaiming license for computer {computer_id}: {str(e)}"
                        self.logger.error(error_msg)
                        
                        failed.append({
                            **computer,
                            'status': 'failed',
                            'error': str(e)
                        })
                        
                        # Add to reclamation history as failed
                        cursor.execute('''
                            INSERT INTO reclamation_history 
                            (computer_id, computer_name, serial_number, last_contact,
                             days_inactive, user_info, reclamation_date, success, error_message)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            computer_id,
                            computer['name'],
                            computer['serial_number'],
                            computer['last_contact'].isoformat() if computer['last_contact'] else None,
                            computer['days_inactive'],
                            json.dumps(computer['user_info']),
                            datetime.now().isoformat(),
                            False,
                            str(e)
                        ))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Failed during license reclamation: {str(e)}")
        
        return reclaimed, failed
    
    def get_grace_period_status(self) -> List[Dict]:
        """
        Get current grace period status
        
        Returns:
            List of computers currently in grace period
        """
        grace_period_computers = []
        
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT computer_id, computer_name, serial_number, last_contact,
                           days_inactive, grace_start_date, grace_end_date, user_info, notified
                    FROM grace_periods 
                    ORDER BY grace_end_date ASC
                ''')
                
                rows = cursor.fetchall()
                
                for row in rows:
                    computer_id, computer_name, serial_number, last_contact, \
                    days_inactive, grace_start_date, grace_end_date, user_info_json, notified = row
                    
                    last_contact_dt = None
                    if last_contact:
                        try:
                            last_contact_dt = datetime.fromisoformat(last_contact)
                        except ValueError:
                            pass
                    
                    user_info = json.loads(user_info_json) if user_info_json else {}
                    grace_start_dt = datetime.fromisoformat(grace_start_date)
                    grace_end_dt = datetime.fromisoformat(grace_end_date)
                    
                    days_remaining = (grace_end_dt - datetime.now()).days
                    
                    grace_period_computers.append({
                        'computer_id': computer_id,
                        'computer_name': computer_name,
                        'serial_number': serial_number,
                        'last_contact': last_contact_dt,
                        'days_inactive': days_inactive,
                        'grace_start_date': grace_start_dt,
                        'grace_end_date': grace_end_dt,
                        'days_remaining': max(0, days_remaining),
                        'user_info': user_info,
                        'notified': bool(notified),
                        'expired': days_remaining <= 0
                    })
                
        except Exception as e:
            self.logger.error(f"Failed to get grace period status: {str(e)}")
        
        return grace_period_computers
    
    def get_reclamation_history(self, days: int = 30) -> List[Dict]:
        """
        Get reclamation history for specified number of days
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of reclamation history entries
        """
        history = []
        
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
                
                cursor.execute('''
                    SELECT computer_id, computer_name, serial_number, last_contact,
                           days_inactive, user_info, reclamation_date, success, error_message
                    FROM reclamation_history 
                    WHERE reclamation_date >= ?
                    ORDER BY reclamation_date DESC
                ''', (cutoff_date,))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    computer_id, computer_name, serial_number, last_contact, \
                    days_inactive, user_info_json, reclamation_date, success, error_message = row
                    
                    last_contact_dt = None
                    if last_contact:
                        try:
                            last_contact_dt = datetime.fromisoformat(last_contact)
                        except ValueError:
                            pass
                    
                    user_info = json.loads(user_info_json) if user_info_json else {}
                    reclamation_dt = datetime.fromisoformat(reclamation_date)
                    
                    history.append({
                        'computer_id': computer_id,
                        'computer_name': computer_name,
                        'serial_number': serial_number,
                        'last_contact': last_contact_dt,
                        'days_inactive': days_inactive,
                        'user_info': user_info,
                        'reclamation_date': reclamation_dt,
                        'success': bool(success),
                        'error_message': error_message
                    })
                
        except Exception as e:
            self.logger.error(f"Failed to get reclamation history: {str(e)}")
        
        return history
    
    def cleanup_old_records(self, days: int = 365):
        """
        Clean up old records from the database
        
        Args:
            days: Number of days to keep records
        """
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
                
                # Clean up old reclamation history
                cursor.execute(
                    'DELETE FROM reclamation_history WHERE created_at < ?',
                    (cutoff_date,)
                )
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                self.logger.info(f"Cleaned up {deleted_count} old reclamation history records")
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup old records: {str(e)}")
    
    def close(self):
        """Close the service and clean up resources"""
        try:
            self.jamf_client.invalidate_token()
            self.logger.info("License reclamation service closed")
        except Exception as e:
            self.logger.warning(f"Error closing service: {str(e)}")