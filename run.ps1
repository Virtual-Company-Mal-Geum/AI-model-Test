param(
    [string]$Config = "questions.json",
    [switch]$PauseForLogin
)

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Virtual environment was not found. Run the install commands in README.md first."
    exit 1
}

$Script = Join-Path $PSScriptRoot "src\chatgpt_macro.py"
$ConfigPath = if ([System.IO.Path]::IsPathRooted($Config)) {
    $Config
} else {
    Join-Path $PSScriptRoot $Config
}

$Args = @($Script, "--config", $ConfigPath)
if ($PauseForLogin) {
    $Args += "--pause-for-login"
}

& $Python @Args
