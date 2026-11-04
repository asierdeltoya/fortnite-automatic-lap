pk-auto
=======
pk-auto.exe works on its own - no other files are needed.

1. Run pk-auto.exe, open the game lobby and press "Start".
   F8 starts or stops it at any time.
2. "Interface language" switches the window between Japanese, English and
   Spanish. On first launch it follows the Windows display language.
3. Choose the language your Fortnite is in under "Game language". Spanish,
   Portuguese and Russian are beta: they look at the button shape only, so
   they need no translation.
4. With several monitors, pick the one showing Fortnite under "Screen".
5. With "Pause when Fortnite is not in the foreground" on (the default), no
   clicks or key presses are sent while another window is active.
6. If buttons are not detected (different resolution or UI), use "Crop image"
   to capture your own, or put PNGs into an "assets" folder next to
   pk-auto.exe. Files there override the built-in ones:
     play_btn.png          - lobby "Play" button
     continue_btn.png      - "Continue" button after elimination
     skip_btn.png          - "Skip" button on the XP screen
     return_lobby_btn.png  - "Return to Lobby" button on the summary
     claim_btn.png         - reward screen "Claim all" button
     popup_btn.png         - optional: any other pop-up button to dismiss
   English UI images use the suffix _en (play_btn_en.png, ...).
7. Mode A = normal loop (Continue / Skip / Return to Lobby).
   Mode B = wait on the pre-match island (default 90 s), then Esc, the menu,
   "Return to Lobby", and queue again.

Settings are saved automatically to pk-auto-config.json next to the exe.

Warning: automation may violate the game's terms of service and anti-cheat
rules. Use at your own risk.
