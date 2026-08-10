---
name: download
description: Print a ready-to-paste scp command that copies a file (or folder) from this machine to the user's laptop Downloads folder. Use when the user invokes /download, or asks to "download that", "send me that file", "get that onto my laptop", "scp me that".
---

# download

Give the user **one copy-pasteable `scp` command** they run **from their laptop** to pull a file off this machine into their Downloads folder. Print the command and stop — never run it, never try to push the file yourself.

## Steps

1. **Resolve the target.** Use the path in the argument if given (`/download report.md`). With no argument, use the file you most recently created or wrote in this session. Ambiguous or nothing obvious → ask which file, don't guess.
2. **Make it absolute.** `realpath <file>` — a relative path is useless on the other end. Confirm it exists; if it doesn't, say so instead of emitting a command that will fail.
3. **Get the remote.** `whoami` and `hostname -f`. If `hostname -f` returns something unqualified or `localhost`, fall back to `hostname` and flag that the user may need their own SSH alias.
4. **Print the command**, in a shell block, for the destination `C:\Users\SpencerWatkinson\Downloads\`:

   ```
   scp <user>@<fqdn>:<absolute-path> "C:\Users\SpencerWatkinson\Downloads\"
   ```

   Add `-r` for a directory.

## Rules

- **From their laptop, not here.** Say so in one short line above the command — it's the mistake this skill exists to prevent.
- **Keep the trailing backslash** on the Windows destination and keep it quoted, so a path with spaces survives and scp treats it as a folder.
- **Offer the alias form as a fallback** in one line if the FQDN might not resolve from outside: `scp <shorthost>:<path> "C:\Users\SpencerWatkinson\Downloads\"`.
- **No preamble, no epilogue.** One line of context, the command, and at most one fallback line. That's the whole output.
