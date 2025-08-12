## Jamf Pro Inactive Mac License Reclaimer

Reclaims licenses by removing inactive Macs from app scopes in Jamf Pro and optionally adding them to a quarantine Static Computer Group.

### What it does
- Finds managed Macs that have not contacted Jamf Pro for N days (using `lastContactTime`)
- (Dry-run by default) Shows which devices would be quarantined and excluded from specified Mac App Store apps (frees VPP licenses)
- Can apply changes when `--apply` is used
- Exports a CSV report of inactive devices

### Prerequisites
- Jamf Pro URL, and one of:
  - OAuth service account (Client Credentials): recommended
  - Or an API user account (will use `/api/auth/tokens`)
- App IDs for the Mac App Store apps you want to reclaim licenses from
- A Static Computer Group ID for quarantining (optional)

### Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r /workspace/jamf_license_reclaimer/requirements.txt
```

### Configure
Copy the example config and edit values:
```bash
cp /workspace/jamf_license_reclaimer/config.example.yaml /workspace/jamf_license_reclaimer/config.yaml
```

Edit `config.yaml`:
- `jamf.base_url`: your Jamf Pro URL
- `jamf.auth`: `oauth` (with `client_id` and `client_secret`) or `user` (with `username`/`password`)
- `policy.days_inactive`: days with no Jamf contact to consider a Mac inactive
- `policy.quarantine_static_group_id`: Static Computer Group ID (optional)
- `mac_app_store_apps`: list of Jamf `macapplications` IDs you want to reclaim

Tip: find IDs by opening the object in Jamf and checking the URL (e.g., `macapplications.html?id=5678`).

### Usage
Dry-run (default):
```bash
python /workspace/jamf_license_reclaimer/reclaim.py --config /workspace/jamf_license_reclaimer/config.yaml
```

Apply changes:
```bash
python /workspace/jamf_license_reclaimer/reclaim.py --config /workspace/jamf_license_reclaimer/config.yaml --apply
```

Override inactivity window:
```bash
python /workspace/jamf_license_reclaimer/reclaim.py --config /workspace/jamf_license_reclaimer/config.yaml --days 90 --apply
```

Disable CSV export:
```bash
python /workspace/jamf_license_reclaimer/reclaim.py --config /workspace/jamf_license_reclaimer/config.yaml --no-export
```

### How it reclaims
- It queries `/api/v1/computers-inventory` with an RSQL filter on `lastContactTime` and `managementStatus.managed==true`.
- For each inactive Mac:
  - Adds it to the configured Static Computer Group (if set).
  - Updates each `macapplications` scope to exclude that Mac, freeing the associated VPP license.

### Notes and extensions
- This sample focuses on Mac App Store (VPP) apps. For third‑party licensing (Adobe, MS, etc.), integrate vendor APIs to unassign seats.
- You can run this on a schedule (cron, GitHub Actions, etc.).
- To reverse upon reactivation, run a companion job that removes devices from the quarantine group and app exclusions if `lastContactTime` is recent.

### Safety
- Runs in dry‑run by default. Use `--apply` to make changes.
- CSV export helps audit what would change before applying.