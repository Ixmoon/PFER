@echo off
echo Changing SVG icon colors...
for %%f in (icons\*.svg) do (
    powershell -Command "(Get-Content '%%f') -replace 'stroke=\"currentColor\"', 'stroke=\"#e0e0e0\"' | Set-Content '%%f'"
    echo Updated color for %%~nxf
)
echo All icons have been updated.