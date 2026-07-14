$action = New-ScheduledTaskAction -Execute "C:\Users\ajou\Desktop\autoRe-agent\pg_backup.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At "09:00AM"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable:$false
Register-ScheduledTask -TaskName "autoRe_pg_backup" -Action $action -Trigger $trigger -Settings $settings -Description "reagent DB 일일 pg_dump 백업" -RunLevel Highest -Force
Write-Host "등록 완료" -ForegroundColor Green
