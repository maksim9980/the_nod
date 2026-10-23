# Export habits to CSV

Date: 2026-10-11. Status: approved 2026-10-12.

## 1. Pain
"I track my habits in Tidepool, but I cannot get the history out into a spreadsheet."

## 2. Verdict
Do. The export is small, and the owner asks for it every week.

## 3. Cost
Cards: 1. Run hours: 3. Paid services: none.

## 4. Decisions
1. The export is one CSV file per user. Why: one file opens in any spreadsheet.
2. Question: Which period goes into the file? Proposed: all history. Why: the owner wants the full record. Options: the last 30 days | a period the user picks.
3. Question: Which column separator? Proposed: comma. Why: the CSV default. Options: semicolon.

## 5. For the user
- An "Export to CSV" button on the habit grid.

## 6. For the system
- A new endpoint GET /export.csv that streams the rows.

## 7. Risks
- A long history makes a big file. If it fires: the download is slow.

## 8. Maintain later
- Nothing.

## 9. How we check
Account: a test user with 40 days of habits. Steps:
1. Open the habit grid.
2. Click "Export to CSV".
See: a file with one row per habit and day, 40 days.

## 10. Steps
1. Add the CSV writer for the habit history
2. Add the export endpoint
3. Add the export button to the habit grid

Outside the run: owner — open the file in a spreadsheet app.
