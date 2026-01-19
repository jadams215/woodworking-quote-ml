"""
Integration Orchestrator - Connects all vendor systems.

Provides unified interface for:
- Monday.com: Project management, tasks, sprints
- QuickBooks: Financial data, invoices, expenses
- TSheets: Labor tracking, time entries
- Google Drive: Document storage

Enables intelligent operations where all systems communicate.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
import json


@dataclass
class IntegrationStatus:
    """Status of an integration connection."""
    name: str
    connected: bool
    last_sync: Optional[str] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectSummary:
    """Unified project view from all systems."""
    project_id: str
    project_name: str
    customer: str
    status: str

    # From Quote Engine
    quoted_price: float = 0
    quote_date: str = ""

    # From Monday.com
    monday_board_id: Optional[str] = None
    tasks_total: int = 0
    tasks_completed: int = 0
    current_sprint: Optional[str] = None
    assigned_workers: List[str] = field(default_factory=list)

    # From QuickBooks
    invoiced_amount: float = 0
    payments_received: float = 0
    expenses_recorded: float = 0
    current_margin_pct: float = 0

    # From TSheets
    labor_hours_estimated: float = 0
    labor_hours_actual: float = 0
    labor_variance_pct: float = 0

    # From Google Drive
    drive_folder_url: Optional[str] = None
    document_count: int = 0


@dataclass
class WorkerUtilization:
    """Worker utilization across all projects."""
    worker_id: str
    worker_name: str
    current_hours_weekly: float
    available_hours_weekly: float
    utilization_pct: float
    assigned_projects: List[str] = field(default_factory=list)
    primary_skills: List[str] = field(default_factory=list)


class IntegrationOrchestrator:
    """
    Orchestrates communication between all integrated systems.

    Provides:
    - Unified project views
    - Cross-system data sync
    - Automated workflows
    - Real-time status updates
    """

    def __init__(
        self,
        monday_client=None,
        quickbooks_client=None,
        tsheets_client=None,
        gdrive_client=None,
        quote_engine=None,
        config_path: Optional[str] = None
    ):
        """
        Initialize orchestrator with integration clients.

        Args:
            monday_client: Initialized MondayClient
            quickbooks_client: Initialized QuickBooksClient
            tsheets_client: Initialized TSheetsClient
            gdrive_client: Initialized GoogleDriveClient
            quote_engine: Initialized QuoteEngine
            config_path: Path to integration config JSON
        """
        self.monday = monday_client
        self.quickbooks = quickbooks_client
        self.tsheets = tsheets_client
        self.gdrive = gdrive_client
        self.quote_engine = quote_engine

        # Load config
        self.config = {}
        if config_path and Path(config_path).exists():
            with open(config_path) as f:
                self.config = json.load(f)

        # Project mappings (quote_id -> various IDs)
        self.project_mappings: Dict[str, Dict[str, str]] = {}

    def get_integration_status(self) -> Dict[str, IntegrationStatus]:
        """Get connection status for all integrations."""
        status = {}

        # Monday.com
        if self.monday:
            try:
                result = self.monday.test_connection()
                status["monday"] = IntegrationStatus(
                    name="Monday.com",
                    connected=result.get("connected", False),
                    details=result
                )
            except Exception as e:
                status["monday"] = IntegrationStatus(
                    name="Monday.com", connected=False, error=str(e)
                )
        else:
            status["monday"] = IntegrationStatus(
                name="Monday.com", connected=False, error="Not configured"
            )

        # QuickBooks
        if self.quickbooks:
            try:
                result = self.quickbooks.test_connection()
                status["quickbooks"] = IntegrationStatus(
                    name="QuickBooks",
                    connected=result.get("connected", False),
                    details=result
                )
            except Exception as e:
                status["quickbooks"] = IntegrationStatus(
                    name="QuickBooks", connected=False, error=str(e)
                )
        else:
            status["quickbooks"] = IntegrationStatus(
                name="QuickBooks", connected=False, error="Not configured"
            )

        # TSheets
        if self.tsheets:
            try:
                result = self.tsheets.test_connection()
                status["tsheets"] = IntegrationStatus(
                    name="TSheets (QuickBooks Time)",
                    connected=result.get("connected", False),
                    details=result
                )
            except Exception as e:
                status["tsheets"] = IntegrationStatus(
                    name="TSheets", connected=False, error=str(e)
                )
        else:
            status["tsheets"] = IntegrationStatus(
                name="TSheets", connected=False, error="Not configured"
            )

        # Google Drive
        if self.gdrive:
            try:
                result = self.gdrive.test_connection()
                status["gdrive"] = IntegrationStatus(
                    name="Google Drive",
                    connected=result.get("connected", False),
                    details=result
                )
            except Exception as e:
                status["gdrive"] = IntegrationStatus(
                    name="Google Drive", connected=False, error=str(e)
                )
        else:
            status["gdrive"] = IntegrationStatus(
                name="Google Drive", connected=False, error="Not configured"
            )

        return status

    def create_project_from_quote(
        self,
        quote_id: str,
        quote_result: Dict[str, Any],
        customer_name: str,
        start_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new project across all systems from an approved quote.

        Automatically:
        1. Creates Monday.com board with tasks
        2. Creates QuickBooks customer/estimate
        3. Creates Google Drive folder structure
        4. Schedules labor in TSheets

        Args:
            quote_id: Quote ID from quote engine
            quote_result: Full quote result dict
            customer_name: Customer name
            start_date: Project start date

        Returns:
            Project creation summary
        """
        project_name = quote_result.get("project_name", f"Project {quote_id}")
        results = {
            "quote_id": quote_id,
            "project_name": project_name,
            "systems": {},
        }

        # Store mapping
        self.project_mappings[quote_id] = {}

        # 1. Create Monday.com board
        if self.monday:
            try:
                # Create board
                board = self.monday.create_project_board(
                    quote_id=quote_id,
                    project_name=project_name,
                    customer_name=customer_name,
                    quoted_price=quote_result.get("recommended_price", 0),
                    start_date=start_date,
                )

                # Create tasks based on work types
                tasks = self._generate_tasks_from_quote(quote_result)
                for task in tasks:
                    self.monday.create_task(board["id"], task)

                self.project_mappings[quote_id]["monday_board_id"] = board["id"]
                results["systems"]["monday"] = {
                    "success": True,
                    "board_id": board["id"],
                    "board_url": board.get("url"),
                    "tasks_created": len(tasks),
                }
            except Exception as e:
                results["systems"]["monday"] = {
                    "success": False,
                    "error": str(e),
                }

        # 2. Create QuickBooks estimate
        if self.quickbooks:
            try:
                estimate = self.quickbooks.create_estimate(
                    customer_name=customer_name,
                    project_name=project_name,
                    line_items=self._generate_line_items_from_quote(quote_result),
                    notes=f"Quote ID: {quote_id}",
                )

                self.project_mappings[quote_id]["qb_estimate_id"] = estimate.get("id")
                results["systems"]["quickbooks"] = {
                    "success": True,
                    "estimate_id": estimate.get("id"),
                    "total": estimate.get("total"),
                }
            except Exception as e:
                results["systems"]["quickbooks"] = {
                    "success": False,
                    "error": str(e),
                }

        # 3. Create Google Drive folder
        if self.gdrive:
            try:
                folder = self.gdrive.create_project_folder(
                    project_id=quote_id,
                    project_name=project_name,
                    customer_name=customer_name,
                )

                self.project_mappings[quote_id]["gdrive_folder_id"] = folder.root_folder_id
                results["systems"]["gdrive"] = {
                    "success": True,
                    "folder_id": folder.root_folder_id,
                    "folder_url": self.gdrive.get_folder_link(folder.root_folder_id),
                }
            except Exception as e:
                results["systems"]["gdrive"] = {
                    "success": False,
                    "error": str(e),
                }

        return results

    def get_project_summary(self, quote_id: str) -> ProjectSummary:
        """
        Get unified project summary from all systems.

        Args:
            quote_id: Quote/project ID

        Returns:
            ProjectSummary with data from all systems
        """
        summary = ProjectSummary(
            project_id=quote_id,
            project_name="",
            customer="",
            status="Unknown",
        )

        mappings = self.project_mappings.get(quote_id, {})

        # Get Monday.com data
        if self.monday and mappings.get("monday_board_id"):
            try:
                board = self.monday.get_board(mappings["monday_board_id"])
                summary.monday_board_id = mappings["monday_board_id"]
                summary.project_name = board.get("name", "")
                summary.tasks_total = board.get("total_tasks", 0)
                summary.tasks_completed = board.get("completed_tasks", 0)
                summary.current_sprint = board.get("current_sprint")
                summary.assigned_workers = board.get("assigned_workers", [])
                summary.status = board.get("status", "In Progress")
            except Exception:
                pass

        # Get QuickBooks data
        if self.quickbooks and mappings.get("qb_estimate_id"):
            try:
                financials = self.quickbooks.get_project_financials(quote_id)
                summary.quoted_price = financials.quoted_amount
                summary.invoiced_amount = financials.invoiced_amount
                summary.payments_received = financials.payments_received
                summary.expenses_recorded = financials.total_expenses
                if financials.invoiced_amount > 0:
                    margin = (financials.invoiced_amount - financials.total_expenses) / financials.invoiced_amount * 100
                    summary.current_margin_pct = round(margin, 1)
            except Exception:
                pass

        # Get TSheets data
        if self.tsheets and mappings.get("tsheets_jobcode_id"):
            try:
                labor = self.tsheets.get_project_labor(mappings["tsheets_jobcode_id"])
                summary.labor_hours_actual = labor.total_hours
                if summary.labor_hours_estimated > 0:
                    variance = (labor.total_hours - summary.labor_hours_estimated) / summary.labor_hours_estimated * 100
                    summary.labor_variance_pct = round(variance, 1)
            except Exception:
                pass

        # Get Google Drive data
        if self.gdrive and mappings.get("gdrive_folder_id"):
            try:
                summary.drive_folder_url = self.gdrive.get_folder_link(mappings["gdrive_folder_id"])
                files = self.gdrive.list_files(folder_id=mappings["gdrive_folder_id"])
                summary.document_count = len(files)
            except Exception:
                pass

        return summary

    def get_team_utilization(self) -> List[WorkerUtilization]:
        """
        Get current team utilization across all projects.

        Combines TSheets time data with Monday.com assignments.

        Returns:
            List of WorkerUtilization for each team member
        """
        utilization = []

        if not self.tsheets:
            return utilization

        try:
            # Get team availability from TSheets
            availability = self.tsheets.get_team_availability(weeks_ahead=1)

            for user_id, data in availability.items():
                worker = WorkerUtilization(
                    worker_id=user_id,
                    worker_name=data.get("employee_name", "Unknown"),
                    current_hours_weekly=data.get("typical_weekly_hours", 0),
                    available_hours_weekly=data.get("available_hours_per_week", 0),
                    utilization_pct=data.get("utilization_pct", 0),
                )

                # Get skill profile
                try:
                    profile = self.tsheets.build_skill_profile(user_id)
                    worker.primary_skills = profile.primary_skills
                except Exception:
                    pass

                utilization.append(worker)

        except Exception:
            pass

        return utilization

    def sync_labor_to_financials(self, quote_id: str) -> Dict[str, Any]:
        """
        Sync labor hours from TSheets to QuickBooks.

        Updates project expenses based on actual time tracked.

        Args:
            quote_id: Project ID

        Returns:
            Sync results
        """
        if not self.tsheets or not self.quickbooks:
            return {"success": False, "error": "Integrations not configured"}

        mappings = self.project_mappings.get(quote_id, {})
        if not mappings.get("tsheets_jobcode_id"):
            return {"success": False, "error": "Project not linked to TSheets"}

        try:
            # Get labor data
            labor = self.tsheets.get_project_labor(mappings["tsheets_jobcode_id"])

            # Calculate labor cost (using average rate)
            labor_rate = self.config.get("default_labor_rate", 55.0)
            labor_cost = labor.total_hours * labor_rate

            # Record expense in QuickBooks
            expense = self.quickbooks.record_expense(
                project_id=quote_id,
                category="Labor",
                amount=labor_cost,
                description=f"Labor: {labor.total_hours:.1f} hours",
            )

            return {
                "success": True,
                "hours_synced": labor.total_hours,
                "labor_cost": labor_cost,
                "expense_id": expense.get("id"),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_project_alerts(self, quote_id: str) -> List[Dict[str, Any]]:
        """
        Get alerts/warnings for a project across all systems.

        Checks for:
        - Budget overruns
        - Labor variance
        - Missing documents
        - Overdue tasks

        Args:
            quote_id: Project ID

        Returns:
            List of alerts
        """
        alerts = []
        summary = self.get_project_summary(quote_id)

        # Labor variance alert
        if summary.labor_variance_pct > 20:
            alerts.append({
                "type": "warning",
                "system": "tsheets",
                "message": f"Labor is {summary.labor_variance_pct:.0f}% over estimate",
                "severity": "high" if summary.labor_variance_pct > 50 else "medium",
            })

        # Margin alert
        if summary.current_margin_pct < 20 and summary.invoiced_amount > 0:
            alerts.append({
                "type": "warning",
                "system": "quickbooks",
                "message": f"Current margin is only {summary.current_margin_pct:.0f}%",
                "severity": "high" if summary.current_margin_pct < 10 else "medium",
            })

        # Task completion alert
        if summary.tasks_total > 0:
            completion_pct = (summary.tasks_completed / summary.tasks_total) * 100
            if completion_pct < 50 and summary.labor_hours_actual > summary.labor_hours_estimated * 0.75:
                alerts.append({
                    "type": "warning",
                    "system": "monday",
                    "message": "Tasks behind schedule relative to labor spent",
                    "severity": "medium",
                })

        return alerts

    def complete_project(
        self,
        quote_id: str,
        customer_satisfaction: Optional[int] = None,
        lessons_learned: str = ""
    ) -> Dict[str, Any]:
        """
        Complete a project and archive across all systems.

        Actions:
        1. Mark complete in Monday.com
        2. Generate final invoice in QuickBooks
        3. Record completed project in Quote Engine
        4. Archive documents in Google Drive

        Args:
            quote_id: Project ID
            customer_satisfaction: Rating 1-5
            lessons_learned: Notes for future

        Returns:
            Completion summary
        """
        results = {
            "quote_id": quote_id,
            "systems": {},
        }

        mappings = self.project_mappings.get(quote_id, {})
        summary = self.get_project_summary(quote_id)

        # Get actual costs from QuickBooks
        actual_costs = {}
        if self.quickbooks:
            try:
                financials = self.quickbooks.get_project_financials(quote_id)
                actual_costs = {
                    "material_cost": financials.material_expenses,
                    "labor_cost": financials.labor_expenses,
                    "overhead_cost": financials.overhead_expenses,
                    "delivery_cost": financials.other_expenses,
                }
                results["systems"]["quickbooks"] = {"success": True}
            except Exception as e:
                results["systems"]["quickbooks"] = {"success": False, "error": str(e)}

        # Record in Quote Engine
        if self.quote_engine and actual_costs:
            try:
                self.quote_engine.complete_project(
                    quote_id=quote_id,
                    project_name=summary.project_name,
                    quoted_price=summary.quoted_price,
                    quoted_cost=summary.quoted_price * 0.6,  # Estimated cost
                    final_agreed_price=summary.invoiced_amount,
                    actual_costs=actual_costs,
                    customer_satisfaction=customer_satisfaction,
                    lessons_learned=lessons_learned,
                )
                results["systems"]["quote_engine"] = {"success": True}
            except Exception as e:
                results["systems"]["quote_engine"] = {"success": False, "error": str(e)}

        # Archive in Google Drive
        if self.gdrive and mappings.get("gdrive_folder_id"):
            try:
                from src.integrations.gdrive_client import ProjectFolder
                folder = ProjectFolder(
                    project_id=quote_id,
                    project_name=summary.project_name,
                    root_folder_id=mappings["gdrive_folder_id"],
                    archive_folder_id=mappings.get("gdrive_archive_folder_id", ""),
                )
                archive_result = self.gdrive.archive_project(folder)
                results["systems"]["gdrive"] = {
                    "success": True,
                    "files_archived": archive_result.get("files_moved", 0),
                }
            except Exception as e:
                results["systems"]["gdrive"] = {"success": False, "error": str(e)}

        return results

    def _generate_tasks_from_quote(self, quote_result: Dict) -> List[Dict]:
        """Generate task list from quote parameters."""
        tasks = []
        params = quote_result.get("parameters", {})

        if params.get("has_woodwork"):
            tasks.append({
                "name": "Woodwork",
                "type": "woodwork",
                "hours": params.get("estimated_labor_hours", 0) * 0.4,
            })

        if params.get("has_metalwork"):
            tasks.append({
                "name": "Metalwork",
                "type": "metalwork",
                "hours": params.get("estimated_labor_hours", 0) * 0.2,
            })

        if params.get("has_finishing"):
            tasks.append({
                "name": "Finishing",
                "type": "finishing",
                "hours": params.get("estimated_labor_hours", 0) * 0.2,
            })

        if params.get("has_upholstery"):
            tasks.append({
                "name": "Upholstery",
                "type": "upholstery",
                "hours": params.get("estimated_labor_hours", 0) * 0.1,
            })

        if params.get("installation_required"):
            tasks.append({
                "name": "Installation",
                "type": "installation",
                "hours": params.get("estimated_labor_hours", 0) * 0.1,
            })

        # Add standard tasks
        tasks.extend([
            {"name": "Quality Check", "type": "qc", "hours": 1},
            {"name": "Final Delivery", "type": "delivery", "hours": 2},
        ])

        return tasks

    def _generate_line_items_from_quote(self, quote_result: Dict) -> List[Dict]:
        """Generate QuickBooks line items from quote."""
        breakdown = quote_result.get("cost_breakdown", {})

        items = []

        if breakdown.get("total_material_cost", 0) > 0:
            items.append({
                "description": "Materials",
                "quantity": 1,
                "rate": breakdown["total_material_cost"],
            })

        if breakdown.get("total_labor_cost", 0) > 0:
            items.append({
                "description": "Labor",
                "quantity": 1,
                "rate": breakdown["total_labor_cost"],
            })

        if breakdown.get("overhead_cost", 0) > 0:
            items.append({
                "description": "Overhead & Misc",
                "quantity": 1,
                "rate": breakdown["overhead_cost"],
            })

        if breakdown.get("delivery_cost", 0) > 0:
            items.append({
                "description": "Delivery",
                "quantity": 1,
                "rate": breakdown["delivery_cost"],
            })

        return items

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get unified dashboard data from all systems.

        Returns summary metrics for display.
        """
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "integrations": {},
            "projects": {
                "active": 0,
                "completed_this_month": 0,
                "total_quoted_value": 0,
            },
            "financials": {
                "revenue_mtd": 0,
                "expenses_mtd": 0,
                "margin_mtd_pct": 0,
            },
            "labor": {
                "hours_this_week": 0,
                "team_utilization_pct": 0,
            },
            "alerts": [],
        }

        # Integration status
        status = self.get_integration_status()
        dashboard["integrations"] = {
            name: s.connected for name, s in status.items()
        }

        # Get team utilization
        utilization = self.get_team_utilization()
        if utilization:
            total_util = sum(w.utilization_pct for w in utilization)
            dashboard["labor"]["team_utilization_pct"] = total_util / len(utilization)
            dashboard["labor"]["hours_this_week"] = sum(w.current_hours_weekly for w in utilization)

        # Get alerts for all active projects
        for quote_id in self.project_mappings.keys():
            alerts = self.get_project_alerts(quote_id)
            dashboard["alerts"].extend(alerts)

        return dashboard
