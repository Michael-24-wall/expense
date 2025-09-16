from datetime import datetime, timedelta

class ExpenseTracker:
    def __init__(self):
        self.expenses = []
        self.subscriptions = []
        self.categories = ["Food", "Transport", "Entertainment", "Utilities", "Shopping", "Healthcare", "Other"]
        self.subscription_categories = ["Streaming", "Software", "Gaming", "Memberships", "Other"]
        self.load_data()
        self.setup_event_listeners()
        self.show_page('dashboard')
        
    def setup_event_listeners(self):
        # Navigation links
        document.getElementById("nav-dashboard").addEventListener("click", create_proxy(lambda e: self.show_page('dashboard')))
        document.getElementById("nav-expenses").addEventListener("click", create_proxy(lambda e: self.show_page('expenses')))
        document.getElementById("nav-subscriptions").addEventListener("click", create_proxy(lambda e: self.show_page('subscriptions')))
        document.getElementById("nav-reports").addEventListener("click", create_proxy(lambda e: self.show_page('reports')))
        
        # Expense form
        document.getElementById("add-expense-btn").addEventListener("click", create_proxy(self.add_expense))
        
        # Subscription form
        document.getElementById("add-subscription-btn").addEventListener("click", create_proxy(self.add_subscription))
        
        # Filter buttons
        document.getElementById("filter-expenses").addEventListener("click", create_proxy(self.filter_expenses))
        document.getElementById("filter-subscriptions").addEventListener("click", create_proxy(self.filter_subscriptions))
        
        # Report generation
        document.getElementById("generate-report").addEventListener("click", create_proxy(self.generate_report))
    
    def show_page(self, page_id):
        # Hide all pages
        pages = document.querySelectorAll(".page")
        for page in pages:
            page.style.display = "none"
        
        document.getElementById(f"{page_id}-page").style.display = "block"
        
        nav_links = document.querySelectorAll(".nav-link")
        for link in nav_links:
            link.classList.remove("active")
        document.getElementById(f"nav-{page_id}").classList.add("active")
        
        if page_id == 'dashboard':
            self.update_dashboard()
        elif page_id == 'expenses':
            self.render_expenses_list()
        elif page_id == 'subscriptions':
            self.render_subscriptions_list()
    
    def add_expense(self, event):
        event.preventDefault()
        description = document.getElementById("expense-description").value
        amount = float(document.getElementById("expense-amount").value)
        category = document.getElementById("expense-category").value
        date = document.getElementById("expense-date").value or datetime.now().strftime("%Y-%m-%d")
        
        expense = {
            "id": len(self.expenses) + 1,
            "description": description,
            "amount": amount,
            "category": category,
            "date": date
        }
        
        self.expenses.append(expense)
        self.save_data()
        self.render_expenses_list()
        self.update_dashboard()
        
        document.getElementById("expense-form").reset()
        
        
        self.show_notification("Expense added successfully!")
    
    def add_subscription(self, event):
        event.preventDefault()
        name = document.getElementById("subscription-name").value
        amount = float(document.getElementById("subscription-amount").value)
        category = document.getElementById("subscription-category").value
        start_date = document.getElementById("subscription-start-date").value
        billing_cycle = document.getElementById("subscription-billing-cycle").value
        
        subscription = {
            "id": len(self.subscriptions) + 1,
            "name": name,
            "amount": amount,
            "category": category,
            "start_date": start_date,
            "billing_cycle": billing_cycle,
            "next_payment": self.calculate_next_payment(start_date, billing_cycle)
        }
        
        self.subscriptions.append(subscription)
        self.save_data()
        self.render_subscriptions_list()
        self.update_dashboard()
        
        document.getElementById("subscription-form").reset()
        
        self.show_notification("Subscription added successfully!")
    
    def calculate_next_payment(self, start_date, billing_cycle):
        start = datetime.strptime(start_date, "%Y-%m-%d")
        today = datetime.now()
        
        if billing_cycle == "monthly":
            next_date = start
            while next_date < today:
                next_date += timedelta(days=30)  
            return next_date.strftime("%Y-%m-%d")
        elif billing_cycle == "yearly":
            next_date = start
            while next_date < today:
                next_date += timedelta(days=365)  
            return next_date.strftime("%Y-%m-%d")
        else:  
            next_date = start
            while next_date < today:
                next_date += timedelta(weeks=1)
            return next_date.strftime("%Y-%m-%d")
    
    def render_expenses_list(self):
        container = document.getElementById("expenses-list")
        container.innerHTML = ""
        
        filtered_expenses = self.expenses
        category_filter = document.getElementById("expense-category-filter").value
        date_filter = document.getElementById("expense-date-filter").value
        
        if category_filter:
            filtered_expenses = [e for e in filtered_expenses if e["category"] == category_filter]
        
        if date_filter:
            filtered_expenses = [e for e in filtered_expenses if e["date"].startswith(date_filter)]
        
        filtered_expenses.sort(key=lambda x: x["date"], reverse=True)
        
        if not filtered_expenses:
            container.innerHTML = "<tr><td colspan='5' class='no-data'>No expenses found</td></tr>"
            return
        
        for expense in filtered_expenses:
            row = document.createElement("tr")
            row.innerHTML = f"""
                <td>{expense['description']}</td>
                <td>${expense['amount']:.2f}</td>
                <td>{expense['category']}</td>
                <td>{expense['date']}</td>
                <td>
                    <button class="btn btn-sm btn-danger" data-id="{expense['id']}">Delete</button>
                </td>
            """
            container.appendChild(row)
        
        delete_buttons = document.querySelectorAll("#expenses-list .btn-danger")
        for button in delete_buttons:
            button.addEventListener("click", create_proxy(self.delete_expense))
    
    def render_subscriptions_list(self):
        container = document.getElementById("subscriptions-list")
        container.innerHTML = ""
        
        
        filtered_subscriptions = self.subscriptions
        category_filter = document.getElementById("subscription-category-filter").value
        
        if category_filter:
            filtered_subscriptions = [s for s in filtered_subscriptions if s["category"] == category_filter]
        
        if not filtered_subscriptions:
            container.innerHTML = "<tr><td colspan='6' class='no-data'>No subscriptions found</td></tr>"
            return
        
        for sub in filtered_subscriptions:
            row = document.createElement("tr")
            row.innerHTML = f"""
                <td>{sub['name']}</td>
                <td>${sub['amount']:.2f}</td>
                <td>{sub['category']}</td>
                <td>{sub['billing_cycle']}</td>
                <td>{sub['next_payment']}</td>
                <td>
                    <button class="btn btn-sm btn-danger" data-id="{sub['id']}">Delete</button>
                </td>
            """
            container.appendChild(row)
        
        # Add event listeners to delete buttons
        delete_buttons = document.querySelectorAll("#subscriptions-list .btn-danger")
        for button in delete_buttons:
            button.addEventListener("click", create_proxy(self.delete_subscription))
    
    def delete_expense(self, event):
        expense_id = int(event.target.getAttribute("data-id"))
        self.expenses = [e for e in self.expenses if e["id"] != expense_id]
        self.save_data()
        self.render_expenses_list()
        self.update_dashboard()
        self.show_notification("Expense deleted successfully!")
    
    def delete_subscription(self, event):
        sub_id = int(event.target.getAttribute("data-id"))
        self.subscriptions = [s for s in self.subscriptions if s["id"] != sub_id]
        self.save_data()
        self.render_subscriptions_list()
        self.update_dashboard()
        self.show_notification("Subscription deleted successfully!")
    
    def update_dashboard(self):
        # Calculate total expenses
        total_expenses = sum(e["amount"] for e in self.expenses)
        document.getElementById("total-expenses").textContent = f"${total_expenses:.2f}"
        
        # Calculate monthly expenses
        current_month = datetime.now().strftime("%Y-%m")
        monthly_expenses = sum(
            e["amount"] for e in self.expenses 
            if e["date"].startswith(current_month)
        )
        document.getElementById("monthly-expenses").textContent = f"${monthly_expenses:.2f}"
        
        # Calculate subscription costs
        total_subscriptions = sum(s["amount"] for s in self.subscriptions)
        document.getElementById("total-subscriptions").textContent = f"${total_subscriptions:.2f}"
        
        # Monthly subscription cost
        monthly_subs = 0
        for sub in self.subscriptions:
            if sub["billing_cycle"] == "monthly":
                monthly_subs += sub["amount"]
            elif sub["billing_cycle"] == "yearly":
                monthly_subs += sub["amount"] / 12
            else:  
                monthly_subs += sub["amount"] * 4
        
        document.getElementById("monthly-subscriptions").textContent = f"${monthly_subs:.2f}"
        
        upcoming_subs = []
        for sub in self.subscriptions:
            next_payment = datetime.strptime(sub["next_payment"], "%Y-%m-%d")
            if (next_payment - datetime.now()).days <= 7:
                upcoming_subs.append(sub)
        
        container = document.getElementById("upcoming-subscriptions")
        container.innerHTML = ""
        
        if not upcoming_subs:
            container.innerHTML = "<li class='list-group-item'>No upcoming subscriptions</li>"
        else:
            for sub in upcoming_subs:
                item = document.createElement("li")
                item.className = "list-group-item"
                item.innerHTML = f"""
                    <div class="d-flex justify-content-between">
                        <span>{sub['name']}</span>
                        <span>${sub['amount']:.2f} on {sub['next_payment']}</span>
                    </div>
                """
                container.appendChild(item)
    
    def filter_expenses(self, event):
        event.preventDefault()
        self.render_expenses_list()
    
    def filter_subscriptions(self, event):
        event.preventDefault()
        self.render_subscriptions_list()
    
    def generate_report(self, event):
        event.preventDefault()
        
        # Get date range
        start_date = document.getElementById("report-start-date").value
        end_date = document.getElementById("report-end-date").value
        
        if not start_date or not end_date:
            self.show_notification("Please select both start and end dates", "warning")
            return
        
        # Filter expenses by date range
        filtered_expenses = [
            e for e in self.expenses 
            if start_date <= e["date"] <= end_date
        ]
        
        if not filtered_expenses:
            self.show_notification("No expenses found in the selected date range", "warning")
            return
        
        # Calculate category breakdown
        categories = {}
        for expense in filtered_expenses:
            if expense["category"] not in categories:
                categories[expense["category"]] = 0
            categories[expense["category"]] += expense["amount"]
        
        # Generate report HTML
        report_html = "<h4>Expense Report</h4>"
        report_html += f"<p>Date Range: {start_date} to {end_date}</p>"
        report_html += "<h5>Category Breakdown</h5><ul>"
        
        for category, amount in categories.items():
            report_html += f"<li>{category}: ${amount:.2f}</li>"
        
        report_html += "</ul>"
        
        # Show report
        document.getElementById("report-results").innerHTML = report_html
        self.show_notification("Report generated successfully!")
    
    def show_notification(self, message, type="success"):
        notification = document.getElementById("notification")
        notification.textContent = message
        notification.className = f"alert alert-{type} show"
        
        # Hide after 3 seconds
        window.setTimeout(create_proxy(lambda: notification.classList.remove("show")), 3000)
    
    def save_data(self):
        localStorage.setItem("expenses", js.JSON.stringify(self.expenses))
        localStorage.setItem("subscriptions", js.JSON.stringify(self.subscriptions))
    
    def load_data(self):
        try:
            expenses_data = localStorage.getItem("expenses")
            subscriptions_data = localStorage.getItem("subscriptions")
            
            if expenses_data:
                self.expenses = js.JSON.parse(expenses_data)
            if subscriptions_data:
                self.subscriptions = js.JSON.parse(subscriptions_data)
        except:
            self.expenses = []
            self.subscriptions = []

# Initialize the app when the page loads
def main():
    tracker = ExpenseTracker()


if __name__ == "__main__":
    main()