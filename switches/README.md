# Switches — start and really stop the bot

Three files you double-click. They control the two Windows services the demo runs as:

| Service | What it is |
|---|---|
| `n8n` | the workflow server, listening on `127.0.0.1:5678` |
| `ngrok` | the tunnel that publishes that port under the permanent hostname `flyable-rekindle-disobey.ngrok-free.dev` |

| Double-click | What it does |
|---|---|
| **`bot-on.bat`** | sets both services to Automatic and starts them, waits until n8n really answers, then checks the public address from the outside and reports what is up |
| **`bot-off.bat`** | stops both services **and** sets them to Disabled, so a reboot does not bring the demo back on its own |
| `bot-status.bat` | reports the state and changes nothing (read only, no administrator rights needed) |

## The one prompt, and why you will probably never see it again

Windows lets only administrators start or stop a service: each service carries its own access list,
and the default one gives ordinary users the right to read its status but not to start or stop it
(Microsoft documents this as *Service Security and Access Rights*, and the supported way to change it
is the service's own security descriptor).

So the switch does not fight the prompt, it removes the need for it. On its first run it appends a
single rule to these two services — and to nothing else — giving this account the five rights the
PowerShell service cmdlets need:

| Right | Needed for |
|---|---|
| `SERVICE_START` | starting the service |
| `SERVICE_STOP` | stopping it |
| `SERVICE_QUERY_STATUS` | reading whether it is running |
| `SERVICE_ENUMERATE_DEPENDENTS` | `Start-Service` / `Stop-Service`, which walk the dependency list |
| `SERVICE_CHANGE_CONFIG` | switching the service between Automatic and Disabled |

After that one prompt, `bot-on.bat`, `bot-off.bat` and `bot-status.bat` work with **no prompt at
all**, for ever, including after a reboot. `bot-status.bat` prints which of the two modes you are in
(`needs no permission prompt` / `will ask Windows once, then never again`).

Two honest notes:

- `SERVICE_CHANGE_CONFIG` lets the holder repoint a service at another executable, which is why
  Microsoft says to keep it for administrators. The rule is scoped to these two demo services and this
  one account, and the account is an administrator anyway (with Windows' usual filtered token), so it
  removes a prompt rather than crossing a trust boundary. If you would rather not have it, run
  `-Action revoke` (below) and accept one prompt per switch.
- Every run is written to `switches\last-run.log`, including the elevated part, and the window you
  double-clicked prints it. If you dismiss the Windows prompt, the switch says so instead of pretending
  it did something.

## Grant, revoke, and the log

```powershell
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action on        # start (no prompt after the first run)
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action off       # stop, and keep it off across a reboot
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action status    # report only, never changes anything
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action grant     # (re)apply the service rule, asks once
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action revoke    # put the original service rule back
```

`-Action grant` and `-Action revoke` are the only two that always need the prompt. `revoke` puts back
the descriptor that was there before the first grant: the original is saved in
`switches\service-sddl-backup.txt` when the first grant runs, and if that file is missing (a fresh
clone, or someone deleted it) `revoke` removes just its own rule from the current descriptor instead,
which comes to the same thing. Both files are runtime state and stay out of git.

## Why nothing has to be refreshed any more

The page reads `site/backend.json`, which names the tunnel hostname. That hostname belongs to the
account and is written in `D:\Tools\ngrok\ngrok.yml`, so it is the same after a restart, a crash or a
reboot. There is no republish step, and no watchdog script either: Windows starts both services at
boot and restarts them if they stop.

## What a visitor sees in each state

| State | The published page (`https://uhygyuf.github.io/rag-support-bot/`) |
|---|---|
| On | Loads, and the chat answers with the source file named, e.g. `… 7–14 business days. [faq.md]` |
| Off, or the machine is asleep | Still loads — GitHub hosts it — but a question gets `Sorry, our assistant is offline right now.` |

The page itself never depends on this machine being switched on; only the answering does.

## What the switches deliberately do not do

They never read a credential and never touch the database. Switching the bot off cannot delete
anything. (`start-demo.bat` in the project root is different: it clears the QA tickets so the table
looks clean on camera. Use `start-demo.bat -KeepTickets` if you do not want that.)

## If something goes wrong

| Symptom | What to do |
|---|---|
| The window says the permission prompt was cancelled | Nothing was changed. Double-click again and choose **Yes** |
| `bot-status.bat` says the switch will ask Windows once, and it does every time | The rule is missing, which is what happens if the services were reinstalled. Run `-Action grant` once |
| The status says the n8n service is not answering | `services.msc` → **n8n support bot** → Restart. Its output is in `D:\Tools\n8n\logs\n8n-service.*.log` |
| The status says the public tunnel does not answer | `services.msc` → **ngrok** → Restart. Its config is `D:\Tools\ngrok\ngrok.yml` |
| Opening the public address in a browser shows an ngrok notice page | Expected on the free plan: click through it. The demo page never sees it, because the widget sends a JSON POST |
| You want n8n up but not reachable from the internet | Run `D:\Tools\n8n\start-n8n.bat` by hand (local only, no tunnel) |
| The status says the published page points somewhere else | `site/backend.json` and `D:\Tools\ngrok\ngrok.yml` disagree. Fix whichever is wrong, then run `bot-status.bat` again |

## How these scripts know where things are

The switch itself knows two service names and one hostname; all three are constants at the top of
`switch-bot.ps1`. The service definitions live outside the repository, in the tool folders:

- `D:\Tools\n8n\service\n8n-service.xml` (WinSW wrapper for n8n)
- `D:\Tools\ngrok\ngrok.yml` (hostname, port, authtoken)
