"""Class sections for "My Classes", from Ole Miss's public Banner class search (no login).

Adapted from RebelSnatch's Banner client. Once a day it reads every subject for GROVE_TERM
(e.g. 202710 for Fall 2026) and stores each section's meeting days, times and room.
"""

import html
import os
import time
from datetime import datetime

import requests

from .. import db

BASE_URL = "https://reg-prod.olemiss.elluciancloud.com/StudentRegistrationSsb/ssb"
USER_AGENT = "Grove/0.1 (Ole Miss student dashboard)"
PAGE_SIZE = 500
DAYS = [("monday", "M"), ("tuesday", "T"), ("wednesday", "W"), ("thursday", "R"),
        ("friday", "F"), ("saturday", "S"), ("sunday", "U")]


def term() -> str | None:
    return os.environ.get("GROVE_TERM") or None


def _hhmm(value) -> str | None:
    value = str(value or "")
    return f"{value[:2]}:{value[2:]}" if len(value) == 4 and value.isdigit() else None


def _date(value) -> str | None:
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def parse_meeting(mt: dict) -> dict:
    building = html.unescape(mt.get("buildingDescription") or mt.get("building") or "").strip()
    room = str(mt.get("room") or "").strip()
    return {
        "days": "".join(code for key, code in DAYS if mt.get(key)),
        "begin": _hhmm(mt.get("beginTime")),
        "end": _hhmm(mt.get("endTime")),
        "where": " ".join(p for p in (building, room) if p) or None,
        "start_date": _date(mt.get("startDate")),
        "end_date": _date(mt.get("endDate")),
    }


def parse_section(raw: dict) -> dict:
    faculty = raw.get("faculty") or []
    primary = [f for f in faculty if f.get("primaryIndicator")] or faculty
    return {
        "crn": str(raw["courseReferenceNumber"]),
        "label": f'{raw["subject"]} {raw["courseNumber"]}',
        "section": raw.get("sequenceNumber"),
        "title": html.unescape(raw.get("courseTitle") or ""),
        "instructor": html.unescape(primary[0].get("displayName") or "") if primary else "",
        "meetings": [parse_meeting(mf.get("meetingTime") or {}) for mf in raw.get("meetingsFaculty") or []],
    }


class BannerClient:
    def __init__(self, base_url: str = BASE_URL, delay: float = 1.0):
        self.base_url = base_url
        self.delay = delay  # seconds between requests, to be polite to Banner
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._term = None
        self._session_id = None

    def _get(self, path: str, **params):
        time.sleep(self.delay)
        r = self.session.get(f"{self.base_url}/{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, params=None, data=None):
        time.sleep(self.delay)
        r = self.session.post(f"{self.base_url}/{path}", params=params, data=data, timeout=30)
        r.raise_for_status()
        return r

    def get_subjects(self, term: str) -> list[dict]:
        return self._get("classSearch/get_subject", searchTerm="", term=term, offset=1, max=1000)

    def _select_term(self, term: str):
        """Banner search is stateful: the session cookie remembers the chosen term."""
        if self._term == term:
            return
        self._session_id = f"grove{int(time.time() * 1000)}"
        self._post("term/search", params={"mode": "search"}, data={
            "term": term, "studyPath": "", "studyPathText": "",
            "startDatepicker": "", "endDatepicker": "", "uniqueSessionId": self._session_id,
        })
        self._term = term

    def search_subject(self, term: str, subject: str) -> list[dict]:
        self._select_term(term)
        self._post("classSearch/resetDataForm")
        found, offset = [], 0
        while True:
            r = self._get(
                "searchResults/searchResults",
                txt_subject=subject, txt_term=term, pageOffset=offset, pageMaxSize=PAGE_SIZE,
                sortColumn="subjectDescription", sortDirection="asc", uniqueSessionId=self._session_id,
            )
            page = r.get("data") or []
            found += page
            offset += len(page)
            if not page or offset >= (r.get("totalCount") or 0):
                return found


def fetch(conn: db.DB, client: BannerClient | None = None) -> dict:
    t = term()
    if not t:
        raise RuntimeError("set GROVE_TERM (e.g. 202710 for Fall 2026) to turn on My Classes")
    client = client or BannerClient()
    sections, failed = {}, []
    for subj in client.get_subjects(t):
        code = subj.get("code")
        try:
            for raw in client.search_subject(t, code):
                s = parse_section(raw)
                sections[s["crn"]] = s
        except Exception as e:  # keep going; one subject failing shouldn't lose the rest
            failed.append(f"{code}: {e}")
    if not sections:
        raise RuntimeError("Banner returned no sections; " + "; ".join(failed[:3]))
    db.replace_sections(conn, t, list(sections.values()))
    return {"term": t, "count": len(sections), "failed_subjects": len(failed)}


fetch.needs_db = True
