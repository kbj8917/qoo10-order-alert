#!/usr/bin/env python3
"""Qoo10 Japan 신규 주문 알림 (텔레그램 / 디스코드)"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_BASE = "https://api.qoo10.jp/GMKT.INC.Front.QAPIService/ebayjapan.qapi"
JST = timezone(timedelta(hours=9))

# ShippingStat: 1=배송대기 2=배송요청(신규 결제완료) 3=발송확인 4=배송중 5=배송완료
STATUS_NAMES = {"1": "배송대기", "2": "배송요청(신규)", "3": "발송확인", "4": "배송중", "5": "배송완료"}


def env(name, default=""
