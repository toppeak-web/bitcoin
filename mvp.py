import os
from dotenv import load_dotenv
import json
import pandas as pd
import pyupbit
import time

def hicin_ashi():
    # 30일치 일봉데이터
    df = pyupbit.get_ohlcv("KRW-BTC", count=60, interval="minute1")
    
    # 데이터가 유효한지 확인
    if df is None or df.empty:
        print("데이터를 가져오는 데 실패했습니다.")
        return  # 데이터가 없으면 함수 종료

    # 하이킨 아시 캔들 계산 함수
    def calculate_heikin_ashi(df):
        ha_df = df.copy()
        ha_df['HA_Close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        ha_df['HA_Open'] = ha_df['HA_Close'].shift(1)  # 초기값 설정
        ha_df['HA_Open'].iloc[0] = df['open'].iloc[0]  # 첫 번째 HA_Open 설정
        ha_df['HA_High'] = ha_df[['high', 'HA_Open', 'HA_Close']].max(axis=1)
        ha_df['HA_Low'] = ha_df[['low', 'HA_Open', 'HA_Close']].min(axis=1)
        
        return ha_df

    # 하이킨 아시 데이터프레임 생성
    ha_df = calculate_heikin_ashi(df)

    # 매매 신호 생성 (가장 최근 신호만 반환)
    def generate_signals(ha_df):
        if len(ha_df) < 2:
            return "Hold"  # 데이터가 부족할 경우 기본적으로 Hold
        if ha_df['HA_Close'].iloc[-1] > ha_df['HA_Open'].iloc[-1] and ha_df['HA_Close'].iloc[-2] <= ha_df['HA_Open'].iloc[-2]:
            return "Buy"
        elif ha_df['HA_Close'].iloc[-1] < ha_df['HA_Open'].iloc[-1] and ha_df['HA_Close'].iloc[-2] >= ha_df['HA_Open'].iloc[-2]:
            return "Sell"
        else:
            return "Hold"

    load_dotenv()
    access = os.getenv("API_KEY")
    secret = os.getenv("API_SECRET")
    upbit = pyupbit.Upbit(access, secret)

    # 매매 신호 출력 (가장 최근 신호만 출력)
    signal = generate_signals(ha_df)
    print(signal)
    
    if signal.lower() == "buy":  # 대소문자 무시
        my_krw = upbit.get_balance("KRW")
        if my_krw is not None and my_krw > 0:  # 잔고가 0보다 큰지 확인
            if my_krw * 0.9995 > 5000:
                print(upbit.buy_market_order("KRW-BTC", my_krw * 0.9995))
                print("buy: 신호에 따른 매수")
            else:
                print("실패: krw 5000원 미만")
        else:
            print("실패: 잔고 없음")

    elif signal.lower() == "sell":  # 대소문자 무시
        my_btc = upbit.get_balance("KRW-BTC")
        current_price = pyupbit.get_orderbook(ticker="KRW-BTC")['orderbook_units'][0]['ask_price']
        if my_btc is not None and my_btc > 0:  # 잔고가 0보다 큰지 확인
            if my_btc * current_price > 5000:
                print(upbit.sell_market_order("KRW-BTC", my_btc))
                print("sell: 신호에 따른 매도")
            else:
                print("실패: btc 5000원 미만")
        else:
            print("실패: 잔고 없음")

    elif signal.lower() == "hold":  # 대소문자 무시
        print("hold: 신호에 따른 보유")

while True:
    hicin_ashi()
    time.sleep(60)  # 1분 간격으로 실행
