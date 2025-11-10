# Connections Helper

**Connections Helper** is a macOS desktop app built with Python and PyQt6 to explore and organize exported LinkedIn connections.  
It makes it easy to import CSVs, filter people by company or role, and open their profiles directly in Safari while tracking which ones you’ve already viewed.  

I created this after noticing how annoying it was to browse LinkedIn exports.

---


You can:
- Import one or more LinkedIn connections CSVs (from different accounts)
- Automatically group people by company
- Filter and sort within large organizations
- Track which profiles you’ve already opened
- Maintain a personalized connection note and clipboard message for outreach
- Reset or rebuild your database at any time

---

## Features

- Import LinkedIn connection exports (handles extra headers and duplicate rows)
- Groups companies with more than _N_ employees together (threshold adjustable in toolbar)
- Fuzzy search for companies by name
- Toggle between dark and pastel light modes
- “Show Unvisited Only” view for focused outreach
- Double-click or select multiple people to open their LinkedIn profiles in new tabs
- Automatically marks opened profiles as visited (can be undone)
- Persistent connection note area (copied to clipboard before each open)
- Resizable font via Command + / Command –
- Reset Database option (with confirmation)

---




## Screenshot

![App Interface](interface.png)

---

## Packaging & Installation

Connections Helper can be run from source or packaged as a standalone macOS app.

### From source

```bash
pip install -r requirements.txt
python main.py
```

#### Package as macOS app

```bash
pyinstaller --onedir --windowed --icon code/connections.icns --name "ConnectionsHelper" code/main.py
```
This creates a self-contained .app bundle under dist/ConnectionsHelper.app.
You can copy or share it directly with no dependencies required.

For Intel or older macOS targets, build using:

```bash
arch -x86_64 python3 -m PyInstaller --onedir --windowed --icon code/connections.icns --name "ConnectionsHelper" code/main.py
```






### `Connections.csv` (sample)

Save this in your project root (next to `main.py`):

```csv
First Name,Last Name,URL,Email Address,Company,Position,Connected On
Sebastien,Lee,https://www.linkedin.com/in/sebastien-lee/,,Georgia Institute of Technology,Graduate Student,24 Oct 2025
Mickey,Mouse,https://www.linkedin.com/in/mickey-mouse,,Disney,Animator,20 Oct 2025
Bugs,Bunny,https://www.linkedin.com/in/bugs-bunny,,Warner Bros,Voice Actor,19 Oct 2025
SpongeBob,SquarePants,https://www.linkedin.com/in/spongebob-squarepants,,Nickelodeon,Marine Biologist,18 Oct 2025
Velma,Dinkley,https://www.linkedin.com/in/velma-dinkley,,Mystery Inc,Data Analyst,17 Oct 2025
Homer,Simpson,https://www.linkedin.com/in/homer-simpson,,Springfield Nuclear Power Plant,Safety Inspector,16 Oct 2025
```


