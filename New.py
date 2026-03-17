# FULL STREAMLIT APP – SQLITE BACKED CHIT FUND TRACKER
# SQLite + Dashboard + Roles + 3-Color Ledger + Responsive Payment UX

import streamlit as st
import sqlite3
from datetime import date, datetime, timedelta

import pdfplumber
import re
from datetime import datetime

from contextlib import contextmanager
import pandas as pd
import plotly.express as px


import psycopg2
import streamlit as st
from contextlib import contextmanager
import psycopg2.extras


# ===================== DB LAYER =====================

@contextmanager
def get_conn():
    conn = psycopg2.connect(st.secrets["DATABASE_URL"])
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            name TEXT,
            phone TEXT,
            address TEXT,
            start_date DATE,
            daily_amount NUMERIC,
            principal NUMERIC,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            phonepe_contact_name TEXT,
            witness_name TEXT,
            witness_address TEXT,
            witness_phone TEXT
        );
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(id),
            txn_date DATE,
            expected_amount NUMERIC,
            paid_amount NUMERIC DEFAULT 0,
            paid_on DATE,
            UNIQUE (customer_id, txn_date)
        );
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(id),
            payment_date DATE,
            amount NUMERIC,
            txn_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)


# ===================== BUSINESS LOGIC =====================
class ChitFundDB:

    def __init__(self):
        init_db()

    # ✅ ADD CUSTOMER
    def add_customer(self, name, phonepe_name, address, phone, start_date, daily, principal,
                     wname, waddr, wphone):

        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("""
                INSERT INTO customers
                (name, phonepe_contact_name, address, phone, start_date,
                 daily_amount, principal,
                 witness_name, witness_address, witness_phone)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (name, phonepe_name, address, phone, start_date, daily,
                  principal, wname, waddr, wphone))

            cid = cur.fetchone()["id"]

        self._init_ledger(cid)
        return cid

    # ✅ INIT LEDGER
    def _init_ledger(self, cid):

        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("SELECT * FROM customers WHERE id=%s", (cid,))
            cust = cur.fetchone()

            principal = float(cust["principal"])
            daily_amount = float(cust["daily_amount"])
            start_date = cust["start_date"]

            bal = principal
            d = start_date

            while bal > 0:
                if d.weekday() != 6:
                    bal -= daily_amount

                    cur.execute("""
                        INSERT INTO transactions
                        (customer_id, txn_date, expected_amount)
                        VALUES (%s,%s,%s)
                        ON CONFLICT (customer_id, txn_date) DO NOTHING
                    """, (cid, d, daily_amount))

                d += timedelta(days=1)

    # ✅ COLLECT PAYMENT
    def collect_payment(self, cid, amount, pay_date, txn_id=None):
        with get_conn() as conn:
            cur = conn.cursor()
    
            # 🚫 Duplicate prevention
            if txn_id:
                cur.execute("SELECT 1 FROM payments WHERE txn_id=%s", (txn_id,))
                if cur.fetchone():
                    return
    
            # ✅ Insert payment
            cur.execute("""
                INSERT INTO payments (customer_id, payment_date, amount, txn_id)
                VALUES (%s,%s,%s,%s)
            """, (cid, pay_date, amount, txn_id))
    
            remaining = amount
    
            # 🔥 Get pending transactions
            cur.execute("""
                SELECT id, txn_date, expected_amount, paid_amount
                FROM transactions
                WHERE customer_id=%s
                ORDER BY txn_date
            """, (cid,))
    
            txns = cur.fetchall()
    
            # 🔥 Allocation logic
            for t in txns:
                txn_id_db, txn_date, expected, paid = t
                pending = expected - paid
    
                if remaining <= 0:
                    break
    
                if pending <= 0:
                    continue
    
                allocate = min(remaining, pending)
    
                # ✅ FULL PAYMENT
                if allocate == pending:
                    cur.execute("""
                        UPDATE transactions
                        SET paid_amount = expected_amount,
                            paid_on = %s
                        WHERE id=%s
                    """, (pay_date, txn_id_db))
    
                # 🟡 PARTIAL PAYMENT
                else:
                    cur.execute("""
                        UPDATE transactions
                        SET paid_amount = paid_amount + %s
                        WHERE id=%s
                    """, (allocate, txn_id_db))
    
                remaining -= allocate

    # ✅ CUSTOMERS LIST
    def customers(self):

        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM customers ORDER BY id")
            return cur.fetchall()

    # ✅ LEDGER
    def ledger(self, cid):
        with get_conn() as conn:
            cur = conn.cursor()
    
            cur.execute("""
                SELECT 
                    txn_date,
                    expected_amount,
                    paid_amount,
                    (expected_amount - paid_amount) AS pending,
                    paid_on
                FROM transactions
                WHERE customer_id=%s
                ORDER BY txn_date
            """, (cid,))
    
            return cur.fetchall()

    # ✅ UPDATE PHOTO
    def update_customer_photo(self, cid, path):

        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "UPDATE customers SET customer_photo=%s WHERE id=%s",
                (path, cid)
            )

    # ✅ UPDATE CUSTOMER
    def update_customer(self, cid, name, phonepe, address, phone):

        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                UPDATE customers
                SET name=%s, phonepe_contact_name=%s,
                    address=%s, phone=%s
                WHERE id=%s
            """, (name, phonepe, address, phone, cid))


    def dashboard_summary(self):

        today = date.today()

        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("SELECT COUNT(*) AS total FROM customers")
            total_customers = cur.fetchone()["total"]

            cur.execute("SELECT COALESCE(SUM(principal),0) AS total FROM customers")
            total_principal = cur.fetchone()["total"]

            cur.execute("SELECT COALESCE(SUM(amount),0) AS total FROM payments")
            total_collected = cur.fetchone()["total"]

            money_with_customers = total_principal - total_collected

            cur.execute("""
                SELECT COUNT(DISTINCT customer_id) AS total
                FROM transactions
                WHERE txn_date < %s
                  AND paid_amount < expected_amount
            """, (today,))
            overdue_customers = cur.fetchone()["total"]

            cur.execute("""
                SELECT COALESCE(SUM(expected_amount - paid_amount),0) AS total
                FROM transactions
                WHERE txn_date <= %s
                  AND paid_amount < expected_amount
            """, (today,))
            overdue_amount = cur.fetchone()["total"]

            cur.execute("""
                SELECT COALESCE(SUM(expected_amount - paid_amount),0) AS total
                FROM transactions
                WHERE txn_date = %s
                  AND paid_amount < expected_amount
            """, (today,))
            todays_target = cur.fetchone()["total"]

            cur.execute("""
                SELECT COALESCE(SUM(amount),0) AS total
                FROM payments
                WHERE payment_date = %s
            """, (today,))
            todays_collected = cur.fetchone()["total"]

            cur.execute("""
                SELECT COUNT(*) AS total
                FROM customers c
                WHERE NOT EXISTS (
                    SELECT 1 FROM transactions t
                    WHERE t.customer_id = c.id
                      AND t.paid_amount < t.expected_amount
                )
            """)
            closed_customers = cur.fetchone()["total"]

            cur.execute("""
                SELECT COALESCE(SUM(expected_amount),0) AS total
                FROM transactions
                WHERE txn_date = %s
                  AND paid_amount >= expected_amount
                  AND customer_id NOT IN (
                      SELECT customer_id
                      FROM payments
                      WHERE payment_date = %s
                  )
            """, (today, today))
            advance_used_today = cur.fetchone()["total"]

        active_customers = total_customers - closed_customers

        efficiency = (
            round((total_collected / total_principal) * 100, 2)
            if total_principal else 0
        )

        return {
            "total_customers": total_customers,
            "total_principal": total_principal,
            "total_collected": total_collected,
            "money_with_customers": money_with_customers,
            "overdue_customers": overdue_customers,
            "overdue_amount": overdue_amount,
            "todays_target": todays_target,
            "todays_collected": todays_collected,
            "advance_used_today": advance_used_today,
            "closed_customers": closed_customers,
            "active_customers": active_customers,
            "efficiency": efficiency
        }


    

    def customer_ledger_summary(self, cid):

        today = date.today()
    
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Principal
            cur.execute(
                "SELECT principal FROM customers WHERE id=%s",
                (cid,)
            )
            principal = cur.fetchone()["principal"]

            # Total Paid
            cur.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE customer_id=%s",
                (cid,)
            )
            total_paid = cur.fetchone()["total"]

            # Pending till today
            cur.execute("""
                SELECT COALESCE(SUM(expected_amount - paid_amount),0) AS pending
                FROM transactions
                WHERE customer_id=%s
                  AND txn_date <= %s
                  AND paid_amount < expected_amount
            """, (cid, today))
            pending_till_today = cur.fetchone()["pending"]

            # Total days
            cur.execute(
                "SELECT COUNT(*) AS total_days FROM transactions WHERE customer_id=%s",
                (cid,)
            )
            total_days = cur.fetchone()["total_days"]

            # Days paid
            cur.execute("""
                SELECT COUNT(*) AS days_paid
                FROM transactions
                WHERE customer_id=%s
                  AND paid_amount >= expected_amount
            """, (cid,))
            days_paid = cur.fetchone()["days_paid"]

        extra_paid = max(0, total_paid - (principal - pending_till_today))

        return {
            "principal": principal,
            "total_paid": total_paid,
            "pending_till_today": pending_till_today,
            "extra_paid": extra_paid,
            "days_paid": days_paid,
            "total_days": total_days
        }
        
    



# =====================================================
# 🔐 SECURE LOGIN SYSTEM
# =====================================================

def login_page():

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if st.session_state.logged_in:
        return

    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        st.title("🔐 Secure Access")

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login", width='stretch'):

            if (
                username == st.secrets["APP_USERNAME"]
                and password == st.secrets["APP_PASSWORD"]
            ):
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Invalid credentials")

    st.stop()

# Run login check BEFORE loading app
login_page()

# =====================================================
# ✅ APP STARTS BELOW
# =====================================================

st.title("💰 Chit Fund Management Dashboard")


# ===================== DASHBOARD =====================
def dashboard(db):
    st.subheader("📊 Business Dashboard")

    d = db.dashboard_summary()

    # --- ROW 1: Business Snapshot ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👥 Total Customers", d["total_customers"])
    c2.metric("💼 Principal Given", f"₹{d['total_principal']:,.2f}")
    c3.metric("💰 Total Collected", f"₹{d['total_collected']:,.2f}")
    c4.metric("📉 Money With Customers", f"₹{d['money_with_customers']:,.2f}")

    st.divider()

    # --- ROW 2: Risk & Health ---
    c5, c6, c7, c8, c9 = st.columns(5)
    c5.metric("🚨 Overdue Customers", d["overdue_customers"])
    c6.metric("⏳ Overdue Amount", f"₹{d['overdue_amount']:,.2f}")
    c7.metric("📅 Today’s Target", f"₹{d['todays_target']:,.2f}")
    c8.metric("✅ Today’s Collection", f"₹{d['todays_collected']:,.2f}")
    c9.metric("🟣 Advance Used Today",f"₹{d['advance_used_today']:,.2f}",help="Amount of today's installment settled using past advance payments")


    st.divider()

    # --- ROW 3: Performance ---
    c9, c10, c11 = st.columns(3)
    c9.metric("📈 Collection Efficiency", f"{d['efficiency']}%")
    c10.metric("🟢 Closed Customers", d["closed_customers"])
    c11.metric("🟡 Active Customers", d["active_customers"])


# ===================== DAY-WISE ANALYSIS =====================
def day_wise_analysis(db):

    st.subheader("📅 Day-wise Payment Analysis")

    selected_date = st.date_input("Select Date", date.today())

    with get_conn() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Paid amount
        c.execute("""
            SELECT COALESCE(SUM(amount),0) AS total
            FROM payments
            WHERE payment_date=%s
        """, (selected_date,))
        paid_total = c.fetchone()["total"]

        # Total expected
        c.execute("""
            SELECT COALESCE(SUM(expected_amount),0) AS total
            FROM transactions
            WHERE txn_date=%s
        """, (selected_date,))
        total_expected = c.fetchone()["total"]

        # Unpaid total
        c.execute("""
            SELECT COALESCE(SUM(expected_amount - paid_amount),0) AS total
            FROM transactions
            WHERE txn_date=%s
              AND paid_amount < expected_amount
        """, (selected_date,))
        unpaid_total = c.fetchone()["total"]

        # Paid customers
        c.execute("""
            SELECT cust.id, cust.name, cust.phone,
                   SUM(p.amount) AS paid_amount
            FROM customers cust
            JOIN payments p ON cust.id = p.customer_id
            WHERE p.payment_date=%s
            GROUP BY cust.id, cust.name, cust.phone
            ORDER BY cust.name
        """, (selected_date,))
        paid_rows = c.fetchall()

        # Unpaid customers
        c.execute("""
            SELECT cust.id, cust.name, cust.phone,
                   SUM(t.expected_amount - t.paid_amount) AS due_amount
            FROM customers cust
            JOIN transactions t ON cust.id = t.customer_id
            WHERE t.txn_date=%s
              AND t.paid_amount < t.expected_amount
            GROUP BY cust.id, cust.name, cust.phone
            ORDER BY cust.name
        """, (selected_date,))
        unpaid_rows = c.fetchall()

    # ---- Paid Table ----
    st.markdown("### ✅ Paid Customers")

    if paid_rows:
        df_paid = pd.DataFrame(paid_rows)
        df_paid.index = df_paid.index + 1
        st.dataframe(df_paid, width='stretch')
    else:
        st.info("No payments collected on this date.")

    # ---- Unpaid Table ----
    st.markdown("### 🔴 Unpaid / Pending Customers")

    if unpaid_rows:
        df_unpaid = pd.DataFrame(unpaid_rows)
        df_unpaid.index = df_unpaid.index + 1
        st.dataframe(df_unpaid, width='stretch')
    else:
        st.success("No pending dues for this date.")

    # ---- Pie Chart ----
    st.markdown("### 📊 Payment Status Pie Chart")

    df_chart = pd.DataFrame({
        "Status": ["Paid", "Pending"],
        "Amount": [paid_total, unpaid_total]
    })

    fig = px.pie(
        df_chart,
        names="Status",
        values="Amount",
        color="Status",
        color_discrete_map={"Paid": "#4CAF50", "Pending": "#f44336"},
        hole=0.3
    )

    fig.update_traces(textinfo='percent+label')
    st.plotly_chart(fig, width='stretch')



# ===================== LEDGER COLOR LOGIC =====================
today = pd.Timestamp(date.today())


def highlight_ledger_row(r):
    txn_date = pd.to_datetime(r['txn_date'])
    if r['pending'] == 0:
        color = '#d4edda'      # Green
    elif txn_date < today:
        color = '#f8d7da'      # Red
    else:
        color = '#fff3cd'      # Yellow
    return [f'background-color:{color}'] * len(r)


def add_customer_ui(db):
    st.subheader("➕ Add Customer")
    with st.form("add_customer_form"):
        name = st.text_input("Customer Name *")
        addr = st.text_area("Address")
        phone = st.text_input("Phone *")
        phonepe_name = st.text_input("PhonePe Contact Name *", help="Exact name as in PhonePe statement")
        start = st.date_input("Start Date", date.today())
        daily = st.number_input("Daily Amount *", min_value=0.01, step=0.01, format="%.2f")
        principal = st.number_input("Principal *", min_value=0.01, step=0.01, format="%.2f")
        wname = st.text_input("Witness Name")
        waddr = st.text_area("Witness Address")
        wphone = st.text_input("Witness Phone")
        photo = st.file_uploader(
            "Customer Photo",
            type=["jpg", "jpeg", "png"]
            )   

        submitted = st.form_submit_button("Create Customer")
        if submitted:
            if not name or not phone:
                st.error("Customer name and phone are mandatory")
            else:
                cid = db.add_customer(
                    name, phonepe_name, addr, phone, start,
                    daily, principal,
                    wname, waddr, wphone
                )
                if photo:
                    photo_path = f"customer_photos/customer_{cid}.jpg"
                    with open(photo_path, "wb") as f:
                        f.write(photo.getbuffer())

                    db.update_customer_photo(cid, photo_path)
                st.success(f"✅ Customer created successfully (ID: {cid})")


def collect_payment_ui(db):
    st.subheader("💳 Collect Payment")
    customers = db.customers()
    if customers:
        with st.form("collect_payment_form"):
            options = {f"{c['name']} (ID {c['id']})": c['id'] for c in customers}
            sel = st.selectbox("Customer", options)
            amt = st.number_input("Amount", min_value=0.01, value=250.00, step=0.01, format="%.2f")
            d = st.date_input("Payment Date", date.today())

            submitted = st.form_submit_button("Collect Payment")
            if submitted:
                with st.spinner("Settling payment..."):
                    db.collect_payment(options[sel], amt, d)
                st.success("✅ Payment collected and settled successfully")
                st.toast("Ledger updated", icon="💰")
                st.session_state['payment_done'] = True

        if st.session_state.get('payment_done'):
            st.session_state['payment_done'] = False
            #st.experimental_rerun()  # Safe rerun only for UI refresh


def ledger_ui(db):
    st.subheader("📒 Customer Ledger")

    cid = st.number_input("Enter Customer ID", step=1)

    if not cid:
        return

    rows = db.ledger(cid)

    if not rows:
        st.info("No records found")
        return

    df = pd.DataFrame(rows, columns=[
        "Date", "Expected", "Paid", "Pending", "Paid On"
    ])

    # ✅ Keep original datetime for logic
    df["Date_dt"] = pd.to_datetime(df["Date"])
    df["Paid_On_dt"] = pd.to_datetime(df["Paid On"], errors="coerce")

    # 🔥 STATUS LOGIC (correct comparison)
    def get_status(row):
        if row["Pending"] == 0:
            if pd.notnull(row["Paid_On_dt"]) and row["Paid_On_dt"] > row["Date_dt"]:
                return "🔴 Late"
            else:
                return "🟢 On Time"
        return "🟡 Pending"

    df["Status"] = df.apply(get_status, axis=1)

    # 🎯 Format for display
    df["Date"] = df["Date_dt"].dt.strftime("%b %d")
    df["Paid On"] = df["Paid_On_dt"].dt.strftime("%b %d")

    df["Paid On"] = df["Paid On"].fillna("NULL")

    # Drop helper columns
    df = df.drop(columns=["Date_dt", "Paid_On_dt"])

    st.dataframe(df, use_container_width=True)



# ===================== PDF UPLOAD =====================

def parse_phonepe_pdf(file):
    records = []

    with pdfplumber.open(file) as pdf:
        # Extract text from all pages
        text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())

    # Split text into blocks by dates (start of transaction lines)
    blocks = re.split(r'\n(?=Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', text)

    for block in blocks:
        if "CREDIT" not in block.upper():
            continue  # Skip debit/other entries

        try:
            # Extract date
            date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}', block)
            # Extract amount
            amt_match = re.search(r'₹([\d,]+\.\d+|[\d,]+)', block)
            # Extract sender
            sender_match = re.search(r'Received from\s+([A-Za-z .]+?)(?:\s+CREDIT|\s+₹|\n)', block)
            # Flexible txn_id extraction
            txn_match = re.search(r'Transaction\s+ID\s*[:\s]*([A-Za-z0-9]+)', block, re.I)
            txn_id = txn_match.group(1).strip() if txn_match else None

            if not (date_match and amt_match and sender_match):
                continue  # Skip if mandatory fields missing

            txn_date = datetime.strptime(date_match.group(), "%b %d, %Y").date()
            amount = float(amt_match.group(1).replace(",", ""))
            sender = sender_match.group(1).strip()

            records.append({
                "date": txn_date,
                "amount": amount,
                "sender": sender,
                "txn_id": txn_id
            })

        except Exception:
            continue  # Skip any problematic blocks

    return pd.DataFrame(records)




def find_customer_by_name(db, sender):
    customers = db.customers()
    for c in customers:
        if sender.lower() == c['phonepe_contact_name'].lower():
            return c['id']

    return None


def upload_pdf_ui(db):
    st.subheader("📄 Upload Daily Payment PDF")

    pdf = st.file_uploader("Upload PhonePe Statement PDF", type=["pdf"])

    if not pdf:
        st.info("Please upload a PhonePe statement PDF")
        return

    # 🔹 Date range selector
    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input("From Date")
    with col2:
        to_date = st.date_input("To Date")

    if from_date > to_date:
        st.error("From Date cannot be after To Date")
        return

    # 🔹 Parse PDF
    df = parse_phonepe_pdf(pdf)

    if df.empty:
        st.error("No CREDIT transactions found in PDF")
        return

    # 🔹 Filter by date range
    df_filtered = df[
        (df["date"] >= from_date) &
        (df["date"] <= to_date)
    ].copy()

    if df_filtered.empty:
        st.warning("No transactions found in selected date range")
        return

    st.success(f"Found {len(df_filtered)} transactions in selected date range")
    st.dataframe(df_filtered, width='stretch')

    # 🔹 Import button
    if st.button("✅ Import to Ledger"):
        success, failed = 0, 0

        for _, row in df_filtered.iterrows():
            cid = find_customer_by_name(db, row["sender"])
            if cid:
                db.collect_payment(cid, row["amount"], row["date"], txn_id=row["txn_id"])
                success += 1
            else:
                failed += 1

        st.success(f"Imported: {success}")
        if failed:
            st.warning(f"Unmatched transactions: {failed}")

        st.rerun()


def customer_inquiry_ui(db):
    st.subheader("🔍 Customer Inquiry & Edit")

    customers = db.customers()
    if not customers:
        st.info("No customers found")
        return

    options = {f"{c['name']} (ID {c['id']})": c['id'] for c in customers}
    selected = st.selectbox("Select Customer", options)

    cid = options[selected]

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            "SELECT * FROM customers WHERE id=%s",
            (cid,)
        )
        cust = cur.fetchone()

    col1, col2 = st.columns([1, 2])

    # 📸 PHOTO
    with col1:
        if cust.get("customer_photo"):
            st.image(cust["customer_photo"], caption="Customer Photo", width='stretch')
        else:
            st.info("No photo uploaded")

    # ✏️ EDIT FORM
    with col2:
        with st.form("edit_customer_form"):
            name = st.text_input("Name", cust["name"])
            phonepe = st.text_input("PhonePe Name", cust["phonepe_contact_name"])
            phone = st.text_input("Phone", cust["phone"])
            address = st.text_area("Address", cust["address"])

            submitted = st.form_submit_button("💾 Update Customer")

            if submitted:
                with get_conn() as conn:
                    conn.execute("""
                        UPDATE customers
                        SET name=?, phonepe_contact_name=?, phone=?, address=?
                        WHERE id=%s
                    """, (name, phonepe, phone, address, cid))

                st.success("✅ Customer details updated")
                st.rerun()




def main():
    # -------------------- PAGE CONFIG --------------------
    st.set_page_config(
        page_title="Chit Fund Tracker",
        layout="wide"
    )

    # -------------------- DB INIT --------------------
    db = ChitFundDB()

    # -------------------- SESSION STATE --------------------
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state['payment_done'] = False

    # -------------------- LOGIN PAGE --------------------
    if not st.session_state.logged_in:
        # Title and welcome message
        st.markdown("<h1 style='text-align:center;'>💰 Welcome to Chit Fund Tracker</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:gray;'>Please login to continue</p>", unsafe_allow_html=True)
        st.write("")

        # Centered columns for responsiveness
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            # Compact login card
            #st.markdown(
            #    """
            #    <div style="
            #        border: 2px solid #4CAF50;
            #        border-radius: 10px;
            #        padding: 30px 20px;
            #        box-shadow: 2px 2px 12px rgba(0,0,0,0.15);
            #        background-color: #f9f9f9;
            #   ">
            #    </div>
            #    """,
            #    unsafe_allow_html=True
            #)

            # Input fields
            user = st.text_input("Username", placeholder="Enter your username")
            pwd = st.text_input("Password", type="password", placeholder="Enter your password")

            # Green login button
            login_btn = st.button("Login", key="login_btn", width='stretch')

            if login_btn:
                if user == "admin" and pwd == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.role = "admin"
                elif user == "collector" and pwd == "collector123":
                    st.session_state.logged_in = True
                    st.session_state.role = "collector"
                else:
                    st.error("❌ Invalid credentials")

        # Stop rendering rest of app until login
        st.stop()

    # -------------------- DASHBOARD AFTER LOGIN --------------------
    role = "admin"

    # -------------------- SIDEBAR --------------------
    # Logout button at top of sidebar
    if st.sidebar.button("🔓 Logout", key="logout_btn"):
        st.session_state.logged_in = False
        st.session_state.role = None
        # Force a rerun
        st.session_state['rerun_flag'] = not st.session_state.get('rerun_flag', False)
        st.stop()  # stops current execution, app reruns automatically

    tabs = [
    "📊 Dashboard",
    "🔍 Customer Inquiry",
    "➕ Add Customer",
    "💳 Collect Payment",
    "📒 Ledger",
    "📅 Day-wise Analysis",
    "📄 Upload Payment PDF"]

    
    if role == "collector":
        tabs.remove("➕ Add Customer")

    selected = st.sidebar.radio("Menu", tabs)


    # -------------------- TAB RENDER --------------------
    if selected == "📊 Dashboard":
        dashboard(db)
    elif selected == "➕ Add Customer" and role == "admin":
        add_customer_ui(db)
    elif selected == "💳 Collect Payment":
        collect_payment_ui(db)
    elif selected == "📒 Ledger":
        ledger_ui(db)
    elif selected == "📅 Day-wise Analysis":
        day_wise_analysis(db)
    elif selected == "📄 Upload Payment PDF":
        upload_pdf_ui(db)
    elif selected == "🔍 Customer Inquiry":
        customer_inquiry_ui(db)




if __name__ == '__main__':
    main()
