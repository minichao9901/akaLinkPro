@echo off
@cd /d "%~dp0"
@REM ---------------------------------------------------------------------------
@REM Application build for the akaLinkPro board (BOARD=akaLinkPro).
@REM
@REM Links the APP at 0x80000000 + 0x20000 = 0x80020000 (right after the 128K
@REM bootloader) with linker/flash_dfu_app.ld; the APP entry moves to 0x80020100
@REM so the first 256 bytes stay free for the integrity/version header.
@REM Output can be either:
@REM   - flashed by J-Link directly at 0x80020000 (see flash_jlink.bat), or
@REM   - transferred by dfu-util (see program.bat).
@REM
@REM HPM SDK 1.11+ removed the flash_dfu build type, so the default here is the
@REM flash_xip emulation used by the hpm5301evklite build (custom linker script
@REM + -DFLASH_XIP=0 -DFLASH_DFU=1 in CMakeLists.txt). Set HPM_BUILD_TYPE=flash_dfu
@REM when building against an older SDK that still ships that type.
@REM
@REM Toolchain paths point at the local sdk_env install (E:\sdk_env_v1.11.0);
@REM override by setting HPM_SDK_ENV_DIR before running.
@REM ---------------------------------------------------------------------------
@if not defined HPM_SDK_ENV_DIR set "HPM_SDK_ENV_DIR=E:\sdk_env_v1.11.0"
@if not defined HPM_BUILD_TYPE set "HPM_BUILD_TYPE=flash_xip"

@set "HPM_TOOLCHAIN_PATH=%HPM_SDK_ENV_DIR%"
@set "PATH=%HPM_TOOLCHAIN_PATH%\tools\python3;%HPM_TOOLCHAIN_PATH%\tools\cmake\bin;%HPM_TOOLCHAIN_PATH%\tools\ninja;%PATH%"
@set "HPM_SDK_BASE=%HPM_TOOLCHAIN_PATH%\hpm_sdk"
@set "GNURISCV_TOOLCHAIN_PATH=%HPM_TOOLCHAIN_PATH%\toolchains\rv32imac_zicsr_zifencei_multilib_b_ext-win"
@set "HPM_SDK_TOOLCHAIN_VARIANT=gcc"
@set "BOARD=akaLinkPro"

@cmake -G Ninja -DBOARD=%BOARD% -DHPM_BUILD_TYPE=%HPM_BUILD_TYPE% -DCMAKE_BUILD_TYPE=debug -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -B=./build_dfu -S .
@if errorlevel 1 exit /b %errorlevel%
@cmake --build ./build_dfu
@if errorlevel 1 exit /b %errorlevel%

@echo.
@echo [build_dfu] ELF: build_dfu\output\akaLinkPro_App.elf
@echo [build_dfu] APP image (flash this): build_dfu\output\akaLinkPro_App_pack.hex / _pack.bin (linked at 0x80020000, entry 0x80020100)
@echo [build_dfu] raw (no header): build_dfu\output\akaLinkPro_App.hex / .bin
