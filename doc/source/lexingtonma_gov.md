# Lexington, MA

This source retrieves curbside single-stream trash, recycling, and compost collection schedules for the Town of Lexington, Massachusetts. It fetches the collection day by street and adjusts for holidays by delaying pickup by one day.

It uses simple fuzzy matching (via Python's `difflib.get_close_matches`) to handle minor differences in the street name.

## Configuration via `configuration.yaml`

**Mandatory arguments:**
- `street`: The street name for which you want to retrieve the schedule.

If an exact match for the street name is not found, the integration attempts to find the closest known street name.

**Optional arguments:**
- None

### Example Configuration

```yaml
waste_collection_schedule:
  sources:
    - name: lexingtonma_gov
      args:
        street: "Abbott Rd"
