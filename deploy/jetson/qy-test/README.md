# QY Frappe on NVIDIA Jetson ARM64

Native ARM64 release tooling for Orin Nano Super / Ubuntu 22.04 / L4T R36.5.2.
AC/SmartEyes remain native; the Docker stack contains QY Frappe, ERPNext,
Healthcare, Solvronix Desk, smart_hospital, qy_vision_hospital, MariaDB,
Redis cache/queue, Mosquitto, worker, scheduler, websocket and Nginx.

- [Deployment, offline install, backup, upgrade and rollback](PRODUCTION.md)
- [Ticket acceptance matrix and remaining hardware checks](ACCEPTANCE.md)
- [Pinned app versions](sources.lock.json)

Run the `Build QY native ARM64` GitHub workflow. Download a successful run's
artifact, extract it, verify SHA256SUMS and extract qy-jetson-config.tar.gz into a
separate deployment directory. From that directory run one installer command:

```bash
sudo BUNDLE_DIR=/absolute/path/to/transfer ./install.sh
```

The bundle includes the Docker packages for a blank Ubuntu 22.04 ARM64 device;
it does not need internet during installation. No build happens on Jetson.
The installer retains existing .env and volumes. It prints the LAN URL and
stores generated credentials in root-readable .env. Never commit or share .env.

Old RESULT.md, BUILD_ENVIRONMENT.md and VERSION_CHECK.md document the historical
QEMU test1 build. They do not certify the native release. Existing out/ files on
Coder are still that historical build until explicitly replaced by a successful
native release artifact. No production-ready claim is made without real Jetson
acceptance, agreed performance limits and a successful restore drill.

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
