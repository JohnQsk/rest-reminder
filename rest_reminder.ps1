param (
    [int]$WorkTime_s = 20 * 60,   # Work time per cycle, in seconds
    [int]$BreakTime_s = 20,       # Break time per cycle, in seconds
    [int]$TotalCycles = 30,       # Total number of cycles
    [switch]$Gentle               # Prefer a system notification over the popup
)

function Show-Notification {
    param(
        [Parameter(Mandatory)][string]$Message,
        [string]$Title = 'Health Reminder',
        [switch]$Gentle
    )

    if ($Gentle) {
        # Opt-in gentle mode: a normal Windows toast, which does not steal focus.
        if (Get-Module -ListAvailable -Name BurntToast) {
            Import-Module BurntToast -ErrorAction Stop
            New-BurntToastNotification -Text $Title, $Message
            return
        }
        Write-Warning 'Gentle mode requested but the BurntToast module is not installed; falling back to the topmost popup. Install it with: Install-Module BurntToast -Scope CurrentUser'
    }

    # Topmost dialog.
    # A timer re-asserts TopMost every second (SetWindowPos is not subject to
    # the foreground lock), so the dialog climbs back above all windows
    # until the user clicks OK.
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = $Title
    $form.TopMost = $true
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.ClientSize = New-Object System.Drawing.Size(400, 180)

    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Message
    $label.Dock = 'Fill'
    $label.TextAlign = 'MiddleCenter'
    $form.Controls.Add($label)

    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = 'OK'
    $ok.Dock = 'Bottom'
    $ok.Height = 32
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.Add($ok)
    $form.AcceptButton = $ok

    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 1000
    $timer.add_Tick({
        # Toggling TopMost forces the window back to the top of the z-order
        $form.TopMost = $false
        $form.TopMost = $true
        $form.BringToFront()
        $form.Activate()
    })
    $timer.Start()

    try {
        $form.ShowDialog() | Out-Null
    }
    finally {
        $timer.Stop()
        $timer.Dispose()
        $form.Dispose()
    }
}

function Start-RestReminder {
    param(
        [int]$WorkTime_s,
        [int]$BreakTime_s,
        [int]$TotalCycles,
        [switch]$Gentle
    )

    for ($i = 1; $i -le $TotalCycles; $i++) {
        Write-Host ''
        Write-Host "=== Work Cycle $i/$TotalCycles ===" -ForegroundColor Cyan
        Write-Host "Working... (Next break in $([math]::Round($WorkTime_s / 60, 1)) minutes)" -ForegroundColor Gray
        # Work time countdown
        for ($sec = $WorkTime_s; $sec -gt 0; $sec--) {
            Write-Progress -Activity 'Work Countdown' -Status "Time remaining: $sec seconds" -PercentComplete (($WorkTime_s - $sec) / $WorkTime_s * 100)
            Start-Sleep -Seconds 1
        }

        # Break reminder
        Show-Notification -Title 'Health Reminder' -Gentle:$Gentle -Message "Work session complete! Please take a $BreakTime_s second break.`n- Stretch your neck and shoulders`n- Look at something 20 feet away`n- Drink some water"

        Write-Host "Taking break... ($BreakTime_s seconds)" -ForegroundColor Green

        # Break time countdown
        for ($sec = $BreakTime_s; $sec -gt 0; $sec--) {
            Write-Progress -Activity 'Break Countdown' -Status "Time remaining: $sec seconds" -PercentComplete (($BreakTime_s - $sec) / $BreakTime_s * 100)
            Start-Sleep -Seconds 1
        }
    }

    Write-Host ''
    Write-Host "Daily session complete! Finished $TotalCycles pomodoro cycles." -ForegroundColor Magenta
    Show-Notification -Title 'Health Reminder' -Gentle:$Gentle -Message 'Daily work session completed! Remember to stay active!'
}

# Allow dot-sourcing for reuse; run automatically only when invoked directly.
if ($MyInvocation.InvocationName -ne '.') {
    Start-RestReminder -WorkTime_s $WorkTime_s -BreakTime_s $BreakTime_s -TotalCycles $TotalCycles -Gentle:$Gentle
}
