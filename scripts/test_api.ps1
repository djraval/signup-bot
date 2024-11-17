# Test script for Old Navy/Gap Promo Fetcher API
$baseUrl = "http://localhost:5000"

Write-Host "Testing Old Navy/Gap Promo Fetcher API..." -ForegroundColor Cyan

# Function to fetch promo codes
function Get-PromoCodes {
    param (
        [string]$retailer
    )
    
    Write-Host "`nFetching promo codes for $retailer..." -ForegroundColor Yellow
    
    $body = @{
        retailer = $retailer
    } | ConvertTo-Json
    
    try {
        # Initial request to create the task
        $response = Invoke-RestMethod -Uri "$baseUrl/api/promo" -Method Post -Body $body -ContentType "application/json"
        $taskId = $response.task_id
        $statusUrl = $response.status_url
        
        # Poll for results
        do {
            Start-Sleep -Seconds 2
            $status = Invoke-RestMethod -Uri $statusUrl -Method Get
            
            # Show progress based on status
            switch ($status.status) {
                "queued" { Write-Host "Waiting in queue..." -ForegroundColor Yellow }
                "subscribing" { Write-Host "Subscribing with email: $($status.email)" -ForegroundColor Yellow }
                "waiting_for_email" { Write-Host "Waiting for promotional email..." -ForegroundColor Yellow }
                "failed" { 
                    Write-Host "Error: $($status.error)" -ForegroundColor Red
                    return $null
                }
            }
            
        } while ($status.status -notin @("completed", "failed"))
        
        # Show results
        Write-Host "Success!" -ForegroundColor Green
        Write-Host "`nResults for $retailer" -ForegroundColor Cyan
        Write-Host "Email used: $($status.email)" -ForegroundColor Green
        Write-Host "Promo Codes:" -ForegroundColor Green
        Write-Host ($status.codes | ConvertTo-Json -Depth 10)
        return $status
        
    }
    catch {
        Write-Host "Error fetching promo codes!" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        return $null
    }
}

# Test Old Navy
$oldNavyResults = Get-PromoCodes -retailer "oldnavy"

# Test Gap
$gapResults = Get-PromoCodes -retailer "gap"

Write-Host "`nTesting complete!" -ForegroundColor Cyan
