# Switches — start and really stop the bot

Two files you double-click. Nothing else in this folder is needed for daily use.

| Double-click | What it does |
|---|---|
| **`bot-on.bat`** | Leaves the self-healing task enabled, starts n8n and the public tunnel if needed, checks the tunnel from the outside and only replaces it when the edge does not answer at all (a tunnel whose service is merely still booting is waited for), restarts n8n when the address changed so it knows the new one, refreshes the address the hosted page reads, and reports what is actually up |
| **`bot-off.bat`** | Disables the self-healing task **first**, then stops n8n and the tunnel |
| `bot-status.bat` | Reports the state and changes nothing (useful before a demo) |

## Why stopping is two steps, not one

The scheduled task `n8n watchdog` restarts n8n within about five minutes whenever it is missing —
that is the self-healing that keeps the demo alive through crashes. It also means "stop n8n" alone is
not "stop the bot": the service would be back before you finished closing the window. `bot-off.bat`
therefore disables the task and stops the service, in that order, and verifies both afterwards.

## What a visitor sees in each state

| State | The published page (`https://uhygyuf.github.io/rag-support-bot/`) |
|---|---|
| On | Loads, and the chat answers with the source file named, e.g. `… 7–14 business days. [faq.md]` |
| On, but the tab was open while the tunnel restarted | The first question retries against a freshly looked-up address and still answers; no reload needed |
| Off | Still loads — GitHub hosts it — but a question gets `Sorry, our assistant is offline right now.` |

The page itself never depends on this machine being switched on; only the answering does.

## What the switches deliberately do not do

They never read a credential and never touch the database. Switching the bot off cannot delete
anything. (`start-demo.bat` in the project root is different: it clears the QA tickets so the table
looks clean on camera. Use `start-demo.bat -KeepTickets` if you do not want that.)

## If something goes wrong

| Symptom | What to do |
|---|---|
| The status says the published page is `STALE` | Run `bot-on.bat`: it republishes the current address (the tunnel gets a new hostname whenever it restarts, and the page reads the address from the repository) |
| "the tunnel still does not answer" | Run `bot-on.bat` again; quick tunnels occasionally need a second attempt. If it fails twice, run `D:\Tools\n8n\start-public.bat`, read its window, then run the switch again |
| "n8n did not answer within 4 minutes" | Open the minimised `n8n public (Cloudflare tunnel)` window and read the error |
| You want the bot up but not reachable from the internet | Double-click `D:\Tools\n8n\start-n8n.bat` instead (local only, no tunnel) |

## How these scripts know where things are

Paths and task names are the defaults of this installation (`D:\Tools\n8n`, tasks
`n8n watchdog` / `n8n zombie cleanup`). The tunnel executable, its arguments and the log path are
read from `D:\Tools\n8n\watchdog-config.json`, so there is one place to change them.

Commands, if you prefer a terminal:

```powershell
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action on
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action off
powershell -ExecutionPolicy Bypass -File switches\switch-bot.ps1 -Action status
```
