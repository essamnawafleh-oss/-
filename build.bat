@echo off
chcp 65001 >nul
REM بناء التطبيق على ويندوز محلياً (يتطلب Python 3.10+ و Inno Setup 6 للمُثبّت)
python -m pip install -r requirements.txt pyinstaller || exit /b 1
pyinstaller --noconfirm build.spec || exit /b 1
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss
  echo.
  echo المُثبّت جاهز في مجلد installer_output
) else (
  echo.
  echo التطبيق جاهز في dist\StreetStudies\StreetStudies.exe
  echo لصنع مُثبّت بأيقونة على سطح المكتب ثبّت Inno Setup 6 ثم أعد التشغيل.
)
