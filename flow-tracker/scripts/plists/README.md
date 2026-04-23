# LaunchAgent plists

macOS LaunchAgent templates for flowtracker cron jobs. Files here end in `.plist.tmpl`
— they contain `__HOME__` placeholders that the installer substitutes with the
current user's `$HOME`. Companion shell scripts live in `../` and are expected to
be accessible at `$HOME/.local/share/flowtracker/scripts/` on the install host
(symlink or copy).

All jobs log to `$HOME/.local/share/flowtracker/cron.log`.

## Inventory

| Label | Schedule | Script |
| --- | --- | --- |
| `com.flowtracker.nightly-adj-close` | Daily 21:00 | `scripts/nightly-adj-close.sh` |
| `com.flowtracker.daily-fno` | Daily 18:30 | `scripts/daily-fno.sh` |
| `com.flowtracker.quarterly-fno-universe` | 1st of month 10:00 | `scripts/quarterly-fno-universe.sh` |

## Install

Run the install script from the `flow-tracker` directory:

```
bash scripts/install-launch-agents.sh
```

The script renders every `*.plist.tmpl` under `scripts/plists/` to
`~/Library/LaunchAgents/` (with `__HOME__` substituted), then `launchctl load`s
each one. Re-running is safe — existing plists are unloaded before reload.

## Verify

```
launchctl list | grep flowtracker
```

## Uninstall

```
launchctl unload ~/Library/LaunchAgents/com.flowtracker.<label>.plist
rm ~/Library/LaunchAgents/com.flowtracker.<label>.plist
```
