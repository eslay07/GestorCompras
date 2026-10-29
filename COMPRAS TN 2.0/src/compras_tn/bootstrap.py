from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from compras_tn.application.services import ApplicationFacade
from compras_tn.infrastructure.automation.downloads import SeleniumOrderDownloadGateway
from compras_tn.infrastructure.automation.purchase_orders import SeleniumPurchaseOrderGateway
from compras_tn.infrastructure.automation.telcos import SeleniumTelcosGateway
from compras_tn.infrastructure.db import Database, Repositories
from compras_tn.infrastructure.delivery import DeliveryQueue
from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway
from compras_tn.infrastructure.mail import CorporateMailGateway
from compras_tn.infrastructure.order_mail import PopOrderMailScanner
from compras_tn.infrastructure.orders import OrderFileService
from compras_tn.infrastructure.quotations import QuotationOrganizer
from compras_tn.infrastructure.reports import ExcelReportGateway
from compras_tn.infrastructure.seafile import SeafileHttpGateway
from compras_tn.infrastructure.templates import JinjaTemplateRenderer
from compras_tn.paths import AppPaths


@dataclass(slots=True)
class AppContainer:
    paths: AppPaths
    database: Database
    repositories: Repositories
    services: ApplicationFacade
    project_root: Path


def build_container(
    *, app_paths: AppPaths | None = None, project_root: Path | None = None
) -> AppContainer:
    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    paths = app_paths or AppPaths.default()
    paths.ensure()
    database = Database(paths.database, root)
    database.upgrade()
    repositories = Repositories(database)
    for key, value in {
        'seafile_url': 'https://telcodrive.telconet.net',
        'seafile_repo_id': '',
        'seafile_parent_dir': '/BD_TN',
    }.items():
        if repositories.get('downloads', key, None) is None:
            repositories.set('downloads', key, value)
    for key, value in {
        "google_sheet_id": "",
        "google_oc_sheet_name": "GENERAL",
    }.items():
        if repositories.get("google", key, None) is None:
            repositories.set("google", key, value)
    orders = OrderFileService(repositories, repositories)
    mail = CorporateMailGateway(repositories)
    seafile = SeafileHttpGateway(repositories)
    seafile.delivery = DeliveryQueue(database, seafile, repositories)
    sheets = GoogleSheetsGateway(repositories)
    services = ApplicationFacade(
        suppliers=repositories,
        settings=repositories,
        catalogs=repositories,
        inbox=repositories,
        jobs=repositories,
        mail=mail,
        telcos=SeleniumTelcosGateway(repositories, orders, paths),
        downloads=SeleniumOrderDownloadGateway(repositories, orders, seafile, paths),
        orders=orders,
        sheets=sheets,
        quotations=QuotationOrganizer(database, repositories, repositories, sheets, paths),
        renderer=JinjaTemplateRenderer(),
        order_mail=PopOrderMailScanner(database, repositories),
        reports=ExcelReportGateway(paths),
        seafile=seafile,
        purchases=SeleniumPurchaseOrderGateway(repositories, paths),
    )
    return AppContainer(
        paths=paths,
        database=database,
        repositories=repositories,
        services=services,
        project_root=root,
    )
