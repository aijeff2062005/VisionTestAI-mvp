using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Reflection;
using System.Text.Encodings.Web;
using System.Text.Json;
using VisionAgent.Models;

namespace VisionAgent.Services;

/// <summary>Builds the two daily reports on the workstation where the output folder lives.</summary>
public sealed class DailyReportExporter(AgentConfig config, ApiCredentials credentials, AgentLogWriter logs)
{
    private static readonly HttpClient Client = new() { Timeout = TimeSpan.FromMinutes(2) };
    private static readonly string ReportTemplate = ReadTextResource("VisionAgent.ReportTemplate.html");
    private static readonly string HospitalLogo = Convert.ToBase64String(ReadBinaryResource("VisionAgent.hospital-logo.png"));
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly HashSet<DateTime> _checkedDays = [];

    public async Task RunIfDueAsync(CancellationToken cancellationToken)
    {
        if (!await _gate.WaitAsync(0, cancellationToken)) return;
        try
        {
            var now = DateTime.Now;
            var yesterday = now.Date.AddDays(-1);
            if (!_checkedDays.Contains(yesterday))
            {
                await ExportIfMissingAsync(yesterday, cancellationToken);
                _checkedDays.Add(yesterday);
            }
            var cutoff = now.Date.AddHours(Math.Clamp(config.ReportHour, 0, 23))
                .AddMinutes(Math.Clamp(config.ReportMinute, 0, 59));
            if (now >= cutoff && !_checkedDays.Contains(now.Date))
            {
                await ExportIfMissingAsync(now.Date, cancellationToken);
                _checkedDays.Add(now.Date);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { }
        catch (Exception ex) { logs.Write($"Xuất báo cáo ngày thất bại: {ex.Message}"); }
        finally { _gate.Release(); }
    }

    public async Task<bool> ExportNowAsync(DateTime day, CancellationToken cancellationToken = default) =>
        await ExportIfMissingAsync(day.Date, cancellationToken, overwrite: true);

    private async Task<bool> ExportIfMissingAsync(DateTime day, CancellationToken cancellationToken, bool overwrite = false)
    {
        var root = string.IsNullOrWhiteSpace(config.ReportPath)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "VisionAgent", "BaoCao")
            : Path.GetFullPath(Environment.ExpandEnvironmentVariables(config.ReportPath));
        var folder = Path.Combine(root, day.ToString("yyyy-MM-dd"));
        var summaryPath = Path.Combine(folder, $"Tong-hop_{day:yyyy-MM-dd}.html");
        var detailPath = Path.Combine(folder, $"Chi-tiet_{day:yyyy-MM-dd}.html");
        if (!overwrite && File.Exists(summaryPath) && File.Exists(detailPath)) return true;

        var uri = new Uri(new Uri(config.BackendUrl.TrimEnd('/') + "/"),
            $"api/method/qy_vision_hospital.api.xml_intake.daily_vision_report?report_date={day:yyyy-MM-dd}");
        using var request = new HttpRequestMessage(HttpMethod.Get, uri);
        request.Headers.Authorization = new AuthenticationHeaderValue("token", $"{credentials.ApiKey}:{credentials.ApiSecret}");
        using var response = await Client.SendAsync(request, cancellationToken);
        var responseText = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw new HttpRequestException(FormatApiError(response.StatusCode, responseText));
        using var envelope = JsonDocument.Parse(responseText);
        var payload = envelope.RootElement.GetProperty("message");
        var rows = payload.GetProperty("rows").EnumerateArray().ToArray();
        if (rows.Length == 0)
        {
            logs.Write($"Không có lượt đo hoàn tất cho ngày {day:yyyy-MM-dd}; không tạo báo cáo HTML.");
            return false;
        }

        Directory.CreateDirectory(folder);
        var cutoff = day.Date.AddHours(Math.Clamp(config.ReportHour, 0, 23))
            .AddMinutes(Math.Clamp(config.ReportMinute, 0, 59));
        var exportedAt = DateTime.Now;
        await WriteHtmlAsync(summaryPath, BuildHtml(day, cutoff, exportedAt, rows, false), cancellationToken);
        await WriteHtmlAsync(detailPath, BuildHtml(day, cutoff, exportedAt, rows, true), cancellationToken);
        logs.Write($"Đã lưu báo cáo HTML ngày {day:yyyy-MM-dd}: 2 file, {rows.Length} lượt đo.");
        return true;
    }

    private static string FormatApiError(System.Net.HttpStatusCode statusCode, string responseText)
    {
        var details = responseText;
        try
        {
            using var error = JsonDocument.Parse(responseText);
            var root = error.RootElement;
            var parts = new List<string>();
            foreach (var key in new[] { "exc_type", "message", "_server_messages", "exception" })
            {
                if (root.TryGetProperty(key, out var value) && value.ValueKind is not JsonValueKind.Null and not JsonValueKind.Undefined)
                    parts.Add($"{key}: {value}");
            }
            if (parts.Count > 0) details = string.Join(" | ", parts);
        }
        catch (JsonException) { }

        details = details.Replace('\r', ' ').Replace('\n', ' ').Trim();
        if (details.Length > 1600) details = details[..1600] + "…";
        return $"Backend trả HTTP {(int)statusCode} ({statusCode}) khi lấy báo cáo: {details}";
    }

    private static string BuildHtml(DateTime day, DateTime cutoff, DateTime exportedAt, JsonElement[] rows, bool detail)
    {
        var page = detail
            ? BuildDetailPage(day, exportedAt, rows)
            : BuildSummaryPage(day, cutoff, exportedAt, rows);
        return ReportTemplate
            .Replace("{{REPORT_PAGE}}", page.Replace("__HOSPITAL_LOGO__", "data:image/png;base64," + HospitalLogo, StringComparison.Ordinal), StringComparison.Ordinal);
    }

    private static string BuildSummaryPage(DateTime day, DateTime cutoff, DateTime exportedAt, JsonElement[] rows)
    {
        var patients = rows.Select(r => Get(r, "patient_id", Get(r, "patient_name")))
            .Where(id => !string.IsNullOrWhiteSpace(id)).Distinct(StringComparer.OrdinalIgnoreCase).Count();
        var tableRows = string.Join("", rows.Select(r =>
            $"<tr><td><strong>{Get(r, "patient_name", "Chưa có tên")}</strong><br><span class='code'>{Get(r, "patient_id")}</span></td><td>{Time(r)}</td><td><span class='score'>{Get(r, "right_score", "—")}</span></td><td><span class='score'>{Get(r, "left_score", "—")}</span></td></tr>"));
        return $"""
            <article class="page summary-page">
              <header class="hospital"><div class="brand"><div class="logo"><img src="__HOSPITAL_LOGO__" alt="Logo Bệnh viện Quân Dân Y Miền Đông"></div><div><div class="hospital-name">BỆNH VIỆN QUÂN DÂN Y MIỀN ĐÔNG</div><div class="hospital-sub">Báo cáo đo thị lực</div></div></div></header>
              <section class="report-title"><div class="eyebrow">Báo cáo vận hành</div><h1>TỔNG HỢP KẾT QUẢ ĐO THỊ LỰC</h1><div class="date-line">Ngày đo <strong>__DATE__</strong> &nbsp;·&nbsp; Chốt lúc <strong>__CUTOFF__</strong></div></section>
              <section class="stats summary-stats"><div class="stat"><div class="stat-label">Lượt đo hoàn tất</div><div class="stat-value">__TOTAL__</div><div class="stat-note">Lượt đo trong ngày</div></div><div class="stat"><div class="stat-label">Bệnh nhân</div><div class="stat-value">__PATIENTS__</div><div class="stat-note">Bệnh nhân có kết quả đo</div></div></section>
              <section><div class="section-heading"><h2>DANH SÁCH KẾT QUẢ</h2><span>Trang tổng hợp · không có STT</span></div><table class="summary-table"><thead><tr><th>Bệnh nhân</th><th>Giờ đo</th><th>Mắt phải</th><th>Mắt trái</th></tr></thead><tbody>__SUMMARY_ROWS__</tbody></table></section>
              <div class="disclaimer">Báo cáo được tạo tự động từ các kết quả đo đã lưu trên hệ thống.</div>
              <footer class="footer"><span>Ngày xuất: __EXPORTED__</span><span><b>BV_QYMD_BaoCaoDoThiLuc___FILE_DATE__</b></span></footer>
            </article>
            """
            .Replace("__DATE__", day.ToString("dd/MM/yyyy"), StringComparison.Ordinal)
            .Replace("__CUTOFF__", cutoff.ToString("HH:mm, dd/MM/yyyy"), StringComparison.Ordinal)
            .Replace("__TOTAL__", rows.Length.ToString(), StringComparison.Ordinal)
            .Replace("__PATIENTS__", patients.ToString(), StringComparison.Ordinal)
            .Replace("__SUMMARY_ROWS__", tableRows, StringComparison.Ordinal)
            .Replace("__EXPORTED__", exportedAt.ToString("dd/MM/yyyy HH:mm"), StringComparison.Ordinal)
            .Replace("__FILE_DATE__", day.ToString("yyyy-MM-dd"), StringComparison.Ordinal);
    }

    private static string BuildDetailPage(DateTime day, DateTime exportedAt, JsonElement[] rows)
    {
        var panels = string.Join("", rows.Select(BuildPatientPanel));
        return $"""
            <article class="page detail-page">
              <header class="hospital running-header"><div><div class="hospital-name">BỆNH VIỆN QUÂN DÂN Y MIỀN ĐÔNG</div><div class="hospital-sub">Báo cáo đo thị lực</div></div><div class="detail-page-label">PHỤ LỤC CHI TIẾT</div></header>
              <section class="report-title detail-title"><div class="eyebrow">Báo cáo vận hành</div><h1>CHI TIẾT KẾT QUẢ THEO BỆNH NHÂN</h1><div class="date-line">Ngày đo <strong>__DATE__</strong></div></section>
              <section><div class="section-heading"><h2>KẾT QUẢ CHI TIẾT</h2><span>Một mục riêng cho mỗi bệnh nhân</span></div>__PATIENT_PANELS__</section>
              <div class="disclaimer">Các lượt trả lời và ký tự được lấy từ dữ liệu phiên đo đã lưu.</div>
              <section class="signatures"><div><strong>NGƯỜI LẬP BÁO CÁO</strong><div class="sign-space"></div>(Tự động từ hệ thống)</div><div><strong>ĐẠI DIỆN CƠ SỞ Y TẾ</strong><div class="sign-space"></div>(Ký, ghi rõ họ tên)</div></section>
              <footer class="footer"><span>Ngày xuất: __EXPORTED__</span><span><b>BV_QYMD_BaoCaoDoThiLuc___FILE_DATE__</b></span></footer>
            </article>
            """
            .Replace("__DATE__", day.ToString("dd/MM/yyyy"), StringComparison.Ordinal)
            .Replace("__EXPORTED__", exportedAt.ToString("dd/MM/yyyy HH:mm"), StringComparison.Ordinal)
            .Replace("__FILE_DATE__", day.ToString("yyyy-MM-dd"), StringComparison.Ordinal)
            .Replace("__PATIENT_PANELS__", panels, StringComparison.Ordinal);
    }

    private static string BuildPatientPanel(JsonElement row)
    {
        var trials = ReadTrials(row);
        var rightCount = trials.Count(t => t.Eye == "right");
        var leftCount = trials.Count(t => t.Eye == "left");
        var trialRows = string.Join("", trials.Select(trial =>
            $"<tr><td><span class='eye-label'>{(trial.Eye == "right" ? "Phải" : trial.Eye == "left" ? "Trái" : "Hai mắt")}</span></td><td>{Encode(trial.Score, "—")}</td><td>{Encode(trial.Expected, "—")}</td><td>{Encode(trial.Actual, "—")}</td><td>{(trial.Matched ? "<span class='result-ok'>Đúng</span>" : "<span class='score below'>Chưa khớp</span>")}</td></tr>"));
        var trialsTable = trials.Count == 0
            ? "<p class='hospital-sub'>Không có dữ liệu ký tự chi tiết cho lượt đo này.</p>"
            : $"<table class='trials-table'><thead><tr><th>Mắt</th><th>VN/10</th><th>Dự kiến</th><th>Thực tế</th><th>Kết quả</th></tr></thead><tbody>{trialRows}</tbody></table>";
        return $"""
            <div class="patient-panel">
              <div class="patient-panel-head"><div><div class="patient-name-large">__NAME__</div><div class="patient-meta">Mã bệnh nhân: <strong>__PATIENT_ID__</strong> &nbsp;·&nbsp; Giờ đo: <strong>__TIME__</strong></div></div><div class="trial-count">__TRIALS__ lượt · __RIGHT_COUNT__ phải / __LEFT_COUNT__ trái</div></div>
              <div class="vision-scores"><div class="vision-score"><div class="vision-score-label">Mắt phải</div><div class="vision-score-value">__RIGHT_SCORE__</div></div><div class="vision-score"><div class="vision-score-label">Mắt trái</div><div class="vision-score-value">__LEFT_SCORE__</div></div></div>
              <div class="trials-heading"><strong>CÁC KÝ TỰ ĐÃ KIỂM TRA</strong><span>Chi tiết theo mắt và từng lượt trả lời</span></div>__TRIAL_TABLE__
            </div>
            """
            .Replace("__NAME__", Get(row, "patient_name", "Chưa có tên"), StringComparison.Ordinal)
            .Replace("__PATIENT_ID__", Get(row, "patient_id", "—"), StringComparison.Ordinal)
            .Replace("__TIME__", Time(row), StringComparison.Ordinal)
            .Replace("__TRIALS__", trials.Count.ToString(), StringComparison.Ordinal)
            .Replace("__RIGHT_COUNT__", rightCount.ToString(), StringComparison.Ordinal)
            .Replace("__LEFT_COUNT__", leftCount.ToString(), StringComparison.Ordinal)
            .Replace("__RIGHT_SCORE__", Get(row, "right_score", "—"), StringComparison.Ordinal)
            .Replace("__LEFT_SCORE__", Get(row, "left_score", "—"), StringComparison.Ordinal)
            .Replace("__TRIAL_TABLE__", trialsTable, StringComparison.Ordinal);
    }

    private static List<TrialResult> ReadTrials(JsonElement row)
    {
        if (!row.TryGetProperty("letters", out var raw) || raw.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
            return [];
        if (raw.ValueKind == JsonValueKind.String)
        {
            var json = raw.GetString();
            if (string.IsNullOrWhiteSpace(json)) return [];
            try
            {
                using var parsed = JsonDocument.Parse(json);
                return ExpandTrials(parsed.RootElement);
            }
            catch (JsonException) { return []; }
        }
        return ExpandTrials(raw);
    }

    private static List<TrialResult> ExpandTrials(JsonElement raw)
    {
        var result = new List<TrialResult>();
        if (raw.ValueKind != JsonValueKind.Array) return result;
        foreach (var trial in raw.EnumerateArray())
        {
            if (trial.ValueKind != JsonValueKind.Object) continue;
            var eye = GetValue(trial, "eye").ToLowerInvariant();
            if (eye is not ("right" or "left" or "both")) eye = "left";
            var score = GetValue(trial, "vn_over_10");
            var expected = ReadStrings(trial, "target");
            var actual = ReadStrings(trial, "heard");
            if (expected.Count == 0 && trial.TryGetProperty("expected", out var expectedValue)) expected.Add(expectedValue.ToString());
            if (actual.Count == 0 && trial.TryGetProperty("actual", out var actualValue)) actual.Add(actualValue.ToString());
            var count = Math.Max(expected.Count, actual.Count);
            if (count == 0) continue;
            for (var i = 0; i < count; i++)
            {
                var target = i < expected.Count ? expected[i].Trim().ToUpperInvariant() : "";
                var response = i < actual.Count ? actual[i].Trim().ToUpperInvariant() : "";
                var matched = target.Length > 0 && response.Length > 0 && response != "?" && target == response;
                result.Add(new TrialResult(eye, score, target, response, matched));
            }
        }
        return result;
    }

    private static List<string> ReadStrings(JsonElement obj, string key)
    {
        if (!obj.TryGetProperty(key, out var value)) return [];
        if (value.ValueKind == JsonValueKind.Array) return value.EnumerateArray().Select(x => x.ToString()).ToList();
        return value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined ? [] : [value.ToString()];
    }

    private sealed record TrialResult(string Eye, string Score, string Expected, string Actual, bool Matched);

    private static string Time(JsonElement row) => DateTime.TryParse(GetValue(row, "measured_at"), out var dt) ? dt.ToString("HH:mm") : "—";
    private static string Get(JsonElement row, string key, string fallback = "") => row.TryGetProperty(key, out var value) ? Encode(value.ToString(), fallback) : fallback;
    private static string GetValue(JsonElement row, string key) => row.TryGetProperty(key, out var value) ? value.ToString() : "";
    private static string Encode(string value, string fallback = "") => HtmlEncoder.Default.Encode(string.IsNullOrEmpty(value) ? fallback : value);

    private static string ReadTextResource(string name)
    {
        using var stream = typeof(DailyReportExporter).Assembly.GetManifestResourceStream(name)
            ?? throw new FileNotFoundException($"Không tìm thấy mẫu báo cáo nhúng: {name}");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    private static byte[] ReadBinaryResource(string name)
    {
        using var stream = typeof(DailyReportExporter).Assembly.GetManifestResourceStream(name)
            ?? throw new FileNotFoundException($"Không tìm thấy tài nguyên nhúng: {name}");
        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        return memory.ToArray();
    }

    private static async Task WriteHtmlAsync(string path, string html, CancellationToken cancellationToken)
    {
        var temporaryPath = path + ".tmp";
        try
        {
            await File.WriteAllTextAsync(temporaryPath, html, new System.Text.UTF8Encoding(false), cancellationToken);
            File.Move(temporaryPath, path, true);
        }
        finally
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
        }
    }
}
