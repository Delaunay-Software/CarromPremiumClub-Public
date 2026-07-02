using System.Diagnostics;
using System.Text;

namespace CarromContentAdmin.Services;

public sealed record ProcessResult(int ExitCode, string Output)
{
    public bool Ok => ExitCode == 0;
}

/// <summary>
/// Thin wrapper over Process for shelling out to git / python / openssl. Merges
/// stdout+stderr in arrival order and, optionally, streams each line to a callback
/// so the UI can render live build output.
/// </summary>
public sealed class ProcessRunner
{
    public async Task<ProcessResult> RunAsync(
        string fileName,
        IEnumerable<string> args,
        string workingDir,
        IDictionary<string, string>? env = null,
        Action<string>? onLine = null,
        CancellationToken ct = default)
    {
        var psi = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (var a in args) psi.ArgumentList.Add(a);
        if (env != null)
            foreach (var kv in env) psi.Environment[kv.Key] = kv.Value;

        var sb = new StringBuilder();
        var gate = new object();
        void Sink(string? line)
        {
            if (line is null) return;
            lock (gate) sb.AppendLine(line);
            onLine?.Invoke(line);
        }

        using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (_, e) => Sink(e.Data);
        proc.ErrorDataReceived += (_, e) => Sink(e.Data);

        try
        {
            proc.Start();
        }
        catch (Exception ex)
        {
            return new ProcessResult(-1, $"failed to start '{fileName}': {ex.Message}");
        }

        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        await proc.WaitForExitAsync(ct).ConfigureAwait(false);
        // Let the async readers flush.
        proc.WaitForExit();

        lock (gate) return new ProcessResult(proc.ExitCode, sb.ToString());
    }
}
