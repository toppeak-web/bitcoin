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


# RSI 계산 함수
def calculate_rsi(data, periods=14):
    if len(data) < periods:
        return pd.Series([None] * len(data))  # NaN 반환
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss.replace(0, float('inf'))
    return 100 - (100 / (1 + rs))


# 수익성 점수 계산 함수
def calculate_profitability_score(ticker, interval="minute5"):
    try:
        for attempt in range(3):  # 3회 재시도
            df = pyupbit.get_ohlcv(ticker, count=200, interval=interval)
            if df is not None and not df.empty:
                break
            time.sleep(1)  # 잠시 대기 후 재시도
        else:
            print(f"{ticker}: 데이터를 가져오지 못했습니다.")
            return 0, []

        # NaN 값 점검
        if df.isna().any().any():
            print(f"{ticker}: 데이터에 NaN 값이 있습니다.")
            return 0, []

        score = 0
        score_logs = []

        # 1. RSI 점수
        rsi = calculate_rsi(df['close'], periods=14).iloc[-1]
        if pd.isna(rsi):
            print(f"{ticker}: RSI 계산 실패")
            return 0, []
        if rsi < 30:
            score += 25
            score_logs.append("RSI: +25")
        elif rsi > 70:
            score -= 15
            score_logs.append("RSI: -15")
        else:
            score += 10
            score_logs.append("RSI: +10")

        # 2. MACD 점수
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - signal

        if macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0:
            score += 20
            score_logs.append("MACD: +20")
        elif macd_hist.iloc[-1] < 0 and macd_hist.iloc[-2] >= 0:
            score -= 15
            score_logs.append("MACD: -15")
        else:
            score_logs.append("MACD: 0")

        # 3. 볼린저 밴드 점수
        ma20 = df['close'].rolling(window=20).mean()
        std = df['close'].rolling(window=20).std()
        upper = ma20 + 2 * std
        lower = ma20 - 2 * std
        current_price = df['close'].iloc[-1]

        bb_position = (current_price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])
        if bb_position < 0.2:
            score += 15
            score_logs.append("BB: +15")
        elif bb_position > 0.8:
            score -= 10
            score_logs.append("BB: -10")
        else:
            score_logs.append("BB: 0")

        # 4. 이동평균선 점수
        ma5 = df['close'].rolling(window=5).mean()
        if ma5.iloc[-1] > ma20.iloc[-1]:
            score += 15
            score_logs.append("이평선: +15")
        else:
            score -= 10
            score_logs.append("이평선: -10")

        final_score = max(0, min(100, score))
        return final_score, score_logs

    except Exception as e:
        print(f"점수 계산 오류: {str(e)}")
        return 0, []


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


# 자동 매매 실행 함수
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

            # 보유 코인 점수 확인
            balances = upbit.get_balances()
            owned_coins = ["KRW-" + balance['currency'] for balance in balances if float(balance['balance']) > 0 and balance['currency'] != "KRW"]

            best_score = 0
            best_ticker = None
            best_logs = []

            # 전체 코인 점수 계산
            for ticker in tickers:
                score, logs = calculate_profitability_score(ticker)
                print(f"{ticker} 점수: {score} | 로그: {logs}")

                if score > best_score:
                    best_score = score
                    best_ticker = ticker
                    best_logs = logs

            print(f"\n최고 점수 코인: {best_ticker} | 점수: {best_score} | 로그: {best_logs}")

            # 보유 코인 점수 확인 및 매도 판단
            for coin in owned_coins:
                coin_score, coin_logs = calculate_profitability_score(coin)
                print(f"보유 코인 {coin} 점수: {coin_score} | 로그: {coin_logs}")

                # 매도 조건: 점수가 20 이하이거나 최고 점수 코인이 10점 더 높은 경우
                if coin_score <= 20 or (best_score - coin_score >= 10):
                    print(f"{coin} 매도 결정")
                    handle_sell(upbit, coin)

            # 최고 점수 코인 매수
            if best_ticker and best_score >= 45:
                handle_buy(upbit, best_ticker)

            time.sleep(300)  # 5분 대기

        except Exception as e:
            print(f"오류 발생: {str(e)}")
            time.sleep(10)


if __name__ == "__main__":
    run_trading_bot()
