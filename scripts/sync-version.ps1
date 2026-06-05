#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Keep the plugin version in sync across the three places it appears.

.DESCRIPTION
  The version lives in three files and must match:
    1. plugins/swatkinson-toolkit/.claude-plugin/plugin.json   (source of truth)
    2. .claude-plugin/marketplace.json                          (metadata.version)
    3. README.md                                                (the "_Version X.Y.Z_" subtitle)

  Run with no arguments to CHECK that all three agree with plugin.json
  (exits 1 on any drift — suitable for CI or a pre-commit hook).

  Run with -Set <version> to WRITE that version to all three files.

.EXAMPLE
  pwsh scripts/sync-version.ps1
  # check mode: reports drift, exits 1 if the three disagree

.EXAMPLE
  pwsh scripts/sync-version.ps1 -Set 0.2.0
  # bump mode: writes 0.2.0 to all three files
#>
[CmdletBinding()]
param(
  [Parameter()]
  [string]$Set
)

$ErrorActionPreference = 'Stop'

# Resolve repo root from this script's location (scripts/ is one level down).
$repoRoot = Split-Path -Parent $PSScriptRoot

$pluginJson      = Join-Path $repoRoot 'plugins/swatkinson-toolkit/.claude-plugin/plugin.json'
$marketplaceJson = Join-Path $repoRoot '.claude-plugin/marketplace.json'
$readme          = Join-Path $repoRoot 'README.md'

# Each target: file path, a regex that captures the version in group 1, and a
# template to rebuild the matched line with a new version ({0} = new version).
$targets = @(
  @{ Name = 'plugin.json';      Path = $pluginJson;      Pattern = '("version":\s*")([^"]+)(")';     Template = '"version": "{0}"' }
  @{ Name = 'marketplace.json'; Path = $marketplaceJson; Pattern = '("version":\s*")([^"]+)(")';     Template = '"version": "{0}"' }
  @{ Name = 'README.md';        Path = $readme;          Pattern = '(_Version\s+)([^_]+)(_)';         Template = '_Version {0}_' }
)

# Read as UTF-8 explicitly. Windows PowerShell 5.1's Get-Content -Raw decodes
# with the ANSI codepage, which mangles the em-dashes / arrows / emoji in these
# files; .NET ReadAllText with UTF8 honours any BOM and decodes correctly.
function Read-Utf8 {
  param([string]$Path)
  return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Get-FileVersion {
  param($Target)
  $content = Read-Utf8 -Path $Target.Path
  $m = [regex]::Match($content, $Target.Pattern)
  if (-not $m.Success) {
    throw "Could not find a version in $($Target.Name) (pattern: $($Target.Pattern))"
  }
  return $m.Groups[2].Value.Trim()
}

if ($Set) {
  if ($Set -notmatch '^\d+\.\d+\.\d+') {
    throw "Version '$Set' does not look like semver (expected X.Y.Z)."
  }
  foreach ($t in $targets) {
    $content = Read-Utf8 -Path $t.Path
    $replacement = $t.Template -f $Set
    $updated = [regex]::Replace($content, $t.Pattern, $replacement, 1)
    if ($updated -ne $content) {
      # Write UTF-8 without a BOM, preserving the file's existing bytes elsewhere.
      $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
      [System.IO.File]::WriteAllText($t.Path, $updated, $utf8NoBom)
      Write-Host "  updated $($t.Name) -> $Set"
    } else {
      Write-Host "  $($t.Name) already at $Set"
    }
  }
  Write-Host "Version set to $Set in all three files." -ForegroundColor Green
  exit 0
}

# Check mode: compare every target against plugin.json (source of truth).
$source = Get-FileVersion -Target $targets[0]
$drift = @()
foreach ($t in $targets) {
  $v = Get-FileVersion -Target $t
  $ok = $v -eq $source
  $marker = if ($ok) { 'ok' } else { 'DRIFT' }
  Write-Host ("  {0,-18} {1,-10} {2}" -f $t.Name, $v, $marker)
  if (-not $ok) { $drift += $t.Name }
}

if ($drift.Count -gt 0) {
  Write-Host ""
  Write-Host "Version drift: $($drift -join ', ') do not match plugin.json ($source)." -ForegroundColor Red
  Write-Host "Fix with: pwsh scripts/sync-version.ps1 -Set $source"
  exit 1
}

Write-Host ""
Write-Host "All three in sync at $source." -ForegroundColor Green
exit 0
