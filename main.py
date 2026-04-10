from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import yfinance as yf
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to DATCo Robo-Adviser API. Go to /api/treasury for data."}

def get_jpy_exchange_rate():
    """獲取 1 日圓等於多少美金 (JPY/USD)"""
    try:
        ticker = yf.Ticker("JPYUSD=X")
        # 優先使用 fast_info，失敗則用 info
        rate = ticker.fast_info.get('last_price') or ticker.info.get('regularMarketPrice')
        return rate if rate else 1/150
    except:
        return 1 / 150

def fetch_data_from_coingecko():
    t_url = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
    p_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    
    try:
        t_res = requests.get(t_url, timeout=10).json()
        p_res = requests.get(p_url, timeout=10).json()
        btc_price = p_res.get('bitcoin', {}).get('usd', 0)
        
        jpy_to_usd = get_jpy_exchange_rate()
        companies = t_res.get('companies', [])[:5]
        structured_data = []

        for co in companies:
            name_upper = co['name'].upper()
            yf_symbol = str(co['symbol']).upper().replace(".US", "")
            
            # 符號對應邏輯
            if "METAPLANET" in name_upper or "3350" in yf_symbol:
                yf_symbol = "3350.T"
            elif "MICROSTRATEGY" in name_upper:
                yf_symbol = "MSTR"
            elif "MARATHON" in name_upper:
                yf_symbol = "MARA"

            try:
                # 這裡會比較慢，因為 yf.info 會請求大量資料
                ticker = yf.Ticker(yf_symbol)
                info = ticker.info
                raw_mkt_cap = info.get('marketCap') or info.get('enterpriseValue') or 0
                currency = info.get('currency', 'USD')

                # 單位轉換
                mkt_cap_usd = raw_mkt_cap * jpy_to_usd if currency == 'JPY' else raw_mkt_cap
                holdings = co.get('total_holdings', 0)
                nav_usd = holdings * btc_price
                mnav = (mkt_cap_usd / nav_usd) if nav_usd > 0 else 0
                
                structured_data.append({
                    "name": co['name'],
                    "symbol": yf_symbol,
                    "holdings": holdings,
                    "value_usd": round(nav_usd, 2),
                    "mkt_cap": round(mkt_cap_usd, 2),
                    "mnav": round(mnav, 2),
                    "btc_price": btc_price,
                    "currency": currency
                })
            except Exception as e:
                print(f"Skipping {yf_symbol}: {e}")
                continue
                
        return structured_data
    except Exception as e:
        return {"error": str(e)}

def fetch_market_indicators():
    try:
        fg_url = "https://api.alternative.me/fng/"
        fg_res = requests.get(fg_url).json()
        fg_value = fg_res['data'][0]['value']
        fg_status = fg_res['data'][0]['value_classification']

        dxy = yf.Ticker("UUP")
        dxy_price = dxy.fast_info.get('last_price') or dxy.info.get('regularMarketPrice') or 100

        return {
            "fear_greed": {"value": fg_value, "status": fg_status},
            "dxy": round(dxy_price, 2)
        }
    except:
        return {"fear_greed": {"value": 50, "status": "Neutral"}, "dxy": 100}

def fetch_bitcoin_network_health():
    try:
        # 獲取算力與難度
        hashrate_gh = float(requests.get("https://blockchain.info/q/hashrate", timeout=10).text)
        difficulty = float(requests.get("https://blockchain.info/q/getdifficulty", timeout=10).text)
        total_sats = float(requests.get("https://blockchain.info/q/totalbc", timeout=10).text)
        
        # 直接使用這個精確係數行，不會再出錯
        efficiency = 16
        elec_price = 0.065
        block_reward = 3.125

        # 最終精確公式
        mining_cost_usd = (difficulty * 4294967296 * efficiency * elec_price * 1.45) / (block_reward * 3.6e18)
        
        return {
            "hashrate_eh": round(hashrate_gh / 1_000_000_000, 2),
            "difficulty": difficulty,
            "total_supply": round(total_sats / 100_000_000, 4),
            "mining_cost_usd": round(mining_cost_usd , 2)
        }
    except Exception as e:
        print(f"Network Data Error: {e}")
        return {"hashrate_eh": 0, "difficulty": 0, "total_supply": 0, "mining_cost_usd": 0}

@app.get("/api/treasury")
def get_treasury():
    return {
        "companies": fetch_data_from_coingecko(),
        "market": fetch_market_indicators(),
        "network": fetch_bitcoin_network_health()
    }

if __name__ == "__main__":
    import uvicorn
    import os
    # Render 會給一個環境變數叫做 PORT，如果沒有就預設 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)