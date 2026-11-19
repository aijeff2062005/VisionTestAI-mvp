# Native ARM64 release preparation

Status: installer and workflow scaffolding; NOT a production-certified release.
Existing out/ artifacts were built under QEMU and are unchanged.
Target recorded: Jetson Orin Nano Super, Ubuntu 22.04.5, L4T 36.5.2,
7.4 GiB RAM, Docker Root Dir /var/lib/docker on NVMe.

## Build

Run build.sh then package.sh on a dedicated Linux ARM64 host with local Docker,
Buildx, git and Python 3. build.sh refuses x86/QEMU release builds. The default
local Docker builder must support the pinned upstream recipe. No app build is
performed by install.sh on the target.

The workflow .github/workflows/qy-arm64.yml requires an explicitly registered
self-hosted runner carrying labels Linux, ARM64, qy-builder. It is not provisioned
by this repository. Register it only for trusted code. The workflow must be pushed
to the root of the mvp_platform Git repository to become available in GitHub.

## Install on a prepared Jetson

Docker Engine, Compose plugin, Python 3 and curl must already be installed.
Place all three release files in one transfer directory; verify SHA256SUMS there.
Extract qy-jetson-config.tar.gz into a dedicated directory, then run:

```bash
sudo BUNDLE_DIR=/absolute/path/to/transfer ./install.sh
```

On first installation environment variables override .env.example. Subsequent
runs preserve .env. Set QY_SITE, QY_BASE_URL and STATION_ID deliberately for the
installation. Default values remain isolated QY test values. Configure client DNS
or hosts entries so qy-test.lan resolves to the Jetson. Installer reports the URL
only after ping succeeds; ping alone does not validate the clinical workflow.
Credentials are in .env, not printed to logs. Do not publish that file.

Compose restart policies restart long-running containers after Docker starts.
Enable Docker at boot using the device's service manager and verify a real reboot.
Re-running the installer may rerun the existing provisioner's migration; reboot
alone does not invoke the installer. Do not run multiple installers concurrently.

## Backup, upgrade and recovery requirements

Before upgrade: record the current image ID, preserve .env securely, and create
an off-device backup using bench --site SITE backup --with-files. Include the
site_config.json encryption key. Verify database/public/private backup files.
Stop writes and workers during the final consistent backup and upgrade window.
Load the next release, change CUSTOM_IMAGE, migrate with the release provisioner,
then verify login, assets, worker, websocket and QY measurement callback.
Database migrations may be irreversible: rollback requires restoring the matching
pre-upgrade database and files together with the old image. Never use down -v.
A timed restore drill and automated backup/restore tooling remain release gates.

## Remaining acceptance gates

- Native ARM64 build and dependency/PDF testing, plus browser VisionCare check.
- All service healthchecks and resource limits validated under real AC workload.
- Worker job, scheduler, websocket, reboot and attachment persistence tests.
- Fully offline fresh-JetPack bootstrap: include pinned OS-matched Docker and
  dependency packages. Current installer refuses missing prerequisites rather
  than silently downloading them. This is not yet a one-command bare-device kit.
- Decide measured image/install-time/concurrency thresholds with device owner.
- Keep >=1 GiB MemAvailable under workload, no sustained swap growth or OOM.
- Test backup/restore and image+database rollback before production promotion.

Do not change production AC, MQTT or DNS as part of this isolated deployment.
