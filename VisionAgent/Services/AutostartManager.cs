using Microsoft.Win32;

namespace VisionAgent.Services;

public static class AutostartManager
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ValueName = "VisionAgent";

    public static void SetEnabled(bool enabled)
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable: true)
            ?? Registry.CurrentUser.CreateSubKey(RunKey, writable: true);
        if (enabled)
            key.SetValue(ValueName, $"\"{Environment.ProcessPath ?? Environment.GetCommandLineArgs()[0]}\"");
        else
            key.DeleteValue(ValueName, throwOnMissingValue: false);
    }
}
