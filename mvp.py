import os
import time
import pandas as pd
import pyupbit
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import telegram  # telegram 라이브러리 import 추가

# API 키 로드
def load_api_keys():
    load_dotenv()
    access = os.getenv("API_KEY")
    secret = os.getenv("API_SECRET")
    return access, secret

# 텔레그램 봇 설정 함수 추가
def setup_telegram():
    try:
        load_dotenv()
        token = os.getenv('TELEGRAM_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not token or not chat_id:
            log_message("텔레그램 설정이 없습니다. (.env 파일의 TELEGRAM_TOKEN과 TELEGRAM_CHAT_ID를 확인하세요)")
            return None, None
            
        bot = telegram.Bot(token=token)
        log_message("텔레그램 봇 설정 완료")
        return bot, chat_id
        
    except Exception as e:
        log_message(f"텔레그램 봇 설정 실패: {str(e)}")
        return None, None

# 텔레그램 메시지 전송 함수 추가
async def send_telegram_message(bot, chat_id, message):
    if bot and chat_id:
        try:
            await bot.send_message(chat_id=chat_id, text=message)
            log_message(f"텔레그램 메시지 전송 성공: {message}")
        except Exception as e:
            log_message(f"텔레그램 메시지 전송 실패: {str(e)}")
    else:
        log_message("텔레그램 봇 또는 채팅 ID가 설정되지 않았습니다.")

# 현재 시간 로그 출력 함수
def log_message(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# 현재 시간 로그 출력 함수
def log_message(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# 거래량 증가율 계산 함수
def calculate_volume_ratio(data):
    avg_volume = data['volume'].rolling(window=20).mean().iloc[-2]
    current_volume = data['volume'].iloc[-1]
    return current_volume / avg_volume if avg_volume > 0 else 0

# 급등주 탐색 함수
def find_rising_stars(tickers, interval="minute1"):
    candidates = []
    for ticker in tickers:
        try:
            df = pyupbit.get_ohlcv(ticker, count=200, interval=interval)
            if df is None or df.empty:
                continue

            # 거래량 증가율 계산
            volume_ratio = calculate_volume_ratio(df)

            # RSI 계산
            rsi = calculate_rsi(df['close'], periods=14).iloc[-1] if len(df) >= 14 else None

            # 현재가 및 거래대금 계산
            current_price = df['close'].iloc[-1]
            trading_value = current_price * df['volume'].iloc[-1]  # 최근 거래대금

            # 거래대금에 따른 차등 조건 적용
            volume_condition = False
            rsi_condition = False

            if trading_value >= 1000000000:  # 10억원 이상
                volume_condition = volume_ratio > 3
                rsi_condition = rsi and rsi < 30
            elif trading_value >= 100000000:  # 1억원 이상
                volume_condition = volume_ratio > 4
                rsi_condition = rsi and rsi < 25
            else:  # 1억원 미만
                volume_condition = volume_ratio > 5
                rsi_condition = rsi and rsi < 20

            # 급등주 조건 확인
            if volume_condition and rsi_condition:
                candidates.append({
                    "ticker": ticker,
                    "volume_ratio": volume_ratio,
                    "rsi": rsi,
                    "current_price": current_price,
                    "trading_value": trading_value
                })
                log_message(
                    f"후보 발견: {ticker} "
                    f"(거래량 증가율: {volume_ratio:.2f}, "
                    f"RSI: {rsi:.2f}, "
                    f"거래대금: {trading_value/100000000:.1f}억)"
                )

        except Exception as e:
            log_message(f"{ticker} 데이터 분석 오류: {str(e)}")
            continue

    # 거래대금 기준으로 정렬
    candidates = sorted(candidates, key=lambda x: x['trading_value'], reverse=True)
    
    # 상위 5개만 반환
    return candidates[:5]

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
        log_message(f"[매수] {ticker}: 매수 완료. 매수 금액: {my_krw} KRW")
    else:
        log_message(f"[매수 실패] {ticker}: 잔액 부족 (보유 KRW: {my_krw})")

# 매도 함수
def handle_sell(upbit, ticker):
    my_coin = upbit.get_balance(ticker.split("-")[1])
    if my_coin > 0:
        upbit.sell_market_order(ticker, my_coin)
        log_message(f"[매도] {ticker}: 매도 완료. 매도 수량: {my_coin}")
    else:
        log_message(f"[매도 실패] {ticker}: 보유 코인 없음")

# 매도 판단 함수
def should_sell(opportunity, buy_price):
    # RSI 과매수 조건
    if opportunity['rsi'] > 70:
        log_message(f"[매도 판단] {opportunity['ticker']}: RSI 과매수 (RSI={opportunity['rsi']:.2f})")
        return True

    # 목표 수익률 도달 조건
    current_price = opportunity['current_price']
    profit_margin = (current_price - buy_price) / buy_price * 100
    if profit_margin >= 5:  # 목표 수익률 5%
        log_message(f"[매도 판단] {opportunity['ticker']}: 목표 수익률 도달 (이익률={profit_margin:.2f}%)")
        return True

    log_message(f"[매도 판단] {opportunity['ticker']}: 매도 조건 미충족 (RSI={opportunity['rsi']:.2f}, 이익률={profit_margin:.2f}%)")
    return False

# 보유 코인 정보 출력 함수
def print_owned_coins(upbit):
    balances = upbit.get_balances()
    if not balances:
        log_message("보유한 코인이 없습니다.")
        return

    for balance in balances:
        if balance['currency'] == "KRW":
            continue
        ticker = f"KRW-{balance['currency']}"
        avg_buy_price = float(balance['avg_buy_price'])
        quantity = float(balance['balance'])
        log_message(f"[보유 코인] {ticker}: 평균 매수가={avg_buy_price}, 보유량={quantity}")

# 거래 기회 분석 함수
def analyze_trading_opportunity(ticker, interval="minute1"):
    try:
        df = pyupbit.get_ohlcv(ticker, count=200, interval=interval)
        if df is None or df.empty:
            log_message(f"{ticker}: 거래 데이터 부족")
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
        log_message(f"{ticker} 데이터 분석 오류: {str(e)}")
        return None

# 자동 매매 실행 함수
def run_trading_bot():
    access, secret = load_api_keys()
    upbit = pyupbit.Upbit(access, secret)
    bot, chat_id = setup_telegram() 

    try:
        # 시작 알림 추가
        if bot and chat_id:
            asyncio.run(send_telegram_message(bot, chat_id, "자동매매 프로그램이 시작되었습니다."))

        while True:
            try:
                log_message("\n=== 자동 매매 실행 ===")
                tickers = pyupbit.get_tickers(fiat="KRW")
                if tickers is None:
                    log_message("API 호출 실패: 티커 목록을 가져올 수 없습니다.")
                    time.sleep(10)
                    continue

                # 급등주 탐색
                rising_stars = find_rising_stars(tickers, interval="minute1")

                # 추가 디버깅 로그
                if rising_stars:
                    log_message(f"[급등주 후보 리스트] {rising_stars}")
                    best_candidate = rising_stars[0]

                    # 텔레그램 알림 추가
                    if bot and chat_id:
                        alert_message = (
                            f"급등주 발견\n"
                            f"코인: {best_candidate['ticker']}\n"
                            f"거래량 증가율: {best_candidate['volume_ratio']:.2f}배\n"
                            f"RSI: {best_candidate['rsi']:.2f}\n"
                            f"거래대금: {best_candidate['trading_value']/100000000:.1f}억"
                        )
                        asyncio.run(send_telegram_message(bot, chat_id, alert_message))

                    log_message(f"[급등주 후보] 최고 매수 후보: {best_candidate}")

                    # 보유 코인 확인 및 매도 판단
                    print_owned_coins(upbit)
                    balances = upbit.get_balances()
                    for balance in balances:
                        if balance['currency'] == "KRW":
                            continue

                        ticker = f"KRW-{balance['currency']}"
                        avg_buy_price = float(balance['avg_buy_price'])
                        opportunity = analyze_trading_opportunity(ticker, interval="minute1")

                        if opportunity and should_sell(opportunity, avg_buy_price):
                            handle_sell(upbit, ticker)
                        else:
                            log_message(f"[매도 조건 미충족] {ticker}: 매도하지 않음")

                    # 매수 실행
                    if 'ticker' in best_candidate:
                        log_message(f"[매수 시도] {best_candidate['ticker']}")
                        handle_buy(upbit, best_candidate['ticker'])
                    else:
                        log_message("[오류] 매수 후보에 'ticker' 키가 없습니다.")
                else:
                    log_message("급등주 후보가 없습니다.")
                    print_owned_coins(upbit)

                time.sleep(60)  # 1분 대기

            except Exception as e:
                log_message(f"오류 발생1: {str(e)}")
                time.sleep(10)

    finally:
        # 종료 알림 추가
        if bot and chat_id:
            asyncio.run(send_telegram_message(bot, chat_id, "자동매매 프로그램이 종료되었습니다."))

if __name__ == "__main__":
    run_trading_bot()
