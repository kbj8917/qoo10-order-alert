#!/usr/bin/env python3
"""Qoo10 Japan 신규 주문 알림 (텔레그램 / 디스코드)

외부 라이브러리 없이 파이썬 3.8+ 표준 라이브러리만 사용합니다.

사용법:
  python qoo10_alert.py            # 한 번 확인 (GitHub Actions용)
  python qoo10_alert.py --loop     # 계속 실행 (PC용, 기본 3분 간격)
  python qoo10_alert.py --test     # API 연결 테스트 (주문 원본 데이터 출력)
  python qoo10_alert.py --chat-id  # 텔레그램 chat_id 확인
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
