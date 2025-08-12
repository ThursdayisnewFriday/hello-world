#!/usr/bin/env python3
import argparse
import csv
import dataclasses
import datetime as dt
import os
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

import requests
import yaml

ISO8601 = "%Y-%m-%dT%H:%M:%SZ"


@dataclasses.dataclass
class JamfConfig:
    base_url: str
    auth: str  # "oauth" or "user"
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


@dataclasses.dataclass
class PolicyConfig:
    days_inactive: int
    dry_run: bool
    quarantine_static_group_id: Optional[int] = None


@dataclasses.dataclass
class AppConfig:
    id: int
    name: Optional[str] = None


@dataclasses.dataclass
class ReportingConfig:
    output_dir: str = "./output"
    export_inactive_csv: bool = True


@dataclasses.dataclass
class Config:
    jamf: JamfConfig
    policy: PolicyConfig
    mac_app_store_apps: List[AppConfig]
    reporting: ReportingConfig


@dataclasses.dataclass
class Computer:
    id: int
    serial_number: str
    computer_name: str
    last_contact_time: Optional[str]
    user_email: Optional[str]
    username: Optional[str]


class JamfClient:
    def __init__(self, jamf: JamfConfig, session: Optional[requests.Session] = None) -> None:
        if not jamf.base_url:
            raise ValueError("Jamf base_url is required")
        self.base_url = jamf.base_url.rstrip('/')
        self.jamf = jamf
        self.session = session or requests.Session()
        self.token: Optional[str] = None

    def _headers(self, accept: str = "application/json") -> Dict[str, str]:
        if not self.token:
            raise RuntimeError("API token is not initialized")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
        }
        # For JSON writes, caller sets Content-Type
        return headers

    # ---- Auth ----
    def authenticate(self) -> None:
        if self.jamf.auth.lower() == "oauth":
            self.token = self._get_oauth_token(
                client_id=self.jamf.client_id,
                client_secret=self.jamf.client_secret,
            )
        elif self.jamf.auth.lower() == "user":
            self.token = self._get_user_token(
                username=self.jamf.username,
                password=self.jamf.password,
            )
        else:
            raise ValueError("Unsupported auth type. Use 'oauth' or 'user'.")

    def _get_oauth_token(self, client_id: Optional[str], client_secret: Optional[str]) -> str:
        if not client_id or not client_secret:
            raise ValueError("OAuth client_id and client_secret are required for oauth auth")
        url = f"{self.base_url}/api/oauth/token"
        data = {"grant_type": "client_credentials"}
        resp = self.session.post(url, data=data, auth=(client_id, client_secret))
        if resp.status_code != 200:
            raise RuntimeError(f"OAuth token request failed: {resp.status_code} {resp.text}")
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("OAuth token missing in response")
        return token

    def _get_user_token(self, username: Optional[str], password: Optional[str]) -> str:
        if not username or not password:
            raise ValueError("Username and password are required for user auth")
        url = f"{self.base_url}/api/auth/tokens"
        resp = self.session.post(url, auth=(username, password))
        if resp.status_code != 200:
            raise RuntimeError(f"User token request failed: {resp.status_code} {resp.text}")
        token = resp.json().get("token")
        if not token:
            raise RuntimeError("User token missing in response")
        return token

    # ---- Inventory ----
    def find_inactive_computers(self, days_inactive: int) -> List[Computer]:
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=days_inactive)
        cutoff_iso = cutoff.strftime(ISO8601)
        url = f"{self.base_url}/api/v1/computers-inventory"
        params = {
            "section": [
                "GENERAL",
                "USER_AND_LOCATION",
            ],
            # RSQL filter: lastContactTime before cutoff and still managed
            "filter": f"lastContactTime<{cutoff_iso};managementStatus.managed==true",
            "page": 0,
            "page-size": 200,
            "sort": "id:asc",
        }
        computers: List[Computer] = []
        while True:
            resp = self.session.get(url, headers=self._headers(), params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"Inventory query failed: {resp.status_code} {resp.text}")
            data = resp.json()
            results = data.get("results", [])
            for item in results:
                general = item.get("general", {})
                userloc = item.get("userAndLocation", {})
                computers.append(
                    Computer(
                        id=item.get("id"),
                        serial_number=general.get("serialNumber"),
                        computer_name=general.get("name"),
                        last_contact_time=general.get("lastContactTime"),
                        user_email=userloc.get("email"),
                        username=userloc.get("username"),
                    )
                )
            total_count = data.get("totalCount")
            page = data.get("page", params["page"])  # Jamf may echo current page
            page_size = data.get("pageSize", params["page-size"])  # Jamf may echo size
            if total_count is None:
                # Fallback: if no pagination metadata, stop when results < requested page-size
                if len(results) < params["page-size"]:
                    break
                params["page"] += 1
                continue
            # Calculate next page
            next_offset = (page + 1) * page_size
            if next_offset >= total_count:
                break
            params["page"] = page + 1
        return computers

    # ---- Static Group management (Classic API; XML) ----
    def add_computer_to_static_group(self, group_id: int, computer_id: int) -> None:
        url = f"{self.base_url}/JSSResource/computergroups/id/{group_id}"
        xml = f"""
        <computer_group>
          <id>{group_id}</id>
          <computer_additions>
            <computer>
              <id>{computer_id}</id>
            </computer>
          </computer_additions>
        </computer_group>
        """.strip()
        headers = self._headers(accept="application/xml")
        headers["Content-Type"] = "application/xml"
        resp = self.session.put(url, headers=headers, data=xml.encode("utf-8"))
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Add to static group failed (group {group_id}, computer {computer_id}): {resp.status_code} {resp.text}")

    # ---- Mac App Store app scope exclusions (Classic API; XML) ----
    def exclude_computer_from_mac_app(self, app_id: int, computer_id: int) -> None:
        # Pull current scope subset, add computer to <scope><exclusions><computers>
        get_url = f"{self.base_url}/JSSResource/macapplications/id/{app_id}/subset/scope"
        headers = self._headers(accept="application/xml")
        resp = self.session.get(get_url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Fetch app scope failed (app {app_id}): {resp.status_code} {resp.text}")
        xml_text = resp.text
        # Minimal insertion without full XML parsing: append a new computer exclusion if not present
        marker = "<computers>"
        end_marker = "</computers>"
        if marker not in xml_text:
            # Create the exclusions/computers block inside <exclusions>
            exclusions_marker = "<exclusions>"
            if exclusions_marker not in xml_text:
                # Create full exclusions block just before </scope>
                xml_text = xml_text.replace(
                    "</scope>",
                    f"<exclusions><computers><computer><id>{computer_id}</id></computer></computers></exclusions></scope>",
                )
            else:
                xml_text = xml_text.replace(
                    exclusions_marker,
                    f"<exclusions><computers><computer><id>{computer_id}</id></computer></computers>",
                )
        else:
            # If the computer is already listed, avoid duplicates
            if f"<id>{computer_id}</id>" in xml_text:
                # No change needed
                pass
            else:
                xml_text = xml_text.replace(
                    marker,
                    f"<computers><computer><id>{computer_id}</id></computer>",
                )
        put_url = f"{self.base_url}/JSSResource/macapplications/id/{app_id}/subset/scope"
        put_headers = self._headers(accept="application/xml")
        put_headers["Content-Type"] = "application/xml"
        put_resp = self.session.put(put_url, headers=put_headers, data=xml_text.encode("utf-8"))
        if put_resp.status_code not in (200, 201):
            raise RuntimeError(f"Update app scope failed (app {app_id}, computer {computer_id}): {put_resp.status_code} {put_resp.text}")


# ---- Helpers ----

def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    jamf = JamfConfig(**raw["jamf"])  # type: ignore[arg-type]
    policy = PolicyConfig(**raw["policy"])  # type: ignore[arg-type]
    apps = [AppConfig(**a) for a in raw.get("mac_app_store_apps", [])]
    reporting = ReportingConfig(**raw.get("reporting", {}))
    return Config(jamf=jamf, policy=policy, mac_app_store_apps=apps, reporting=reporting)


def ensure_output_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def export_inactive_csv(path: str, computers: List[Computer]) -> None:
    fieldnames = [
        "id",
        "serial_number",
        "computer_name",
        "last_contact_time",
        "username",
        "user_email",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in computers:
            writer.writerow(
                {
                    "id": c.id,
                    "serial_number": c.serial_number,
                    "computer_name": c.computer_name,
                    "last_contact_time": c.last_contact_time or "",
                    "username": c.username or "",
                    "user_email": c.user_email or "",
                }
            )


# ---- Main flow ----

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Jamf Pro inactive Mac license reclaimer")
    p.add_argument("--config", default="/workspace/jamf_license_reclaimer/config.yaml", help="Path to YAML config")
    p.add_argument("--days", type=int, default=None, help="Override days inactive (default from config)")
    p.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    p.add_argument("--no-export", action="store_true", help="Disable CSV export")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not os.path.exists(args.config):
        print(f"Config file not found: {args.config}", file=sys.stderr)
        return 2
    cfg = load_config(args.config)

    # Runtime overrides
    if args.days is not None:
        cfg.policy.days_inactive = args.days
    if args.apply:
        cfg.policy.dry_run = False
    if args.no_export:
        cfg.reporting.export_inactive_csv = False

    client = JamfClient(cfg.jamf)
    client.authenticate()

    print(f"Searching for Macs inactive for >= {cfg.policy.days_inactive} days...")
    inactive = client.find_inactive_computers(cfg.policy.days_inactive)
    print(f"Found {len(inactive)} inactive managed Macs")

    if cfg.reporting.export_inactive_csv:
        ensure_output_dir(cfg.reporting.output_dir)
        export_path = os.path.join(
            cfg.reporting.output_dir,
            f"inactive_macs_{cfg.policy.days_inactive}d_{dt.datetime.utcnow().strftime('%Y%m%d')}.csv",
        )
        export_inactive_csv(export_path, inactive)
        print(f"Exported inactive list to {export_path}")

    if not inactive:
        print("No inactive devices found. Exiting.")
        return 0

    # Apply actions per device
    errors: List[str] = []
    for comp in inactive:
        prefix = "[DRY-RUN] " if cfg.policy.dry_run else ""
        print(f"{prefix}Processing computer id={comp.id} name={comp.computer_name} serial={comp.serial_number}")
        # Quarantine static group
        if cfg.policy.quarantine_static_group_id:
            try:
                if cfg.policy.dry_run:
                    print(
                        f"{prefix}Would add computer {comp.id} to static group {cfg.policy.quarantine_static_group_id}"
                    )
                else:
                    client.add_computer_to_static_group(cfg.policy.quarantine_static_group_id, comp.id)
                    print(
                        f"Added computer {comp.id} to static group {cfg.policy.quarantine_static_group_id}"
                    )
            except Exception as e:
                msg = f"Failed to add to static group for computer {comp.id}: {e}"
                print(msg, file=sys.stderr)
                errors.append(msg)
        # Exclude from Mac App Store app scopes to reclaim VPP licenses
        for app in cfg.mac_app_store_apps:
            try:
                if cfg.policy.dry_run:
                    print(f"{prefix}Would exclude computer {comp.id} from app id {app.id} ({app.name or ''})")
                else:
                    client.exclude_computer_from_mac_app(app.id, comp.id)
                    print(f"Excluded computer {comp.id} from app id {app.id} ({app.name or ''})")
            except Exception as e:
                msg = f"Failed to update app scope for computer {comp.id}, app {app.id}: {e}"
                print(msg, file=sys.stderr)
                errors.append(msg)

    if errors:
        print(f"Completed with {len(errors)} errors.")
        return 1
    print("All actions completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())