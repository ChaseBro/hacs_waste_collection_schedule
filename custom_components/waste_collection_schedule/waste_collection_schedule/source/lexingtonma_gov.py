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
    "Abbott Road": {"street": "Abbott Road"},
    # Should match one of the Bedford Street segments
    "Bedford Street": {"street": "bedford street (battlegreen to revere st)"}
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
        print("[DEBUG] Initializing Source with street:", street)
        if not street or not street.strip():
            print("[DEBUG] No street provided, attempting to load suggestions...")
            suggestions = self._load_street_suggestions()
            if suggestions:
                print(
                    "[DEBUG] Raising SourceArgumentRequiredWithSuggestions with suggestions:", suggestions)
                raise SourceArgumentRequiredWithSuggestions(
                    "street", suggestions=suggestions)
            else:
                print("[DEBUG] No suggestions found, raising SourceArgumentRequired")
                raise SourceArgumentRequired("street")
        self._input_street = street.lower().strip()
        print("[DEBUG] Normalized street input:", self._input_street)

    def fetch(self):
        print("[DEBUG] Fetching collection schedule...")
        normal_pickup_day = self._get_normal_pickup_day()
        if normal_pickup_day is None:
            print("[DEBUG] Normal pickup day not found, raising SourceArgumentNotFound")
            raise SourceArgumentNotFound("street")

        print("[DEBUG] Normal pickup day:", normal_pickup_day)
        holidays = self._get_holiday_delays()
        today = date.today()
        print("[DEBUG] Today:", today)
        print("[DEBUG] Holidays found:", holidays)

        future_holidays = [h for h in holidays if h >= today]
        print("[DEBUG] Future holidays:", future_holidays)
        if not future_holidays:
            print("[DEBUG] No future holidays, raising Exception")
            raise Exception(
                "No future holidays found, cannot determine schedule.")

        max_year = max(h.year for h in future_holidays)
        end_date = date(max_year, 12, 31)
        print("[DEBUG] Generating schedule until end of year:", end_date)

        collections = []
        current_date = today
        while current_date <= end_date:
            collection_date = self._next_weekday(
                current_date, normal_pickup_day)
            # Check holiday delay
            if any(
                hol_date <= collection_date and
                hol_date >= (collection_date -
                             timedelta(days=collection_date.weekday()))
                for hol_date in future_holidays
            ):
                print("[DEBUG] Holiday affects week starting",
                      current_date, "- shifting by one day.")
                collection_date += timedelta(days=1)

            if today <= collection_date <= end_date:
                print("[DEBUG] Adding collection date:", collection_date)
                collections.append(Collection(
                    collection_date, "Trash, recycling, & compost", icon="mdi:recycle"))

            current_date += timedelta(weeks=1)

        print("[DEBUG] Total collections found:", len(collections))
        return collections

    def _get_normal_pickup_day(self):
        print("[DEBUG] Getting normal pickup day for street:", self._input_street)
        streets_dict = self._load_streets_dict()
        if not streets_dict:
            print("[DEBUG] No streets dict found, raising SourceArgumentNotFound")
            raise SourceArgumentNotFound("street")

        # Exact match
        if self._input_street in streets_dict:
            print("[DEBUG] Exact street match found:", self._input_street)
            return streets_dict[self._input_street]

        # Fuzzy match
        fuzzy_matches = get_close_matches(
            self._input_street, streets_dict.keys(), n=5, cutoff=0.7)
        print("[DEBUG] Fuzzy matches found:", fuzzy_matches)

        if len(fuzzy_matches) == 1:
            print("[DEBUG] Single fuzzy match found:", fuzzy_matches[0])
            return streets_dict[fuzzy_matches[0]]
        elif len(fuzzy_matches) > 1:
            print(
                "[DEBUG] Multiple fuzzy matches, raising SourceArgAmbiguousWithSuggestions")
            raise SourceArgAmbiguousWithSuggestions(
                "street", self._input_street, suggestions=fuzzy_matches)
        else:
            # No matches
            suggestions = list(streets_dict.keys())
            print(
                "[DEBUG] No matches found, raising SourceArgumentNotFoundWithSuggestions with suggestions:", suggestions)
            raise SourceArgumentNotFoundWithSuggestions(
                "street", self._input_street, suggestions=suggestions)

    def _load_streets_dict(self):
        print("[DEBUG] Loading streets dictionary from URL:", STREET_SCHEDULE_URL)
        try:
            resp = requests.get(STREET_SCHEDULE_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            divs = soup.find_all("div", class_="fr-view")
            uls = []
            for div in divs:
                # Find top-level ul elements inside this fr-view div
                # Using recursive=False ensures we only get the immediate ul children,
                # not nested ones directly here. If you need nested ul’s, omit recursive=False.
                these_uls = div.find_all("ul", recursive=False)
                uls.extend(these_uls)

            if not uls:
                print("[DEBUG] No ul elements found")
                return None

            streets = self._parse_streets(uls)
            print("[DEBUG] Parsed streets dictionary with",
                  len(streets), "entries")
            return streets
        except Exception as e:
            print("[DEBUG] Exception while loading streets dict:", e)
            return None

    def _load_street_suggestions(self):
        print("[DEBUG] Loading street suggestions...")
        streets_dict = self._load_streets_dict()
        if streets_dict:
            suggestions = list(streets_dict.keys())[:10]
            print("[DEBUG] Suggestions loaded:", suggestions)
            return suggestions if suggestions else None
        print("[DEBUG] No streets dict, no suggestions available.")
        return None

    def _parse_streets(self, uls):
        streets_dict = {}
        print("[DEBUG] Parsing streets...")

        for ul in uls:
            # Print how many LI we have in this UL
            li_elements = ul.find_all("li", recursive=False)
            print(
                f"[DEBUG] Found {len(li_elements)} <li> elements at this level")

            for li in li_elements:
                text = li.get_text(strip=True)
                # Look for a nested UL if present
                nested_ul = li.find("ul", recursive=True)

                # Debug info about this li element
                # print("[DEBUG] Processing <li>: ", text[:50],
                #       "..." if len(text) > 50 else "")

                if nested_ul:
                    # Multi-segment street case, e.g. "Bedford Street:"
                    if ":" in text:
                        main_street = text.split(":")[0].lower().strip()
                        # print(
                        #     f"[DEBUG] Found multi-segment street: {main_street}")

                        # Parse each sub_li for the segments
                        sub_lis = nested_ul.find_all("li", recursive=False)
                        # print(
                        #     f"[DEBUG] Found {len(sub_lis)} segment(s) for street: {main_street}")

                        for sub_li in sub_lis:
                            sub_text = sub_li.get_text(strip=True)
                            print("[DEBUG] Segment line:", sub_text)

                            if " - " not in sub_text:
                                # No day info, skip
                                print(
                                    "[DEBUG] No day info found in segment, skipping")
                                continue

                            segment_street, segment_day = sub_text.rsplit(
                                " - ", 1)
                            segment_street_clean = f"{main_street} ({segment_street.lower().strip()})"
                            wday = WEEKDAY_MAP.get(segment_day.upper())
                            if wday is not None:
                                streets_dict[segment_street_clean] = wday
                                # print(
                                #     f"[DEBUG] Added segment: {segment_street_clean} -> {segment_day}")
                            else:
                                print("[DEBUG] Could not map weekday:",
                                      segment_day)

                    else:
                        # If we have a nested UL but no colon, that's unusual; debug it
                        print(
                            "[DEBUG] Nested UL found but no ':' in text. Possibly malformed data. Skipping.")
                        continue
                else:
                    # Regular single-entry street
                    if " - " in text:
                        line_street, line_day = text.rsplit(" - ", 1)
                        cleaned_street = line_street.lower().strip()
                        wday = WEEKDAY_MAP.get(line_day.upper())
                        if wday is not None:
                            streets_dict[cleaned_street] = wday
                            # print(
                            #     f"[DEBUG] Added regular street: {cleaned_street} -> {line_day}")
                        else:
                            print("[DEBUG] Could not map weekday:", line_day)
                    else:
                        # No ' - ' means no day info here, skipping
                        print(
                            "[DEBUG] No ' - ' found in line. Likely not a valid street-day entry.")
                        continue

        print("[DEBUG] Finished parsing streets. Total streets found:",
              len(streets_dict))
        return streets_dict

    def _get_holiday_delays(self):
        print("[DEBUG] Loading holiday delays from URL:", HOLIDAY_URL)
        resp = requests.get(HOLIDAY_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        holidays = []
        for table in soup.find_all("td", data_label_="date"):
            tbody = table.find("tbody")
            if not tbody:
                continue
            for row in tbody.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue
                date_str = cols[1].get_text(
                    strip=True).replace("\n", "").strip()
                print("[DEBUG]: holiday date string", date_str)
                try:
                    hol_date = datetime.strptime(
                        date_str, "%A, %B %d, %Y").date()
                    holidays.append(hol_date)
                except ValueError:
                    pass

        print("[DEBUG] Holidays loaded:", holidays)
        return holidays

    def _next_weekday(self, start_date, weekday):
        days_ahead = weekday - start_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        result_date = start_date + timedelta(days=days_ahead)
        print("[DEBUG] Next weekday for", start_date, "->",
              result_date, "target weekday:", weekday)
        return result_date
