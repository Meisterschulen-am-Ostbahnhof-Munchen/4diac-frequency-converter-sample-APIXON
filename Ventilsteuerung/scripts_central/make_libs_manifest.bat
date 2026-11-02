::Script
:: Erzeugt/aktualisiert nur lokal boot-files/FU_Demo_APIXON.libs.json - kein
:: Netzwerkzugriff. Siehe make_libs_manifest.py.

@echo off & setlocal

cd /d "%~dp0"
python make_libs_manifest.py
