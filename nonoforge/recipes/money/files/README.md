# {{NAME}}

Write down what you spend, and it adds itself up by month and by group.

Made with [nonoForge](https://github.com/Agarwalrishu13/nonoforge). No account,
no bank connection, no internet — one CSV file and a small program.

## Start it

```bash
python start.py            # opens http://127.0.0.1:8767
```

Windows: `run.bat`. macOS / Linux: `./run.sh`.

## Your data

Everything lives in `data/expenses.csv` with four columns: `when`, `what`,
`amount`, `category`. It is an ordinary CSV — open it in Excel, Numbers or
Google Sheets, fix a typo by hand, or add rows directly. The app re-reads the
file every time the page loads.

Amounts: `12.50`, `12,50` and `£12.50` all work. A negative number like `-50`
means money coming in, and it is subtracted from the totals.

## Changing the groups

Edit `categories.txt` — one group per line, then refresh the page. Nothing else
needs changing.

## Changing the currency

The symbol is set once near the top of `start.py`:

```python
CURRENCY = "£"
```

Change it, save, restart the app.

## Exporting

The **Spreadsheet** button at the top right downloads a CSV called
`{{PROJECT}} YYYY-MM-DD.csv`, ready for Excel (it includes a byte-order mark so
accents survive).
