import os
import time
import pandas as pd
import pyupbit
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import telegram

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
            async with bot:
                await bot.send_message(chat_id=chat_id, text=message)
            log_message(f"텔레그램 메시지 전송 성공: {message}")
        except Exception as e:
            log_message(f"텔레그램 메시지 전송 실패: {str(e)}")
    else:
        log_message("텔레그램 봇 또는 채팅 ID가 설정되지 않았습니다.")

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
            # BTC와 ETH 제외
            if ticker in ["KRW-BTC", "KRW-ETH"]:
                continue

            df = pyupbit.get_ohlcv(ticker, count=200, interval=interval)
            if df is None or df.empty:
                continue

            # 거래량 증가율 계산
            volume_ratio = calculate_volume_ratio(df)

            # RSI 계산
            rsi = calculate_rsi(df['close'], periods=14).iloc[-1] if len(df) >= 14 else None

            # 현재가 및 거래대금 계산
            current_price = df['close'].iloc[-1]
            trading_value = current_price * df['volume'].iloc[-1]

            # 거래대금에 따른 차등 조건 적용
            if trading_value >= 1000000000 and volume_ratio > 2 and rsi and rsi < 30:
                candidates.append({
                    "ticker": ticker,
                    "volume_ratio": volume_ratio,
                    "rsi": rsi,
                    "current_price": current_price,
                    "trading_value": trading_value
                })
                log_message(f"후보 발견: {ticker} (거래량 증가율: {volume_ratio:.2f}, RSI: {rsi:.2f}, 거래대금: {trading_value/100000000:.1f}억)")

        except Exception as e:
            log_message(f"{ticker} 데이터 분석 오류: {str(e)}")
            continue

    return sorted(candidates, key=lambda x: x['trading_value'], reverse=True)[:5]

# RSI 계산 함수
def calculate_rsi(data, periods=14):
    if len(data) < periods:
        return pd.Series([None] * len(data))
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

def trade_rising_star(upbit, rising_star, balances):
    """
    급등주 후보와 보유 코인을 비교하고 매매 결정
    """
    try:
        rising_ticker = rising_star['ticker']
        rising_price = rising_star['current_price']

        log_message(f"[급등주] {rising_ticker}: 가격={rising_price}, 강제 매수 진행")
        log_message("[보유 코인 정보]")

        # 모든 보유 코인 매도
        for balance in balances:
            if balance['currency'] == "KRW":  # 현금 잔액은 제외
                continue

            ticker = f"KRW-{balance['currency']}"
            avg_buy_price = float(balance['avg_buy_price'])
            quantity = float(balance['balance'])
            log_message(f"{ticker}: 보유량={quantity}")

            # 동일 코인 매도 방지
            if ticker == rising_ticker:
                log_message(f"[매도 생략] {ticker}: 동일 코인 보유 중")
                continue

            if quantity > 0:
                log_message(f"[매도 실행] {ticker}: 보유량={quantity}")
                handle_sell(upbit, ticker)

        # 급등주 매수
        log_message(f"[매수 실행] {rising_ticker}")
        handle_buy(upbit, rising_ticker)

    except Exception as e:
        log_message(f"[오류] 거래 로직 중 오류 발생: {str(e)}")

    return False
# 자동 매매 실행
def run_trading_bot():
    access, secret = load_api_keys()
    upbit = pyupbit.Upbit(access, secret)
    bot, chat_id = setup_telegram()

    try:
        asyncio.run(send_telegram_message(bot, chat_id, "자동매매 프로그램이 시작되었습니다."))

        while True:
            tickers = pyupbit.get_tickers(fiat="KRW")
            rising_stars = find_rising_stars(tickers)

            if rising_stars:
                log_message(f"[급등주 후보 리스트] {rising_stars}")
                best_candidate = rising_stars[0]
                balances = upbit.get_balances()
                trade_rising_star(upbit, best_candidate, balances)

                # 텔레그램 메시지 전송
                if bot and chat_id:
                    try:
                        alert_message = (
                            f"급등주 발견\n"
                            f"코인: {best_candidate['ticker']}\n"
                            f"거래량 증가율: {best_candidate['volume_ratio']:.2f}배\n"
                            f"RSI: {best_candidate['rsi']:.2f}\n"
                            f"거래대금: {best_candidate['trading_value']/100000000:.1f}억"
                        )
                        asyncio.run(send_telegram_message(bot, chat_id, alert_message))
                    except Exception as e:
                        log_message(f"[텔레그램 오류] 메시지 전송 실패: {str(e)}")
            else:
                # 급등주가 없을 경우 보유 코인 정보 출력
                log_message("[급등주 후보 없음]")
                balances = upbit.get_balances()
                log_message("[보유 코인 정보]")
                for balance in balances:
                    if balance['currency'] == "KRW":  # 현금 잔액은 제외
                        continue
                    ticker = f"KRW-{balance['currency']}"
                    quantity = float(balance['balance'])
                    log_message(f"{ticker}: 보유량={quantity}")

            time.sleep(60)

    except Exception as e:
        log_message(f"[오류] {str(e)}")
    finally:
        # 종료 알림 추가
        if bot and chat_id:
            asyncio.run(send_telegram_message(bot, chat_id, "자동매매 프로그램이 종료되었습니다."))

if __name__ == "__main__":
    run_trading_bot()
