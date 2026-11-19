using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using VisionAgent.Models;

namespace VisionAgent.Services;

public sealed class ConfigStore
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    public string DataDirectory { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "VisionAgent");
    public string LogPath => Path.Combine(DataDirectory, "vision-agent.log");
    public string StatePath => Path.Combine(DataDirectory, "processed-files.json");
    private string ConfigPath => Path.Combine(DataDirectory, "config.json");
    private string CredentialsPath => Path.Combine(DataDirectory, "credentials.dat");

    public (AgentConfig Config, ApiCredentials Credentials) Load()
    {
        Directory.CreateDirectory(DataDirectory);
        var config = File.Exists(ConfigPath)
            ? JsonSerializer.Deserialize<AgentConfig>(File.ReadAllText(ConfigPath)) ?? new AgentConfig()
            : new AgentConfig();
        var credentials = File.Exists(CredentialsPath)
            ? JsonSerializer.Deserialize<ApiCredentials>(Dpapi.Unprotect(File.ReadAllBytes(CredentialsPath))) ?? new ApiCredentials()
            : new ApiCredentials();
        return (config, credentials);
    }

    public void Save(AgentConfig config, ApiCredentials credentials)
    {
        Directory.CreateDirectory(DataDirectory);
        var configTemp = ConfigPath + ".tmp";
        File.WriteAllText(configTemp, JsonSerializer.Serialize(config, JsonOptions));
        File.Move(configTemp, ConfigPath, true);

        var protectedCredentials = Dpapi.Protect(JsonSerializer.SerializeToUtf8Bytes(credentials));
        var credentialsTemp = CredentialsPath + ".tmp";
        File.WriteAllBytes(credentialsTemp, protectedCredentials);
        File.Move(credentialsTemp, CredentialsPath, true);
    }
}

internal static class Dpapi
{
    [StructLayout(LayoutKind.Sequential)]
    private struct DataBlob
    {
        public int Size;
        public IntPtr Data;
    }

    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CryptProtectData(ref DataBlob input, string? description, IntPtr entropy,
        IntPtr reserved, IntPtr prompt, uint flags, out DataBlob output);

    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CryptUnprotectData(ref DataBlob input, out IntPtr description, IntPtr entropy,
        IntPtr reserved, IntPtr prompt, uint flags, out DataBlob output);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr memory);

    public static byte[] Protect(byte[] clearText) => Transform(clearText, protect: true);
    public static byte[] Unprotect(byte[] cipherText) => Transform(cipherText, protect: false);

    private static byte[] Transform(byte[] inputBytes, bool protect)
    {
        var inputMemory = Marshal.AllocHGlobal(inputBytes.Length);
        Marshal.Copy(inputBytes, 0, inputMemory, inputBytes.Length);
        var input = new DataBlob { Size = inputBytes.Length, Data = inputMemory };
        DataBlob output = default;
        IntPtr description = IntPtr.Zero;
        try
        {
            var ok = protect
                ? CryptProtectData(ref input, "Vision Agent credentials", IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0, out output)
                : CryptUnprotectData(ref input, out description, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0, out output);
            if (!ok) throw new CryptographicException(Marshal.GetLastWin32Error());
            var result = new byte[output.Size];
            Marshal.Copy(output.Data, result, 0, output.Size);
            return result;
        }
        finally
        {
            Marshal.FreeHGlobal(inputMemory);
            if (output.Data != IntPtr.Zero) LocalFree(output.Data);
            if (description != IntPtr.Zero) LocalFree(description);
        }
    }
}
