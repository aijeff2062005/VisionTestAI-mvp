#!/usr/bin/env bash

set -u

#
# =========================================================
# Jetson Kiosk Launcher
# =========================================================
#

CONFIG_FILE="$HOME/.config/jetson-kiosk/config.env"

LOG_DIR="$HOME/jetson-kiosk/logs"
LOG_FILE="$LOG_DIR/kiosk.log"

LOCK_FILE="$HOME/jetson-kiosk/kiosk.lock"

PROFILE_DIR="$HOME/.config/google-chrome/kiosk-profile"

BROWSER="/usr/bin/google-chrome-stable"

UNCLUTTER_PID=""


#
# =========================================================
# Prepare directories
# =========================================================
#

mkdir -p "$LOG_DIR"
mkdir -p "$PROFILE_DIR"


#
# =========================================================
# Logging
# =========================================================
#

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"
}


#
# =========================================================
# Prevent multiple launcher instances
# =========================================================
#

exec 9>"$LOCK_FILE"

if ! flock -n 9; then
    log "Another kiosk launcher is already running. Exit."
    exit 0
fi


#
# =========================================================
# Cleanup
# =========================================================
#

cleanup() {

    log "Kiosk launcher stopping"

    if [ -n "${UNCLUTTER_PID:-}" ]; then
        kill "$UNCLUTTER_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM


#
# =========================================================
# Load configuration
# =========================================================
#

if [ ! -f "$CONFIG_FILE" ]; then
    log "ERROR: Config file not found: $CONFIG_FILE"
    exit 1
fi

set -a
source "$CONFIG_FILE"
set +a


if [ -z "${KIOSK_URL:-}" ]; then
    log "ERROR: KIOSK_URL is empty"
    exit 1
fi


#
# =========================================================
# Check browser
# =========================================================
#

if [ ! -x "$BROWSER" ]; then
    log "ERROR: Chromium not found: $BROWSER"
    exit 1
fi


#
# =========================================================
# Check graphical session
# =========================================================
#

if [ -z "${DISPLAY:-}" ]; then
    log "ERROR: DISPLAY is not set"
    exit 1
fi


#
# =========================================================
# Startup information
# =========================================================
#

log "=================================================="
log "Jetson Kiosk Launcher started"
log "PID=$$"
log "URL=$KIOSK_URL"
log "Browser=$BROWSER"
log "Profile=$PROFILE_DIR"
log "DISPLAY=${DISPLAY:-}"
log "=================================================="


#
# =========================================================
# Disable screen blanking / screensaver
# =========================================================
#

if command -v xset >/dev/null 2>&1; then

    xset s off 2>/dev/null || true
    xset s noblank 2>/dev/null || true
    xset -dpms 2>/dev/null || true

fi

# The connected Samsung display is limited to 4K at 30 Hz on this TMDS link.
# 1920x1080 at 60 Hz keeps software compositing responsive.
if command -v xrandr >/dev/null 2>&1; then
    if xrandr --output DP-1 --mode 1920x1080 --rate 60.00; then
        log "Display set to 1920x1080 at 60.00 Hz"
    else
        log "WARNING: Could not set 1920x1080 at 60.00 Hz"
    fi
fi


#
# =========================================================
# Hide mouse cursor
#
# IMPORTANT:
# Close FD 9 so unclutter does NOT inherit the flock.
# =========================================================
#

if command -v unclutter >/dev/null 2>&1; then

    unclutter \
        -idle 1 \
        -root \
        9>&- \
        >/dev/null 2>&1 &

    UNCLUTTER_PID=$!

    log "unclutter started PID=$UNCLUTTER_PID"
fi


#
# =========================================================
# Chromium watchdog
# =========================================================
#

while true; do

    log "Starting Chromium"

    #
    # GPU compositing stopped presenting new frames after a long exam on this Jetson.
    # Use software rendering for the kiosk page.
    # 9>&- prevents Chrome and its child processes
    # from inheriting the kiosk flock descriptor.
    #

    "$BROWSER" \
        --kiosk \
        --disable-gpu \
        --no-first-run \
        --no-default-browser-check \
        --disable-session-crashed-bubble \
        --disable-infobars \
        --disable-features=TranslateUI \
        --disable-translate \
        --disable-pinch \
        --overscroll-history-navigation=0 \
        --user-data-dir="$PROFILE_DIR" \
        "$KIOSK_URL" \
        9>&-

    EXIT_CODE=$?

    log "Chromium exited with code=$EXIT_CODE"

    sleep "${RESTART_DELAY:-3}"

done
