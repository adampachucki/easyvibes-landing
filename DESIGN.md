# easyvibes

Design notes for the CLI behind easyvibes.dev.

This is the working spec. It captures what we're building, why, how it
works, what the user experience looks like, and the core decisions we
made along the way. Treat it as a living document.

---

## 1. Vision

**A `vibe` command that lets a developer run coding agents in the cloud
and access them, mid-session, from any device.**

Concretely: one CLI installs and configures a small Linux VM the user
already has, so that Claude Code, Codex, and Gemini run inside persistent
terminal sessions on that VM. The user attaches to those sessions from
their Mac or iPhone. The same session, the same scrollback, the same
agent state, regardless of what's connected.

The product is the configurator and the ergonomics around it. The
infrastructure (zmx, Eternal Terminal, mosh, tmux, the agent CLIs) is
all open source software we orchestrate.

---

## 2. The problem

Modern coding agents are designed to run unattended for long stretches.
They plan, code, execute, and iterate over minutes or hours. The current
default is to run them on a laptop, where:

- Closing the lid stops the run.
- Network changes (cafe wifi, switching to a hotspot) drop the
  connection.
- The user can't check progress or give the agent the next instruction
  from a phone or tablet.
- Workarounds like `/remote-control` in Claude don't actually move the
  agent off the laptop. They just let one process talk to another on
  the same machine.

Some users solve this by running a Mac mini at home as a server. That's
expensive, brittle, and runs against the grain of how everything else in
modern software development already works. The repos live on GitHub. The
agents are fundamentally cloud-based services. The compilers, CI,
storage, and editors all moved to the cloud over the last decade. Only
the agent process itself is still tethered to a personal device.

A VM in the cloud is the right home: doesn't sleep, no desktop
dependency, repo lives nearby, reasonable security boundary, billed by
the user directly to their cloud provider. The hard part is making it
*pleasant* to use. Plain SSH is too fragile. tmux on its own breaks
native scrollback. Setting up the right combination of tools across two
devices and two transports is enough work that almost nobody bothers.

That setup work is the gap easyvibes fills.

---

## 3. The solution

A single command on the user's Mac:

```
npx easyvibes init
```

After roughly five minutes of mostly automated work (and possibly
provisioning a VM if the user doesn't have one), the user can do this:

```
$ vibe
```

…and land directly in their persistent agent session on the VM. Open
the Moshi app on their iPhone, and the same session is one tap away.

The CLI hides everything that makes this work: zmx for persistence,
Eternal Terminal for the Mac transport, mosh + tmux for the phone
transport, the agent CLIs themselves, the systemd units, the firewall
rules, the shell functions on the Mac. The user never has to know any
of those names.

---

## 4. How it works

### 4.1 Architecture

There are three actors: the **VM**, the **Mac**, and the **phone**.

```
   Mac (terminal)  ─── Eternal Terminal ──▶│
                                            │
                                            ▼
                                  ┌──── VM (Linux) ────┐
                                  │                    │
                                  │  zmx session       │
                                  │   ├─ shell         │
                                  │   └─ claude/codex/ │
                                  │      gemini agent  │
                                  │                    │
                                  └────────────────────┘
                                            ▲
                                            │
   iPhone (Moshi) ─── mosh ── tmux wrap ───▶│
```

- **zmx** holds the actual persistent session. It keeps a raw PTY
  alive on the VM and avoids the alternate screen, which is what
  makes native scrollback work cleanly on the Mac.
- **Eternal Terminal** is the Mac's transport. SSH-shaped, but
  silently reconnects on network changes.
- **mosh** is the phone's transport. UDP-based, roams across networks.
- **Moshi** is the iOS mosh client app. It needs the alternate screen
  for scrollback, so on the phone path the zmx session is wrapped in
  a thin tmux layer purely as an adapter. tmux is **not** the
  persistence layer.
- **The agent CLIs** (Claude Code, Codex, Gemini) are off-the-shelf
  npm packages, just running inside the zmx session.

Both transports attach to the same zmx session. When the Mac detaches,
the phone can attach. When both are attached, they see the same
content. Neither client owns the state. The state lives on the VM, in
zmx.

### 4.2 What `init` actually does

The CLI runs from the Mac. Over SSH, on the VM:

1. Detects the OS (Ubuntu/Debian via `apt`, Fedora/RHEL via `dnf`).
2. Installs build deps and runtime packages: `mosh`, `tmux`,
   `eternalterminal`, `git`, `curl`, `build-essential`, Zig.
3. Builds zmx from source (or pulls a prebuilt binary when available).
4. Installs the agent CLIs as global npm packages.
5. Writes a systemd unit so the Eternal Terminal server starts on boot
   and listens on port 2022.
6. Opens the firewall: tcp/2022 (ET), udp/60000-61000 (mosh).

On the Mac:

1. Adds a `Host easyvibes-vm` entry to `~/.ssh/config`.
2. Writes `~/.zsh-easyvibes` with the `vibe` command and helpers.
3. Appends a single source line to `~/.zshrc` (with a backup).
4. Optionally opens the App Store page for Moshi.

A small smoke test follows: spawn a session, attach, detach, kill.
If anything fails, the install fails loudly with the specific step.

### 4.3 What `vibe` does at runtime

`vibe` is the only command the user ever runs day-to-day. It does
roughly this:

1. Ensures the SSH connection to the VM is alive (Eternal Terminal
   handles reconnection, but the first invocation establishes it).
2. Lists existing zmx sessions on the VM.
3. Shows a picker. The user chooses an existing session or `new`.
4. Attaches to (or creates) the chosen session.

That's it. No magic about repos, no automatic agent launching, no
implicit `cd`. Inside the session, the user navigates and runs agents
the same way they would on any other shell.

The session shell is persistent. `cwd` persists. Whatever agent is
running keeps running. Detaching is just closing the terminal or
disconnecting. Reattaching restores the exact state.

---

## 5. User experience

### 5.1 First install

User runs:

```
$ npx easyvibes init
```

The wizard walks through three questions:

1. **Do you have a VM with SSH access?**
   - Yes: ask for `user@ip`.
   - No: offer Hetzner / DigitalOcean / GCP / "I'll come back later",
     with a pre-filled cloud-init config and step-by-step.
2. **Which agents to install?** (Default: all three.)
3. **Where should sessions and repos live on the VM?** (Default:
   `~/src`.)

Then the install runs. The user sees live progress for each step
(SSH, OS detect, package install, zmx build, systemd setup, Mac
config, smoke test). Total time on a fresh VM: ~3 minutes. Existing
VM with deps already installed: under 60 seconds.

When done, the wizard prints:

```
done.

  start a session:        vibe
  on iPhone:              install Moshi, point it at easyvibes-vm
  diagnose anything:      vibe doctor
```

### 5.2 Day-to-day on the Mac

A new terminal:

```
$ vibe
sessions on easyvibes-vm:
  1) myapp            45m   ~/src/myapp        (claude, idle)
  2) auth-rewrite     3h    ~/src/myapp/auth   (claude, working)
  3) other-project    2d    ~/src/other-app    (codex, idle)
  > new
choose: 1
[reattaching]
~/src/myapp ❯ _
```

The user is back in their Claude session. The agent is exactly where
they left it.

If they pick `new`, they get a fresh session with a friendly pet name
(`twinkling-marinating-torvalds`), in the home directory of the VM.
From there they `cd ~/src/...`, run `claude`, work normally.

### 5.3 Phone

After install, on the iPhone:

1. Install **Moshi** from the App Store (one tap from the install
   summary email/output).
2. Add a server: host = the VM IP, user = the VM user, key = same
   SSH key paired during init.
3. Open the server. Moshi shows the running zmx sessions.
4. Tap a session. The user is in. Same scrollback, same prompt.

Swiping between sessions works like browser tabs in Moshi.

### 5.4 The full surface

| Command | What it does |
|---|---|
| `vibe` | Picker. Pick existing or `new`. |
| `vibe new [name]` | New session. Name defaults to a pet name. |
| `vibe ls` | Same as `vibe`. |
| `vibe kill [name]` | Kill a session. |
| `vibe doctor` | Diagnose connection, install, version mismatches. |
| `vibe upgrade` | Re-run the install at latest versions. Idempotent. |
| `vibe uninstall` | Remove Mac-side config (with backup). Optionally clean the VM. |

That's the whole CLI. Five core verbs.

---

## 6. Core decisions and why

### 6.1 Don't provision VMs

We help the user *get* a VM (docs, optional one-click for Hetzner/DO),
but we don't run the cloud APIs ourselves.

**Why:** Cloud provisioning is a tar pit. Each provider has a different
SDK, auth flow, IAM model, network model, billing model. Going down
that path means most of the engineering effort is spent on cloud
plumbing, not on the actual product. The product is the configurator
and the ergonomics. Anyone who can spin up a VM can use easyvibes;
anyone who can't, follows a 2-minute Hetzner walkthrough.

### 6.2 Run the installer from the Mac

`npx easyvibes init` runs on the user's Mac and configures both ends
over SSH. We considered a VM-side install script (curl-pipe-bash), but
chose Mac-first.

**Why:** The Mac is where the user already is. They open one terminal,
type one command, done. The CLI also needs to drop shell functions and
ssh_config entries on the Mac itself, which is awkward to do from a
script running on the VM. Failures are also easier to surface and
recover from when the orchestrator is local.

### 6.3 Sessions are just persistent shells

The CLI manages sessions. It does not manage repos, agents, or working
directories.

**Why:** Earlier drafts of this design tried to make `vibe foo` mean
"open Claude in `~/src/foo`". That conflated three things (session,
repo, agent) into a single concept. Users got confused. The clean
abstraction is that a session is a persistent shell, period. Inside,
the user runs Claude or Codex or bash like normal. They `cd` like
normal. Their session list ends up reflecting their work-in-progress
contexts naturally, without any magic from the CLI.

### 6.4 zmx, not tmux, on the Mac path

zmx provides persistence on the Mac. tmux only appears on the phone
path, as a thin adapter for Moshi.

**Why:** tmux uses the alternate screen by default, which breaks the
terminal's native scrollback. The user has to enter copy mode to scroll
back through agent output. zmx avoids the alternate screen entirely,
keeping the raw PTY stream intact, so the host terminal's normal scroll
just works. Combined with Claude Code's `--no-flicker` flag (which
reduces redraw spam in the stream), the Mac scrollback is clean.

We tried a tmux-only path early and the scrollback experience was bad
enough that we kept iterating until we found zmx.

### 6.5 Eternal Terminal, not plain SSH, on the Mac

ET is a transport that reconnects silently when the network changes.
SSH is not.

**Why:** Plain SSH drops on every network blip. The user has to
reconnect, which is a constant interruption when working from a
laptop on shifting wifi. ET papers over this. The user never sees a
disconnect. (mosh handles the same problem on the phone path, in a
way that's better suited to mobile networks.)

### 6.6 Moshi for iOS

Moshi is a third-party iOS mosh client. It renders the terminal,
provides a usable touch keyboard, and lists running tmux sessions
from a sidebar.

**Why:** mosh from a phone needs a real client; the protocol won't
work in a browser. Moshi is the best option that exists today. It
also handles tmux session listing/switching well, which is what
makes the phone experience feel like browser tabs.

Moshi specifically requires the alternate screen for scrollback,
which is why the phone path has tmux wrapped around zmx. tmux is
not used as a persistence layer; zmx is. tmux is purely an adapter
for Moshi's expectations.

### 6.7 The user-facing command is `vibe`

Not `easyvibes`, not `evx`, not `x` (which is what the dev's personal
setup used). Just `vibe`.

**Why:** The product is `easyvibes`. The action is `vibe`. The brand
reads consistently top to bottom: install via `npx easyvibes`, use
via `vibe`. It's also a verb that matches how the user thinks about
what they're doing ("I'll vibe on this for an hour").

### 6.8 Pet names by default

A new session with no name gets one like `twinkling-marinating-torvalds`.

**Why:** Naming sessions feels like work, especially for short tasks.
Pet names mean the user can always run `vibe new` and get a session
without thinking. The name list ships with the CLI; it's the same
pattern Heroku, Docker, and Linear use. Users who want explicit names
pass them: `vibe new auth-rewrite`.

### 6.9 No web dashboard. No team features. No multi-VM.

For v1.

**Why:** The point is a CLI that does one thing well. Anything beyond
that creates surface area to maintain and questions to answer (auth?
billing? multi-tenant?). v1 is a single user, a single VM, a CLI.

---

## 7. Out of scope (for v1)

- Provisioning VMs end-to-end (we help, we don't run the cloud APIs).
- Repo cloning and onboarding (`vibe clone <git-url>` is a v2 nice-to-have).
- Setting up GitHub auth on the VM (out of scope; document `gh auth login`).
- A web UI of any kind.
- Team features, shared VMs, multi-user auth.
- Multiple VMs per user.
- Background `cron`-like agents that run unattended without a session.
- Windows or Linux as the user's primary device. We support Mac +
  iPhone. Linux/Android can come later.

---

## 8. Open questions

These are real tensions we haven't resolved yet:

1. **VM auth for git.** The first time a user runs `git clone` inside a
   session, it'll fail without auth. Best path: ship `gh` on the VM,
   prompt the user to run `gh auth login` once during init. Adds one
   step but solves a class of problems.
2. **Agent updates.** Claude Code, Codex, and Gemini ship updates often.
   Should `vibe upgrade` always pull latest, or pin? Likely: pin to
   minor versions, prompt to upgrade.
3. **Pricing.** The CLI is free and open source. The user pays their
   cloud provider directly. We may, at some point, offer a managed
   "we provision the VM for you" tier on top, but not in v1.
4. **Distribution.** Is this `npx easyvibes` (npm) or
   `brew install easyvibes` (Homebrew) or both? Probably both, with
   npm primary because it works on day one with no extra setup.
5. **What happens when the VM goes away.** If the user wipes the VM,
   their sessions are gone. Is that acceptable, or do we want to
   sync session metadata somewhere? For v1: acceptable. The user owns
   the VM. We don't.

---

## 9. Why this should exist at all

We've moved compilers, CI, storage, and editors to the cloud over the
last decade. Coding agents are a new kind of long-running process, and
they inherited the localhost assumption from the era they were born in.
That assumption is wrong, and small teams and individuals are paying
the cost for it every day in interrupted runs and laptops they can't
close.

The pattern is going to be the default eventually. Anthropic, OpenAI,
or Google will probably ship some version of it themselves. Until they
do, easyvibes is the bridge: a small, sharp CLI that takes the working
setup we've already proved and packages it so anyone can have it in
five minutes.

The experience that surprises every person who sees it (start
something on a laptop, close the lid, pick it up on a phone, agent
still running, mid-thought) should not be surprising. It should be
the floor.
