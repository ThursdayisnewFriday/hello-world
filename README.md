# Jamf License Reclamation System

🔄 **자동화된 Mac 라이센스 회수 시스템** - Jamf Pro에서 장시간 비활성 상태인 Mac 사용자들의 라이센스를 자동으로 회수하는 시스템

## 🌟 주요 기능

- **비활성 장치 자동 감지**: 설정 가능한 임계값(기본 90일)을 기반으로 비활성 Mac 장치 감지
- **유예 기간 관리**: 라이센스 회수 전 7일간의 유예 기간 제공
- **자동 알림 시스템**: 이메일 및 Slack을 통한 실시간 알림
- **안전한 라이센스 회수**: 단계별 검증 및 롤백 가능한 회수 프로세스
- **상세한 로깅**: 모든 작업에 대한 완전한 감사 추적
- **유연한 스케줄링**: 일간/주간/월간 자동 실행
- **드라이 런 모드**: 실제 회수 없이 테스트 가능

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Jamf Pro API  │    │   License       │    │  Notification   │
│    Integration  │◄──►│  Reclamation    │◄──►│    Service      │
│                 │    │    Service      │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       ▲                       ▲
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Configuration  │    │   SQLite        │    │   Email/Slack   │
│    Manager      │    │   Database      │    │   Integration   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd jamf-license-reclamation

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 파일 생성
cp .env.example .env
```

### 2. 설정 파일 구성

```bash
# 설정 템플릿 생성
python main.py --generate-config-template

# config.ini 파일 편집
vim config.ini
```

### 3. Jamf Pro API 자격 증명 설정

`.env` 파일에 다음 정보를 입력:

```bash
JAMF_SERVER_URL=https://your-jamf-instance.jamfcloud.com
JAMF_USERNAME=your_api_username
JAMF_PASSWORD=your_api_password
# 또는 API 토큰 사용
JAMF_API_TOKEN=your_api_token
```

### 4. 이메일 알림 설정

```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USERNAME=your_email@company.com
EMAIL_PASSWORD=your_app_password
ADMIN_EMAIL=admin@company.com
```

### 5. 설정 검증

```bash
python main.py --validate-config
```

## 📖 사용법

### 기본 명령어

```bash
# 설정 검증
python main.py --validate-config

# 시스템 상태 확인
python main.py --status

# 즉시 회수 사이클 실행
python main.py --run-now

# 드라이 런 모드로 테스트
python main.py --run-now --dry-run

# 데몬으로 실행 (스케줄된 자동 실행)
python main.py --daemon

# 유예 기간 상태 확인
python main.py --grace-period-status

# 회수 기록 조회
python main.py --reclamation-history
```

### 설정 옵션

#### 라이센스 회수 설정

```ini
[LICENSE_RECLAMATION]
# 비활성 임계값 (일)
inactive_days_threshold = 90
# 유예 기간 (일)
grace_period_days = 7
# 한 번에 회수할 최대 라이센스 수
max_reclaims_per_run = 10
```

#### 스케줄 설정

```ini
[SCHEDULE]
# 실행 빈도 (daily, weekly, monthly)
run_frequency = weekly
# 실행 시간 (HH:MM 형식)
run_time = 02:00
# 실행 요일 (0=월요일, 6=일요일)
run_days = 0,3,5
```

## 🔧 고급 설정

### 시스템 서비스로 등록 (Linux)

```bash
# systemd 서비스 파일 생성
sudo tee /etc/systemd/system/jamf-license-reclamation.service > /dev/null <<EOF
[Unit]
Description=Jamf License Reclamation Service
After=network.target

[Service]
Type=simple
User=jamf-service
WorkingDirectory=/opt/jamf-license-reclamation
ExecStart=/usr/bin/python3 /opt/jamf-license-reclamation/main.py --daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 서비스 활성화 및 시작
sudo systemctl enable jamf-license-reclamation
sudo systemctl start jamf-license-reclamation
```

### 로그 순환 설정

```bash
# logrotate 설정
sudo tee /etc/logrotate.d/jamf-license-reclamation > /dev/null <<EOF
/var/log/jamf-license-reclamation/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 jamf-service jamf-service
}
EOF
```

## 📊 모니터링 및 알림

### 이메일 알림

시스템은 다음 상황에서 자동으로 이메일을 발송합니다:

- **유예 기간 시작**: 비활성 장치가 유예 기간에 진입할 때
- **라이센스 회수 완료**: 라이센스가 성공적으로 회수되었을 때
- **오류 발생**: 시스템 오류가 발생했을 때

### Slack 통합

Slack 웹훅을 설정하여 실시간 알림을 받을 수 있습니다:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
```

### 로그 모니터링

```bash
# 실시간 로그 모니터링
tail -f jamf_license_reclamation.log

# 최근 오류 확인
grep ERROR jamf_license_reclamation.log | tail -10
```

## 🔒 보안 고려사항

### API 자격 증명 보호

- `.env` 파일 권한을 제한적으로 설정 (`chmod 600 .env`)
- API 토큰을 사용하는 경우 정기적으로 순환
- 최소 권한 원칙에 따라 Jamf API 권한 설정

### 데이터베이스 보안

- SQLite 데이터베이스 파일 접근 권한 제한
- 정기적인 백업 수행
- 개인정보가 포함된 로그의 적절한 관리

## 🔍 문제 해결

### 일반적인 문제

#### 1. Jamf API 연결 실패

```bash
# 연결 테스트
curl -u "username:password" "https://your-jamf.com/JSSResource/computers"

# 설정 확인
python main.py --validate-config
```

#### 2. 이메일 발송 실패

```bash
# SMTP 설정 확인
python -c "
import smtplib
server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('your_email', 'your_password')
print('SMTP connection successful')
server.quit()
"
```

#### 3. 권한 오류

```bash
# 파일 권한 확인
ls -la jamf_license_reclamation.log
ls -la license_reclamation.db

# 권한 수정
chmod 644 jamf_license_reclamation.log
chmod 644 license_reclamation.db
```

### 로그 레벨 조정

```bash
# 디버그 모드로 실행
python main.py --run-now --log-level DEBUG
```

## 📈 성능 최적화

### 대규모 환경 최적화

- `max_reclaims_per_run` 설정으로 한 번에 처리할 장치 수 제한
- 피크 시간을 피해 스케줄 설정
- 데이터베이스 정기 정리 (`cleanup_old_records`)

### 네트워크 최적화

- API 호출 수를 최소화하기 위한 배치 처리
- 재시도 로직으로 일시적 네트워크 오류 처리

## 🤝 기여하기

1. 저장소 포크
2. 기능 브랜치 생성 (`git checkout -b feature/amazing-feature`)
3. 변경사항 커밋 (`git commit -m 'Add amazing feature'`)
4. 브랜치에 푸시 (`git push origin feature/amazing-feature`)
5. Pull Request 생성

## 📝 라이센스

이 프로젝트는 MIT 라이센스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 🙋‍♂️ 지원

- **문서**: 이 README 파일과 코드 내 주석 참조
- **이슈 리포팅**: GitHub Issues를 통해 버그 신고 및 기능 요청
- **토론**: GitHub Discussions에서 질문 및 토론

## 📋 체크리스트

### 초기 설정 체크리스트

- [ ] Python 3.7+ 설치 확인
- [ ] 의존성 패키지 설치
- [ ] Jamf Pro API 자격 증명 설정
- [ ] 이메일 SMTP 설정 구성
- [ ] 설정 파일 검증 완료
- [ ] 테스트 실행 (드라이 런 모드)
- [ ] 프로덕션 스케줄 설정
- [ ] 모니터링 및 알림 테스트

### 운영 체크리스트

- [ ] 일일 로그 검토
- [ ] 주간 시스템 상태 확인
- [ ] 월간 설정 검토
- [ ] 분기별 API 자격 증명 순환
- [ ] 반기별 재해 복구 테스트

---

**🎯 목표**: Jamf Pro 환경에서 효율적이고 안전한 라이센스 관리를 통해 비용 최적화와 보안 강화를 동시에 달성
