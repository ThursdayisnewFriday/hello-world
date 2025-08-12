#!/usr/bin/env python3
"""
Jamf Pro automation script

Purpose:
- Retrieve members (Macs) of a Jamf Pro Smart Computer Group
- For each device, automatically perform one of the following actions:
  - Remove a configuration profile by its profile identifier (MDM RemoveProfile command), or
  - Unmanage the device (MDM UnmanageDevice command)

Authentication:
- Uses Bearer Token for requests. You can either:
  1) Provide an already generated Bearer Token via env `JAMF_BEARER_TOKEN`, or
  2) Provide `JAMF_USERNAME` and `JAMF_PASSWORD`; the script will obtain a token via `/api/v1/auth/token`.

Safety:
- Supports `DRY_RUN=true` to preview what would happen without sending any destructive commands.

Configuration via environment variables:
- JAMF_URL              (required) Base URL to Jamf Pro, e.g. https://yourcompany.jamfcloud.com
- SMART_GROUP_ID        (optional) Defaults to 123, the smart group id to process
- ACTION                (optional) "remove_profile" (default) or "unmanage"
- PROFILE_IDENTIFIER    (required for ACTION=remove_profile) e.g. com.company.profile.identifier
- JAMF_BEARER_TOKEN     (optional) If present, used directly
- JAMF_USERNAME         (optional) Username used to generate bearer token if JAMF_BEARER_TOKEN not provided
- JAMF_PASSWORD         (optional) Password used to generate bearer token if JAMF_BEARER_TOKEN not provided
- VERIFY_SSL            (optional) "true" (default) or "false" to disable TLS verification (self-signed)
- DRY_RUN               (optional) "false" (default) or "true" to print planned actions only

Notes:
- This script uses the Classic API endpoint to fetch smart group membership and send MDM commands.
  The Bearer Token generated from `/api/v1/auth/token` is valid for both the Classic and Jamf Pro APIs.
- Removing a configuration profile requires the exact profile identifier installed on the device.

Usage example:
  SMART_GROUP_ID=123 ACTION=remove_profile PROFILE_IDENTIFIER=com.company.security.vpn \
  JAMF_URL="https://yourcompany.jamfcloud.com" JAMF_USERNAME="apiuser" JAMF_PASSWORD="apipass" \
  python3 jamf_maintenance.py

  # Or with a pre-generated bearer token
  JAMF_URL="https://yourcompany.jamfcloud.com" JAMF_BEARER_TOKEN="eyJhbGciOi..." \
  python3 jamf_maintenance.py
"""
from __future__ import annotations

import os
import sys
import time
from typing import Dict, List, Optional, Tuple, Any

import requests


class JamfClient:
    """Lightweight client for Jamf Pro APIs with Bearer Token auth and basic retry logic."""

    def __init__(
        self,
        base_url: str,
        bearer_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_ssl: bool = True,
    ) -> None:
        # Normalize base_url by stripping trailing slashes
        self.base_url: str = base_url.rstrip("/")
        self._explicit_token: Optional[str] = bearer_token
        self._username: Optional[str] = username
        self._password: Optional[str] = password
        self._token_cache: Optional[str] = None
        self.verify_ssl: bool = verify_ssl

    # -------------------------
    # Authentication management
    # -------------------------
    def get_bearer_token(self) -> str:
        """Return a valid Bearer Token, using provided token or obtaining a new one via API.

        Preference order:
          1) Use explicitly provided token (`JAMF_BEARER_TOKEN`)
          2) Generate via `/api/v1/auth/token` using `JAMF_USERNAME`/`JAMF_PASSWORD`
        """
        if self._explicit_token:
            return self._explicit_token

        if self._token_cache:
            return self._token_cache

        if not (self._username and self._password):
            raise RuntimeError(
                "No bearer token provided and missing JAMF_USERNAME/JAMF_PASSWORD to generate one."
            )

        auth_url = f"{self.base_url}/api/v1/auth/token"
        print(f"[auth] Requesting Bearer Token from {auth_url}")
        try:
            response = requests.post(
                auth_url,
                auth=(self._username, self._password),  # HTTP Basic auth
                headers={"Accept": "application/json"},
                timeout=30,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to connect to Jamf auth endpoint: {exc}") from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to obtain token (HTTP {response.status_code}): {response.text}"
            )

        try:
            token_json = response.json()
            token = token_json.get("token") or token_json.get("bearerToken")
        except ValueError as exc:
            raise RuntimeError(f"Unexpected auth response (not JSON): {response.text}") from exc

        if not token:
            raise RuntimeError(f"Token not present in auth response: {response.text}")

        # Cache for this run
        self._token_cache = token
        print("[auth] Bearer Token obtained successfully")
        return token

    def invalidate_bearer_token(self) -> None:
        """Invalidate the current Bearer Token if it was generated by this client."""
        # Only invalidate if we generated it (i.e., not an explicitly provided token).
        if not self._token_cache:
            return
        token = self._token_cache
        url = f"{self.base_url}/api/v1/auth/invalidate-token"
        print(f"[auth] Invalidating Bearer Token at {url}")
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                timeout=30,
                verify=self.verify_ssl,
            )
            if response.status_code in (200, 204):
                print("[auth] Token invalidated successfully")
            else:
                print(
                    f"[auth] Warning: token invalidation returned HTTP {response.status_code}: {response.text}"
                )
        except requests.RequestException as exc:
            print(f"[auth] Warning: exception while invalidating token: {exc}")

    # -----------------
    # HTTP request util
    # -----------------
    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        expected_statuses: Tuple[int, ...] = (200,),
        attempt_count: int = 3,
        backoff_seconds: float = 1.0,
    ) -> requests.Response:
        """Internal request with retries, Bearer auth, and status validation.

        - `endpoint` must start with "/" and is appended to `base_url`.
        - Retries on network-level errors and on 429/5xx responses.
        """
        if not endpoint.startswith("/"):
            raise ValueError("endpoint must start with '/'")

        url = f"{self.base_url}{endpoint}"
        token = self.get_bearer_token()
        merged_headers: Dict[str, str] = {"Authorization": f"Bearer {token}"}
        if headers:
            merged_headers.update(headers)

        for attempt_index in range(1, attempt_count + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    data=data,
                    headers=merged_headers,
                    timeout=60,
                    verify=self.verify_ssl,
                )
            except requests.RequestException as exc:
                print(
                    f"[http] Attempt {attempt_index}/{attempt_count} failed with exception: {exc}"
                )
                if attempt_index >= attempt_count:
                    raise
                time.sleep(backoff_seconds * attempt_index)
                continue

            # Retry on Too Many Requests or server errors
            if response.status_code in (429, 500, 502, 503, 504):
                print(
                    f"[http] Attempt {attempt_index}/{attempt_count} received HTTP {response.status_code}; retrying..."
                )
                if attempt_index >= attempt_count:
                    # Return (and let caller decide) or raise. We raise for consistency.
                    response.raise_for_status()
                time.sleep(backoff_seconds * attempt_index)
                continue

            # Break out if status is one of expected
            if response.status_code in expected_statuses:
                return response

            # Otherwise, raise with helpful info
            raise requests.HTTPError(
                f"Unexpected HTTP {response.status_code} for {method} {url}: {response.text}",
                response=response,
            )

        # Should not be reachable
        raise RuntimeError("HTTP retry loop exited unexpectedly")

    # --------------------------------------
    # Classic API: Smart group and commands
    # --------------------------------------
    def get_smart_group_computers(self, group_id: int) -> List[Dict[str, Any]]:
        """Return the list of computers in the specified smart group.

        Uses the Classic API endpoint: GET /JSSResource/computergroups/id/{id}
        Response contains a `computers` array with objects having keys like id, name, serial_number.
        """
        endpoint = f"/JSSResource/computergroups/id/{group_id}"
        print(f"[group] Fetching smart group membership: {endpoint}")
        response = self._request(
            "GET",
            endpoint,
            headers={"Accept": "application/json"},
            expected_statuses=(200,),
        )
        try:
            group_json = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Group response is not JSON: {response.text}") from exc

        computers = group_json.get("computer_group", {}).get("computers", [])
        print(f"[group] Found {len(computers)} computer(s) in group {group_id}")
        return computers

    def send_remove_profile_command(self, computer_id: int, profile_identifier: str) -> None:
        """Send the RemoveProfile MDM command to a specific computer via Classic API.

        Endpoint form (no body required):
        POST /JSSResource/computercommands/command/RemoveProfile/identifier/{identifier}/id/{id}
        """
        endpoint = (
            f"/JSSResource/computercommands/command/RemoveProfile/identifier/"
            f"{requests.utils.quote(profile_identifier, safe='')}/id/{computer_id}"
        )
        print(
            f"[command] Sending RemoveProfile for identifier='{profile_identifier}' to computer id={computer_id}"
        )
        self._request(
            "POST",
            endpoint,
            headers={"Accept": "application/json"},
            expected_statuses=(200, 201),
        )

    def send_unmanage_device_command(self, computer_id: int) -> None:
        """Send the UnmanageDevice MDM command to a specific computer via Classic API.

        Endpoint:
        POST /JSSResource/computercommands/command/UnmanageDevice/id/{id}
        """
        endpoint = f"/JSSResource/computercommands/command/UnmanageDevice/id/{computer_id}"
        print(f"[command] Sending UnmanageDevice to computer id={computer_id}")
        self._request(
            "POST",
            endpoint,
            headers={"Accept": "application/json"},
            expected_statuses=(200, 201),
        )


def env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable with a default."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    # -----------------
    # Read configuration
    # -----------------
    jamf_url = os.environ.get("JAMF_URL", "").strip()
    if not jamf_url:
        print("[config] ERROR: JAMF_URL is required (e.g., https://yourcompany.jamfcloud.com)")
        return 2

    smart_group_id_str = os.environ.get("SMART_GROUP_ID", "123").strip()
    action = os.environ.get("ACTION", "remove_profile").strip().lower()
    profile_identifier = os.environ.get("PROFILE_IDENTIFIER", "").strip()

    # Authentication inputs
    bearer_token = os.environ.get("JAMF_BEARER_TOKEN")
    username = os.environ.get("JAMF_USERNAME")
    password = os.environ.get("JAMF_PASSWORD")

    verify_ssl = env_bool("VERIFY_SSL", True)
    dry_run = env_bool("DRY_RUN", False)

    # Validate smart group id
    try:
        smart_group_id = int(smart_group_id_str)
    except ValueError:
        print(f"[config] ERROR: SMART_GROUP_ID must be an integer, got '{smart_group_id_str}'")
        return 2

    # Validate action and required params
    if action not in {"remove_profile", "unmanage"}:
        print("[config] ERROR: ACTION must be either 'remove_profile' or 'unmanage'")
        return 2

    if action == "remove_profile" and not profile_identifier:
        print(
            "[config] ERROR: PROFILE_IDENTIFIER is required when ACTION=remove_profile (e.g., com.company.profile)"
        )
        return 2

    if not (bearer_token or (username and password)):
        print(
            "[config] ERROR: Provide JAMF_BEARER_TOKEN or JAMF_USERNAME and JAMF_PASSWORD to authenticate"
        )
        return 2

    print("[config] Configuration loaded:")
    print(f"         JAMF_URL          = {jamf_url}")
    print(f"         SMART_GROUP_ID    = {smart_group_id}")
    print(f"         ACTION            = {action}")
    if action == "remove_profile":
        print(f"         PROFILE_IDENTIFIER = {profile_identifier}")
    print(f"         VERIFY_SSL        = {verify_ssl}")
    print(f"         DRY_RUN           = {dry_run}")

    # -----------------------
    # Initialize Jamf client
    # -----------------------
    client = JamfClient(
        base_url=jamf_url,
        bearer_token=bearer_token,
        username=username,
        password=password,
        verify_ssl=verify_ssl,
    )

    # Ensure token works
    try:
        _ = client.get_bearer_token()
    except Exception as exc:  # noqa: BLE001 - provide user-friendly message
        print(f"[auth] ERROR: {exc}")
        return 1

    # --------------------------------------
    # Fetch members of the smart group (id)
    # --------------------------------------
    try:
        computers = client.get_smart_group_computers(smart_group_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[group] ERROR: {exc}")
        client.invalidate_bearer_token()
        return 1

    if not computers:
        print("[group] No computers found in the specified smart group. Nothing to do.")
        client.invalidate_bearer_token()
        return 0

    # ----------------------------------------
    # Iterate over devices and perform actions
    # ----------------------------------------
    failures: List[str] = []
    success_count: int = 0

    print(f"[run] Processing {len(computers)} device(s) in smart group {smart_group_id}...")
    for device in computers:
        # Each `device` dict minimally contains 'id' and 'name'; serial_number may be present too
        device_id = device.get("id")
        device_name = device.get("name") or "<unknown>"
        serial_number = device.get("serial_number") or ""

        if not isinstance(device_id, int):
            print(f"[skip] Device has missing/invalid id: {device}")
            failures.append(f"invalid_id:{device}")
            continue

        print(
            f"[device] id={device_id}, name='{device_name}', serial='{serial_number}' -> action={action}"
        )

        if dry_run:
            print("[dryrun] Skipping command send (DRY_RUN=true)")
            success_count += 1
            continue

        try:
            if action == "remove_profile":
                client.send_remove_profile_command(device_id, profile_identifier)
            elif action == "unmanage":
                client.send_unmanage_device_command(device_id)
            else:
                # Should not occur due to earlier validation
                raise RuntimeError(f"Unsupported action: {action}")
        except requests.HTTPError as http_exc:
            # Provide a concise, actionable error including HTTP status
            status = getattr(http_exc.response, "status_code", "?")
            body = getattr(http_exc.response, "text", "")
            print(
                f"[error] HTTP {status} while processing device id={device_id} ({device_name}): {body}"
            )
            failures.append(f"id={device_id}:http_{status}")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"[error] Exception while processing device id={device_id} ({device_name}): {exc}")
            failures.append(f"id={device_id}:{exc}")
            continue

        print(f"[ok] Command queued for device id={device_id} ({device_name})")
        success_count += 1

    # Attempt to invalidate the generated token (if any)
    client.invalidate_bearer_token()

    # ------------------------------
    # Final result and exit status
    # ------------------------------
    print("[done] Summary:")
    print(f"       Success: {success_count}")
    print(f"       Failed : {len(failures)}")
    if failures:
        print("       Failure details:")
        for item in failures:
            print(f"         - {item}")

    # Non-zero exit if any failures
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())