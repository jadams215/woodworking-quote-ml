"""
Monday.com Integration for Project Management.

Connects quotes to Monday.com boards for:
- Creating project boards from approved quotes
- Building sprints based on worker expertise
- Tracking project progress
- Managing resource allocation
"""

import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json


class TaskType(str, Enum):
    """Types of tasks in woodworking projects."""
    WOODWORK = "Woodwork"
    METALWORK = "Metalwork"
    FINISHING = "Finishing"
    POWDER_COATING = "Powder Coating"
    UPHOLSTERY = "Upholstery"
    ASSEMBLY = "Assembly"
    INSTALLATION = "Installation"
    DELIVERY = "Delivery"
    QC = "Quality Control"


@dataclass
class Employee:
    """Employee with skills and availability."""
    id: str
    name: str
    email: str
    skills: List[TaskType] = field(default_factory=list)
    skill_levels: Dict[str, int] = field(default_factory=dict)  # TaskType -> 1-5
    hourly_rate: float = 0.0
    hours_per_week: float = 40.0
    current_allocation_hours: float = 0.0  # Hours already committed

    @property
    def available_hours(self) -> float:
        """Hours available for new work."""
        return max(0, self.hours_per_week - self.current_allocation_hours)

    def expertise_for_task(self, task_type: TaskType) -> int:
        """Get expertise level (1-5) for a task type."""
        return self.skill_levels.get(task_type.value, 0)


@dataclass
class ProjectTask:
    """A task within a project."""
    id: str
    name: str
    task_type: TaskType
    estimated_hours: float
    assigned_to: Optional[str] = None  # Employee ID
    status: str = "Not Started"
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    actual_hours: float = 0.0
    dependencies: List[str] = field(default_factory=list)  # Task IDs
    notes: str = ""


@dataclass
class ProjectSprint:
    """A sprint/phase within a project."""
    id: str
    name: str
    start_date: str
    end_date: str
    tasks: List[ProjectTask] = field(default_factory=list)
    status: str = "Planned"


@dataclass
class MondayProject:
    """A project synced with Monday.com."""
    quote_id: str
    board_id: Optional[str] = None
    project_name: str = ""
    customer_name: str = ""
    sprints: List[ProjectSprint] = field(default_factory=list)
    team: List[str] = field(default_factory=list)  # Employee IDs
    total_hours: float = 0.0
    start_date: Optional[str] = None
    target_end_date: Optional[str] = None
    status: str = "Planning"


class MondayClient:
    """
    Client for Monday.com API integration.

    Handles:
    - Authentication
    - Creating/updating boards
    - Managing items (tasks)
    - Syncing project status
    """

    API_URL = "https://api.monday.com/v2"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Monday.com client.

        Args:
            api_key: Monday.com API key (from environment or config)
        """
        self.api_key = api_key
        self.headers = {
            "Authorization": api_key or "",
            "Content-Type": "application/json",
        }

        # Cache for employees and projects
        self._employees: Dict[str, Employee] = {}
        self._projects: Dict[str, MondayProject] = {}

    def _graphql_query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute a GraphQL query against Monday.com API."""
        if not self.api_key:
            raise ValueError("Monday.com API key not configured")

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = requests.post(
            self.API_URL,
            headers=self.headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def test_connection(self) -> Dict[str, Any]:
        """Test API connection and return account info."""
        query = """
        query {
            me {
                id
                name
                email
            }
            account {
                name
                plan {
                    tier
                }
            }
        }
        """
        try:
            result = self._graphql_query(query)
            return {
                "connected": True,
                "user": result.get("data", {}).get("me", {}),
                "account": result.get("data", {}).get("account", {}),
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }

    def get_boards(self) -> List[Dict]:
        """Get all boards in the workspace."""
        query = """
        query {
            boards(limit: 100) {
                id
                name
                state
                board_kind
            }
        }
        """
        result = self._graphql_query(query)
        return result.get("data", {}).get("boards", [])

    def create_project_board(
        self,
        quote_id: str,
        project_name: str,
        customer_name: str,
        template_board_id: Optional[str] = None
    ) -> str:
        """
        Create a new project board from an approved quote.

        Args:
            quote_id: Quote ID for reference
            project_name: Name of the project
            customer_name: Customer name
            template_board_id: Optional template board to duplicate

        Returns:
            Board ID of created board
        """
        board_name = f"{customer_name} - {project_name} ({quote_id})"

        if template_board_id:
            # Duplicate from template
            query = """
            mutation ($boardId: ID!, $boardName: String!) {
                duplicate_board(
                    board_id: $boardId,
                    duplicate_type: duplicate_board_with_structure,
                    board_name: $boardName
                ) {
                    board {
                        id
                    }
                }
            }
            """
            variables = {
                "boardId": template_board_id,
                "boardName": board_name,
            }
            result = self._graphql_query(query, variables)
            board_id = result["data"]["duplicate_board"]["board"]["id"]
        else:
            # Create new board
            query = """
            mutation ($boardName: String!) {
                create_board(
                    board_name: $boardName,
                    board_kind: public
                ) {
                    id
                }
            }
            """
            variables = {"boardName": board_name}
            result = self._graphql_query(query, variables)
            board_id = result["data"]["create_board"]["id"]

        # Store project reference
        self._projects[quote_id] = MondayProject(
            quote_id=quote_id,
            board_id=board_id,
            project_name=project_name,
            customer_name=customer_name,
        )

        return board_id

    def create_task(
        self,
        board_id: str,
        task: ProjectTask,
        group_id: Optional[str] = None
    ) -> str:
        """
        Create a task item on a board.

        Args:
            board_id: Board to add task to
            task: Task details
            group_id: Optional group/sprint to add to

        Returns:
            Item ID of created task
        """
        query = """
        mutation ($boardId: ID!, $itemName: String!, $groupId: String, $columnValues: JSON) {
            create_item(
                board_id: $boardId,
                item_name: $itemName,
                group_id: $groupId,
                column_values: $columnValues
            ) {
                id
            }
        }
        """

        column_values = {
            "status": {"label": task.status},
            "numbers": task.estimated_hours,
            "text": task.notes,
        }

        if task.start_date:
            column_values["date"] = {"date": task.start_date}
        if task.due_date:
            column_values["date4"] = {"date": task.due_date}

        variables = {
            "boardId": board_id,
            "itemName": f"{task.task_type.value}: {task.name}",
            "groupId": group_id,
            "columnValues": json.dumps(column_values),
        }

        result = self._graphql_query(query, variables)
        return result["data"]["create_item"]["id"]

    def get_users(self) -> List[Dict]:
        """Get all users in the workspace."""
        query = """
        query {
            users {
                id
                name
                email
            }
        }
        """
        result = self._graphql_query(query)
        return result.get("data", {}).get("users", [])

    def assign_person(self, board_id: str, item_id: str, person_id: str) -> bool:
        """Assign a person to a task."""
        query = """
        mutation ($boardId: ID!, $itemId: ID!, $columnId: String!, $value: JSON!) {
            change_column_value(
                board_id: $boardId,
                item_id: $itemId,
                column_id: $columnId,
                value: $value
            ) {
                id
            }
        }
        """
        variables = {
            "boardId": board_id,
            "itemId": item_id,
            "columnId": "person",
            "value": json.dumps({"personsAndTeams": [{"id": person_id, "kind": "person"}]}),
        }
        try:
            self._graphql_query(query, variables)
            return True
        except Exception:
            return False


class ResourceAllocator:
    """
    Allocates resources to project tasks based on expertise and availability.

    Optimizes for:
    - Matching skills to task requirements
    - Balancing workload across team
    - Minimizing time-to-value
    """

    def __init__(self, employees: List[Employee]):
        """Initialize with available employees."""
        self.employees = {e.id: e for e in employees}

    def find_best_worker(
        self,
        task_type: TaskType,
        required_hours: float,
        exclude_ids: Optional[List[str]] = None
    ) -> Optional[Employee]:
        """
        Find the best available worker for a task.

        Args:
            task_type: Type of task
            required_hours: Hours needed
            exclude_ids: Employee IDs to exclude

        Returns:
            Best matching employee or None
        """
        exclude_ids = exclude_ids or []
        candidates = []

        for emp in self.employees.values():
            if emp.id in exclude_ids:
                continue

            # Check if they have the skill
            expertise = emp.expertise_for_task(task_type)
            if expertise == 0:
                continue

            # Check availability
            if emp.available_hours < required_hours:
                continue

            # Score: expertise + availability factor
            availability_factor = emp.available_hours / emp.hours_per_week
            score = expertise * 2 + availability_factor

            candidates.append((emp, score))

        if not candidates:
            return None

        # Return highest scoring candidate
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def allocate_project(
        self,
        tasks: List[ProjectTask],
        start_date: datetime
    ) -> List[ProjectTask]:
        """
        Allocate workers to all tasks in a project.

        Args:
            tasks: List of tasks needing assignment
            start_date: Project start date

        Returns:
            Tasks with assignments and dates
        """
        assigned_tasks = []
        current_date = start_date

        # Sort tasks by dependencies and type
        # (simplified - production would use topological sort)
        task_order = sorted(tasks, key=lambda t: len(t.dependencies))

        for task in task_order:
            # Find best worker
            worker = self.find_best_worker(
                task.task_type,
                task.estimated_hours
            )

            if worker:
                task.assigned_to = worker.id

                # Update worker allocation
                worker.current_allocation_hours += task.estimated_hours

                # Calculate dates (simplified)
                hours_per_day = 8
                days_needed = task.estimated_hours / hours_per_day
                task.start_date = current_date.strftime("%Y-%m-%d")
                task.due_date = (current_date + timedelta(days=max(1, days_needed))).strftime("%Y-%m-%d")

            assigned_tasks.append(task)

        return assigned_tasks

    def build_sprints(
        self,
        tasks: List[ProjectTask],
        sprint_length_days: int = 5,
        start_date: datetime = None
    ) -> List[ProjectSprint]:
        """
        Organize tasks into sprints based on dependencies and capacity.

        Args:
            tasks: Tasks to organize
            sprint_length_days: Working days per sprint
            start_date: First sprint start date

        Returns:
            List of sprints with assigned tasks
        """
        start_date = start_date or datetime.now()
        sprints = []
        remaining_tasks = tasks.copy()
        sprint_number = 1

        while remaining_tasks:
            sprint_start = start_date + timedelta(days=(sprint_number - 1) * sprint_length_days)
            sprint_end = sprint_start + timedelta(days=sprint_length_days - 1)

            sprint = ProjectSprint(
                id=f"sprint-{sprint_number}",
                name=f"Sprint {sprint_number}",
                start_date=sprint_start.strftime("%Y-%m-%d"),
                end_date=sprint_end.strftime("%Y-%m-%d"),
            )

            # Calculate available hours per sprint
            hours_per_sprint = sprint_length_days * 8  # 8 hours/day
            hours_allocated = 0

            # Add tasks that fit in this sprint
            tasks_to_remove = []
            for task in remaining_tasks:
                # Check dependencies are met
                deps_met = all(
                    any(t.id == dep and t in [s for s in sprints for t in s.tasks] for t in tasks)
                    for dep in task.dependencies
                ) if task.dependencies else True

                if deps_met and hours_allocated + task.estimated_hours <= hours_per_sprint:
                    sprint.tasks.append(task)
                    hours_allocated += task.estimated_hours
                    tasks_to_remove.append(task)

            for task in tasks_to_remove:
                remaining_tasks.remove(task)

            if sprint.tasks:
                sprints.append(sprint)
                sprint_number += 1
            else:
                # No tasks fit, force add one to prevent infinite loop
                if remaining_tasks:
                    sprint.tasks.append(remaining_tasks.pop(0))
                    sprints.append(sprint)
                    sprint_number += 1

        return sprints

    def calculate_time_to_value(
        self,
        tasks: List[ProjectTask],
        team: List[Employee]
    ) -> Dict[str, Any]:
        """
        Calculate time-to-value metrics for resource allocation.

        Args:
            tasks: Project tasks
            team: Assigned team members

        Returns:
            Metrics including total time, bottlenecks, recommendations
        """
        total_hours = sum(t.estimated_hours for t in tasks)
        team_capacity = sum(e.available_hours for e in team)

        # Calculate by task type
        hours_by_type = {}
        for task in tasks:
            task_type = task.task_type.value
            hours_by_type[task_type] = hours_by_type.get(task_type, 0) + task.estimated_hours

        # Find bottlenecks (tasks without skilled workers)
        bottlenecks = []
        for task in tasks:
            skilled_workers = [
                e for e in team
                if e.expertise_for_task(task.task_type) >= 3
            ]
            if not skilled_workers:
                bottlenecks.append({
                    "task": task.name,
                    "type": task.task_type.value,
                    "issue": "No highly skilled worker available",
                })

        # Recommendations
        recommendations = []
        if total_hours > team_capacity:
            recommendations.append(
                f"Project requires {total_hours:.0f} hours but team has {team_capacity:.0f} available. "
                "Consider extending timeline or adding resources."
            )

        for task_type, hours in hours_by_type.items():
            experts = [e for e in team if e.expertise_for_task(TaskType(task_type)) >= 4]
            if not experts and hours > 16:
                recommendations.append(
                    f"{task_type} requires {hours:.0f} hours but no expert assigned. "
                    "Consider training or hiring."
                )

        return {
            "total_hours": total_hours,
            "team_capacity": team_capacity,
            "utilization_pct": (total_hours / team_capacity * 100) if team_capacity > 0 else 0,
            "hours_by_type": hours_by_type,
            "bottlenecks": bottlenecks,
            "recommendations": recommendations,
            "estimated_weeks": total_hours / 40 if total_hours > 0 else 0,
        }


def create_tasks_from_quote(quote_params: Dict[str, Any], labor_hours: float) -> List[ProjectTask]:
    """
    Generate project tasks from a quote's parameters.

    Args:
        quote_params: Quote parameters
        labor_hours: Estimated total labor hours

    Returns:
        List of project tasks
    """
    tasks = []
    task_id = 1

    # Distribute hours based on work types
    work_types = []
    if quote_params.get('has_woodwork', True):
        work_types.append((TaskType.WOODWORK, 0.35))
    if quote_params.get('has_metalwork', False):
        work_types.append((TaskType.METALWORK, 0.20))
    if quote_params.get('has_finishing', True):
        work_types.append((TaskType.FINISHING, 0.20))
    if quote_params.get('has_powder_coating', False):
        work_types.append((TaskType.POWDER_COATING, 0.10))
    if quote_params.get('has_upholstery', False):
        work_types.append((TaskType.UPHOLSTERY, 0.15))

    # Normalize ratios
    total_ratio = sum(r for _, r in work_types)
    if total_ratio > 0:
        work_types = [(t, r / total_ratio) for t, r in work_types]

    # Create tasks for each work type
    for task_type, ratio in work_types:
        hours = labor_hours * ratio
        tasks.append(ProjectTask(
            id=f"task-{task_id}",
            name=f"{task_type.value} - Main work",
            task_type=task_type,
            estimated_hours=hours,
        ))
        task_id += 1

    # Add assembly task
    tasks.append(ProjectTask(
        id=f"task-{task_id}",
        name="Assembly",
        task_type=TaskType.ASSEMBLY,
        estimated_hours=labor_hours * 0.15,
        dependencies=[t.id for t in tasks],  # Depends on all previous
    ))
    task_id += 1

    # Add QC task
    tasks.append(ProjectTask(
        id=f"task-{task_id}",
        name="Quality Control",
        task_type=TaskType.QC,
        estimated_hours=max(2, labor_hours * 0.05),
        dependencies=[f"task-{task_id - 1}"],
    ))
    task_id += 1

    # Add installation if required
    if quote_params.get('installation_required', False):
        tasks.append(ProjectTask(
            id=f"task-{task_id}",
            name="Installation",
            task_type=TaskType.INSTALLATION,
            estimated_hours=labor_hours * 0.25,
            dependencies=[f"task-{task_id - 1}"],
        ))
        task_id += 1

    # Add delivery
    if quote_params.get('delivery_miles', 0) > 0:
        tasks.append(ProjectTask(
            id=f"task-{task_id}",
            name="Delivery",
            task_type=TaskType.DELIVERY,
            estimated_hours=max(2, quote_params.get('delivery_miles', 0) / 30),  # ~30 mph average
            dependencies=[f"task-{task_id - 1}"],
        ))

    return tasks
