param(
  [switch]$OneFile,
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Resolve-DesktopPython {
  if ($env:RESERVOIR_DESKTOP_PYTHON) {
    return $env:RESERVOIR_DESKTOP_PYTHON
  }

  $defaultEnv = Join-Path $env:USERPROFILE "miniconda3\envs\reservoir_desktop\python.exe"
  if (Test-Path $defaultEnv) {
    return $defaultEnv
  }

  return "python"
}

function Add-PythonRuntimeToPath([string]$PythonExe) {
  $pythonCommand = Get-Command $PythonExe -ErrorAction Stop
  $pythonPath = $pythonCommand.Source
  $pythonDir = Split-Path -Parent $pythonPath
  $pathParts = @($pythonDir)

  $libraryBin = Join-Path $pythonDir "Library\bin"
  if (Test-Path $libraryBin) {
    $pathParts += $libraryBin
  }

  $scriptsDir = Join-Path $pythonDir "Scripts"
  if (Test-Path $scriptsDir) {
    $pathParts += $scriptsDir
  }

  $env:PATH = (($pathParts + $env:PATH) -join ";")
  return $pythonPath
}

$projectRoot = (Get-Location).Path
$pythonExe = Resolve-DesktopPython
$pythonExe = Add-PythonRuntimeToPath $pythonExe

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:NUITKA_CACHE_DIR = Join-Path $projectRoot ".nuitka-cache"
New-Item -ItemType Directory -Force -Path $env:NUITKA_CACHE_DIR | Out-Null

Write-Host "Using Python: $pythonExe"
& $pythonExe -c "import PySide6, matplotlib, numpy, pandas; import nuitka; print('Desktop dependencies OK')"

$previousQtPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = "offscreen"
try {
  & $pythonExe run_desktop_dashboard.py --smoke-test
} finally {
  if ($null -eq $previousQtPlatform) {
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
  } else {
    $env:QT_QPA_PLATFORM = $previousQtPlatform
  }
}

$outputDir = Join-Path $projectRoot "dist"
$standaloneDir = Join-Path $outputDir "run_desktop_dashboard.dist"
$packageDir = Join-Path $outputDir "ReservoirDashboardDesktop"
$oneFileExe = Join-Path $outputDir "ReservoirDashboardDesktop.exe"
$standaloneExe = Join-Path $packageDir "ReservoirDashboardDesktop.exe"

if ($Clean) {
  foreach ($path in @(
      (Join-Path $outputDir "run_desktop_dashboard.build"),
      $standaloneDir,
      $packageDir,
      (Join-Path $outputDir "run_desktop_dashboard.onefile-build"),
      $oneFileExe
    )) {
    if (Test-Path $path) {
      Remove-Item -LiteralPath $path -Recurse -Force
    }
  }
}

$nuitkaArgs = @(
  "-m", "nuitka",
  "--standalone",
  "--assume-yes-for-downloads",
  "--windows-console-mode=disable",
  "--enable-plugin=pyside6",
  "--include-data-dir=data=data",
  "--include-package-data=matplotlib",
  "--nofollow-import-to=streamlit",
  "--nofollow-import-to=plotly",
  "--nofollow-import-to=pytest",
  "--output-dir=dist",
  "--output-filename=ReservoirDashboardDesktop.exe",
  "run_desktop_dashboard.py"
)

if ($OneFile) {
  $nuitkaArgs = @(
    "-m", "nuitka",
    "--onefile"
  ) + $nuitkaArgs[2..($nuitkaArgs.Count - 1)]
}

Write-Host "Building desktop executable with Nuitka..."
& $pythonExe @nuitkaArgs

if ($OneFile) {
  if (-not (Test-Path $oneFileExe)) {
    throw "Build finished, but expected output was not found: $oneFileExe"
  }
  Write-Host "Built: $oneFileExe"
} else {
  $rawStandaloneExe = Join-Path $standaloneDir "ReservoirDashboardDesktop.exe"
  if (-not (Test-Path $rawStandaloneExe)) {
    throw "Build finished, but expected output was not found: $rawStandaloneExe"
  }
  if (Test-Path $packageDir) {
    Remove-Item -LiteralPath $packageDir -Recurse -Force
  }
  Move-Item -LiteralPath $standaloneDir -Destination $packageDir
  if (-not (Test-Path $standaloneExe)) {
    throw "Build finished, but expected output was not found: $standaloneExe"
  }
  Write-Host "Built: $standaloneExe"
  Write-Host "Distribute the whole folder: $packageDir"
}
