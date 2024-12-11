import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from difflib import get_close_matches
from waste_collection_schedule import Collection
from waste_collection_schedule.exceptions import (
    SourceArgumentNotFound,
    SourceArgumentNotFoundWithSuggestions,
    SourceArgAmbiguousWithSuggestions,
    SourceArgumentRequired,
    SourceArgumentRequiredWithSuggestions,
)

TITLE = "Lexington, MA"
DESCRIPTION = "Town of Lexington, MA curbside single-stream trash/recycling/compost collection."
URL = "https://lexingtonma.gov/239/Curbside-Collection"
COUNTRY = "us"

TEST_CASES = {
    "Aaron Road": {"street": "Aaron Road"},
    "Abbott Road": {"street": "Abbott Rd"},
    "Bedford Street": {"street": "Bedford St"}  # Should match one of the Bedford Street segments
}

STREET_SCHEDULE_URL = "https://lexingtonma.gov/248/Trash-Recycling-Collection-Schedule-by-S"
HOLIDAY_URL = "https://lexingtonma.gov/317/Official-Town-Holidays-Other-Closing-Day"

WEEKDAY_MAP = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6
}

HOW_TO_GET_ARGUMENTS_DESCRIPTION = {
    "en": "Visit the Town of Lexington website to find your street in the collection schedule. If the exact name isn't listed, try a close approximation. The source will attempt fuzzy matching."
}

PARAM_DESCRIPTIONS = {
    "en": {
        "street": "The street name for which you want to retrieve the collection schedule. If multiple segments exist (e.g., 'Bedford Street'), provide part of the name and fuzzy matching will find the closest match."
    }
}

PARAM_TRANSLATIONS = {
    "en": {
        "street": "Street Name"
    }
}


class Source:
    def __init__(self, street: str = None):
        if not street or not street.strip():
            # No street provided, try to load suggestions
            suggestions = self._load_street_suggestions()
            if suggestions:
                raise SourceArgumentRequiredWithSuggestions("street", suggestions=suggestions)
            else:
                # If we cannot load suggestions, just raise a normal required error
                raise SourceArgumentRequired("street")
        self._input_street = street.lower().strip()

    def fetch(self):
        normal_pickup_day = self._get_normal_pickup_day()
        if normal_pickup_day is None:
            raise SourceArgumentNotFound("street")

        holidays = self._get_holiday_delays()
        today = date.today()

        future_holidays = [h for h in holidays if h >= today]
        if not future_holidays:
            # No future holidays found
            raise Exception("No future holidays found, cannot determine schedule.")

        max_year = max(h.year for h in future_holidays)
        end_date = date(max_year, 12, 31)

        collections = []
        current_date = today
        while current_date <= end_date:
            collection_date = self._next_weekday(current_date, normal_pickup_day)

            # Check if a holiday affects this week's pickup
            if any(
                hol_date <= collection_date and
                hol_date >= (collection_date - timedelta(days=collection_date.weekday()))
                for hol_date in future_holidays
            ):
                collection_date += timedelta(days=1)

            if today <= collection_date <= end_date:
                collections.append(Collection(collection_date, "Trash, recycling, & compost", icon="mdi:recycle"))

            current_date += timedelta(weeks=1)

        return collections

    def _get_normal_pickup_day(self):
        streets_dict = self._load_streets_dict()
        if not streets_dict:
            raise SourceArgumentNotFound("street")

        # Try exact match
        if self._input_street in streets_dict:
            return streets_dict[self._input_street]

        # Fuzzy matching
        fuzzy_matches = get_close_matches(self._input_street, streets_dict.keys(), n=5, cutoff=0.4)

        if len(fuzzy_matches) == 1:
            # One fuzzy match
            return streets_dict[fuzzy_matches[0]]
        elif len(fuzzy_matches) > 1:
            # Multiple matches - ambiguous
            raise SourceArgAmbiguousWithSuggestions("street", suggestions=fuzzy_matches)
        else:
            # No matches at all
            suggestions = list(streets_dict.keys())
            raise SourceArgumentNotFoundWithSuggestions("street", suggestions=suggestions)

    def _load_streets_dict(self):
        # Load and parse the entire street dictionary from the website
        try:
            resp = requests.get(STREET_SCHEDULE_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            div = soup.find("div", class_="fr-view")
            if not div:
                return None

            uls = div.find_all("ul")
            if not uls:
                return None

            return self._parse_streets(uls)
        except:
            return None

    def _load_street_suggestions(self):
        # Attempt to load streets for suggestions if no street argument is given
        streets_dict = self._load_streets_dict()
        if streets_dict:
            suggestions = list(streets_dict.keys())
            return suggestions if suggestions else None
        return None

    def _parse_streets(self, uls):
        streets_dict = {}
        for ul in uls:
            for li in ul.find_all("li", recursive=False):
                text = li.get_text(strip=True)
                nested_ul = li.find("ul")
                if nested_ul:
                    # Multi-segment street
                    main_street = text.replace(":", "").lower().strip()
                    for sub_li in nested_ul.find_all("li"):
                        sub_text = sub_li.get_text(strip=True)
                        if " - " not in sub_text:
                            continue
                        segment_street, segment_day = sub_text.rsplit(" - ", 1)
                        segment_street_clean = f"{main_street} ({segment_street.lower().strip()})"
                        wday = WEEKDAY_MAP.get(segment_day.upper())
                        if wday is not None:
                            streets_dict[segment_street_clean] = wday
                else:
                    # Regular street
                    if " - " in text:
                        line_street, line_day = text.rsplit(" - ", 1)
                        cleaned_street = line_street.lower().strip()
                        wday = WEEKDAY_MAP.get(line_day.upper())
                        if wday is not None:
                            streets_dict[cleaned_street] = wday
        return streets_dict

    def _get_holiday_delays(self):
        resp = requests.get(HOLIDAY_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        holidays = []
        for table in soup.find_all("table", class_="fr-alternate-rows"):
            tbody = table.find("tbody")
            if not tbody:
                continue
            for row in tbody.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue
                date_str = cols[1].get_text(strip=True).replace("\n", "").strip()
                try:
                    hol_date = datetime.strptime(date_str, "%A, %B %d, %Y").date()
                    holidays.append(hol_date)
                except ValueError:
                    pass

        return holidays

    def _next_weekday(self, start_date, weekday):
        days_ahead = weekday - start_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        return start_date + timedelta(days=days_ahead)
