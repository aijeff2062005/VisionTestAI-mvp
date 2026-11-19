using System.IO;
using System.Globalization;

namespace VisionAgent.Services;

public sealed record AgentLog(DateTime Time, string Message)
{
    public override string ToString() => $"{Time.ToString("HH:mm:ss", CultureInfo.CurrentCulture)}    {Message}";
}

public sealed class AgentLogWriter(string path)
{
    private readonly object _sync = new();

    public void Write(string message)
    {
        lock (_sync)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.AppendAllText(path, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {message}{Environment.NewLine}");
        }
    }

    public IReadOnlyList<AgentLog> ReadRecent(int count = 100)
    {
        lock (_sync)
        {
            if (!File.Exists(path)) return [];
            return File.ReadLines(path).TakeLast(count).Reverse().Select(line =>
            {
                var split = line.Split(' ', 2);
                if (split.Length == 2 && DateTime.TryParse($"{split[0]} {split[1][..Math.Min(8, split[1].Length)]}", out var time))
                    return new AgentLog(time, split[1].Length > 9 ? split[1][9..] : "");
                return new AgentLog(DateTime.Now, line);
            }).ToArray();
        }
    }
}
