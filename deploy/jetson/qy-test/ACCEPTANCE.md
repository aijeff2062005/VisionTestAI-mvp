# Release acceptance matrix

No native release is certified until the workflow succeeds and the device checks
below are recorded. An Actions artifact from a failed run is diagnostic only.

| Ticket criterion | Automated native CI | Required on Jetson |
|---|---|---|
| 1. One-command install + LAN + admin login | Installer, login, Desk route | Fresh JetPack install, second LAN client |
| 2. Services healthy + automatic boot | All 9 persistent services healthy, stop/start | Physical reboot, Docker enabled |
| 3. Size and install time within agreed limits | Image inspect, install-report.json | Owner-defined limits and measured timing |
| 4. ARM64 PDF | Patched-Qt engine + Frappe PDF text assertion | Actual clinical print format and visual layout |
| 5. Background job | RQ job enqueued and completed | Scheduler execution and logs during clinical workload |
| 6. Offline fresh install + migration | All images/debs packaged, no runtime pull | Network disconnected, fresh JetPack, installer |
| 7. Database and attachments survive reboot | File document + bytes survive stop/start and restore | Physical reboot with same checks |

Additional QY acceptance: start/cancel session, camera/audio, SmartEyes callback,
realtime updates and no production writes. Keep >=1 GiB MemAvailable throughout,
no OOM or sustained swap growth. Current device report of 1.7 GiB available
requires a maintenance window and resource monitoring before adding this stack.

No image-size, install-time or concurrency limits were supplied by the owner.
Record agreed limits here; do not invent a passing threshold after measurement.
