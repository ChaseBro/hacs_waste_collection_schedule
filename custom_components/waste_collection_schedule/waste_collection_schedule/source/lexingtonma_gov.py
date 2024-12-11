import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from difflib import get_close_matches
from waste_collection_schedule import Collection

TITLE = "Lexington, MA"
DESCRIPTION = "Town of Lexington, MA curbside single-stream trash/recycling/compost collection."
URL = "https://lexingtonma.gov/239/Curbside-Collection"

STREET_SCHEDULE_URL = "https://lexingtonma.gov/248/Trash-Recycling-Collection-Schedule-by-S"
HOLIDAY_URL = "https://lexingtonma.gov/317/Official-Town-Holidays-Other-Closing-Day"

TEST_CASES = {
    "Aaron Road": {"street": "Aaron Road"},
    "Abbott Road": {"street": "Abbott Rd"},
}


class Source:
    def __init__(self, street: str):
        self._input_street = street.lower().strip()

    def fetch(self):
        normal_pickup_day = self._get_normal_pickup_day()
        if normal_pickup_day is None:
            return []

        holidays = self._get_holiday_delays()

        today = date.today()
        collections = []
        for week_offset in range(8):
            base_week_date = today + timedelta(weeks=week_offset)
            collection_date = self._next_weekday(
                base_week_date, normal_pickup_day)

            # Check if any holiday affects this collection week
            if any(
                hol_date <= collection_date and
                hol_date >= (collection_date -
                             timedelta(days=collection_date.weekday()))
                for hol_date in holidays
            ):
                collection_date += timedelta(days=1)

            collections.append(Collection(
                collection_date, "Trash, recycling, & compost", icon="mdi:recycle"))

        return collections

    def _get_normal_pickup_day(self):
        resp = requests.get(STREET_SCHEDULE_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        div = soup.find("div", class_="fr-view")
        if not div:
            return None
        ul = div.find("ul")
        if not ul:
            return None

        weekday_map = {
            "MONDAY": 0,
            "TUESDAY": 1,
            "WEDNESDAY": 2,
            "THURSDAY": 3,
            "FRIDAY": 4,
            "SATURDAY": 5,
            "SUNDAY": 6
        }

        streets_dict = {}
        # Extract all streets and their days
        for li in ul.find_all("li"):
            text = li.get_text(strip=True)
            if " - " in text:
                line_street, line_day = text.rsplit(" - ", 1)
                cleaned_street = line_street.lower().strip()
                streets_dict[cleaned_street] = weekday_map.get(
                    line_day.upper())

        # Attempt exact match first
        if self._input_street in streets_dict:
            return streets_dict[self._input_street]

        # If no exact match, try fuzzy match
        matches = get_close_matches(
            self._input_street, streets_dict.keys(), n=1, cutoff=0.5)
        if matches:
            return streets_dict[matches[0]]

        return None

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
                date_str = cols[1].get_text(
                    strip=True).replace("\n", "").strip()
                try:
                    hol_date = datetime.strptime(
                        date_str, "%A, %B %d, %Y").date()
                    holidays.append(hol_date)
                except ValueError:
                    pass

        return holidays

    def _next_weekday(self, start_date, weekday):
        days_ahead = weekday - start_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        return start_date + timedelta(days=days_ahead)
