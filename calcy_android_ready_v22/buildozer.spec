[app]
title = Calcy
package.name = calcy
package.domain = org.calcy
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt,ttf
source.exclude_dirs = tests,__pycache__,.git,.github
source.exclude_exts = pyc,pyo
version = 1.5.0
requirements = python3,kivy==2.3.1,pillow,charset-normalizer==2.1.1
orientation = portrait
fullscreen = 0

# Android
android.api = 35
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

# Performance / packaging
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1
