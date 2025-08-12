#!/usr/bin/env python3
"""
Notification Service for Jamf License Reclamation
This module handles email and Slack notifications for license reclamation events.
"""

import smtplib
import logging
import requests
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import List, Dict, Optional
import csv
import io

class NotificationService:
    """Service for sending notifications about license reclamation events"""
    
    def __init__(self, smtp_server: str, smtp_port: int, email_username: str, 
                 email_password: str, admin_email: str, slack_webhook_url: str = None):
        """
        Initialize notification service
        
        Args:
            smtp_server: SMTP server address
            smtp_port: SMTP server port
            email_username: Email username for authentication
            email_password: Email password for authentication
            admin_email: Admin email address for notifications
            slack_webhook_url: Optional Slack webhook URL
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email_username = email_username
        self.email_password = email_password
        self.admin_email = admin_email
        self.slack_webhook_url = slack_webhook_url
        self.logger = logging.getLogger(__name__)
    
    def send_email_notification(self, subject: str, body: str, recipient: str = None, 
                              attachment_data: Optional[Dict] = None) -> bool:
        """
        Send email notification
        
        Args:
            subject: Email subject
            body: Email body (HTML supported)
            recipient: Email recipient (defaults to admin_email)
            attachment_data: Optional attachment data {'filename': str, 'content': str}
            
        Returns:
            True if successful, False otherwise
        """
        try:
            recipient = recipient or self.admin_email
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.email_username
            msg['To'] = recipient
            msg['Subject'] = subject
            
            # Add body
            msg.attach(MIMEText(body, 'html'))
            
            # Add attachment if provided
            if attachment_data:
                attachment = MIMEBase('application', 'octet-stream')
                attachment.set_payload(attachment_data['content'])
                encoders.encode_base64(attachment)
                attachment.add_header(
                    'Content-Disposition',
                    f"attachment; filename= {attachment_data['filename']}"
                )
                msg.attach(attachment)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_username, self.email_password)
                server.send_message(msg)
            
            self.logger.info(f"Email notification sent to {recipient}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {str(e)}")
            return False
    
    def send_slack_notification(self, message: str, channel: str = None) -> bool:
        """
        Send Slack notification
        
        Args:
            message: Message to send
            channel: Slack channel (optional, uses webhook default)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.slack_webhook_url:
            self.logger.warning("Slack webhook URL not configured")
            return False
        
        try:
            payload = {
                'text': message,
                'username': 'Jamf License Reclamation Bot',
                'icon_emoji': ':computer:'
            }
            
            if channel:
                payload['channel'] = channel
            
            response = requests.post(self.slack_webhook_url, json=payload)
            response.raise_for_status()
            
            self.logger.info("Slack notification sent successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send Slack notification: {str(e)}")
            return False
    
    def send_grace_period_notification(self, inactive_computers: List[Dict]) -> bool:
        """
        Send notification about computers entering grace period
        
        Args:
            inactive_computers: List of inactive computers
            
        Returns:
            True if successful, False otherwise
        """
        if not inactive_computers:
            return True
        
        # Generate email content
        subject = f"Jamf License Reclamation - Grace Period Started ({len(inactive_computers)} devices)"
        
        body = self._generate_grace_period_email(inactive_computers)
        
        # Generate CSV attachment
        csv_content = self._generate_csv_report(inactive_computers)
        attachment = {
            'filename': f'grace_period_devices_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
            'content': csv_content
        }
        
        # Send email
        email_sent = self.send_email_notification(subject, body, attachment_data=attachment)
        
        # Send Slack notification
        slack_message = f"🔔 Grace period started for {len(inactive_computers)} inactive devices. License reclamation will occur in 7 days if devices remain inactive."
        slack_sent = self.send_slack_notification(slack_message)
        
        return email_sent or slack_sent
    
    def send_reclamation_notification(self, reclaimed_computers: List[Dict], 
                                    failed_reclamations: List[Dict] = None) -> bool:
        """
        Send notification about completed license reclamations
        
        Args:
            reclaimed_computers: List of successfully reclaimed computers
            failed_reclamations: List of failed reclamation attempts
            
        Returns:
            True if successful, False otherwise
        """
        if not reclaimed_computers and not failed_reclamations:
            return True
        
        # Generate email content
        subject = f"Jamf License Reclamation Complete - {len(reclaimed_computers)} licenses reclaimed"
        
        body = self._generate_reclamation_email(reclaimed_computers, failed_reclamations)
        
        # Generate CSV attachment
        all_computers = reclaimed_computers + (failed_reclamations or [])
        csv_content = self._generate_csv_report(all_computers, include_status=True)
        attachment = {
            'filename': f'license_reclamation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
            'content': csv_content
        }
        
        # Send email
        email_sent = self.send_email_notification(subject, body, attachment_data=attachment)
        
        # Send Slack notification
        success_count = len(reclaimed_computers)
        failed_count = len(failed_reclamations) if failed_reclamations else 0
        
        slack_message = f"✅ License reclamation complete: {success_count} licenses reclaimed"
        if failed_count > 0:
            slack_message += f", {failed_count} failed"
        
        slack_sent = self.send_slack_notification(slack_message)
        
        return email_sent or slack_sent
    
    def send_error_notification(self, error_message: str, details: str = None) -> bool:
        """
        Send error notification to administrators
        
        Args:
            error_message: Main error message
            details: Additional error details
            
        Returns:
            True if successful, False otherwise
        """
        subject = "Jamf License Reclamation - Error Alert"
        
        body = f"""
        <html>
        <body>
            <h2>🚨 Jamf License Reclamation Error</h2>
            <p><strong>Error:</strong> {error_message}</p>
            {f'<p><strong>Details:</strong> {details}</p>' if details else ''}
            <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Please check the logs and investigate the issue.</p>
        </body>
        </html>
        """
        
        # Send email
        email_sent = self.send_email_notification(subject, body)
        
        # Send Slack notification
        slack_message = f"🚨 Jamf License Reclamation Error: {error_message}"
        slack_sent = self.send_slack_notification(slack_message)
        
        return email_sent or slack_sent
    
    def _generate_grace_period_email(self, inactive_computers: List[Dict]) -> str:
        """Generate HTML email content for grace period notification"""
        
        devices_table = ""
        for computer in inactive_computers[:10]:  # Show first 10 devices
            last_contact = computer.get('last_contact')
            last_contact_str = last_contact.strftime('%Y-%m-%d %H:%M:%S') if last_contact else 'Unknown'
            
            devices_table += f"""
            <tr>
                <td>{computer.get('name', 'Unknown')}</td>
                <td>{computer.get('serial_number', '')}</td>
                <td>{last_contact_str}</td>
                <td>{computer.get('days_inactive', 'Unknown')}</td>
            </tr>
            """
        
        additional_devices = len(inactive_computers) - 10
        if additional_devices > 0:
            devices_table += f"""
            <tr>
                <td colspan="4" style="text-align: center; font-style: italic;">
                    ... and {additional_devices} more devices (see attachment for full list)
                </td>
            </tr>
            """
        
        return f"""
        <html>
        <body>
            <h2>🔔 Jamf License Reclamation - Grace Period Started</h2>
            <p>The following devices have been inactive for more than the configured threshold and have entered the grace period:</p>
            
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #f2f2f2;">
                        <th>Device Name</th>
                        <th>Serial Number</th>
                        <th>Last Contact</th>
                        <th>Days Inactive</th>
                    </tr>
                </thead>
                <tbody>
                    {devices_table}
                </tbody>
            </table>
            
            <h3>⚠️ Important Information:</h3>
            <ul>
                <li><strong>Total devices affected:</strong> {len(inactive_computers)}</li>
                <li><strong>Grace period:</strong> 7 days</li>
                <li><strong>Action required:</strong> If these devices remain inactive, their licenses will be automatically reclaimed in 7 days</li>
                <li><strong>To prevent reclamation:</strong> Have users log into their devices or contact IT support</li>
            </ul>
            
            <p>For a complete list of affected devices, please see the attached CSV file.</p>
            
            <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
    
    def _generate_reclamation_email(self, reclaimed_computers: List[Dict], 
                                  failed_reclamations: List[Dict] = None) -> str:
        """Generate HTML email content for reclamation notification"""
        
        # Success table
        success_table = ""
        for computer in reclaimed_computers[:10]:  # Show first 10 devices
            last_contact = computer.get('last_contact')
            last_contact_str = last_contact.strftime('%Y-%m-%d %H:%M:%S') if last_contact else 'Unknown'
            
            success_table += f"""
            <tr>
                <td>{computer.get('name', 'Unknown')}</td>
                <td>{computer.get('serial_number', '')}</td>
                <td>{last_contact_str}</td>
                <td>{computer.get('days_inactive', 'Unknown')}</td>
            </tr>
            """
        
        additional_success = len(reclaimed_computers) - 10
        if additional_success > 0:
            success_table += f"""
            <tr>
                <td colspan="4" style="text-align: center; font-style: italic;">
                    ... and {additional_success} more devices successfully reclaimed
                </td>
            </tr>
            """
        
        # Failed table
        failed_table = ""
        if failed_reclamations:
            for computer in failed_reclamations[:5]:  # Show first 5 failed devices
                failed_table += f"""
                <tr>
                    <td>{computer.get('name', 'Unknown')}</td>
                    <td>{computer.get('serial_number', '')}</td>
                    <td>{computer.get('error', 'Unknown error')}</td>
                </tr>
                """
        
        return f"""
        <html>
        <body>
            <h2>✅ Jamf License Reclamation Complete</h2>
            
            <h3>Successfully Reclaimed Licenses ({len(reclaimed_computers)} devices):</h3>
            {f'''
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #d4edda;">
                        <th>Device Name</th>
                        <th>Serial Number</th>
                        <th>Last Contact</th>
                        <th>Days Inactive</th>
                    </tr>
                </thead>
                <tbody>
                    {success_table}
                </tbody>
            </table>
            ''' if reclaimed_computers else '<p>No devices were reclaimed in this run.</p>'}
            
            {f'''
            <h3>❌ Failed Reclamations ({len(failed_reclamations)} devices):</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #f8d7da;">
                        <th>Device Name</th>
                        <th>Serial Number</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody>
                    {failed_table}
                </tbody>
            </table>
            ''' if failed_reclamations else ''}
            
            <h3>📊 Summary:</h3>
            <ul>
                <li><strong>Licenses reclaimed:</strong> {len(reclaimed_computers)}</li>
                {f'<li><strong>Failed reclamations:</strong> {len(failed_reclamations)}</li>' if failed_reclamations else ''}
                <li><strong>Completion time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
            </ul>
            
            <p>For a complete list of all affected devices, please see the attached CSV file.</p>
        </body>
        </html>
        """
    
    def _generate_csv_report(self, computers: List[Dict], include_status: bool = False) -> str:
        """Generate CSV report of computers"""
        output = io.StringIO()
        
        if include_status:
            fieldnames = ['Device Name', 'Serial Number', 'Last Contact', 'Days Inactive', 'Status', 'Error']
        else:
            fieldnames = ['Device Name', 'Serial Number', 'Last Contact', 'Days Inactive', 'User Name', 'Email']
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for computer in computers:
            last_contact = computer.get('last_contact')
            last_contact_str = last_contact.strftime('%Y-%m-%d %H:%M:%S') if last_contact else 'Unknown'
            
            row = {
                'Device Name': computer.get('name', 'Unknown'),
                'Serial Number': computer.get('serial_number', ''),
                'Last Contact': last_contact_str,
                'Days Inactive': computer.get('days_inactive', 'Unknown'),
            }
            
            if include_status:
                row['Status'] = computer.get('status', 'Unknown')
                row['Error'] = computer.get('error', '')
            else:
                user_info = computer.get('user_info', {})
                row['User Name'] = user_info.get('real_name', '')
                row['Email'] = user_info.get('email_address', '')
            
            writer.writerow(row)
        
        return output.getvalue()