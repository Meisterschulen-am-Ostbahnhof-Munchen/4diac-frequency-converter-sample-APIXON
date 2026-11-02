::Script
:: Spielt Boot-File, Libs-Manifest und ELF-Libs auf die APIXON (siehe
:: deploy_common.py) - siehe make_fu_demo_deploy.py fuer die Logik.

@echo off & setlocal

cd /d "%~dp0"
python make_fu_demo_deploy.py
