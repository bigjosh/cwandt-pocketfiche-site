echo ** Starting the world builder. It will run every 60 seconds to update any new tiles.
echo ** Note that you MUST init with 'python incremental_build.py --parcels-dir %PF_DATA_DIR%\parcels --output-dir docs\world --init'
:loop
python incremental_build.py --parcels-dir %PF_DATA_DIR%\parcels --output-dir docs\world
@echo "Repeat? (Y=repeats, N=Quit, wait 60 seconds to auto repeat)"
choice /C YN /T 60 /D Y
if not errorlevel 2 goto :loop

