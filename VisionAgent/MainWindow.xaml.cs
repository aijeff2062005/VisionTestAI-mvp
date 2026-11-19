using System.IO;
using System.Security.Principal;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using VisionAgent.Models;
using VisionAgent.Services;
using Forms = System.Windows.Forms;
using Application = System.Windows.Application;
using Brushes = System.Windows.Media.Brushes;
using WpfMessageBox = System.Windows.MessageBox;

namespace VisionAgent;

public partial class MainWindow : Window
{
    private readonly ConfigStore _store = new();
    private readonly AgentLogWriter _logs;
    private readonly ProcessedState _state;
    private readonly Dictionary<TextBlock, DispatcherTimer> _feedbackTimers = [];
    private AgentConfig _config = new();
    private ApiCredentials _credentials = new();
    private XmlAgent? _agent;
    private Forms.NotifyIcon? _trayIcon;
    private System.Drawing.Icon? _appIcon;
    private bool _allowClose;
    private bool _isCompact;
    private double _expandedHeight;
    private double _expandedWidth;

    public MainWindow()
    {
        InitializeComponent();
        _logs = new AgentLogWriter(_store.LogPath);
        _state = new ProcessedState(_store.StatePath);
        WindowsAccountText.Text = $"Tài khoản Windows hiện tại: {WindowsIdentity.GetCurrent().Name}";
        Loaded += MainWindow_Loaded;
        Closing += MainWindow_Closing;
        InitializeTrayIcon();
    }

    private void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        try
        {
            (_config, _credentials) = _store.Load();
            LoadFields();
            if (IsConfigured()) StartAgent();
            else SetStatus("Chưa cấu hình đủ thông tin.", false);
        }
        catch (Exception ex)
        {
            SetStatus($"Không tải được cấu hình: {ex.Message}", false);
        }
    }

    private void LoadFields()
    {
        BackendUrlBox.Text = _config.BackendUrl;
        AuthorizationBox.Password = string.IsNullOrWhiteSpace(_credentials.ApiKey)
            || string.IsNullOrWhiteSpace(_credentials.ApiSecret)
            ? ""
            : $"token {_credentials.ApiKey}:{_credentials.ApiSecret}";
        InboxBox.Text = _config.InboxPath;
        ReportPathBox.Text = string.IsNullOrWhiteSpace(_config.ReportPath)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "VisionAgent", "BaoCao")
            : _config.ReportPath;
        ReportDatePicker.SelectedDate = DateTime.Today;
        ReportHourBox.Text = _config.ReportHour.ToString("00");
        ReportMinuteBox.Text = _config.ReportMinute.ToString("00");
        PollSecondsBox.Text = _config.PollSeconds.ToString();
        StableSecondsBox.Text = _config.StableSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture);
        AutostartCheck.IsChecked = _config.StartWithWindows;
        MinimizeToTrayCheck.IsChecked = _config.MinimizeToTray;
    }

    private AgentConfig ReadConfigFromFields()
    {
        if (!Uri.TryCreate(BackendUrlBox.Text.Trim(), UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp))
            throw new InvalidOperationException("Backend URL cần bắt đầu bằng https:// hoặc http://.");
        if (!int.TryParse(PollSecondsBox.Text, out var poll) || poll < 5 || poll > 3600)
            throw new InvalidOperationException("Chu kỳ quét phải từ 5 đến 3600 giây.");
        if (!double.TryParse(StableSecondsBox.Text, System.Globalization.NumberStyles.Number,
                System.Globalization.CultureInfo.InvariantCulture, out var stable) || stable < 0.5 || stable > 60)
            throw new InvalidOperationException("Thời gian chờ file ổn định phải từ 0.5 đến 60 giây.");
        var inbox = InboxBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(inbox)) throw new InvalidOperationException("Chọn thư mục XML trước khi lưu.");
        if (!int.TryParse(ReportHourBox.Text, out var reportHour) || reportHour is < 0 or > 23)
            throw new InvalidOperationException("Giờ chốt phải nằm trong khoảng 0 đến 23.");
        if (!int.TryParse(ReportMinuteBox.Text, out var reportMinute) || reportMinute is < 0 or > 59)
            throw new InvalidOperationException("Phút chốt phải nằm trong khoảng 0 đến 59.");

        return new AgentConfig
        {
            BackendUrl = uri.ToString().TrimEnd('/'),
            InboxPath = Path.GetFullPath(inbox),
            ReportPath = Path.GetFullPath(Environment.ExpandEnvironmentVariables(ReportPathBox.Text.Trim())),
            ReportHour = reportHour,
            ReportMinute = reportMinute,
            PollSeconds = poll,
            StableSeconds = stable,
            StartWithWindows = AutostartCheck.IsChecked == true,
            MinimizeToTray = MinimizeToTrayCheck.IsChecked == true,
        };
    }

    private ApiCredentials ReadCredentialsFromFields()
    {
        var authorization = AuthorizationBox.Password.Trim();
        const string scheme = "token ";
        if (!authorization.StartsWith(scheme, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Dán token theo dạng: token API_KEY:API_SECRET.");

        var token = authorization[scheme.Length..].Trim();
        var separator = token.IndexOf(':');
        if (separator <= 0 || separator == token.Length - 1 || token.IndexOf(':', separator + 1) >= 0)
            throw new InvalidOperationException("Token cần có đủ API Key và API Secret, ngăn cách bằng dấu hai chấm.");

        return new ApiCredentials
        {
            ApiKey = token[..separator].Trim(),
            ApiSecret = token[(separator + 1)..].Trim(),
        };
    }

    private bool IsConfigured() => !string.IsNullOrWhiteSpace(_config.BackendUrl)
        && !string.IsNullOrWhiteSpace(_config.InboxPath)
        && !string.IsNullOrWhiteSpace(_credentials.ApiKey)
        && !string.IsNullOrWhiteSpace(_credentials.ApiSecret);

    private async void TestConnection_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var url = BackendUrlBox.Text.Trim();
            var credentials = ReadCredentialsFromFields();
            ShowFeedback(BackendFeedbackText, "Đang kiểm tra kết nối…", good: true, hideAfter: false);
            var user = await XmlAgent.TestConnectionAsync(url, credentials);
            ShowFeedback(BackendFeedbackText, $"Kết nối thành công · {user}", good: true);
        }
        catch (Exception ex)
        {
            ShowFeedback(BackendFeedbackText, ex.Message, good: false);
        }
    }

    private void Browse_Click(object sender, RoutedEventArgs e)
    {
        using var dialog = new Forms.FolderBrowserDialog
        {
            Description = "Chọn thư mục chứa các file XML HIS",
            UseDescriptionForTitle = true,
            ShowNewFolderButton = false,
            SelectedPath = Directory.Exists(InboxBox.Text) ? InboxBox.Text : "",
        };
        if (dialog.ShowDialog() == Forms.DialogResult.OK) InboxBox.Text = dialog.SelectedPath;
    }

    private void BrowseReport_Click(object sender, RoutedEventArgs e)
    {
        using var dialog = new Forms.FolderBrowserDialog
        {
            Description = "Chọn folder gốc để lưu báo cáo HTML",
            UseDescriptionForTitle = true,
            ShowNewFolderButton = true,
            SelectedPath = Directory.Exists(ReportPathBox.Text) ? ReportPathBox.Text : "",
        };
        if (dialog.ShowDialog() == Forms.DialogResult.OK) ReportPathBox.Text = dialog.SelectedPath;
    }

    private async void CreateReport_Click(object sender, RoutedEventArgs e)
    {
        var selectedDay = ReportDatePicker.SelectedDate?.Date;
        if (selectedDay is null)
        {
            WpfMessageBox.Show(this, "Chọn ngày cần tạo lại báo cáo.", "Vision Agent", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        if (!IsConfigured())
        {
            WpfMessageBox.Show(this, "Hãy cấu hình backend và API token trước khi tạo báo cáo HTML.", "Vision Agent", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        try
        {
            var reportRoot = ReportPathBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(reportRoot))
                throw new InvalidOperationException("Chọn folder báo cáo trước khi tạo HTML.");
            reportRoot = Path.GetFullPath(Environment.ExpandEnvironmentVariables(reportRoot));
            var outputFolder = Path.Combine(reportRoot, selectedDay.Value.ToString("yyyy-MM-dd"));
            var choice = WpfMessageBox.Show(this,
                $"Tạo lại 2 file HTML cho ngày {selectedDay.Value:dd/MM/yyyy}?\n\nNếu file đã tồn tại, chúng sẽ bị ghi đè.\n\nFolder lưu:\n{outputFolder}",
                "Xác nhận tạo lại báo cáo", MessageBoxButton.YesNo, MessageBoxImage.Warning);
            if (choice != MessageBoxResult.Yes) return;

            CreateReportButton.IsEnabled = false;
            SetStatus($"Đang tạo lại báo cáo HTML ngày {selectedDay.Value:dd/MM/yyyy}…", true);
            var reportConfig = new AgentConfig
            {
                BackendUrl = _config.BackendUrl,
                ReportPath = reportRoot,
                ReportHour = _config.ReportHour,
                ReportMinute = _config.ReportMinute,
            };
            var created = await new DailyReportExporter(reportConfig, _credentials, _logs)
                .ExportNowAsync(selectedDay.Value);
            if (!created)
            {
                WpfMessageBox.Show(this, $"Không có lượt đo hoàn tất ngày {selectedDay.Value:dd/MM/yyyy}; chưa tạo file HTML.",
                    "Không có dữ liệu", MessageBoxButton.OK, MessageBoxImage.Information);
                SetStatus("Không có dữ liệu đo hoàn tất cho ngày đã chọn.", false);
                return;
            }

            var message = $"Đã tạo lại 2 file HTML cho ngày {selectedDay.Value:dd/MM/yyyy}.\n\n{outputFolder}";
            _logs.Write($"Người dùng tạo lại báo cáo ngày {selectedDay.Value:yyyy-MM-dd}.");
            SetStatus($"Đã tạo lại báo cáo HTML ngày {selectedDay.Value:dd/MM/yyyy}.", true);
            WpfMessageBox.Show(this, message, "Đã tạo báo cáo", MessageBoxButton.OK, MessageBoxImage.Information);
        }
        catch (Exception ex)
        {
            _logs.Write($"Tạo lại báo cáo HTML thất bại: {ex.Message}");
            SetStatus($"Tạo lại báo cáo HTML thất bại: {ex.Message}", false);
            WpfMessageBox.Show(this, ex.Message, "Không tạo được báo cáo", MessageBoxButton.OK, MessageBoxImage.Error);
        }
        finally
        {
            CreateReportButton.IsEnabled = true;
        }
    }

    private void CheckFolder_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var path = Path.GetFullPath(InboxBox.Text.Trim());
            if (!Directory.Exists(path)) throw new DirectoryNotFoundException("Không tìm thấy thư mục đã chọn.");
            using var iterator = Directory.EnumerateFileSystemEntries(path).GetEnumerator();
            _ = iterator.MoveNext();
            ShowFeedback(FolderFeedbackText, $"Có quyền đọc thư mục · {WindowsIdentity.GetCurrent().Name}", good: true);
        }
        catch (Exception ex)
        {
            ShowFeedback(FolderFeedbackText, $"Chưa đọc được thư mục: {ex.Message}", good: false);
        }
    }

    private void Save_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var config = ReadConfigFromFields();
            var credentials = ReadCredentialsFromFields();
            _store.Save(config, credentials);
            _config = config;
            _credentials = credentials;
            AutostartManager.SetEnabled(_config.StartWithWindows);
            StopAgent();
            StartAgent();
            _logs.Write("Đã lưu cấu hình.");
            ShowFeedback(BackendFeedbackText, "Đã lưu cấu hình.", good: true);
        }
        catch (Exception ex) { SetStatus($"Không lưu được cấu hình: {ex.Message}", false); }
    }

    private void StartAgent()
    {
        if (!IsConfigured())
        {
            SetStatus("Thiếu cấu hình backend, API hoặc thư mục XML.", false);
            return;
        }
        StopAgent();
        _agent = new XmlAgent(_config, _credentials, _state, _logs);
        _agent.StatusChanged += OnAgentStatus;
        PauseButton.Content = "Tạm dừng";
    }

    private void StopAgent()
    {
        var old = _agent;
        _agent = null;
        if (old is not null)
        {
            old.StatusChanged -= OnAgentStatus;
            _ = old.DisposeAsync();
        }
        PauseButton.Content = "Chạy tiếp";
    }

    private void Pause_Click(object sender, RoutedEventArgs e)
    {
        if (_agent is null) StartAgent();
        else
        {
            StopAgent();
            SetStatus("Đã tạm dừng theo dõi XML.", false);
        }
    }

    private void HideToTray_Click(object sender, RoutedEventArgs e) => HideToTray();

    private void HideToTray()
    {
        Hide();
        _trayIcon?.ShowBalloonTip(1200, "Vision Agent", "Agent tiếp tục chạy nền.", Forms.ToolTipIcon.Info);
    }

    private void Compact_Click(object sender, RoutedEventArgs e)
    {
        if (_isCompact) return;
        _expandedHeight = Height;
        _expandedWidth = Width;
        _isCompact = true;
        HeaderPanel.Visibility = Visibility.Collapsed;
        FolderGroup.Visibility = Visibility.Collapsed;
        StatusGroup.Visibility = Visibility.Collapsed;
        OptionsGroup.Visibility = Visibility.Collapsed;
        FooterPanel.Visibility = Visibility.Collapsed;
        ActionButtons.Visibility = Visibility.Collapsed;
        Grid.SetColumnSpan(BackendGroup, 2);
        BackendGroup.Margin = new Thickness(2, 2, 2, 2);
        ExpandCompactButton.Visibility = Visibility.Visible;
        MinWidth = 720;
        MinHeight = 175;
        Width = 780;
        Height = 205;
    }

    private void Expand_Click(object sender, RoutedEventArgs e)
    {
        if (!_isCompact) return;
        _isCompact = false;
        Grid.SetColumnSpan(BackendGroup, 1);
        BackendGroup.Margin = new Thickness(2, 0, 8, 8);
        HeaderPanel.Visibility = Visibility.Visible;
        FolderGroup.Visibility = Visibility.Visible;
        StatusGroup.Visibility = Visibility.Visible;
        OptionsGroup.Visibility = Visibility.Visible;
        FooterPanel.Visibility = Visibility.Visible;
        ActionButtons.Visibility = Visibility.Visible;
        ExpandCompactButton.Visibility = Visibility.Collapsed;
        MinWidth = 820;
        MinHeight = 660;
        Width = Math.Max(_expandedWidth, MinWidth);
        Height = Math.Max(_expandedHeight, MinHeight);
    }

    private void InitializeTrayIcon()
    {
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("Mở Vision Agent", null, (_, _) => Dispatcher.Invoke(ShowWindow));
        menu.Items.Add("Tạm dừng / chạy tiếp", null, (_, _) => Dispatcher.Invoke(() => Pause_Click(this, new RoutedEventArgs())));
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add("Kết thúc", null, (_, _) => Dispatcher.Invoke(ExitApplication));

        try
        {
            using var stream = Application.GetResourceStream(new Uri("pack://application:,,,/Assets/vision-agent.ico", UriKind.Absolute))?.Stream;
            if (stream is not null)
            {
                using var sourceIcon = new System.Drawing.Icon(stream);
                _appIcon = (System.Drawing.Icon)sourceIcon.Clone();
            }
        }
        catch { }

        _trayIcon = new Forms.NotifyIcon
        {
            Text = "Vision Agent",
            Icon = _appIcon ?? System.Drawing.SystemIcons.Application,
            ContextMenuStrip = menu,
            Visible = true,
        };
        _trayIcon.DoubleClick += (_, _) => Dispatcher.Invoke(ShowWindow);
    }

    private void ShowWindow()
    {
        Show();
        WindowState = WindowState.Normal;
        Activate();
    }

    private void ExitApplication()
    {
        _allowClose = true;
        _trayIcon?.Dispose();
        _appIcon?.Dispose();
        StopAgent();
        Application.Current.Shutdown();
    }

    private void MainWindow_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        if (!_allowClose && MinimizeToTrayCheck.IsChecked == true)
        {
            e.Cancel = true;
            HideToTray();
            return;
        }
        _trayIcon?.Dispose();
        _appIcon?.Dispose();
        StopAgent();
        Application.Current.Shutdown();
    }

    private void OpenLog_Click(object sender, RoutedEventArgs e)
    {
        var window = new LogWindow(_logs) { Owner = this };
        window.ShowDialog();
    }

    private void Defaults_Click(object sender, RoutedEventArgs e)
    {
        PollSecondsBox.Text = "30";
        StableSecondsBox.Text = "1";
        ReportHourBox.Text = "17";
        ReportMinuteBox.Text = "00";
        AutostartCheck.IsChecked = true;
        MinimizeToTrayCheck.IsChecked = true;
    }

    private void ShowFeedback(TextBlock target, string message, bool good, bool hideAfter = true)
    {
        if (_feedbackTimers.TryGetValue(target, out var existing))
        {
            existing.Stop();
            _feedbackTimers.Remove(target);
        }
        target.Text = message;
        target.Foreground = good ? Brushes.DarkGreen : Brushes.DarkRed;
        target.Visibility = Visibility.Visible;
        if (!hideAfter) return;

        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(5) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            target.Visibility = Visibility.Collapsed;
            _feedbackTimers.Remove(target);
        };
        _feedbackTimers[target] = timer;
        timer.Start();
    }

    private void SetStatus(string text, bool good)
    {
        StatusText.Text = text;
        StatusDot.Fill = good ? Brushes.ForestGreen : Brushes.DarkOrange;
    }

    private void OnAgentStatus(string text, bool good) => Dispatcher.Invoke(() => SetStatus(text, good));
}
