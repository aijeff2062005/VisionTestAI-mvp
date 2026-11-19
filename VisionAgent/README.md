# Vision Agent (.NET for Windows)

Vision Agent is a small Windows desktop/tray application that watches the HIS XML inbox and sends stable XML files to the QY intake API. The source is placed at `mvp_platform/VisionAgent`, next to `docs` and `tmp`.

## Current behavior

- WPF utility window with a compact native Windows layout.
- One masked authorization field accepts `token API_KEY:API_SECRET`; the app separates and protects the two values when saving.
- A small teal eye/XML icon, no version in the window title, no recent-activity panel; details are in **Nhật ký**.
- Backend and folder-check results appear below the related section and clear after five seconds. **Thu nhỏ** collapses the app to the backend section; **Mở rộng** restores the full window.
- Uses the currently signed-in Windows account to read the HIS folder. It does not ask for or store the Windows password.
- Checks the backend API credential with `frappe.auth.get_logged_user`.
- Polls the folder every 30 seconds by default and waits 1 second for a file to stop changing.
- Uploads UTF-8 XML to `qy_vision_hospital.api.xml_intake.import_patient_xml`, with a 2 MB client limit and retry on later polls.
- Keeps source files in place and records successfully processed file versions locally.
- At the configured daily cutoff (17:00 by default), fetches completed measurements from QY Frappe and saves one summary HTML report plus one detailed HTML report under the configured report folder, in a date-named subfolder. Set the cutoff hour and minute in **Giờ chốt báo cáo**. If the app was closed at cutoff, it checks the previous day's report at next startup.
- The report folder can be selected in **Folder báo cáo**. Reports use the embedded QY report template and open directly in a web browser; Microsoft Edge PDF rendering is not required.
- Stores API credentials encrypted with Windows DPAPI for the current Windows user.
- Can start when that Windows user logs in and minimize to the notification area.

## Build and make the installer on Windows

Install the .NET 10 SDK and either Inno Setup 6 or NSIS, then run from PowerShell:

```powershell
./build-windows.ps1
```

The script publishes a self-contained `win-x64` app and creates `installer-output/VisionAgent-Setup.exe` using Inno Setup or NSIS when available. The NSIS recipe is also cross-compilable from Linux. The installer is per-user and does not request administrator privileges. It installs a Start menu shortcut; the app's “Chạy cùng Windows” option writes the current user's Run key after configuration is saved.

On Linux with the .NET Windows targeting pack and NSIS installed, run `./build-linux-installer.sh` to produce the same Windows installer.

The current development container is Linux. Windows targeting and the NSIS installer can be compiled here, but the WPF app cannot be launched here. Verify runtime behavior on Windows before production use.

## First-run setup

1. Select the HIS XML folder (use its UNC path such as `\\HIS-SERVER\Share\QY\XML`).
2. Enter the HTTPS QY site URL and the Authorization value supplied by the QY operator, in the format `token API_KEY:API_SECRET`.
3. Use **Kiểm tra kết nối** and **Kiểm tra quyền đọc**.
4. Save the configuration. The agent begins polling; default interval is 30 seconds.
5. Choose a writable **Folder báo cáo** (default: `Documents\VisionAgent\BaoCao`). VisionAgent creates a `yyyy-MM-dd` subfolder containing `Tong-hop_yyyy-MM-dd.html` and `Chi-tiet_yyyy-MM-dd.html`. Use **Tạo lại báo cáo** to regenerate and overwrite reports for a selected day.

Daily reports require the QY Frappe app with `qy_vision_hospital.api.xml_intake.daily_vision_report` installed and the API user assigned an allowed clinic role. Only completed items in the QY measurement queue are included. The Windows account running VisionAgent needs write access to the report folder.

The user account must have read/list permission on both the network share and its folder security ACL. The current-user startup option runs only after that same user logs in; it does not run before login as a Windows service.

## Data location

Configuration and state are stored under `%LOCALAPPDATA%\VisionAgent`. The non-secret settings are in `config.json`; API credentials are protected for the current Windows account in `credentials.dat`. Logs and the processed-file ledger are stored alongside them. The local ledger is an implementation detail and can be rebuilt by the server's idempotent intake behavior if it is lost.
