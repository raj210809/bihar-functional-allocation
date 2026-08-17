"""Fetch live metrics from government dashboard APIs (server-side to avoid CORS)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
}

DBT_REFERER = {"Referer": "https://dbtbharat.gov.in/"}
CURRENT_FY = "2024_2025"
BIHAR_STATE_ID = 10
REQUEST_TIMEOUT = 40


def _request_get(url: str, **kwargs: Any) -> requests.Response:
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    last_err: Exception | None = None
    for _ in range(2):
        try:
            resp = requests.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise last_err  # type: ignore[misc]


def _ok(value: str, year: str, source: str, **extra: Any) -> dict[str, Any]:
    return {"status": "ok", "value": value, "year": year, "source": source, **extra}


def _fail(source: str, error: str) -> dict[str, Any]:
    return {"status": "error", "error": error, "source": source}


def format_inr(amount: float | str) -> str:
    num = float(amount)
    if num >= 1e7:
        cr = num / 1e7
        return f"₹{cr:,.2f} cr"
    if num >= 1e5:
        lakh = num / 1e5
        return f"₹{lakh:,.2f} lakh"
    return f"₹{num:,.0f}"


def format_count(num: float | str) -> str:
    n = float(num)
    if n >= 1e7:
        return f"{n / 1e7:.2f} cr"
    if n >= 1e5:
        return f"{n / 1e5:.2f} lakh"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return f"{int(n):,}"


def fetch_dbt_bihar() -> dict[str, Any]:
    source = "dbtbharat.gov.in"
    url = (
        "https://dbtbharat.gov.in/ajax/home/state-data-map"
        f"?financial-year={CURRENT_FY}"
    )
    try:
        resp = _request_get(url, headers={**HEADERS, **DBT_REFERER})
        payload = resp.json()
        if payload.get("code") != 200:
            return _fail(source, payload.get("message", "API error"))

        bihar = next(
            (s for s in payload["data"] if s.get("state_name", "").upper() == "BIHAR"),
            None,
        )
        if not bihar:
            return _fail(source, "Bihar not found in state map")

        transfer = float(bihar["total_dbt_transfer"])
        txns = int(float(bihar["no_of_dbt_transactions"]))
        fy_label = CURRENT_FY.replace("_", "-")
        per_capita = transfer / 12.5e7  # ~125 million Bihar population (approx)

        return _ok(
            f"{format_inr(transfer)} · {format_count(txns)} txns",
            f"FY {fy_label} (live)",
            source,
            detail=(
                f"₹{per_capita:,.0f} per capita (est.) · "
                f"state DBT score {bihar.get('state_score', '—')}"
            ),
            raw={"transfer_inr": transfer, "transactions": txns},
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(source, str(exc))


def fetch_dilrmp_bihar() -> dict[str, Any]:
    source = "dilrmp.gov.in"
    url = f"https://dilrmp.gov.in/getStateData?stateId={BIHAR_STATE_ID}"
    try:
        resp = _request_get(url, verify=False)
        rows = resp.json()
        if not rows:
            return _fail(source, "Empty response")

        bihar = rows[0]
        ror_pct = bihar.get("rorComputerizedPercent")
        villages_done = bihar.get("villagesComputerizationCompleted")
        villages_total = bihar.get("totalVillage")
        ror_count = bihar.get("rorComputerized")

        value = f"{ror_pct:.1f}% RoR digitised" if ror_pct is not None else "Data fetched"
        detail = (
            f"{format_count(ror_count or 0)} records · "
            f"{villages_done:,}/{villages_total:,} villages computerised"
            if villages_done and villages_total
            else ""
        )

        return _ok(
            value,
            "DILRMP MIS (live)",
            source,
            detail=detail,
            raw={
                "rorComputerizedPercent": ror_pct,
                "villagesComputerizationCompleted": villages_done,
                "totalVillage": villages_total,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(source, str(exc))


def fetch_dilrmp_national() -> dict[str, Any]:
    """National DILRMP snapshot — used to contextualise Bihar."""
    source = "dilrmp.gov.in"
    url = "https://dilrmp.gov.in/getDashboardData"
    try:
        resp = _request_get(url, verify=False)
        data = resp.json().get("nationalDashBordDTOList", {})
        pct = data.get("rorComputerizedPercent")
        count = data.get("rorComputerized")
        return _ok(
            f"{pct:.1f}% nationally" if pct else "National data fetched",
            "DILRMP MIS (live)",
            source,
            detail=f"{format_count(count or 0)} RoR records nationally",
            raw={"rorComputerizedPercent": pct},
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(source, str(exc))


def fetch_bharatnet_bihar() -> dict[str, Any]:
    source = "bbnl.nic.in"
    urls = [
        "https://bbnl.nic.in/new/BBNL_Dashboard.aspx",
        "https://bbnl.nic.in/",
    ]
    for url in urls:
        try:
            resp = requests.get(
                url, headers=HEADERS, timeout=15, verify=False
            )
            resp.raise_for_status()
            text = resp.text
            # Look for Bihar + percentage patterns in dashboard HTML
            patterns = [
                r"Bihar[^0-9]{0,40}([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
                r"BIHAR[^0-9]{0,40}([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
                r"service[- ]ready[^0-9]{0,30}([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.I)
                if match:
                    pct = match.group(1)
                    return _ok(
                        f"{pct}% GPs service-ready",
                        "BBNL MIS (live scrape)",
                        source,
                        detail="Extracted from BBNL dashboard page",
                    )

            soup = BeautifulSoup(text, "html.parser")
            for cell in soup.find_all(string=re.compile(r"Bihar", re.I)):
                parent_text = cell.parent.get_text(" ", strip=True) if cell.parent else ""
                pct_match = re.search(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%", parent_text)
                if pct_match:
                    return _ok(
                        f"{pct_match.group(1)}% GPs service-ready",
                        "BBNL MIS (live scrape)",
                        source,
                        detail=parent_text[:120],
                    )
        except Exception:
            continue

    return _fail(source, "Could not parse Bihar GP stats from BBNL dashboard")


def fetch_njdg_bihar() -> dict[str, Any]:
    source = "njdg.ecourts.gov.in"
    url = "https://njdg.ecourts.gov.in/njdg_v3/?p=home/fetchDist&state_code=10"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # District list confirms connectivity; fetch pending via home page scrape
        home = requests.get(
            "https://njdg.ecourts.gov.in/njdg_v3/?p=home",
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        home.raise_for_status()
        html = home.text

        # National pending totals visible on home dashboard widgets
        reg_match = re.search(
            r"getAlertData\('pending','2'\)[^>]*>\s*([0-9,]+)", html, re.I
        )
        trial_match = re.search(
            r"getAlertData\('pending','3'\)[^>]*>\s*([0-9,]+)", html, re.I
        )

        if reg_match and trial_match:
            reg = int(reg_match.group(1).replace(",", ""))
            trial = int(trial_match.group(1).replace(",", ""))
            total = reg + trial
            return _ok(
                f"{format_count(total)} pending (all-India)",
                "NJDG home dashboard (live)",
                source,
                detail=(
                    f"Registration: {reg:,} · Trial: {trial:,} — "
                    "national widget; filter Bihar in NJDG for district breakdown"
                ),
                raw={"pending_registration": reg, "pending_trial": trial},
            )

        pending_reg = reg_match
        pending_trial = trial_match

        if pending_reg and pending_trial:
            reg = int(pending_reg.group(1).replace(",", ""))
            trial = int(pending_trial.group(1).replace(",", ""))
            total = reg + trial
            return _ok(
                f"{format_count(total)} pending (all-India)",
                "NJDG home dashboard (live)",
                source,
                detail=(
                    f"Registration: {reg:,} · Trial: {trial:,} — "
                    "national widget; filter Bihar in NJDG for district breakdown"
                ),
                raw={"pending_registration": reg, "pending_trial": trial},
            )

        return _fail(source, "Pending case widgets not found on NJDG home")
    except Exception as exc:  # noqa: BLE001
        return _fail(source, str(exc))


def fetch_esanjeevani_bihar() -> dict[str, Any]:
    source = "esanjeevani.mohfw.gov.in"
    try:
        resp = requests.get(
            "https://esanjeevani.mohfw.gov.in/",
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        html = resp.text

        # Public landing page sometimes embeds cumulative consultation counts
        patterns = [
            r"total[^0-9]{0,20}consultations[^0-9]{0,20}([0-9,]+)",
            r"([div][0-9,]+)[^<]{0,40}consultation",
            r"\"totalConsultations\"\s*:\s*([0-9,]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                count = match.group(1).replace(",", "")
                return _ok(
                    f"{format_count(count)} consultations (national)",
                    "eSanjeevani portal (live scrape)",
                    source,
                    detail="National cumulative figure from public portal",
                )

        return _fail(
            source,
            "Portal loads data via authenticated API — public scrape unavailable",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(source, str(exc))


def fetch_soil_health_bihar() -> dict[str, Any]:
    source = "soilhealth.dac.gov.in"
    try:
        resp = requests.get(
            "https://soilhealth.dac.gov.in/",
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            verify=False,
        )
        resp.raise_for_status()
        return _fail(
            source,
            "Dashboard uses GraphQL auth — no public state API without login",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(source, str(exc))


SCRAPERS: dict[str, Any] = {
    "dbt_bihar": fetch_dbt_bihar,
    "dilrmp_bihar": fetch_dilrmp_bihar,
    "bharatnet_bihar": fetch_bharatnet_bihar,
    "njdg_bihar": fetch_njdg_bihar,
    "esanjeevani_bihar": fetch_esanjeevani_bihar,
    "soil_health_bihar": fetch_soil_health_bihar,
}


def fetch_all_live_data() -> dict[str, Any]:
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fn): key for key, fn in SCRAPERS.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[key] = _fail(key, str(exc))

    ok_count = sum(1 for v in results.values() if v.get("status") == "ok")
    return {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(SCRAPERS),
            "ok": ok_count,
            "failed": len(SCRAPERS) - ok_count,
        },
        "sources": results,
    }
