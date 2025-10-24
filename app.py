import models.trades as trades
import pandas as pd
import time
import os
import smtplib
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from jinja2               import Environment, FileSystemLoader, select_autoescape

load_dotenv()

# SMTP configuration
SMTP_HOST    = 'smtp.gmail.com'
SMTP_PORT    = 587
USERNAME     = os.getenv('EMAIL_ADDRESS')
APP_PASSWORD = os.getenv('EMAIL_APP_PASSWORD')

def getTradeData():
    trade = trades.Trades()
    account = trades.Account()
    get_trades = trade.getPreviousTrades()
    accounts = account.getAccountDetails()
    acc = pd.DataFrame([
        {
            "AccountId":t['accountId'],
            "AccountName":t['accountName'],
            "AccType":t['accountType'],
            "Balance":float(t['balance']),
        }
        for i, t in accounts.iterrows()
    ])
    html_tbl = acc.to_html(
        index=False,
        border=1,
        justify="center",
        float_format="%.2f"
    )
    # Normalize and clean
    df = pd.DataFrame([
        {
            "epic": t["instrumentName"],
            "trade_date": pd.to_datetime(t["dateUtc"]),
            "dealId": t["reference"],
            "stake": float(t["size"].replace("+", "").replace("-", "0")),
            "pnl": float(t["profitAndLoss"].replace("£", "")),
        }
        for i, t in get_trades.iterrows()
    ])

    if get_trades.empty == False:
        # Add day column
        df["day"] = df["trade_date"].dt.date

        # Group by day and epic
        summary = (
            df.groupby(["day", "epic", "stake"])
            .agg(
                total_trades=("dealId", "count"),
                net_pnl=("pnl", "sum"),
            )
            .reset_index()
        )
    else: 
        summary = df
        # Step 1: Get daily total PnL
        daily_pnl = summary.groupby("day")["net_pnl"].sum().sort_index(ascending=False)

        # Step 2: Compute rolling balance backwards from known final balance
        balance = daily_pnl[::-1].cumsum()[::-1] + acc['Balance'][0] - daily_pnl.sum()

        # Step 3: Map rolling balance back to summary
        summary["balance"] = summary["day"].map(balance)

    # summary = pd.DataFrame(...) from your groupby logic
    html_table = summary.to_html(
        index=False,
        border=1,
        justify="center",
        classes="trade-summary",
        float_format="%.2f"
    )
    return html_tbl, html_table

def send_email(to_addr, subject, html_body):
    # 1. Root container: related = HTML + images
    msg_root = MIMEMultipart('related')
    msg_root['From']    = USERNAME
    msg_root['To']      = to_addr
    msg_root['Subject'] = subject

    # 2. Alternative container: plain-text fallback + HTML
    msg_alt = MIMEMultipart('alternative')
    msg_root.attach(msg_alt)

    # 3. Plain-text fallback
    text = "Please view this email in an HTML-capable client."
    msg_alt.attach(MIMEText(text, 'plain'))

    # 4. HTML body
    msg_alt.attach(MIMEText(html_body, 'html'))

    # 6. Send via SMTP
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(USERNAME, APP_PASSWORD)
        server.send_message(msg_root)

def main():
    html_header, html_body = getTradeData()
    try:
        send_email(
            to_addr    = 'usher_darryl@hotmail.com',
            subject    = "Daily Trade Summary",
            html_body  = html_header+'<br><br>'+html_body
        )
        print(f"✔ Sent to {'usher_darryl@hotmail.com'}")
    except Exception as e:
        print(f"✖ Failed for {'usher_darryl@hotmail.com'}: {e}")
    time.sleep(1)

main()