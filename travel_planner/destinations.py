"""Curated country and city picker list for the setup form.

This is a convenience for choosing a destination, never a planner constraint.
The planner accepts any destination string, and both dropdowns are typeable, so
a destination absent from this table stays reachable — the worldwide acceptance
check in `Prototype the owner-led setup and confirmation flow` requires that a
city with no local adapter can still complete setup.

Two deliberate choices:

- The canonical latin name is the stable value. It becomes the geocoder query,
  so localizing it would let a language switch change which place is searched.
  Countries carry a Thai label because the country is the coarse filter chosen
  first; city names read the same in both languages.
- The table is ordered by region rather than alphabetically, so the dropdown a
  Thai owner opens shows nearby destinations before distant ones.

No live geocoding autocomplete: the OpenStreetMap notice in `i18n/copy.json` commits
this app to identified, cached, user-triggered requests only.
"""

from __future__ import annotations


COUNTRIES: dict[str, dict[str, object]] = {
    # Asia — the pilot region.
    "Taiwan": {
        "th": "ไต้หวัน",
        "cities": ("Taipei", "New Taipei", "Taoyuan", "Taichung", "Tainan", "Kaohsiung", "Hualien"),
    },
    "Japan": {
        "th": "ญี่ปุ่น",
        "cities": ("Tokyo", "Osaka", "Kyoto", "Nagoya", "Fukuoka", "Sapporo", "Hiroshima", "Nara"),
    },
    "South Korea": {
        "th": "เกาหลีใต้",
        "cities": ("Seoul", "Busan", "Incheon", "Jeju", "Gyeongju", "Daegu"),
    },
    "China": {
        "th": "จีน",
        "cities": ("Beijing", "Shanghai", "Chengdu", "Xi'an", "Guangzhou", "Shenzhen", "Hangzhou", "Chongqing"),
    },
    "Hong Kong": {"th": "ฮ่องกง", "cities": ("Hong Kong", "Kowloon", "Tsim Sha Tsui", "Causeway Bay")},
    "Thailand": {
        "th": "ไทย",
        "cities": ("Bangkok", "Chiang Mai", "Chiang Rai", "Phuket", "Krabi", "Pattaya", "Ayutthaya", "Khon Kaen"),
    },
    "Vietnam": {
        "th": "เวียดนาม",
        "cities": ("Hanoi", "Ho Chi Minh City", "Da Nang", "Hoi An", "Hue", "Da Lat"),
    },
    "Singapore": {"th": "สิงคโปร์", "cities": ("Singapore",)},
    "Malaysia": {
        "th": "มาเลเซีย",
        "cities": ("Kuala Lumpur", "Penang", "Malacca", "Johor Bahru", "Kota Kinabalu"),
    },
    "Indonesia": {"th": "อินโดนีเซีย", "cities": ("Jakarta", "Bali", "Yogyakarta", "Bandung", "Surabaya")},
    "Philippines": {"th": "ฟิลิปปินส์", "cities": ("Manila", "Cebu", "Davao", "Boracay", "Palawan")},
    "India": {
        "th": "อินเดีย",
        "cities": ("New Delhi", "Mumbai", "Jaipur", "Agra", "Bengaluru", "Kolkata", "Chennai"),
    },
    "United Arab Emirates": {"th": "สหรัฐอาหรับเอมิเรตส์", "cities": ("Dubai", "Abu Dhabi", "Sharjah")},
    # Europe.
    "United Kingdom": {
        "th": "สหราชอาณาจักร",
        "cities": ("London", "Edinburgh", "Manchester", "Liverpool", "Oxford", "Bath", "Glasgow"),
    },
    "France": {"th": "ฝรั่งเศส", "cities": ("Paris", "Nice", "Lyon", "Marseille", "Bordeaux", "Strasbourg")},
    "Italy": {"th": "อิตาลี", "cities": ("Rome", "Milan", "Venice", "Florence", "Naples", "Turin", "Bologna")},
    "Spain": {"th": "สเปน", "cities": ("Madrid", "Barcelona", "Seville", "Valencia", "Granada", "Bilbao")},
    "Portugal": {"th": "โปรตุเกส", "cities": ("Lisbon", "Porto", "Faro", "Sintra")},
    "Germany": {"th": "เยอรมนี", "cities": ("Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne", "Dresden")},
    "Netherlands": {"th": "เนเธอร์แลนด์", "cities": ("Amsterdam", "Rotterdam", "The Hague", "Utrecht")},
    "Switzerland": {"th": "สวิตเซอร์แลนด์", "cities": ("Zurich", "Geneva", "Lucerne", "Interlaken", "Bern", "Zermatt")},
    "Austria": {"th": "ออสเตรีย", "cities": ("Vienna", "Salzburg", "Innsbruck", "Hallstatt")},
    "Czech Republic": {"th": "เช็กเกีย", "cities": ("Prague", "Brno", "Karlovy Vary")},
    "Greece": {"th": "กรีซ", "cities": ("Athens", "Santorini", "Mykonos", "Thessaloniki", "Rhodes")},
    "Turkey": {"th": "ตุรกี", "cities": ("Istanbul", "Cappadocia", "Antalya", "Izmir", "Ankara")},
    # Americas.
    "United States": {
        "th": "สหรัฐอเมริกา",
        "cities": (
            "New York",
            "Los Angeles",
            "San Francisco",
            "Chicago",
            "Las Vegas",
            "Seattle",
            "Boston",
            "Washington, D.C.",
            "Honolulu",
        ),
    },
    "Canada": {"th": "แคนาดา", "cities": ("Toronto", "Vancouver", "Montreal", "Quebec City", "Banff", "Ottawa")},
    "Mexico": {"th": "เม็กซิโก", "cities": ("Mexico City", "Cancun", "Guadalajara", "Oaxaca", "Merida")},
    "Brazil": {"th": "บราซิล", "cities": ("Rio de Janeiro", "Sao Paulo", "Salvador", "Brasilia")},
    "Argentina": {"th": "อาร์เจนตินา", "cities": ("Buenos Aires", "Mendoza", "Bariloche", "Cordoba")},
    # Oceania.
    "Australia": {
        "th": "ออสเตรเลีย",
        "cities": ("Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Cairns", "Gold Coast"),
    },
    "New Zealand": {
        "th": "นิวซีแลนด์",
        "cities": ("Auckland", "Wellington", "Christchurch", "Queenstown", "Rotorua"),
    },
}


def country_options() -> tuple[str, ...]:
    """Countries in region order. The dropdown also accepts a typed name."""

    return tuple(COUNTRIES)


def city_options(country: str) -> tuple[str, ...]:
    """Cities for one country, empty for a country that was typed in."""

    entry = COUNTRIES.get(country)
    return tuple(entry["cities"]) if entry else ()


def country_label(country: str, language: str) -> str:
    """Display name for one country. Falls back to the value itself when typed."""

    entry = COUNTRIES.get(country)
    if entry is None:
        return country
    if language == "th":
        return str(entry["th"])
    return country


def destination_text(country: str, city: str) -> str:
    """The geocoder query for a chosen country and city.

    `"Taipei, Taiwan"` resolves more precisely than a bare `"Taipei"`, so the
    pair is joined rather than either part used alone. A city-state repeats its
    own name, which is dropped instead of searching `"Singapore, Singapore"`.
    """

    clean_country = country.strip()
    clean_city = city.strip()
    if not clean_country and not clean_city:
        raise ValueError("destination needs a country or a city")
    if not clean_city:
        return clean_country
    if not clean_country:
        return clean_city
    if clean_city.casefold() == clean_country.casefold():
        # Prefer the table's casing over whatever the owner typed.
        return clean_country
    return f"{clean_city}, {clean_country}"
