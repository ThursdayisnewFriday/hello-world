#!/bin/bash
# Jamf Pro License Manager 설치 스크립트

echo "=== Jamf Pro License Manager 설치 시작 ==="

# Python 가상환경 생성
echo "Python 가상환경 생성 중..."
python3 -m venv jamf_license_env
source jamf_license_env/bin/activate

# 패키지 설치
echo "필요한 패키지 설치 중..."
pip install --upgrade pip
pip install -r requirements.txt

# 실행 권한 부여
echo "실행 권한 설정 중..."
chmod +x jamf_license_manager.py
chmod +x web_interface.py
chmod +x scheduler.py

# 설정 파일 백업 생성
echo "설정 파일 백업 생성 중..."
if [ -f "config.json" ]; then
    cp config.json config.json.example
fi

# 로그 디렉토리 생성
echo "로그 디렉토리 생성 중..."
mkdir -p logs

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "다음 단계:"
echo "1. config.json 파일을 편집하여 Jamf Pro 서버 정보와 이메일 설정을 입력하세요"
echo "2. 웹 인터페이스 실행: python web_interface.py"
echo "3. 스케줄러 실행: python scheduler.py"
echo "4. 수동 실행: python jamf_license_manager.py"
echo ""
echo "참고: config.json.example 파일을 참조하여 설정하세요"