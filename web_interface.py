#!/usr/bin/env python3
"""
Jamf Pro License Manager - Web Interface
사용자가 이메일 링크를 통해 라이선스 회수를 확인할 수 있는 웹 인터페이스
"""

from flask import Flask, request, render_template_string, redirect, url_for
import sqlite3
from datetime import datetime
import hashlib
import logging

app = Flask(__name__)

# HTML 템플릿
CONFIRMATION_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jamf Pro 라이선스 확인</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 600px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f5f5f7;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        h1 {
            color: #1d1d1f;
            margin-bottom: 20px;
        }
        .device-info {
            background: #f6f6f6;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }
        .button {
            display: inline-block;
            padding: 12px 24px;
            margin: 10px 10px 10px 0;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            text-align: center;
            min-width: 120px;
        }
        .keep {
            background-color: #007AFF;
            color: white;
        }
        .remove {
            background-color: #FF3B30;
            color: white;
        }
        .keep:hover {
            background-color: #0056CC;
        }
        .remove:hover {
            background-color: #D70015;
        }
        .success {
            background-color: #30D158;
            color: white;
            padding: 15px;
            border-radius: 6px;
            margin: 20px 0;
        }
        .error {
            background-color: #FF3B30;
            color: white;
            padding: 15px;
            border-radius: 6px;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        {% if message %}
            <div class="{{ message_type }}">{{ message }}</div>
        {% endif %}
        
        {% if device %}
            <h1>디바이스 라이선스 확인</h1>
            <p>안녕하세요 {{ device.username }}님,</p>
            <p>아래 디바이스에 대한 Jamf Pro 라이선스 처리를 확인해주세요:</p>
            
            <div class="device-info">
                <strong>컴퓨터 이름:</strong> {{ device.computer_name }}<br>
                <strong>사용자:</strong> {{ device.username }}<br>
                <strong>마지막 체크인:</strong> {{ device.last_checkin }}<br>
            </div>
            
            <p>이 디바이스를 계속 사용하시나요?</p>
            
            <a href="{{ url_for('process_response', device_id=device.device_id, token=token, action='keep') }}" 
               class="button keep">계속 사용</a>
            <a href="{{ url_for('process_response', device_id=device.device_id, token=token, action='remove') }}" 
               class="button remove">사용 안함 (라이선스 회수)</a>
               
            <p><small>이 확인은 보안을 위해 토큰이 유효한 동안만 가능합니다.</small></p>
        {% endif %}
    </div>
</body>
</html>
"""

def verify_token(device_id: str, token: str) -> bool:
    """토큰 유효성 검증"""
    expected_token = hashlib.md5(f"{device_id}{datetime.now().strftime('%Y%m%d')}".encode()).hexdigest()
    return token == expected_token

def get_device_info(device_id: str) -> dict:
    """데이터베이스에서 디바이스 정보 조회"""
    conn = sqlite3.connect('license_manager.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT device_id, computer_name, username, email, last_checkin 
        FROM user_confirmations 
        WHERE device_id = ?
    ''', (device_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'device_id': result[0],
            'computer_name': result[1],
            'username': result[2],
            'email': result[3],
            'last_checkin': result[4]
        }
    return None

def update_user_response(device_id: str, action: str):
    """사용자 응답을 데이터베이스에 기록"""
    conn = sqlite3.connect('license_manager.db')
    cursor = conn.cursor()
    
    response_text = "계속 사용" if action == "keep" else "라이선스 회수 동의"
    
    cursor.execute('''
        UPDATE user_confirmations 
        SET user_response = ?, response_date = ?
        WHERE device_id = ?
    ''', (response_text, datetime.now().isoformat(), device_id))
    
    conn.commit()
    conn.close()

@app.route('/confirm')
def confirm():
    """확인 페이지"""
    device_id = request.args.get('device_id')
    token = request.args.get('token')
    
    if not device_id or not token:
        return render_template_string(CONFIRMATION_TEMPLATE, 
                                    message="잘못된 요청입니다.", 
                                    message_type="error")
    
    if not verify_token(device_id, token):
        return render_template_string(CONFIRMATION_TEMPLATE, 
                                    message="유효하지 않은 토큰입니다.", 
                                    message_type="error")
    
    device = get_device_info(device_id)
    if not device:
        return render_template_string(CONFIRMATION_TEMPLATE, 
                                    message="디바이스 정보를 찾을 수 없습니다.", 
                                    message_type="error")
    
    return render_template_string(CONFIRMATION_TEMPLATE, 
                                device=device, 
                                token=token)

@app.route('/process')
def process_response():
    """사용자 응답 처리"""
    device_id = request.args.get('device_id')
    token = request.args.get('token')
    action = request.args.get('action')
    
    if not all([device_id, token, action]):
        return render_template_string(CONFIRMATION_TEMPLATE, 
                                    message="잘못된 요청입니다.", 
                                    message_type="error")
    
    if not verify_token(device_id, token):
        return render_template_string(CONFIRMATION_TEMPLATE, 
                                    message="유효하지 않은 토큰입니다.", 
                                    message_type="error")
    
    if action not in ['keep', 'remove']:
        return render_template_string(CONFIRMATION_TEMPLATE, 
                                    message="잘못된 액션입니다.", 
                                    message_type="error")
    
    # 사용자 응답 기록
    update_user_response(device_id, action)
    
    # 라이선스 회수 액션인 경우
    if action == 'remove':
        # 여기서 실제 라이선스 회수를 트리거할 수 있습니다
        # 또는 별도의 배치 작업에서 처리하도록 플래그만 설정
        message = "라이선스 회수에 동의해주셔서 감사합니다. 곧 처리될 예정입니다."
        logging.info(f"사용자가 라이선스 회수에 동의: 디바이스 ID {device_id}")
    else:
        message = "계속 사용하신다는 것을 확인했습니다. 라이선스가 유지됩니다."
        logging.info(f"사용자가 디바이스 계속 사용 선택: 디바이스 ID {device_id}")
    
    return render_template_string(CONFIRMATION_TEMPLATE, 
                                message=message, 
                                message_type="success")

@app.route('/status')
def status():
    """시스템 상태 확인"""
    conn = sqlite3.connect('license_manager.db')
    cursor = conn.cursor()
    
    # 통계 조회
    cursor.execute('SELECT COUNT(*) FROM user_confirmations')
    total_notifications = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM user_confirmations WHERE user_response IS NOT NULL')
    responded = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM user_confirmations WHERE license_recovered IS NOT NULL')
    recovered = cursor.fetchone()[0]
    
    conn.close()
    
    status_html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>Jamf License Manager 상태</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 50px; }}
            .stats {{ background: #f6f6f6; padding: 20px; border-radius: 8px; }}
        </style>
    </head>
    <body>
        <h1>Jamf License Manager 상태</h1>
        <div class="stats">
            <h3>통계</h3>
            <p><strong>총 알림 발송:</strong> {total_notifications}</p>
            <p><strong>사용자 응답:</strong> {responded}</p>
            <p><strong>라이선스 회수:</strong> {recovered}</p>
            <p><strong>응답률:</strong> {(responded/total_notifications*100 if total_notifications > 0 else 0):.1f}%</p>
        </div>
    </body>
    </html>
    """
    
    return status_html

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=5000, debug=True)