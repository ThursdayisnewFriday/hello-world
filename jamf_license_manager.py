#!/usr/bin/env python3
"""
Jamf Pro License Manager
1년 이상 체크인하지 않은 디바이스의 라이선스를 자동으로 회수하는 시스템
"""

import requests
import json
import smtplib
import sqlite3
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import time
import os
from typing import List, Dict, Optional

class JamfLicenseManager:
    def __init__(self, config_file: str = 'config.json'):
        """Jamf Pro License Manager 초기화"""
        self.config = self.load_config(config_file)
        self.jamf_url = self.config['jamf']['url']
        self.jamf_username = self.config['jamf']['username'] 
        self.jamf_password = self.config['jamf']['password']
        self.token = None
        self.setup_logging()
        self.setup_database()
        
    def load_config(self, config_file: str) -> dict:
        """설정 파일 로드"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"설정 파일을 찾을 수 없습니다: {config_file}")
            raise
        except json.JSONDecodeError:
            logging.error(f"설정 파일 형식이 올바르지 않습니다: {config_file}")
            raise
    
    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('jamf_license_manager.log'),
                logging.StreamHandler()
            ]
        )
        
    def setup_database(self):
        """SQLite 데이터베이스 설정"""
        conn = sqlite3.connect('license_manager.db')
        cursor = conn.cursor()
        
        # 사용자 확인 상태를 추적하는 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_confirmations (
                device_id TEXT PRIMARY KEY,
                computer_name TEXT,
                username TEXT,
                email TEXT,
                last_checkin TEXT,
                notification_sent TEXT,
                user_response TEXT,
                response_date TEXT,
                license_recovered TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def get_api_token(self) -> str:
        """Jamf Pro API 토큰 획득"""
        auth_url = f"{self.jamf_url}/api/v1/auth/token"
        
        try:
            response = requests.post(
                auth_url,
                auth=(self.jamf_username, self.jamf_password),
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.token = token_data['token']
            logging.info("API 토큰을 성공적으로 획득했습니다.")
            return self.token
            
        except requests.exceptions.RequestException as e:
            logging.error(f"API 토큰 획득 실패: {e}")
            raise
            
    def create_smart_group(self) -> Optional[int]:
        """1년 이상 체크인하지 않은 디바이스를 위한 스마트 그룹 생성"""
        if not self.token:
            self.get_api_token()
            
        # 1년 전 날짜 계산
        one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        smart_group_data = {
            "name": "License Recovery - 1년 미체크인 디바이스",
            "is_smart": True,
            "criteria": [
                {
                    "name": "Last Check-in",
                    "priority": 0,
                    "and_or": "and",
                    "search_type": "less than x days ago",
                    "value": "365",
                    "opening_paren": False,
                    "closing_paren": False
                }
            ]
        }
        
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        try:
            # 기존 스마트 그룹이 있는지 확인
            existing_groups = self.get_smart_groups()
            for group in existing_groups:
                if group['name'] == smart_group_data['name']:
                    logging.info(f"스마트 그룹이 이미 존재합니다: ID {group['id']}")
                    return group['id']
            
            # 새 스마트 그룹 생성
            response = requests.post(
                f"{self.jamf_url}/JSSResource/computergroups/id/0",
                headers=headers,
                data=json.dumps({"computer_group": smart_group_data})
            )
            response.raise_for_status()
            
            # 생성된 그룹 ID 추출
            group_id = response.headers.get('Location', '').split('/')[-1]
            logging.info(f"스마트 그룹을 성공적으로 생성했습니다: ID {group_id}")
            return int(group_id)
            
        except requests.exceptions.RequestException as e:
            logging.error(f"스마트 그룹 생성 실패: {e}")
            return None
            
    def get_smart_groups(self) -> List[Dict]:
        """모든 스마트 그룹 조회"""
        headers = {'Authorization': f'Bearer {self.token}'}
        
        try:
            response = requests.get(
                f"{self.jamf_url}/JSSResource/computergroups",
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get('computer_groups', [])
            
        except requests.exceptions.RequestException as e:
            logging.error(f"스마트 그룹 조회 실패: {e}")
            return []
            
    def get_devices_in_group(self, group_id: int) -> List[Dict]:
        """특정 그룹의 디바이스 목록 조회"""
        headers = {'Authorization': f'Bearer {self.token}'}
        
        try:
            response = requests.get(
                f"{self.jamf_url}/JSSResource/computergroups/id/{group_id}",
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            computers = data.get('computer_group', {}).get('computers', [])
            
            # 각 컴퓨터의 상세 정보 조회
            device_details = []
            for computer in computers:
                detail = self.get_device_details(computer['id'])
                if detail:
                    device_details.append(detail)
                    
            return device_details
            
        except requests.exceptions.RequestException as e:
            logging.error(f"그룹 디바이스 조회 실패: {e}")
            return []
            
    def get_device_details(self, device_id: int) -> Optional[Dict]:
        """디바이스 상세 정보 조회"""
        headers = {'Authorization': f'Bearer {self.token}'}
        
        try:
            response = requests.get(
                f"{self.jamf_url}/JSSResource/computers/id/{device_id}",
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            computer = data.get('computer', {})
            general = computer.get('general', {})
            location = computer.get('location', {})
            
            return {
                'id': device_id,
                'name': general.get('name', ''),
                'serial_number': general.get('serial_number', ''),
                'last_contact_time': general.get('last_contact_time', ''),
                'username': location.get('username', ''),
                'email_address': location.get('email_address', ''),
                'managed': general.get('remote_management', {}).get('managed', False)
            }
            
        except requests.exceptions.RequestException as e:
            logging.error(f"디바이스 상세 정보 조회 실패 (ID: {device_id}): {e}")
            return None
            
    def send_user_notification(self, device: Dict) -> bool:
        """사용자에게 라이선스 회수 확인 이메일 발송"""
        if not device.get('email_address'):
            logging.warning(f"이메일 주소가 없는 디바이스: {device['name']}")
            return False
            
        smtp_config = self.config['email']
        
        # 확인 URL 생성 (웹 인터페이스용)
        confirmation_url = f"{self.config['web_interface']['url']}/confirm?device_id={device['id']}&token={self.generate_confirmation_token(device['id'])}"
        
        # 이메일 내용 작성
        subject = "Jamf Pro 라이선스 회수 알림 - 확인 필요"
        
        body = f"""
안녕하세요 {device['username']}님,

귀하의 디바이스 '{device['name']}'이 1년 이상 Jamf Pro에 체크인하지 않은 것으로 확인되었습니다.

디바이스 정보:
- 컴퓨터 이름: {device['name']}
- 시리얼 번호: {device['serial_number']}
- 마지막 체크인: {device['last_contact_time']}

만약 이 디바이스를 더 이상 사용하지 않으신다면, 라이선스를 회수하여 다른 사용자가 사용할 수 있도록 하겠습니다.

아래 링크를 클릭하여 선택해주세요:

🔗 계속 사용: {confirmation_url}&action=keep
🔗 사용 안함 (라이선스 회수): {confirmation_url}&action=remove

이 알림에 7일 이내 응답하지 않으시면 자동으로 라이선스가 회수됩니다.

문의사항이 있으시면 IT 팀에 연락주세요.

감사합니다.
IT 관리팀
"""

        try:
            msg = MIMEMultipart()
            msg['From'] = smtp_config['sender_email']
            msg['To'] = device['email_address']
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            server = smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port'])
            server.starttls()
            server.login(smtp_config['username'], smtp_config['password'])
            
            text = msg.as_string()
            server.sendmail(smtp_config['sender_email'], device['email_address'], text)
            server.quit()
            
            # 데이터베이스에 알림 발송 기록
            self.record_notification_sent(device)
            
            logging.info(f"알림 이메일 발송 완료: {device['email_address']}")
            return True
            
        except Exception as e:
            logging.error(f"이메일 발송 실패: {e}")
            return False
            
    def generate_confirmation_token(self, device_id: int) -> str:
        """확인 토큰 생성 (간단한 구현)"""
        import hashlib
        return hashlib.md5(f"{device_id}{datetime.now().strftime('%Y%m%d')}".encode()).hexdigest()
        
    def record_notification_sent(self, device: Dict):
        """알림 발송 기록을 데이터베이스에 저장"""
        conn = sqlite3.connect('license_manager.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_confirmations 
            (device_id, computer_name, username, email, last_checkin, notification_sent)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            str(device['id']),
            device['name'],
            device['username'],
            device['email_address'],
            device['last_contact_time'],
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
    def check_user_responses(self):
        """사용자 응답 확인 및 처리"""
        conn = sqlite3.connect('license_manager.db')
        cursor = conn.cursor()
        
        # 7일 이상 응답이 없는 알림들 조회
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        
        cursor.execute('''
            SELECT * FROM user_confirmations 
            WHERE notification_sent < ? 
            AND user_response IS NULL 
            AND license_recovered IS NULL
        ''', (seven_days_ago,))
        
        expired_notifications = cursor.fetchall()
        
        for notification in expired_notifications:
            device_id = notification[0]
            logging.info(f"응답 기한 만료 - 자동 라이선스 회수: 디바이스 ID {device_id}")
            self.recover_license(device_id, "자동 회수 (무응답)")
            
        conn.close()
        
    def recover_license(self, device_id: str, reason: str = "사용자 요청"):
        """디바이스 라이선스 회수"""
        if not self.token:
            self.get_api_token()
            
        headers = {'Authorization': f'Bearer {self.token}'}
        
        try:
            # 디바이스를 관리 해제
            response = requests.put(
                f"{self.jamf_url}/JSSResource/computers/id/{device_id}",
                headers=headers,
                data=json.dumps({
                    "computer": {
                        "general": {
                            "remote_management": {
                                "managed": False
                            }
                        }
                    }
                })
            )
            response.raise_for_status()
            
            # 데이터베이스 업데이트
            conn = sqlite3.connect('license_manager.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE user_confirmations 
                SET license_recovered = ?, user_response = ?
                WHERE device_id = ?
            ''', (datetime.now().isoformat(), reason, device_id))
            
            conn.commit()
            conn.close()
            
            logging.info(f"라이선스 회수 완료: 디바이스 ID {device_id}, 사유: {reason}")
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"라이선스 회수 실패: {e}")
            return False
            
    def run_license_recovery_process(self):
        """전체 라이선스 회수 프로세스 실행"""
        logging.info("라이선스 회수 프로세스 시작")
        
        try:
            # 1. API 토큰 획득
            self.get_api_token()
            
            # 2. 스마트 그룹 생성/확인
            group_id = self.create_smart_group()
            if not group_id:
                logging.error("스마트 그룹 생성/확인 실패")
                return
                
            # 3. 그룹 내 디바이스 조회
            devices = self.get_devices_in_group(group_id)
            logging.info(f"1년 미체크인 디바이스 {len(devices)}대 발견")
            
            # 4. 각 디바이스에 대해 사용자 알림 발송
            for device in devices:
                if device['email_address']:
                    # 이미 알림을 보냈는지 확인
                    if not self.is_notification_already_sent(device['id']):
                        self.send_user_notification(device)
                        time.sleep(1)  # API 속도 제한 고려
                        
            # 5. 이전 알림들의 응답 확인 및 처리
            self.check_user_responses()
            
            logging.info("라이선스 회수 프로세스 완료")
            
        except Exception as e:
            logging.error(f"라이선스 회수 프로세스 실행 중 오류: {e}")
            
    def is_notification_already_sent(self, device_id: int) -> bool:
        """이미 알림이 발송되었는지 확인"""
        conn = sqlite3.connect('license_manager.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT notification_sent FROM user_confirmations 
            WHERE device_id = ? AND notification_sent IS NOT NULL
        ''', (str(device_id),))
        
        result = cursor.fetchone()
        conn.close()
        
        return result is not None

def main():
    """메인 실행 함수"""
    manager = JamfLicenseManager()
    manager.run_license_recovery_process()

if __name__ == "__main__":
    main()