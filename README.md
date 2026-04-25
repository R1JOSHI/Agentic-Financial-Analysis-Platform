# Financial Agentic AI — SEC Visual Investor Dashboard

A local prototype that searches SEC-listed companies, converts ticker to CIK, fetches SEC EDGAR company facts/submissions, scores financial strength, visualizes risk, and exports an investor PowerPoint-compatible memo.

## Run
```bat
cd C:\Users\Riddh\Downloads\Financial_Agentic_AI_SEC_Visual_Dashboard\financial_sec_visual_agent
python app.py
```
Open `http://localhost:8000/index.html`.

## Features
- Real SEC ticker/company search
- CIK conversion
- Financial factor scoring
- Visual dashboard
- Risk assessment bars
- Financial strength pie chart
- Recent SEC filings
- Export investor PPT, JSON, CSV, and print/PDF

## SEC note
No API token is required. For production, update the User-Agent in `app.py` with your name and email.
