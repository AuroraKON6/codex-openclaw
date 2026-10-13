Set-StrictMode -Version Latest

function Resolve-QuantPython {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $root = [IO.Path]::GetFullPath($ProjectRoot)
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Project Python environment is missing. Run .\bootstrap_python.ps1 first."
    }

    $version = (& $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^3\.11\.') {
        throw "Project Python must be CPython 3.11.x; found '$version' at $python."
    }
    return (Resolve-Path -LiteralPath $python).Path
}
