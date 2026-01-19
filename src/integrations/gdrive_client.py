"""
Google Drive Integration for Document Management.

Connects to Google Drive for:
- Storing and organizing project documents
- Syncing design files and photos
- Managing quote attachments
- Archiving completed project files
"""

import io
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class DriveFile:
    """A file from Google Drive."""
    id: str
    name: str
    mime_type: str
    size_bytes: int = 0
    created_time: str = ""
    modified_time: str = ""
    parent_folder_id: Optional[str] = None
    web_view_link: str = ""
    download_link: str = ""


@dataclass
class DriveFolder:
    """A folder in Google Drive."""
    id: str
    name: str
    parent_id: Optional[str] = None
    path: str = ""
    file_count: int = 0
    subfolder_count: int = 0


@dataclass
class ProjectFolder:
    """Standardized project folder structure."""
    project_id: str
    project_name: str
    root_folder_id: str
    quote_folder_id: str = ""
    design_folder_id: str = ""
    photos_folder_id: str = ""
    documents_folder_id: str = ""
    archive_folder_id: str = ""


class GoogleDriveClient:
    """
    Client for Google Drive API integration.

    Handles:
    - Authentication via service account or OAuth
    - File/folder operations
    - Project folder structure management
    - Document syncing
    """

    # Standard project folder structure
    PROJECT_SUBFOLDERS = [
        "01_Quotes",
        "02_Designs",
        "03_Photos",
        "04_Documents",
        "05_Archive",
    ]

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        service_account_info: Optional[Dict] = None,
        root_folder_id: Optional[str] = None
    ):
        """
        Initialize Google Drive client.

        Args:
            credentials_path: Path to OAuth credentials JSON
            service_account_info: Service account credentials dict
            root_folder_id: Root folder ID for all projects
        """
        self.credentials_path = credentials_path
        self.service_account_info = service_account_info
        self.root_folder_id = root_folder_id
        self.service = None

    def _get_service(self):
        """Get or create Google Drive service client."""
        if self.service:
            return self.service

        try:
            from googleapiclient.discovery import build
            from google.oauth2 import service_account

            if self.service_account_info:
                credentials = service_account.Credentials.from_service_account_info(
                    self.service_account_info,
                    scopes=['https://www.googleapis.com/auth/drive']
                )
            elif self.credentials_path:
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=['https://www.googleapis.com/auth/drive']
                )
            else:
                raise ValueError("No Google Drive credentials provided")

            self.service = build('drive', 'v3', credentials=credentials)
            return self.service

        except ImportError:
            raise ImportError(
                "Google API client not installed. "
                "Run: pip install google-api-python-client google-auth"
            )

    def test_connection(self) -> Dict[str, Any]:
        """Test API connection and return account info."""
        try:
            service = self._get_service()
            about = service.about().get(fields="user,storageQuota").execute()

            return {
                "connected": True,
                "user_email": about.get("user", {}).get("emailAddress"),
                "storage_used": about.get("storageQuota", {}).get("usage"),
                "storage_limit": about.get("storageQuota", {}).get("limit"),
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }

    def list_files(
        self,
        folder_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        search_query: Optional[str] = None,
        max_results: int = 100
    ) -> List[DriveFile]:
        """
        List files in a folder or matching criteria.

        Args:
            folder_id: Parent folder ID (None for root)
            mime_type: Filter by MIME type
            search_query: Full-text search query
            max_results: Maximum files to return

        Returns:
            List of DriveFile objects
        """
        service = self._get_service()

        # Build query
        query_parts = ["trashed = false"]

        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")

        if mime_type:
            query_parts.append(f"mimeType = '{mime_type}'")

        if search_query:
            query_parts.append(f"fullText contains '{search_query}'")

        query = " and ".join(query_parts)

        results = service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink)",
        ).execute()

        files = []
        for f in results.get("files", []):
            files.append(DriveFile(
                id=f["id"],
                name=f["name"],
                mime_type=f["mimeType"],
                size_bytes=int(f.get("size", 0)),
                created_time=f.get("createdTime", ""),
                modified_time=f.get("modifiedTime", ""),
                parent_folder_id=f.get("parents", [None])[0],
                web_view_link=f.get("webViewLink", ""),
            ))

        return files

    def list_folders(
        self,
        parent_id: Optional[str] = None,
        search_name: Optional[str] = None
    ) -> List[DriveFolder]:
        """
        List folders.

        Args:
            parent_id: Parent folder ID
            search_name: Search by name

        Returns:
            List of DriveFolder objects
        """
        service = self._get_service()

        query_parts = [
            "trashed = false",
            "mimeType = 'application/vnd.google-apps.folder'"
        ]

        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")

        if search_name:
            query_parts.append(f"name contains '{search_name}'")

        query = " and ".join(query_parts)

        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, parents)",
        ).execute()

        folders = []
        for f in results.get("files", []):
            folders.append(DriveFolder(
                id=f["id"],
                name=f["name"],
                parent_id=f.get("parents", [None])[0],
            ))

        return folders

    def create_folder(
        self,
        name: str,
        parent_id: Optional[str] = None
    ) -> DriveFolder:
        """
        Create a new folder.

        Args:
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Created DriveFolder
        """
        service = self._get_service()

        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }

        if parent_id:
            file_metadata["parents"] = [parent_id]
        elif self.root_folder_id:
            file_metadata["parents"] = [self.root_folder_id]

        folder = service.files().create(
            body=file_metadata,
            fields="id, name, parents"
        ).execute()

        return DriveFolder(
            id=folder["id"],
            name=folder["name"],
            parent_id=folder.get("parents", [None])[0],
        )

    def create_project_folder(
        self,
        project_id: str,
        project_name: str,
        customer_name: Optional[str] = None
    ) -> ProjectFolder:
        """
        Create a standardized project folder structure.

        Creates:
        - Root project folder
        - Subfolders for quotes, designs, photos, documents, archive

        Args:
            project_id: Unique project identifier
            project_name: Project display name
            customer_name: Optional customer name for folder naming

        Returns:
            ProjectFolder with all folder IDs
        """
        # Create folder name
        date_str = datetime.now().strftime("%Y%m%d")
        if customer_name:
            folder_name = f"{date_str}_{customer_name}_{project_name}"
        else:
            folder_name = f"{date_str}_{project_name}"

        # Sanitize folder name
        folder_name = "".join(c for c in folder_name if c.isalnum() or c in " _-")

        # Create root project folder
        root_folder = self.create_folder(folder_name, self.root_folder_id)

        # Create subfolders
        subfolder_ids = {}
        for subfolder_name in self.PROJECT_SUBFOLDERS:
            subfolder = self.create_folder(subfolder_name, root_folder.id)
            subfolder_ids[subfolder_name] = subfolder.id

        return ProjectFolder(
            project_id=project_id,
            project_name=project_name,
            root_folder_id=root_folder.id,
            quote_folder_id=subfolder_ids.get("01_Quotes", ""),
            design_folder_id=subfolder_ids.get("02_Designs", ""),
            photos_folder_id=subfolder_ids.get("03_Photos", ""),
            documents_folder_id=subfolder_ids.get("04_Documents", ""),
            archive_folder_id=subfolder_ids.get("05_Archive", ""),
        )

    def upload_file(
        self,
        file_path: str,
        folder_id: Optional[str] = None,
        custom_name: Optional[str] = None
    ) -> DriveFile:
        """
        Upload a file to Google Drive.

        Args:
            file_path: Local file path
            folder_id: Destination folder ID
            custom_name: Custom file name (uses original if None)

        Returns:
            Uploaded DriveFile
        """
        from googleapiclient.http import MediaFileUpload

        service = self._get_service()
        path = Path(file_path)

        file_metadata = {
            "name": custom_name or path.name,
        }

        if folder_id:
            file_metadata["parents"] = [folder_id]

        # Determine MIME type
        mime_types = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".txt": "text/plain",
            ".csv": "text/csv",
        }
        mime_type = mime_types.get(path.suffix.lower(), "application/octet-stream")

        media = MediaFileUpload(file_path, mimetype=mime_type)

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, mimeType, size, webViewLink"
        ).execute()

        return DriveFile(
            id=file["id"],
            name=file["name"],
            mime_type=file["mimeType"],
            size_bytes=int(file.get("size", 0)),
            web_view_link=file.get("webViewLink", ""),
            parent_folder_id=folder_id,
        )

    def upload_content(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        folder_id: Optional[str] = None
    ) -> DriveFile:
        """
        Upload content directly to Google Drive.

        Args:
            content: File content as bytes
            filename: File name
            mime_type: MIME type
            folder_id: Destination folder ID

        Returns:
            Uploaded DriveFile
        """
        from googleapiclient.http import MediaIoBaseUpload

        service = self._get_service()

        file_metadata = {"name": filename}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype=mime_type,
            resumable=True
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, mimeType, size, webViewLink"
        ).execute()

        return DriveFile(
            id=file["id"],
            name=file["name"],
            mime_type=file["mimeType"],
            size_bytes=int(file.get("size", 0)),
            web_view_link=file.get("webViewLink", ""),
            parent_folder_id=folder_id,
        )

    def download_file(self, file_id: str) -> bytes:
        """
        Download a file's content.

        Args:
            file_id: File ID

        Returns:
            File content as bytes
        """
        from googleapiclient.http import MediaIoBaseDownload

        service = self._get_service()

        request = service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        return buffer.getvalue()

    def get_file_metadata(self, file_id: str) -> DriveFile:
        """Get metadata for a file."""
        service = self._get_service()

        file = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink"
        ).execute()

        return DriveFile(
            id=file["id"],
            name=file["name"],
            mime_type=file["mimeType"],
            size_bytes=int(file.get("size", 0)),
            created_time=file.get("createdTime", ""),
            modified_time=file.get("modifiedTime", ""),
            parent_folder_id=file.get("parents", [None])[0],
            web_view_link=file.get("webViewLink", ""),
        )

    def move_file(
        self,
        file_id: str,
        new_parent_id: str,
        old_parent_id: Optional[str] = None
    ) -> DriveFile:
        """
        Move a file to a different folder.

        Args:
            file_id: File ID
            new_parent_id: Destination folder ID
            old_parent_id: Current parent folder ID (will be looked up if not provided)

        Returns:
            Updated DriveFile
        """
        service = self._get_service()

        if not old_parent_id:
            file = service.files().get(
                fileId=file_id,
                fields="parents"
            ).execute()
            old_parent_id = file.get("parents", [""])[0]

        file = service.files().update(
            fileId=file_id,
            addParents=new_parent_id,
            removeParents=old_parent_id,
            fields="id, name, mimeType, parents, webViewLink"
        ).execute()

        return DriveFile(
            id=file["id"],
            name=file["name"],
            mime_type=file["mimeType"],
            parent_folder_id=new_parent_id,
            web_view_link=file.get("webViewLink", ""),
        )

    def delete_file(self, file_id: str, permanent: bool = False):
        """
        Delete or trash a file.

        Args:
            file_id: File ID
            permanent: If True, permanently delete. If False, move to trash.
        """
        service = self._get_service()

        if permanent:
            service.files().delete(fileId=file_id).execute()
        else:
            service.files().update(
                fileId=file_id,
                body={"trashed": True}
            ).execute()

    def share_folder(
        self,
        folder_id: str,
        email: str,
        role: str = "reader"
    ) -> Dict[str, Any]:
        """
        Share a folder with a user.

        Args:
            folder_id: Folder ID
            email: User's email address
            role: Permission role (reader, writer, commenter)

        Returns:
            Permission info
        """
        service = self._get_service()

        permission = {
            "type": "user",
            "role": role,
            "emailAddress": email,
        }

        result = service.permissions().create(
            fileId=folder_id,
            body=permission,
            sendNotificationEmail=True,
            fields="id, emailAddress, role"
        ).execute()

        return {
            "permission_id": result["id"],
            "email": result.get("emailAddress"),
            "role": result.get("role"),
        }

    def get_folder_link(self, folder_id: str) -> str:
        """Get shareable web link for a folder."""
        return f"https://drive.google.com/drive/folders/{folder_id}"

    def archive_project(
        self,
        project_folder: ProjectFolder
    ) -> Dict[str, Any]:
        """
        Archive a completed project.

        Moves all files to the archive subfolder and updates permissions.

        Args:
            project_folder: ProjectFolder to archive

        Returns:
            Archive summary
        """
        # Get all files in project folders
        source_folders = [
            project_folder.quote_folder_id,
            project_folder.design_folder_id,
            project_folder.photos_folder_id,
            project_folder.documents_folder_id,
        ]

        moved_count = 0
        for source_id in source_folders:
            if source_id:
                files = self.list_files(folder_id=source_id)
                for file in files:
                    self.move_file(
                        file.id,
                        project_folder.archive_folder_id,
                        source_id
                    )
                    moved_count += 1

        return {
            "project_id": project_folder.project_id,
            "archived": True,
            "files_moved": moved_count,
            "archive_folder": self.get_folder_link(project_folder.archive_folder_id),
        }

    def get_project_files_summary(
        self,
        project_folder: ProjectFolder
    ) -> Dict[str, Any]:
        """
        Get summary of all files in a project folder.

        Args:
            project_folder: ProjectFolder to summarize

        Returns:
            Summary with file counts and sizes by folder
        """
        summary = {
            "project_id": project_folder.project_id,
            "project_name": project_folder.project_name,
            "folders": {},
            "total_files": 0,
            "total_size_mb": 0,
        }

        folders = {
            "quotes": project_folder.quote_folder_id,
            "designs": project_folder.design_folder_id,
            "photos": project_folder.photos_folder_id,
            "documents": project_folder.documents_folder_id,
            "archive": project_folder.archive_folder_id,
        }

        total_size = 0
        total_files = 0

        for name, folder_id in folders.items():
            if folder_id:
                files = self.list_files(folder_id=folder_id)
                folder_size = sum(f.size_bytes for f in files)

                summary["folders"][name] = {
                    "file_count": len(files),
                    "size_mb": round(folder_size / (1024 * 1024), 2),
                    "files": [{"name": f.name, "type": f.mime_type} for f in files[:10]],
                }

                total_files += len(files)
                total_size += folder_size

        summary["total_files"] = total_files
        summary["total_size_mb"] = round(total_size / (1024 * 1024), 2)
        summary["drive_link"] = self.get_folder_link(project_folder.root_folder_id)

        return summary
