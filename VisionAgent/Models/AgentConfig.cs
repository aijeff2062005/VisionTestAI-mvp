namespace VisionAgent.Models;

public sealed class AgentConfig
{
    public string BackendUrl { get; set; } = "";
    public string InboxPath { get; set; } = "";
    public string ReportPath { get; set; } = "";
    public int ReportHour { get; set; } = 17;
    public int ReportMinute { get; set; } = 0;
    public int PollSeconds { get; set; } = 30;
    public double StableSeconds { get; set; } = 1;
    public bool StartWithWindows { get; set; } = true;
    public bool MinimizeToTray { get; set; } = true;
}

public sealed class ApiCredentials
{
    public string ApiKey { get; set; } = "";
    public string ApiSecret { get; set; } = "";
}
