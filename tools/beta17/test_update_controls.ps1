$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$script=Get-Content (Join-Path $PSScriptRoot 'test_update_window.ps1') -Raw
$code=[regex]::Match($script,"(?s)Add-Type @'\r?\n(.*?)\r?\n'@").Groups[1].Value
if(-not $code){throw 'Native probe source missing'}
Add-Type $code
$form=New-Object Windows.Forms.Form
$button=New-Object Windows.Forms.Button
$button.Text='OK';$form.Controls.Add($button)
try {
    $form.Show()
    [Windows.Forms.Application]::DoEvents()
    $found=[UpdateWindowProbe]::FindOkButton($form.Handle)
    if($found -ne $button.Handle){throw ('Native button lookup failed: found='+$found+' actual='+$button.Handle)}
    if(-not [UpdateWindowProbe]::IsWindowEnabled($found)){throw 'Native probe button is disabled'}
    Write-Host 'PASS: native Windows control lookup.'
} finally {$form.Close();$form.Dispose()}
