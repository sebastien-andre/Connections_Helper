"""
Safari integration

Handles opening LinkedIn profiles in new Safari windows using AppleScript.
"""

import subprocess


def open_linkedin_tabs(urls):
    """
    Open a list of LinkedIn URLs in a new Safari window, each as a separate tab.

    Parameters:
    
    urls : list[str]
        The LinkedIn profile URLs to open.
    """
    if not urls:
        return

    esc = lambda s: s.replace('"', '\\"')

    script_lines = [
        'tell application "Safari"',
        'make new document',
        'delay 0.4',
        f'open location "{esc(urls[0])}"',
        'delay 0.5'
    ]
    for u in urls[1:]:
        script_lines.append(f'open location "{esc(u)}"')
        script_lines.append('delay 0.3')
    script_lines.append('activate')
    script_lines.append('end tell')

    subprocess.run(["osascript", "-"], input="\n".join(script_lines).encode("utf-8"))