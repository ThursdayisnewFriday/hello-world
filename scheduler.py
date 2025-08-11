#!/usr/bin/env python3
"""
Jamf Pro License Manager - Scheduler
주기적으로 라이선스 회수 프로세스를 실행하는 스케줄러
"""

import schedule
import time
import logging
from datetime import datetime
from jamf_license_manager import JamfLicenseManager

def run_license_recovery():
    """라이선스 회수 작업 실행"""
    try:
        logging.info("스케줄된 라이선스 회수 작업 시작")
        manager = JamfLicenseManager()
        manager.run_license_recovery_process()
        logging.info("스케줄된 라이선스 회수 작업 완료")
    except Exception as e:
        logging.error(f"스케줄된 작업 실행 중 오류: {e}")

def setup_scheduler():
    """스케줄러 설정"""
    # 매일 오전 9시에 실행
    schedule.every().day.at("09:00").do(run_license_recovery)
    
    # 또는 매주 월요일 오전 9시에 실행
    # schedule.every().monday.at("09:00").do(run_license_recovery)
    
    # 또는 6시간마다 실행
    # schedule.every(6).hours.do(run_license_recovery)
    
    logging.info("스케줄러가 설정되었습니다.")
    logging.info("다음 실행 예정: " + str(schedule.next_run()))

def main():
    """메인 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('scheduler.log'),
            logging.StreamHandler()
        ]
    )
    
    setup_scheduler()
    
    print("Jamf License Manager Scheduler 시작됨")
    print("종료하려면 Ctrl+C를 누르세요")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크
    except KeyboardInterrupt:
        logging.info("스케줄러가 사용자에 의해 중단됨")
        print("\n스케줄러가 중단되었습니다.")

if __name__ == "__main__":
    main()