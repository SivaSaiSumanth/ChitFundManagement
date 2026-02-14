import streamlit as st
import json
import os
from datetime import datetime, timedelta
import pandas as pd
import time
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =====================================================
# 📱 PAGE SETTINGS (Tablet Optimized)
# =====================================================

st.set_page_config(
    page_title="Chit Fund Manager",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =====================================================
# 🎨 TABLET UI STYLING
# =====================================================

st.markdown("""
<style>

.block-container {
    padding-top: 2rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

html, body, [class*="css"] {
    font-size: 18px;
}

.stButton>button {
    height: 3rem;
    font-size: 18px;
    border-radius: 8px;
}

.stTextInput input {
    height: 45px;
    font-size: 18px;
}

h1, h2, h3 {
    text-align: center;
}

</style>
""", unsafe_allow_html=True)

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

        if st.button("Login", use_container_width=True):

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



class ChitFundTracker:
    def __init__(self, data_file="chitfund_data.json"):
        self.data_file = data_file
        self.data = self.load_data()
   
    def load_data(self):
        """Load data from JSON file"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    # Ensure overpayments key exists
                    if "overpayments" not in data:
                        data["overpayments"] = {}
                    return data
            except:
                return {"customers": {}, "collections": {}, "overpayments": {}}
        return {"customers": {}, "collections": {}, "overpayments": {}}
   
    def save_data(self):
        """Save data to JSON file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            return True
        except:
            return False
   
    def add_customer(self, name, principal, daily_amount, start_date, phone="", address=""):
        """Add a new customer to the system"""
        customer_id = f"CUST{len(self.data['customers']) + 1:04d}"
   
        # Convert date to string if it's a date object
        if hasattr(start_date, 'strftime'):
            start_date_str = start_date.strftime("%Y-%m-%d")
        else:
            start_date_str = str(start_date)
   
        # Fix: This was incorrectly indented
        self.data["customers"][customer_id] = {
            "name": name,
            "principal": principal,
            "daily_amount": daily_amount,
            "collected": 0,
            "start_date": start_date_str,
            "phone": phone,
            "address": address,
            "created_at": datetime.now().isoformat()
        }
   
        self.save_data()
        return customer_id
   
    def add_collection(self, customer_id, amount, date, notes=""):
        """Add a collection record"""
        if customer_id not in self.data["customers"]:
            return False
       
        collection_id = f"COL_{len(self.data.get('collections', {})) + 1:06d}"
       
        if "collections" not in self.data:
            self.data["collections"] = {}
       
        self.data["collections"][collection_id] = {
            "customer_id": customer_id,
            "amount": amount,
            "date": date,
            "notes": notes,
            "created_at": datetime.now().isoformat()
        }
       
        # Update customer's collected amount
        self.data["customers"][customer_id]["collected"] += amount
       
        return self.save_data()
   
    def handle_overpayment(self, customer_id, overpayment_amount, payment_date):
        """Handle overpayment by storing it for future use"""
        if "overpayments" not in self.data:
            self.data["overpayments"] = {}
       
        if customer_id not in self.data["overpayments"]:
            self.data["overpayments"][customer_id] = []
       
        self.data["overpayments"][customer_id].append({
            "amount": overpayment_amount,
            "date": payment_date,
            "remaining": overpayment_amount,
            "created_at": datetime.now().isoformat()
        })
       
        return self.save_data()
   
    def apply_overpayment_to_future_days(self, customer_id):
        """Automatically apply overpayments to future missed days"""
        if customer_id not in self.data.get("overpayments", {}):
            return False, []
       
        customer = self.data["customers"].get(customer_id)
        if not customer:
            return False, []
       
        daily_amount = customer["daily_amount"]
        applied_payments = []
       
        # Get future dates that need payment (next 30 days)
        current_date = datetime.now().date()
        future_dates = []
       
        for i in range(1, 31):
            future_date = current_date + timedelta(days=i)
            # Skip Sundays
            if future_date.weekday() != 6:
                # Check if payment already exists for this date
                date_str = future_date.strftime("%Y-%m-%d")
                has_payment = any(
                    c["customer_id"] == customer_id and c["date"] == date_str
                    for c in self.data.get("collections", {}).values()
                )
                if not has_payment:
                    future_dates.append(future_date)
       
        # Apply overpayments to future dates
        for overpayment in self.data["overpayments"][customer_id]:
            if overpayment["remaining"] <= 0:
                continue
               
            for future_date in future_dates[:]:  # Use slice to avoid modification during iteration
                if overpayment["remaining"] <= 0:
                    break
                   
                date_str = future_date.strftime("%Y-%m-%d")
               
                if overpayment["remaining"] >= daily_amount:
                    # Full day coverage
                    if self.add_collection(
                        customer_id,
                        daily_amount,
                        date_str,
                        f"Auto-applied from overpayment on {overpayment['date']}"
                    ):
                        overpayment["remaining"] -= daily_amount
                        applied_payments.append({
                            "date": date_str,
                            "amount": daily_amount,
                            "type": "full_advance"
                        })
                        future_dates.remove(future_date)
                else:
                    # Partial coverage
                    if self.add_collection(
                        customer_id,
                        overpayment["remaining"],
                        date_str,
                        f"Partial auto-applied from overpayment on {overpayment['date']}"
                    ):
                        applied_payments.append({
                            "date": date_str,
                            "amount": overpayment["remaining"],
                            "type": "partial_advance"
                        })
                        overpayment["remaining"] = 0
                        future_dates.remove(future_date)
       
        success = self.save_data()
        return success, applied_payments
   
    def get_customer_overpayment_balance(self, customer_id):
        """Get total overpayment balance for a customer"""
        if customer_id not in self.data.get("overpayments", {}):
            return 0
       
        return sum(
            op["remaining"] for op in self.data["overpayments"][customer_id]
            if op["remaining"] > 0
        )

    def collect_payment(self, customer_id, amount, payment_date, notes=""):
        """Collect payment with smart handling of missed days and overpayments"""
        customer = self.data["customers"].get(customer_id)
        if not customer:
            return False, "Customer not found"
   
        # Convert date to string if it's a date object
        if hasattr(payment_date, 'strftime'):
            payment_date_str = payment_date.strftime("%Y-%m-%d")
        else:
            payment_date_str = str(payment_date)
   
        # Use the smart collection method
        success, collections_added = self.add_collection_with_auto_fill(
            customer_id, amount, payment_date_str, notes
        )
   
        if success:
            # Create a summary message
            regular_payments = [c for c in collections_added if c["type"] == "regular"]
            backfills = [c for c in collections_added if c["type"] == "backfill"]
            future_fills = [c for c in collections_added if c["type"] == "future_fill"]
            overpayments = [c for c in collections_added if c["type"] == "overpayment"]
       
            message_parts = []
       
            if regular_payments:
                message_parts.append(f"Regular payment: ₹{sum(c['amount'] for c in regular_payments):,}")
       
            if backfills:
                message_parts.append(f"Backfilled {len(backfills)} missed days: ₹{sum(c['amount'] for c in backfills):,}")
       
            if future_fills:
                message_parts.append(f"Applied to {len(future_fills)} future days: ₹{sum(c['amount'] for c in future_fills):,}")
       
            if overpayments:
                message_parts.append(f"Overpayment stored: ₹{sum(c['amount'] for c in overpayments):,}")
       
            message = "Payment collected successfully! " + " | ".join(message_parts)
            return True, message
        else:
            return False, "Failed to process payment"
   
    def add_collection_with_auto_fill(self, customer_id, amount, payment_date, notes=""):
        """Add collection with automatic filling of missed days and overpayment handling"""
        customer = self.data["customers"].get(customer_id)
        if not customer:
            return False, []
       
        daily_amount = customer["daily_amount"]
        remaining_amount = amount
       
        # Get payment history to identify gaps
        history = self.get_customer_comprehensive_history(customer_id)
        payment_date_obj = datetime.strptime(payment_date, "%Y-%m-%d").date()
       
        # Find all unpaid days up to payment date
        unpaid_days = []
        for record in history:
            if record["date"] <= payment_date_obj and record["status"] == "missed":
                unpaid_days.append(record["date"])
       
        # Sort unpaid days (oldest first)
        unpaid_days.sort()
       
        collections_to_add = []
       
        # Step 1: Fill missed days first (oldest to newest)
        for missed_date in unpaid_days:
            if remaining_amount >= daily_amount:
                collections_to_add.append({
                    "date": missed_date.strftime("%Y-%m-%d"),
                    "amount": daily_amount,
                    "notes": f"Auto-filled from excess payment on {payment_date}. {notes}".strip(),
                    "type": "backfill"
                })
                remaining_amount -= daily_amount
            elif remaining_amount > 0:
                # Partial payment for this day
                collections_to_add.append({
                    "date": missed_date.strftime("%Y-%m-%d"),
                    "amount": remaining_amount,
                    "notes": f"Partial auto-fill from excess payment on {payment_date}. {notes}".strip(),
                    "type": "partial_backfill"
                })
                remaining_amount = 0
                break
       
        # Step 2: Fill today's payment if it's not already covered
        today_already_covered = any(
            c["date"] == payment_date for c in collections_to_add
        )
       
        if not today_already_covered:
            if remaining_amount >= daily_amount:
                collections_to_add.append({
                    "date": payment_date,
                    "amount": daily_amount,
                    "notes": f"Regular payment. {notes}".strip(),
                    "type": "regular"
                })
                remaining_amount -= daily_amount
            elif remaining_amount > 0:
                collections_to_add.append({
                    "date": payment_date,
                    "amount": remaining_amount,
                    "notes": f"Partial payment. {notes}".strip(),
                    "type": "partial"
                })
                remaining_amount = 0
       
        # Step 3: Apply remaining amount to future days
        if remaining_amount > 0:
            # Get future dates for auto-application
            future_dates = []
            current_date = payment_date_obj + timedelta(days=1)
           
            for i in range(30):  # Next 30 days
                check_date = current_date + timedelta(days=i)
                if check_date.weekday() != 6:  # Skip Sundays
                    # Check if payment already exists
                    date_str = check_date.strftime("%Y-%m-%d")
                    has_payment = any(
                        c["customer_id"] == customer_id and c["date"] == date_str
                        for c in self.data.get("collections", {}).values()
                    )
                    if not has_payment:
                        future_dates.append(check_date)
           
            # Apply to future dates
            for future_date in future_dates:
                if remaining_amount <= 0:
                    break
                   
                if remaining_amount >= daily_amount:
                    collections_to_add.append({
                        "date": future_date.strftime("%Y-%m-%d"),
                        "amount": daily_amount,
                        "notes": f"Auto-applied from excess payment on {payment_date}. {notes}".strip(),
                        "type": "future_fill"
                    })
                    remaining_amount -= daily_amount
                else:
                    collections_to_add.append({
                        "date": future_date.strftime("%Y-%m-%d"),
                        "amount": remaining_amount,
                        "notes": f"Partial auto-applied from excess payment on {payment_date}. {notes}".strip(),
                        "type": "future_partial"
                    })
                    remaining_amount = 0
       
        # Step 4: Handle any remaining overpayment
        if remaining_amount > 0:
            # Store as overpayment
            self.handle_overpayment(customer_id, remaining_amount, payment_date)
            collections_to_add.append({
                "date": payment_date,
                "amount": remaining_amount,
                "notes": f"Overpayment stored for future use. {notes}".strip(),
                "type": "overpayment"
            })
       
        # Save all collections (except overpayment which is already saved)
        success_count = 0
        for collection_data in collections_to_add:
            if collection_data["type"] != "overpayment":
                if self.add_collection(
                    customer_id,
                    collection_data["amount"],
                    collection_data["date"],
                    collection_data["notes"]
                ):
                    success_count += 1
            else:
                success_count += 1  # Overpayment was already handled
       
        return success_count == len(collections_to_add), collections_to_add
   
    def get_customer_comprehensive_history(self, customer_id, days_ahead=30):
        """Get comprehensive payment history including past, present and future days"""
        customer = self.data["customers"].get(customer_id)
        if not customer:
            return []
       
        start_date = datetime.strptime(customer["start_date"], "%Y-%m-%d").date()
        today = datetime.now().date()
        end_date = today + timedelta(days=days_ahead)  # Include future days
       
        # Create a comprehensive history
        history = []
        current_date = start_date
       
        # Get all collections for this customer
        collections = self.data.get("collections", {})
        customer_collections = {}
        for collection in collections.values():
            if collection["customer_id"] == customer_id:
                date_key = collection["date"]
                if date_key in customer_collections:
                    # Multiple payments on same day - sum them up
                    customer_collections[date_key]["amount"] += collection["amount"]
                    customer_collections[date_key]["notes"] += f"; {collection.get('notes', '')}"
                else:
                    customer_collections[date_key] = collection.copy()
       
        while current_date <= end_date:
            # Skip Sundays (or customize based on your collection days)
            if current_date.weekday() != 6:  # 6 = Sunday
                date_str = current_date.strftime("%Y-%m-%d")
               
                if date_str in customer_collections:
                    # Payment made
                    collection = customer_collections[date_str]
                   
                    # Determine payment type based on notes and amount
                    notes = collection.get("notes", "")
                    amount = collection["amount"]
                    expected = customer["daily_amount"]
                   
                    payment_type = "regular"
                    if "Auto-filled from excess payment" in notes:
                        payment_type = "backfilled"
                    elif "Auto-applied from excess payment" in notes:
                        payment_type = "future_filled"
                    elif "Auto-applied from overpayment" in notes:
                        payment_type = "overpayment_applied"
                    elif amount < expected:
                        payment_type = "partial"
                    elif amount > expected:
                        payment_type = "overpayment"
                   
                    history.append({
                        "date": current_date,
                        "status": "paid",
                        "amount": amount,
                        "notes": notes,
                        "expected_amount": expected,
                        "payment_type": payment_type,
                        "is_future": current_date > today
                    })
                else:
                    # Payment not made
                    if current_date <= today:
                        # Past/today - missed payment
                        history.append({
                            "date": current_date,
                            "status": "missed",
                            "amount": 0,
                            "notes": "Payment not collected",
                            "expected_amount": customer["daily_amount"],
                            "payment_type": "missed",
                            "is_future": False
                        })
                    else:
                        # Future - pending payment
                        history.append({
                            "date": current_date,
                            "status": "pending",
                            "amount": 0,
                            "notes": "Future payment",
                            "expected_amount": customer["daily_amount"],
                            "payment_type": "pending",
                            "is_future": True
                        })
           
            current_date += timedelta(days=1)
       
        return history

    def apply_overpayment_manually(self, customer_id, apply_date, apply_amount):
        """Manually apply overpayment to a specific date"""
        if customer_id not in self.data.get("overpayments", {}):
            return False, "No overpayments found for this customer"
   
        # Convert date to string if it's a date object
        if hasattr(apply_date, 'strftime'):
            apply_date_str = apply_date.strftime("%Y-%m-%d")
        else:
            apply_date_str = str(apply_date)
   
        # Check if payment already exists for this date
        existing_payment = any(
            c["customer_id"] == customer_id and c["date"] == apply_date_str
            for c in self.data.get("collections", {}).values()
        )
   
        if existing_payment:
            return False, "Payment already exists for this date"
   
        # Check if sufficient overpayment balance exists
        overpayment_balance = self.get_customer_overpayment_balance(customer_id)
        if overpayment_balance < apply_amount:
            return False, f"Insufficient overpayment balance. Available: ₹{overpayment_balance:,}"
   
        # Apply the overpayment
        success = self.add_collection(
            customer_id,
            apply_amount,
            apply_date_str,
            f"Manual application of overpayment"
        )
   
        if success:
            # Reduce overpayment balance
            remaining_to_deduct = apply_amount
            for overpayment in self.data["overpayments"][customer_id]:
                if remaining_to_deduct <= 0:
                    break
                if overpayment["remaining"] > 0:
                    deduction = min(overpayment["remaining"], remaining_to_deduct)
                    overpayment["remaining"] -= deduction
                    remaining_to_deduct -= deduction
       
            self.save_data()
            return True, f"Successfully applied ₹{apply_amount:,} to {apply_date_str}"
        else:
            return False, "Failed to apply overpayment"
   
   
    def get_missed_collections(self, customer_id):
        """Get list of missed collection dates for a customer"""
        customer = self.data["customers"].get(customer_id)
        if not customer:
            return []
       
        start_date = datetime.strptime(customer["start_date"], "%Y-%m-%d").date()
        today = datetime.now().date()
       
        # Get all dates from start_date to today
        all_dates = []
        current_date = start_date
        while current_date <= today:
            # Skip Sundays (or any day you don't collect)
            if current_date.weekday() != 6:  # 6 = Sunday
                all_dates.append(current_date)
            current_date += timedelta(days=1)
       
        # Get dates when payments were made
        collections = self.data.get("collections", {})
        paid_dates = set()
        for collection in collections.values():
            if collection["customer_id"] == customer_id:
                paid_date = datetime.strptime(collection["date"], "%Y-%m-%d").date()
                paid_dates.add(paid_date)
       
        # Find missed dates
        missed_dates = [date for date in all_dates if date not in paid_dates]
        return missed_dates
   
    def get_customer_payment_history(self, customer_id):
        """Get detailed payment history with missed days (legacy function for compatibility)"""
        return self.get_customer_comprehensive_history(customer_id, days_ahead=0)
   
    def get_dashboard_data(self):
        """Get dashboard summary data"""
        customers = self.data.get("customers", {})
        collections = self.data.get("collections", {})
       
        total_customers = len(customers)
        total_principal = sum(c["principal"] for c in customers.values())
        total_collected = sum(c["collected"] for c in customers.values())
        total_remaining = total_principal - total_collected
       
        # Today's collections
        today = datetime.now().date().strftime("%Y-%m-%d")
        today_collections = sum(
            c["amount"] for c in collections.values()
            if c["date"] == today
        )
       
        # Customers with missed payments
        customers_with_missed = 0
        total_missed_amount = 0
       
        # Total overpayments
        total_overpayments = 0
        customers_with_overpayments = 0
       
        for customer_id in customers:
            missed_dates = self.get_missed_collections(customer_id)
            if missed_dates:
                customers_with_missed += 1
                total_missed_amount += len(missed_dates) * customers[customer_id]["daily_amount"]
           
            # Check overpayments
            overpayment_balance = self.get_customer_overpayment_balance(customer_id)
            if overpayment_balance > 0:
                customers_with_overpayments += 1
                total_overpayments += overpayment_balance
       
        return {
            "total_customers": total_customers,
            "total_principal": total_principal,
            "total_collected": total_collected,
            "total_remaining": total_remaining,
            "today_collections": today_collections,
            "customers_with_missed": customers_with_missed,
            "total_missed_amount": total_missed_amount,
            "total_overpayments": total_overpayments,
            "customers_with_overpayments": customers_with_overpayments
        }

def display_comprehensive_payment_record(record, customer):
    """Display payment record with comprehensive visual indicators"""
    date_str = record["date"].strftime("%Y-%m-%d (%A)")
    status = record["status"]
    amount = record.get("amount", 0)
    expected = record["expected_amount"]
    notes = record.get("notes", "")
    payment_type = record.get("payment_type", "regular")
    is_future = record.get("is_future", False)
   
    # Determine styling based on payment type and status
    if status == "missed":
        # Missed payment - RED
        st.markdown(f"""
        <div style="background-color: #ffebee; border-left: 5px solid #f44336; padding: 15px; margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #d32f2f; font-size: 16px;">📅 {date_str}</strong><br>
                    <span style="color: #d32f2f; font-weight: bold; font-size: 14px;">❌ MISSED PAYMENT</span><br>
                    <span style="color: #d32f2f;">Expected: ₹{expected:,}</span>
                </div>
                <div style="text-align: right;">
                    <span style="color: #d32f2f; font-weight: bold; font-size: 18px;">-₹{expected:,}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
       
    elif status == "pending":
        # Future pending payment - GRAY
        st.markdown(f"""
        <div style="background-color: #f5f5f5; border-left: 5px solid #9e9e9e; padding: 15px; margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #616161; font-size: 16px;">📅 {date_str}</strong><br>
                    <span style="color: #616161; font-weight: bold; font-size: 14px;">⏳ PENDING PAYMENT</span><br>
                    <span style="color: #616161;">Expected: ₹{expected:,}</span>
                </div>
                <div style="text-align: right;">
                    <span style="color: #616161; font-size: 14px;">Future</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
       
    elif payment_type == "backfilled":
        # Backfilled from excess payment - BLUE
        st.markdown(f"""
        <div style="background-color: #e3f2fd; border-left: 5px solid #2196f3; padding: 15px; margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #1976d2; font-size: 16px;">📅 {date_str}</strong><br>
                    <span style="color: #1976d2; font-weight: bold; font-size: 14px;">🔄 AUTO-FILLED (Backfill)</span><br>
                    <span style="color: #1976d2;">Amount: ₹{amount:,}</span><br>
                    <small style="color: #666; font-style: italic;">{notes}</small>
                </div>
                <div style="text-align: right;">
                    <span style="color: #1976d2; font-weight: bold; font-size: 18px;">+₹{amount:,}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
       
    elif payment_type == "future_filled":
        # Future filled from excess payment - PURPLE
        st.markdown(f"""
        <div style="background-color: #f3e5f5; border-left: 5px solid #9c27b0; padding: 15px; margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #7b1fa2; font-size: 16px;">📅 {date_str}</strong><br>
                    <span style="color: #7b1fa2; font-weight: bold; font-size: 14px;">🚀 ADVANCE PAYMENT</span><br>
                    <span style="color: #7b1fa2;">Amount: ₹{amount:,}</span><br>
                    <small style="color: #666; font-style: italic;">{notes}</small>
                </div>
                <div style="text-align: right;">
                    <span style="color: #7b1fa2; font-weight: bold; font-size: 18px;">+₹{amount:,}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
       
    elif payment_type == "overpayment_applied":
        # Overpayment applied - TEAL
        st.markdown(f"""
        <div style="background-color: #e0f2f1; border-left: 5px solid #009688; padding: 15px; margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #00695c; font-size: 16px;">📅 {date_str}</strong><br>
                    <span style="color: #00695c; font-weight: bold; font-size: 14px;">💰 OVERPAYMENT APPLIED</span><br>
                    <span style="color: #00695c;">Amount: ₹{amount:,}</span><br>
                    <small style="color: #666; font-style: italic;">{notes}</small>
                </div>
                <div style="text-align: right;">
                    <span style="color: #00695c; font-weight: bold; font-size: 18px;">+₹{amount:,}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
       
    elif payment_type == "partial":
        # Partial payment - ORANGE
        st.markdown(f"""
        <div style="background-color: #fff8e1; border-left: 5px solid #ff9800; padding: 15px; margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #f57c00; font-size: 16px;">📅 {date_str}</strong><br>
                    <span style="color: #f57c00; font-weight: bold; font-size: 14px;">⚠️ PARTIAL PAYMENT</span><br>
                    <span style="color: #f57c00;">Paid: ₹{amount:,} / Expected: ₹{expected:,}</span><br>
                    <small style="color: #666; font-style: italic;">{notes}</small>
                </div>
                <div style="text-align: right;">
                    <span style="color: #f57c00; font-weight: bold; font-size: 18px;">+₹{amount:,}</span><br>
                    <small style="color: #d84315;">Short: ₹{expected - amount:,}</small>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
       
    else:
        # Regular payment - GREEN
        st.markdown(f"""
        <div style="background-color: #e8f5e8; border-left: 5px solid #4caf50; padding: 15px; margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #2e7d32; font-size: 16px;">📅 {date_str}</strong><br>
                    <span style="color: #2e7d32; font-weight: bold; font-size: 14px;">✅ REGULAR PAYMENT</span><br>
                    <span style="color: #2e7d32;">Amount: ₹{amount:,}</span><br>
                    {f'<small style="color: #666; font-style: italic;">{notes}</small>' if notes else ''}
                </div>
                <div style="text-align: right;">
                    <span style="color: #2e7d32; font-weight: bold; font-size: 18px;">+₹{amount:,}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

def display_payment_with_indicators(record, customer):
    """Display payment record with special indicators for auto-filled payments (legacy function)"""
    display_comprehensive_payment_record(record, customer)

def display_overpayment_management(tracker):
    """Display overpayment management interface"""
    st.subheader("💰 Overpayment Management")
   
    customers = tracker.data.get("customers", {})
   
    # Check for customers with overpayments
    customers_with_overpayments = []
    for customer_id in customers:
        overpayment_balance = tracker.get_customer_overpayment_balance(customer_id)
        if overpayment_balance > 0:
            customers_with_overpayments.append({
                "id": customer_id,
                "name": customers[customer_id]["name"],
                "balance": overpayment_balance,
                "daily_amount": customers[customer_id]["daily_amount"]
            })
   
    if not customers_with_overpayments:
        st.info("📝 No pending overpayments found.")
        return
   
    # Display customers with overpayments
    for customer_info in customers_with_overpayments:
        customer_id = customer_info["id"]
        customer_name = customer_info["name"]
        overpayment_balance = customer_info["balance"]
        daily_amount = customer_info["daily_amount"]
       
        with st.expander(f"👤 {customer_name} - Balance: ₹{overpayment_balance:,}"):
            # Show overpayment details
            st.write("**Overpayment History:**")
            overpayments = tracker.data.get("overpayments", {}).get(customer_id, [])
            for overpayment in overpayments:
                if overpayment["remaining"] > 0:
                    st.write(f"• {overpayment['date']}: ₹{overpayment['amount']:,} (Remaining: ₹{overpayment['remaining']:,})")
           
            # Auto-apply and manual options
            col1, col2 = st.columns(2)
           
            with col1:
                st.write("**🔄 Auto-Apply to Future Days**")
                days_covered = overpayment_balance // daily_amount
                st.info(f"📅 Can cover {days_covered} full days")
               
                if st.button(f"Auto-apply to Future Days", key=f"auto_{customer_id}"):
                    success, applied_payments = tracker.apply_overpayment_to_future_days(customer_id)
                    if success and applied_payments:
                        st.success(f"✅ Applied overpayment to {len(applied_payments)} future days!")
                        for payment in applied_payments:
                            st.write(f"• {payment['date']}: ₹{payment['amount']:,}")
                        st.rerun()
                    elif success:
                        st.warning("⚠️ No future days available for application")
                    else:
                        st.error("❌ Failed to apply overpayment")
           
            with col2:
                st.write("**✋ Manual Application**")
               
                # Date selection for manual application
                apply_date = st.date_input(
                    "Select date",
                    min_value=datetime.now().date(),
                    key=f"date_{customer_id}"
                )
               
                # Amount to apply
                max_applicable = min(overpayment_balance, daily_amount)
                apply_amount = st.number_input(
                    "Amount to apply",
                    min_value=1,
                    max_value=int(overpayment_balance),
                    value=int(max_applicable),
                    key=f"amount_{customer_id}"
                )
               
                if st.button(f"Apply ₹{apply_amount:,}", key=f"manual_{customer_id}"):
                    success, message = tracker.apply_overpayment_manually(customer_id, apply_date, apply_amount)
                    if success:
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")

def main():
    st.set_page_config(
        page_title="Chit Fund Tracker",
        page_icon="💰",
        layout="wide"
    )
   
    
    st.markdown("---")
   
    # Initialize tracker
    tracker = ChitFundTracker()
   
    # Sidebar for navigation
    st.sidebar.title("📊 Navigation")
   
    # Dashboard metrics in sidebar
    dashboard_data = tracker.get_dashboard_data()
   
    st.sidebar.metric("👥 Total Customers", dashboard_data["total_customers"])
    st.sidebar.metric("💰 Total Principal", f"₹{dashboard_data['total_principal']:,}")
    st.sidebar.metric("✅ Total Collected", f"₹{dashboard_data['total_collected']:,}")
    st.sidebar.metric("⏳ Remaining", f"₹{dashboard_data['total_remaining']:,}")
   
    # Show overpayment info in sidebar
    if dashboard_data["customers_with_overpayments"] > 0:
        st.sidebar.success(f"💰 {dashboard_data['customers_with_overpayments']} customers have overpayments")
        st.sidebar.success(f"💵 Total overpayments: ₹{dashboard_data['total_overpayments']:,}")
   
    if dashboard_data["customers_with_missed"] > 0:
        st.sidebar.error(f"🚨 {dashboard_data['customers_with_missed']} customers have missed payments")
        st.sidebar.error(f"💸 Total missed: ₹{dashboard_data['total_missed_amount']:,}")
   
    # Main tabs - REMOVED Overpayment Management
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard",
        "👥 Add Customer",
        "💳 Collect Payment",
        "📋 Customer Details",
        "📈 Reports"
    ])
   
    # Tab 1: Dashboard
    with tab1:
        st.header("📊 Dashboard Overview")
       
        # Key metrics
        col1, col2, col3, col4, col5 = st.columns(5)
       
        with col1:
            st.metric(
                "👥 Total Customers",
                dashboard_data["total_customers"],
                help="Total number of active customers"
            )
       
        with col2:
            collection_rate = (dashboard_data["total_collected"] / dashboard_data["total_principal"] * 100) if dashboard_data["total_principal"] > 0 else 0
            st.metric(
                "📈 Collection Rate",
                f"{collection_rate:.1f}%",
                help="Percentage of principal amount collected"
            )
       
        with col3:
            st.metric(
                "💰 Today's Collections",
                f"₹{dashboard_data['today_collections']:,}",
                help="Total amount collected today"
            )
       
        with col4:
            st.metric(
                "🚨 Missed Payments",
                dashboard_data["customers_with_missed"],
                delta=f"₹{dashboard_data['total_missed_amount']:,}",
                delta_color="inverse",
                help="Customers with pending collections"
            )
       
        with col5:
            st.metric(
                "💵 Overpayments",
                dashboard_data["customers_with_overpayments"],
                delta=f"₹{dashboard_data['total_overpayments']:,}",
                delta_color="normal",
                help="Customers with overpayment balance"
            )
       
        st.markdown("---")
       
        # Quick Overpayment Summary in Dashboard
        if dashboard_data["customers_with_overpayments"] > 0:
            with st.expander("💰 Overpayment Summary", expanded=False):
                customers = tracker.data.get("customers", {})
                overpayment_data = []
               
                for customer_id, customer in customers.items():
                    overpayment_balance = tracker.get_customer_overpayment_balance(customer_id)
                    if overpayment_balance > 0:
                        days_covered = overpayment_balance // customer['daily_amount']
                        overpayment_data.append({
                            "Customer": customer['name'],
                            "Overpayment": f"₹{overpayment_balance:,}",
                            "Days Covered": f"{days_covered} days",
                            "Daily Amount": f"₹{customer['daily_amount']:,}"
                        })
               
                if overpayment_data:
                    df_overpayment = pd.DataFrame(overpayment_data)
                    st.dataframe(df_overpayment, use_container_width=True)
                    st.info("💡 **Note:** Overpayments are automatically applied when collecting future payments.")
       
        # Customers overview with missed payment highlighting
        st.subheader("👥 Customers Overview")
       
        customers = tracker.data.get("customers", {})
        if customers:
            customer_data = []
           
            for customer_id, customer in customers.items():
                missed_dates = tracker.get_missed_collections(customer_id)
                missed_amount = len(missed_dates) * customer["daily_amount"]
                remaining = customer["principal"] - customer["collected"]
                overpayment_balance = tracker.get_customer_overpayment_balance(customer_id)
               
                status = "✅ COMPLETED" if remaining <= 0 else ("🚨 OVERDUE" if missed_dates else "🟢 ACTIVE")
                if overpayment_balance > 0:
                    status += " 💰"
               
                customer_data.append({
                    "Customer ID": customer_id,
                    "Name": customer["name"],
                    "Principal": f"₹{customer['principal']:,}",
                    "Daily Amount": f"₹{customer['daily_amount']:,}",
                    "Collected": f"₹{customer['collected']:,}",
                    "Remaining": f"₹{remaining:,}",
                    "Missed Days": len(missed_dates),
                    "Missed Amount": f"₹{missed_amount:,}",
                    "Overpayment": f"₹{overpayment_balance:,}",
                    "Status": status
                })
           
            df = pd.DataFrame(customer_data)
           
            # Apply styling for missed payments and overpayments
            def highlight_rows(row):
                if row["Missed Days"] > 0:
                    return ['background-color: #ffebee; color: #d32f2f'] * len(row)
                elif "COMPLETED" in row["Status"]:
                    return ['background-color: #e8f5e8; color: #2e7d32'] * len(row)
                elif "💰" in row["Status"]:
                    return ['background-color: #fff3e0; color: #f57c00'] * len(row)
                else:
                    return [''] * len(row)
           
            styled_df = df.style.apply(highlight_rows, axis=1)
            st.dataframe(styled_df, use_container_width=True)
           
            # Quick actions for overdue customers
            overdue_customers = [c for c in customer_data if c["Missed Days"] > 0]
            if overdue_customers:
                st.error(f"🚨 **{len(overdue_customers)} customers have overdue payments!**")
               
                with st.expander("📋 View Overdue Customers"):
                    for customer in overdue_customers:
                        st.markdown(f"""
                        **{customer['Name']}** ({customer['Customer ID']})
                        - Missed Days: **{customer['Missed Days']}**
                        - Missed Amount: **{customer['Missed Amount']}**
                        - Daily Amount: {customer['Daily Amount']}
                        """)
           
            # Show overpayment summary
            overpayment_customers = [c for c in customer_data if "💰" in c["Status"]]
            if overpayment_customers:
                st.success(f"💰 **{len(overpayment_customers)} customers have overpayments available!**")
               
                with st.expander("💵 View Customers with Overpayments"):
                    for customer in overpayment_customers:
                        st.markdown(f"""
                        **{customer['Name']}** ({customer['Customer ID']})
                        - Overpayment Balance: **{customer['Overpayment']}**
                        - Daily Amount: {customer['Daily Amount']}
                        """)
        else:
            st.info("📝 No customers added yet. Use the 'Add Customer' tab to get started.")
   
    # Tab 2: Add Customer
    with tab2:
        st.header("👥 Add New Customer")
       
        with st.form("add_customer_form"):
            col1, col2 = st.columns(2)
           
            with col1:
                customer_name = st.text_input("Customer Name *", placeholder="Enter customer name")
                principal_amount = st.number_input("Principal Amount (₹) *", min_value=1000, step=1000, value=10000)
                daily_amount = st.number_input("Daily Collection Amount (₹) *", min_value=10, step=10, value=100)
           
            with col2:
                start_date = st.date_input("Start Date *", value=datetime.now().date())
                phone = st.text_input("Phone Number", placeholder="Enter phone number")
                address = st.text_area("Address", placeholder="Enter address")
           
            submitted = st.form_submit_button("➕ Add Customer", type="primary")
           
            if submitted:
                if customer_name and principal_amount and daily_amount:
                    customer_id = tracker.add_customer(
                        customer_name, principal_amount, daily_amount,
                        start_date, phone, address
                    )
                    st.success(f"✅ Customer '{customer_name}' added successfully with ID: {customer_id}")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Please fill in all required fields marked with *")
   
    # Tab 3: Collect Payment
    with tab3:
        st.header("💳 Collect Payment")
       
        customers = tracker.data.get("customers", {})
        if not customers:
            st.warning("⚠️ No customers available. Please add customers first.")
        else:
            # Customer selection with search
            customer_options = {f"{customer['name']} ({customer_id})": customer_id
                             for customer_id, customer in customers.items()}
           
            selected_customer_display = st.selectbox(
                "Select Customer",
                options=list(customer_options.keys()),
                help="Choose the customer for payment collection"
            )
           
            if selected_customer_display:
                selected_customer_id = customer_options[selected_customer_display]
                customer = customers[selected_customer_id]
               
                # Show customer info
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.info(f"**Daily Amount:** ₹{customer['daily_amount']:,}")
                with col2:
                    remaining = customer['principal'] - customer['collected']
                    st.info(f"**Remaining:** ₹{remaining:,}")
                with col3:
                    overpayment_balance = tracker.get_customer_overpayment_balance(selected_customer_id)
                    if overpayment_balance > 0:
                        st.success(f"**Overpayment:** ₹{overpayment_balance:,}")
                    else:
                        st.info("**Overpayment:** ₹0")
               
                # Payment form
                with st.form("collect_payment_form"):
                    col1, col2 = st.columns(2)
                   
                    with col1:
                        payment_date = st.date_input("Payment Date", value=datetime.now().date())
                        payment_amount = st.number_input(
                            "Payment Amount (₹)",
                            min_value=1,
                            value=customer['daily_amount'],
                            help="Enter the amount collected"
                        )
                   
                    with col2:
                        payment_notes = st.text_area("Notes (Optional)", placeholder="Add any notes about this payment")
                   
                    # Show payment type prediction
                    if payment_amount:
                        expected = customer['daily_amount']
                        if payment_amount == expected:
                            st.success("✅ Regular payment amount")
                        elif payment_amount < expected:
                            st.warning(f"⚠️ Partial payment (Short by ₹{expected - payment_amount:,})")
                        else:
                            excess = payment_amount - expected
                            st.info(f"💰 Overpayment (Excess: ₹{excess:,})")
                   
                    submitted = st.form_submit_button("💳 Collect Payment", type="primary")
                   
                    if submitted:
                        success, message = tracker.collect_payment(
                            selected_customer_id, payment_amount, payment_date, payment_notes
                        )
                       
                        if success:
                            st.success(f"✅ {message}")
                            st.balloons()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
   
    # Tab 4: Customer Details
    with tab4:
        st.header("📋 Customer Details & Payment History")
       
        customers = tracker.data.get("customers", {})
        if not customers:
            st.warning("⚠️ No customers available.")
        else:
            # Customer selection
            customer_options = {f"{customer['name']} ({customer_id})": customer_id
                             for customer_id, customer in customers.items()}
           
            selected_customer_display = st.selectbox(
                "Select Customer for Details",
                options=list(customer_options.keys()),
                key="customer_details_select"
            )
           
            if selected_customer_display:
                selected_customer_id = customer_options[selected_customer_display]
                customer = customers[selected_customer_id]
               
                # Customer summary
                col1, col2 = st.columns(2)
               
                with col1:
                    st.subheader("👤 Customer Information")
                    st.write(f"**Name:** {customer['name']}")
                    st.write(f"**Customer ID:** {selected_customer_id}")
                    st.write(f"**Phone:** {customer.get('phone', 'N/A')}")
                    st.write(f"**Address:** {customer.get('address', 'N/A')}")
                    st.write(f"**Start Date:** {customer['start_date']}")
               
                with col2:
                    st.subheader("💰 Financial Summary")
                    remaining = customer['principal'] - customer['collected']
                    collection_rate = (customer['collected'] / customer['principal'] * 100)
                   
                    st.metric("Principal Amount", f"₹{customer['principal']:,}")
                    st.metric("Daily Amount", f"₹{customer['daily_amount']:,}")
                    st.metric("Total Collected", f"₹{customer['collected']:,}")
                    st.metric("Remaining Amount", f"₹{remaining:,}")
                    st.metric("Collection Rate", f"{collection_rate:.1f}%")
               
                # Overpayment details (if any)
                overpayment_balance = tracker.get_customer_overpayment_balance(selected_customer_id)
                if overpayment_balance > 0:
                    st.markdown("---")
                    st.subheader("💰 Overpayment Details")
                   
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.success(f"**Available Balance:** ₹{overpayment_balance:,}")
                    with col2:
                        days_covered = overpayment_balance // customer['daily_amount']
                        st.info(f"**Can Cover:** {days_covered} full days")
                    with col3:
                        st.caption("💡 Auto-applied to future collections")
                   
                    # Show overpayment history
                    overpayments = tracker.data.get("overpayments", {}).get(selected_customer_id, [])
                    if overpayments:
                        with st.expander("📋 Overpayment History"):
                            for i, op in enumerate(overpayments):
                                if op["remaining"] > 0:
                                    st.write(f"• **{op['date']}:** ₹{op['amount']:,} (Remaining: ₹{op['remaining']:,})")
               
                # Missed collections
                missed_dates = tracker.get_missed_collections(selected_customer_id)
                if missed_dates:
                    st.markdown("---")
                    st.subheader("🚨 Missed Collections")
                    missed_amount = len(missed_dates) * customer['daily_amount']
                   
                    col1, col2 = st.columns(2)
                    with col1:
                        st.error(f"**Missed Days:** {len(missed_dates)}")
                    with col2:
                        st.error(f"**Total Missed Amount:** ₹{missed_amount:,}")
                   
                    with st.expander("📅 View Missed Dates"):
                        for date in missed_dates[:10]:  # Show first 10
                            st.write(f"• {date}")
                        if len(missed_dates) > 10:
                            st.write(f"... and {len(missed_dates) - 10} more dates")
               
                # Payment history
                st.markdown("---")
                st.subheader("📊 Payment History")
               
                # Fix: Get payments from collections, not payments
                all_collections = tracker.data.get("collections", {})
                payments = [c for c in all_collections.values() if c['customer_id'] == selected_customer_id]
                if payments:
                    # Recent payments summary
                    recent_payments = sorted(payments, key=lambda x: x['date'], reverse=True)[:5]
                   
                    st.write("**Recent Payments:**")
                    for payment in recent_payments:
                        col1, col2, col3 = st.columns([2, 1, 2])
                        with col1:
                            st.write(f"📅 {payment['date']}")
                        with col2:
                            st.write(f"💰 ₹{payment['amount']:,}")
                        with col3:
                            if payment.get('notes'):
                                st.write(f"📝 {payment['notes']}")
                   
                    # Full payment history
                    with st.expander("📋 View All Payments"):
                        payment_data = []
                        for payment in sorted(payments, key=lambda x: x['date'], reverse=True):
                            payment_data.append({
                                "Date": payment['date'],
                                "Amount": f"₹{payment['amount']:,}",
                                "Notes": payment.get('notes', '')
                            })
                       
                        if payment_data:
                            df_payments = pd.DataFrame(payment_data)
                            st.dataframe(df_payments, use_container_width=True)
                   
                    # Payment analytics
                    with st.expander("📈 Payment Analytics"):
                        total_payments = len(payments)
                        avg_payment = sum(p['amount'] for p in payments) / total_payments
                       
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Payments", total_payments)
                        with col2:
                            st.metric("Average Payment", f"₹{avg_payment:,.0f}")
                        with col3:
                            on_time_payments = sum(1 for p in payments if p['amount'] >= customer['daily_amount'])
                            on_time_rate = (on_time_payments / total_payments * 100) if total_payments > 0 else 0
                            st.metric("On-time Rate", f"{on_time_rate:.1f}%")
                else:
                    st.info("📝 No payments recorded yet.")
               
                # Quick actions
                st.markdown("---")
                st.subheader("⚡ Quick Actions")
               
                col1, col2, col3 = st.columns(3)
               
                with col1:
                    if st.button("💳 Collect Today's Payment", key="quick_collect"):
                        success, message = tracker.collect_payment(
                            selected_customer_id,
                            customer['daily_amount'],
                            datetime.now().date()
                        )
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
               
                with col2:
                    if missed_dates and st.button("🔄 Collect Missed Payment", key="quick_missed"):
                        success, message = tracker.collect_payment(
                            selected_customer_id,
                            customer['daily_amount'],
                            datetime.now().date(),
                            f"Missed payment collection"
                        )
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
               
                with col3:
                    if remaining <= 0:
                        st.success("✅ Collection Complete!")
                    else:
                        days_remaining = remaining // customer['daily_amount']
                        st.info(f"📅 {days_remaining} days remaining")
   
    # Tab 5: Reports
    with tab5:
        st.header("📈 Reports & Analytics")
       
        customers = tracker.data.get("customers", {})
        if not customers:
            st.warning("⚠️ No data available for reports.")
        else:
            # Report type selection
            report_type = st.selectbox(
                "Select Report Type",
                ["📊 Collection Summary", "📅 Daily Collections", "🚨 Overdue Report", "💰 Overpayment Report", "📈 Performance Analytics"]
            )
           
            if report_type == "📊 Collection Summary":
                st.subheader("📊 Overall Collection Summary")
               
                # Summary metrics
                total_customers = len(customers)
                total_principal = sum(c['principal'] for c in customers.values())
                total_collected = sum(c['collected'] for c in customers.values())
                total_remaining = total_principal - total_collected
               
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Customers", total_customers)
                with col2:
                    st.metric("Total Principal", f"₹{total_principal:,}")
                with col3:
                    st.metric("Total Collected", f"₹{total_collected:,}")
                with col4:
                    collection_rate = (total_collected / total_principal * 100) if total_principal > 0 else 0
                    st.metric("Collection Rate", f"{collection_rate:.1f}%")
               
                # Customer-wise summary
                st.subheader("👥 Customer-wise Collection Status")
               
                summary_data = []
                for customer_id, customer in customers.items():
                    remaining = customer['principal'] - customer['collected']
                    collection_rate = (customer['collected'] / customer['principal'] * 100)
                    missed_dates = tracker.get_missed_collections(customer_id)
                    overpayment = tracker.get_customer_overpayment_balance(customer_id)
                   
                    status = "✅ COMPLETED" if remaining <= 0 else ("🚨 OVERDUE" if missed_dates else "🟢 ACTIVE")
                   
                    summary_data.append({
                        "Customer": customer['name'],
                        "Principal": f"₹{customer['principal']:,}",
                        "Collected": f"₹{customer['collected']:,}",
                        "Remaining": f"₹{remaining:,}",
                        "Collection %": f"{collection_rate:.1f}%",
                        "Missed Days": len(missed_dates),
                        "Overpayment": f"₹{overpayment:,}",
                        "Status": status
                    })
               
                df_summary = pd.DataFrame(summary_data)
                st.dataframe(df_summary, use_container_width=True)
           
            elif report_type == "📅 Daily Collections":
                st.subheader("📅 Daily Collection Report")
               
                # Date range selection
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input("From Date", value=datetime.now().date() - timedelta(days=30))
                with col2:
                    end_date = st.date_input("To Date", value=datetime.now().date())
               
                # Generate daily report
                daily_collections = {}
                all_collections = tracker.data.get("collections", {})
               
                # Group collections by customer
                customer_collections = {}
                for collection in all_collections.values():
                    customer_id = collection['customer_id']
                    if customer_id not in customer_collections:
                        customer_collections[customer_id] = []
                    customer_collections[customer_id].append(collection)
               
                for customer_id, payments in customer_collections.items():
                    customer_name = customers.get(customer_id, {}).get('name', 'Unknown')
                    for payment in payments:
                        payment_date = datetime.strptime(payment['date'], '%Y-%m-%d').date()
                        if start_date <= payment_date <= end_date:
                            date_str = payment_date.strftime('%Y-%m-%d')
                            if date_str not in daily_collections:
                                daily_collections[date_str] = []
                            daily_collections[date_str].append({
                                'customer': customer_name,
                                'amount': payment['amount'],
                                'notes': payment.get('notes', '')
                            })
               
                if daily_collections:
                    for date_str in sorted(daily_collections.keys(), reverse=True):
                        with st.expander(f"📅 {date_str} - ₹{sum(p['amount'] for p in daily_collections[date_str]):,}"):
                            for payment in daily_collections[date_str]:
                                st.write(f"• **{payment['customer']}**: ₹{payment['amount']:,} {payment['notes']}")
                else:
                    st.info("📝 No collections found for the selected date range.")
           
            elif report_type == "🚨 Overdue Report":
                st.subheader("🚨 Overdue Customers Report")
               
                overdue_data = []
                for customer_id, customer in customers.items():
                    missed_dates = tracker.get_missed_collections(customer_id)
                    if missed_dates:
                        missed_amount = len(missed_dates) * customer['daily_amount']
                        overdue_data.append({
                            "Customer": customer['name'],
                            "Daily Amount": f"₹{customer['daily_amount']:,}",
                            "Missed Days": len(missed_dates),
                            "Missed Amount": f"₹{missed_amount:,}",
                            "Last Payment": "N/A",  # You can enhance this
                            "Phone": customer.get('phone', 'N/A')
                        })
               
                if overdue_data:
                    df_overdue = pd.DataFrame(overdue_data)
                    st.dataframe(df_overdue, use_container_width=True)
                   
                    total_overdue_amount = sum(len(tracker.get_missed_collections(cid)) * customers[cid]['daily_amount']
                                             for cid in customers.keys() if tracker.get_missed_collections(cid))
                    st.error(f"💸 **Total Overdue Amount: ₹{total_overdue_amount:,}**")
                else:
                    st.success("✅ No overdue customers! Great job!")
           
            elif report_type == "💰 Overpayment Report":
                st.subheader("💰 Overpayment Report")
               
                overpayment_data = []
                for customer_id, customer in customers.items():
                    overpayment_balance = tracker.get_customer_overpayment_balance(customer_id)
                    if overpayment_balance > 0:
                        days_covered = overpayment_balance // customer['daily_amount']
                        overpayment_data.append({
                            "Customer": customer['name'],
                            "Daily Amount": f"₹{customer['daily_amount']:,}",
                            "Overpayment Balance": f"₹{overpayment_balance:,}",
                            "Days Covered": f"{days_covered} days",
                            "Phone": customer.get('phone', 'N/A')
                        })
               
                if overpayment_data:
                    df_overpayment = pd.DataFrame(overpayment_data)
                    st.dataframe(df_overpayment, use_container_width=True)
                   
                    total_overpayment = sum(tracker.get_customer_overpayment_balance(cid) for cid in customers.keys())
                    st.success(f"💰 **Total Overpayment Balance: ₹{total_overpayment:,}**")
                    st.info("💡 **Note:** These overpayments will be automatically applied to future collections.")
                else:
                    st.info("📝 No customers have overpayment balances.")
           
            elif report_type == "📈 Performance Analytics":
                st.subheader("📈 Performance Analytics")
               
                # Overall performance metrics
                col1, col2, col3 = st.columns(3)
               
                with col1:
                    # Collection efficiency
                    total_expected = sum(c['principal'] for c in customers.values())
                    total_collected = sum(c['collected'] for c in customers.values())
                    efficiency = (total_collected / total_expected * 100) if total_expected > 0 else 0
                    st.metric("Collection Efficiency", f"{efficiency:.1f}%")
               
                with col2:
                    # Average collection per customer
                    avg_collection = total_collected / len(customers) if customers else 0
                    st.metric("Avg Collection/Customer", f"₹{avg_collection:,.0f}")
               
                with col3:
                    # Completion rate
                    completed_customers = sum(1 for c in customers.values() if c['collected'] >= c['principal'])
                    completion_rate = (completed_customers / len(customers) * 100) if customers else 0
                    st.metric("Completion Rate", f"{completion_rate:.1f}%")
               
                # Customer performance breakdown
                st.subheader("👥 Customer Performance Breakdown")
               
                performance_data = []
                for customer_id, customer in customers.items():
                    # Fix: Get payments from collections, not payments
                    all_collections = tracker.data.get("collections", {})
                    customer_payments = [c for c in all_collections.values() if c['customer_id'] == customer_id]
                    total_payments = len(customer_payments)
                   
                    if total_payments > 0:
                        avg_payment = sum(p['amount'] for p in customer_payments) / total_payments
                        on_time_payments = sum(1 for p in customer_payments if p['amount'] >= customer['daily_amount'])
                        on_time_rate = (on_time_payments / total_payments * 100)
                    else:
                        avg_payment = 0
                        on_time_rate = 0
                   
                    collection_rate = (customer['collected'] / customer['principal'] * 100)
                    missed_days = len(tracker.get_missed_collections(customer_id))
                   
                    performance_data.append({
                        "Customer": customer['name'],
                        "Collection Rate": f"{collection_rate:.1f}%",
                        "Total Payments": total_payments,
                        "Avg Payment": f"₹{avg_payment:,.0f}",
                        "On-time Rate": f"{on_time_rate:.1f}%",
                        "Missed Days": missed_days,
                        "Performance": "🟢 Good" if collection_rate >= 80 and missed_days <= 2 else
                                     ("🟡 Average" if collection_rate >= 60 else "🔴 Poor")
                    })
               
                df_performance = pd.DataFrame(performance_data)
                st.dataframe(df_performance, use_container_width=True)
               
                # Performance insights
                st.subheader("💡 Performance Insights")
               
                good_performers = len([p for p in performance_data if "🟢" in p["Performance"]])
                poor_performers = len([p for p in performance_data if "🔴" in p["Performance"]])
               
                col1, col2 = st.columns(2)
                with col1:
                    st.success(f"🟢 **Good Performers:** {good_performers} customers")
                    st.info("• Collection rate ≥ 80%")
                    st.info("• Missed days ≤ 2")
               
                with col2:
                    if poor_performers > 0:
                        st.error(f"🔴 **Poor Performers:** {poor_performers} customers")
                        st.warning("• Collection rate < 60% OR")
                        st.warning("• Frequent missed payments")
                    else:
                        st.success("🎉 No poor performers!")
               
                # Monthly trends (if you want to add this)
                st.subheader("📊 Collection Trends")
                st.info("💡 **Tip:** Focus on improving collection rates for poor performers and maintaining good relationships with top performers.")

if __name__ == "__main__":
    main()






