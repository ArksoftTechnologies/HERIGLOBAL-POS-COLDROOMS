# API Endpoints Documentation

## Authentication
- `GET/POST /auth/login`: User login.
- `GET /auth/logout`: User logout.
- `GET/POST /auth/register`: Register new user (Super Admin only).

## Dashboard
- `GET /dashboard/`: Redirects to role-specific dashboard.
- `GET /admin/dashboard`: Super Admin Executive Dashboard.
- `GET /admin/dashboard/api/summary`: Executive summary statistics (JSON).
- `GET /admin/dashboard/api/outlets`: Outlet performance data (JSON).
- `GET /admin/dashboard/api/trends`: Sales trend data (JSON).

## POS (Point of Sale)
- `GET /pos/`: POS Interface.
- `GET /pos/api/products`: Search products for POS.
- `POST /pos/checkout`: Process a sale.

## Sales
- `GET /sales/`: List sales history.
- `GET /sales/<id>`: View sale details.

## Inventory
- `GET /inventory/`: List inventory for current outlet.
- `GET /inventory/transfer`: Stock transfer management.
- `POST /inventory/transfer/create`: Initiate stock transfer.

## Reports
- `GET /reports/`: Reports Dashboard.
- `GET /reports/sales/summary`: Sales summary report.
- `GET /reports/sales/detailed`: Detailed sales log.
- `GET /reports/inventory/balance-sheet`: Stock movement analysis.
- `GET /reports/inventory/low-stock`: Low stock alerts.

*Note: Most endpoints return HTML. API endpoints returning JSON are explicitly marked.*
