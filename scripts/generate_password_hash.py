#!/usr/bin/env python3
"""
비밀번호 해시 생성 유틸리티

사용법:
    python scripts/generate_password_hash.py [비밀번호]
    
예시:
    python scripts/generate_password_hash.py admin123
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.auth_service import get_password_hash

def main():
    if len(sys.argv) != 2:
        print("사용법: python generate_password_hash.py <비밀번호>")
        print("예시: python generate_password_hash.py admin123")
        sys.exit(1)
    
    password = sys.argv[1]
    hash_value = get_password_hash(password)
    
    print("비밀번호가 입력되었습니다.")
    print(f"해시값: {hash_value}")
    print()
    print("이 해시값을 .env 파일의 ADMIN_PASSWORD_HASH에 설정하세요:")
    print(f"ADMIN_PASSWORD_HASH={hash_value}")

if __name__ == "__main__":
    main()