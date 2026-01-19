"""
QuickBooks Integration for Financial Data.

Connects to QuickBooks for:
- Syncing actual costs from completed projects
- Pulling material costs for price updates
- Tracking invoices and payments
- Comparing quoted vs actual profitability
"""

import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import json


class ExpenseCategory(str, Enum):
    """Expense categories matching QuickBooks."""
    MATERIALS = "Materials"
    LABOR = "Labor"
    SUBCONTRACTOR = "Subcontractor"
    EQUIPMENT = "Equipment"
    DELIVERY = "Delivery"
    OVERHEAD = "Overhead"
    OTHER = "Other"


@dataclass
class Expense:
    """An expense record from QuickBooks."""
    id: str
    date: str
    amount: float
    category: ExpenseCategory
    vendor: str
    description: str
    project_id: Optional[str] = None
    receipt_url: Optional[str] = None


@dataclass
class Invoice:
    """An invoice from QuickBooks."""
    id: str
    customer_name: str
    project_id: Optional[str] = None
    amount: float
    date_created: str
    date_due: str
    date_paid: Optional[str] = None
    status: str = "Open"  # Open, Paid, Overdue, Void
    line_items: List[Dict] = field(default_factory=list)


@dataclass
class ProjectFinancials:
    """Financial summary for a project."""
    project_id: str
    project_name: str
    quoted_price: float
    invoiced_amount: float
    paid_amount: float
    total_expenses: float
    expenses_by_category: Dict[str, float] = field(default_factory=dict)
    gross_profit: float = 0.0
    gross_margin_pct: float = 0.0
    status: str = "In Progress"


class QuickBooksClient:
    """
    Client for QuickBooks Online API integration.

    Handles:
    - OAuth2 authentication
    - Reading expenses and invoices
    - Syncing project financials
    - Updating cost tables from actual data
    """

    SANDBOX_BASE_URL = "https://sandbox-quickbooks.api.intuit.com/v3"
    PROD_BASE_URL = "https://quickbooks.api.intuit.com/v3"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        realm_id: Optional[str] = None,
        sandbox: bool = True
    ):
        """
        Initialize QuickBooks client.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            access_token: Current access token
            refresh_token: Refresh token for renewal
            realm_id: QuickBooks company ID
            sandbox: Use sandbox environment
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.realm_id = realm_id
        self.base_url = self.SANDBOX_BASE_URL if sandbox else self.PROD_BASE_URL

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Dict:
        """Make an API request to QuickBooks."""
        if not self.access_token or not self.realm_id:
            raise ValueError("QuickBooks credentials not configured")

        url = f"{self.base_url}/company/{self.realm_id}/{endpoint}"

        response = requests.request(
            method,
            url,
            headers=self._get_headers(),
            json=data,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def test_connection(self) -> Dict[str, Any]:
        """Test API connection and return company info."""
        try:
            result = self._api_request("GET", "companyinfo/" + self.realm_id)
            company = result.get("CompanyInfo", {})
            return {
                "connected": True,
                "company_name": company.get("CompanyName"),
                "country": company.get("Country"),
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }

    def get_expenses(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[Expense]:
        """
        Get expenses/purchases from QuickBooks.

        Args:
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date
            project_id: Filter by project/class

        Returns:
            List of expenses
        """
        # Build query
        query = "SELECT * FROM Purchase"
        conditions = []

        if start_date:
            conditions.append(f"TxnDate >= '{start_date}'")
        if end_date:
            conditions.append(f"TxnDate <= '{end_date}'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        result = self._api_request(
            "GET",
            f"query?query={query}&minorversion=65"
        )

        expenses = []
        for purchase in result.get("QueryResponse", {}).get("Purchase", []):
            # Map to expense
            expense = Expense(
                id=purchase.get("Id"),
                date=purchase.get("TxnDate"),
                amount=float(purchase.get("TotalAmt", 0)),
                category=self._map_category(purchase.get("AccountRef", {}).get("name", "")),
                vendor=purchase.get("EntityRef", {}).get("name", "Unknown"),
                description=purchase.get("PrivateNote", ""),
                project_id=self._extract_project_id(purchase),
            )
            expenses.append(expense)

        return expenses

    def get_invoices(
        self,
        customer_name: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Invoice]:
        """
        Get invoices from QuickBooks.

        Args:
            customer_name: Filter by customer
            status: Filter by status

        Returns:
            List of invoices
        """
        query = "SELECT * FROM Invoice"
        conditions = []

        if customer_name:
            conditions.append(f"CustomerRef.name = '{customer_name}'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        result = self._api_request(
            "GET",
            f"query?query={query}&minorversion=65"
        )

        invoices = []
        for inv in result.get("QueryResponse", {}).get("Invoice", []):
            invoice = Invoice(
                id=inv.get("Id"),
                customer_name=inv.get("CustomerRef", {}).get("name", "Unknown"),
                amount=float(inv.get("TotalAmt", 0)),
                date_created=inv.get("TxnDate"),
                date_due=inv.get("DueDate"),
                status=self._map_invoice_status(inv),
                line_items=inv.get("Line", []),
            )
            invoices.append(invoice)

        return invoices

    def get_project_financials(self, project_id: str) -> ProjectFinancials:
        """
        Get complete financial summary for a project.

        Args:
            project_id: Project/job ID

        Returns:
            ProjectFinancials summary
        """
        # Get expenses for project
        expenses = self.get_expenses(project_id=project_id)

        # Aggregate by category
        expenses_by_category = {}
        total_expenses = 0
        for exp in expenses:
            cat = exp.category.value
            expenses_by_category[cat] = expenses_by_category.get(cat, 0) + exp.amount
            total_expenses += exp.amount

        # Get invoices (would need project mapping)
        # For now, return partial data
        financials = ProjectFinancials(
            project_id=project_id,
            project_name=project_id,  # Would lookup
            quoted_price=0,  # Would lookup
            invoiced_amount=0,
            paid_amount=0,
            total_expenses=total_expenses,
            expenses_by_category=expenses_by_category,
        )

        # Calculate margins
        if financials.invoiced_amount > 0:
            financials.gross_profit = financials.invoiced_amount - total_expenses
            financials.gross_margin_pct = (financials.gross_profit / financials.invoiced_amount) * 100

        return financials

    def _map_category(self, account_name: str) -> ExpenseCategory:
        """Map QuickBooks account name to expense category."""
        name_lower = account_name.lower()
        if 'material' in name_lower or 'supplies' in name_lower:
            return ExpenseCategory.MATERIALS
        elif 'labor' in name_lower or 'wage' in name_lower or 'payroll' in name_lower:
            return ExpenseCategory.LABOR
        elif 'subcontract' in name_lower:
            return ExpenseCategory.SUBCONTRACTOR
        elif 'equipment' in name_lower or 'tool' in name_lower:
            return ExpenseCategory.EQUIPMENT
        elif 'delivery' in name_lower or 'shipping' in name_lower or 'freight' in name_lower:
            return ExpenseCategory.DELIVERY
        elif 'overhead' in name_lower or 'rent' in name_lower or 'utilit' in name_lower:
            return ExpenseCategory.OVERHEAD
        else:
            return ExpenseCategory.OTHER

    def _map_invoice_status(self, invoice: Dict) -> str:
        """Map QuickBooks invoice to status."""
        balance = float(invoice.get("Balance", 0))
        if balance == 0:
            return "Paid"
        due_date = invoice.get("DueDate")
        if due_date and due_date < date.today().isoformat():
            return "Overdue"
        return "Open"

    def _extract_project_id(self, purchase: Dict) -> Optional[str]:
        """Extract project/class ID from purchase."""
        # QuickBooks uses "Class" for job/project tracking
        class_ref = purchase.get("ClassRef", {})
        return class_ref.get("value") if class_ref else None

    def sync_material_costs(self) -> Dict[str, float]:
        """
        Analyze recent material purchases to update cost tables.

        Returns:
            Dictionary of material type -> average cost
        """
        # Get recent material expenses
        today = date.today()
        start = date(today.year, today.month - 3 if today.month > 3 else 1, 1)

        expenses = self.get_expenses(
            start_date=start.isoformat(),
            end_date=today.isoformat()
        )

        # Filter to materials
        material_expenses = [e for e in expenses if e.category == ExpenseCategory.MATERIALS]

        # Aggregate by vendor/description (simplified)
        material_costs = {}
        for exp in material_expenses:
            key = exp.vendor.lower()
            if key not in material_costs:
                material_costs[key] = []
            material_costs[key].append(exp.amount)

        # Calculate averages
        averages = {k: sum(v) / len(v) for k, v in material_costs.items()}

        return averages
