# Native ARM64 deployment runbook

Target: Orin Nano Super / L4T R36.5.2 / Ubuntu 22.04.5 ARM64, NVMe.
AC and SmartEyes stay native. No production DNS, database or broker changes.
The CI runner is ubuntu-24.04-arm (real ARM64); it is not the runtime base.
The runtime is pinned Python 3.14.10 / Debian trixie and Node 24.22.3, using the
recorded upstream Frappe Docker commit and app release/commit lock. Container
userland supplies its own glibc; no CUDA/L4T user-space libraries are used here.
Pin L4T in the device inventory, not by substituting a CUDA base into Frappe.

## Release/build

GitHub Actions -> Build QY native ARM64 -> Run workflow. No QEMU registration.
Download only a successful run's qy-arm64-release artifact. It includes 4 image
archives (one Docker save tar containing app, MariaDB, Redis and Mosquitto), the
configuration/installer archive, checksum file and validation reports.
Image version qy-arm64-native1 is separate from old QEMU test1. Use a distinct
CUSTOM_IMAGE release tag for subsequent releases; image IDs are recorded.
The multi-stage official recipe excludes compiler toolchains from runtime.
Node build dependencies remain where required by upstream; do not blindly prune
runtime dependencies. All frontend builds happen during image creation.
PDF uses pinned wkhtmltox 0.12.6.1-3 bookworm ARM64 with patched Qt from the
wkhtmltopdf packaging release, exercised both standalone and via Frappe in CI.

## One-command install after bundle extraction

Extract the Actions artifact into a transfer folder, verify SHA256SUMS, and
extract qy-jetson-config.tar.gz into a dedicated deployment folder. Then run:

```bash
sudo BUNDLE_DIR=/absolute/transfer ./install.sh
```

The same installer works with the network disconnected: all app/infra images
and Ubuntu Jammy ARM64 Docker .debs with their complete resolved dependency
closure are included. PACKAGES.lock records exact downloaded versions.
On a blank device, bootstrap-docker.sh installs these packages with
apt --no-download, enables Docker and refuses to replace an existing conflicting
Docker/containerd installation. Existing working Docker/Compose are retained.
Never uninstall NVIDIA container runtime as part of this install.

First run generates 3 separate random passwords in root-readable .env; later
runs preserve them. Installer discovers LAN source IP without making an internet
request; QY_BASE_URL can be overridden explicitly before first install. Frontend
routes requests by the configured site so opening the displayed IP URL works
without a manual hosts entry. Default project/station remain isolated test names.
For production promotion, agree site identity/station and load expected business
data through a separately authorized migration; do not copy live production DB.

Site creation and migration run in the one-time provision container. Reboot only
restarts persistent containers, not install.sh; running installer again may rerun
migration, but retains the database. Preserve all named Docker volumes on NVMe.
CPU and RAM limits are starting profiles for this 8 GB Orin Nano; validate them
under the actual AC workload. Docker logs rotate at 10 MB x 3 per service. Application logs use Frappe logging.
Check `docker compose ps -a`, `docker compose logs --tail=100 provision` and
`sudo docker stats`; credentials should never be pasted into tickets.

## Backup, upgrade, rollback

```bash
sudo ./backup.sh /absolute/new-backup-directory
# Load the next release images first; select a new immutable application tag.
sudo ./upgrade.sh visiontestai/frappe:NEW_TAG /absolute/pre-upgrade-backup
# Explicitly replaces database/files; use only in an authorized recovery window.
sudo ./rollback.sh /absolute/pre-upgrade-backup --restore-data
```

Backup stops application writers, saves an SQL dump, public/private attachments,
site_config.json (including encryption key), deployment .env and old image.
Keep backups off-device with restricted access. An error leaves writers stopped
so the operator can assess consistency. No volume is deleted by these scripts.
Rollback restores data with its previous app image, rather than assuming database
migrations can be undone by switching images. Infrastructure versions are fixed;
these scripts do not implement MariaDB major-version downgrades.

## Release gates

See ACCEPTANCE.md. A successful native CI run does not prove Jetson camera/audio,
physical reboot, offline fresh JetPack, clinical PDF layout or load performance.
A failed-run artifact must not be deployed. Agree size/time/concurrency limits
before final acceptance. Keep >=1 GiB MemAvailable with no sustained swap growth.
With only 1.7 GiB currently available, schedule a maintenance window before
starting this stack beside AC. Never auto-stop or modify production services.

## Device evidence collection

During the real measurement acceptance session run
`sudo python3 device_report.py --seconds 300 --output device-report.json`.
The sampler reads memory/swap/OOM counters; it does not start or reconfigure AC.
After a physical reboot verify `systemctl is-enabled docker`, all persistent
services healthy, login and the same database/file data. Record uptime and the
reboot event separately. A container restart in CI is not a Jetson reboot.
Record offline installation by disconnecting the external network before running
the installer on a fresh device. Do not disconnect an active production station.

## Single-command offline distribution

The release artifact now contains `qy-jetson-install.run` and `SHA256SUMS.run`.
After downloading/extracting the Actions artifact, verify `sha256sum -c
SHA256SUMS.run`, then run exactly:

```bash
sudo bash qy-jetson-install.run
```

This self-extracting file contains all images, configuration, installer and Docker
packages. It installs into /opt/visiontestai-qy by default, retaining .env and data
on rerun. `sudo QY_INSTALL_DIR=/absolute/path bash qy-jetson-install.run` overrides
that directory. `bash qy-jetson-install.run --extract-only DIR` unpacks the three
transfer files for inspection without installing Docker or starting services.
The total installer timing includes extraction when invoked through this bundle.
