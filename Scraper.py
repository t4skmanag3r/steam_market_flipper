from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
import textwrap
from datetime import datetime, timedelta
import os.path
import pickle as pkl
from time import sleep
from random import randint
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import requests
from playsound import playsound
from bs4 import BeautifulSoup as Soup
from forex_python.converter import CurrencyRates


class ItemNotFound(Exception):  # Custom error
    def __init__(self, item_name) -> None:
        self.item_name = item_name
        self.message = f"item with item_name: [{item_name}] not found in price history"
        super().__init__(self.message)


# Item dataclasses
@dataclass
class SteamPrice:
    """
    dataclass for storing steam item information
    """

    name: str
    lowest_price: float
    median_price: float
    volume: int
    date: datetime
    url: str


@dataclass
class ThirdPartyMarketItem(ABC):
    """
    abstract dataclass for storing item information from third party markets
    """

    name: str
    price: float


@dataclass
class SkinportItem(ThirdPartyMarketItem):
    suggested_price: float
    url: str


@dataclass
class CSDealsItem(ThirdPartyMarketItem):
    url: str = ""


#

#
class PriceHistory:
    """
    class containing the steam price history of items to save time by skiping price requests for items that are up to date
    """

    def __init__(self, price_history_file_path: str, up_to_date_days: int = 3) -> None:
        """
        args:
            price_history_file_path : str
                path to price history file (must be a .pkl file)
            up_to_date_days :
                days that items are considered up to date
        """
        self.today = datetime.today()
        self.price_history_file_path = price_history_file_path
        self.up_to_date_days = up_to_date_days
        self.load_data()

    def load_data(self) -> None:
        """
        loads price history data from file
        """
        if not os.path.exists(self.price_history_file_path):
            self.data = {}
            self.save_data()
        else:
            with open(self.price_history_file_path, "rb") as p:
                self.data = pkl.load(p)

    def save_data(self) -> None:
        """
        saves price history to file
        """
        with open(self.price_history_file_path, "wb") as p:
            pkl.dump(self.data, p)

    def update_data(self, name: str, SteamPrice) -> None:
        """
        updates price of item
        """
        self.data[name] = SteamPrice

    def get_item_info(self, name: str) -> SteamPrice:
        """
        gets information on item
        """
        if name not in self.data:
            raise ItemNotFound(name)
        return self.data[name]

    def check_exists(self, name: str) -> bool:
        """
        checks if item exists in price history
        """
        if name not in self.data:
            return False
        return True

    def check_up_to_date(self, name: str) -> bool:
        """
        check if item price is updated
        """
        if self.data[name]:
            if (self.today - self.data[name].date).days > self.up_to_date_days:
                return False
            else:
                return True
        else:
            return True

    def check_item(self, name: str) -> bool:
        """
        check if item exists and is up to date
        """
        if not self.check_exists(name):
            return False
        if not self.check_up_to_date(name):
            return False
        return True


class SteamMarket:
    """
    class that stores functions for retrieving steam price
    """

    def __init__(self) -> None:
        self.today = datetime.today()
        self.steam_url = "https://steamcommunity.com/market/priceoverview/?appid=252490&currency=3&market_hash_name={}"

    def get_steam_price(self, name: str) -> Optional[SteamPrice]:
        """
        function to get price data of item from steam
        """
        page_html = None
        uClient = None
        for atempt in range(3):
            try:
                uClient = urlopen(self.steam_url.format(self._encode_url_string(name)))
                page_html = uClient.read()
                break

            except HTTPError as error:
                if atempt >= 2:
                    print(
                        textwrap.dedent(
                            f"""\
                        failed while trying to get price for item: "{name}"
                        error code: {error.code},
                        reason - {error.reason}
                        """
                        )
                    )
                else:
                    sleep(1)
                    continue
            finally:
                if uClient:
                    uClient.close()

        if page_html:
            page_soup = Soup(page_html, "html.parser")
            steam_json = json.loads(page_soup.getText())
            if not steam_json["success"]:
                return None
            return self._parse_price_info(steam_json, name)
        return None

    def _parse_price_info(self, json_info: dict, name: str) -> SteamPrice:
        """
        funtion to parse steam market json
        """
        lowest_price = (
            float(self._filter_string_price(json_info["lowest_price"])) / 100
            if "lowest_price" in json_info
            else 0
        )
        median_price = (
            float(self._filter_string_price(json_info["median_price"])) / 100
            if "median_price" in json_info
            else 0
        )
        volume = int(json_info["volume"].strip()) if "volume" in json_info else 0
        steam_url = f"https://steamcommunity.com/market/listings/252490/{self._encode_url_string(name)}"
        return SteamPrice(
            name=name,
            lowest_price=lowest_price,
            median_price=median_price,
            volume=volume,
            date=self.today,
            url=steam_url,
        )

    def _encode_url_string(self, string: str) -> str:
        """
        function for url encoding
        """
        maping = {" ": "%20", "'": "%27", "&": "%26", "é": "%C3%A9"}
        for k, v in maping.items():
            string = string.replace(k, v)
        return string

    def _filter_string_price(self, string) -> float:
        """
        function to filter out symbols from price in steam json
        """
        char_list = ["€", ",", "--", "â‚¬", " ", "$", "."]
        for char in char_list:
            string = string.replace(char, "")
        return string.strip()


# Third party market scraper classes
class ThirdPartyMarket(ABC):
    @abstractmethod
    def get_page_items(self, page):
        pass


class CSDeals(ThirdPartyMarket):
    """
    scraper class for https://cs.deals
    """

    def __init__(self, min_price: float = 2.0, max_price: float = 100.0):
        """
        args:
            min_price : float = 2.0
                minimum price for item to show
            max_price : float = 100.0
                maximum price for item to show
        """
        self.url = "https://cs.deals/ajax/marketplace-search"
        self.headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36 OPR/85.0.4341.65",
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        self.form_data = {"appid": 252490, "sort": "discount", "sort_desc": 1}
        self.conversion_rate = CurrencyRates().get_rate("USD", "EUR")
        self.min_price = min_price
        self.max_price = max_price

    def get_page_items(self, page: int) -> Optional[List[SkinportItem]]:
        """
        retrieves page items for csdeals
        """
        self.form_data["page"] = page
        try:
            req = requests.post(url=self.url, data=self.form_data, headers=self.headers)
        except HTTPError as error:
            print(
                textwrap.dedent(
                    f"""\
                failed while scraping CSDeals page {page}
                error code: {error.code},
                reason - {error.reason}
                """
                )
            )
            return None
        try:
            data = req.json()["response"]["results"]["252490"]

            items = []
            for item in data:
                name = item["c"]
                price = round(float(item["i"]) * self.conversion_rate, 2)
                new_item = CSDealsItem(name=name, price=price)
                if price > self.min_price and price < self.max_price:
                    items.append(new_item)
        except Exception as exc:
            raise exc

        return items


class Skinport(ThirdPartyMarket):
    """
    scraper class for https://skinport.com
    """

    def __init__(
        self,
        sortby: str = "date",
        order: str = "desc",
        price_min: int = 200,
        price_max: int = 10000,
    ) -> None:
        """
        args:
            sortby : str = "date"
                sort order by ["sale", "popular", "percent", "price", "wear", "date"]
            order : str = "desc"
                sort in ascending or descending order ["asc", "desc"]
            price_min : int = 200
                minimum price for items 200 = 2.00€
            price_max : int = 10000
                maximum price for items 10000 = 100.00€
        """
        self.headers = {
            "accept": "application/json text/plain, */*",
            "accept-encoding": "utf-8",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://skinport.com",
            "referer": "https://skinport.com/market/252490",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36 OPR/73.0.3856.415",
        }
        self.sort_options = ["sale", "popular", "percent", "price", "wear", "date"]
        self.sort_by = sortby
        self.order = order
        self.price_min = price_min
        self.price_max = price_max

        self.url = "https://app.skinport.com/browse/252490?pricegt={}&pricelt={}&sort={}&order={}&skip={}"

    def get_page_items(self, page) -> Optional[List[SkinportItem]]:
        """
        function to get all items from Skinport page
        """
        page_html = None
        response = None
        formated_url = self.url.format(
            self.price_min, self.price_max, self.sort_by, self.order, page
        )
        for atempt in range(3):
            try:
                req = Request(formated_url, headers=self.headers)
                response = urlopen(req, timeout=500)
                page_html = response.read()

                break
            except HTTPError as error:
                if atempt >= 2:
                    print(
                        textwrap.dedent(
                            f"""\
                        failed while scraping Skinport page {page}
                        error code: {error.code},
                        reason - {error.reason}
                        """
                        )
                    )
                else:
                    sleep(1)
                    continue
            finally:
                if response:
                    response.close()

        if page_html:
            page_soup = Soup(page_html, "html.parser")
            text = json.loads(page_soup.getText())

            page_items = []
            for item in text["items"]:
                page_items.append(
                    SkinportItem(
                        name=item["marketName"],
                        price=item["salePrice"] / 100,
                        suggested_price=item["suggestedPrice"] / 100,
                        url=f"https://skinport.com/market/252490?search={item['url']}",
                    )
                )

            return page_items
        return None


#


def tax_calculation(price) -> float:
    """
    tax calculation for transaction
    drop 2% of base price,
    13 % steam market cut
    12 % skinport sale cut
    """
    return round(round(price * 0.98 * 0.87, 2) * 0.88, 2)


@dataclass
class Alert:
    """
    dataclass for alerts
    """

    market_item: ThirdPartyMarketItem
    steam_price: SteamPrice
    percentage: float

    def __post_init__(self):
        self.sell_even = round(self.market_item.price * 1.13 * 1.12, 2)
        self.profit = tax_calculation(self.steam_price.lowest_price)

    def __str__(self) -> str:
        return (
            f'item: ["{self.market_item.name}"],  buy price: {self.market_item.price}€  sell price: {self.steam_price.lowest_price}€  volume: {self.steam_price.volume}\n'
            + f"profit percent: {self.percentage}% profit: {self.profit}€ sell/even: {self.sell_even}€\n"
            + f"market_link: {self.market_item.url}  steam: {self.steam_price.url}\n"
            + "-" * 150
        )


class Scraper:
    """
    class for automaticaly scraping and comparing prices between steam and external market
    """

    def __init__(
        self,
        third_party_market: ThirdPartyMarket,
        steam_market: SteamMarket,
        price_history: PriceHistory,
        percent_thershold: float = 20.0,
    ) -> None:
        """
        args:
            percent_threshold : float = 20.0
                percent threshold needed to be exceeded to trigger an Alert
        """
        self.percent_threshold = percent_thershold
        self.third_party_market = third_party_market
        self.steam_market = steam_market
        self.price_history = price_history
        self.alerts = {}

    def scrape(
        self, total_pages: int = 20, verbose: bool = False, play_sound=True
    ) -> None:
        """
        function starts the scraping and comparing proccess

        args:
            total_pages : int = 20
                total_pages to scrape from skinport.com
            verbose : bool = False
                if True prints item name trying to be retrieved from steam to console
        """
        print("Starting scraper")
        for page in range(0, total_pages + 1):
            print(f"getting page {page}")
            market_items = self.third_party_market.get_page_items(page)
            if not market_items:
                print("failed getting page items")
                continue
            for c, market_item in enumerate(market_items):
                # checks if item already exist in price data and is up to date, if not updates it
                if not self.price_history.check_item(market_item.name):
                    if verbose:
                        print(f'getting steam price for ["{market_item.name}"]')
                    steam_price = self.steam_market.get_steam_price(market_item.name)
                    self.price_history.update_data(market_item.name, steam_price)
                    sleep(randint(2, 5))

                # saves the updated price history periodicaly
                if c % 10:
                    self.price_history.save_data()

                # gets steam price and compares skinport price to steam price
                steam_price = self.price_history.get_item_info(market_item.name)
                if not steam_price:
                    continue

                percentage = self.compare_price(market_item, steam_price)
                # if profit percentage exceeds certain threshold generates an alert and prints to terminal
                if percentage > self.percent_threshold:
                    try:
                        alert = Alert(market_item, steam_price, percentage)
                        if market_item.name not in self.alerts.keys():
                            self.alerts[market_item.name] = [alert]
                            print("#" * 10, "ALERT!", "#" * 10)
                            print(alert)

                            # playing alert sound
                            if play_sound:
                                playsound("alert.mp3", block=True)
                        else:
                            self.alerts[market_item.name].append(alert)

                        self.write_alert_to_file(alert)

                    except Exception as e:
                        print(e)

            self.price_history.save_data()  # saves updates steam prices every page

            print("waiting...")
            sleep(randint(2, 5))

        print("done!")
        print(f"found {len(self.alerts)} alerts")
        print("-" * 150)
        for _, alert in self.alerts.items():  # printing all alerts
            print(alert[0])

    def compare_price(
        self, skinport_item: SkinportItem, steam_price: SteamPrice
    ) -> float:
        """
        compares price between skinport ant steam and returns percantage difference
        """
        return round(
            (
                tax_calculation(steam_price.lowest_price) / skinport_item.price * 100
                - 100
            ),
            2,
        )

    def write_alert_to_file(self, alert):
        with open("deals.txt", "a") as f:
            f.write(f"{alert}\n")


def main():
    steam = SteamMarket()
    history = PriceHistory(
        price_history_file_path="steam_prices.pkl", up_to_date_days=3
    )
    market = Skinport()  # Choose from [CSDeals(), Skinport()]
    scraper = Scraper(
        percent_thershold=25,
        steam_market=steam,
        third_party_market=market,
        price_history=history,
    )
    scraper.scrape(total_pages=20, verbose=True, play_sound=True)


if __name__ == "__main__":
    main()
