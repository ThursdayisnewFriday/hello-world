#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jamf Pro 스마트 그룹 기반 맥북 관리 자동화 스크립트

이 스크립트는 다음 기능을 제공합니다:
1. Jamf Pro API를 통한 Bearer Token 인증
2. 지정된 스마트 그룹(1년 이상 체크인하지 않은 맥북)의 멤버 조회
3. 각 디바이스에 대한 라이선스 회수 또는 구성 프로필 삭제 작업 수행
4. 상세한 로깅 및 오류 처리

Author: AI Assistant
Date: 2024
"""

import requests
import json
import time
import logging
from typing import List, Dict, Optional
from datetime import datetime
import sys

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('jamf_macbook_manager.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class JamfProManager:
    """Jamf Pro API를 사용한 디바이스 관리 클래스"""
    
    def __init__(self, server_url: str, username: str, password: str):
        """
        JamfProManager 초기화
        
        Args:
            server_url (str): Jamf Pro 서버 URL (예: https://yourcompany.jamfcloud.com)
            username (str): Jamf Pro 관리자 계정 사용자명
            password (str): Jamf Pro 관리자 계정 비밀번호
        """
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.password = password
        self.bearer_token = None
        self.token_expires = None
        
        # HTTP 세션 설정 (연결 재사용을 위함)
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        print(f"🔧 Jamf Pro Manager 초기화 완료 - 서버: {self.server_url}")
        logger.info(f"Jamf Pro Manager initialized for server: {self.server_url}")
    
    def authenticate(self) -> bool:
        """
        Jamf Pro API에 인증하고 Bearer Token을 획득
        
        Returns:
            bool: 인증 성공 여부
        """
        print("🔐 Jamf Pro API 인증을 시작합니다...")
        logger.info("Starting Jamf Pro API authentication")
        
        auth_url = f"{self.server_url}/api/v1/auth/token"
        
        try:
            # Basic 인증을 사용하여 Bearer Token 요청
            response = self.session.post(
                auth_url,
                auth=(self.username, self.password),
                timeout=30
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.bearer_token = token_data.get('token')
                self.token_expires = token_data.get('expires')
                
                # Bearer Token을 세션 헤더에 추가
                self.session.headers.update({
                    'Authorization': f'Bearer {self.bearer_token}'
                })
                
                print("✅ API 인증 성공!")
                print(f"   토큰 만료 시간: {self.token_expires}")
                logger.info(f"Authentication successful. Token expires: {self.token_expires}")
                return True
            else:
                print(f"❌ 인증 실패 - HTTP {response.status_code}")
                print(f"   오류 메시지: {response.text}")
                logger.error(f"Authentication failed - HTTP {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 인증 중 네트워크 오류 발생: {e}")
            logger.error(f"Network error during authentication: {e}")
            return False
        except Exception as e:
            print(f"❌ 인증 중 예상치 못한 오류 발생: {e}")
            logger.error(f"Unexpected error during authentication: {e}")
            return False
    
    def get_smart_group_members(self, group_id: int) -> List[Dict]:
        """
        지정된 스마트 그룹의 멤버 디바이스 목록을 조회
        
        Args:
            group_id (int): 스마트 그룹 ID (예: 123)
            
        Returns:
            List[Dict]: 그룹에 속한 디바이스 정보 리스트
        """
        print(f"📋 스마트 그룹 ID {group_id}의 멤버를 조회합니다...")
        logger.info(f"Fetching members of smart group ID: {group_id}")
        
        # Jamf Pro Classic API 사용 (스마트 그룹 정보는 Classic API에서만 제공)
        group_url = f"{self.server_url}/JSSResource/computergroups/id/{group_id}"
        
        try:
            response = self.session.get(group_url, timeout=30)
            
            if response.status_code == 200:
                group_data = response.json()
                computers = group_data.get('computer_group', {}).get('computers', [])
                
                print(f"✅ 스마트 그룹 멤버 조회 성공!")
                print(f"   그룹명: {group_data.get('computer_group', {}).get('name', 'Unknown')}")
                print(f"   총 디바이스 수: {len(computers)}대")
                
                logger.info(f"Successfully retrieved {len(computers)} devices from smart group")
                
                # 각 디바이스 정보 출력
                for i, computer in enumerate(computers, 1):
                    device_id = computer.get('id')
                    device_name = computer.get('name')
                    serial_number = computer.get('serial_number')
                    
                    print(f"   [{i:3d}] ID: {device_id:>5} | 이름: {device_name:<20} | 시리얼: {serial_number}")
                    logger.info(f"Device {i}: ID={device_id}, Name={device_name}, Serial={serial_number}")
                
                return computers
                
            elif response.status_code == 404:
                print(f"❌ 스마트 그룹 ID {group_id}를 찾을 수 없습니다.")
                logger.error(f"Smart group ID {group_id} not found")
                return []
            else:
                print(f"❌ 스마트 그룹 조회 실패 - HTTP {response.status_code}")
                print(f"   오류 메시지: {response.text}")
                logger.error(f"Failed to get smart group - HTTP {response.status_code}: {response.text}")
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 스마트 그룹 조회 중 네트워크 오류: {e}")
            logger.error(f"Network error while fetching smart group: {e}")
            return []
        except Exception as e:
            print(f"❌ 스마트 그룹 조회 중 예상치 못한 오류: {e}")
            logger.error(f"Unexpected error while fetching smart group: {e}")
            return []
    
    def get_device_details(self, device_id: int) -> Optional[Dict]:
        """
        특정 디바이스의 상세 정보를 조회
        
        Args:
            device_id (int): 디바이스 ID
            
        Returns:
            Optional[Dict]: 디바이스 상세 정보 또는 None
        """
        print(f"🔍 디바이스 ID {device_id}의 상세 정보를 조회합니다...")
        logger.info(f"Fetching details for device ID: {device_id}")
        
        device_url = f"{self.server_url}/JSSResource/computers/id/{device_id}"
        
        try:
            response = self.session.get(device_url, timeout=30)
            
            if response.status_code == 200:
                device_data = response.json()
                computer = device_data.get('computer', {})
                
                general = computer.get('general', {})
                last_contact = general.get('last_contact_time_utc', 'Unknown')
                
                print(f"   ✅ 디바이스 정보 조회 성공")
                print(f"   마지막 연락: {last_contact}")
                
                logger.info(f"Device details retrieved successfully. Last contact: {last_contact}")
                return computer
            else:
                print(f"   ❌ 디바이스 정보 조회 실패 - HTTP {response.status_code}")
                logger.error(f"Failed to get device details - HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"   ❌ 디바이스 정보 조회 중 오류: {e}")
            logger.error(f"Error while fetching device details: {e}")
            return None
    
    def remove_configuration_profiles(self, device_id: int) -> bool:
        """
        디바이스에서 모든 구성 프로필을 제거
        
        Args:
            device_id (int): 디바이스 ID
            
        Returns:
            bool: 작업 성공 여부
        """
        print(f"🗑️  디바이스 ID {device_id}의 구성 프로필을 제거합니다...")
        logger.info(f"Removing configuration profiles from device ID: {device_id}")
        
        # 먼저 디바이스의 현재 구성 프로필 목록을 조회
        profiles_url = f"{self.server_url}/JSSResource/computers/id/{device_id}/subset/configuration_profiles"
        
        try:
            response = self.session.get(profiles_url, timeout=30)
            
            if response.status_code == 200:
                profiles_data = response.json()
                profiles = profiles_data.get('computer', {}).get('configuration_profiles', [])
                
                if not profiles:
                    print(f"   ℹ️  디바이스에 제거할 구성 프로필이 없습니다.")
                    logger.info(f"No configuration profiles found on device {device_id}")
                    return True
                
                print(f"   📋 총 {len(profiles)}개의 구성 프로필을 발견했습니다.")
                
                success_count = 0
                for profile in profiles:
                    profile_id = profile.get('id')
                    profile_name = profile.get('name')
                    
                    print(f"   🔄 프로필 제거 시도: {profile_name} (ID: {profile_id})")
                    
                    # 구성 프로필 제거 명령 전송
                    remove_url = f"{self.server_url}/JSSResource/computercommands/command/UnmanageDevice/id/{device_id}"
                    
                    try:
                        remove_response = self.session.post(remove_url, timeout=30)
                        
                        if remove_response.status_code in [200, 201]:
                            print(f"   ✅ 프로필 제거 명령 전송 성공: {profile_name}")
                            success_count += 1
                        else:
                            print(f"   ❌ 프로필 제거 명령 전송 실패: {profile_name} - HTTP {remove_response.status_code}")
                            
                    except Exception as e:
                        print(f"   ❌ 프로필 제거 중 오류: {profile_name} - {e}")
                        logger.error(f"Error removing profile {profile_name}: {e}")
                
                success_rate = (success_count / len(profiles)) * 100
                print(f"   📊 구성 프로필 제거 완료: {success_count}/{len(profiles)} ({success_rate:.1f}%)")
                logger.info(f"Configuration profile removal completed: {success_count}/{len(profiles)} profiles")
                
                return success_count > 0
            else:
                print(f"   ❌ 구성 프로필 목록 조회 실패 - HTTP {response.status_code}")
                logger.error(f"Failed to get configuration profiles - HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ 구성 프로필 제거 중 오류: {e}")
            logger.error(f"Error during configuration profile removal: {e}")
            return False
    
    def revoke_device_management(self, device_id: int) -> bool:
        """
        디바이스 관리 해제 (Unmanage Device)
        
        Args:
            device_id (int): 디바이스 ID
            
        Returns:
            bool: 작업 성공 여부
        """
        print(f"🚫 디바이스 ID {device_id}의 관리를 해제합니다...")
        logger.info(f"Unmanaging device ID: {device_id}")
        
        unmanage_url = f"{self.server_url}/JSSResource/computercommands/command/UnmanageDevice/id/{device_id}"
        
        try:
            response = self.session.post(unmanage_url, timeout=30)
            
            if response.status_code in [200, 201]:
                print(f"   ✅ 디바이스 관리 해제 명령 전송 성공")
                logger.info(f"Device {device_id} unmanage command sent successfully")
                return True
            else:
                print(f"   ❌ 디바이스 관리 해제 실패 - HTTP {response.status_code}")
                print(f"   오류 메시지: {response.text}")
                logger.error(f"Failed to unmanage device - HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ 디바이스 관리 해제 중 오류: {e}")
            logger.error(f"Error during device unmanagement: {e}")
            return False
    
    def process_inactive_devices(self, group_id: int, action: str = "both") -> Dict[str, int]:
        """
        비활성 디바이스들에 대한 처리 작업을 수행
        
        Args:
            group_id (int): 스마트 그룹 ID
            action (str): 수행할 작업 ("profiles", "unmanage", "both")
            
        Returns:
            Dict[str, int]: 처리 결과 통계
        """
        print(f"\n🚀 비활성 디바이스 처리 작업을 시작합니다...")
        print(f"   스마트 그룹 ID: {group_id}")
        print(f"   수행 작업: {action}")
        print("=" * 80)
        
        logger.info(f"Starting inactive device processing for group {group_id} with action: {action}")
        
        # 통계 초기화
        stats = {
            "total_devices": 0,
            "profiles_removed": 0,
            "devices_unmanaged": 0,
            "failed_operations": 0
        }
        
        # 스마트 그룹 멤버 조회
        devices = self.get_smart_group_members(group_id)
        
        if not devices:
            print("❌ 처리할 디바이스가 없습니다.")
            return stats
        
        stats["total_devices"] = len(devices)
        
        print(f"\n📋 총 {len(devices)}대의 디바이스를 처리합니다...\n")
        
        # 각 디바이스 처리
        for i, device in enumerate(devices, 1):
            device_id = device.get('id')
            device_name = device.get('name')
            serial_number = device.get('serial_number')
            
            print(f"🔄 [{i:3d}/{len(devices)}] 처리 중: {device_name} (Serial: {serial_number})")
            print(f"    디바이스 ID: {device_id}")
            
            try:
                # 구성 프로필 제거
                if action in ["profiles", "both"]:
                    print(f"    📋 구성 프로필 제거 작업...")
                    if self.remove_configuration_profiles(device_id):
                        stats["profiles_removed"] += 1
                        print(f"    ✅ 구성 프로필 제거 완료")
                    else:
                        print(f"    ⚠️  구성 프로필 제거 실패")
                        stats["failed_operations"] += 1
                
                # 디바이스 관리 해제
                if action in ["unmanage", "both"]:
                    print(f"    🚫 디바이스 관리 해제 작업...")
                    if self.revoke_device_management(device_id):
                        stats["devices_unmanaged"] += 1
                        print(f"    ✅ 디바이스 관리 해제 완료")
                    else:
                        print(f"    ⚠️  디바이스 관리 해제 실패")
                        stats["failed_operations"] += 1
                
                print(f"    ✅ 디바이스 처리 완료\n")
                
                # API 부하 방지를 위한 잠시 대기
                time.sleep(1)
                
            except Exception as e:
                print(f"    ❌ 디바이스 처리 중 오류 발생: {e}")
                logger.error(f"Error processing device {device_id}: {e}")
                stats["failed_operations"] += 1
                print()
        
        # 최종 결과 출력
        print("=" * 80)
        print("📊 비활성 디바이스 처리 작업 완료!")
        print(f"   총 처리 디바이스: {stats['total_devices']}대")
        print(f"   구성 프로필 제거: {stats['profiles_removed']}대")
        print(f"   디바이스 관리 해제: {stats['devices_unmanaged']}대")
        print(f"   실패한 작업: {stats['failed_operations']}개")
        
        success_rate = ((stats['profiles_removed'] + stats['devices_unmanaged']) / 
                       (stats['total_devices'] * (2 if action == "both" else 1))) * 100
        print(f"   전체 성공률: {success_rate:.1f}%")
        print("=" * 80)
        
        logger.info(f"Processing completed. Stats: {stats}")
        
        return stats

def main():
    """메인 실행 함수"""
    print("🍎 Jamf Pro 비활성 맥북 관리 스크립트")
    print("=" * 80)
    
    # 설정값 (실제 환경에 맞게 수정하세요)
    JAMF_SERVER_URL = "https://yourcompany.jamfcloud.com"  # 실제 Jamf Pro 서버 URL로 변경
    JAMF_USERNAME = "your_username"                        # 실제 관리자 계정으로 변경
    JAMF_PASSWORD = "your_password"                        # 실제 비밀번호로 변경
    SMART_GROUP_ID = 123                                   # 1년 이상 비활성 맥북 스마트 그룹 ID
    
    # 수행할 작업 선택
    # "profiles" - 구성 프로필만 제거
    # "unmanage" - 디바이스 관리만 해제
    # "both" - 구성 프로필 제거 + 디바이스 관리 해제
    ACTION = "both"
    
    print("⚙️  설정 정보:")
    print(f"   Jamf Pro 서버: {JAMF_SERVER_URL}")
    print(f"   사용자명: {JAMF_USERNAME}")
    print(f"   스마트 그룹 ID: {SMART_GROUP_ID}")
    print(f"   수행 작업: {ACTION}")
    print()
    
    # 경고 메시지
    print("⚠️  주의사항:")
    print("   이 스크립트는 비활성 디바이스의 관리를 해제하고 구성 프로필을 제거합니다.")
    print("   실행 전에 반드시 설정값을 확인하고, 테스트 환경에서 먼저 실행해보세요.")
    print()
    
    # 사용자 확인 (실제 운영 환경에서는 주석 해제)
    # user_input = input("계속 진행하시겠습니까? (yes/no): ")
    # if user_input.lower() != 'yes':
    #     print("작업이 취소되었습니다.")
    #     return
    
    try:
        # Jamf Pro Manager 인스턴스 생성
        jamf_manager = JamfProManager(JAMF_SERVER_URL, JAMF_USERNAME, JAMF_PASSWORD)
        
        # API 인증
        if not jamf_manager.authenticate():
            print("❌ API 인증에 실패했습니다. 스크립트를 종료합니다.")
            return
        
        # 비활성 디바이스 처리 실행
        results = jamf_manager.process_inactive_devices(SMART_GROUP_ID, ACTION)
        
        # 최종 결과 로깅
        logger.info(f"Script execution completed with results: {results}")
        
        print("\n🎉 스크립트 실행이 완료되었습니다!")
        print("   자세한 로그는 'jamf_macbook_manager.log' 파일을 확인하세요.")
        
    except KeyboardInterrupt:
        print("\n⚠️  사용자에 의해 스크립트가 중단되었습니다.")
        logger.info("Script interrupted by user")
    except Exception as e:
        print(f"\n❌ 스크립트 실행 중 오류가 발생했습니다: {e}")
        logger.error(f"Script execution failed: {e}")
        raise

if __name__ == "__main__":
    main()