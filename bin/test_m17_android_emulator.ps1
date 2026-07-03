param(
    [string]$AndroidProject = "device_edge/android_edge",
    [string]$AvdName = "",
    [string]$TestClass = "dev.openhalo.android.edge.M17AndroidEdgeComposeTest",
    [int]$BootTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

function Resolve-AndroidSdk {
    $candidates = @()
    if ($env:ANDROID_HOME) {
        $candidates += $env:ANDROID_HOME
    }
    if ($env:ANDROID_SDK_ROOT) {
        $candidates += $env:ANDROID_SDK_ROOT
    }

    $localProperties = Join-Path $PSScriptRoot "..\device_edge\android_edge\local.properties"
    if (Test-Path $localProperties) {
        foreach ($line in Get-Content $localProperties) {
            if ($line -match "^sdk\.dir=(.+)$") {
                $candidates += ($Matches[1] -replace "\\:", ":" -replace "\\\\", "\")
            }
        }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path (Join-Path $candidate "platform-tools\adb.exe"))) {
            return $candidate
        }
    }

    throw "Android SDK not found. Start Android Studio once or set ANDROID_HOME/ANDROID_SDK_ROOT to the SDK root."
}

function Require-Tool([string]$path) {
    if (-not (Test-Path $path)) {
        throw "Required tool not found: $path"
    }
    return $path
}

function Run-Checked([string]$file, [string[]]$arguments, [string]$workingDirectory = ".") {
    Write-Host ">> $file $($arguments -join ' ')"
    Push-Location $workingDirectory
    try {
        & $file @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $file"
        }
    } finally {
        Pop-Location
    }
}

function Run-InstrumentationChecked([string]$adb, [string[]]$arguments) {
    Write-Host ">> $adb $($arguments -join ' ')"
    $output = & $adb @arguments 2>&1
    $output | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "Instrumentation command failed with exit code ${LASTEXITCODE}: $adb"
    }
    $text = $output -join "`n"
    if ($text -match "FAILURES!!!" -or $text -match "Process crashed" -or $text -match "INSTRUMENTATION_RESULT: shortMsg=Error") {
        throw "Instrumentation tests failed."
    }
    if ($text -notmatch "OK \(") {
        throw "Instrumentation result did not include an OK summary."
    }
}

function Online-Emulators([string]$adb) {
    $result = @()
    $devices = & $adb devices
    foreach ($line in $devices) {
        if ($line -match "^(emulator-\d+)\s+device$") {
            $result += $Matches[1]
        }
    }
    return $result
}

function Online-PhysicalDevices([string]$adb) {
    $result = @()
    $devices = & $adb devices
    foreach ($line in $devices) {
        if ($line -match "^(\S+)\s+device$" -and -not $Matches[1].StartsWith("emulator-")) {
            $result += $Matches[1]
        }
    }
    return $result
}

function Wait-For-EmulatorBoot([string]$adb, [string]$serial, [int]$timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $booted = (& $adb -s $serial shell getprop sys.boot_completed 2>$null).Trim()
        if ($booted -eq "1") {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Emulator did not finish booting within $timeoutSeconds seconds: $serial"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$projectRoot = Resolve-Path (Join-Path $repoRoot $AndroidProject)
$sdk = Resolve-AndroidSdk
$adb = Require-Tool (Join-Path $sdk "platform-tools\adb.exe")
$emulatorTool = Require-Tool (Join-Path $sdk "emulator\emulator.exe")
$gradle = Require-Tool (Join-Path $projectRoot "gradlew.bat")

$emulators = @(Online-Emulators $adb)
if ($emulators.Count -eq 0) {
    $knownAvds = @(& $emulatorTool -list-avds)
    if ($AvdName -eq "") {
        if ($knownAvds.Count -eq 1) {
            $AvdName = $knownAvds[0]
        } else {
            throw "No emulator is online. Start one from Android Studio Device Manager or rerun with -AvdName. Known AVDs: $($knownAvds -join ', ')"
        }
    }
    if (-not ($knownAvds -contains $AvdName)) {
        throw "AVD not found: $AvdName. Known AVDs: $($knownAvds -join ', ')"
    }
    Write-Host ">> starting existing Android Studio AVD: $AvdName"
    Start-Process -FilePath $emulatorTool -ArgumentList @(
        "-avd", $AvdName,
        "-no-snapshot-save",
        "-no-boot-anim",
        "-netdelay", "none",
        "-netspeed", "full"
    ) | Out-Null
    Run-Checked $adb @("wait-for-device")
    Start-Sleep -Seconds 2
    $emulators = @(Online-Emulators $adb)
}
if ($emulators.Count -gt 1) {
    throw "More than one emulator is online: $($emulators -join ', '). Close extras or set one active before rerunning."
}

$physicalDevices = @(Online-PhysicalDevices $adb)
if ($physicalDevices.Count -gt 0) {
    Write-Host "Ignoring physical adb device(s): $($physicalDevices -join ', ')"
}

$serial = $emulators[0]
Wait-For-EmulatorBoot $adb $serial $BootTimeoutSeconds

Run-Checked $gradle @(":app:testDebugUnitTest", ":app:assembleDebug", ":app:assembleDebugAndroidTest") $projectRoot

$debugApk = Join-Path $projectRoot "app\build\outputs\apk\debug\app-debug.apk"
$testApk = Join-Path $projectRoot "app\build\outputs\apk\androidTest\debug\app-debug-androidTest.apk"
Require-Tool $debugApk | Out-Null
Require-Tool $testApk | Out-Null

Run-Checked $adb @("-s", $serial, "install", "-r", "-t", $debugApk)
Run-Checked $adb @("-s", $serial, "install", "-r", "-t", $testApk)
Run-InstrumentationChecked $adb @(
    "-s", $serial,
    "shell", "am", "instrument", "-w",
    "-e", "class", $TestClass,
    "dev.openhalo.android.edge.test/androidx.test.runner.AndroidJUnitRunner"
)

Write-Host "ok: M17 Android emulator tests passed on $serial"
