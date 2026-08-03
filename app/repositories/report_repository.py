from app.models.research_report import ResearchReport
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[ResearchReport]):
    model = ResearchReport
