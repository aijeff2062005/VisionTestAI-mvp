using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using VisionAgent.Models;

namespace VisionAgent.Services;

public sealed class XmlAgent : IAsyncDisposable
{
    public const int MaxXmlBytes = 2 * 1024 * 1024;
    public const string ImportMethod = "/api/method/qy_vision_hospital.api.xml_intake.import_patient_xml";
    private static readonly HttpClient Client = new() { Timeout = TimeSpan.FromSeconds(30) };
    private readonly AgentConfig _config;
    private readonly ApiCredentials _credentials;
    private readonly ProcessedState _state;
    private readonly AgentLogWriter _logs;
    private readonly DailyReportExporter _reports;
    private readonly CancellationTokenSource _cancellation = new();
    private readonly Task _runner;
    private DateTime? _lastSuccess;

    public event Action<string, bool>? StatusChanged;
    public event Action<AgentLog>? Activity;
    public DateTime? LastSuccess => _lastSuccess;

    public XmlAgent(AgentConfig config, ApiCredentials credentials, ProcessedState state, AgentLogWriter logs)
    {
        _config = config;
        _credentials = credentials;
        _state = state;
        _logs = logs;
        _reports = new DailyReportExporter(config, credentials, logs);
        _runner = Task.Run(() => RunAsync(_cancellation.Token));
    }

    public static async Task<string> TestConnectionAsync(string backendUrl, ApiCredentials credentials, CancellationToken cancellationToken = default)
    {
        var baseUri = NormalizeBackendUrl(backendUrl);
        using var request = CreateRequest(HttpMethod.Get, new Uri(baseUri, "/api/method/frappe.auth.get_logged_user"), credentials);
        using var response = await Client.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException(response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden
                ? "Backend từ chối API Key/Secret hoặc tài khoản chưa được cấp quyền."
                : $"Backend trả về HTTP {(int)response.StatusCode}.");
        using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellationToken));
        if (!doc.RootElement.TryGetProperty("message", out var message) || message.ValueKind != JsonValueKind.String)
            throw new InvalidOperationException("Backend phản hồi không đúng định dạng.");
        return message.GetString() ?? "Tài khoản tích hợp";
    }

    public async Task StopAsync()
    {
        await _cancellation.CancelAsync();
        try { await _runner.WaitAsync(TimeSpan.FromSeconds(5)); }
        catch (TimeoutException) { }
    }

    private async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await _reports.RunIfDueAsync(cancellationToken);
                await ScanAsync(cancellationToken);
                StatusChanged?.Invoke("Đang theo dõi thư mục XML.", true);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { break; }
            catch (Exception)
            {
                Log("Không đọc được thư mục XML. Kiểm tra đường dẫn và quyền truy cập.", success: false);
                StatusChanged?.Invoke("Không đọc được thư mục XML; sẽ thử lại.", false);
            }

            try { await Task.Delay(TimeSpan.FromSeconds(Math.Clamp(_config.PollSeconds, 5, 3600)), cancellationToken); }
            catch (OperationCanceledException) { break; }
        }
    }

    public Task ExportReportNowAsync(DateTime day, CancellationToken cancellationToken = default) =>
        _reports.ExportNowAsync(day, cancellationToken);

    private async Task ScanAsync(CancellationToken cancellationToken)
    {
        if (!Directory.Exists(_config.InboxPath))
        {
            StatusChanged?.Invoke("Không tìm thấy thư mục XML.", false);
            return;
        }

        var files = Directory.EnumerateFiles(_config.InboxPath, "*.xml", SearchOption.AllDirectories)
            .OrderBy(File.GetLastWriteTimeUtc).ThenBy(Path.GetFileName, StringComparer.OrdinalIgnoreCase).ToArray();
        foreach (var file in files)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try { await ProcessFileAsync(file, cancellationToken); }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
            catch (Exception ex)
            {
                Log(ex is UnauthorizedAccessException
                    ? "Không có quyền đọc một file XML; sẽ thử lại ở lần quét sau."
                    : "Không xử lý được một file XML; sẽ thử lại ở lần quét sau.", success: false);
            }
        }
    }

    private async Task ProcessFileAsync(string file, CancellationToken cancellationToken)
    {
        var before = new FileInfo(file);
        if (!before.Exists || before.Length <= 0 || before.Length > MaxXmlBytes)
        {
            if (before.Exists && before.Length > MaxXmlBytes) Log("Bỏ qua file XML vượt giới hạn 2 MB.", success: false);
            return;
        }
        var relativeName = Path.GetRelativePath(_config.InboxPath, file);
        var relativeKey = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(relativeName))).ToLowerInvariant();
        var versionMarker = $"{relativeKey}:{before.LastWriteTimeUtc.Ticks}:{before.Length}";
        if (_state.Contains(versionMarker)) return;

        await Task.Delay(TimeSpan.FromSeconds(Math.Clamp(_config.StableSeconds, 0.5, 60)), cancellationToken);
        var after = new FileInfo(file);
        after.Refresh();
        if (!after.Exists || before.Length != after.Length || before.LastWriteTimeUtc != after.LastWriteTimeUtc) return;

        var bytes = await File.ReadAllBytesAsync(file, cancellationToken);
        if (bytes.Length == 0 || bytes.Length > MaxXmlBytes) return;
        var contentHash = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        var keyInput = Encoding.UTF8.GetBytes($"{relativeName}\0{after.LastWriteTimeUtc.Ticks}\0{contentHash}");
        var sourceKey = Convert.ToHexString(SHA256.HashData(keyInput)).ToLowerInvariant();
        var xml = new UTF8Encoding(false, true).GetString(bytes).TrimStart('\uFEFF');
        var safeSourceName = $"xml-{sourceKey[..12]}.xml";
        var body = JsonSerializer.Serialize(new { xml_content = xml, source_file = safeSourceName, source_key = sourceKey });
        var baseUri = NormalizeBackendUrl(_config.BackendUrl);
        using var request = CreateRequest(HttpMethod.Post, new Uri(baseUri, ImportMethod), _credentials);
        request.Content = new StringContent(body, Encoding.UTF8, "application/json");
        using var response = await Client.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            var message = response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden
                ? "Backend từ chối API Key/Secret hoặc tài khoản chưa được cấp quyền."
                : $"Backend trả về HTTP {(int)response.StatusCode}; sẽ thử lại.";
            Log(message, success: false);
            return;
        }

        using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellationToken));
        if (!doc.RootElement.TryGetProperty("message", out var result)
            || !result.TryGetProperty("success", out var successNode)
            || !successNode.GetBoolean())
        {
            Log("Backend chưa xác nhận nhận XML; sẽ thử lại.", success: false);
            return;
        }

        _state.Add(versionMarker);
        _lastSuccess = DateTime.Now;
        var duplicate = result.TryGetProperty("duplicate", out var duplicateNode) && duplicateNode.ValueKind == JsonValueKind.True;
        Log(duplicate ? "Backend đã nhận diện lô XML trùng; không tạo lại." : "Gửi XML thành công.", success: true);
    }

    private static HttpRequestMessage CreateRequest(HttpMethod method, Uri uri, ApiCredentials credentials)
    {
        var request = new HttpRequestMessage(method, uri);
        request.Headers.Authorization = new AuthenticationHeaderValue("token", $"{credentials.ApiKey}:{credentials.ApiSecret}");
        return request;
    }

    private static Uri NormalizeBackendUrl(string value)
    {
        if (!Uri.TryCreate(value.Trim().TrimEnd('/') + "/", UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp))
            throw new InvalidOperationException("Backend URL phải bắt đầu bằng https:// hoặc http://.");
        return uri;
    }

    private void Log(string message, bool success)
    {
        var item = new AgentLog(DateTime.Now, message);
        _logs.Write(message);
        Activity?.Invoke(item);
        if (!success) StatusChanged?.Invoke(message, false);
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync();
        _cancellation.Dispose();
    }
}
