# LaunchAgent plists

macOS LaunchAgent definitions for flowtracker cron jobs. Companion shell scripts live in `../` and are expected to be accessible at `/Users/tarang/.local/share/flowtracker/scripts/` on the install host (symlink or copy).

All jobs log to `/Users/tarang/.local/share/flowtracker/cron.log`.

## Inventory

| Label | Schedule | Script |
| --- | --- | --- |
| `com.flowtracker.nightly-adj-close` | Daily 21:00 | `scripts/nightly-adj-close.sh` |
| `com.flowtracker.daily-fno` | Daily 18:30 | `scripts/daily-fno.sh` |
| `com.flowtracker.quarterly-fno-universe` | 1st of month 10:00 | `scripts/quarterly-fno-universe.sh` |

## Install

```
cp scripts/plists/com.flowtracker.nightly-adj-close.plist ~/Library/LaunchAgents/
cp scripts/plists/com.flowtracker.daily-fno.plist ~/Library/LaunchAgents/
cp scripts/plists/com.flowtracker.quarterly-fno-universe.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.flowtracker.nightly-adj-close.plist
launchctl load ~/Library/LaunchAgents/com.flowtracker.daily-fno.plist
launchctl load ~/Library/LaunchAgents/com.flowtracker.quarterly-fno-universe.plist
```

## Verify

```
launchctl list | grep flowtracker
```

## Uninstall

```
launchctl unload ~/Library/LaunchAgents/com.flowtracker.<label>.plist
rm ~/Library/LaunchAgents/com.flowtracker.<label>.plist
```
