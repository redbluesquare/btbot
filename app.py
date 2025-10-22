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

trades = trades.Trades()
def getTradeData():
    get_trades = trades.getPreviousTrades()

    # Normalize and clean
    df = pd.DataFrame([
        {
            "epic": t["instrumentName"],
            "trade_date": pd.to_datetime(t["dateUtc"]),
            "dealId": t["reference"],
            "price_open": float(t["openLevel"].replace("-", "0")),
            "price_close": float(t["closeLevel"].replace("-", "0")),
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
            df.groupby(["day", "epic"])
            .agg(
                total_trades=("dealId", "count"),
                net_pnl=("pnl", "sum"),
                avg_stake=("stake", "mean"),
                avg_open=("price_open", "mean"),
                avg_close=("price_close", "mean")
            )
            .reset_index()
        )
    else: 
        summary = df

    # summary = pd.DataFrame(...) from your groupby logic
    html_table = summary.to_html(
        index=False,
        border=1,
        justify="center",
        classes="trade-summary",
        float_format="%.2f"
    )
    return html_table

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
    html_body = getTradeData()
    try:
        send_email(
            to_addr    = 'usher_darryl@hotmail.com',
            subject    = "Daily Trade Summary",
            html_body  = html_body
        )
        print(f"✔ Sent to {'usher_darryl@hotmail.com'}")
    except Exception as e:
        print(f"✖ Failed for {'usher_darryl@hotmail.com'}: {e}")
    time.sleep(1)