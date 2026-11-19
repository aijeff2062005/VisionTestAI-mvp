# QY XML folder connector

Runs on an always-on clinic PC that can read the HIS XML share and reach the QY Hospital site. It polls `QY_XML_INBOX`, waits for each XML file to stop changing, then posts it over HTTPS to the QY-only intake API. It does not modify or delete HIS files. Successfully delivered file versions are recorded in a local SQLite state file so API/network retries do not create duplicate queue requests.

## Expected XML

The XML contains patient data only. It does not contain a measurement-request flag or an instruction to start a measurement. QY imports the patient records and, for each HIS patient ID that has not already been imported into the QY measurement queue, creates a `QY Measurement Request` with status `Chờ đo`. In other words, adding a patient to this XML intake is what causes QY to enqueue that patient.

HIS does not need to send a `batch_id`; the QY service fingerprints the sorted HIS patient IDs internally, so retrying the same ID list is acknowledged as a duplicate even if the XML formatting or file modification time changed. Each `his_patient_id` may appear only once in a file. The connector accepts XML up to 2 MB and up to 500 patients per file.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<patients>
    <patient>
        <his_patient_id>BN123456</his_patient_id>
        <full_name>Nguyen Van A</full_name>
        <cccd_last4>1234</cccd_last4>
    </patient>
    <patient>
        <his_patient_id>BN123457</his_patient_id>
        <full_name>Tran Thi B</full_name>
        <cccd_last4>5678</cccd_last4>
    </patient>
</patients>
```

QY maps each XML row to a `Patient` record and adds a queue row; HIS supplies patient data, not measurement workflow fields. Current implementation deduplicates by HIS patient ID: if that ID already has a `QY Measurement Request`, it will not create another queue row. An exact repeat of an earlier ID list is acknowledged without creating another batch. Consequently, this implementation is for ingesting patient records into the QY queue once per HIS ID; if an already-imported patient must be refreshed or measured again, the QY-side deduplication/requeue behavior must be agreed and adjusted separately. The API response contains the receipt ID, patient/request counts, and per-patient request IDs.

## Configuration

Set these environment variables on the clinic PC:

- `QY_XML_INBOX`: path to the HIS shared folder
- `QY_SITE_URL`: base URL of the QY site, for example `https://qy.example.vn`
- `QY_API_KEY` and `QY_API_SECRET`: API credentials of a restricted Frappe integration user with a QY clinic staff role
- `QY_XML_STATE`: optional path for the local SQLite receipt ledger
- `QY_XML_POLL_SECONDS`: optional folder polling interval (default 30 seconds)
- `QY_XML_STABLE_SECONDS`: optional file stability interval (default 1 second)

Run with Python 3.10+: `python connector.py`. Configure Windows Task Scheduler to launch it at startup and restart it after failure; it must stay running for automatic intake. Use HTTPS for the QY site and protect the API secret and local state file. The initial scan imports existing XML files too, so point the connector at the intended inbox/archive policy before starting it. Keep processed files in place or move them outside the watched inbox; the connector never deletes or moves HIS files.
