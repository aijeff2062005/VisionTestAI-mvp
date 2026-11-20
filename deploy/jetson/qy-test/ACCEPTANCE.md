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
| 6. Offline fresh install + migration | All images/debs packaged; Docker package closure installed with network disabled | Network disconnected, fresh JetPack, installer |
| 7. Database and attachments survive reboot | File document + bytes survive stop/start and restore | Physical reboot with same checks |

Additional QY acceptance: start/cancel session, camera/audio, SmartEyes callback,
realtime updates and no production writes. Keep >=1 GiB MemAvailable throughout,
no OOM or sustained swap growth. Current device report of 1.7 GiB available
requires a maintenance window and resource monitoring before adding this stack.

No image-size, install-time or concurrency limits were supplied by the owner.
Record agreed limits here; do not invent a passing threshold after measurement.

Owner decision: no formal size, installation-time or concurrency thresholds yet.
Record actual image/archive bytes, install elapsed seconds, CI machine specs and
1/3/5 distinct authenticated users on read-only patient/queue endpoints in
acceptance-measurements.json. These are characterization measurements, not a
maximum supported user count or proof of clinical workload capacity. Attachment
upload maximum is separately unmeasured. All performance criteria stay UNDECIDED.

## Validated native candidate — 2026-11-20

Full native build and all software integration checks succeeded in
https://github.com/aijeff2062005/VisionTestAI-mvp/actions/runs/44653614307
Source commit: b6e22d50e2d3e73fe9d1bf7496cd02ab943f19f9.
Permanent candidate/evidence: GitHub Releases draft qy-jetson-native-rc-44653614307.

Observed configuration: ubuntu-24.04-arm, 4 logical CPUs, MemTotal
16,324,144 KiB, kernel 7.0.0-1017-azure, host glibc 2.39. Application container
uses its own pinned Python 3.14.10 / Debian trixie userland and Node 24.22.3.
Runtime CPU/RAM limits are those in compose.yml; this VM is not the 7.4 GiB Jetson.

| Observation | Actual result | Acceptance threshold |
|---|---|---|
| Largest image, uncompressed | 3,212,721,290 bytes | UNDECIDED |
| Four-image compressed archive | 1,118,809,021 bytes | UNDECIDED |
| Complete self-extracting installer | 1,216,574,830 bytes | UNDECIDED |
| Installer elapsed time | 160 seconds | UNDECIDED |
| Concurrent authenticated accounts tested | 1, 3, 5 | UNDECIDED |

Timing method: start of the self-extracting installer through setup completion,
nine healthy persistent services and HTTP ping. CI already had Docker and the
images loaded by the preceding build. It excludes downloading the bundle and
does not measure a blank JetPack installation or Jetson installation speed.
Offline Docker dependency closure was independently installed in an Ubuntu 22.04
ARM64 container with `--network none` and `apt --no-download`.

Load method: distinct synthetic System Manager accounts, each reading patient
list and measurement queue five times, on a small fresh dataset. At 1/3/5 accounts
there were 10/30/50 requests respectively and zero HTTP errors. These are short
read-only bursts, not sustained medical-workflow load or maximum capacity.
Attachment/image upload size limits have not been characterized.

Validated: Administrator login, actual VisionCare rendering with no page errors,
PDF generation and content extraction, RQ job completion, database plus file-byte
persistence after Engine stop/start, and restoration after deliberately deleting
the synthetic attachment. Rollback drill restores the same-version image and
matching data; it does not prove arbitrary cross-version schema downgrades.

Still pending: fresh JetPack offline installation, another LAN client, physical
reboot, actual clinical PDF layout, AC/camera/audio flow and RAM/swap/OOM under
real station load. All performance thresholds remain UNDECIDED. The overall
production ticket is not closed by this CI result alone.
