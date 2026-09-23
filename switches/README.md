# Switches — start and really stop the bot

Two files you double-click. They control the two Windows services the demo runs as:

| Service | What it is |
|---|---|
| `n8n` | the workflow server, listening on `127.0.0.1:5678` |
| `ngrok` | the tunnel that publishes that port under the permanent hostname `flyable-rekindle-disobey.ngrok-free.dev` |

| Double-click | What it does |
|---|---|
| **`bot-on.bat`** | sets both services to Automatic and starts them, waits until n8n really answers, then checks the public address from the outside and reports what is up |
| **`bot-off.bat`** | stops both services **and** sets them to Disabled, so a reboot does not bring the demo back on its own |
| `bot-status.bat` | reports the state and changes nothing (read only, no administrator rights needed) |

Starting and stopping a service needs administrator rights, so `bot-on.bat` and `bot-off.bat` trigger
one Windows prompt and then do the work in the elevated window. `bot-status.bat` never does.

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

Commands, if you prefer a terminal:

```powershell
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action on
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action off
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action status
```
