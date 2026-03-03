#!/usr/bin/env bash
export AVALONIA_SCREEN_SCALE_FACTORS="DP-3=2;DP-2=2"
exec ryujinx "$@"
