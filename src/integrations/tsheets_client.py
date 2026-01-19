"""
TSheets (QuickBooks Time) Integration for Labor Tracking.

Connects to TSheets for:
- Pulling actual labor hours by employee and project
- Tracking employee availability
- Analyzing labor efficiency vs estimates
- Building employee skill profiles
"""

import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from collections import defaultdict


@dataclass
class TimeEntry:
    """A time entry from TSheets."""
    id: str
    employee_id: str
    employee_name: str
    job_code: str  # Project/task identifier
    date: str
    hours: float
    notes: str = ""
    billable: bool = True
    approved: bool = False


@dataclass
class EmployeeHours:
    """Aggregated hours for an employee."""
    employee_id: str
    employee_name: str
    total_hours: float
    hours_by_job: Dict[str, float] = field(default_factory=dict)
    hours_by_task_type: Dict[str, float] = field(default_factory=dict)
    days_worked: int = 0
    avg_hours_per_day: float = 0.0


@dataclass
class ProjectLabor:
    """Labor summary for a project."""
    project_id: str
    project_name: str
    total_hours: float
    hours_by_employee: Dict[str, float] = field(default_factory=dict)
    hours_by_task: Dict[str, float] = field(default_factory=dict)
    estimated_hours: float = 0.0
    variance_hours: float = 0.0
    variance_pct: float = 0.0


@dataclass
class EmployeeSkillProfile:
    """Employee skill profile derived from time entries."""
    employee_id: str
    employee_name: str
    total_hours_tracked: float
    hours_by_task_type: Dict[str, float] = field(default_factory=dict)
    efficiency_scores: Dict[str, float] = field(default_factory=dict)  # task -> efficiency
    primary_skills: List[str] = field(default_factory=list)
    availability_hours_per_week: float = 40.0
    current_utilization_pct: float = 0.0


class TSheetsClient:
    """
    Client for TSheets (QuickBooks Time) API integration.

    Handles:
    - Authentication
    - Fetching time entries
    - Aggregating labor data
    - Building skill profiles
    """

    BASE_URL = "https://rest.tsheets.com/api/v1"

    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize TSheets client.

        Args:
            access_token: TSheets API access token
        """
        self.access_token = access_token

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _api_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict:
        """Make an API request to TSheets."""
        if not self.access_token:
            raise ValueError("TSheets access token not configured")

        url = f"{self.BASE_URL}/{endpoint}"

        response = requests.request(
            method,
            url,
            headers=self._get_headers(),
            params=params,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def test_connection(self) -> Dict[str, Any]:
        """Test API connection and return current user info."""
        try:
            result = self._api_request("GET", "current_user")
            user = result.get("results", {}).get("users", {})
            if user:
                user_data = list(user.values())[0]
                return {
                    "connected": True,
                    "user_name": f"{user_data.get('first_name')} {user_data.get('last_name')}",
                    "company": user_data.get("company_name"),
                }
            return {"connected": True}
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }

    def get_users(self) -> List[Dict]:
        """Get all users/employees."""
        result = self._api_request("GET", "users", params={"active": "yes"})
        users = result.get("results", {}).get("users", {})
        return list(users.values())

    def get_jobcodes(self) -> List[Dict]:
        """Get all job codes (projects/tasks)."""
        result = self._api_request("GET", "jobcodes", params={"active": "yes"})
        jobcodes = result.get("results", {}).get("jobcodes", {})
        return list(jobcodes.values())

    def get_timesheets(
        self,
        start_date: str,
        end_date: str,
        user_ids: Optional[List[str]] = None,
        jobcode_ids: Optional[List[str]] = None
    ) -> List[TimeEntry]:
        """
        Get timesheets for a date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            user_ids: Filter by specific users
            jobcode_ids: Filter by specific job codes

        Returns:
            List of time entries
        """
        params = {
            "start_date": start_date,
            "end_date": end_date,
        }
        if user_ids:
            params["user_ids"] = ",".join(user_ids)
        if jobcode_ids:
            params["jobcode_ids"] = ",".join(jobcode_ids)

        result = self._api_request("GET", "timesheets", params=params)
        timesheets = result.get("results", {}).get("timesheets", {})

        # Also get user names
        users = {u["id"]: f"{u.get('first_name', '')} {u.get('last_name', '')}"
                 for u in self.get_users()}

        entries = []
        for ts in timesheets.values():
            duration_seconds = ts.get("duration", 0)
            hours = duration_seconds / 3600 if duration_seconds else 0

            entry = TimeEntry(
                id=str(ts.get("id")),
                employee_id=str(ts.get("user_id")),
                employee_name=users.get(str(ts.get("user_id")), "Unknown"),
                job_code=str(ts.get("jobcode_id")),
                date=ts.get("date"),
                hours=hours,
                notes=ts.get("notes", ""),
                billable=ts.get("billable", True),
                approved=ts.get("approved", False),
            )
            entries.append(entry)

        return entries

    def get_employee_hours(
        self,
        employee_id: str,
        start_date: str,
        end_date: str
    ) -> EmployeeHours:
        """
        Get hours summary for an employee.

        Args:
            employee_id: Employee ID
            start_date: Start date
            end_date: End date

        Returns:
            EmployeeHours summary
        """
        entries = self.get_timesheets(
            start_date=start_date,
            end_date=end_date,
            user_ids=[employee_id]
        )

        total_hours = 0
        hours_by_job = defaultdict(float)
        dates_worked = set()
        employee_name = "Unknown"

        for entry in entries:
            total_hours += entry.hours
            hours_by_job[entry.job_code] += entry.hours
            dates_worked.add(entry.date)
            employee_name = entry.employee_name

        days_worked = len(dates_worked)

        return EmployeeHours(
            employee_id=employee_id,
            employee_name=employee_name,
            total_hours=total_hours,
            hours_by_job=dict(hours_by_job),
            days_worked=days_worked,
            avg_hours_per_day=total_hours / days_worked if days_worked > 0 else 0,
        )

    def get_project_labor(
        self,
        project_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> ProjectLabor:
        """
        Get labor summary for a project.

        Args:
            project_id: Job code ID for the project
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            ProjectLabor summary
        """
        # Default to last 90 days if no dates
        if not start_date:
            start_date = (date.today() - timedelta(days=90)).isoformat()
        if not end_date:
            end_date = date.today().isoformat()

        entries = self.get_timesheets(
            start_date=start_date,
            end_date=end_date,
            jobcode_ids=[project_id]
        )

        total_hours = 0
        hours_by_employee = defaultdict(float)
        hours_by_task = defaultdict(float)

        for entry in entries:
            total_hours += entry.hours
            hours_by_employee[entry.employee_name] += entry.hours
            # Parse task from notes or job code
            task = entry.notes.split(":")[0] if ":" in entry.notes else "General"
            hours_by_task[task] += entry.hours

        return ProjectLabor(
            project_id=project_id,
            project_name=project_id,  # Would lookup
            total_hours=total_hours,
            hours_by_employee=dict(hours_by_employee),
            hours_by_task=dict(hours_by_task),
        )

    def build_skill_profile(
        self,
        employee_id: str,
        lookback_days: int = 180
    ) -> EmployeeSkillProfile:
        """
        Build a skill profile for an employee based on time entries.

        Analyzes past work to determine:
        - Primary skills/task types
        - Efficiency compared to estimates
        - Current utilization

        Args:
            employee_id: Employee ID
            lookback_days: Days of history to analyze

        Returns:
            EmployeeSkillProfile
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        hours = self.get_employee_hours(
            employee_id=employee_id,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat()
        )

        # Analyze task types from job codes
        hours_by_task_type = defaultdict(float)
        jobcodes = {str(j["id"]): j for j in self.get_jobcodes()}

        for job_id, job_hours in hours.hours_by_job.items():
            jobcode = jobcodes.get(job_id, {})
            task_type = self._classify_task_type(jobcode.get("name", ""))
            hours_by_task_type[task_type] += job_hours

        # Determine primary skills (top 3 by hours)
        sorted_tasks = sorted(hours_by_task_type.items(), key=lambda x: x[1], reverse=True)
        primary_skills = [t[0] for t in sorted_tasks[:3]]

        # Calculate current utilization (last 2 weeks)
        recent_start = (end_date - timedelta(days=14)).isoformat()
        recent_hours = self.get_employee_hours(
            employee_id=employee_id,
            start_date=recent_start,
            end_date=end_date.isoformat()
        )

        # Assuming 80 hours available in 2 weeks
        expected_hours = 80
        current_utilization = (recent_hours.total_hours / expected_hours) * 100

        return EmployeeSkillProfile(
            employee_id=employee_id,
            employee_name=hours.employee_name,
            total_hours_tracked=hours.total_hours,
            hours_by_task_type=dict(hours_by_task_type),
            primary_skills=primary_skills,
            current_utilization_pct=min(100, current_utilization),
        )

    def get_team_availability(
        self,
        user_ids: Optional[List[str]] = None,
        weeks_ahead: int = 2
    ) -> Dict[str, Dict]:
        """
        Get team availability for upcoming weeks.

        Args:
            user_ids: Specific users to check, or all if None
            weeks_ahead: Number of weeks to look ahead

        Returns:
            Dict of employee_id -> availability info
        """
        if not user_ids:
            users = self.get_users()
            user_ids = [str(u["id"]) for u in users]

        # Get recent timesheets to estimate typical hours
        end_date = date.today()
        start_date = end_date - timedelta(days=28)

        availability = {}

        for user_id in user_ids:
            hours = self.get_employee_hours(
                employee_id=user_id,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat()
            )

            # Estimate typical weekly hours
            weeks_in_period = 4
            typical_weekly = hours.total_hours / weeks_in_period

            # Available = capacity - current load (simplified)
            weekly_capacity = 40  # Standard work week
            available_per_week = max(0, weekly_capacity - typical_weekly * 0.8)

            availability[user_id] = {
                "employee_name": hours.employee_name,
                "typical_weekly_hours": typical_weekly,
                "available_hours_per_week": available_per_week,
                "total_available_hours": available_per_week * weeks_ahead,
                "utilization_pct": (typical_weekly / weekly_capacity) * 100,
            }

        return availability

    def _classify_task_type(self, job_name: str) -> str:
        """Classify a job code name into a task type."""
        name_lower = job_name.lower()

        if any(w in name_lower for w in ['wood', 'cabinet', 'millwork', 'carpentry']):
            return "Woodwork"
        elif any(w in name_lower for w in ['metal', 'weld', 'steel']):
            return "Metalwork"
        elif any(w in name_lower for w in ['finish', 'paint', 'stain', 'lacquer']):
            return "Finishing"
        elif any(w in name_lower for w in ['powder', 'coat']):
            return "Powder Coating"
        elif any(w in name_lower for w in ['uphol', 'fabric', 'foam']):
            return "Upholstery"
        elif any(w in name_lower for w in ['install']):
            return "Installation"
        elif any(w in name_lower for w in ['deliver', 'ship']):
            return "Delivery"
        elif any(w in name_lower for w in ['assembl']):
            return "Assembly"
        elif any(w in name_lower for w in ['qc', 'quality', 'inspect']):
            return "QC"
        else:
            return "General"

    def compare_estimate_vs_actual(
        self,
        project_id: str,
        estimated_hours: float
    ) -> Dict[str, Any]:
        """
        Compare estimated vs actual hours for a project.

        Args:
            project_id: Job code for the project
            estimated_hours: Original estimated hours

        Returns:
            Comparison metrics
        """
        labor = self.get_project_labor(project_id)

        variance = labor.total_hours - estimated_hours
        variance_pct = (variance / estimated_hours * 100) if estimated_hours > 0 else 0

        return {
            "project_id": project_id,
            "estimated_hours": estimated_hours,
            "actual_hours": labor.total_hours,
            "variance_hours": variance,
            "variance_pct": variance_pct,
            "status": "Under" if variance < 0 else "Over" if variance > 0 else "On Target",
            "hours_by_employee": labor.hours_by_employee,
            "hours_by_task": labor.hours_by_task,
        }
