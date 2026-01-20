from bs4 import BeautifulSoup
from datetime import datetime, timezone
import pytz
import hashlib
import os

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------

RESPONSE_FILE = "response.txt"
OLD_CALENDAR = "old_calendar.ics"
NEW_CALENDAR = "calendar.ics"
LOCAL_TZ = pytz.timezone("Europe/London")

# ------------------------------------------------------------
# Parsing timetable JS
# ------------------------------------------------------------

def parse_events(events_data):
    # Replace JS date objects
    events_data = events_data.replace("new Date", "")

    cleaned_data = ""

    for line in events_data.split("\n"):
        comment_pos = line.find("//")
        if comment_pos != -1:
            line = line[:comment_pos]

        if ":" in line:
            key, val = line.split(":", 1)
            line = f"'{key}': {val}"

        cleaned_data += line + "\n"

    parsed_data = eval(cleaned_data)

    for event in parsed_data:
        if "start" in event:
            s = list(event["start"])
            s[1] += 1
            s.append(0)
            event["start"] = LOCAL_TZ.localize(datetime(*s))

        if "end" in event:
            e = list(event["end"])
            e[1] += 1
            e.append(0)
            event["end"] = LOCAL_TZ.localize(datetime(*e))

    return parsed_data


def get_events_data_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        page_data = f.read()

    soup = BeautifulSoup(page_data, features="html.parser")

    for script in soup.head.find_all("script", {"type": "text/javascript"}):
        if not script.has_attr("src"):
            source = script.text
            break
    else:
        raise RuntimeError("Could not find inline timetable script")

    return source.split("events:")[1].split("]")[0] + "]"

# ------------------------------------------------------------
# ICS helpers
# ------------------------------------------------------------

def ics_time(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def make_uid(event):
    key = f"{event['moduleDesc']}|{event['title']}|{event['start'].isoformat()}"
    return hashlib.sha1(key.encode()).hexdigest() + "@timetable"


def create_ics_event(event):
    return {
        "uid": make_uid(event),
        "summary": f"{event['moduleDesc']} - {event['title']}",
        "description": f"{event['lecturer']} - {event['room']}",
        "start": event["start"],
        "end": event["end"],
    }

# ------------------------------------------------------------
# Load existing calendar (UIDs only)
# ------------------------------------------------------------

def load_existing_uids(path):
    uids = set()

    if not os.path.exists(path):
        return uids

    with open(path, "r", encoding="utf-8") as f:
        current_uid = None
        cancelled = False

        for line in f:
            line = line.strip()

            if line == "BEGIN:VEVENT":
                current_uid = None
                cancelled = False

            elif line.startswith("UID:"):
                current_uid = line[4:]

            elif line == "STATUS:CANCELLED":
                cancelled = True

            elif line == "END:VEVENT" and current_uid and not cancelled:
                uids.add(current_uid)

    return uids

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    events_js = get_events_data_from_file(RESPONSE_FILE)
    parsed_events = parse_events(events_js)

    new_events = [
        create_ics_event(e)
        for e in parsed_events
        if e
    ]

    old_uids = load_existing_uids(OLD_CALENDAR)
    new_uids = {e["uid"] for e in new_events}

    now = ics_time(datetime.now(timezone.utc))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Timetable Sync//EN",
        "CALSCALE:GREGORIAN",
    ]

    # Add / update events
    for ev in new_events:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}",
            f"DTSTAMP:{now}",
            f"DTSTART:{ics_time(ev['start'])}",
            f"DTEND:{ics_time(ev['end'])}",
            f"SUMMARY:{ev['summary']}",
            f"DESCRIPTION:{ev['description']}",
            "END:VEVENT",
        ])

    # Cancel removed events
    for uid in old_uids - new_uids:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            "STATUS:CANCELLED",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")

    with open(NEW_CALENDAR, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Added / updated: {len(new_events)}")
    print(f"Removed: {len(old_uids - new_uids)}")
    print(f"Wrote {NEW_CALENDAR}")

# ------------------------------------------------------------

if __name__ == "__main__":
    main()
