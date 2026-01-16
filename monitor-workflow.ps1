#!/usr/bin/env pwsh

# 워크플로우 완료 모니터링 스크립트
$repo = "zecal0707-harry/scanner-project"
$maxWait = 600  # 10분

Write-Host "🚀 OpenCode 워크플로우 모니터링 시작..." -ForegroundColor Cyan
Write-Host "Repository: $repo" -ForegroundColor Cyan
Write-Host "최대 대기 시간: $maxWait초" -ForegroundColor Cyan
Write-Host ""

$startTime = Get-Date
$checkInterval = 5

while ([int]((Get-Date) - $startTime).TotalSeconds -lt $maxWait) {
    $run = gh run list --repo $repo -L 1 --json "number,status,conclusion,updatedAt" 2>$null | ConvertFrom-Json | Select-Object -First 1
    
    $elapsed = (Get-Date) - $startTime
    $elapsedStr = "{0:d2}:{1:d2}" -f [int]$elapsed.TotalMinutes, $elapsed.Seconds
    
    Write-Host "⏳ [$elapsedStr] 진행 중... (Run #$($run.number), Status=$($run.status))" -ForegroundColor Yellow
    
    if ($run.status -eq "completed") {
        if ($run.conclusion -eq "success") {
            Write-Host "✅ [$elapsedStr] 워크플로우 성공!" -ForegroundColor Green
            break
        } else {
            Write-Host "❌ [$elapsedStr] 워크플로우 완료: $($run.conclusion)" -ForegroundColor Red
            break
        }
    }
    
    Start-Sleep -Seconds $checkInterval
}

# 최종 결과
Write-Host ""
Write-Host "📊 최종 상태 조회..." -ForegroundColor Cyan
gh run list --repo $repo -L 1 --json "number,status,conclusion,name,updatedAt"
