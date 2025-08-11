#!/bin/bash
# 스케줄러 실행 스크립트

echo "Jamf License Manager 스케줄러 시작 중..."

# 가상환경 활성화
source jamf_license_env/bin/activate

# 스케줄러 실행
python scheduler.py