# Steam Market Flipper
This is a scraper that compares item prices from steam and third party markets

## Usage:

### Step one
install prerequisite packages from requirements.txt
```
"""in console"""
pip install -r requirements.txt
```

### First way
modify and run Scraper.py main() function

### Second way
```
from Scraper import SteamMarket, PriceHistory, CSDeals, Scraper, SteamPrice

steam = SteamMarket()
history = PriceHistory(
    price_history_file_path="steam_prices.pkl", up_to_date_days=3
)
market = CSDeals() # Choose from classes [CSDeals(), Skinport()] or make your own
scraper = Scraper(
    percent_thershold=35,
    steam_market=steam,
    third_party_market=market,
    price_history=history,
)
scraper.scrape(total_pages=20, verbose=True, play_sound=True)
```