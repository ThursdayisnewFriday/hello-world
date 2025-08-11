#!/bin/bash
# 웹 인터페이스 실행 스크립트

echo "Jamf License Manager 웹 인터페이스 시작 중..."

# 가상환경 활성화
source jamf_license_env/bin/activate

# 웹 인터페이스 실행
python web_interface.py