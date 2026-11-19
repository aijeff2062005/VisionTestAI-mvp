using System.IO;
using System.Text.Json;

namespace VisionAgent.Services;

public sealed class ProcessedState(string path)
{
    private readonly object _sync = new();
    private readonly HashSet<string> _keys = LoadKeys(path);

    public bool Contains(string key)
    {
        lock (_sync) return _keys.Contains(key);
    }

    public void Add(string key)
    {
        lock (_sync)
        {
            if (!_keys.Add(key)) return;
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var temp = path + ".tmp";
            File.WriteAllText(temp, JsonSerializer.Serialize(_keys));
            File.Move(temp, path, true);
        }
    }

    private static HashSet<string> LoadKeys(string path)
    {
        try
        {
            return File.Exists(path)
                ? JsonSerializer.Deserialize<HashSet<string>>(File.ReadAllText(path)) ?? new HashSet<string>()
                : new HashSet<string>();
        }
        catch
        {
            return new HashSet<string>();
        }
    }
}
