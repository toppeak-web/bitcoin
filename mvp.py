import os
import time
import pandas as pd
import pyupbit
from dotenv import load_dotenv

# API 키 로드
def load_api_keys():
    load_dotenv()
    access = os.getenv("API_KEY")
    secret = os.getenv("API_SECRET")
    return access, secret

# 거래량 증가율 계산 함수
def calculate_volume_ratio(data):
    avg_volume = data['volume'].rolling(window=20).mean().iloc[-2]
    current_volume = data['volume'].iloc[-1]
    return current_volume / avg_volume if avg_volume > 0 else 0

# 거래량 기반 매수/매도 판단 함수
def analyze_trading_opportunity(ticker, interval="minute1"):
    try:
        for attempt in range(3):  # 최대 3회 재시도
            df = pyupbit.get_ohlcv(ticker, count=200, interval=interval)
            if df is not None and not df.empty:
                break
            time.sleep(1)  # 재시도 전 대기
        else:
            print(f"{ticker}: 데이터를 가져오지 못했습니다.")
            return None

        # 거래량 증가율 계산
        volume_ratio = calculate_volume_ratio(df)

        # RSI 계산
        rsi = calculate_rsi(df['close'], periods=14).iloc[-1] if len(df) >= 14 else None

        return {
            "volume_ratio": volume_ratio,
            "rsi": rsi,
            "current_price": df['close'].iloc[-1]
        }

    except Exception as e:
        print(f"{ticker} 데이터 분석 오류: {str(e)}")
        return None

# RSI 계산 함수
def calculate_rsi(data, periods=14):
    if len(data) < periods:
        return pd.Series([None] * len(data))  # NaN 반환
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss.replace(0, float('inf'))
    return 100 - (100 / (1 + rs))

# 매수 함수
def handle_buy(upbit, ticker):
    my_krw = upbit.get_balance("KRW")
    if my_krw > 5000:
        upbit.buy_market_order(ticker, my_krw * 0.9995)
        print(f"{ticker} 매수 완료")

# 매도 함수
def handle_sell(upbit, ticker):
    my_coin = upbit.get_balance(ticker.split("-")[1])
    if my_coin > 0:
        upbit.sell_market_order(ticker, my_coin)
        print(f"{ticker} 매도 완료")

# 매도/매수 최소 조건
MIN_PROFIT_MARGIN = 0.06  # 수수료 보전 후 최소 이익률 (0.06 = 6% 설정)

# 예상 수익률 계산
def calculate_expected_profit(buy_price, current_price):
    return (current_price - buy_price) / buy_price * 100

# 매도 판단 함수
def should_sell(coin_opportunity, best_opportunity, buy_price):
    # 1. RSI 과매수 조건
    if coin_opportunity['rsi'] and coin_opportunity['rsi'] > 70:
        print(f"매도 결정: RSI 과매수 (RSI={coin_opportunity['rsi']:.2f})")
        return True

    # 2. 거래량 급증 비교
    if best_opportunity['volume_ratio'] > coin_opportunity['volume_ratio'] * 1.5:
        print(f"매도 결정: 거래량 급증 기회 비교")
        return True

    # 3. 수익률 판단
    current_price = coin_opportunity['current_price']
    profit_margin = calculate_expected_profit(buy_price, current_price)
    if profit_margin >= MIN_PROFIT_MARGIN:
        print(f"매도 결정: 예상 수익률 만족 (이익률={profit_margin:.2f}%)")
        return True

    return False

# 수정된 run_trading_bot
def run_trading_bot():
    access, secret = load_api_keys()
    upbit = pyupbit.Upbit(access, secret)

    while True:
        try:
            print("\n=== 자동 매매 실행 ===")
            tickers = pyupbit.get_tickers(fiat="KRW")
            if tickers is None:
                print("API 호출 실패: 티커 목록을 가져올 수 없습니다.")
                time.sleep(10)
                continue

            best_ticker = None
            best_opportunity = None

            # 보유 코인 확인 및 매수 가격 기록
            balances = upbit.get_balances()
            owned_coins = {
                "KRW-" + balance['currency']: float(balance['avg_buy_price'])
                for balance in balances if float(balance['balance']) > 0 and balance['currency'] != "KRW"
            }

            # 전체 코인 분석
            for ticker in tickers:
                opportunity = analyze_trading_opportunity(ticker, interval="minute1")
                if not opportunity:
                    continue

                print(f"{ticker} 분석 결과: {opportunity}")

                # 매수 기회 판단
                if opportunity['volume_ratio'] > 3 and opportunity['rsi'] and opportunity['rsi'] < 20:
                    if not best_opportunity or opportunity['volume_ratio'] > best_opportunity['volume_ratio']:
                        best_ticker = ticker
                        best_opportunity = opportunity

            # 매도/매수 실행
            if best_ticker and best_opportunity:
                print(f"최고 매수 후보: {best_ticker} | 분석: {best_opportunity}")

                # 보유 코인 매도 판단
                for coin, buy_price in owned_coins.items():
                    coin_opportunity = analyze_trading_opportunity(coin, interval="minute1")
                    if not coin_opportunity:
                        continue

                    print(f"보유 코인 {coin} 분석 결과: {coin_opportunity}")

                    if should_sell(coin_opportunity, best_opportunity, buy_price):
                        handle_sell(upbit, coin)

                # 매수 실행
                handle_buy(upbit, best_ticker)

            # 보유 중인 코인 정보 출력
            if owned_coins:
                print("현재 보유 중인 코인:")
                for coin, buy_price in owned_coins.items():
                    print(f"{coin}: 매수 가격 {buy_price:.2f} 원")
            else:
                print("보유 중인 코인이 없습니다.")

            time.sleep(60)  # 1분 대기

        except Exception as e:
            print(f"오류 발생: {str(e)}")
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
