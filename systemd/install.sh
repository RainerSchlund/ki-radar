#!/bin/sh
# Installiert den täglichen Timer für den aktuellen Benutzer.
set -e
mkdir -p "$HOME/.config/systemd/user"
cp "$(dirname "$0")/ki-radar.service" "$(dirname "$0")/ki-radar.timer" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now ki-radar.timer
systemctl --user list-timers ki-radar.timer
