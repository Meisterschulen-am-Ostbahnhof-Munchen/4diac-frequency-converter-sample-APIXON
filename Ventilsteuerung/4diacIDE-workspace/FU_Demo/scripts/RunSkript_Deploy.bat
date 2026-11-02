::Script
:: Spielt Boot-File, Libs-Manifest und ELF-Libs auf die APIXON - siehe
:: scripts_central/make_fu_demo_deploy.py.

@echo off & setlocal

cd /d "%~dp0"
python ..\..\..\scripts_central\make_fu_demo_deploy.py
